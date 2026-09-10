"""``/ws/jobs`` — one shared socket multiplexing every job's status plus subscribed jobs' events.

Server -> client: ``{"type": "job", "job": <JobStatus>}`` for *every* job's transition
(unconditional — the jobs rail needs this regardless of what's open); ``{"type": "event",
"job_id": ..., "event": <Event>}`` only for jobs the client has subscribed to, in ``seq`` order.
Client -> server: ``{"subscribe": {"<job_id>": <since_seq>}}`` / ``{"unsubscribe": [job_id, ...]}``.

Follows the exact pattern of ``tit/server/ws.py`` (``/ws/system``): origin check, then auth,
then accept; ``run_in_threadpool`` bridges the manager's thread-safe ``queue.Queue`` pub/sub
(fed from :class:`tit.jobs.manager.JobManager`'s own background thread) onto this coroutine's
event loop. Each poll uses a short timeout rather than blocking forever so a disconnected
client's forwarder task actually stops instead of leaking a blocked threadpool worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from tit.jobs.bootstrap import get_manager
from tit.server.auth import origin_allowed, websocket_authorized

logger = logging.getLogger(__name__)

ws_router = APIRouter()

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN_ORIGIN = 4403
POLL_TIMEOUT_S = 1.0


async def _pump(
    source: "queue.Queue[dict[str, Any]]",
    wrap: Any,
    out_queue: "asyncio.Queue[dict[str, Any]]",
) -> None:
    """Forward items from a thread-safe queue to *out_queue*, wrapped by *wrap*.

    Polls with a timeout (rather than blocking forever) so ``asyncio.Task.cancel()`` is honoured
    promptly instead of leaving a threadpool worker blocked on a queue nobody will ever feed
    again.
    """
    while True:
        try:
            item = await run_in_threadpool(source.get, True, POLL_TIMEOUT_S)
        except queue.Empty:
            continue
        await out_queue.put(wrap(item))


@ws_router.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket) -> None:
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

    manager = get_manager(ws.app)
    out_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    status_q = manager.subscribe_status()
    event_subs: dict[str, tuple["queue.Queue[dict[str, Any]]", asyncio.Task]] = {}

    def _wrap_status(job: dict[str, Any]) -> dict[str, Any]:
        return {"type": "job", "job": job}

    def _wrap_event(job_id: str) -> Any:
        return lambda event: {"type": "event", "job_id": job_id, "event": event}

    status_task = asyncio.create_task(_pump(status_q, _wrap_status, out_queue))

    async def _sender() -> None:
        while True:
            message = await out_queue.get()
            await ws.send_text(json.dumps(message))

    sender_task = asyncio.create_task(_sender())

    def _subscribe(job_id: str, since: int) -> None:
        _unsubscribe(job_id)
        q = manager.subscribe_events(job_id, since=since)
        task = asyncio.create_task(_pump(q, _wrap_event(job_id), out_queue))
        event_subs[job_id] = (q, task)

    def _unsubscribe(job_id: str) -> None:
        entry = event_subs.pop(job_id, None)
        if entry is None:
            return
        q, task = entry
        task.cancel()
        manager.unsubscribe_events(job_id, q)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            subscribe = message.get("subscribe")
            if isinstance(subscribe, dict):
                for job_id, since in subscribe.items():
                    try:
                        _subscribe(job_id, int(since))
                    except (TypeError, ValueError):
                        continue
            unsubscribe = message.get("unsubscribe")
            if isinstance(unsubscribe, list):
                for job_id in unsubscribe:
                    if isinstance(job_id, str):
                        _unsubscribe(job_id)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("/ws/jobs: connection failed")
    finally:
        status_task.cancel()
        sender_task.cancel()
        manager.unsubscribe_status(status_q)
        for job_id in list(event_subs):
            _unsubscribe(job_id)
        for task in (status_task, sender_task):
            with _suppress_cancelled():
                await task


class _suppress_cancelled:
    def __enter__(self) -> "_suppress_cancelled":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return exc_type is not None and issubclass(
            exc_type, (asyncio.CancelledError, RuntimeError)
        )
