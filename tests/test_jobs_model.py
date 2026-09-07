"""Pure unit tests: spec (de)serialization, costs, kinds, and the lock-key table."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

import pytest

from tit.jobs import costs, kinds, locks
from tit.jobs import runner as jobs_runner
from tit.jobs.spec import (
    Artifact,
    Cost,
    JobError,
    JobProgress,
    JobSpec,
    JobStatus,
    WaitingOn,
)


@pytest.fixture(autouse=True, scope="module")
def _mock_scipy_ndimage_and_stats():
    """tit.stats.config's package __init__ eagerly imports tit.stats.permutation ->
    tit.stats.engine, which needs scipy.ndimage / scipy.stats. Neither is in
    tests/conftest.py's ``_MOCK_PACKAGES``; test_config_schema.py / test_plotting.py /
    test_pre_pipeline.py already carry this same fallback so importing tit.stats.config below
    (for the keys_for() lock-key tests) works regardless of pytest's file collection order.

    Scoped through ``pytest.MonkeyPatch`` (module-scoped: setup once before this file's first
    test, undone once after its last) rather than a bare module-level ``sys.modules[...] = ...``
    assignment, so a real ``scipy.ndimage``/``scipy.stats`` already present is never clobbered
    for good and a mock inserted here can never outlive this module's tests regardless of
    collection order (a plain, unscoped module-level mutation would do both).
    """
    mp = pytest.MonkeyPatch()
    for _mod in ("scipy.ndimage", "scipy.stats"):
        if _mod not in sys.modules:
            mp.setitem(sys.modules, _mod, MagicMock())
    yield
    mp.undo()


# ---------------------------------------------------------------------------------------------
# spec.py
# ---------------------------------------------------------------------------------------------


def test_cost_add_and_fits():
    a = Cost(cpus=2, mem_gb=4)
    b = Cost(cpus=1, mem_gb=2)
    total = a + b
    assert total.cpus == 3 and total.mem_gb == 6
    assert total.fits(Cost(cpus=3, mem_gb=6))
    assert not total.fits(Cost(cpus=2.9, mem_gb=6))


def test_job_spec_round_trip():
    spec = JobSpec(
        id="abc123",
        kind="sim",
        config={"subject_id": "001"},
        subject_ids=["001"],
        after=["dep1"],
        tags=["batch"],
        env={"FOO": "1"},
        locks=["subject:001:m2m:read"],
        cost=Cost(cpus=1, mem_gb=4),
        created_by="notebook",
        group_id="g1",
        group_cap=2,
        overwrite=True,
    )
    restored = JobSpec.from_dict(spec.to_dict())
    assert restored == spec


def test_job_spec_to_api_is_wire_shaped():
    spec = JobSpec(
        id="abc",
        kind="sim",
        config={"a": 1},
        subject_ids=["001"],
        after=["x"],
        tags=["t"],
        overwrite=True,
    )
    api = spec.to_api()
    assert set(api) == {"kind", "config", "subject_ids", "after", "tags", "overwrite"}
    assert (
        "id" not in api
        and "cost" not in api
        and "locks" not in api
        and "created_by" not in api
        and "group_cap" not in api
    )


def test_job_status_round_trip_and_api_strips_internals():
    status = JobStatus(
        id="j1",
        kind="ex",
        state="running",
        subject_ids=["001"],
        created_at="2026-01-01T00:00:00+00:00",
        started_at="2026-01-01T00:00:01+00:00",
        progress=JobProgress(stage="pair1", i=1, n=4, pct=25.0),
        liveness="active",
        waiting_on=[WaitingOn(key="k", job_id="other")],
        artifacts=[Artifact(path="/x/y.csv", kind="csv", label="results")],
        error=JobError(type="t", message="m", last_lines=["a", "b"]),
        exit_code=1,
        cpu_percent=12.5,
        rss=1024,
        pid=999,
        create_time=123.0,
        budget_wait="waiting for cpu",
    )
    restored = JobStatus.from_dict(status.to_dict())
    assert restored == status

    api = status.to_api()
    assert "pid" not in api and "create_time" not in api and "budget_wait" not in api
    assert api["progress"] == {"stage": "pair1", "i": 1, "n": 4, "pct": 25.0}
    assert api["waiting_on"] == [{"key": "k", "job_id": "other"}]
    assert api["artifacts"] == [{"path": "/x/y.csv", "kind": "csv", "label": "results"}]
    # ra_13 finding #6: log_path is derived from project_dir on the fly, not persisted --
    # None with no project_dir (e.g. this bare-dataclass test), the registry's real stdout
    # path convention once one is supplied.
    assert api["log_path"] is None
    from tit.jobs.registry import stdout_path

    assert status.to_api("/proj")["log_path"] == stdout_path("/proj", "j1")


def test_job_status_queued_factory():
    spec = JobSpec(id="j1", kind="sim", config={}, subject_ids=["001"], group_id="g1")
    status = JobStatus.queued(spec)
    assert status.state == "queued"
    assert status.id == "j1"
    assert status.group_id == "g1"
    assert status.progress is None and status.artifacts == []


# ---------------------------------------------------------------------------------------------
# costs.py
# ---------------------------------------------------------------------------------------------


def test_default_cost_table_lookup():
    assert costs.default_cost("leadfield") == Cost(cpus=2, mem_gb=8)
    assert costs.default_cost("unknown_kind_xyz") == costs._FALLBACK


def test_default_cost_legacy_viewer_kind_falls_back_without_crashing():
    # "viewer" was removed from JOB_KINDS/DEFAULT_COSTS (nothing submits it any more), but a
    # job.jsonl record persisted before that change may still carry kind="viewer" -- costing it
    # must never raise, just fall back to the generic default.
    assert costs.default_cost("viewer") == costs._FALLBACK


def test_default_cost_sim_scales_with_montage_count():
    one = costs.default_cost("sim", {"montages": [{"name": "m1"}]})
    two = costs.default_cost("sim", {"montages": [{"name": "m1"}, {"name": "m2"}]})
    none = costs.default_cost("sim", {})
    assert one.mem_gb == 4 and two.mem_gb == 8 and none.mem_gb == 4
    assert one.cpus == two.cpus == 1


def test_default_cost_config_override_wins():
    cost = costs.default_cost("pre", {"cpus": 6, "memory_gb": 12})
    assert cost == Cost(cpus=6, mem_gb=12)
    cost2 = costs.default_cost("flex", {"cpus": 4})
    assert cost2.cpus == 4 and cost2.mem_gb == 6  # mem stays at the table default


# ---------------------------------------------------------------------------------------------
# kinds.py
# ---------------------------------------------------------------------------------------------


def test_command_for_module_kind_needs_importable_module():
    # sim/pre/flex/... are always importable under this suite (conftest mocks simnibs).
    argv = kinds.command_for("sim", {}, "/proj/jobs/abc/spec.json")
    assert argv == ["simnibs_python", "-m", "tit.sim", "/proj/jobs/abc/spec.json"]


def test_command_for_leadfield():
    # tit.opt.leadfield_runner is B3's thin runner module; command_for() raises a clear
    # KindError instead if it's ever missing (module_exists() gate), exercised directly below.
    argv = kinds.command_for("leadfield", {}, "/proj/jobs/abc/spec.json")
    assert argv == [
        "simnibs_python",
        "-m",
        "tit.opt.leadfield_runner",
        "/proj/jobs/abc/spec.json",
    ]


def test_command_for_report():
    """F0: 'report' used to have no MODULE_FOR_KIND entry at all, so every trailing
    report job of a `pre` group failed with KindError("unknown job kind: 'report'")
    (jobs 614b666712054f03, d6ccfcce2e2c43ce). tit.pre.report is its runner now."""
    argv = kinds.command_for("report", {}, "/proj/jobs/abc/spec.json")
    assert argv == ["simnibs_python", "-m", "tit.pre.report", "/proj/jobs/abc/spec.json"]


def test_command_for_module_kind_missing_module_raises_clear_error(monkeypatch):
    monkeypatch.setitem(
        kinds.MODULE_FOR_KIND, "leadfield", "tit.opt.does_not_exist_xyz"
    )
    with pytest.raises(kinds.KindError, match="tit.opt.does_not_exist_xyz"):
        kinds.command_for("leadfield", {}, "/proj/jobs/abc/spec.json")


def test_command_for_legacy_viewer_kind_raises_clear_error():
    # D3: Freeview/Gmsh launchers and the "viewer" job kind are gone. A stray legacy request
    # for it must fail cleanly (KindError), never with a stale freeview/gmsh command line.
    with pytest.raises(kinds.KindError, match="unknown job kind"):
        kinds.command_for(
            "viewer", {"program": "freeview", "args": ["-v", "/x/T1.nii.gz"]}, "unused"
        )


def test_command_for_tools():
    argv = kinds.command_for(
        "tools", {"module": "tit.tools.check_for_update", "args": ["--quiet"]}, "unused"
    )
    assert argv == ["simnibs_python", "-m", "tit.tools.check_for_update", "--quiet"]

    with pytest.raises(kinds.KindError, match="module"):
        kinds.command_for("tools", {"module": "definitely.not.a.real.module"}, "unused")
    with pytest.raises(kinds.KindError):
        kinds.command_for("tools", {}, "unused")


@pytest.mark.parametrize(
    "module",
    [
        "timeit",  # ra_14 finding #2's PoC: arbitrary stdlib module execution
        "http.server",
        "pip",
        "os",
        "tit.tools",  # the package itself, not a specific tool script
        "tit.tools.",  # trailing dot, no module name at all
        "tit.toolsx.evil",  # prefix-looking but not actually under tit.tools
        "tit.jobs.kinds",  # importable, under tit.*, but not under tit.tools
        "tit.tools.__init__",  # rb_12 re-check: resolves inside TOOLS_DIR but is not a tool script
    ],
)
def test_command_for_tools_rejects_anything_outside_tit_tools(module):
    with pytest.raises(kinds.KindError, match="not an allowed tit.tools module"):
        kinds.command_for("tools", {"module": module}, "unused")


def test_command_for_tools_allowlist_checks_the_resolved_file_not_just_the_string():
    """A module string that starts with the right prefix but whose import machinery resolves
    somewhere other than tit/tools/ (e.g. shadowed on PYTHONPATH, or a name that simply isn't a
    real submodule) must still be rejected — checking the dotted string alone would not catch
    that (ra_14 finding #2's fix note: "verify it resolves under tit/tools/")."""
    assert kinds._resolve_tool_module_path("tit.tools.does_not_exist_xyz") is None
    real = kinds._resolve_tool_module_path("tit.tools.check_for_update")
    assert real is not None
    assert real.is_relative_to(kinds.TOOLS_DIR)
    assert real.name == "check_for_update.py"


def test_resolve_tool_module_path_rejects_dunder_init():
    """``tit.tools.__init__`` resolves under TOOLS_DIR just like a real tool script would (Python's
    import machinery treats a package's own __init__.py as importable by that dotted name) -- it
    must still be rejected, since it is the package marker, not a tool a caller should run
    (rb_12 re-check NEW issue)."""
    assert kinds._resolve_tool_module_path("tit.tools.__init__") is None


def test_command_for_unknown_kind():
    with pytest.raises(kinds.KindError, match="unknown job kind"):
        kinds.command_for("not_a_kind", {}, "unused")


# ---------------------------------------------------------------------------------------------
# runner.py: is_alive()/terminate_tree() refuse untouchable pids (ra_14 finding #5)
# ---------------------------------------------------------------------------------------------


def test_is_alive_refuses_pid_1_and_own_pid_even_with_a_matching_create_time():
    # A real, live create_time is used deliberately: the point is that _is_untouchable_pid()
    # short-circuits before create_time is ever consulted, not that these values fail to match.
    own_create_time = jobs_runner.psutil.Process(os.getpid()).create_time()
    assert jobs_runner.is_alive(1, None) is False
    assert jobs_runner.is_alive(os.getpid(), own_create_time) is False
    assert jobs_runner.is_alive(os.getpid(), None) is False


def test_is_alive_still_works_for_an_ordinary_live_pid():
    own_create_time = jobs_runner.psutil.Process(os.getpid()).create_time()
    # A pid this process didn't spawn but that is legitimately alive (this test process itself,
    # addressed via its parent) must not be swept up by the untouchable-pid guard.
    parent_pid = os.getppid()
    if parent_pid > 1:
        assert jobs_runner.is_alive(parent_pid, None) is True


@pytest.mark.parametrize("pid", [1, 0, -1])
def test_terminate_tree_is_a_noop_for_pid_1_and_below(pid):
    """Never even looks the pid up (a real ``psutil.Process(1)`` would exist on most hosts and
    is exactly what must not be signalled — see the module docstring)."""
    asyncio.run(
        jobs_runner.terminate_tree(pid)
    )  # must not raise, must not signal anything


def test_terminate_tree_is_a_noop_for_this_servers_own_pid():
    asyncio.run(jobs_runner.terminate_tree(os.getpid()))
    # Reaching this line at all (the test process is still running) is the assertion.


# ---------------------------------------------------------------------------------------------
# runner.py: runner_env() scrubs server secrets (ra_14 finding #10)
# ---------------------------------------------------------------------------------------------


def test_runner_env_scrubs_token_and_settings_file():
    """``tit/server/__main__.py``'s module docstring promises a spawned job's environment never
    carries ``TIT_SERVER_TOKEN`` (the shared auth secret) or ``TIT_SERVER_SETTINGS_FILE`` (a
    0600 JSON file that itself contains the token, handed to a ``--reload`` child) -- only the
    first one was actually scrubbed."""
    base_env = {
        "PATH": "/usr/bin",
        "TIT_SERVER_TOKEN": "super-secret",
        "TIT_SERVER_SETTINGS_FILE": "/tmp/settings-0600.json",
    }
    env = jobs_runner.runner_env("job1", "/proj/events.jsonl", base_env=base_env)
    assert "TIT_SERVER_TOKEN" not in env
    assert "TIT_SERVER_SETTINGS_FILE" not in env
    # Everything else the caller passed in survives.
    assert env["PATH"] == "/usr/bin"


def test_runner_env_scrub_is_a_noop_when_absent():
    env = jobs_runner.runner_env(
        "job1", "/proj/events.jsonl", base_env={"PATH": "/usr/bin"}
    )
    assert "TIT_SERVER_TOKEN" not in env
    assert "TIT_SERVER_SETTINGS_FILE" not in env


# ---------------------------------------------------------------------------------------------
# runner.py: runner_env() disables PETSc's own SIGTERM handler (lane FX2)
# ---------------------------------------------------------------------------------------------


def test_runner_env_disables_the_petsc_signal_handler():
    """PETSc installs a C SIGTERM handler on ``import simnibs`` -- in *every* runner, solver or
    not -- and turns a cancel into a ten-line "Caught signal number 15 / MPI_Abort" crash block
    (`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` open issue 2: a cancelled ``blender`` job,
    which runs no solver, ended that way). PETSc reads this variable, so one env entry covers
    every kind without touching a runner module."""
    env = jobs_runner.runner_env(
        "job1", "/proj/events.jsonl", base_env={"PATH": "/usr/bin"}
    )
    assert env["PETSC_OPTIONS"] == "-no_signal_handler"


def test_runner_env_keeps_petsc_options_the_caller_already_set():
    env = jobs_runner.runner_env(
        "job1",
        "/proj/events.jsonl",
        base_env={"PETSC_OPTIONS": "-ksp_monitor"},
    )
    assert env["PETSC_OPTIONS"].split() == ["-ksp_monitor", "-no_signal_handler"]
    # and never doubles it up on an environment that already carries it
    env = jobs_runner.runner_env(
        "job1",
        "/proj/events.jsonl",
        base_env={"PETSC_OPTIONS": "-no_signal_handler"},
    )
    assert env["PETSC_OPTIONS"].split().count("-no_signal_handler") == 1


# ---------------------------------------------------------------------------------------------
# locks.py: keys_for()
# ---------------------------------------------------------------------------------------------


def _resources(requests):
    return {(r.resource, r.mode) for r in requests}


def test_keys_for_sim_includes_montage_and_m2m_read():
    reqs = locks.keys_for(
        "sim",
        ["001"],
        {"montages": [{"name": "TI_test"}], "subject_id": "001"},
    )
    assert ("subject:001:m2m", "read") in _resources(reqs)
    assert ("subject:001:m2m:t1mni", "write") in _resources(reqs)
    assert ("subject:001:sim:TI_test", "write") in _resources(reqs)


def test_keys_for_leadfield_is_exclusive_write_on_m2m_and_leadfields():
    reqs = locks.keys_for("leadfield", ["001"], {})
    resources = _resources(reqs)
    assert ("subject:001:leadfields", "write") in resources
    assert ("subject:001:m2m", "write") in resources


def test_keys_for_ex_reads_leadfields_and_locks_run_name():
    reqs = locks.keys_for("ex", ["001"], {"run_name": "myrun"})
    resources = _resources(reqs)
    assert ("subject:001:ex:myrun", "write") in resources
    assert ("subject:001:leadfields", "read") in resources
    assert ("subject:001:m2m", "read") in resources


def test_keys_for_pre_uses_stage_field_when_present():
    reqs = locks.keys_for("pre", ["001"], {"stage": "charm"})
    resources = _resources(reqs)
    assert ("subject:001:stage:charm", "write") in resources
    assert ("subject:001:m2m", "write") in resources  # charm writes m2m


def test_keys_for_pre_falls_back_to_flags_or_coarse_lock():
    # Real PreprocessConfig flag names (tit/pre/config.py), as tit.jobs.plans.plan_preprocessing
    # emits them -- every stage flag but one forced False per job.
    reqs = locks.keys_for(
        "pre", ["001"], {"convert_dicom": True, "run_fastsurfer": True}
    )
    resources = _resources(reqs)
    assert ("subject:001:stage:dicom", "write") in resources
    assert ("subject:001:stage:fastsurfer", "write") in resources
    assert ("subject:001:bids", "write") in resources  # convert_dicom writes bids
    # dicom/fastsurfer do not write m2m
    assert ("subject:001:m2m", "write") not in resources

    coarse = locks.keys_for("pre", ["001"], {})
    assert _resources(coarse) == {("subject:001:stage:pre", "write")}


def test_keys_for_pre_matches_plan_preprocessing_stage_configs():
    """End-to-end sanity: every stage tit.jobs.plans.plan_preprocessing actually emits maps to
    a lock (no stage silently falls through to the generic "pre" fallback)."""
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    config = PreprocessConfig(
        subject_ids=["001"],
        convert_dicom=True,
        create_m2m=True,
        run_fastsurfer=True,
        run_tissue_analysis=True,
        run_qsiprep=True,
        run_qsirecon=True,
        extract_dti=True,
    )
    planned = plan_preprocessing(config, ["001"])
    stage_jobs = [j for j in planned if j.kind == "pre"]
    assert stage_jobs  # the fixture above should produce every G1-G6 stage
    for job in stage_jobs:
        resources = _resources(locks.keys_for(job.kind, job.subject_ids, job.config))
        stage_resources = {
            r for r, mode in resources if r.startswith("subject:001:stage:")
        }
        assert stage_resources, f"{job.label}: no stage lock derived from {job.config}"
        assert (
            "subject:001:stage:pre" not in stage_resources
        ), f"{job.label}: fell through to the coarse fallback"


def test_keys_for_report_holds_read_locks_for_what_it_scans():
    """FX2: a per-subject ``report`` job used to request *no* locks at all
    (`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` open issue 1) while ``scan_for_data()`` walked the
    subject's rawdata and derivatives -- only a top-level "group report" branch existed, and
    ``plan_preprocessing``'s config has no ``group`` key, so it never fired."""
    reqs = locks.keys_for(
        "report",
        ["001"],
        {"convert_dicom": True, "create_m2m": True, "run_fastsurfer": True},
    )
    resources = _resources(reqs)
    # what it reads
    assert ("subject:001:bids", "read") in resources
    assert ("subject:001:m2m", "read") in resources
    assert ("subject:001:stage:dicom", "read") in resources
    assert ("subject:001:stage:charm", "read") in resources
    assert ("subject:001:stage:fastsurfer", "read") in resources
    # a stage the group did not run is not locked
    assert ("subject:001:stage:qsiprep", "read") not in resources
    # what it writes: its own report, so two reports for one subject serialize
    assert ("subject:001:report", "write") in resources
    # nothing it takes may be exclusive apart from that one output
    assert {mode for _r, mode in resources if _r != "subject:001:report"} == {"read"}


def test_keys_for_report_of_a_planned_group_locks_that_subject_only():
    """The real shape: whatever ``plan_preprocessing`` hands the report job must produce locks
    scoped to its own subject, so two subjects' reports still run concurrently."""
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    config = PreprocessConfig(
        subject_ids=["001", "002"], convert_dicom=True, create_m2m=True
    )
    planned = plan_preprocessing(config, ["001", "002"])
    reports = [j for j in planned if j.kind == "report"]
    assert len(reports) == 2
    keys = {
        j.subject_ids[0]: _resources(locks.keys_for(j.kind, j.subject_ids, j.config))
        for j in reports
    }
    assert keys["001"] and keys["002"]
    assert not {r for r, _m in keys["001"]} & {r for r, _m in keys["002"]}
    for sid, resources in keys.items():
        assert all(r.startswith(f"subject:{sid}:") for r, _m in resources)


def test_plan_preprocessing_report_job_carries_every_requested_flag():
    """F0: the trailing report job's config used to be just {"subject_id": ...} --
    tit.pre.report needs the group's actual stage flags (not stage-narrowed like each
    G1..G6 job's own config) to know which steps to report on, so plan_preprocessing
    now serializes the *un-narrowed* PreprocessConfig, one subject at a time."""
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    config = PreprocessConfig(
        subject_ids=["001", "002"],
        convert_dicom=True,
        create_m2m=True,
        run_tissue_analysis=True,
    )
    planned = plan_preprocessing(config, ["001"])
    report_jobs = [j for j in planned if j.kind == "report"]
    assert len(report_jobs) == 1
    report = report_jobs[0]
    assert report.subject_ids == ["001"]
    assert report.config["subject_ids"] == ["001"]
    assert report.config["convert_dicom"] is True
    assert report.config["create_m2m"] is True
    assert report.config["run_tissue_analysis"] is True
    # A flag the caller never requested must not be reported as having run.
    assert report.config["run_fastsurfer"] is False
    # After every stage job planned for this subject, by label.
    stage_labels = {j.label for j in planned if j.kind == "pre"}
    assert set(report.after_labels) == stage_labels


def test_plan_preprocessing_no_jobs_no_report():
    """A subject with every step flag False plans no jobs at all, report included --
    plan_preprocessing's own contract (see its docstring's Returns section)."""
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    config = PreprocessConfig(subject_ids=["001"])
    assert plan_preprocessing(config, ["001"]) == []


def test_keys_for_viewer_and_tools_are_empty():
    assert locks.keys_for("viewer", ["001"], {"program": "freeview"}) == []
    assert locks.keys_for("tools", [], {"module": "x"}) == []


def test_keys_for_matches_sim_main_call_site():
    """tit/sim/__main__.py calls ``keys_for("sim", [config.subject_id], data)`` where *data*
    is the raw request dict (``project_dir`` already popped) -- exercise that exact shape via
    the real ``SimulationConfig``/``serialize_config`` round trip, not a hand-built dict.
    """
    from tit.config_io import serialize_config
    from tit.sim.config import Montage, MontageMode, SimulationConfig

    config = SimulationConfig(
        subject_id="001",
        montages=[
            Montage(
                name="TI_test",
                mode=MontageMode.NET,
                electrode_pairs=[("E1", "E2"), ("E3", "E4")],
                eeg_net="GSN-HydroCel-185.csv",
            )
        ],
    )
    data = serialize_config(config)
    reqs = locks.keys_for("sim", [config.subject_id], data)
    resources = _resources(reqs)
    assert ("subject:001:m2m", "read") in resources
    assert ("subject:001:m2m:t1mni", "write") in resources
    assert ("subject:001:sim:TI_test", "write") in resources


def test_keys_for_matches_ex_main_call_site():
    """tit/opt/ex/__main__.py calls ``keys_for("ex", [config.subject_id], data)`` the same
    way -- via the real ``ExConfig``/``serialize_config`` round trip."""
    from tit.config_io import serialize_config
    from tit.opt.config import ExConfig

    config = ExConfig(
        subject_id="001",
        leadfield_hdf="leadfield.hdf5",
        roi_name="roi1",
        electrodes=ExConfig.PoolElectrodes(electrodes=["E1", "E2", "E3", "E4"]),
        run_name="myrun",
    )
    data = serialize_config(config)
    reqs = locks.keys_for("ex", [config.subject_id], data)
    resources = _resources(reqs)
    assert ("subject:001:ex:myrun", "write") in resources
    assert ("subject:001:leadfields", "read") in resources
    assert ("subject:001:m2m", "read") in resources


def test_keys_for_analyzer_uses_the_real_output_dir_field():
    """tit/analyzer/config.py::AnalyzerConfig's field is ``output_dir`` (not
    ``analysis_output_dir``) -- exercised via the real dataclass/serialize_config round trip,
    the same shape tit/analyzer/__main__.py's ``_hold_locks`` call site passes."""
    from tit.analyzer.config import AnalyzerConfig
    from tit.config_io import serialize_config

    config = AnalyzerConfig(
        subject_id="001",
        analysis_type="spherical",
        center=[0.0, 0.0, 0.0],
        radius=5.0,
        output_dir="my_analysis",
    )
    data = serialize_config(config)
    reqs = locks.keys_for("analyzer", [config.subject_id], data)
    resources = _resources(reqs)
    assert ("subject:001:analysis:my_analysis", "write") in resources
    assert ("subject:001:m2m", "read") in resources


def test_keys_for_stats_uses_analysis_name_and_the_main_entrypoints_mode_key():
    """tit/stats/config.py's ``GroupComparisonConfig``/``CorrelationConfig`` have no
    ``analysis_type``/``output_dir``/``name`` field (and no config_io ``_type`` discriminator
    of their own -- that mechanism is for union-typed fields, not this top-level kind switch).
    The run's human name is ``analysis_name`` on both dataclasses; which one applies is a
    top-level ``mode`` key ``tit/stats/__main__.py`` itself pops off the request dict.
    """
    from tit.config_io import serialize_config
    from tit.stats.config import CorrelationConfig, GroupComparisonConfig

    comparison = GroupComparisonConfig(
        analysis_name="run1",
        subjects=[
            GroupComparisonConfig.Subject(
                subject_id="001", simulation_name="TI_test", response=1
            ),
            GroupComparisonConfig.Subject(
                subject_id="002", simulation_name="TI_test", response=0
            ),
        ],
    )
    comparison_data = serialize_config(comparison)
    assert "_type" not in comparison_data
    reqs = locks.keys_for("stats", [], comparison_data)
    resources = _resources(reqs)
    assert ("project:stats:group_comparison/run1", "write") in resources

    correlation_data = {
        **serialize_config(
            CorrelationConfig(
                analysis_name="run2",
                subjects=[
                    CorrelationConfig.Subject(
                        subject_id="001", simulation_name="TI_test", effect_size=1.0
                    ),
                    CorrelationConfig.Subject(
                        subject_id="002", simulation_name="TI_test", effect_size=2.0
                    ),
                    CorrelationConfig.Subject(
                        subject_id="003", simulation_name="TI_test", effect_size=3.0
                    ),
                ],
            )
        ),
        "mode": "correlation",
    }
    reqs = locks.keys_for("stats", [], correlation_data)
    resources = _resources(reqs)
    assert ("project:stats:correlation/run2", "write") in resources


def test_lock_request_key_property():
    assert locks.LockRequest("subject:001:m2m", "write").key == "subject:001:m2m:write"
    assert locks.parse_key("subject:001:m2m:write") == locks.LockRequest(
        "subject:001:m2m", "write"
    )
    assert locks.parse_key("subject:001:m2m:read") == locks.LockRequest(
        "subject:001:m2m", "read"
    )
    assert locks.parse_key("project:montage_list") == locks.LockRequest(
        "project:montage_list", "write"
    )


# ---------------------------------------------------------------------------------------------
# generic per-subject group plans (R3)
# ---------------------------------------------------------------------------------------------


def test_group_kind_classes_match_validate():
    """`tit.jobs.plans._KIND_CONFIG_CLASS` deliberately copies rows out of
    `tit.server.routes.validate.SIMPLE_KIND_CLASS` (jobs must not import server). This is the
    check that keeps the copy honest."""
    from tit.jobs.plans import _KIND_CONFIG_CLASS
    from tit.server.routes.validate import SIMPLE_KIND_CLASS

    for kind, cls_name in _KIND_CONFIG_CLASS.items():
        assert SIMPLE_KIND_CLASS[kind] == cls_name


def test_plan_per_subject_forces_each_config_to_its_own_subject(tmp_path):
    """One job per (subject, config) entry, each config carrying exactly its own subject id --
    no matter which subject the caller's template named."""
    from tit.jobs.plans import plan_per_subject
    from tit.paths import get_path_manager

    get_path_manager(str(tmp_path))
    template = {
        "subject_id": "whoever",
        "montages": [
            {
                "_type": "Montage",
                "name": "m1",
                "mode": "net",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            }
        ],
    }
    planned = plan_per_subject(
        "sim", [("001", template), ("002", template)], tags=["sim-batch"]
    )
    assert [p.kind for p in planned] == ["sim", "sim"]
    assert [p.subject_ids for p in planned] == [["001"], ["002"]]
    assert [p.config["subject_id"] for p in planned] == ["001", "002"]
    # Independent jobs: no intra-group dependency edges, so the cap is the only sequencer.
    assert all(p.after_labels == [] for p in planned)
    assert all(p.tags == ["sim-batch"] for p in planned)


def test_plan_per_subject_rejects_a_cohort_kind():
    from tit.jobs.plans import plan_per_subject

    with pytest.raises(ValueError, match="per-subject group"):
        plan_per_subject("analyzer", [("001", {})])
