"""An interrupted FastSurfer, charm or QSIPrep run never counts as done (2026-10-22).

What this pins: "skip existing outputs" skips only an output the producer finished, and an
empty head-model folder neither blocks charm nor needs the user to delete it.

- FastSurfer is done when ``mri/aparc.DKTatlas+aseg.deep.mgz`` exists: the runner's own
  success check (``tit/pre/fastsurfer.py``: "FastSurfer reported success but <seg> was not
  written") and its idempotent early return both key on that file.
- charm is done when ``m2m_<id>/<id>.msh`` and ``final_tissues.nii.gz`` exist: SimNIBS 4
  charm writes the segmentation and then the mesh as its last science step; every head model
  in Dataset 000 (101, CHN, LA, ernie, MNI152) has both.
- QSIPrep is done when ``validate_qsiprep_output`` accepts it (a preprocessed
  ``dwi/*_dwi.nii*``), the check QSIRecon and DTI extraction apply to their input.

The partial FastSurfer layout copies Dataset 000 ``derivatives/fastsurfer/sub-101`` as
empty stand-ins: ``mri/orig.mgz``, ``mri/orig/001.mgz`` and ``scripts/deep-seg.log`` ending at
"Run coronal prediction" (the real run was interrupted there). Under "skip" an incomplete
output stops the stage with a sentence telling the user to choose replace; skip never deletes.

Reproduce: ``pytest tests/test_pre_incomplete_outputs.py -q``; the real-data checks with
``TIT_DATASET_000=/path/to/000``.

Deliberately elsewhere: the catalog's ``has_fastsurfer``/``has_m2m`` flags (package p24 calls
:func:`tit.pre.preflight.step_output_complete`); the step x state matrix is
``tests/test_pre_existing_output_contract.py``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.paths import get_path_manager
from tit.pre.utils import CommandRunner, PreprocessError

SID = "001"
SEG = "aparc.DKTatlas+aseg.deep.mgz"


def _project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    anat = tmp_path / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)
    (anat / f"sub-{SID}_T1w.nii.gz").write_bytes(b"t1")
    return tmp_path


def _interrupted_fastsurfer(project: Path) -> Path:
    subject = project / "derivatives" / "fastsurfer" / f"sub-{SID}"
    (subject / "mri" / "orig").mkdir(parents=True)
    (subject / "scripts").mkdir()
    (subject / "mri" / "orig.mgz").write_bytes(b"")
    (subject / "mri" / "orig" / "001.mgz").write_bytes(b"")
    (subject / "scripts" / "deep-seg.log").write_text(
        "[INFO: run_prediction.py:  385]: Run coronal prediction\n"
    )
    return subject


def _m2m(project: Path) -> Path:
    return project / "derivatives" / "SimNIBS" / f"sub-{SID}" / f"m2m_{SID}"


def _runner() -> MagicMock:
    runner = MagicMock(spec=CommandRunner)
    runner.stop_event = None
    runner.run.return_value = 0
    return runner


@pytest.fixture
def quiet_pipeline():
    with (
        patch("tit.pre.structural._install_sigterm_handler"),
        patch(
            "tit.pre.structural.build_logger",
            return_value=logging.getLogger("tests.p17.incomplete"),
        ),
    ):
        yield


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# --------------------------------------------------------------------------- FastSurfer


def test_interrupted_fastsurfer_exists_but_is_not_complete(tmp_path):
    from tit.pre.preflight import (
        STEP_FASTSURFER,
        existing_outputs_for_step,
        step_output_complete,
    )

    project = _project(tmp_path)
    subject = _interrupted_fastsurfer(project)

    [output] = existing_outputs_for_step(str(project), SID, STEP_FASTSURFER)
    assert output.path == subject  # replace still removes the leftovers
    assert step_output_complete(str(project), SID, STEP_FASTSURFER) is False

    (subject / "mri" / SEG).write_bytes(b"seg")
    assert step_output_complete(str(project), SID, STEP_FASTSURFER) is True


def test_skip_refuses_an_interrupted_fastsurfer_and_keeps_it(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    subject = _interrupted_fastsurfer(project)
    before = _files(subject)

    with (
        patch("tit.pre.structural.run_fastsurfer") as run_fastsurfer,
        pytest.raises(PreprocessError) as excinfo,
    ):
        run_pipeline(
            [SID], run_fastsurfer=True, skip_existing_outputs=True, runner=_runner()
        )

    message = str(excinfo.value)
    assert "incomplete" in message and "replace" in message
    assert SEG in message  # names what is missing
    run_fastsurfer.assert_not_called()
    assert _files(subject) == before


def test_skip_keeps_a_finished_fastsurfer(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    subject = _interrupted_fastsurfer(project)
    (subject / "mri" / SEG).write_bytes(b"seg")

    with patch("tit.pre.structural.run_fastsurfer") as run_fastsurfer:
        assert (
            run_pipeline(
                [SID],
                run_fastsurfer=True,
                skip_existing_outputs=True,
                runner=_runner(),
            )
            == 0
        )

    run_fastsurfer.assert_not_called()


def test_replace_reruns_an_interrupted_fastsurfer(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    subject = _interrupted_fastsurfer(project)

    with patch("tit.pre.structural.run_fastsurfer") as run_fastsurfer:
        run_pipeline(
            [SID],
            run_fastsurfer=True,
            replace_existing_outputs=True,
            runner=_runner(),
        )

    run_fastsurfer.assert_called_once()
    assert not subject.exists()


# --------------------------------------------------------------------------- charm


def test_skip_refuses_a_cancelled_charm(tmp_path, quiet_pipeline):
    from tit.pre.preflight import STEP_CHARM, step_output_complete
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    m2m = _m2m(project)
    m2m.mkdir(parents=True)
    (m2m / "charm_log.html").write_text("<html>cancelled</html>")

    assert step_output_complete(str(project), SID, STEP_CHARM) is False
    with (
        patch("tit.pre.structural.run_charm") as run_charm,
        patch("tit.pre.structural.run_subject_atlas") as run_atlas,
        pytest.raises(PreprocessError, match="incomplete"),
    ):
        run_pipeline(
            [SID], create_m2m=True, skip_existing_outputs=True, runner=_runner()
        )

    run_charm.assert_not_called()
    run_atlas.assert_not_called()
    assert (m2m / "charm_log.html").is_file()


@pytest.mark.parametrize("missing", [f"{SID}.msh", "final_tissues.nii.gz"])
def test_charm_needs_both_the_mesh_and_the_final_segmentation(tmp_path, missing):
    from tit.pre.preflight import STEP_CHARM, step_output_complete

    project = _project(tmp_path)
    m2m = _m2m(project)
    m2m.mkdir(parents=True)
    for name in {f"{SID}.msh", "final_tissues.nii.gz"} - {missing}:
        (m2m / name).write_bytes(b"x")

    assert step_output_complete(str(project), SID, STEP_CHARM) is False
    (m2m / missing).write_bytes(b"x")
    assert step_output_complete(str(project), SID, STEP_CHARM) is True


def test_skip_keeps_a_finished_head_model(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    m2m = _m2m(project)
    m2m.mkdir(parents=True)
    (m2m / f"{SID}.msh").write_bytes(b"mesh")
    (m2m / "final_tissues.nii.gz").write_bytes(b"labels")

    with patch("tit.pre.structural.run_charm") as run_charm:
        run_pipeline(
            [SID], create_m2m=True, skip_existing_outputs=True, runner=_runner()
        )

    run_charm.assert_not_called()


@pytest.mark.parametrize(
    "policy",
    [{"skip_existing_outputs": True}, {"replace_existing_outputs": True}, {}],
    ids=["skip", "replace", "no-policy"],
)
def test_an_empty_m2m_folder_does_not_block_charm(tmp_path, quiet_pipeline, policy):
    """The real run_charm gets past its guard and launches charm whatever the policy."""
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    m2m = _m2m(project)
    m2m.mkdir(parents=True)
    runner = _runner()
    m2m_present_when_charm_ran = []
    runner.run.side_effect = lambda cmd, **_kw: (
        m2m_present_when_charm_ran.append(m2m.exists()) or 0
    )

    with (
        patch("tit.pre.charm._get_form_flag", return_value="--forcesform"),
        patch("tit.pre.charm._write_thread_settings"),
        patch("tit.pre.charm.copy_charm_report"),
        patch("tit.pre.structural.run_subject_atlas"),
    ):
        run_pipeline([SID], create_m2m=True, runner=runner, **policy)

    commands = [call.args[0] for call in runner.run.call_args_list]
    assert [cmd[:3] for cmd in commands] == [["charm", "--forcesform", SID]]
    # charm creates m2m_<id> itself; the empty leftover is gone before it starts.
    assert m2m_present_when_charm_ran == [False]


# --------------------------------------------------------------------------- QSIPrep


def test_qsiprep_without_a_preprocessed_dwi_is_not_complete(tmp_path, quiet_pipeline):
    from tit.pre.preflight import STEP_QSIPREP, step_output_complete
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    subject = project / "derivatives" / "qsiprep" / f"sub-{SID}"
    (subject / "log").mkdir(parents=True)
    (subject / "log" / "crash.toml").write_text("killed")

    assert step_output_complete(str(project), SID, STEP_QSIPREP) is False
    with (
        patch("tit.pre.structural.find_missing_preprocessing_inputs", return_value=[]),
        patch("tit.pre.structural.run_qsiprep") as run_qsiprep,
        pytest.raises(PreprocessError, match="incomplete"),
    ):
        run_pipeline(
            [SID], run_qsiprep=True, skip_existing_outputs=True, runner=_runner()
        )
    run_qsiprep.assert_not_called()

    (subject / "dwi").mkdir()
    (subject / "dwi" / f"sub-{SID}_space-ACPC_desc-preproc_dwi.nii.gz").write_bytes(
        b"d"
    )
    assert step_output_complete(str(project), SID, STEP_QSIPREP) is True


def test_step_output_complete_is_false_when_nothing_exists(tmp_path):
    from tit.pre.preflight import (
        STEP_CHARM,
        STEP_FASTSURFER,
        STEP_QSIPREP,
        step_output_complete,
    )

    project = _project(tmp_path)
    for step in (STEP_CHARM, STEP_FASTSURFER, STEP_QSIPREP):
        assert step_output_complete(str(project), SID, step) is False


# --------------------------------------------------------------------------- plan


@pytest.fixture
def plan_client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    for mod in ("scipy.ndimage", "scipy.stats"):
        sys.modules.setdefault(mod, MagicMock())
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    project = _project(tmp_path)
    settings = ServerSettings(project_dir=str(project), token="t")
    return project, TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _plan(client, **config) -> dict:
    resp = client.post(
        "/api/plan/pre",
        json={"config": {"subject_ids": [SID], **config}, "subject_ids": [SID]},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_plan_blocks_skip_over_an_interrupted_fastsurfer(plan_client):
    """The desktop marks a cell 'blocked' when a warning names its subject and stage id."""
    project, client = plan_client
    _interrupted_fastsurfer(project)

    skip = _plan(client, run_fastsurfer=True, skip_existing_outputs=True)
    [job] = skip["jobs"]
    assert job["exists"] is True and job["will_overwrite"] is False
    [warning] = [w for w in skip["warnings"] if "G2b" in w]
    assert SID in warning and "incomplete" in warning and "replace" in warning

    replace = _plan(client, run_fastsurfer=True, replace_existing_outputs=True)
    assert replace["jobs"][0]["will_overwrite"] is True
    assert not [w for w in replace["warnings"] if "G2b" in w]


def test_plan_does_not_warn_over_a_finished_fastsurfer(plan_client):
    project, client = plan_client
    subject = _interrupted_fastsurfer(project)
    (subject / "mri" / SEG).write_bytes(b"seg")

    body = _plan(client, run_fastsurfer=True, skip_existing_outputs=True)

    assert body["jobs"][0]["exists"] is True
    assert not [w for w in body["warnings"] if "G2b" in w]


# --------------------------------------------------------------------------- Dataset 000

_DATASET = os.environ.get("TIT_DATASET_000", "")
_HAVE_DATASET = bool(_DATASET) and Path(_DATASET, "derivatives").is_dir()


def _mtimes(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in sorted(root.rglob("*"))}


@pytest.mark.skipif(
    not _HAVE_DATASET,
    reason="skipping: TIT_DATASET_000 unset or not a Dataset 000 copy",
)
def test_dataset_000_interrupted_fastsurfer_is_not_done_read_only():
    from tit.pre.preflight import STEP_FASTSURFER, step_output_complete

    root = Path(_DATASET)
    fastsurfer = root / "derivatives" / "fastsurfer"
    interrupted = fastsurfer / "sub-101"
    log = interrupted / "scripts" / "deep-seg.log"
    if (
        not log.is_file()
        or "Run coronal prediction" not in log.read_text()
        or (interrupted / "mri" / SEG).exists()
    ):
        pytest.skip(
            "skipping: Dataset 000 sub-101 FastSurfer is no longer the interrupted run"
        )
    before = _mtimes(fastsurfer)

    get_path_manager(str(root))
    assert step_output_complete(str(root), "101", STEP_FASTSURFER) is False
    assert (
        step_output_complete(str(root), "ernie", STEP_FASTSURFER)
        is (fastsurfer / "sub-ernie" / "mri" / SEG).is_file()
    )
    assert _mtimes(fastsurfer) == before


@pytest.mark.skipif(
    not _HAVE_DATASET,
    reason="skipping: TIT_DATASET_000 unset or not a Dataset 000 copy",
)
def test_dataset_000_finished_head_models_count_as_done_read_only():
    from tit.pre.preflight import STEP_CHARM, step_output_complete

    root = Path(_DATASET)
    simnibs = root / "derivatives" / "SimNIBS"
    subjects = sorted(
        p.name[len("sub-") :]
        for p in simnibs.glob("sub-*")
        if (p / f"m2m_{p.name[len('sub-'):]}").is_dir()
    )
    assert subjects, "has head models to check"
    m2m_dirs = {sid: simnibs / f"sub-{sid}" / f"m2m_{sid}" for sid in subjects}
    before = {sid: _mtimes(m2m) for sid, m2m in m2m_dirs.items()}

    get_path_manager(str(root))
    for sid, m2m in m2m_dirs.items():
        # Independent reading of the same rule: both charm products on disk.
        finished = (m2m / f"{sid}.msh").is_file() and (
            m2m / "final_tissues.nii.gz"
        ).is_file()
        assert (
            finished
        ), f"Dataset 000 m2m_{sid} is expected to be a finished head model"
        assert step_output_complete(str(root), sid, STEP_CHARM) is True
    assert {sid: _mtimes(m2m) for sid, m2m in m2m_dirs.items()} == before
