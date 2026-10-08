"""The MCP stdio transport both plugin servers share: JSON-RPC 2.0, one message per line.

``serve(handler(...))`` answers ``initialize``, ``ping``, ``tools/list`` and ``tools/call``.
Each ``tools/call`` runs on its own thread, so a long call (a wait Claude Code moves to the
background) never holds up the agent's next one; everything else is answered in order. A tool
reports progress with :func:`progress` and sleeps with :func:`pause`, which returns early once
the client sends ``notifications/cancelled`` for that call. When stdin closes, every call still
in flight is cancelled and answered before the process exits.

Standard library only, Python 3.9+. A server imports it as ``import stdio_loop`` after putting
its own directory on ``sys.path`` (Claude Code and Codex run the server by absolute path from
any working directory).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

PROTOCOL_VERSION = "2025-06-18"

Handler = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


class ToolError(Exception):
    """A tool failure reported to the agent as ``isError: true`` text."""


#: The tools/call being served on this thread: its progress token and cancel event.
_CALL = threading.local()
#: In-flight tools/call id -> its cancel event (set by notifications/cancelled).
_CANCELS: Dict[Any, threading.Event] = {}
_WRITE_LOCK = threading.Lock()


def write(message: Dict[str, Any]) -> None:
    line = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    with _WRITE_LOCK:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


def pause(seconds: float) -> bool:
    """Sleep; True when the client cancelled the current call (stop waiting)."""
    cancel = getattr(_CALL, "cancel", None)
    if cancel is None:
        time.sleep(seconds)
        return False
    return cancel.wait(seconds)


def progress(message: str) -> None:
    """A notifications/progress for the current call, when its client asked for them: shows in
    the client's task list and keeps an idle timer from expiring. At most every 30 s unless the
    message changes."""
    token = getattr(_CALL, "token", None)
    if token is None:
        return
    now = time.monotonic()
    if message == getattr(_CALL, "said", None) and now - _CALL.said_at < 30:
        return
    _CALL.said, _CALL.said_at = message, now
    _CALL.count = getattr(_CALL, "count", 0) + 1
    write(
        {
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {
                "progressToken": token,
                "progress": _CALL.count,
                "message": message,
            },
        }
    )


def _result(id_: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _text(id_: Any, text: str, is_error: bool) -> Dict[str, Any]:
    return _result(
        id_, {"content": [{"type": "text", "text": text}], "isError": is_error}
    )


def handler(
    name: str,
    version: str,
    instructions: str,
    tools: List[Dict[str, Any]],
    on_initialize: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Handler:
    """``handle(message) -> response or None`` for a server with these *tools*.

    Each tool is ``{name, description, inputSchema, annotations, handler}``; ``handler(args)``
    returns a JSON-serialisable result or raises :class:`ToolError`. *on_initialize* receives
    the ``initialize`` params (the client's name, say).
    """
    handlers = {t["name"]: t["handler"] for t in tools}
    listed = [{k: v for k, v in t.items() if k != "handler"} for t in tools]

    def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method, id_ = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            if on_initialize is not None:
                on_initialize(params)
            return _result(
                id_,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": name, "version": version},
                    "instructions": instructions,
                },
            )
        if method == "notifications/cancelled":
            cancel = _CANCELS.get(params.get("requestId"))
            if cancel is not None:
                cancel.set()
            return None
        if method == "ping":
            return _result(id_, {})
        if method == "tools/list":
            return _result(id_, {"tools": listed})
        if method == "tools/call":
            fn = handlers.get(params.get("name"))
            if fn is None:
                return _error(id_, -32602, f"Unknown tool: {params.get('name')}")
            _CALL.token = (params.get("_meta") or {}).get("progressToken")
            _CALL.cancel = _CANCELS.setdefault(id_, threading.Event())
            _CALL.said = None
            try:
                out = fn(params.get("arguments") or {})
                return _text(id_, json.dumps(out, indent=2, ensure_ascii=False), False)
            except ToolError as exc:
                return _text(id_, str(exc), True)
            except Exception as exc:  # noqa: BLE001 - report, never crash the server
                return _text(id_, f"{type(exc).__name__}: {exc}", True)
            finally:
                _CANCELS.pop(id_, None)
                _CALL.token = _CALL.cancel = None
        if id_ is None:
            return None  # an unknown notification (notifications/initialized, ...)
        return _error(id_, -32601, f"Method not found: {method}")

    return handle


def serve(handle: Handler) -> None:
    """Read stdin until it closes, answering each message with *handle*."""

    def respond(msg: Any) -> None:
        resp = handle(msg) if isinstance(msg, dict) else None
        if resp is not None:
            write(resp)

    workers: List[threading.Thread] = []
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            write(_error(None, -32700, "Parse error"))
            continue
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            _CANCELS[msg.get("id")] = threading.Event()  # before a cancel can arrive
            worker = threading.Thread(target=respond, args=(msg,), daemon=True)
            worker.start()
            workers = [w for w in workers if w.is_alive()] + [worker]
        else:
            respond(msg)
    for cancel in list(_CANCELS.values()):
        cancel.set()
    for worker in workers:
        worker.join()
