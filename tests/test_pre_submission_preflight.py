"""Submission refuses what the QSIRecon and tissue runners refuse later (2026-10-22, p27).

What this pins: ``POST /api/jobs/groups`` (and ``/api/jobs/preflight``, which share
``tit.jobs.preflight._check_pre``) answers 422 "Missing inputs" for a pre group the runners would
refuse hours later, and accepts the neighbouring groups they would run:

- QSIRecon atlases are warped from MNI, so they need QSIPrep's MNI normalization. The runtime
  guard (``tit/pre/qsi/qsirecon.py``: no ``*_to-MNI152NLin2009cAsym_*xfm.h5`` under the QSIPrep
  output -> refuse) is the expected rule; for a QSIPrep that runs in the same group the rule is
  ``tit/pre/qsi/qsiprep.py``'s: the transform is written when ``mni_normalization`` is on or when
  distortion correction falls back to fieldmap-less SyN (``plan_distortion_correction``).
- QSIRecon alone needs a valid QSIPrep output (``validate_qsiprep_output``, the runtime check).
- Tissue analysis reads ``m2m_<id>/segmentation/labeling.nii.gz``
  (``tit/pre/tissue_analyzer.py``: missing -> ``labeling.nii.gz not found``); a charm in the same
  group writes it.
- Under "skip" a step whose output already exists does not run, so its inputs are not required.

Data is synthetic and hand-written (BIDS T1 placeholder, a DWI with a valid gradient table from
``tests/conftest.py::write_dwi`` -- phase encoding j-, a reverse-PE (j) fieldmap). The parity
test runs the real ``run_qsirecon`` guard (Docker preflight patched) on the same files. Nothing
is queued to run: the job manager is never started.

Reproduce: ``.venv/bin/python -m pytest tests/test_pre_submission_preflight.py -q``.
"""

from __future__ import annotations

import gzip
import json
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.pre.utils import PreprocessError  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

SID = "001"
AUTH = {"Authorization": "Bearer t"}
NONE = dict.fromkeys(
    (
        "convert_dicom",
        "create_m2m",
        "run_fastsurfer",
        "run_freesurfer",
        "run_tissue_analysis",
        "run_qsiprep",
        "run_qsirecon",
        "extract_dti",
    ),
    False,
)
ATLAS_MSG = "QSIRecon atlases need QSIPrep's MNI normalization"


@pytest.fixture
def project(tmp_path, monkeypatch, write_dwi) -> Path:
    """sub-001 with a BIDS T1 and a j- DWI that QSIPrep's own input check accepts."""
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "prefs.json"
    )
    pm = get_path_manager(str(tmp_path))
    anat = Path(pm.bids_anat(SID))
    anat.mkdir(parents=True)
    (anat / f"sub-{SID}_T1w.nii.gz").write_bytes(b"t1")
    write_dwi(Path(pm.bids_dwi(SID)), stem=f"sub-{SID}_dwi")
    return tmp_path


@pytest.fixture
def client(project):
    manager = JobManager(str(project), budget=Cost(cpus=8, mem_gb=64))
    bootstrap.set_manager_for_testing(manager)
    yield TestClient(
        create_app(ServerSettings(project_dir=str(project), token="t")),
        base_url="http://127.0.0.1:8765",
    ), manager
    bootstrap.reset_manager()


def _reverse_pe_fieldmap(project: Path) -> Path:
    """fmap/sub-001_acq-dwi_dir-PA_epi: phase encoding j (the DWI's is j-), readout known."""
    fmap = Path(get_path_manager(str(project)).bids_datatype(SID, "fmap"))
    fmap.mkdir(parents=True, exist_ok=True)
    header = bytearray(352)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 4, 64, 64, 40, 2, 1, 1, 1)
    header[344:348] = b"n+1\x00"
    image = fmap / f"sub-{SID}_acq-dwi_dir-PA_epi.nii.gz"
    with gzip.open(image, "wb") as handle:
        handle.write(bytes(header))
    (fmap / f"sub-{SID}_acq-dwi_dir-PA_epi.json").write_text(
        json.dumps(
            {
                "PhaseEncodingDirection": "j",
                "TotalReadoutTime": 0.05,
                "IntendedFor": [f"dwi/sub-{SID}_dwi.nii.gz"],
            }
        )
    )
    return image


def _qsiprep_output(project: Path, *, mni: bool) -> Path:
    """A QSIPrep output ``validate_qsiprep_output`` accepts, with or without the MNI xfm."""
    subject = Path(get_path_manager(str(project)).qsiprep_subject(SID))
    (subject / "dwi").mkdir(parents=True)
    (subject / "dwi" / f"sub-{SID}_space-ACPC_desc-preproc_dwi.nii.gz").write_bytes(
        b"d"
    )
    (subject / "anat").mkdir()
    (subject / "anat" / f"sub-{SID}_from-ACPC_to-anat_mode-image_xfm.mat").write_bytes(
        b"x"
    )
    if mni:
        (
            subject
            / "anat"
            / f"sub-{SID}_from-ACPC_to-MNI152NLin2009cAsym_mode-image_xfm.h5"
        ).write_bytes(b"x")
    return subject


def _post(client, config: dict, *, route: str = "/api/jobs/groups"):
    http, _ = client
    return http.post(
        route,
        headers=AUTH,
        json={
            "kind": "pre",
            "config": {"subject_ids": [SID], **NONE, **config},
            "subject_ids": [SID],
        },
    )


def _refused(r, expected_path: Path, *needles: str) -> dict:
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["detail"] == "Missing inputs"
    (item,) = body["missing"]
    assert Path(item["expected_path"]) == expected_path
    for needle in needles:
        assert needle in item["how_to_fix"], item
    return item


def _accepted(r, client, tags: list[str]) -> None:
    assert r.status_code == 201, r.text
    _, manager = client
    specs = [manager.get_detail(job["id"])["spec"] for job in r.json()["jobs"]]
    assert [t for spec in specs for t in spec["tags"] if t.startswith("G")] == tags


def _qsi(mni: bool, atlases) -> dict:
    return {
        "qsiprep_config": {"mni_normalization": mni},
        "qsi_recon_config": {"atlases": atlases},
    }


# ---------------------------------------------------------------------------------------------
# (a)/(b) QSIPrep and QSIRecon in one group: this run's QSIPrep settings decide the transform
# ---------------------------------------------------------------------------------------------
def test_atlases_with_mni_off_and_a_usable_fieldmap_are_refused(project, client):
    _reverse_pe_fieldmap(project)
    r = _post(
        client, {"run_qsiprep": True, "run_qsirecon": True, **_qsi(False, ["AAL116"])}
    )
    _refused(
        r,
        Path(get_path_manager(str(project)).qsiprep_subject(SID)),
        ATLAS_MSG,
        "MNI normalization",
        "without atlases",
    )
    assert client[1].list_jobs() == []


@pytest.mark.parametrize(
    "fieldmap, mni, atlases",
    [
        (
            False,
            False,
            ["AAL116"],
        ),  # no fieldmap: SyN, which turns MNI normalization on
        (True, True, ["AAL116"]),  # the user turned it on
        (True, False, None),  # no atlases, nothing to warp
    ],
    ids=["syn-forces-mni", "mni-on", "no-atlases"],
)
def test_the_neighbouring_qsi_groups_are_accepted(
    project, client, fieldmap, mni, atlases
):
    if fieldmap:
        _reverse_pe_fieldmap(project)
    r = _post(client, {"run_qsiprep": True, "run_qsirecon": True, **_qsi(mni, atlases)})
    _accepted(r, client, ["G4", "G5"])


def test_preflight_route_reports_the_same_conflict(project, client):
    _reverse_pe_fieldmap(project)
    http, _ = client
    r = http.post(
        "/api/jobs/preflight",
        headers=AUTH,
        json={
            "kind": "pre",
            "config": {
                "subject_ids": [SID],
                **NONE,
                "run_qsiprep": True,
                "run_qsirecon": True,
                **_qsi(False, ["AAL116"]),
            },
        },
    )
    assert r.status_code == 200
    (item,) = r.json()["missing"]
    assert ATLAS_MSG in item["how_to_fix"]


# ---------------------------------------------------------------------------------------------
# (c) QSIRecon alone reads the QSIPrep output on disk
# ---------------------------------------------------------------------------------------------
def test_qsirecon_alone_without_qsiprep_output_is_refused(project, client):
    r = _post(client, {"run_qsirecon": True})
    _refused(
        r,
        Path(get_path_manager(str(project)).qsiprep_subject(SID)),
        "QSIPrep output",
        f"Run QSIPrep for sub-{SID} first",
    )


def test_qsirecon_alone_with_atlases_needs_the_transform_on_disk(project, client):
    _qsiprep_output(project, mni=False)
    r = _post(client, {"run_qsirecon": True, **_qsi(False, ["AAL116"])})
    _refused(r, Path(get_path_manager(str(project)).qsiprep_subject(SID)), ATLAS_MSG)


@pytest.mark.parametrize(
    "mni, atlases", [(True, ["AAL116"]), (False, None)], ids=["xfm", "no-atlases"]
)
def test_qsirecon_alone_on_a_usable_output_is_accepted(project, client, mni, atlases):
    _qsiprep_output(project, mni=mni)
    r = _post(client, {"run_qsirecon": True, **_qsi(False, atlases)})
    _accepted(r, client, ["G5"])


def test_qsirecon_under_skip_with_a_reconstruction_is_not_checked(project, client):
    """It will not run (the runner skips it), so its missing QSIPrep input is no reason to refuse."""
    recon = (
        project
        / "derivatives"
        / "qsirecon"
        / "derivatives"
        / "qsirecon-DSIStudio"
        / f"sub-{SID}"
        / "dwi"
    )
    recon.mkdir(parents=True)
    (recon / "model.nii.gz").write_bytes(b"x")
    r = _post(client, {"run_qsirecon": True, "skip_existing_outputs": True})
    _accepted(r, client, ["G5"])


@pytest.mark.parametrize("mni", [False, True])
def test_preflight_and_the_runtime_guard_agree_on_the_transform(project, mni):
    """The same QSIPrep output: preflight refuses exactly when ``run_qsirecon`` would."""
    from tit.pre.preflight import find_missing_preprocessing_inputs
    from tit.pre.qsi.qsirecon import run_qsirecon

    _qsiprep_output(project, mni=mni)
    problems = find_missing_preprocessing_inputs(
        str(project), [SID], run_qsirecon=True, qsi_recon_config={"atlases": ["AAL116"]}
    )
    with (
        patch(
            "tit.pre.qsi.qsirecon.validate_dood_environment", return_value=(True, None)
        ),
        patch("tit.pre.qsi.qsirecon.pull_image_if_needed", return_value=True),
        patch("tit.pre.qsi.qsirecon.DockerCommandBuilder"),
    ):
        runner = MagicMock()
        runner.run.return_value = 0
        try:
            run_qsirecon(
                str(project),
                SID,
                atlases=["AAL116"],
                logger=MagicMock(),
                runner=runner,
            )
            runtime_refused = False
        except PreprocessError as exc:
            assert ATLAS_MSG in str(exc)
            runtime_refused = True
    assert runtime_refused is (not mni)
    assert bool(problems) is runtime_refused


# ---------------------------------------------------------------------------------------------
# (d) Tissue analysis reads charm's segmentation
# ---------------------------------------------------------------------------------------------
def _labeling(project: Path) -> Path:
    return Path(get_path_manager(str(project)).tissue_labeling(SID))


def test_tissue_analysis_without_a_segmentation_is_refused(project, client):
    r = _post(client, {"run_tissue_analysis": True})
    _refused(r, _labeling(project), "Tissue analysis", "charm")
    assert client[1].list_jobs() == []


def test_tissue_analysis_with_charm_in_the_same_group_is_accepted(project, client):
    r = _post(client, {"run_tissue_analysis": True, "create_m2m": True})
    _accepted(r, client, ["G2a", "G3"])


def test_tissue_analysis_on_an_existing_segmentation_is_accepted(project, client):
    _labeling(project).parent.mkdir(parents=True)
    _labeling(project).write_bytes(b"labels")
    r = _post(client, {"run_tissue_analysis": True})
    _accepted(r, client, ["G3"])


def test_a_skipped_charm_does_not_supply_the_segmentation(project, client):
    """Under "skip" an existing head model is not rebuilt, so a head model made without the
    segmentation folder (Dataset 000's sub-ernie) still leaves tissue analysis without input.
    """
    m2m = Path(get_path_manager(str(project)).m2m(SID))
    m2m.mkdir(parents=True)
    (m2m / f"{SID}.msh").write_bytes(b"mesh")
    (m2m / "final_tissues.nii.gz").write_bytes(b"seg")
    r = _post(
        client,
        {
            "run_tissue_analysis": True,
            "create_m2m": True,
            "skip_existing_outputs": True,
        },
    )
    _refused(r, _labeling(project), "Tissue analysis")
