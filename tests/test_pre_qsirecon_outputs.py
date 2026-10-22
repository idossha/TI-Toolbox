"""QSIRecon's existing output is found where QSIRecon 26 writes it (2026-10-22).

What this pins: the skip/replace policy and the plan's ``exists`` flag look at the same
directory the runner's own guard refuses on. QSIRecon 26 writes each reconstruction to
``derivatives/qsirecon/derivatives/qsirecon-<suffix>/sub-<id>/`` and keeps
``derivatives/qsirecon/sub-<id>/`` for logs (documented in ``tit/pre/qsi/qsirecon.py``;
Dataset 000 sub-CHN has exactly ``derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-CHN``
and no ``derivatives/qsirecon/sub-CHN``). Before this fix the policy looked at
``derivatives/qsirecon/sub-<id>``, so "skip" ran the stage and "replace" removed nothing; both
ended in the runner's "QSIRecon output already exists ... Remove those directories manually".

Where the expectations come from: the runner's own guard (``run_qsirecon`` refusing on a
non-empty ``qsirecon-*/sub-<id>``) is the spec; every expected path is built from that layout,
not read back from the code under test. The real-data case reads Dataset 000 read-only.

Reproduce: ``pytest tests/test_pre_qsirecon_outputs.py -q``; real data with
``TIT_DATASET_000=/path/to/000``.

Deliberately elsewhere: the full step x disk-state matrix is
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
from tit.pre.preflight import STEP_QSIRECON, existing_outputs_for_step
from tit.pre.utils import CommandRunner, PreprocessError

SID = "001"


def _project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    # A valid QSIPrep output, so QSIRecon's own input check passes.
    dwi = tmp_path / "derivatives" / "qsiprep" / f"sub-{SID}" / "dwi"
    dwi.mkdir(parents=True)
    (dwi / f"sub-{SID}_space-ACPC_desc-preproc_dwi.nii.gz").write_bytes(b"dwi")
    return tmp_path


def _reconstruction(project: Path, suffix: str = "DSIStudio") -> Path:
    """The directory QSIRecon 26 writes one reconstruction to, holding one file."""
    recon = (
        project
        / "derivatives"
        / "qsirecon"
        / "derivatives"
        / f"qsirecon-{suffix}"
        / f"sub-{SID}"
    )
    (recon / "dwi").mkdir(parents=True)
    (recon / "dwi" / f"sub-{SID}_space-ACPC_model-gqi_dwimap.nii.gz").write_bytes(b"x")
    return recon


def _runner() -> MagicMock:
    runner = MagicMock(spec=CommandRunner)
    runner.stop_event = None
    runner.run.return_value = 0
    return runner


@pytest.fixture
def quiet_pipeline():
    """run_pipeline without a SIGTERM handler in the test process or a per-subject log file."""
    with (
        patch("tit.pre.structural._install_sigterm_handler"),
        patch(
            "tit.pre.structural.build_logger",
            return_value=logging.getLogger("tests.p17.qsirecon"),
        ),
    ):
        yield


def test_preflight_finds_the_reconstruction_the_runner_guards(tmp_path):
    project = _project(tmp_path)
    recon = _reconstruction(project)

    outputs = existing_outputs_for_step(str(project), SID, STEP_QSIRECON)

    assert outputs, "the runner refuses on this directory, so preflight must report it"
    removed = {p for output in outputs for p in output.paths_to_remove}
    assert recon in removed


def test_every_reconstruction_suffix_is_cleaned_up(tmp_path):
    """Two specs write two qsirecon-<suffix> folders; replace must clear both or the guard refuses."""
    project = _project(tmp_path)
    first = _reconstruction(project, "DSIStudio")
    second = _reconstruction(project, "DIPYDKI")

    outputs = existing_outputs_for_step(str(project), SID, STEP_QSIRECON)

    removed = {p for output in outputs for p in output.paths_to_remove}
    assert {first, second} <= removed


def test_replace_also_clears_the_report_and_logs_that_describe_it(tmp_path):
    """QSIRecon 26 writes qsirecon-<suffix>/sub-<id>.html and logs under qsirecon/sub-<id>."""
    from tit.pre.preflight import remove_preprocessing_output

    project = _project(tmp_path)
    recon = _reconstruction(project)
    report = recon.with_name(f"sub-{SID}.html")
    report.write_text("<html>old reconstruction</html>")
    logs = project / "derivatives" / "qsirecon" / f"sub-{SID}"
    (logs / "log").mkdir(parents=True)
    (logs / "log" / "run.toml").write_text("old")
    other_subject = recon.with_name("sub-002")
    (other_subject / "dwi").mkdir(parents=True)
    shared = recon.parent / "dataset_description.json"
    shared.write_text("{}")

    for output in existing_outputs_for_step(str(project), SID, STEP_QSIRECON):
        remove_preprocessing_output(output)

    assert not recon.exists() and not report.exists() and not logs.exists()
    assert other_subject.is_dir()  # another subject's reconstruction is untouched
    assert shared.is_file()  # the pipeline's own description stays


def test_log_folder_alone_is_not_an_existing_reconstruction(tmp_path):
    """A crashed run that wrote only derivatives/qsirecon/sub-<id>/log does not block the runner."""
    project = _project(tmp_path)
    logs = project / "derivatives" / "qsirecon" / f"sub-{SID}" / "log"
    logs.mkdir(parents=True)
    (logs / "crash.txt").write_text("boom")

    assert existing_outputs_for_step(str(project), SID, STEP_QSIRECON) == []


def test_skip_policy_does_not_run_qsirecon_over_an_existing_reconstruction(
    tmp_path, quiet_pipeline
):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    recon = _reconstruction(project)

    with patch("tit.pre.structural.run_qsirecon") as run_qsirecon:
        assert (
            run_pipeline(
                [SID],
                run_qsirecon=True,
                skip_existing_outputs=True,
                runner=_runner(),
            )
            == 0
        )

    run_qsirecon.assert_not_called()
    assert recon.is_dir()


def test_replace_policy_clears_the_reconstruction_and_the_runner_guard_passes(
    tmp_path, quiet_pipeline
):
    """The real run_qsirecon reaches its container command once replace has run."""
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    recon = _reconstruction(project)
    builder = MagicMock()
    builder.build_qsirecon_cmd.return_value = ["docker", "run", "qsirecon"]
    runner = _runner()

    with (
        patch(
            "tit.pre.qsi.qsirecon.validate_dood_environment", return_value=(True, None)
        ),
        patch("tit.pre.qsi.qsirecon.pull_image_if_needed", return_value=True),
        patch("tit.pre.qsi.qsirecon.DockerCommandBuilder", return_value=builder),
    ):
        assert (
            run_pipeline(
                [SID],
                run_qsirecon=True,
                replace_existing_outputs=True,
                runner=runner,
            )
            == 0
        )

    assert not recon.exists()
    runner.run.assert_called_once()
    assert runner.run.call_args.args[0] == ["docker", "run", "qsirecon"]


def test_without_a_policy_the_existing_reconstruction_is_reported_by_the_pipeline(
    tmp_path, quiet_pipeline
):
    """The pipeline's own sentence (choose skip or replace) wins over the runner's 'remove manually'."""
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    _reconstruction(project)

    with (
        patch("tit.pre.structural.run_qsirecon") as run_qsirecon,
        pytest.raises(PreprocessError, match="skip existing outputs, replace"),
    ):
        run_pipeline([SID], run_qsirecon=True, runner=_runner())

    run_qsirecon.assert_not_called()


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
    client = TestClient(create_app(settings), base_url="http://127.0.0.1:8765")
    return project, client


def _plan_g5(client) -> dict:
    resp = client.post(
        "/api/plan/pre",
        json={
            "config": {
                "subject_ids": [SID],
                "run_qsirecon": True,
                "skip_existing_outputs": True,
            },
            "subject_ids": [SID],
        },
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [index] = [
        i for i, stage in enumerate(body["resolved"]["stages"]) if "G5" in stage["tags"]
    ]
    return body["jobs"][index]


def test_plan_reports_the_reconstruction_as_existing(plan_client):
    project, client = plan_client
    recon = _reconstruction(project)

    job = _plan_g5(client)

    assert job["exists"] is True
    assert job["will_overwrite"] is False  # skip policy keeps it
    assert Path(job["output_dir"]) == recon


def test_plan_does_not_flag_a_log_folder_the_runner_ignores(plan_client):
    project, client = plan_client
    logs = project / "derivatives" / "qsirecon" / f"sub-{SID}"
    logs.mkdir(parents=True)
    (logs / "log.txt").write_text("crashed before reconstructing")

    assert _plan_g5(client)["exists"] is False


_DATASET = os.environ.get("TIT_DATASET_000", "")


def _mtimes(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in sorted(root.rglob("*"))}


@pytest.mark.skipif(
    not _DATASET or not Path(_DATASET, "derivatives", "qsirecon").is_dir(),
    reason="skipping: TIT_DATASET_000 unset or has no derivatives/qsirecon",
)
def test_dataset_000_sub_chn_reconstruction_is_found_read_only():
    root = Path(_DATASET)
    recon_root = root / "derivatives" / "qsirecon"
    before = _mtimes(recon_root)
    expected = recon_root / "derivatives" / "qsirecon-DSIStudio" / "sub-CHN"
    assert expected.is_dir(), f"skipping premise: {expected} missing"

    outputs = existing_outputs_for_step(str(root), "CHN", STEP_QSIRECON)

    assert expected in {p for o in outputs for p in o.paths_to_remove}
    assert _mtimes(recon_root) == before
