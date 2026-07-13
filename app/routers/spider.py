"""
Spider router — FastAPI surface for the Spider Xray integration.

  GET  /spider/sub/{uuid}   -> plain-text (base64) VLESS subscription for one user
  GET  /spider/links        -> JSON list of all active VLESS links
  WS   /ws/{uuid}           -> WebSocket relay to the local Xray VLESS-WS inbound

The /ws/{uuid} relay accepts a connection when the UUID belongs to an active
user, then bridges bytes to Xray's internal WS inbound (127.0.0.1:INBOUND_PORT
at WS_BASE_PATH). It returns 403 ONLY when the UUID is unknown or the user is
inactive — never for a valid, active user.
"""

import asyncio
import base64
import logging

import websockets
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse

from app.spider_xray import (
    INBOUND_PORT,
    WS_BASE_PATH,
    _collect_vless_clients,
    build_user_links,
    build_vless_link,
    spider,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/spider", tags=["Spider"])
ws_router = APIRouter(tags=["Spider"])


def _uuid_is_active(uuid: str) -> bool:
    uuid = uuid.lower()
    return any(c["id"].lower() == uuid for c in _collect_vless_clients())


@router.get("/sub/{uuid}")
def spider_subscription(uuid: str):
    if not _uuid_is_active(uuid):
        raise HTTPException(status_code=404, detail="unknown or inactive user")
    if not spider.endpoint_ready:
        raise HTTPException(status_code=503, detail="Railway domain not ready yet")
    domain, port = spider.domain, spider.port
    assert domain and port
    link = build_vless_link(uuid, domain, port)
    body = base64.b64encode((link + "\n").encode()).decode()
    return PlainTextResponse(body)


@router.get("/links")
def spider_links():
    if not spider.endpoint_ready:
        raise HTTPException(status_code=503, detail="Railway domain not ready yet")
    domain, port = spider.domain, spider.port
    assert domain and port
    return JSONResponse({"links": build_user_links(domain, port)})


@ws_router.websocket("/ws/{uuid}")
async def ws_relay(websocket: WebSocket, uuid: str):
    """Relay a client WebSocket onto the local Xray VLESS-WS inbound.

    Accept only when the UUID belongs to an active user (never a blanket 403).
    """
    if not _uuid_is_active(uuid):
        # Reject BEFORE the handshake completes — 403 for unknown/inactive only.
        await websocket.close(code=4403)
        logger.warning(f"[WS] rejected unknown/inactive uuid {uuid}")
        return

    await websocket.accept()

    upstream_url = f"ws://127.0.0.1:{INBOUND_PORT}{WS_BASE_PATH}"
    try:
        async with websockets.connect(
            upstream_url, subprotocols=None, open_timeout=10, max_size=None
        ) as upstream:
            await _pump(websocket, upstream)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[WS] relay error for uuid {uuid}: {e}")
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


async def _pump(client: WebSocket, upstream) -> None:
    """Bidirectionally forward binary frames between client and upstream."""

    async def client_to_upstream():
        try:
            while True:
                data = await client.receive_bytes()
                await upstream.send(data)
        except (WebSocketDisconnect, Exception):  # noqa: BLE001
            return

    async def upstream_to_client():
        try:
            async for message in upstream:
                if isinstance(message, str):
                    message = message.encode()
                await client.send_bytes(message)
        except Exception:  # noqa: BLE001
            return

    await asyncio.gather(client_to_upstream(), upstream_to_client())
