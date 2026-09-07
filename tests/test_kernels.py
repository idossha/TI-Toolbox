"""The notebook kernel registry and its routes, against a fake jupyter_client.

``jupyter_client`` is not installed on the host that runs this suite (it lives
in the container's SimNIBS Python, which is the whole point of §7.6), so a
fake stands in. The fake is not a stub of convenience: it reproduces the two
things the registry's correctness actually rests on — that iopub and shell are
separate channels polled with a timeout, and that an output is attributed to a
cell through ``parent_header.msg_id`` — so a test that passes here is testing
the attribution rule rather than a mock's memory.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server import kernels as kernels_mod  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


# --------------------------------------------------------------------------
# the fake kernel
# --------------------------------------------------------------------------


class FakeSpec:
    display_name = "SimNIBS + TI-Toolbox"
    language = "python"


class FakeClient:
    """A kernel that echoes: ``print(x)`` streams, an expression returns."""

    def __init__(self, manager: "FakeManager") -> None:
        self.manager = manager
        self.iopub: queue.Queue[dict[str, Any]] = queue.Queue()
        self.shell: queue.Queue[dict[str, Any]] = queue.Queue()
        self.channels_started = False
        self.ready_waits = 0
        self._seq = 0

    def start_channels(self) -> None:
        self.channels_started = True
        self.manager.log.append("start_channels")

    def stop_channels(self) -> None:
        self.channels_started = False
        self.manager.log.append("stop_channels")

    def wait_for_ready(self, timeout: float | None = None) -> None:
        self.ready_waits += 1

    def _msg(self, msg_type: str, content: dict[str, Any], parent: str) -> dict[str, Any]:
        return {
            "header": {"msg_type": msg_type},
            "parent_header": {"msg_id": parent},
            "content": content,
        }

    def execute(self, code: str, store_history: bool = True, allow_stdin: bool = False) -> str:
        self._seq += 1
        msg_id = f"m{self._seq}"
        self.manager.execution_count += 1
        count = self.manager.execution_count
        self.iopub.put(self._msg("status", {"execution_state": "busy"}, msg_id))
        self.iopub.put(self._msg("execute_input", {"execution_count": count}, msg_id))
        if code.startswith("print("):
            text = code[len("print(") : -1].strip().strip("'\"")
            self.iopub.put(self._msg("stream", {"name": "stdout", "text": text + "\n"}, msg_id))
        elif code.startswith("raise"):
            self.iopub.put(
                self._msg(
                    "error",
                    {"ename": "RuntimeError", "evalue": "boom", "traceback": ["boom"]},
                    msg_id,
                )
            )
            self.iopub.put(self._msg("status", {"execution_state": "idle"}, msg_id))
            self.shell.put(
                self._msg("execute_reply", {"status": "error", "execution_count": count}, msg_id)
            )
            return msg_id
        elif code.strip():
            self.iopub.put(
                self._msg(
                    "execute_result",
                    {"data": {"text/plain": code.strip()}, "metadata": {}, "execution_count": count},
                    msg_id,
                )
            )
        # An output nobody asked for: a background thread's print. The
        # registry must drop it rather than pin it to the last cell.
        self.iopub.put(self._msg("stream", {"name": "stdout", "text": "orphan\n"}, "unknown-msg"))
        self.iopub.put(self._msg("status", {"execution_state": "idle"}, msg_id))
        self.shell.put(
            self._msg("execute_reply", {"status": "ok", "execution_count": count}, msg_id)
        )
        return msg_id

    def complete(self, code: str, cursor_pos: int) -> str:
        self._seq += 1
        msg_id = f"c{self._seq}"
        prefix = code[:cursor_pos].split(".")[-1].split(" ")[-1]
        matches = [n for n in ("get_path_manager", "get_project", "run_simulation") if n.startswith(prefix)]
        self.shell.put(
            self._msg(
                "complete_reply",
                {
                    "matches": matches,
                    "cursor_start": cursor_pos - len(prefix),
                    "cursor_end": cursor_pos,
                    "metadata": {},
                    "status": "ok",
                },
                msg_id,
            )
        )
        return msg_id

    def inspect(self, code: str, cursor_pos: int, detail_level: int = 0) -> str:
        self._seq += 1
        msg_id = f"i{self._seq}"
        self.shell.put(
            self._msg(
                "inspect_reply",
                {"found": True, "data": {"text/plain": "Signature: get_path_manager(d=None)"}},
                msg_id,
            )
        )
        return msg_id

    def get_iopub_msg(self, timeout: float | None = None) -> dict[str, Any]:
        return self.iopub.get(timeout=timeout)

    def get_shell_msg(self, timeout: float | None = None) -> dict[str, Any]:
        return self.shell.get(timeout=timeout)


class NoSuchKernel(Exception):
    pass


class FakeManager:
    started: list[tuple[str, str | None]] = []

    def __init__(self, kernel_name: str = "python3") -> None:
        if kernel_name == "missing":
            self.kernel_name = kernel_name
        self.kernel_name = kernel_name
        self.kernel_spec = FakeSpec()
        self.execution_count = 0
        self.interrupts = 0
        self.restarts = 0
        self.shutdowns = 0
        #: Every lifecycle call, in order. The restart race is an ORDERING bug,
        #: so ordering is what has to be asserted.
        self.log: list[str] = []
        self.clients: list[FakeClient] = []
        self._client = FakeClient(self)

    def start_kernel(self, cwd: str | None = None) -> None:
        if self.kernel_name == "missing":
            raise NoSuchKernel(self.kernel_name)
        if self.kernel_name == "broken":
            raise RuntimeError("no interpreter")
        FakeManager.started.append((self.kernel_name, cwd))

    def client(self) -> FakeClient:
        # A real `KernelManager.client()` hands back a NEW client each call, and
        # after a restart the old one's session key is stale.
        self._client = FakeClient(self)
        self.clients.append(self._client)
        self.log.append("client")
        return self._client

    def interrupt_kernel(self) -> None:
        self.interrupts += 1

    def restart_kernel(self, now: bool = False) -> None:
        self.restarts += 1
        self.execution_count = 0
        self.log.append("restart_kernel")

    def shutdown_kernel(self, now: bool = False) -> None:
        self.shutdowns += 1
        self.log.append("shutdown_kernel")


@pytest.fixture(autouse=True)
def fake_jupyter_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put a fake ``jupyter_client.manager`` on ``sys.modules``."""
    FakeManager.started = []
    package = types.ModuleType("jupyter_client")
    manager_module = types.ModuleType("jupyter_client.manager")
    manager_module.KernelManager = FakeManager  # type: ignore[attr-defined]
    package.manager = manager_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jupyter_client", package)
    monkeypatch.setitem(sys.modules, "jupyter_client.manager", manager_module)
    kernels_mod.reset_kernel_registry()
    yield
    kernels_mod.reset_kernel_registry()


@pytest.fixture()
def registry() -> kernels_mod.KernelRegistry:
    return kernels_mod.KernelRegistry()


def drain(events: list[dict[str, Any]], predicate: Any, timeout: float = 3.0) -> dict[str, Any]:
    """Wait for the first event matching *predicate*, or fail saying so."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in list(events):
            if predicate(event):
                return event
        time.sleep(0.02)
    raise AssertionError(f"no matching event in {events!r}")


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------


def test_output_from_msg_is_nbformat_verbatim() -> None:
    # The claim §7.6 rests on: an iopub content IS an nbformat output once
    # output_type is added, which is why nothing translates between the live
    # kernel and the .ipynb.
    assert kernels_mod.output_from_msg("stream", {"name": "stderr", "text": "hi"}) == {
        "output_type": "stream",
        "name": "stderr",
        "text": "hi",
    }
    assert kernels_mod.output_from_msg("execute_result", {"data": {"text/plain": "2"}}) == {
        "output_type": "execute_result",
        "data": {"text/plain": "2"},
        "metadata": {},
        "execution_count": None,
    }
    assert kernels_mod.output_from_msg("comm_open", {}) is None


def test_start_runs_and_attributes_output(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000", kernel_name="simnibs")
    assert FakeManager.started == [("simnibs", "/mnt/000")]

    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.execute(session.id, "r1", "print('hello')")

    output = drain(events, lambda e: e["type"] == "output")
    assert output["reqId"] == "r1"
    assert output["output"] == {"output_type": "stream", "name": "stdout", "text": "hello\n"}

    reply = drain(events, lambda e: e["type"] == "reply")
    assert reply == {"type": "reply", "reqId": "r1", "status": "ok", "executionCount": 1}

    inputs = drain(events, lambda e: e["type"] == "input")
    assert inputs["executionCount"] == 1
    assert any(e["type"] == "status" and e["state"] == "busy" for e in events)


def test_unattributable_output_is_dropped(registry: kernels_mod.KernelRegistry) -> None:
    # SUNA §16.2: output with no parent is dropped rather than pinned to
    # whichever cell ran last. The fake emits exactly one such message.
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.execute(session.id, "r1", "print('hello')")
    drain(events, lambda e: e["type"] == "reply")
    time.sleep(0.1)
    texts = [e["output"].get("text") for e in events if e["type"] == "output"]
    assert "orphan\n" not in texts


def test_error_output_carries_its_traceback(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.execute(session.id, "r9", "raise RuntimeError('boom')")
    output = drain(events, lambda e: e["type"] == "output")
    assert output["output"]["output_type"] == "error"
    assert output["output"]["ename"] == "RuntimeError"
    reply = drain(events, lambda e: e["type"] == "reply")
    assert reply["status"] == "error"


def test_missing_kernelspec_and_broken_start_get_their_own_codes(
    registry: kernels_mod.KernelRegistry,
) -> None:
    with pytest.raises(kernels_mod.KernelError) as missing:
        registry.start(cwd="/mnt/000", kernel_name="missing")
    assert missing.value.code == "no-kernelspec"
    assert "simnibs" in missing.value.message

    with pytest.raises(kernels_mod.KernelError) as broken:
        registry.start(cwd="/mnt/000", kernel_name="broken")
    assert broken.value.code == "start-failed"


def test_missing_jupyter_client_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "jupyter_client.manager", None)
    registry = kernels_mod.KernelRegistry()
    with pytest.raises(kernels_mod.KernelError) as error:
        registry.start(cwd="/mnt/000")
    assert error.value.code == "no-jupyter-client"


def test_concurrency_is_capped(registry: kernels_mod.KernelRegistry) -> None:
    registry.max_kernels = 2
    registry.start(cwd="/mnt/000")
    registry.start(cwd="/mnt/000")
    with pytest.raises(kernels_mod.KernelError) as error:
        registry.start(cwd="/mnt/000")
    assert error.value.code == "too-many-kernels"
    assert "2 kernels" in error.value.message


def test_idle_kernels_are_reaped() -> None:
    registry = kernels_mod.KernelRegistry(idle_timeout=0.05)
    session = registry.start(cwd="/mnt/000")
    time.sleep(0.1)
    assert registry.reap_idle() == [session.id]
    assert registry.list() == []
    # A reaped kernel had its interpreter shut down, not merely forgotten.
    assert session.manager.shutdowns == 1


def test_a_used_kernel_is_not_reaped() -> None:
    registry = kernels_mod.KernelRegistry(idle_timeout=5.0)
    session = registry.start(cwd="/mnt/000")
    registry.execute(session.id, "r1", "print('x')")
    assert registry.reap_idle() == []
    assert [s.id for s in registry.list()] == [session.id]


def test_interrupt_restart_and_shutdown(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)

    registry.interrupt(session.id)
    assert session.manager.interrupts == 1

    registry.restart(session.id)
    assert session.manager.restarts == 1
    assert any(e["type"] == "status" and e["state"] == "starting" for e in events)
    assert any(e["type"] == "ready" for e in events)

    registry.shutdown(session.id)
    assert session.manager.shutdowns == 1
    with pytest.raises(kernels_mod.KernelError) as error:
        registry.get(session.id)
    assert error.value.code == "no-such-kernel"


def test_complete_answers_from_the_kernel(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)

    code = "from tit import get_p"
    registry.complete(session.id, "c1", code, len(code))
    event = drain(events, lambda e: e["type"] == "complete")
    assert event["reqId"] == "c1"
    assert event["matches"] == ["get_path_manager", "get_project"]
    # The range is the kernel's, not the client's guess: only the kernel knows
    # where the token it completed actually started.
    assert code[event["cursorStart"] : event["cursorEnd"]] == "get_p"


def test_inspect_answers_with_the_text_bundle(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.inspect(session.id, "i1", "get_path_manager", 5)
    event = drain(events, lambda e: e["type"] == "inspect")
    assert event == {
        "type": "inspect",
        "reqId": "i1",
        "found": True,
        "text": "Signature: get_path_manager(d=None)",
    }


def test_a_query_does_not_wait_for_an_iopub_idle(registry: kernels_mod.KernelRegistry) -> None:
    """The bug this guards against.

    An execute is finished by BOTH the shell reply and the iopub `idle`
    (`_finish_half`). A completion produces a shell reply and no iopub traffic
    at all, so routing it through that join would leave it waiting forever.
    """
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.complete(session.id, "c1", "get_pa", 6)
    drain(events, lambda e: e["type"] == "complete", timeout=1.0)
    with session.lock:
        assert session.queries == {}
        assert session.finishing == {}


def test_completion_and_execution_do_not_confuse_each_other(
    registry: kernels_mod.KernelRegistry,
) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.execute(session.id, "r1", "print('x')")
    registry.complete(session.id, "c1", "get_pa", 6)
    reply = drain(events, lambda e: e["type"] == "reply")
    completion = drain(events, lambda e: e["type"] == "complete")
    assert reply["reqId"] == "r1"
    assert completion["reqId"] == "c1"


def test_restart_stops_the_pumps_before_touching_the_sockets(
    registry: kernels_mod.KernelRegistry,
) -> None:
    """The regression this exists for, and it took the whole server down.

    ZMQ sockets are not thread-safe. Restarting while the iopub/shell pumps were
    still polling produced ``Invalid Signature`` and then
    ``Assertion failed: pfd.revents & POLLIN (src/signaler.cpp:238)`` -- libzmq
    aborting the process, taking every running job's API with it. Observed in
    the dev container, 2026-09-06.
    """
    session = registry.start(cwd="/mnt/000")
    manager = session.manager
    before = list(manager.log)
    assert session.pumps and all(pump.is_alive() for pump in session.pumps)

    registry.restart(session.id)

    steps = manager.log[len(before) :]
    # Channels are closed before the kernel is restarted, and only then is a new
    # client built. Any other order is the abort.
    assert steps.index("stop_channels") < steps.index("restart_kernel")
    assert steps.index("restart_kernel") < steps.index("client")
    # And the client is REPLACED: the old one's session key is stale after a
    # restart, which is where "Invalid Signature" came from.
    assert session.client is manager.clients[-1]
    assert session.client is not manager.clients[0]
    # New pumps, alive, polling the new channels.
    assert session.pumps and all(pump.is_alive() for pump in session.pumps)
    assert not session.stopping.is_set()


def test_a_kernel_still_runs_cells_after_a_restart(
    registry: kernels_mod.KernelRegistry,
) -> None:
    session = registry.start(cwd="/mnt/000")
    registry.restart(session.id)
    events: list[dict[str, Any]] = []
    registry.subscribe(session.id, events.append)
    registry.execute(session.id, "r1", "print('after restart')")
    output = drain(events, lambda e: e["type"] == "output")
    assert output["output"]["text"] == "after restart\n"
    # Execution counts start again from 1: a new interpreter, not the old one.
    assert drain(events, lambda e: e["type"] == "reply")["executionCount"] == 1


def test_shutdown_joins_the_pumps(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    pumps = list(session.pumps)
    registry.shutdown(session.id)
    assert not any(pump.is_alive() for pump in pumps)
    steps = session.manager.log
    assert steps.index("stop_channels") < steps.index("shutdown_kernel")


def test_unsubscribe_stops_delivery(registry: kernels_mod.KernelRegistry) -> None:
    session = registry.start(cwd="/mnt/000")
    events: list[dict[str, Any]] = []
    unsubscribe = registry.subscribe(session.id, events.append)
    unsubscribe()
    registry.execute(session.id, "r1", "print('x')")
    time.sleep(0.2)
    assert events == []


def test_a_failing_listener_does_not_stop_the_others(
    registry: kernels_mod.KernelRegistry,
) -> None:
    session = registry.start(cwd="/mnt/000")
    good: list[dict[str, Any]] = []

    def bad(_event: dict[str, Any]) -> None:
        raise RuntimeError("this listener is broken")

    registry.subscribe(session.id, bad)
    registry.subscribe(session.id, good.append)
    registry.execute(session.id, "r1", "print('x')")
    drain(good, lambda e: e["type"] == "reply")


# --------------------------------------------------------------------------
# the routes
# --------------------------------------------------------------------------


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_kernel_routes_lifecycle(client: TestClient, project: Path) -> None:
    empty = client.get("/api/kernels", headers=BEARER)
    assert empty.status_code == 200
    assert empty.json() == {"kernels": [], "max": 2, "idleTimeoutSeconds": 1800}

    started = client.post("/api/kernels", headers=BEARER, json={})
    assert started.status_code == 200
    body = started.json()
    assert body["name"] == "simnibs"
    assert body["displayName"] == "SimNIBS + TI-Toolbox"
    # The kernel's cwd is the project, not the notebook directory.
    assert body["cwd"] == str(project)
    kernel_id = body["id"]

    listed = client.get("/api/kernels", headers=BEARER).json()
    assert [k["id"] for k in listed["kernels"]] == [kernel_id]

    assert client.post(f"/api/kernels/{kernel_id}/interrupt", headers=BEARER).status_code == 200
    assert client.post(f"/api/kernels/{kernel_id}/restart", headers=BEARER).status_code == 200
    assert client.delete(f"/api/kernels/{kernel_id}", headers=BEARER).status_code == 200
    assert client.get("/api/kernels", headers=BEARER).json()["kernels"] == []


def test_kernel_routes_map_codes_to_status(client: TestClient) -> None:
    missing = client.post("/api/kernels", headers=BEARER, json={"kernelName": "missing"})
    assert missing.status_code == 501
    assert missing.json()["detail"]["code"] == "no-kernelspec"

    gone = client.delete("/api/kernels/nope", headers=BEARER)
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "no-such-kernel"

    client.post("/api/kernels", headers=BEARER, json={})
    client.post("/api/kernels", headers=BEARER, json={})
    third = client.post("/api/kernels", headers=BEARER, json={})
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "too-many-kernels"


def test_kernel_routes_need_auth(client: TestClient) -> None:
    assert client.get("/api/kernels").status_code == 401


def test_kernel_websocket_relays_a_cell(client: TestClient) -> None:
    kernel_id = client.post("/api/kernels", headers=BEARER, json={}).json()["id"]
    url = f"ws://127.0.0.1:8765/ws/kernels/{kernel_id}?token={TOKEN}"
    with client.websocket_connect(url) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"id": "r1", "op": "execute", "code": "print('2')"})
        seen: list[dict[str, Any]] = []
        for _ in range(12):
            event = socket.receive_json()
            seen.append(event)
            if event["type"] == "reply":
                break
    outputs = [e for e in seen if e["type"] == "output"]
    assert outputs[0]["reqId"] == "r1"
    assert outputs[0]["output"]["text"] == "2\n"
    assert seen[-1]["status"] == "ok"


def test_kernel_websocket_completes(client: TestClient) -> None:
    kernel_id = client.post("/api/kernels", headers=BEARER, json={}).json()["id"]
    url = f"ws://127.0.0.1:8765/ws/kernels/{kernel_id}?token={TOKEN}"
    code = "from tit import get_p"
    with client.websocket_connect(url) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"id": "c1", "op": "complete", "code": code, "cursorPos": len(code)})
        event = socket.receive_json()
        while event["type"] != "complete":
            event = socket.receive_json()
    assert event["matches"] == ["get_path_manager", "get_project"]

    with client.websocket_connect(url) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"id": "i1", "op": "inspect", "code": code, "cursorPos": 20})
        event = socket.receive_json()
        while event["type"] != "inspect":
            event = socket.receive_json()
    assert event["found"] is True
    assert "Signature" in event["text"]


def test_kernel_websocket_refuses_an_unknown_kernel(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect as Disconnect

    with pytest.raises(Disconnect) as error:
        with client.websocket_connect(f"ws://127.0.0.1:8765/ws/kernels/nope?token={TOKEN}"):
            pass
    assert error.value.code == 4404


def test_kernel_websocket_refuses_without_a_token(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect as Disconnect

    kernel_id = client.post("/api/kernels", headers=BEARER, json={}).json()["id"]
    with pytest.raises(Disconnect) as error:
        with client.websocket_connect(f"ws://127.0.0.1:8765/ws/kernels/{kernel_id}"):
            pass
    assert error.value.code == 4401


def test_ws_kernels_is_in_the_openapi_document(client: TestClient) -> None:
    schema = client.get("/api/openapi.json", headers=BEARER)
    if schema.status_code == 404:
        schema = client.get("/openapi.json", headers=BEARER)
    assert "/ws/kernels/{kernel_id}" in schema.json()["paths"]
