"""Recorded UI submissions replayed through the job manager into each runner's ``main()``.

What this pins: a body the desktop submits (``tests/smoke/payloads/*.json``, recorded from the
real app, and every accepted case of the desktop-config corpus ``tests/fixtures/desktop_configs``)
travels ``JobManager.submit`` -> ``JobManager._runner_config_path`` (the ``config.json`` the
runner reads) -> ``python -m tit.<kind>``'s ``main()`` and reaches the right science entry point
with the values the user chose. Offline: the one science call per runner is replaced by a
recorder, nothing is simulated or optimised.

Per replay it asserts:

- the runner exits 0 and calls exactly the dispatch target its kind (and ``_type``/mode) names;
- ``config.json`` carries ``project_dir`` = the project and, for the flex kinds, ``mode`` = kind;
- the typed config the target receives serialises back to the submitted value, key by key (the
  expected values are the recorded JSON itself);
- the runner's own lock request (captured at ``tit.jobs.locks.hold``) equals ``spec.locks``, which
  the manager computed at submit time;
- every line of the job's events file validates against ``contracts/events.schema.json``;
- for corpus cases, the call matches ``expect`` -- the UI selection the page showed (the currents
  a row displays, the focality mode picked, the analysis type, the space, the group labels).

The flex recorder also runs ``tit.opt.flex.flex._validate_flex_inputs`` -- the runner's own
precondition before any compute -- since a config the runner refuses there never runs.

Known gaps (``tests/fixtures/desktop_configs/known_gaps/*.json`` with ``"dispatch"`` in
``checks``) are ``xfail(strict=True)``. Reproduce:
``.venv/bin/python -m pytest tests/test_runner_dispatch_replay.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tests.test_desktop_config_corpus import (
    PAGES,
    _case_files,
    known_gap_marks,
    load_case,
    make_project,
)
from tit.config_io import serialize_config
from tit.jobs import kinds
from tit.jobs.manager import JobManager
from tit.jobs.plans import GROUP_KINDS
from tit.jobs.spec import Cost

REPO = Path(__file__).resolve().parents[1]
PAYLOADS = REPO / "tests" / "smoke" / "payloads"
EVENTS_SCHEMA = json.loads((REPO / "contracts" / "events.schema.json").read_text())

#: kind -> the runner module ``python -m`` runs (the manager's own table).
RUNNER_MODULE = {
    kind: f"{module}.__main__" for kind, module in kinds.MODULE_FOR_KIND.items()
}
RUNNER_MODULE["nifti_average"] = "tit.stats.nifti_average"


# ---------------------------------------------------------------------------------------------
# The recorder: one science entry per runner, patched where the runner looks it up.
# ---------------------------------------------------------------------------------------------
class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.locks: list[list[str]] = []
        self.env: dict[str, str] = {}
        self.ctor: list[dict[str, Any]] = []
        self.prechecks: list[str] = []

    def record(self, name: str, payload: Any) -> None:
        self.calls.append((name, payload))


def _flex_target(rec: Recorder, name: str):
    def run(config):
        from tit.opt.flex.flex import _validate_flex_inputs

        _validate_flex_inputs(config)
        rec.record(name, config)
        return SimpleNamespace(
            success=True,
            output_folder=config.output_folder,
            best_value=1.0,
            best_run_index=0,
        )

    return run


#: The simulation a montage-publication case names, as the simulator writes its
#: ``documentation/config.json``: a net montage, and a free-hand one with XYZ electrodes.
_MONTAGE_SIMS = {
    "M1": {
        "eeg_net": "GSN-HydroCel-185.csv",
        "electrode_pairs": [["E010", "E011"], ["E012", "E013"]],
    },
    "FH1": {
        "eeg_net": None,
        "electrode_pairs": [
            [[-40, 20, 60], [40, 20, 60]],
            [[-50, -20, 40], [50, -20, 40]],
        ],
    },
}


class _Reached(Exception):
    """The montage builder got past every config check to the EEG-net lookup."""


def _montage_target(rec: Recorder):
    """``run_montage``, run for real up to its EEG-net lookup (the last check before Blender).

    The STL exports are replaced; ``_resolve_eeg_net_csv`` stops the build once every check the
    runner makes on the simulation's own config has passed.
    """

    def run(config, **_):
        from tit.blender import montage_publication as mp

        def reached(**kwargs):
            raise _Reached(kwargs["eeg_net_name"])

        with (
            patch.object(mp, "export_scalp_stl_from_sim"),
            patch.object(mp, "export_gm_stl_from_sim"),
            patch.object(mp, "_resolve_eeg_net_csv", reached),
        ):
            try:
                mp.build_montage_publication_blend(
                    subject_id=config.subject_id,
                    simulation_name=config.simulation_name,
                    output_dir=config.output_dir,
                    show_full_net=config.show_full_net,
                    electrode_diameter_mm=config.electrode_diameter_mm,
                    electrode_height_mm=config.electrode_height_mm,
                )
            except _Reached:
                pass
        rec.record("run_montage", config)
        return SimpleNamespace(final_blend=None)

    return run


def _science_patches(kind: str, rec: Recorder) -> list:
    """``unittest.mock.patch`` objects replacing *kind*'s science entry with *rec*."""

    def opt_result(name):
        def run(config):
            rec.record(name, config)
            return SimpleNamespace(
                success=True,
                results_csv=None,
                config_json=None,
                output_dir=None,
                n_combinations=1,
            )

        return run

    def stats_result(name):
        def run(config):
            rec.record(name, config)
            return SimpleNamespace(
                success=True, n_significant_clusters=0, output_dir=None
            )

        return run

    if kind == "sim":

        def run_simulation(config, **_):
            rec.record("run_simulation", config)
            rec.env = {
                k: v for k, v in os.environ.items() if k.startswith("TISSUE_COND_")
            }
            return [{"status": "completed", "montage_name": config.montages[0].name}]

        return [patch("tit.sim.__main__.run_simulation", run_simulation)]
    if kind in kinds.FLEX_KINDS:
        return [
            patch(
                "tit.opt.flex.__main__.run_flex_search",
                _flex_target(rec, "run_flex_search"),
            ),
            patch(
                "tit.opt.flex.__main__.run_adaptive_focality",
                _flex_target(rec, "run_adaptive_focality"),
            ),
            patch(
                "tit.opt.flex.__main__.run_pareto_sweep",
                _flex_target(rec, "run_pareto_sweep"),
            ),
        ]
    if kind == "ex":
        return [patch("tit.opt.ex.__main__.run_ex_search", opt_result("run_ex_search"))]
    if kind == "mex":
        return [
            patch("tit.opt.mex.__main__.run_m_ex_search", opt_result("run_m_ex_search"))
        ]
    if kind == "analyzer":
        instance = MagicMock(name="analyzer")

        def construct(**kwargs):
            rec.ctor.append(kwargs)
            return instance

        analyzer = MagicMock(name="Analyzer", side_effect=construct)

        def group(**kwargs):
            rec.record("run_group_analysis", kwargs)
            return SimpleNamespace(summary_csv_path=None, comparison_plot_path=None)

        def method(name):
            return lambda **kw: rec.record(name, kw)

        for name in ("analyze_sphere", "analyze_mask", "analyze_cortex"):
            setattr(instance, name, method(name))
        instance.analyze_subcortical = method("analyze_subcortical")
        return [
            patch("tit.analyzer.Analyzer", analyzer),
            # The runner's own mask check reads the NIfTI header (nibabel is mocked on the host).
            patch("tit.opt.masks.validate_mask", rec.prechecks.append),
            patch("tit.analyzer.run_group_analysis", group),
        ]
    if kind == "stats":
        return [
            patch(
                "tit.stats.permutation.run_group_comparison",
                stats_result("run_group_comparison"),
            ),
            patch(
                "tit.stats.permutation.run_correlation", stats_result("run_correlation")
            ),
        ]
    if kind == "nifti_average":

        def load(subject_configs, nifti_file_pattern=None, dtype=None):
            rec.record(
                "load_grouped_subjects_ti_toolbox",
                {"subjects": subject_configs, "pattern": nifti_file_pattern},
            )
            groups: dict[str, list[str]] = {}
            for s in subject_configs:
                groups.setdefault(s["group"], []).append(s["subject_id"])
            data = {g: np.zeros((2, 2, 2, len(ids))) for g, ids in groups.items()}
            return data, MagicMock(name="template"), groups

        return [patch("tit.stats.nifti_average.load_grouped_subjects_ti_toolbox", load)]
    if kind == "nilearn":

        def average(pairs):
            rec.record(
                "_average_fields", [(p.subject_id, p.simulation_name) for p in pairs]
            )
            img = MagicMock(name="averaged")
            img.get_fdata.return_value = np.linspace(0.0, 1.0, 27).reshape(3, 3, 3)
            return img

        return [
            patch("tit.plotting.nilearn.__main__._average_fields", average),
            patch(
                "tit.plotting.nilearn.__main__.create_pdf_entry_point_group",
                lambda *a, **k: "slices.pdf",
            ),
            patch(
                "tit.plotting.nilearn.__main__.create_glass_brain_entry_point_group",
                lambda *a, **k: "glass.pdf",
            ),
        ]
    if kind == "source":

        def target(name):
            def run(config):
                rec.record(name, config)
                return 0

            return run

        return [
            patch("tit.source.__main__._run_forward", target("_run_forward")),
            patch("tit.source.__main__._run_fsavg_map", target("_run_fsavg_map")),
        ]
    if kind == "pre":

        def run_pipeline(**kwargs):
            rec.record("run_pipeline", kwargs)
            return 0

        return [patch("tit.pre.__main__.run_pipeline", run_pipeline)]
    if kind == "blender":

        def target(name):
            def run(config, **_):
                rec.record(name, config)
                return None

            return run

        return [
            patch("tit.blender.montage_publication.run_montage", _montage_target(rec)),
            patch(
                "tit.blender.vector_field_exporter.run_vectors", target("run_vectors")
            ),
            patch("tit.blender.region_exporter.run_regions", target("run_regions")),
            patch(
                "tit.blender.subcortical_exporter.run_subcortical",
                target("run_subcortical"),
            ),
        ]
    raise AssertionError(f"no recorder for kind {kind!r}")


#: kind -> the targets one replay may reach, in the order the runner chooses between them.
EXPECTED_TARGET = {
    "sim": lambda c: "run_simulation",
    "flex": lambda c: "run_flex_search",
    "flex_adaptive": lambda c: "run_adaptive_focality",
    "flex_pareto": lambda c: "run_pareto_sweep",
    "ex": lambda c: "run_ex_search",
    "mex": lambda c: "run_m_ex_search",
    "stats": lambda c: (
        "run_correlation"
        if c.get("_type") == "CorrelationConfig"
        else "run_group_comparison"
    ),
    "nifti_average": lambda c: "load_grouped_subjects_ti_toolbox",
    "nilearn": lambda c: "_average_fields",
    "source": lambda c: (
        "_run_forward" if c.get("mode") == "forward" else "_run_fsavg_map"
    ),
    "pre": lambda c: "run_pipeline",
    "blender": lambda c: {
        "MontageConfig": "run_montage",
        "VectorConfig": "run_vectors",
        "RegionConfig": "run_regions",
        "SubcorticalConfig": "run_subcortical",
    }[c["_type"]],
}


# ---------------------------------------------------------------------------------------------
# One replay
# ---------------------------------------------------------------------------------------------
def _prepare_inputs(
    project: Path, kind: str, config: dict, subject_ids: list[str]
) -> None:
    """The files a runner precondition reads: each subject's head mesh and named EEG nets."""
    from tit.opt.flex.utils import eeg_net_csv_path
    from tit.paths import get_path_manager

    pm = get_path_manager(str(project))
    sids = set(subject_ids) | (
        {config["subject_id"]} if isinstance(config.get("subject_id"), str) else set()
    )
    if kind == "blender" and config.get("_type") == "MontageConfig":
        sim = config["simulation_name"]
        doc = Path(pm.simulation(config["subject_id"], sim), "documentation")
        doc.mkdir(parents=True, exist_ok=True)
        (doc / "config.json").write_text(json.dumps(_MONTAGE_SIMS[sim]))
    for sid in sids:
        os.makedirs(pm.m2m(sid), exist_ok=True)
        Path(pm.m2m(sid), f"{sid}.msh").touch()
        for net in (config.get("eeg_net"), config.get("skin_visualization_net")):
            if isinstance(net, str) and net:
                csv = eeg_net_csv_path(pm.eeg_positions(sid), net)
                csv.parent.mkdir(parents=True, exist_ok=True)
                csv.touch()


def replay(
    project: Path, kind: str, config: dict, subject_ids: list[str], monkeypatch
) -> tuple[Recorder, dict, Any]:
    """Submit, write the runner file, run ``main()`` with the science entry recorded."""
    _prepare_inputs(project, kind, config, subject_ids)
    manager = JobManager(str(project), budget=Cost(cpus=64, mem_gb=256))
    status = manager.submit(kind, config, subject_ids)
    spec = manager._specs[status["id"]]
    runner_file = manager._runner_config_path(spec)
    written = json.loads(Path(runner_file).read_text())

    rec = Recorder()
    events_file = project / "events.jsonl"
    monkeypatch.setenv("TIT_EVENTS_FILE", str(events_file))
    monkeypatch.setenv("TIT_JOB_ID", spec.id)
    import tit.jobs.events as events_mod
    import tit.logger as logger_mod

    logger_mod._event_sinks.clear()
    events_mod._reset_state()

    def hold(project_dir, job_id, requests, **_):
        rec.locks.append([r.key for r in requests])
        return nullcontext()

    module = __import__(RUNNER_MODULE[kind], fromlist=["main"])
    monkeypatch.setattr(sys, "argv", [RUNNER_MODULE[kind], runner_file])
    before_env = set(os.environ)
    patches = [patch("tit.jobs.locks.hold", hold), *_science_patches(kind, rec)]
    try:
        for p in patches:
            p.start()
        try:
            code = module.main()
        except SystemExit as exc:
            code = exc.code
    finally:
        for p in reversed(patches):
            p.stop()
        for key in set(os.environ) - before_env:
            if key.startswith("TISSUE_COND_"):
                del os.environ[key]
        logger_mod._event_sinks.clear()
        events_mod._reset_state()

    assert code in (0, None), f"{kind} runner exited {code}"
    assert written["project_dir"] == str(project)
    if kind in kinds.FLEX_KINDS:
        assert written["mode"] == kind
    assert rec.locks == [list(spec.locks)], "runner lock request != spec.locks"
    _validate_events(events_file)
    return rec, written, spec


def _validate_events(path: Path) -> None:
    import jsonschema

    lines = [json.loads(line) for line in path.read_text().splitlines() if line]
    assert lines, "the runner emitted no events"
    assert lines[-1]["type"] == "exit" and lines[-1].get("code", 0) == 0
    validator = jsonschema.Draft202012Validator(EVENTS_SCHEMA)
    for event in lines:
        validator.validate(event)


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value))


#: Normalisations a config dataclass documents, applied to the SUBMITTED value before comparing:
#: ``ExConfig``/``MExConfig.roi_name`` gain ".csv" (``tit/opt/config.py`` docstring example), and
#: a null ``NiftiAverageConfig.nifti_file_pattern`` becomes the space's default file (the
#: corpus ``expect`` checks which space's file that is).
def _csv(name: str) -> str:
    return name if name.endswith(".csv") else f"{name}.csv"


_NORMALISED = {
    ("ex", "roi_name"): _csv,
    ("mex", "roi_name"): _csv,
    ("ex", "roi_names"): lambda v: v and [_csv(n) for n in v],
    ("mex", "roi_names"): lambda v: v and [_csv(n) for n in v],
}
_FILLED_WHEN_NULL = {
    ("nifti_average", "nifti_file_pattern"),
    ("stats", "nifti_file_pattern"),
}


def _subset_equal(received: Any, submitted: Any, where: str) -> None:
    """*submitted* is found in *received*: the keys the client sent, list items in order."""
    if isinstance(submitted, dict):
        assert isinstance(received, dict), f"{where}: {received!r} is not an object"
        for key, value in submitted.items():
            assert (
                key in received
            ), f"{where}.{key} was dropped on the way to the runner"
            _subset_equal(received[key], value, f"{where}.{key}")
    elif isinstance(submitted, list):
        assert isinstance(received, list) and len(received) == len(
            submitted
        ), f"{where}: {received!r} != {submitted!r}"
        for i, (r, v) in enumerate(zip(received, submitted)):
            _subset_equal(r, v, f"{where}[{i}]")
    else:
        assert received == submitted, f"{where}: {received!r} != {submitted!r}"


def _assert_fields_match(
    kind: str, typed: Any, submitted: dict, skip: set[str]
) -> None:
    """Every submitted key reaches the runner's typed config with the submitted value."""
    received = _plain(serialize_config(typed))
    for key, value in _plain(submitted).items():
        if key in skip or (value is None and (kind, key) in _FILLED_WHEN_NULL):
            continue
        assert key in received, f"{key} was dropped on the way to the runner"
        value = _NORMALISED.get((kind, key), lambda v: v)(value)
        _subset_equal(received[key], value, key)


def _assert_dispatch(kind: str, config: dict, rec: Recorder) -> None:
    if kind == "analyzer":
        names = [name for name, _ in rec.calls]
        want = (
            "run_group_analysis"
            if config.get("mode") == "group"
            else {
                "spherical": "analyze_sphere",
                "cortical": "analyze_cortex",
                "subcortical": "analyze_subcortical",
                "mask": "analyze_mask",
            }[config["analysis_type"]]
        )
        assert names == [want]
        return
    assert [name for name, _ in rec.calls] == [EXPECTED_TARGET[kind](config)]
    name, typed = rec.calls[0]
    if kind in ("pre", "nilearn", "nifti_average"):
        return
    _assert_fields_match(kind, typed, config, skip={"_type", "project_dir", "mode"})


# ---------------------------------------------------------------------------------------------
# Recorded UI payloads
# ---------------------------------------------------------------------------------------------
def _payload_files() -> list[Path]:
    return sorted(PAYLOADS.glob("*.json"))


def test_every_ui_kind_has_a_recorded_payload() -> None:
    """A new job kind cannot skip the replay: each group kind and project-level kind has one."""
    recorded = {json.loads(p.read_text())["kind"] for p in _payload_files()}
    required = (set(GROUP_KINDS) - set(kinds.FLEX_KINDS) | {"flex"}) | {
        "analyzer",
        "stats",
        "nifti_average",
        "nilearn",
        "source",
    }
    assert (
        required <= recorded
    ), f"kinds with no recorded payload: {required - recorded}"


@pytest.mark.parametrize("path", _payload_files(), ids=lambda p: p.stem)
def test_recorded_payload_reaches_its_runner(path: Path, tmp_path, monkeypatch) -> None:
    # The recording ran against Dataset 000 mounted at /mnt/000; its paths move into tmp.
    body = json.loads(path.read_text().replace("/mnt/000", str(tmp_path)))
    kind, config = body["kind"], body["config"]
    subject_ids = body.get("subject_ids") or [config["subject_id"]]
    make_project(tmp_path, {"jobs": [body]})
    rec, written, _ = replay(tmp_path, kind, config, subject_ids, monkeypatch)
    _assert_dispatch(kind, config, rec)
    if kind == "pre":
        flags = rec.calls[0][1]
        for flag in (
            "convert_dicom",
            "create_m2m",
            "run_tissue_analysis",
            "run_qsiprep",
            "run_qsirecon",
            "extract_dti",
        ):
            assert flags[flag] == config[flag], flag
        assert flags["subject_ids"] == subject_ids
    if kind == "analyzer":
        call = rec.calls[0][1]
        if config["analysis_type"] == "spherical":
            assert tuple(call["center"]) == tuple(config["center"])
            assert call["radius"] == config["radius"]
        assert call["coordinate_space"] == config["coordinate_space"]
        assert call["visualize"] is True


# ---------------------------------------------------------------------------------------------
# Accepted desktop-config corpus cases
# ---------------------------------------------------------------------------------------------
def _accepted_corpus_cases() -> list:
    params = []
    gaps = {
        f"{p.parent.name}/{p.stem}" for p in _case_files()
    }  # every id, for the marks lookup below
    for path in _case_files():
        case = json.loads(path.read_text())
        case_id = f"{path.parent.name}/{path.stem}"
        if not case["desktop"]["accepts"] or known_gap_marks(case_id, "verdict"):
            continue  # refused cases never reach a runner; verdict gaps are their own test
        assert case_id in gaps
        params.append(
            pytest.param(path, id=case_id, marks=known_gap_marks(case_id, "dispatch"))
        )
    return params


def _check_expect(case: dict, recs: list[tuple[dict, Recorder]]) -> None:
    exp = case["expect"]
    page = case["page"]
    calls = [(name, payload) for _, rec in recs for name, payload in rec.calls]
    if page == "simulator":
        config = calls[0][1]
        assert list(config.intensities) == exp["intensities"]
        assert config.montages[0].mode.value == exp["montage_mode"]
        assert bool(config.carrier_only) is exp["carrier_only"]
        env = recs[0][1].env
        assert env == {
            f"TISSUE_COND_{k}": str(v) for k, v in exp["tissue_conductivities"].items()
        }
    elif page == "optimizer-flex":
        assert [c.mode.value for _, c in calls] == [exp["flex_mode"]]
        assert calls[0][1].goal.value == exp["goal"]
    elif page == "optimizer-ex":
        assert {name for name, _ in calls} == {exp["runner"]}
        assert [c.roi_name for _, c in calls] == [f"{n}.csv" for n in exp["roi_names"]]
    elif page == "analyzer":
        assert [name for name, _ in calls] == [exp["method"]] * exp["calls"]
        if "regions" in exp:
            got = [
                [kw["region"]] if isinstance(kw["region"], str) else list(kw["region"])
                for _, kw in calls
            ]
            assert got == exp["regions"]
        ctor = [kw for _, rec in recs for kw in rec.ctor]
        if "field" in exp:
            assert [kw["field"] for kw in ctor] == [exp["field"]] * exp["calls"]
        if "tissue_type" in exp:
            assert [kw["tissue_type"] for kw in ctor] == [exp["tissue_type"]] * exp[
                "calls"
            ]
        if "subjects" in exp:
            assert list(calls[0][1]["subject_ids"]) == exp["subjects"]
    elif page == "panels-stats":
        assert [name for name, _ in calls] == [exp["runner_call"]]
    elif page == "panels-nifti":
        loaded = calls[0][1]
        assert sorted({s["group"] for s in loaded["subjects"]}) == sorted(exp["groups"])
        # The space the user picked decides which file is averaged.
        token = "_TI_subject_" if exp["nifti_pattern_space"] == "subject" else "_MNI"
        assert loaded["pattern"] is not None and token in loaded["pattern"]
    elif page == "panels-nilearn":
        assert [list(p) for p in calls[0][1]] == exp["pairs"]
    elif page == "visual-exporter":
        assert [type(c).__name__ for _, c in calls] == exp["blender_types"]
    elif page == "preprocess":
        flags = calls[0][1]
        tags = {
            "convert_dicom": "G1",
            "create_m2m": "G2a",
            "run_fastsurfer": "G2b",
            "run_freesurfer": "G2c",
            "run_tissue_analysis": "G3",
            "run_qsiprep": "G4",
            "run_qsirecon": "G5",
            "extract_dti": "G6",
        }
        assert [t for f, t in tags.items() if flags[f]] == exp["stages_per_subject"]
        assert flags["skip_existing_outputs"] is exp["skip_existing_outputs"]
    else:  # pragma: no cover - a new page needs its expectation written here
        raise AssertionError(f"no expectation reader for page {page!r}")


@pytest.mark.parametrize("path", _accepted_corpus_cases())
def test_accepted_corpus_case_reaches_its_runner_as_the_user_chose(
    path: Path, tmp_path, monkeypatch
) -> None:
    case = load_case(path, tmp_path)
    make_project(tmp_path, case)
    recs = []
    for job in case["jobs"]:
        rec, _, _ = replay(
            tmp_path, job["kind"], job["config"], job["subject_ids"], monkeypatch
        )
        _assert_dispatch(job["kind"], job["config"], rec)
        recs.append((job, rec))
    _check_expect(case, recs)


def test_every_page_with_a_runner_is_replayed() -> None:
    replayed = {p.id.split("/")[0] for p in _accepted_corpus_cases()}
    assert replayed == set(PAGES)
