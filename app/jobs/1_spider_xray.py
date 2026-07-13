"""Spider Xray startup/shutdown job.

Runs the VLESS Reality + XHTTP Xray lifecycle in a background thread so the web
app serves immediately. Startup order (spec section 10):

  1. Check Xray exists (install if missing).
  2. Load config.json (user settings, never overwritten).
  3. Generate missing Reality keys / shortId.
  4. Generate Xray config.
  5. Validate config (xray run -test).
  6. Start Xray.
  7. Web application already running; subscriptions become live (spider.ready).
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
