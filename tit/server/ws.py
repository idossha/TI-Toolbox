"""``/ws/system`` — one :class:`SystemSnapshot` JSON message every 2 s, and
``/ws/tetravox`` — the app-level event stream (today: exactly one event).

Why a second socket rather than a message type on an existing one: ``/ws/system``
is a stream of one shape (a snapshot every 2 s, parsed as a snapshot by
``renderer/ws/systemStream.ts``) and ``/ws/jobs`` is a stream about jobs; a
viewer bundle being replaced under the app is neither, and pushing it down either
would make both consumers branch on a message that has nothing to do with what
they are for.  ``/ws/tetravox`` is silent until something happens, so it costs
one idle connection and nothing else.

One event exists: ``{"type": "tetravox.updated", "version", "protocol",
"message"}``, published by the auto-update policy (A3) after it has installed and
activated a bundle.  It is a notification, not a command — panes already mounted
keep the iframe they have; the toast says to reload the viewer.

(``contracts/events.schema.json`` is *not* the model for this: that file
describes one line of a job's ``events.jsonl``, a different stream with a
different vocabulary.  Adding an app-level event to it would have made every job
event reader accept a type no job can ever emit.)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from tit.server.auth import origin_allowed, websocket_authorized
from tit.server.routes.system import snapshot

logger = logging.getLogger(__name__)

router = APIRouter()

SYSTEM_INTERVAL_S = 2.0
TETRAVOX_EVENT = "tetravox.updated"
#: Bound per subscriber: a client that stops reading is disconnected rather than
#: allowed to grow an unbounded queue in the server.
EVENT_QUEUE_MAX = 32
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


# ── app-level events (one, today) ────────────────────────────────────────────


class EventHub:
    """Fan-out of app-level events to every open ``/ws/tetravox``.

    Deliberately tiny and in-memory: these events are notifications about
    something that has *already happened* on disk, so a client that was not
    connected loses nothing it cannot re-read from ``GET /api/tetravox``.  There
    is no replay, no persistence and no ordering guarantee beyond per-subscriber
    FIFO.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> "asyncio.Queue[dict[str, Any]]":
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=EVENT_QUEUE_MAX)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[dict[str, Any]]") -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: dict[str, Any]) -> None:
        """Deliver to everyone listening.  A full queue drops, never blocks."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - a client not reading
                logger.warning("/ws/tetravox: subscriber queue full; dropping an event")


#: Module-level so the background task in ``tit.server.app`` and the route below
#: are talking about the same hub without threading it through app state.
events = EventHub()


def publish_tetravox_updated(
    version: str, protocol: int | None, message: str
) -> dict[str, Any]:
    """Build and publish the one event; returns what was sent (for tests/logs)."""
    event = {
        "type": TETRAVOX_EVENT,
        "version": version,
        "protocol": protocol,
        "message": message,
    }
    events.publish(event)
    return event


@router.websocket("/ws/tetravox")
async def ws_tetravox(ws: WebSocket) -> None:
    """Silent until the viewer bundle is replaced under the app."""
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
    queue = events.subscribe()

    async def _sender() -> None:
        while True:
            event = await queue.get()
            await ws.send_text(json.dumps(event))

    sender = asyncio.create_task(_sender())
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(queue)
        sender.cancel()
        try:
            await sender
        except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            pass
