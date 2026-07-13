"""Spider Xray startup/shutdown job.

Runs the Spider Xray lifecycle in a background thread so the web app can serve
immediately while we wait (up to indefinitely) for the Railway TCP proxy domain
to appear. Startup order (spec section 8):

  1. Application starts (uvicorn) — already running when this fires.
  2. Detect Railway variables.
  3. Install/check Xray.
  4. Generate config.json.
  5. Validate config.
  6. Start Xray process.
  7. Subscriptions become live (spider.endpoint_ready == True).
"""

import threading

from app import app, logger
from app.spider_xray import spider


def _spider_boot():
    try:
        spider.start()
        logger.info("[Spider] Xray ready — subscriptions enabled")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[Spider] Xray startup failed: {e}")


@app.on_event("startup")
def start_spider_xray():
    logger.info("[Spider] Launching Xray startup flow in background")
    threading.Thread(target=_spider_boot, daemon=True, name="spider-xray").start()


@app.on_event("shutdown")
def stop_spider_xray():
    logger.info("[Spider] Stopping Xray")
    spider.stop()
