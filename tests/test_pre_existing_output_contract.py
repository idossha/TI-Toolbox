"""One contract for every pre-processing stage: runner guard, skip/replace policy and plan agree.

What this pins (2026-10-22): four places decide whether a stage's output "exists" -- the
runner's own refusal, ``tit.pre.preflight.existing_outputs_for_step`` (which drives skip and
replace), and ``POST /api/plan/pre``'s ``exists`` (which drives the desktop's skip / overwrite
chips). For every stage and four disk states (absent, empty, partial = a cancelled run,
complete) they must agree:

1. whenever the runner's guard refuses ("already exists"), preflight reports an output, so
   "replace" can always clear the way;
2. after ``remove_preprocessing_output`` the guard no longer refuses;
3. the plan's ``exists`` equals ``bool(existing_outputs_for_step(...))``;
4. under "skip" the stage is skipped only over a finished output, runs when there is none,
   and stops with an "incomplete ... replace" sentence over a partial one -- never deleting.
   (DICOM conversion skips per modality, so its runner always gets the call.)

Where the expectations come from, independently of the code under test:
``GUARD_REFUSES`` restates each runner's documented refusal (``run_charm``: a non-empty
``m2m_<id>``; ``run_qsiprep``: a non-empty ``qsiprep/sub-<id>``; ``run_qsirecon``: a non-empty
``qsirecon-*/sub-<id>``; ``extract_dti_tensor``: the tensor file; DICOM: a BIDS NIfTI for a
modality with source files; FastSurfer and tissue analysis never refuse) and ``SKIP`` restates
the skip semantics in docs/wiki/pre-processing.md "Run and monitor" with the completion markers
in ``tests/test_pre_incomplete_outputs.py``. Each runner is called for real with only what
happens after its guard replaced by a sentinel, so the test sees the guard itself.

Known gaps, deliberately not covered by "partial": FreeSurfer recon-all and QSIRecon have no
completion marker (any non-empty reconstruction counts as done), and a DTI tensor that is
truncated but not empty is not detected (only a zero-byte one is).

Reproduce: ``pytest tests/test_pre_existing_output_contract.py -q``.
"""

from __future__ import annotations

import importlib
import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.paths import get_path_manager
from tit.pre.preflight import existing_outputs_for_step, remove_preprocessing_output
from tit.pre.utils import CommandRunner, PreprocessError

SID = "001"
STATES = ("absent", "empty", "partial", "complete")
LOGGER = logging.getLogger("tests.p17.contract")


class _PastGuard(Exception):
    """Raised by the first call a runner makes after its existing-output guard."""


# --------------------------------------------------------------------------- disk states


def _base(project: Path) -> None:
    (project / "dataset_description.json").write_text("{}")
    anat = project / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)


def _m2m(project: Path) -> Path:
    return project / "derivatives" / "SimNIBS" / f"sub-{SID}" / f"m2m_{SID}"


def _touch(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _build(step: str, state: str, project: Path) -> None:
    """Lay out *state* of *step*'s output (plus the inputs its runner checks first)."""
    anat = project / f"sub-{SID}" / "anat"
    if step == "dicom":
        _touch(project / "sourcedata" / f"sub-{SID}" / "T1w" / "dicom" / "IM1.dcm")
        if state == "partial":  # a sidecar left behind, no image
            _touch(anat / f"sub-{SID}_T1w.json", b"{}")
        elif state == "complete":
            _touch(anat / f"sub-{SID}_T1w.nii.gz")
            _touch(anat / f"sub-{SID}_T1w.json", b"{}")
        return
    _touch(anat / f"sub-{SID}_T1w.nii.gz")
    if step == "charm":
        m2m = _m2m(project)
        if state != "absent":
            m2m.mkdir(parents=True)
        if state in ("partial", "complete"):
            _touch(m2m / "charm_log.html")
        if state == "complete":
            _touch(m2m / f"{SID}.msh")
            _touch(m2m / "final_tissues.nii.gz")
    elif step == "fastsurfer":
        subject = project / "derivatives" / "fastsurfer" / f"sub-{SID}"
        if state != "absent":
            subject.mkdir(parents=True)
        if state in ("partial", "complete"):
            _touch(subject / "mri" / "orig.mgz")
            _touch(subject / "scripts" / "deep-seg.log", b"Run coronal prediction\n")
        if state == "complete":
            _touch(subject / "mri" / "aparc.DKTatlas+aseg.deep.mgz")
    elif step == "tissue":
        _touch(_m2m(project) / "segmentation" / "labeling.nii.gz")
        out = project / "derivatives" / "ti-toolbox" / "tissue_analysis" / f"sub-{SID}"
        if state != "absent":
            out.mkdir(parents=True)
        tissues = {"partial": ("bone",), "complete": ("bone", "csf", "skin")}
        for tissue in tissues.get(state, ()):
            _touch(out / f"{tissue}_analysis" / f"{tissue}_analysis.txt")
    elif step == "qsiprep":
        subject = project / "derivatives" / "qsiprep" / f"sub-{SID}"
        if state != "absent":
            subject.mkdir(parents=True)
        if state in ("partial", "complete"):
            _touch(subject / "log" / "crash.toml")
        if state == "complete":
            _touch(subject / "dwi" / f"sub-{SID}_space-ACPC_desc-preproc_dwi.nii.gz")
    elif step == "qsirecon":
        root = project / "derivatives" / "qsirecon"
        recon = root / "derivatives" / "qsirecon-DSIStudio" / f"sub-{SID}"
        if state == "empty":
            recon.mkdir(parents=True)
        elif state == "partial":  # crashed before reconstructing: logs only
            _touch(root / f"sub-{SID}" / "log" / "crash.txt")
        elif state == "complete":
            _touch(recon / "dwi" / f"sub-{SID}_space-ACPC_model-gqi_dwimap.nii.gz")
    elif step == "dti":
        m2m = _m2m(project)
        _touch(m2m / "T1.nii.gz")
        _touch(m2m / "final_tissues.nii.gz")
        if state == "empty":
            _touch(m2m / "DTI_coregT1_tensor.nii.gz", b"")  # zero-byte tensor
        elif (
            state == "partial"
        ):  # failed QC gate: the record is written, the tensor is not
            _touch(m2m / "DTI_coregT1_qc.json", b"{}")
        elif state == "complete":
            _touch(m2m / "DTI_coregT1_tensor.nii.gz")
            _touch(m2m / "DTI_coregT1_qc.json", b"{}")
    else:  # pragma: no cover - table and builder out of step
        raise AssertionError(step)


# --------------------------------------------------------------------------- the runners


def _runner() -> MagicMock:
    runner = MagicMock(spec=CommandRunner)
    runner.stop_event = None
    runner.run.return_value = 0
    return runner


def _call_runner(step: str, project: Path) -> str:
    """Call *step*'s real runner; return 'refused', 'past_guard' or 'returned'."""
    p = str(project)
    calls = {
        "dicom": (
            "tit.pre.dicom2nifti.run_dicom_to_nifti",
            [("tit.pre.dicom2nifti._run_dcm2niix", {"side_effect": _PastGuard})],
            lambda f: f(p, SID, logger=LOGGER, runner=_runner()),
        ),
        "charm": (
            "tit.pre.charm.run_charm",
            [("tit.pre.charm._get_form_flag", {"side_effect": _PastGuard})],
            lambda f: f(p, SID, logger=LOGGER, runner=_runner()),
        ),
        "fastsurfer": (
            "tit.pre.fastsurfer.run_fastsurfer",
            [
                ("tit.pre.fastsurfer._find_anat_files", {"side_effect": _PastGuard}),
                ("tit.pre.fastsurfer.write_derived_outputs", {}),
            ],
            lambda f: f(p, SID, logger=LOGGER, runner=_runner()),
        ),
        "tissue": (
            "tit.pre.tissue_analyzer.run_tissue_analysis",
            [("tit.pre.tissue_analyzer.TissueAnalyzer", {"side_effect": _PastGuard})],
            lambda f: f(p, SID, logger=LOGGER),
        ),
        "qsiprep": (
            "tit.pre.qsi.qsiprep.run_qsiprep",
            [
                (
                    "tit.pre.qsi.qsiprep.validate_dood_environment",
                    {"return_value": (True, None)},
                ),
                (
                    "tit.pre.qsi.qsiprep.validate_bids_dwi",
                    {"return_value": (True, None)},
                ),
                (
                    "tit.pre.qsi.qsiprep.ensure_total_readout_time",
                    {"return_value": (True, None)},
                ),
                (
                    "tit.pre.qsi.qsiprep.plan_distortion_correction",
                    {"side_effect": _PastGuard},
                ),
            ],
            lambda f: f(p, SID, logger=LOGGER, runner=_runner()),
        ),
        "qsirecon": (
            "tit.pre.qsi.qsirecon.run_qsirecon",
            [
                (
                    "tit.pre.qsi.qsirecon.validate_dood_environment",
                    {"return_value": (True, None)},
                ),
                (
                    "tit.pre.qsi.qsirecon.validate_qsiprep_output",
                    {"return_value": (True, None)},
                ),
                ("tit.pre.qsi.qsirecon.QSIReconConfig", {"side_effect": _PastGuard}),
            ],
            lambda f: f(p, SID, logger=LOGGER, runner=_runner()),
        ),
        "dti": (
            "tit.pre.qsi.dti_extractor.extract_dti_tensor",
            [("tit.pre.qsi.dti_extractor._find_nifti", {"side_effect": _PastGuard})],
            lambda f: f(p, SID, logger=LOGGER),
        ),
    }
    target, patches, invoke = calls[step]
    module_name, func_name = target.rsplit(".", 1)
    module = importlib.import_module(module_name)
    with ExitStack() as stack:
        for name, kwargs in patches:
            stack.enter_context(patch(name, **kwargs))
        try:
            invoke(getattr(module, func_name))
        except _PastGuard:
            return "past_guard"
        except PreprocessError as exc:
            if "already exists" in str(exc):
                return "refused"
            raise
    return "returned"


# --------------------------------------------------------------------------- expectations

STEPS = ("dicom", "charm", "fastsurfer", "tissue", "qsiprep", "qsirecon", "dti")

#: (step, state) pairs whose runner refuses with "already exists" -- from each runner's guard.
GUARD_REFUSES = {
    ("dicom", "complete"),
    ("charm", "partial"),
    ("charm", "complete"),
    ("qsiprep", "partial"),
    ("qsiprep", "complete"),
    ("qsirecon", "complete"),
    ("dti", "empty"),
    ("dti", "complete"),
}

#: What the runner does when its guard does not refuse: FastSurfer returns early over its own
#: finished segmentation (idempotent); every other runner proceeds to the work.
GUARD_RETURNS = {("fastsurfer", "complete")}

#: Under "skip": run, skip (finished output kept) or refuse (partial output, choose replace).
SKIP = {
    **{(step, "absent"): "run" for step in STEPS},
    **{(step, "empty"): "run" for step in STEPS},
    ("dicom", "partial"): "run",
    (
        "dicom",
        "complete",
    ): "run",  # per modality: the runner skips the converted T1w itself
    ("charm", "partial"): "refuse",
    ("charm", "complete"): "skip",
    ("fastsurfer", "partial"): "refuse",
    ("fastsurfer", "complete"): "skip",
    ("tissue", "partial"): "refuse",
    ("tissue", "complete"): "skip",
    ("qsiprep", "partial"): "refuse",
    ("qsiprep", "complete"): "skip",
    ("qsirecon", "partial"): "run",  # logs only: no reconstruction exists
    ("qsirecon", "complete"): "skip",
    (
        "dti",
        "empty",
    ): "refuse",  # a zero-byte tensor: its copy into place never finished
    ("dti", "partial"): "run",  # a failed QC run left no tensor
    ("dti", "complete"): "skip",
}

#: run_pipeline flag, structural's name for the runner, plan stage tag.
WIRING = {
    "dicom": ("convert_dicom", "run_dicom_to_nifti", "G1"),
    "charm": ("create_m2m", "run_charm", "G2a"),
    "fastsurfer": ("run_fastsurfer", "run_fastsurfer", "G2b"),
    "tissue": ("run_tissue_analysis", "run_tissue_analysis", "G3"),
    "qsiprep": ("run_qsiprep", "run_qsiprep", "G4"),
    "qsirecon": ("run_qsirecon", "run_qsirecon", "G5"),
    "dti": ("extract_dti", "extract_dti_tensor", "G6"),
}

CASES = [(step, state) for step in STEPS for state in STATES]


def test_the_matrix_has_cases_to_check():
    assert len(CASES) == 28
    assert set(SKIP) == set(CASES)
    assert GUARD_REFUSES <= set(CASES)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    _base(tmp_path)
    return tmp_path


def _preflight_step(step: str) -> str:
    from tit.pre import preflight

    return {
        "dicom": preflight.STEP_DICOM,
        "charm": preflight.STEP_CHARM,
        "fastsurfer": preflight.STEP_FASTSURFER,
        "tissue": preflight.STEP_TISSUE,
        "qsiprep": preflight.STEP_QSIPREP,
        "qsirecon": preflight.STEP_QSIRECON,
        "dti": preflight.STEP_DTI,
    }[step]


# --------------------------------------------------------------------------- properties 1, 2


@pytest.mark.parametrize("step,state", CASES)
def test_runner_guard_and_replace_agree(project, step, state):
    _build(step, state, project)

    outcome = _call_runner(step, project)
    expected = (
        "refused"
        if (step, state) in GUARD_REFUSES
        else "returned" if (step, state) in GUARD_RETURNS else "past_guard"
    )
    assert outcome == expected

    outputs = existing_outputs_for_step(str(project), SID, _preflight_step(step))
    if outcome == "refused":
        assert outputs, "the runner refuses, so replace must have something to remove"
    for output in outputs:
        remove_preprocessing_output(output)
    assert _call_runner(step, project) != "refused"


# --------------------------------------------------------------------------- property 3


@pytest.fixture
def client(project: Path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    for mod in ("scipy.ndimage", "scipy.stats"):
        sys.modules.setdefault(mod, MagicMock())
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    settings = ServerSettings(project_dir=str(project), token="t")
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize("policy", ["skip", "replace"])
@pytest.mark.parametrize("step,state", CASES)
def test_plan_exists_is_the_preflight_answer(project, client, step, state, policy):
    _build(step, state, project)
    flag, _runner_name, tag = WIRING[step]

    resp = client.post(
        "/api/plan/pre",
        json={
            "config": {
                "subject_ids": [SID],
                flag: True,
                f"{policy}_existing_outputs": True,
            },
            "subject_ids": [SID],
        },
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [index] = [
        i for i, stage in enumerate(body["resolved"]["stages"]) if tag in stage["tags"]
    ]
    job = body["jobs"][index]

    exists = bool(existing_outputs_for_step(str(project), SID, _preflight_step(step)))
    assert job["exists"] is exists
    assert job["will_overwrite"] is (exists and policy == "replace")
    blocked = [w for w in body["warnings"] if tag in w and SID in w]
    refuses = policy == "skip" and SKIP[(step, state)] == "refuse"
    assert bool(blocked) is refuses


# --------------------------------------------------------------------------- property 4


@pytest.mark.parametrize("step,state", CASES)
def test_skip_policy_runs_skips_or_refuses(project, step, state):
    from tit.pre.structural import run_pipeline

    _build(step, state, project)
    flag, runner_name, _tag = WIRING[step]
    before = sorted(str(p) for p in project.rglob("*") if p.is_file())

    with ExitStack() as stack:
        stack.enter_context(patch("tit.pre.structural._install_sigterm_handler"))
        stack.enter_context(
            patch("tit.pre.structural.build_logger", return_value=LOGGER)
        )
        # Input checks are the subject of tests/test_pre_preflight.py, not this contract.
        stack.enter_context(
            patch(
                "tit.pre.structural.find_missing_preprocessing_inputs", return_value=[]
            )
        )
        stage_runner = stack.enter_context(patch(f"tit.pre.structural.{runner_name}"))
        stack.enter_context(patch("tit.pre.structural.run_subject_atlas"))
        expected = SKIP[(step, state)]
        if expected == "refuse":
            with pytest.raises(PreprocessError) as excinfo:
                run_pipeline(
                    [SID], skip_existing_outputs=True, runner=_runner(), **{flag: True}
                )
            assert "incomplete" in str(excinfo.value)
            assert "replace" in str(excinfo.value)
        else:
            run_pipeline(
                [SID], skip_existing_outputs=True, runner=_runner(), **{flag: True}
            )

    assert stage_runner.called is (expected == "run")
    after = sorted(str(p) for p in project.rglob("*") if p.is_file())
    assert set(before) <= set(after), "skip never deletes"
