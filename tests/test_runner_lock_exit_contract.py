"""Every job runner holds the locks the scheduler reserves for it and always emits ``exit``.

What this pins
--------------
1. Architecture (source read off disk with ``ast``, nothing imported): for every module in
   :data:`tit.jobs.kinds.MODULE_FOR_KIND` except ``project_init`` (which takes no locks), the
   entry file calls ``locks.hold_for_job(<a kind that maps to this module>, ...)`` (the one
   helper that holds ``locks.keys_for`` of that kind, ``tests/test_jobs_model.py``),
   enters that hold in a ``with`` statement, and the ``with`` sits inside a ``try`` whose
   ``finally`` calls ``events.emit_exit``. The kind -> module table is the independent source: a runner added for
   a new kind without the scaffold fails here by name. ``tit.opt.leadfield_runner`` did neither
   until 2026-10-22.
2. Plan/admission parity: while a runner that writes no lock descriptor of its own (the way the
   leadfield runner behaved) is running, ``JobManager.lock_conflicts`` -- what ``POST
   /api/plan/<kind>`` reports -- names that job for the same key the scheduler makes a queued
   ``sim`` wait on. The expected answer is the scheduler's own decision (``waiting_on``).
3. Restart: a leadfield job whose runner finished while the server was down is reconciled from
   the events the REAL runner wrote (``result`` + ``exit`` code 0) as ``succeeded``, not
   ``lost``; and while it ran, the lock directory held exactly the keys the manager recorded in
   ``spec.locks`` at submission.

Reproduce: ``.venv/bin/python -m pytest tests/test_runner_lock_exit_contract.py -q``.
Deliberately elsewhere: the lock table itself (``tests/test_jobs_locks*.py``), the fake-runner
lock tests (``tests/test_jobs_manager.py``). Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import ast
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.jobs import kinds, locks
from tit.jobs.manager import JobManager
from tit.jobs.registry import events_path, job_file_path
from tit.jobs.spec import Cost
from tit.jobs.tailer import read_events

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------------------------
# 1. static contract
# ---------------------------------------------------------------------------------------------


def _entry_file(module: str) -> Path:
    """``python -m <module>`` runs ``<pkg>/__main__.py`` for a package, else ``<module>.py``."""
    base = REPO.joinpath(*module.split("."))
    if base.is_dir():
        return base / "__main__.py"
    return base.with_suffix(".py")


def _modules() -> dict[str, set[str]]:
    by_module: dict[str, set[str]] = {}
    for kind, module in kinds.MODULE_FOR_KIND.items():
        if kind == "project_init":
            continue
        by_module.setdefault(module, set()).add(kind)
    return by_module


def _is_call(node: ast.AST, owner: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
    )


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def _contract_problems(module: str, module_kinds: set[str]) -> list[str]:
    path = _entry_file(module)
    if not path.is_file():
        return [f"{module}: entry file {path} does not exist"]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = _parents(tree)
    holds = [n for n in ast.walk(tree) if _is_call(n, "locks", "hold_for_job")]
    if not holds:
        return [f"{module}: no locks.hold_for_job(...) call in {path.name}"]

    problems: list[str] = []
    entered = False
    for hold in holds:
        kind = hold.args[0] if hold.args else None
        if isinstance(kind, ast.Constant):
            if kind.value not in module_kinds:
                problems.append(
                    f"{module}: holds the locks of kind {kind.value!r}, not one of "
                    f"{sorted(module_kinds)}"
                )
        elif len(module_kinds) == 1:
            # One kind per module: the kind is known, so it must be named.
            problems.append(f"{module}: the lock kind is computed, not named")
        if _entered_in_try_with_exit(tree, parents, hold):
            entered = True
    if not entered:
        problems.append(
            f"{module}: the lock hold is never entered in a `with` inside a try whose "
            "finally calls events.emit_exit"
        )
    return problems


def _entered_in_try_with_exit(tree, parents, site: ast.Call) -> bool:
    """True when *site*'s result is a ``with`` item (directly or through one variable) and
    that ``with`` statement sits in the body of a ``try`` whose ``finally`` emits ``exit``.
    """
    names = set()
    parent = parents.get(site)
    if isinstance(parent, ast.Assign):
        names = {t.id for t in parent.targets if isinstance(t, ast.Name)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        items = [item.context_expr for item in node.items]
        if not any(
            expr is site or (isinstance(expr, ast.Name) and expr.id in names)
            for expr in items
        ):
            continue
        ancestor = node
        while ancestor in parents:
            child, ancestor = ancestor, parents[ancestor]
            if (
                isinstance(ancestor, ast.Try)
                and child in ancestor.body
                and any(
                    _is_call(n, "events", "emit_exit")
                    for stmt in ancestor.finalbody
                    for n in ast.walk(stmt)
                )
            ):
                return True
    return False


def test_the_table_has_runner_modules_to_check():
    modules = _modules()
    # Every kind except project_init: an empty table would make the contract test vacuous.
    assert set().union(*modules.values()) == set(kinds.MODULE_FOR_KIND) - {
        "project_init"
    }
    assert "tit.opt.leadfield_runner" in modules


@pytest.mark.parametrize("module", sorted(_modules()))
def test_runner_holds_its_kinds_locks_and_emits_exit_in_finally(module):
    assert _contract_problems(module, _modules()[module]) == []


def test_the_static_check_refuses_a_runner_without_the_scaffold(tmp_path, monkeypatch):
    """The check itself must be able to fail: the pre-fix leadfield runner shape."""
    pkg = tmp_path / "fake_runner_pkg.py"
    pkg.write_text(
        "import sys\n"
        "def main():\n"
        "    from tit.jobs import events\n"
        "    events.emit_result({})\n"
        "    sys.exit(0)\n"
    )
    monkeypatch.setitem(globals(), "REPO", tmp_path)
    assert _contract_problems("fake_runner_pkg", {"leadfield"}) == [
        "fake_runner_pkg: no locks.hold_for_job(...) call in fake_runner_pkg.py"
    ]


def test_the_static_check_refuses_another_kinds_locks(tmp_path, monkeypatch):
    (tmp_path / "wrong_kind.py").write_text(
        "from tit.jobs import locks\n"
        "def main():\n"
        "    from tit.jobs import events\n"
        "    lock_cm = locks.hold_for_job('sim', ['001'], {})\n"
        "    try:\n"
        "        with lock_cm:\n"
        "            pass\n"
        "    finally:\n"
        "        events.emit_exit(0)\n"
    )
    monkeypatch.setitem(globals(), "REPO", tmp_path)
    assert _contract_problems("wrong_kind", {"leadfield"}) == [
        "wrong_kind: holds the locks of kind 'sim', not one of ['leadfield']"
    ]


# ---------------------------------------------------------------------------------------------
# 2. plan / admission parity while a lock-less runner is running
# ---------------------------------------------------------------------------------------------


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.02)
    raise AssertionError(f"condition not met within {timeout}s (last value: {last!r})")


def _sleeper(kind, config, spec_path):
    # Holds no lock descriptor of its own: what a runner without locks.hold looks like.
    return [sys.executable, "-c", "import time; time.sleep(30)"]


SIM_CONFIG = {
    "subject_id": "001",
    "montages": [
        {
            "_type": "Montage",
            "name": "m1",
            "mode": "net",
            "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-HydroCel-185.csv",
        }
    ],
}


def test_plan_lock_conflicts_see_a_running_job_that_wrote_no_lock_descriptor(tmp_path):
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=_sleeper,
    )
    manager.start()
    try:
        leadfield = manager.submit(
            "leadfield", {"subject_id": "001", "eeg_net": "net"}, ["001"]
        )
        _wait_until(lambda: manager.get(leadfield["id"])["state"] == "running")
        assert locks.holders(str(tmp_path)) == []  # nothing on disk to find

        sim = manager.submit("sim", SIM_CONFIG, ["001"])
        waiting = _wait_until(lambda: manager.get(sim["id"])["waiting_on"])
        # The scheduler's decision is the oracle: the sim waits on the leadfield's m2m write.
        assert waiting == [{"key": "subject:001:m2m:write", "job_id": leadfield["id"]}]

        sim_keys = [r.key for r in locks.keys_for("sim", ["001"], SIM_CONFIG)]
        conflicts = manager.lock_conflicts(sim_keys)
        assert [(c["key"], c["held_by"]) for c in conflicts] == [
            (w["key"], w["job_id"]) for w in waiting
        ]
        assert conflicts[0]["kind"] == "leadfield"
        assert conflicts[0]["subject"] == "001"

        # A key nobody holds is not reported: the reservation is not a blanket conflict.
        assert manager.lock_conflicts(["subject:002:m2m:read"]) == []
    finally:
        for job in manager.list_jobs():
            manager.cancel(job["id"])
        manager.shutdown()


# ---------------------------------------------------------------------------------------------
# 3. the real leadfield runner's events reconcile a restart
# ---------------------------------------------------------------------------------------------


@pytest.fixture()
def _quiet_runner_logging(monkeypatch):
    """The runner attaches stream handlers to process-wide loggers; keep them out of the suite."""
    import tit.logger
    from tit.jobs import events
    from tit.paths import reset_path_manager

    monkeypatch.setattr(tit.logger, "setup_logging", lambda *a, **k: None)
    monkeypatch.setattr(tit.logger, "add_stream_handler", lambda *a, **k: None)
    events._reset_state()
    yield
    events._reset_state()
    reset_path_manager()


def _run_leadfield_in_process(tmp_path, monkeypatch, generate):
    """Submit a leadfield job (never started), then run the REAL runner's ``main()`` for it in
    this process with ``LeadfieldGenerator.generate`` replaced by *generate*.

    Returns ``(project, submitter, job_id, outcome)``; *outcome* is the ``SystemExit`` or the
    exception ``main()`` ended with. The job record is then made to look like the server went
    away mid-run (state running, pid gone), ready for a restarted manager to reconcile.
    """
    from tit.opt import leadfield_runner

    project = str(tmp_path)
    submitter = JobManager(project, budget=Cost(cpus=8, mem_gb=64))  # never started
    job = submitter.submit(
        "leadfield",
        {"subject_id": "001", "eeg_net": "GSN-HydroCel-185", "overwrite": True},
        ["001"],
    )
    job_id = job["id"]
    config_path = job_file_path(project, job_id, "config.json")
    Path(config_path).write_text(
        json.dumps(
            {
                "project_dir": project,
                "subject_id": "001",
                "eeg_net": "GSN-HydroCel-185",
                "overwrite": True,
            }
        )
    )
    generator = MagicMock()
    generator.list_leadfields.return_value = []
    generator.generate.side_effect = generate
    monkeypatch.setattr(
        leadfield_runner, "LeadfieldGenerator", MagicMock(return_value=generator)
    )
    monkeypatch.setenv("TIT_JOB_ID", job_id)
    monkeypatch.setenv("TIT_EVENTS_FILE", events_path(project, job_id))
    monkeypatch.setattr(sys, "argv", ["leadfield_runner", config_path])

    try:
        leadfield_runner.main()
    except (
        BaseException
    ) as exc:  # SystemExit on success, the generator's error on failure
        outcome = exc
    else:  # pragma: no cover - main() always ends in sys.exit or an exception
        outcome = None

    status = submitter.registry.read_status(job_id)
    status.state, status.pid, status.create_time = "running", 999_999_999, 0.0
    submitter.registry.write_status(status)
    return project, submitter, job_id, outcome


def _reconciled_after_restart(project: str, job_id: str) -> dict:
    restarted = JobManager(project, budget=Cost(cpus=8, mem_gb=64))
    restarted.start()
    try:
        return _wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                restarted.get(job_id)
            )
        )
    finally:
        restarted.shutdown()


def test_a_leadfield_that_finished_while_the_server_was_down_is_succeeded(
    tmp_path, monkeypatch, _quiet_runner_logging
):
    project = str(tmp_path)
    hdf5 = str(tmp_path / "leadfields" / "001_leadfield_GSN-HydroCel-185.hdf5")
    held_while_running: list[list[str]] = []

    def _generate(**_kwargs):
        # reconcile_stale=False: the runner runs in this test's process, whose pid
        # tit.jobs.runner.is_alive never counts as a live holder (it is "the server's").
        running = os.environ["TIT_JOB_ID"]
        on_disk = locks.holders(project, reconcile_stale=False)
        held_while_running.append(
            sorted(h["key"] for h in on_disk if h["job_id"] == running)
        )
        return hdf5

    project, submitter, job_id, outcome = _run_leadfield_in_process(
        tmp_path, monkeypatch, _generate
    )
    assert isinstance(outcome, SystemExit) and outcome.code == 0
    assert held_while_running == [sorted(submitter._specs[job_id].locks)]
    # released on the way out
    assert locks.holders(project, reconcile_stale=False) == []
    assert [
        e["code"]
        for e in read_events(events_path(project, job_id))
        if e["type"] == "exit"
    ] == [0]

    final = _reconciled_after_restart(project, job_id)
    assert final["state"] == "succeeded"
    assert final["exit_code"] == 0
    assert final["error"] is None
    assert [a["path"] for a in final["artifacts"]] == [hdf5]


def test_a_leadfield_that_crashed_while_the_server_was_down_is_failed(
    tmp_path, monkeypatch, _quiet_runner_logging
):
    """The failure path of the same scaffold: ``generate`` raising must still release the
    locks and write ``exit`` with code 1, and the restart must read that as ``failed``. An
    ``exit`` of 0 here would reconcile a crashed leadfield as ``succeeded`` (``_finalize_
    interrupted`` decides by the recorded code), so the code itself is what this pins.
    """

    def _crash(**_kwargs):
        raise RuntimeError("SimNIBS leadfield solve failed")

    project, _submitter, job_id, outcome = _run_leadfield_in_process(
        tmp_path, monkeypatch, _crash
    )
    # The generator's error propagates (the job's log gets the traceback); nothing swallows it.
    assert isinstance(outcome, RuntimeError)
    assert str(outcome) == "SimNIBS leadfield solve failed"
    assert locks.holders(project, reconcile_stale=False) == []
    events = read_events(events_path(project, job_id))
    assert [e["code"] for e in events if e["type"] == "exit"] == [1]
    assert not any(e["type"] == "result" for e in events)

    final = _reconciled_after_restart(project, job_id)
    assert final["state"] == "failed"
    assert final["exit_code"] == 1
    assert final["error"]["type"] == "runner_failed"
    assert final["error"]["message"] == "exited with code 1"
