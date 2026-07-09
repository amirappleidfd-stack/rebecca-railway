#!/usr/bin/env bash
# Railway entrypoint for Marzban.
# 1. Run database migrations.
# 2. Create the admin user from env (idempotent — never fails if it exists).
# 3. Start uvicorn bound to $PORT (Railway injects this), HOST=0.0.0.0.
set -euo pipefail

# Resolve the directory containing this script so it works regardless of CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
# uvicorn reads UVICORN_PORT / UVICORN_HOST from config.py; keep them in sync.
export UVICORN_HOST="${HOST}"
export UVICORN_PORT="${PORT}"

echo "==> [railway] Using HOST=${HOST} PORT=${PORT}"

# 1. Database migrations -----------------------------------------------------
echo "==> [railway] Running database migrations (alembic upgrade head)..."
alembic upgrade head || {
    echo "!! [railway] alembic upgrade failed; attempting create-all fallback..."
    python - <<'PY'
import app.db.base as b
try:
    b.Base.metadata.create_all(bind=b.engine)
    print("create_all() succeeded")
except Exception as e:
    print("create_all() also failed:", e)
PY
}

# 2. Create admin (idempotent) ----------------------------------------------
if [ -n "${SUDO_USERNAME:-}" ] && [ -n "${SUDO_PASSWORD:-}" ]; then
    echo "==> [railway] Ensuring admin '${SUDO_USERNAME}' exists..."
    python create_admin.py \
        --username "$SUDO_USERNAME" \
        --password "$SUDO_PASSWORD" \
        --sudo || echo "!! [railway] admin creation reported an issue (continuing)"
else
    echo "==> [railway] SUDO_USERNAME/SUDO_PASSWORD not set; skipping auto admin creation."
    echo "    Create one later with: marzban-cli admin create ..."
fi

# 3. Start the server --------------------------------------------------------
echo "==> [railway] Starting Marzban on ${HOST}:${PORT}"
exec uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 1 \
    --log-level info
