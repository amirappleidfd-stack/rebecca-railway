"""
Spider Xray manager — self-contained Xray-core lifecycle + VLESS-WS subscription
builder tuned for a single-container Railway deployment.

Responsibilities (see project spec):
  1. Detect/install the official Xray-core binary at /app/xray-core/xray.
  2. Detect the Railway public TCP proxy domain/port.
  3. Generate /app/xray-config/config.json automatically (never static).
  4. Validate it with `xray run -test -config ...` before use.
  5. Build correct VLESS-WS subscription links that use the EXTERNAL Railway
     TCP proxy domain:port (never the internal listening port).

This module deliberately does NOT touch Marzban's own Xray core, database,
dashboard, users, or authentication. It reads the same user UUIDs Marzban
stores (Proxy.settings["id"] for vless proxies) so the two stay in sync.
"""

import json
import logging
import os
import shutil
import stat
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger("uvicorn.error")

# --- Paths (spec-mandated) --------------------------------------------------
XRAY_CORE_DIR = Path(os.environ.get("SPIDER_XRAY_CORE_DIR", "/app/xray-core"))
XRAY_BINARY = XRAY_CORE_DIR / "xray"
XRAY_CONFIG_DIR = Path(os.environ.get("SPIDER_XRAY_CONFIG_DIR", "/app/xray-config"))
XRAY_CONFIG_PATH = XRAY_CONFIG_DIR / "config.json"

XRAY_DOWNLOAD_URL = (
    "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
)

# --- Inbound settings -------------------------------------------------------
# Internal listening port for the VLESS WS inbound. This is NOT the port that
# ends up in subscription links — links always use the Railway TCP proxy port.
INBOUND_LISTEN = os.environ.get("SPIDER_INBOUND_LISTEN", "0.0.0.0")
INBOUND_PORT = int(os.environ.get("SPIDER_INBOUND_PORT", "443"))
# The base WS path. Per-user links use /ws/<uuid>; the FastAPI relay
# (app/routers/spider.py) maps /ws/<uuid> onto this base path upstream.
WS_BASE_PATH = os.environ.get("SPIDER_WS_BASE_PATH", "/ws")

REMARK = os.environ.get("SPIDER_REMARK", "Spider")


# ===========================================================================
# 1. Xray Core detection / installation
# ===========================================================================
def _run_version(binary: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            [str(binary), "version"], stderr=subprocess.STDOUT, timeout=30
        ).decode("utf-8", "replace")
        first = out.strip().splitlines()[0] if out.strip() else out.strip()
        return first
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Xray] version check failed: {e}")
        return None


def install_xray(force: bool = False) -> Path:
    """Download and install the official Xray-core binary. Returns its path.

    Raises RuntimeError if installation fails.
    """
    if XRAY_BINARY.exists() and not force:
        return XRAY_BINARY

    XRAY_CORE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = XRAY_CORE_DIR / "xray.zip"

    logger.info(f"[Xray] Downloading Xray-core from {XRAY_DOWNLOAD_URL}")
    try:
        with urllib.request.urlopen(XRAY_DOWNLOAD_URL, timeout=120) as resp, open(
            zip_path, "wb"
        ) as fh:
            shutil.copyfileobj(resp, fh)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"[Xray] download failed: {e}") from e

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(XRAY_CORE_DIR)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"[Xray] unzip failed: {e}") from e
    finally:
        try:
            zip_path.unlink()
        except OSError:
            pass

    if not XRAY_BINARY.exists():
        raise RuntimeError(
            f"[Xray] binary not found at {XRAY_BINARY} after extraction"
        )

    # chmod +x
    st = os.stat(XRAY_BINARY)
    os.chmod(XRAY_BINARY, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    version = _run_version(XRAY_BINARY)
    if not version:
        raise RuntimeError("[Xray] installed binary failed `xray version`")
    logger.info(f"[Xray] Installed successfully: {version}")
    return XRAY_BINARY


def ensure_xray() -> Path:
    """Ensure the Xray binary exists and is runnable. Install if missing.

    Stops startup (raises RuntimeError) if installation fails.
    """
    if XRAY_BINARY.exists():
        version = _run_version(XRAY_BINARY)
        if version:
            logger.info(f"[Xray] Binary found: {XRAY_BINARY}")
            logger.info(f"[Xray] Version: {version}")
            return XRAY_BINARY
        logger.warning("[Xray] Existing binary is not runnable; reinstalling")
        return install_xray(force=True)

    logger.info("[Xray] Binary missing; installing...")
    return install_xray()


# ===========================================================================
# 2. Railway environment / domain detection
# ===========================================================================
def detect_railway_endpoint(
    wait: bool = False, retry_seconds: int = 10, max_attempts: int = 0
) -> Optional[Tuple[str, int]]:
    """Return (domain, port) for the public Railway TCP proxy, or None.

    Priority:
      1. RAILWAY_TCP_PROXY_DOMAIN + RAILWAY_TCP_PROXY_PORT
      2. RAILWAY_PUBLIC_DOMAIN (port falls back to 443)

    When wait=True, retries every `retry_seconds` until a domain appears
    (or max_attempts is reached, 0 = infinite).
    """
    attempt = 0
    while True:
        domain = os.environ.get("RAILWAY_TCP_PROXY_DOMAIN", "").strip()
        port_raw = os.environ.get("RAILWAY_TCP_PROXY_PORT", "").strip()

        if domain and port_raw:
            try:
                port = int(port_raw)
                logger.info(f"[Railway] TCP Domain: {domain}")
                logger.info(f"[Railway] TCP Port: {port}")
                return domain, port
            except ValueError:
                logger.warning(f"[Railway] invalid TCP proxy port: {port_raw!r}")

        public = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if public:
            port = int(os.environ.get("RAILWAY_TCP_PROXY_PORT", "443") or 443)
            logger.info(f"[Railway] Public Domain (fallback): {public}")
            logger.info(f"[Railway] TCP Port: {port}")
            return public, port

        if not wait:
            return None

        attempt += 1
        if max_attempts and attempt >= max_attempts:
            logger.warning("[Railway] domain still missing after max attempts")
            return None
        logger.warning(
            f"[Railway] TCP proxy domain not available yet; "
            f"retrying in {retry_seconds}s (attempt {attempt})"
        )
        time.sleep(retry_seconds)


# ===========================================================================
# 3. Config generation
# ===========================================================================
def _collect_vless_clients() -> List[dict]:
    """Read active users' VLESS UUIDs from Marzban's database.

    Returns a list of xray client dicts: {"id": uuid, "email": ...}.
    Never raises — returns [] if the DB is unavailable.
    """
    clients: List[dict] = []
    try:
        from app.db import GetDB, crud
        from app.models.proxy import ProxyTypes
        from app.models.user import UserStatus

        with GetDB() as db:
            users = crud.get_users(db, status=UserStatus.active)
            if isinstance(users, tuple):  # (list, count) form — we only want the list
                users = users[0]
            for u in users:
                for proxy in u.proxies:
                    if proxy.type != ProxyTypes.VLESS:
                        continue
                    uuid = (proxy.settings or {}).get("id")
                    if uuid:
                        clients.append(
                            {"id": str(uuid), "email": f"{u.id}.{u.username}"}
                        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Xray] could not collect VLESS clients from DB: {e}")
    return clients


def generate_config() -> Path:
    """Generate /app/xray-config/config.json automatically. Returns its path."""
    XRAY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    clients = _collect_vless_clients()

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "spider-vless-ws",
                "listen": INBOUND_LISTEN,
                "port": INBOUND_PORT,
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {"path": WS_BASE_PATH},
                },
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "DIRECT"},
            {"protocol": "blackhole", "tag": "BLOCK"},
        ],
    }

    XRAY_CONFIG_PATH.write_text(json.dumps(config, indent=2))
    logger.info(f"[Xray] Config generated: {XRAY_CONFIG_PATH} ({len(clients)} clients)")
    return XRAY_CONFIG_PATH


# ===========================================================================
# 4. Validation
# ===========================================================================
def validate_config() -> None:
    """Run `xray run -test -config ...`. Raise RuntimeError unless OK."""
    try:
        out = subprocess.run(
            [str(XRAY_BINARY), "run", "-test", "-config", str(XRAY_CONFIG_PATH)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"[Xray] validation could not run: {e}") from e

    combined = (out.stdout or "") + (out.stderr or "")
    if out.returncode != 0 or "Configuration OK" not in combined:
        raise RuntimeError(
            f"[Xray] Config validation FAILED (exit {out.returncode}):\n{combined.strip()}"
        )
    logger.info("[Xray] Config validation OK")


# ===========================================================================
# 5. VLESS link generation
# ===========================================================================
def build_vless_link(uuid: str, domain: str, port: int) -> str:
    """Build a VLESS-WS subscription link using the EXTERNAL Railway endpoint.

    Format:
      vless://UUID@DOMAIN:PORT?encryption=none&security=tls&type=ws
             &host=DOMAIN&path=%2Fws%2FUUID&sni=DOMAIN&fp=chrome#Spider
    """
    path = quote(f"{WS_BASE_PATH}/{uuid}", safe="")
    query = (
        f"encryption=none&security=tls&type=ws"
        f"&host={domain}&path={path}&sni={domain}&fp=chrome"
    )
    return f"vless://{uuid}@{domain}:{port}?{query}#{quote(REMARK)}"


def build_user_links(domain: str, port: int) -> List[str]:
    """Build VLESS links for every active VLESS user."""
    links: List[str] = []
    for client in _collect_vless_clients():
        links.append(build_vless_link(client["id"], domain, port))
    return links


# ===========================================================================
# Orchestration
# ===========================================================================
class SpiderXray:
    """Holds the running Xray process + the resolved Railway endpoint."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.domain: Optional[str] = None
        self.port: Optional[int] = None

    @property
    def endpoint_ready(self) -> bool:
        return bool(self.domain and self.port)

    def start(self) -> None:
        """Full startup flow (spec section 8):

        detect Railway -> install/check Xray -> generate config ->
        validate -> start Xray process.
        """
        # 2. Detect Railway variables (wait until domain exists).
        endpoint = detect_railway_endpoint(wait=True, retry_seconds=10)
        if not endpoint:
            raise RuntimeError("[Railway] no public domain; refusing to start Xray")
        self.domain, self.port = endpoint

        # 3. Install/check Xray.
        ensure_xray()

        # 4. Generate config.
        generate_config()

        # 5. Validate config.
        validate_config()

        # 6. Start Xray process.
        self.process = subprocess.Popen(
            [str(XRAY_BINARY), "run", "-config", str(XRAY_CONFIG_PATH)],
            env={**os.environ},
        )
        # Give it a moment to fail fast on a bad bind.
        time.sleep(1)
        if self.process.poll() is not None:
            raise RuntimeError(
                f"[Xray] process exited immediately (code {self.process.returncode})"
            )
        logger.info("[Xray] Started successfully")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None


spider = SpiderXray()
