"""DICOM conversion never succeeds having converted nothing, and "skip" skips per modality.

What this pins (2026-10-22):

- A DICOM Part 10 file is recognised by its content, not its name: PS3.10 section 7.1 puts
  a 128-byte preamble before the 4-byte prefix ``b"DICM"``. Siemens ``.IMA`` exports and
  extensionless PACS exports carry it, and ``dcm2niix`` reads them; before this fix a folder of
  them was "No DICOM ... found", the stage returned 0 and the next stage failed with "Run DICOM
  conversion first".
- When a modality folder holds files and nothing at all could be ingested, the stage raises a
  ``PreprocessError`` naming the folder and its file count instead of returning normally.
- ``skip_existing_outputs`` skips only the modalities already converted: an existing
  ``anat/sub-<id>_T1w.nii.gz`` no longer stops a newly added T2w from being converted
  (docs/wiki/pre-processing.md "Run and monitor": skip what exists, run the rest).
- The pre-flight input check (``find_missing_preprocessing_inputs``, behind the job
  sweep's "Missing inputs" 422) defers a stage's T1w/DWI check only while conversion can
  still produce that input: under "skip", a modality is still to come only when its source
  folder holds files and its BIDS NIfTI is absent (the converter's own rule). The empty
  ``dicom/`` folders the app scaffolds for every modality are not a source.

Where the expectations come from: the DICOM standard's preamble layout above; the BIDS
names the stage documents (``sub-<id>_<suffix>.nii.gz``); bytes written by the test itself;
for the input checks, what each stage reads (charm, FastSurfer and FreeSurfer a T1w; QSIPrep a
T1w and a DWI with its gradient table) and the scaffold ``tit.pre.utils.ensure_subject_dirs``
really creates.
``dcm2niix`` is replaced by a fake runner that writes the files dcm2niix's ``-f``/``-o``
arguments name, so the test checks that the real folder and name reached the command.

Reproduce: ``pytest tests/test_pre_dicom_outcome.py -q``.

Deliberately elsewhere: archive extraction, scanning and fieldmap naming
(``tests/test_pre_dicom.py``).
"""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.paths import get_path_manager
from tit.pre.dicom2nifti import run_dicom_to_nifti
from tit.pre.utils import CommandRunner, PreprocessError

SID = "001"
LOGGER = logging.getLogger("tests.p17.dicom")


def _dicom_bytes(payload: bytes = b"payload") -> bytes:
    """PS3.10 section 7.1: 128-byte preamble, then the 4-byte prefix 'DICM'."""
    return b"\0" * 128 + b"DICM" + payload


def _project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


def _source(project: Path, modality: str) -> Path:
    folder = project / "sourcedata" / f"sub-{SID}" / modality / "dicom"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _fake_dcm2niix(exit_code: int = 0) -> MagicMock:
    """A runner that writes what `dcm2niix -f <name> -o <dir> <input>` would."""
    runner = MagicMock(spec=CommandRunner)
    runner.stop_event = None

    def run(cmd, **_kwargs):
        if exit_code == 0:
            name = cmd[cmd.index("-f") + 1]
            out = Path(cmd[cmd.index("-o") + 1])
            (out / f"{name}.nii.gz").write_bytes(gzip.compress(b"converted", mtime=0))
            (out / f"{name}.json").write_text("{}")
        return exit_code

    runner.run.side_effect = run
    return runner


@pytest.mark.parametrize(
    "names",
    [["IM0001", "IM0002", "IM0003"], ["SUB.MR.0001.IMA", "SUB.MR.0002.IMA"]],
    ids=["extensionless", "siemens-ima"],
)
def test_dicom_without_a_dcm_extension_is_converted(tmp_path, names):
    project = _project(tmp_path)
    folder = _source(project, "T1w")
    for name in names:
        (folder / name).write_bytes(_dicom_bytes())
    runner = _fake_dcm2niix()

    run_dicom_to_nifti(str(project), SID, logger=LOGGER, runner=runner)

    [call] = runner.run.call_args_list
    cmd = call.args[0]
    assert cmd[0] == "dcm2niix"
    assert cmd[cmd.index("-f") + 1] == f"sub-{SID}_T1w"
    assert (
        Path(cmd[-1]) == folder.parent
    )  # the T1w modality folder, searched recursively
    assert (project / f"sub-{SID}" / "anat" / f"sub-{SID}_T1w.nii.gz").is_file()


def test_a_nifti_is_copied_even_when_its_header_reads_dicm_at_byte_128(tmp_path):
    """A known image extension decides first; only other files are sniffed for the prefix.

    Bytes 128-131 of a NIfTI-1 header are its ``cal_min`` float, which can hold anything.
    """
    project = _project(tmp_path)
    folder = project / "sourcedata" / f"sub-{SID}" / "T1w"
    folder.mkdir(parents=True)
    source = folder / "t1.nii"
    source.write_bytes(_dicom_bytes(b"rest of a NIfTI"))
    runner = _fake_dcm2niix()

    run_dicom_to_nifti(str(project), SID, logger=LOGGER, runner=runner)

    runner.run.assert_not_called()  # not handed to dcm2niix as a DICOM
    target = project / f"sub-{SID}" / "anat" / f"sub-{SID}_T1w.nii.gz"
    assert gzip.decompress(target.read_bytes()) == source.read_bytes()


def test_files_without_the_dicom_prefix_fail_the_stage_with_folder_and_count(tmp_path):
    project = _project(tmp_path)
    folder = _source(project, "T1w")
    for index in range(4):
        # 132 bytes, but the prefix at 128 is not "DICM": not a Part 10 file.
        (folder / f"IM{index:04d}").write_bytes(b"\0" * 128 + b"NOPE" + b"x")
    runner = _fake_dcm2niix()

    with pytest.raises(PreprocessError) as excinfo:
        run_dicom_to_nifti(str(project), SID, logger=LOGGER, runner=runner)

    message = str(excinfo.value)
    assert str(folder.parent) in message
    assert "4 file" in message
    runner.run.assert_not_called()


def test_failed_dcm2niix_on_the_only_series_fails_the_stage(tmp_path):
    project = _project(tmp_path)
    folder = _source(project, "T1w")
    (folder / "scan.dcm").write_bytes(_dicom_bytes())

    with pytest.raises(PreprocessError, match="1 file"):
        run_dicom_to_nifti(
            str(project), SID, logger=LOGGER, runner=_fake_dcm2niix(exit_code=1)
        )


def test_empty_scaffold_is_still_a_warning_not_a_failure(tmp_path):
    """Nothing to convert at all (only the empty dicom/ folders the app scaffolds)."""
    project = _project(tmp_path)
    for modality in ("T1w", "T2w", "ct", "dwi", "fmap"):
        _source(project, modality)
    logger = MagicMock()

    run_dicom_to_nifti(str(project), SID, logger=logger, runner=_fake_dcm2niix())

    logger.warning.assert_called_once()


def test_one_converted_modality_is_enough_to_succeed(tmp_path):
    """A stray unreadable file next to a good series is a warning, not a failed stage."""
    project = _project(tmp_path)
    (_source(project, "T1w") / "scan.dcm").write_bytes(_dicom_bytes())
    (_source(project, "T2w") / "notes.txt").write_text("not an image")

    run_dicom_to_nifti(str(project), SID, logger=LOGGER, runner=_fake_dcm2niix())

    assert (project / f"sub-{SID}" / "anat" / f"sub-{SID}_T1w.nii.gz").is_file()


@pytest.fixture
def quiet_pipeline():
    with (
        patch("tit.pre.structural._install_sigterm_handler"),
        patch("tit.pre.structural.build_logger", return_value=LOGGER),
    ):
        yield


def test_pipeline_no_longer_returns_success_after_converting_nothing(
    tmp_path, quiet_pipeline
):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    (_source(project, "T1w") / "README").write_text("export notes, no images")

    with pytest.raises(PreprocessError, match="1 file"):
        run_pipeline([SID], convert_dicom=True, runner=_fake_dcm2niix())


def test_skip_converts_the_modality_that_is_missing(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    anat = project / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)
    t1 = anat / f"sub-{SID}_T1w.nii.gz"
    t1.write_bytes(gzip.compress(b"the T1w already converted", mtime=0))
    t1_before = t1.read_bytes()
    # The T1w DICOMs are still in sourcedata; skip must not reconvert them.
    (_source(project, "T1w") / "IM0001").write_bytes(_dicom_bytes())
    t2_source = project / "sourcedata" / f"sub-{SID}" / "T2w" / "t2.nii.gz"
    t2_source.parent.mkdir(parents=True, exist_ok=True)
    t2_source.write_bytes(gzip.compress(b"a T2w NIfTI", mtime=0))
    runner = _fake_dcm2niix()

    assert (
        run_pipeline(
            [SID], convert_dicom=True, skip_existing_outputs=True, runner=runner
        )
        == 0
    )

    t2 = anat / f"sub-{SID}_T2w.nii.gz"
    assert gzip.decompress(t2.read_bytes()) == b"a T2w NIfTI"
    assert t1.read_bytes() == t1_before
    runner.run.assert_not_called()  # no dcm2niix over the already-converted T1w


def test_skip_with_everything_converted_runs_nothing(tmp_path, quiet_pipeline):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    anat = project / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)
    (anat / f"sub-{SID}_T1w.nii.gz").write_bytes(b"t1")
    (_source(project, "T1w") / "IM0001").write_bytes(_dicom_bytes())
    runner = _fake_dcm2niix()

    run_pipeline([SID], convert_dicom=True, skip_existing_outputs=True, runner=runner)

    runner.run.assert_not_called()
    assert sorted(p.name for p in anat.iterdir()) == [f"sub-{SID}_T1w.nii.gz"]


def test_skip_over_a_converted_t1w_tolerates_an_unreadable_t2w_folder(tmp_path):
    """The subject already has its T1w, so the stage succeeds; the T2w folder is logged."""
    project = _project(tmp_path)
    anat = project / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)
    (anat / f"sub-{SID}_T1w.nii.gz").write_bytes(b"t1")
    (_source(project, "T1w") / "IM0001").write_bytes(_dicom_bytes())
    (_source(project, "T2w") / "notes.txt").write_text("not an image")
    runner = _fake_dcm2niix()

    run_dicom_to_nifti(
        str(project), SID, logger=LOGGER, runner=runner, skip_existing=True
    )

    runner.run.assert_not_called()
    assert sorted(p.name for p in anat.iterdir()) == [f"sub-{SID}_T1w.nii.gz"]


def test_without_a_policy_an_existing_modality_still_stops_the_stage(
    tmp_path, quiet_pipeline
):
    from tit.pre.structural import run_pipeline

    project = _project(tmp_path)
    anat = project / f"sub-{SID}" / "anat"
    anat.mkdir(parents=True)
    (anat / f"sub-{SID}_T1w.nii.gz").write_bytes(b"t1")
    (_source(project, "T2w") / "IM0001").write_bytes(_dicom_bytes())
    runner = _fake_dcm2niix()

    with pytest.raises(PreprocessError, match="already exists"):
        run_pipeline([SID], convert_dicom=True, runner=runner)

    runner.run.assert_not_called()


# --------------------------------------------------------------------------- input checks


def _converted(project: Path, datatype: str, name: str) -> Path:
    """A BIDS NIfTI an earlier conversion left (``sub-<id>/<datatype>/<name>.nii.gz``)."""
    folder = project / f"sub-{SID}" / datatype
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.nii.gz"
    path.write_bytes(b"converted")
    return path


def _skip_problems(project: Path, **steps) -> list:
    from tit.pre.preflight import find_missing_preprocessing_inputs

    return find_missing_preprocessing_inputs(
        str(project), [SID], convert_dicom=True, skip_existing_outputs=True, **steps
    )


def test_skip_reports_a_missing_t1w_no_source_can_produce_at_job_submission(tmp_path):
    """T2w converted, no T1w anywhere: the job sweep reports it before anything is queued."""
    from tit.jobs.preflight import preflight
    from tit.pre.utils import ensure_subject_dirs

    project = _project(tmp_path)
    ensure_subject_dirs(str(project), SID)  # an empty dicom/ folder for every modality
    _converted(project, "anat", f"sub-{SID}_T2w")

    found = preflight(
        "pre",
        {
            "subject_ids": [SID],
            "convert_dicom": True,
            "create_m2m": True,
            "skip_existing_outputs": True,
        },
        str(project),
    )

    assert [m.expected_path for m in found] == [str(project / f"sub-{SID}" / "anat")]
    assert "requires a BIDS T1w image" in found[0].how_to_fix


def test_skip_reports_missing_dwi_when_no_dwi_source_waits(tmp_path):
    from tit.pre.preflight import STEP_QSIPREP

    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T1w")

    problems = _skip_problems(project, run_qsiprep=True)

    assert [p.step for p in problems] == [STEP_QSIPREP]
    assert "requires BIDS DWI data" in problems[0].message
    assert problems[0].path == project / f"sub-{SID}" / "dwi"


@pytest.mark.parametrize(
    "flag,step",
    [
        ("create_m2m", "charm"),
        ("run_fastsurfer", "fastsurfer"),
        ("run_freesurfer", "freesurfer"),
        ("run_qsiprep", "qsiprep"),
    ],
)
def test_skip_defers_the_t1w_check_while_t1w_dicoms_wait_in_sourcedata(
    tmp_path, write_dwi, flag, step
):
    """The T2w and DWI were converted earlier; T1w DICOMs dropped in since convert now."""
    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T2w")
    write_dwi(project / f"sub-{SID}" / "dwi", stem=f"sub-{SID}_dwi")

    def t1w_problems() -> list[str]:
        return [
            p.step
            for p in _skip_problems(project, **{flag: True})
            if "T1w image" in p.message
        ]

    assert t1w_problems() == [step]  # nothing can produce it yet
    (_source(project, "T1w") / "IM0001").write_bytes(_dicom_bytes())
    assert t1w_problems() == []


def test_skip_defers_the_dwi_check_while_dwi_dicoms_wait_in_sourcedata(tmp_path):
    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T1w")
    (_source(project, "dwi") / "IM0001").write_bytes(_dicom_bytes())

    assert _skip_problems(project, run_qsiprep=True) == []


def test_skip_defers_the_fieldmap_check_while_fieldmap_dicoms_wait(tmp_path, write_dwi):
    """A converted reverse-PE fieldmap can be the usable one QSIPrep's check asks for."""
    import json

    from tit.pre.preflight import STEP_QSIPREP

    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T1w")
    write_dwi(project / f"sub-{SID}" / "dwi", stem=f"sub-{SID}_dwi")  # PE j-
    # A hand-placed DWI fieldmap with the DWI's own PE direction cannot correct it.
    fmap = _converted(project, "fmap", f"sub-{SID}_acq-dwi_dir-AP_epi")
    fmap.with_name(f"sub-{SID}_acq-dwi_dir-AP_epi.json").write_text(
        json.dumps({"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.05})
    )

    problems = _skip_problems(project, run_qsiprep=True)
    assert [p.step for p in problems] == [STEP_QSIPREP]
    assert "fieldmaps were found but none can be used" in problems[0].message

    (_source(project, "fmap") / "IM0001").write_bytes(_dicom_bytes())
    assert _skip_problems(project, run_qsiprep=True) == []


def test_a_waiting_dwi_source_does_not_defer_the_t1w_check(tmp_path):
    """Converting a DWI cannot produce the T1w charm reads, so its check runs now."""
    from tit.pre.preflight import STEP_CHARM

    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T2w")
    (_source(project, "dwi") / "IM0001").write_bytes(_dicom_bytes())

    problems = _skip_problems(project, create_m2m=True)

    assert [p.step for p in problems] == [STEP_CHARM]
    assert "requires a BIDS T1w image" in problems[0].message


def test_a_dwi_source_already_converted_is_not_waiting(tmp_path):
    """Every modality converted: its sourcedata stays, but conversion produces nothing."""
    from tit.pre.preflight import STEP_QSIPREP

    project = _project(tmp_path)
    for datatype, name in (
        ("anat", f"sub-{SID}_T1w"),
        ("anat", f"sub-{SID}_T2w"),
        ("dwi", f"sub-{SID}_dwi"),  # no .bval/.bvec: QSIPrep cannot use it
    ):
        _converted(project, datatype, name)
    for modality in ("T1w", "T2w", "dwi"):
        (_source(project, modality) / "IM0001").write_bytes(_dicom_bytes())

    problems = _skip_problems(project, run_qsiprep=True)

    assert [p.step for p in problems] == [STEP_QSIPREP]
    assert "requires BIDS DWI data" in problems[0].message


def test_without_skip_the_whole_conversion_runs_so_the_checks_wait(tmp_path):
    """No skip (no policy, or replace): conversion owns every input, as before."""
    from tit.pre.preflight import find_missing_preprocessing_inputs

    project = _project(tmp_path)
    _converted(project, "anat", f"sub-{SID}_T2w")

    problems = find_missing_preprocessing_inputs(
        str(project), [SID], convert_dicom=True, create_m2m=True
    )

    assert problems == []
