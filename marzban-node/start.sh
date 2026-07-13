#!/usr/bin/env bash
# Railway / container entrypoint for the combined Marzban panel + Marzban-node.
#
# What it does, in order:
#   1. Run DB migrations.
#   2. Create the sudo admin from env (idempotent).
#   3. Start the Marzban-node service in the BACKGROUND (loopback 127.0.0.1).
#   4. Start the Marzban panel (uvicorn on $PORT) in the BACKGROUND.
#   5. Once the panel is up, AUTO-REGISTER the local node with the panel so the
#      node is connected to the panel immediately after deploy — no manual step.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The node sources live in /code (this folder); the panel lives in /panel.
NODE_DIR="/code"
PANEL_DIR="/panel"

# --- env plumbing ---------------------------------------------------------
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export UVICORN_HOST="${HOST}"
export UVICORN_PORT="${PORT}"

# Node binds loopback; the panel connects to it as an internal proxy.
export SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"
export SERVICE_PROTOCOL="${SERVICE_PROTOCOL:-rest}"
export SERVICE_TLS="${SERVICE_TLS:-true}"
export SSL_DIR="${SSL_DIR:-/var/lib/marzban-node}"

echo "==> [railway] HOST=${HOST} PORT=${PORT} NODE_HOST=${SERVICE_HOST}"

# --- 1. migrations --------------------------------------------------------
echo "==> [railway] Running database migrations (alembic upgrade head)..."
( cd "$PANEL_DIR" && alembic upgrade head ) || {
    echo "!! [railway] alembic upgrade failed; attempting create-all fallback..."
    ( cd "$PANEL_DIR" && python - <<'PY'
import app.db.base as b
try:
    b.Base.metadata.create_all(bind=b.engine)
    print("create_all() succeeded")
except Exception as e:
    print("create_all() also failed:", e)
PY
    )
}

# --- 2. admin -------------------------------------------------------------
if [ -n "${SUDO_USERNAME:-}" ] && [ -n "${SUDO_PASSWORD:-}" ]; then
    echo "==> [railway] Ensuring admin '${SUDO_USERNAME}' exists..."
    ( cd "$PANEL_DIR" && python create_admin.py \
        --username "$SUDO_USERNAME" \
        --password "$SUDO_PASSWORD" \
        --sudo ) || echo "!! [railway] admin creation reported an issue (continuing)"
else
    echo "==> [railway] SUDO_USERNAME/SUDO_PASSWORD not set; skipping auto admin creation."
fi

# --- 3. start Marzban-node (background, loopback) -------------------------
echo "==> [railway] Starting Marzban-node on ${SERVICE_HOST}:${SERVICE_PORT:-62050} ..."
cd "$NODE_DIR"
python main.py > /var/lib/marzban-node/node.log 2>&1 &
NODE_PID=$!
echo "    node pid=${NODE_PID}"

# --- 4. start Marzban panel (background) ----------------------------------
echo "==> [railway] Starting Marzban panel on ${HOST}:${PORT} ..."
cd "$PANEL_DIR"
uvicorn main:app --host "$HOST" --port "$PORT" --workers 1 --log-level info > /var/lib/marzban/panel.log 2>&1 &
PANEL_PID=$!
echo "    panel pid=${PANEL_PID}"

# --- 5. auto-register the node with the panel -----------------------------
# Poll the panel health endpoint until it serves, then register the local
# node via the REST API using the admin token. Idempotent: if the node already
# exists, the call fails gracefully and we proceed.
register_node() {
    local base="http://127.0.0.1:${PORT}"
    local node_addr="${MARZBAN_NODE_ADDRESS:-127.0.0.1}"
    local node_port="${MARZBAN_NODE_PORT:-62050}"
    local api_port="${MARZBAN_NODE_API_PORT:-62051}"
    local node_name="${MARZBAN_NODE_NAME:-local-node}"

    # Wait for the panel to answer.
    for i in $(seq 1 60); do
        if curl -fsS "${base}/" >/dev/null 2>&1; then break; fi
        sleep 1
    done

    if [ -z "${SUDO_USERNAME:-}" ] || [ -z "${SUDO_PASSWORD:-}" ]; then
        echo "!! [railway] Cannot auto-register node without SUDO_USERNAME/SUDO_PASSWORD; skipping."
        return 0
    fi

    echo "==> [railway] Obtaining admin token to auto-register node..."
    local token
    token=$(curl -fsS -X POST "${base}/api/admin/token" \
        -d "username=${SUDO_USERNAME}" -d "password=${SUDO_PASSWORD}" \
        | python -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

    if [ -z "${token}" ]; then
        echo "!! [railway] Failed to obtain admin token; skipping node registration."
        return 0
    fi

    echo "==> [railway] Registering node '${node_name}' (${node_addr}:${node_port}) ..."
    curl -fsS -X POST "${base}/api/node" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"${node_name}\",\"address\":\"${node_addr}\",\"port\":${node_port},\"api_port\":${api_port},\"add_as_new_host\":true}" \
        && echo "    node registered." \
        || echo "    node already registered or registration failed (continuing)."
}

register_node &   # run concurrently; does not block the panel

# --- keep both processes alive -------------------------------------------
# If either dies, the container should restart (Railway on_failure), so we
# just wait and surface logs on exit.
wait -n || true
echo "==> [railway] A child process exited; dumping logs and stopping."
echo "----- panel.log -----"; tail -n 50 /var/lib/marzban/panel.log 2>/dev/null || true
echo "----- node.log -----";  tail -n 50 /var/lib/marzban-node/node.log 2>/dev/null || true
kill "$NODE_PID" "$PANEL_PID" 2>/dev/null || true
