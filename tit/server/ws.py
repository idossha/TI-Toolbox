"""``/ws/system`` — one :class:`SystemSnapshot` JSON message every 2 s.

V4 (``dev/notes/v3-native-panes-external-viewer-plan.md``): ``/ws/tetravox`` and
its ``EventHub`` are gone with the embed.  The one event they carried said "the
viewer bundle under you was just replaced" — a sentence with no referent once
the viewer is a separate application on the host that updates itself.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from tit.server.auth import origin_allowed, websocket_authorized
from tit.server.routes.system import snapshot

logger = logging.getLogger(__name__)

router = APIRouter()

SYSTEM_INTERVAL_S = 2.0
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN_ORIGIN = 4403
WS_CLOSE_INTERNAL_ERROR = 1011


async def _stream_snapshots(ws: WebSocket) -> None:
    try:
        while True:
            snap = await run_in_threadpool(snapshot)
            await ws.send_text(snap.model_dump_json())
            await asyncio.sleep(SYSTEM_INTERVAL_S)
    except (asyncio.CancelledError, WebSocketDisconnect):
        raise
    except Exception:
        logger.exception("/ws/system: snapshot failed; closing the stream")
        try:
            await ws.close(code=WS_CLOSE_INTERNAL_ERROR)
        except RuntimeError:  # already closed by the peer
            pass


@router.websocket("/ws/system")
async def ws_system(ws: WebSocket) -> None:
    if not origin_allowed(
        ws.headers.get("origin"),
        ws.headers.get("host"),
        ws.app.state.settings.dev_origins,
        secure=ws.url.scheme == "wss",
    ):
        await ws.close(code=WS_CLOSE_FORBIDDEN_ORIGIN)
        return
    if not websocket_authorized(ws):
        await ws.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    await ws.accept()
    sender = asyncio.create_task(_stream_snapshots(ws))
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        try:
            await sender
        except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            pass
