"""
Spider router — subscription surface for the VLESS Reality + XHTTP integration.

  GET /spider/sub/{uuid}   -> base64 VLESS-Reality subscription for one user
  GET /spider/links        -> JSON list of all active VLESS-Reality links

There is intentionally NO /ws/{uuid} relay: Reality + XHTTP inbounds are served
directly by Xray on internal_port (the Railway TCP proxy forwards
external_port -> internal_port), so FastAPI never proxies proxy traffic.
"""

import base64
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from app.spider_xray import _collect_vless_clients, build_user_links, build_vless_link, spider

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/spider", tags=["Spider"])


def _uuid_is_active(uuid: str) -> bool:
    uuid = uuid.lower()
    return any(c["id"].lower() == uuid for c in _collect_vless_clients())


@router.get("/sub/{uuid}")
def spider_subscription(uuid: str):
    if not _uuid_is_active(uuid):
        raise HTTPException(status_code=404, detail="unknown or inactive user")
    if not spider.ready:
        raise HTTPException(status_code=503, detail="Xray not ready yet")
    assert spider.user_cfg and spider.keys
    link = build_vless_link(uuid, spider.user_cfg, spider.keys)
    return PlainTextResponse(base64.b64encode((link + "\n").encode()).decode())


@router.get("/links")
def spider_links():
    if not spider.ready:
        raise HTTPException(status_code=503, detail="Xray not ready yet")
    assert spider.user_cfg and spider.keys
    return JSONResponse({"links": build_user_links(spider.user_cfg, spider.keys)})
