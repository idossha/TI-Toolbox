"""``/api/kernels/*`` and ``/ws/kernels/{kernel_id}`` — notebook execution (v1).

Thin HTTP and WebSocket over :mod:`tit.server.kernels`, which owns the
``jupyter_client`` machinery. The split matters: REST does lifecycle (start,
list, interrupt, restart, shut down) because those are things a page and a
command palette both want and neither needs a socket for; the socket carries
exactly one cell's traffic — ``execute`` down, ``status``/``input``/``output``/
``clear``/``reply`` up, plus ``complete``/``inspect`` round trips — because
that is a stream and nothing else here is.

Completion is a kernel round trip rather than a language server on purpose: a
kernel that has run the notebook's imports is *holding* the objects, so
``tit.<Tab>`` answers from the live namespace. ``jedi`` is already inside
ipykernel, so there is nothing to install and nothing to keep in sync.

This is SUNA's kernel bridge protocol (docs/dev/ARCHITECTURE.md §16.2 there) with
the pipe swapped: SUNA frames it over a child process's stdio, and TI-Toolbox
over this socket, because the interpreter that has to run the code is the
container's and the container is where the server already is.

Import cost is deliberately small (``dev/route_import_guard.py``):
``jupyter_client`` is imported inside :mod:`tit.server.kernels`, on first start.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect

from tit.server.auth import origin_allowed, websocket_authorized
from tit.server.kernels import DEFAULT_KERNEL_NAME, KernelError, get_kernel_registry
from tit.server.schemas import Kernel, KernelInterrupted, KernelList, KernelStopped

logger = logging.getLogger(__name__)

router = APIRouter()
ws_router = APIRouter()

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN_ORIGIN = 4403
#: No such kernel, or it died while the client was connecting. Distinct from
#: the auth codes so the page can say "the kernel is gone" rather than
#: "you are not allowed", which are very different things to be told.
WS_CLOSE_NO_KERNEL = 4404

#: Kernel events buffered for one socket. A cell that prints in a loop can
#: outrun a slow client; when it does, dropping the socket is honest, whereas
#: an unbounded queue turns it into the server's memory problem.
WS_QUEUE_MAX = 4096

_STATUS = {
    "no-such-kernel": 404,
    "too-many-kernels": 429,
    "no-jupyter-client": 501,
    "no-kernelspec": 501,
    "start-failed": 500,
    "op-failed": 500,
}


def _fail(error: KernelError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(error.code, 500),
        detail={"code": error.code, "message": error.message},
    )


def _project_root(request: Request) -> str:
    root = request.app.state.settings.project_dir
    if not root:
        raise HTTPException(status_code=409, detail="This server is not bound to a project.")
    return str(root)


@router.get(
    "/api/kernels",
    response_model=KernelList,
    summary="List the kernels this server is running",
)
def list_kernels(request: Request) -> dict[str, Any]:
    registry = get_kernel_registry()
    registry.reap_idle()
    return {
        "kernels": [session.describe() for session in registry.list()],
        "max": registry.max_kernels,
        "idleTimeoutSeconds": registry.idle_timeout,
    }


@router.post(
    "/api/kernels",
    response_model=Kernel,
    responses={
        429: {"description": "the concurrent-kernel limit is already reached"},
        501: {"description": "no jupyter_client, or no such kernelspec, in this container"},
    },
    summary="Start a kernel for a notebook session",
)
def start_kernel(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Start a kernel whose working directory is the project.

    The cwd is the project root and not the notebook's own directory: a
    notebook here is a way of driving *this project*, and a relative path in a
    cell should mean what it means everywhere else in TI-Toolbox.
    """
    root = _project_root(request)
    kernel_name = body.get("kernelName") or DEFAULT_KERNEL_NAME
    if not isinstance(kernel_name, str):
        raise HTTPException(status_code=422, detail="'kernelName' must be a string.")
    try:
        session = get_kernel_registry().start(cwd=root, kernel_name=kernel_name)
    except KernelError as error:
        raise _fail(error) from error
    return session.describe()


@router.delete(
    "/api/kernels/{kernel_id}", response_model=KernelStopped, summary="Shut a kernel down"
)
def stop_kernel(kernel_id: str) -> dict[str, Any]:
    try:
        get_kernel_registry().shutdown(kernel_id)
    except KernelError as error:
        raise _fail(error) from error
    return {"id": kernel_id, "state": "dead"}


@router.post(
    "/api/kernels/{kernel_id}/interrupt",
    response_model=KernelInterrupted,
    summary="Interrupt the running cell",
)
def interrupt_kernel(kernel_id: str) -> dict[str, Any]:
    try:
        get_kernel_registry().interrupt(kernel_id)
    except KernelError as error:
        raise _fail(error) from error
    return {"id": kernel_id, "interrupted": True}


@router.post(
    "/api/kernels/{kernel_id}/restart",
    response_model=Kernel,
    summary="Restart a kernel; every variable is lost",
)
def restart_kernel(kernel_id: str) -> dict[str, Any]:
    registry = get_kernel_registry()
    try:
        registry.restart(kernel_id)
        return registry.get(kernel_id).describe()
    except KernelError as error:
        raise _fail(error) from error


@ws_router.websocket("/ws/kernels/{kernel_id}")
async def ws_kernel(ws: WebSocket, kernel_id: str) -> None:
    """One kernel's traffic, both ways.

    Origin, then auth, then accept — the same order as ``/ws/jobs`` and
    ``/ws/system``, for the same reason: nothing about the request is trusted
    before the handshake is finished.
    """
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

    registry = get_kernel_registry()
    try:
        session = registry.get(kernel_id)
    except KernelError:
        await ws.close(code=WS_CLOSE_NO_KERNEL)
        return

    await ws.accept()

    loop = asyncio.get_running_loop()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=WS_QUEUE_MAX)

    def on_event(event: dict[str, Any]) -> None:
        # Called on the kernel's own iopub/shell thread, so the hop onto the
        # loop is not optional. A full queue means the client cannot keep up;
        # the event is dropped rather than blocking the pump that feeds every
        # other listener on this kernel.
        try:
            loop.call_soon_threadsafe(outgoing.put_nowait, event)
        except (RuntimeError, asyncio.QueueFull):  # pragma: no cover - loop closing
            pass

    unsubscribe = registry.subscribe(kernel_id, on_event)

    async def forward() -> None:
        while True:
            event = await outgoing.get()
            await ws.send_json(event)

    forwarder = asyncio.create_task(forward())
    # The socket's first message is the state the client would otherwise have
    # to ask for: a page that reconnects mid-run must not have to guess.
    await ws.send_json({"type": "ready", "kernel": session.describe()})

    try:
        while True:
            message = await ws.receive_json()
            op = message.get("op")
            req_id = str(message.get("id", ""))
            try:
                if op == "execute":
                    registry.execute(kernel_id, req_id, str(message.get("code", "")))
                elif op == "interrupt":
                    registry.interrupt(kernel_id)
                elif op == "restart":
                    registry.restart(kernel_id)
                elif op == "complete":
                    registry.complete(
                        kernel_id, req_id, str(message.get("code", "")), int(message.get("cursorPos", 0))
                    )
                elif op == "inspect":
                    registry.inspect(
                        kernel_id, req_id, str(message.get("code", "")), int(message.get("cursorPos", 0))
                    )
                else:
                    logger.debug("kernel %s: unknown op %r", kernel_id, op)
            except KernelError as error:
                await ws.send_json(
                    {"type": "fatal", "code": error.code, "message": error.message}
                )
    except WebSocketDisconnect:
        pass
    except Exception as error:  # a malformed frame must not leak the socket
        logger.info("kernel %s socket ended: %s", kernel_id, error)
    finally:
        forwarder.cancel()
        unsubscribe()
