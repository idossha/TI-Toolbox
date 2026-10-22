"""Every job runner holds the locks the scheduler reserves for it and always emits ``exit``.

What this pins
--------------
1. Architecture (source read off disk with ``ast``, nothing imported): for every module in
   :data:`tit.jobs.kinds.MODULE_FOR_KIND` except ``project_init`` (which takes no locks), the
   entry file calls ``locks.hold(..., requests)`` with ``requests`` built by
   ``locks.keys_for(<a kind that maps to this module>, ...)``, enters that hold in a ``with``
   statement, and the ``with`` sits inside a ``try`` whose ``finally`` calls
   ``events.emit_exit``. The kind -> module table is the independent source: a runner added for
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
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.jobs import kinds, locks
from tit.jobs.manager import JobManager
from tit.jobs.registry import events_path, job_file_path
from tit.jobs.spec import Cost

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


def _enclosing_function(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def _requests_source(hold: ast.Call, function) -> ast.Call | None:
    """The ``locks.keys_for(...)`` call the hold's requests come from, or ``None``."""
    named = [kw.value for kw in hold.keywords if kw.arg == "requests"]
    requests = hold.args[2] if len(hold.args) >= 3 else (named[0] if named else None)
    if requests is None:
        return None
    if _is_call(requests, "locks", "keys_for"):
        return requests
    if isinstance(requests, ast.Name) and function is not None:
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == requests.id
                    for t in node.targets
                )
                and _is_call(node.value, "locks", "keys_for")
            ):
                return node.value
    return None


def _contract_problems(module: str, module_kinds: set[str]) -> list[str]:
    path = _entry_file(module)
    if not path.is_file():
        return [f"{module}: entry file {path} does not exist"]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = _parents(tree)
    holds = [n for n in ast.walk(tree) if _is_call(n, "locks", "hold")]
    if not holds:
        return [f"{module}: no locks.hold(...) call in {path.name}"]

    problems: list[str] = []
    entered = False
    for hold in holds:
        function = _enclosing_function(hold, parents)
        source = _requests_source(hold, function)
        if source is None or not source.args:
            problems.append(f"{module}: locks.hold requests do not come from keys_for")
            continue
        kind_arg = source.args[0]
        # The calls whose result is the hold: the helper's own call sites, or the hold itself.
        if isinstance(kind_arg, ast.Constant):
            sites = [hold]
            kind_values = [kind_arg]
        else:
            params = [a.arg for a in function.args.args] if function else []
            if not (isinstance(kind_arg, ast.Name) and kind_arg.id in params):
                problems.append(
                    f"{module}: keys_for kind is not a constant or parameter"
                )
                continue
            position = params.index(kind_arg.id)
            sites = [
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == function.name
            ]
            if not sites:
                problems.append(f"{module}: {function.name}() is never called")
                continue
            kind_values = [site.args[position] for site in sites]
        for value in kind_values:
            if isinstance(value, ast.Constant):
                if value.value not in module_kinds:
                    problems.append(
                        f"{module}: holds the locks of kind {value.value!r}, not one of "
                        f"{sorted(module_kinds)}"
                    )
            elif len(module_kinds) == 1:
                # One kind per module: the kind is known, so it must be named.
                problems.append(f"{module}: the lock kind is computed, not named")
        for site in sites:
            if _entered_in_try_with_exit(tree, parents, site):
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
        "fake_runner_pkg: no locks.hold(...) call in fake_runner_pkg.py"
    ]


def test_the_static_check_refuses_another_kinds_locks(tmp_path, monkeypatch):
    (tmp_path / "wrong_kind.py").write_text(
        "def _hold_locks(kind, subject_ids, config):\n"
        "    from tit.jobs import locks\n"
        "    requests = locks.keys_for(kind, subject_ids, config)\n"
        "    return locks.hold('/p', 'job', requests)\n"
        "def main():\n"
        "    from tit.jobs import events\n"
        "    lock_cm = _hold_locks('sim', ['001'], {})\n"
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


def test_a_leadfield_that_finished_while_the_server_was_down_is_succeeded(
    tmp_path, monkeypatch, _quiet_runner_logging
):
    from tit.opt import leadfield_runner

    project = str(tmp_path)
    submitter = JobManager(project, budget=Cost(cpus=8, mem_gb=64))  # never started
    job = submitter.submit(
        "leadfield",
        {"subject_id": "001", "eeg_net": "GSN-HydroCel-185", "overwrite": True},
        ["001"],
    )
    job_id = job["id"]
    recorded_locks = sorted(submitter._specs[job_id].locks)

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
    held_while_running: list[list[str]] = []
    hdf5 = str(tmp_path / "leadfields" / "001_leadfield_GSN-HydroCel-185.hdf5")

    def _generate(**_kwargs):
        # reconcile_stale=False: the runner runs in this test's process, whose pid
        # tit.jobs.runner.is_alive never counts as a live holder (it is "the server's").
        on_disk = locks.holders(project, reconcile_stale=False)
        held_while_running.append(
            sorted(h["key"] for h in on_disk if h["job_id"] == job_id)
        )
        return hdf5

    generator = MagicMock()
    generator.list_leadfields.return_value = []
    generator.generate.side_effect = _generate
    monkeypatch.setattr(
        leadfield_runner, "LeadfieldGenerator", MagicMock(return_value=generator)
    )
    monkeypatch.setenv("TIT_JOB_ID", job_id)
    monkeypatch.setenv("TIT_EVENTS_FILE", events_path(project, job_id))
    monkeypatch.setattr(sys, "argv", ["leadfield_runner", config_path])

    with pytest.raises(SystemExit) as exited:
        leadfield_runner.main()
    assert exited.value.code == 0
    assert held_while_running == [recorded_locks]
    assert (
        locks.holders(project, reconcile_stale=False) == []
    )  # released on the way out

    # The server went away while the job "ran": its record still says running, pid gone.
    status = submitter.registry.read_status(job_id)
    status.state, status.pid, status.create_time = "running", 999_999_999, 0.0
    submitter.registry.write_status(status)

    restarted = JobManager(project, budget=Cost(cpus=8, mem_gb=64))
    restarted.start()
    try:
        final = _wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                restarted.get(job_id)
            )
        )
        assert final["state"] == "succeeded"
        assert final["exit_code"] == 0
        assert final["error"] is None
        assert [a["path"] for a in final["artifacts"]] == [hdf5]
    finally:
        restarted.shutdown()
