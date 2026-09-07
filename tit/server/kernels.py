"""Jupyter kernels, owned by the server process, one per notebook session.

Ported from SUNA's ``python/suna_kernel/bridge.py`` (github.com/idossha/SUNA,
docs/dev/ARCHITECTURE.md §16.2) — the protocol translation, the nbformat-verbatim
output rule, the request attribution and the fatal error codes are that file's
design. What changed is the *topology*.

SUNA is a desktop app whose kernel runs on the user's own machine, so the
bridge is a child process the Electron main process speaks to over stdio. In
TI-Toolbox the environment that must be loaded is the one inside the
container — SimNIBS Python with ``tit`` importable — and the server already
runs there. So there is no bridge process and no pipe: this module drives
``jupyter_client.manager.KernelManager`` in-process, and the pipe SUNA framed
over stdin/stdout is the WebSocket in ``routes/kernels.py`` instead.

The events are SUNA's, unchanged, because they are the shape the ported
renderer already understands:

    {"type": "ready",  "kernel": {...}}
    {"type": "status", "state": "busy"|"idle"|"starting"|"dead"}
    {"type": "input",  "reqId": "r1", "executionCount": 3}
    {"type": "output", "reqId": "r1", "output": {<nbformat output>}}
    {"type": "clear",  "reqId": "r1", "wait": false}
    {"type": "reply",  "reqId": "r1", "status": "ok", "executionCount": 3}
    {"type": "fatal",  "code": "...", "message": "..."}

plus two SUNA does not have, because SUNA's cells are a CodeMirror driven by a
language server and these cells are driven by the kernel itself:

    {"type": "complete", "reqId": "c1", "matches": [...],
                         "cursorStart": 18, "cursorEnd": 24, "metadata": {...}}
    {"type": "inspect",  "reqId": "i1", "found": true, "text": "..."}

A kernel that has *executed* the notebook knows what `tit.` holds better than
any static analyser could -- it is holding the object. That is why completion
is a kernel round trip here rather than an LSP: `jedi` is already inside
ipykernel, and the namespace it completes against is the live one.

Two limits exist because a kernel here is a container-wide resource rather
than one user's laptop: at most ``MAX_KERNELS`` run at once, and a kernel
nobody has touched for ``IDLE_TIMEOUT_SECONDS`` is shut down. A FEM run and
four abandoned kernels do not get to share the same RAM.

There is no sandbox. A kernel executes arbitrary user code as the container's
own user, with the project mounted. That is the same trust boundary the job
runners already have, and nothing may call it a sandbox.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: The kernelspec the image registers for SimNIBS Python with ``tit`` on the
#: path (container/blueprint/Dockerfile.ti-toolbox). A notebook may name a
#: different one in its metadata; this is what a new session gets.
DEFAULT_KERNEL_NAME = "simnibs"

#: Concurrent kernels. Each is a full SimNIBS Python interpreter — the point
#: of the cap is that they are not free, not that two is a magic number.
MAX_KERNELS = 2

#: A kernel with no request for this long is shut down. Its notebook keeps
#: every output it already produced; only the live variables are lost.
IDLE_TIMEOUT_SECONDS = 30 * 60

#: How long to wait for a kernel to come up before calling it failed.
STARTUP_TIMEOUT_SECONDS = 120

#: How long to wait for a channel pump to notice it has been stopped. Comfortably
#: more than its own 0.2 s poll, and bounded so a wedged channel cannot hang a
#: restart or a shutdown.
PUMP_JOIN_TIMEOUT_S = 5.0

#: iopub message types that ARE nbformat outputs once ``output_type`` is added.
#: This is why the live kernel and the .ipynb need no translation layer.
OUTPUT_MSG_TYPES = frozenset(
    {"stream", "display_data", "execute_result", "error", "update_display_data"}
)


class KernelError(Exception):
    """A kernel operation failed, with one of the codes the UI switches on.

    The codes are SUNA's: ``no-jupyter-client``, ``no-kernelspec``,
    ``start-failed``, ``op-failed`` — plus ``too-many-kernels`` and
    ``no-such-kernel``, which only exist because this server is shared and
    SUNA's desktop was not.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def output_from_msg(msg_type: str, content: dict[str, Any]) -> dict[str, Any] | None:
    """An iopub message as the nbformat output it will be stored as."""
    if msg_type == "stream":
        return {
            "output_type": "stream",
            "name": content.get("name", "stdout"),
            "text": content.get("text", ""),
        }
    if msg_type in ("display_data", "update_display_data"):
        return {
            "output_type": "display_data",
            "data": content.get("data", {}),
            "metadata": content.get("metadata", {}),
        }
    if msg_type == "execute_result":
        return {
            "output_type": "execute_result",
            "data": content.get("data", {}),
            "metadata": content.get("metadata", {}),
            "execution_count": content.get("execution_count"),
        }
    if msg_type == "error":
        return {
            "output_type": "error",
            "ename": content.get("ename", ""),
            "evalue": content.get("evalue", ""),
            "traceback": content.get("traceback", []),
        }
    return None


def _query_event(req_id: str, msg_type: str, content: dict[str, Any]) -> dict[str, Any]:
    """A ``complete_reply``/``inspect_reply`` as the event the client reads.

    An inspect reply's payload is a mime bundle; only ``text/plain`` is taken,
    because the cell's hover is a tooltip and IPython's own signature/docstring
    lives there. It arrives ANSI-coloured, and stays that way -- the renderer
    already parses ANSI for tracebacks and reuses that here.
    """
    if msg_type == "complete_reply":
        return {
            "type": "complete",
            "reqId": req_id,
            "matches": list(content.get("matches", [])),
            "cursorStart": content.get("cursor_start", 0),
            "cursorEnd": content.get("cursor_end", 0),
            "metadata": content.get("metadata", {}),
        }
    data = content.get("data", {}) or {}
    return {
        "type": "inspect",
        "reqId": req_id,
        "found": bool(content.get("found", False)),
        "text": data.get("text/plain", ""),
    }


Listener = Callable[[dict[str, Any]], None]


@dataclass
class KernelSession:
    """One live kernel and the bookkeeping the routes need to talk to it."""

    id: str
    kernel_name: str
    cwd: str
    manager: Any
    client: Any
    display_name: str = ""
    language: str = ""
    started_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    execution_state: str = "idle"
    #: shell msg_id -> the renderer's request id, so an output can be pinned
    #: to the cell that asked for it even while several cells are queued.
    pending: dict[str, str] = field(default_factory=dict)
    #: shell msg_id -> the halves of "this request is finished". A request
    #: ends twice, on two different channels: the shell ``execute_reply``
    #: carries the status, and the iopub ``status: idle`` is the last thing
    #: after its outputs. Two threads poll those channels, so whichever half
    #: arrives second is the one that may emit — otherwise a reply can, and
    #: in the test suite did, overtake the very output it concludes.
    finishing: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: shell msg_id -> (request id, "complete" | "inspect"). Kept apart from
    #: ``pending``: a query produces exactly one shell reply and no iopub
    #: output at all, so it must not go through the two-channel join above --
    #: it would wait forever for an ``idle`` that belongs to nothing.
    queries: dict[str, tuple[str, str]] = field(default_factory=dict)
    listeners: list[Listener] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    stopping: threading.Event = field(default_factory=threading.Event)
    #: The two channel pumps. Held so they can be STOPPED AND JOINED before
    #: anything touches the sockets they poll -- see ``_stop_pumps``.
    pumps: list[threading.Thread] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.kernel_name,
            "displayName": self.display_name or self.kernel_name,
            "language": self.language,
            "cwd": self.cwd,
            "state": self.execution_state,
            "startedAt": self.started_at,
            "lastUsed": self.last_used,
        }


class KernelRegistry:
    """Every kernel this server process owns.

    One instance lives on the FastAPI app; the routes reach it through
    ``get_kernel_registry``. It is deliberately a plain object with a lock
    rather than anything async — ``jupyter_client``'s channels are threads,
    and pretending otherwise would only move the threads somewhere less
    visible.
    """

    def __init__(
        self,
        *,
        max_kernels: int = MAX_KERNELS,
        idle_timeout: float = IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._sessions: dict[str, KernelSession] = {}
        self._lock = threading.Lock()
        self.max_kernels = max_kernels
        self.idle_timeout = idle_timeout

    # ---- lifecycle ------------------------------------------------------

    def start(self, *, cwd: str | Path, kernel_name: str = DEFAULT_KERNEL_NAME) -> KernelSession:
        """Start a kernel, or raise :class:`KernelError` saying why not."""
        self.reap_idle()
        with self._lock:
            if len(self._sessions) >= self.max_kernels:
                raise KernelError(
                    "too-many-kernels",
                    f"{self.max_kernels} kernels are already running, which is the limit "
                    f"for one TI-Toolbox container. Shut one down and try again.",
                )

        try:
            from jupyter_client.manager import KernelManager
        except ImportError:  # pragma: no cover - the image installs it
            raise KernelError(
                "no-jupyter-client",
                "This TI-Toolbox container has no jupyter_client, so no notebook cell can "
                "run. Rebuild the image, or install it with: pip install jupyter_client",
            ) from None

        cwd_str = str(cwd)
        manager = KernelManager(kernel_name=kernel_name)
        try:
            manager.start_kernel(cwd=cwd_str)
            client = manager.client()
            client.start_channels()
            client.wait_for_ready(timeout=STARTUP_TIMEOUT_SECONDS)
        except Exception as error:
            # Best effort: a half-started kernel must not leak a process.
            try:
                manager.shutdown_kernel(now=True)
            except Exception:
                pass
            code = "no-kernelspec" if type(error).__name__ == "NoSuchKernel" else "start-failed"
            message = (
                f"No kernel named {kernel_name!r} is installed in this container. The image "
                f"registers 'simnibs'; check `jupyter kernelspec list` inside the container."
                if code == "no-kernelspec"
                else f"Could not start the kernel: {error}"
            )
            raise KernelError(code, message) from error

        spec = getattr(manager, "kernel_spec", None)
        session = KernelSession(
            id=uuid.uuid4().hex[:12],
            kernel_name=kernel_name,
            cwd=cwd_str,
            manager=manager,
            client=client,
            display_name=getattr(spec, "display_name", "") or kernel_name,
            language=getattr(spec, "language", "") or "",
        )
        with self._lock:
            self._sessions[session.id] = session

        self._start_pumps(session)
        logger.info("kernel %s started (%s) in %s", session.id, kernel_name, cwd_str)
        return session

    def _start_pumps(self, session: KernelSession) -> None:
        session.stopping.clear()
        session.pumps = [
            threading.Thread(
                target=self._pump_iopub,
                args=(session,),
                daemon=True,
                name=f"kernel-iopub-{session.id}",
            ),
            threading.Thread(
                target=self._pump_shell,
                args=(session,),
                daemon=True,
                name=f"kernel-shell-{session.id}",
            ),
        ]
        for pump in session.pumps:
            pump.start()

    def _stop_pumps(self, session: KernelSession) -> None:
        """Stop the channel pumps and WAIT for them to actually be gone.

        ZMQ sockets are not thread-safe, and ``jupyter_client``'s channels are
        ZMQ sockets. Tearing one down while a pump thread is still polling it is
        undefined behaviour, and the behaviour it chose here was
        ``Assertion failed: pfd.revents & POLLIN (src/signaler.cpp:238)`` --
        libzmq aborting the process. That is the whole SERVER, not one notebook:
        a restart taking every running job's API down with it.

        So the order is always stop, join, THEN touch the sockets. The join is
        bounded because a wedged pump must not make shutdown hang either; a
        thread that misses the deadline is a daemon and dies with the process.
        """
        session.stopping.set()
        for pump in session.pumps:
            if pump.is_alive():
                pump.join(timeout=PUMP_JOIN_TIMEOUT_S)
                if pump.is_alive():  # pragma: no cover - a wedged channel
                    logger.warning("kernel %s: %s did not stop", session.id, pump.name)
        session.pumps = []

    def get(self, kernel_id: str) -> KernelSession:
        with self._lock:
            session = self._sessions.get(kernel_id)
        if session is None:
            raise KernelError("no-such-kernel", f"No kernel {kernel_id!r} is running.")
        return session

    def list(self) -> list[KernelSession]:
        with self._lock:
            return list(self._sessions.values())

    def shutdown(self, kernel_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(kernel_id, None)
        if session is None:
            raise KernelError("no-such-kernel", f"No kernel {kernel_id!r} is running.")
        self._shutdown_session(session)

    def shutdown_all(self) -> None:
        """Called when the server stops, so no kernel outlives its owner."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            self._shutdown_session(session)

    def _shutdown_session(self, session: KernelSession) -> None:
        self._emit(session, {"type": "status", "state": "dead"})
        # Stop and join BEFORE closing the sockets, for `_stop_pumps`' reason.
        self._stop_pumps(session)
        try:
            session.client.stop_channels()
        except Exception as error:  # pragma: no cover - shutdown races
            logger.debug("kernel %s stop_channels: %s", session.id, error)
        try:
            session.manager.shutdown_kernel(now=False)
        except Exception as error:  # pragma: no cover
            logger.warning("kernel %s shutdown: %s", session.id, error)
        logger.info("kernel %s shut down", session.id)

    def reap_idle(self) -> list[str]:
        """Shut down kernels nobody has used lately. Returns their ids."""
        if self.idle_timeout <= 0:
            return []
        cutoff = time.time() - self.idle_timeout
        with self._lock:
            stale = [s for s in self._sessions.values() if s.last_used < cutoff]
            for session in stale:
                self._sessions.pop(session.id, None)
        for session in stale:
            logger.info("kernel %s reaped after %.0fs idle", session.id, self.idle_timeout)
            self._shutdown_session(session)
        return [s.id for s in stale]

    # ---- operations -----------------------------------------------------

    def execute(self, kernel_id: str, req_id: str, code: str) -> None:
        session = self.get(kernel_id)
        session.last_used = time.time()
        try:
            msg_id = session.client.execute(code, store_history=True, allow_stdin=False)
        except Exception as error:
            raise KernelError("op-failed", f"execute: {error}") from error
        with session.lock:
            session.pending[msg_id] = req_id

    def complete(self, kernel_id: str, req_id: str, code: str, cursor_pos: int) -> None:
        """Ask the kernel what could follow the cursor.

        This is `complete_request`, the same call Jupyter's own front end
        makes. It is answered by IPython's completer against the kernel's
        **live namespace**, so after the notebook has run its imports,
        ``tit.<Tab>`` lists what `tit` actually holds in that interpreter.
        """
        session = self.get(kernel_id)
        session.last_used = time.time()
        try:
            msg_id = session.client.complete(code, cursor_pos)
        except Exception as error:
            raise KernelError("op-failed", f"complete: {error}") from error
        with session.lock:
            session.queries[msg_id] = (req_id, "complete")

    def inspect(self, kernel_id: str, req_id: str, code: str, cursor_pos: int, detail: int = 0) -> None:
        """Ask the kernel about the name under the cursor (Jupyter's ⇧⇥)."""
        session = self.get(kernel_id)
        session.last_used = time.time()
        try:
            msg_id = session.client.inspect(code, cursor_pos, detail_level=detail)
        except Exception as error:
            raise KernelError("op-failed", f"inspect: {error}") from error
        with session.lock:
            session.queries[msg_id] = (req_id, "inspect")

    def interrupt(self, kernel_id: str) -> None:
        session = self.get(kernel_id)
        session.last_used = time.time()
        try:
            session.manager.interrupt_kernel()
        except Exception as error:
            raise KernelError("op-failed", f"interrupt: {error}") from error

    def restart(self, kernel_id: str) -> None:
        """Restart the interpreter, rebuilding the client around it.

        The pumps are stopped and joined first (:meth:`_stop_pumps` says why),
        and the client is REPLACED rather than reused: ``restart_kernel`` gives
        the new interpreter a new session key, and the old client's channels
        then reject every message with ``Invalid Signature`` -- which is what
        they did, until the socket teardown underneath aborted the process.
        """
        session = self.get(kernel_id)
        session.last_used = time.time()
        with session.lock:
            session.pending.clear()
            session.finishing.clear()
            session.queries.clear()
        self._emit(session, {"type": "status", "state": "starting"})

        self._stop_pumps(session)
        try:
            session.client.stop_channels()
        except Exception as error:  # pragma: no cover - already-closed channels
            logger.debug("kernel %s stop_channels before restart: %s", session.id, error)

        try:
            session.manager.restart_kernel(now=False)
            client = session.manager.client()
            client.start_channels()
            client.wait_for_ready(timeout=STARTUP_TIMEOUT_SECONDS)
        except Exception as error:
            # The pumps stay down: there is no live channel for them to poll,
            # and starting them on a dead kernel is how the abort happened.
            self._emit(session, {"type": "status", "state": "dead"})
            raise KernelError("op-failed", f"restart: {error}") from error

        session.client = client
        session.execution_state = "idle"
        self._start_pumps(session)
        self._emit(session, {"type": "ready", "kernel": session.describe()})

    # ---- events ---------------------------------------------------------

    def subscribe(self, kernel_id: str, listener: Listener) -> Callable[[], None]:
        """Attach a listener; returns the function that detaches it."""
        session = self.get(kernel_id)
        with session.lock:
            session.listeners.append(listener)

        def unsubscribe() -> None:
            with session.lock:
                if listener in session.listeners:
                    session.listeners.remove(listener)

        return unsubscribe

    def _emit(self, session: KernelSession, event: dict[str, Any]) -> None:
        with session.lock:
            listeners = list(session.listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as error:  # a dead socket must not kill the pump
                logger.debug("kernel %s listener failed: %s", session.id, error)

    def _finish_half(
        self, session: KernelSession, parent_id: str, half: str, content: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Record one half of a request's end; return the event when both are in.

        Returns ``None`` while the other channel is still to arrive, so the
        caller emits nothing — and exactly one caller ever emits.
        """
        with session.lock:
            if parent_id not in session.pending:
                return None
            state = session.finishing.setdefault(parent_id, {})
            if content is not None:
                state["content"] = content
            state[half] = True
            if not (state.get("reply") and state.get("idle")):
                return None
            req_id = session.pending.pop(parent_id, None)
            session.finishing.pop(parent_id, None)
        if req_id is None:  # pragma: no cover - popped by a restart
            return None
        reply = state.get("content", {})
        return {
            "type": "reply",
            "reqId": req_id,
            "status": reply.get("status", "ok"),
            "executionCount": reply.get("execution_count"),
        }

    def _req_id_for(self, session: KernelSession, parent: dict[str, Any]) -> str | None:
        parent_id = parent.get("msg_id")
        if parent_id is None:
            return None
        with session.lock:
            return session.pending.get(parent_id)

    def _pump_iopub(self, session: KernelSession) -> None:
        while not session.stopping.is_set():
            try:
                msg = session.client.get_iopub_msg(timeout=0.2)
            except queue.Empty:
                continue
            except Exception as error:
                if not session.stopping.is_set():
                    logger.info("kernel %s iopub ended: %s", session.id, error)
                return
            msg_type = msg["header"]["msg_type"]
            content = msg.get("content", {})
            if msg_type == "status":
                state = content.get("execution_state", "idle")
                session.execution_state = state
                self._emit(session, {"type": "status", "state": state})
                if state == "idle":
                    parent_id = msg.get("parent_header", {}).get("msg_id")
                    if parent_id:
                        event = self._finish_half(session, parent_id, "idle", None)
                        if event is not None:
                            self._emit(session, event)
                continue
            req_id = self._req_id_for(session, msg.get("parent_header", {}))
            if req_id is None:
                # Output with no cell to attribute it to (a background thread,
                # or another client's request). Dropping it is better than
                # pinning it to whichever cell ran last. — SUNA §16.2
                continue
            if msg_type == "execute_input":
                self._emit(
                    session,
                    {
                        "type": "input",
                        "reqId": req_id,
                        "executionCount": content.get("execution_count"),
                    },
                )
                continue
            if msg_type == "clear_output":
                self._emit(
                    session,
                    {"type": "clear", "reqId": req_id, "wait": bool(content.get("wait", False))},
                )
                continue
            if msg_type in OUTPUT_MSG_TYPES:
                output = output_from_msg(msg_type, content)
                if output is not None:
                    self._emit(session, {"type": "output", "reqId": req_id, "output": output})

    def _pump_shell(self, session: KernelSession) -> None:
        while not session.stopping.is_set():
            try:
                msg = session.client.get_shell_msg(timeout=0.2)
            except queue.Empty:
                continue
            except Exception as error:
                if not session.stopping.is_set():
                    logger.info("kernel %s shell ended: %s", session.id, error)
                return
            msg_type = msg["header"]["msg_type"]
            parent_id = msg.get("parent_header", {}).get("msg_id")
            if not parent_id:
                continue
            if msg_type in ("complete_reply", "inspect_reply"):
                with session.lock:
                    query = session.queries.pop(parent_id, None)
                if query is None:
                    continue
                self._emit(session, _query_event(query[0], msg_type, msg.get("content", {})))
                continue
            if msg_type != "execute_reply":
                continue
            event = self._finish_half(session, parent_id, "reply", msg.get("content", {}))
            if event is not None:
                self._emit(session, event)


_registry: KernelRegistry | None = None


def get_kernel_registry() -> KernelRegistry:
    """The process-wide registry, created on first use."""
    global _registry
    if _registry is None:
        _registry = KernelRegistry()
    return _registry


def reset_kernel_registry() -> None:
    """Drop the registry, shutting down whatever it still holds. Tests."""
    global _registry
    if _registry is not None:
        _registry.shutdown_all()
    _registry = None
