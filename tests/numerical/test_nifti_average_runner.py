"""``python -m tit.stats.nifti_average`` end to end with real NIfTI files (p23, 2026-10-22).

The runner had no test that read a file it wrote. Here it runs as the job runner does -- a
subprocess on a JSON config, ``TIT_EVENTS_FILE`` set -- over synthetic 4-D ``(x, y, z, 1)``
volumes on a shared oblique grid in a scratch project, and every output is read back with
nibabel.

Pins:

* the folder it writes is the one ``/api/plan/nifti_average`` names (and the documented
  ``derivatives/ti-toolbox/nifti_average/<output_name>``), and its artifact events are exactly
  the files on disk;
* ``average_<group>`` is the voxelwise mean of that group's input files and every difference is
  ``avgA - avgB`` over every alphabetical pair when none is typed (``np.mean`` over the files
  read back here, a second reading of the inputs);
* ``config.json`` records space, pattern, groups and differences;
* ``space="subject"`` reads ``*_TI_subject_TI_max`` while an MNI decoy beside it holds other
  values; an mTI simulation (``mTI/mesh`` present) is read from ``mTI/niftis`` with the mTI
  spelling;
* two subject-space rows of one group on different grids fail with exit 1 and a result error
  naming the second subject; a missing file fails with the path preflight reports.

Configs are the desktop builders' own (``tests/fixtures/desktop_configs/panels-nifti``), plus one
hand-written three-group config for the default pairs. Input paths are spelled from the
documented simulation layout (``derivatives/SimNIBS/sub-<id>/Simulations/<sim>/TI/niftis``),
not from ``PathManager``.

Known gap, xfail(strict) (``tit/stats/nifti.py`` is owned elsewhere): two GROUPS on different
grids are not compared with each other (``load_grouped_subjects_ti_toolbox`` checks the grid
within a group only). Equal shapes with different affines give exit 0 and a difference map of
voxels that are not the same points; unequal shapes fail on a numpy broadcast error that names
no subject. When that loader checks every group against one reference grid, these XPASS and
the marker goes.

Run (container): ``simnibs_python -m pytest tests/numerical/test_nifti_average_runner.py -q``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "desktop_configs" / "panels-nifti"
SHAPE = (5, 6, 7, 1)
AFFINE = np.array(
    [
        [2.0, 0.25, 0.0, -20.0],
        [0.0, 2.0, 0.5, -30.0],
        [0.1, 0.0, 2.0, -10.0],
        [0, 0, 0, 1],
    ]
)
MNI_FILE = "grey_{sim}_TI_MNI_MNI_TI_max.nii.gz"
SUBJECT_FILE = "grey_{sim}_TI_subject_TI_max.nii.gz"


def _fixture_config(name: str) -> dict:
    case = json.loads((CORPUS / f"{name}.json").read_text())
    (job,) = case["jobs"]
    assert job["kind"] == "nifti_average"
    return job["config"]


def _niftis(project: Path, sid: str, sim: str, mti: bool = False) -> Path:
    sim_dir = project / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / sim
    folder = sim_dir / ("mTI" if mti else "TI") / "niftis"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _write(path: Path, data: np.ndarray, affine: np.ndarray = AFFINE) -> Path:
    import nibabel as nib

    nib.save(nib.Nifti1Image(data.astype(np.float32), affine), str(path))
    return path


def _read(path: Path) -> np.ndarray:
    import nibabel as nib

    return np.squeeze(np.asarray(nib.load(str(path)).get_fdata(), dtype=np.float64))


def _volume(seed: int, shape=SHAPE) -> np.ndarray:
    return np.random.default_rng(seed).random(shape) * 0.3


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    return root


def _run(project: Path, config: dict, tmp_path: Path):
    cfg = tmp_path / "nifti_average.json"
    cfg.write_text(json.dumps({**config, "project_dir": str(project)}))
    events_file = tmp_path / "events.jsonl"
    events_file.unlink(missing_ok=True)
    env = {
        **os.environ,
        "TIT_EVENTS_FILE": str(events_file),
        "PYTHONPATH": str(REPO),
        "TIT_NO_TELEMETRY": "1",
    }
    env.pop("TIT_JOB_ID", None)
    proc = subprocess.run(
        [sys.executable, "-m", "tit.stats.nifti_average", str(cfg)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    events = [json.loads(line) for line in events_file.read_text().splitlines()]
    return proc, events


def _result(events: list[dict]) -> dict:
    (result,) = [e for e in events if e["type"] == "result"]
    return result["outputs"]


def _planned_output_dir(project: Path, config: dict) -> str:
    from tit.paths import get_path_manager
    from tit.server.routes.plan import PlanRequest, plan

    get_path_manager(str(project))
    subjects = sorted({s["subject_id"] for s in config["subjects"]})
    (job,) = plan(
        "nifti_average", PlanRequest(config=config, subject_ids=subjects)
    ).jobs
    return job.output_dir


def _check_written(out: Path, events: list[dict]) -> None:
    artifacts = {e["path"] for e in events if e["type"] == "artifact"}
    assert artifacts == {str(p) for p in out.iterdir()}


def test_mni_fixture_writes_the_mean_and_difference_where_the_plan_says(
    project, tmp_path
):
    config = _fixture_config("mni-space")
    inputs = {}
    for k, row in enumerate(config["subjects"]):
        sid, sim = row["subject_id"], row["simulation_name"]
        folder = _niftis(project, sid, sim)
        inputs[sid] = _write(folder / MNI_FILE.format(sim=sim), _volume(k))
        _write(folder / SUBJECT_FILE.format(sim=sim), _volume(k) + 100.0)  # decoy

    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = (
        project / "derivatives" / "ti-toolbox" / "nifti_average" / config["output_name"]
    )
    assert (
        _result(events)["output_dir"]
        == _planned_output_dir(project, config)
        == str(out)
    )

    group_of = {row["subject_id"]: row["group"] for row in config["subjects"]}
    groups = sorted(set(group_of.values()))
    means = {
        g: np.mean([_read(inputs[s]) for s in inputs if group_of[s] == g], axis=0)
        for g in groups
    }
    for g in groups:
        np.testing.assert_allclose(
            _read(out / f"average_{g}.nii.gz"), means[g], rtol=1e-6
        )
    a, b = groups
    np.testing.assert_allclose(
        _read(out / f"difference_{a}_minus_{b}.nii.gz"), means[a] - means[b], atol=1e-6
    )
    import nibabel as nib

    np.testing.assert_allclose(
        nib.load(str(out / f"average_{a}.nii.gz")).affine, AFFINE
    )

    recorded = json.loads((out / "config.json").read_text())
    assert recorded["space"] == "mni"
    assert (
        recorded["nifti_file_pattern"]
        == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    )
    assert recorded["groups"] == {
        g: [s for s in inputs if group_of[s] == g] for g in groups
    }
    assert recorded["differences"] == [f"{a} - {b}"]
    _check_written(out, events)


def test_three_groups_without_typed_pairs_get_every_alphabetical_difference(
    project, tmp_path
):
    rows = [("001", "C"), ("002", "A"), ("003", "C"), ("004", "B"), ("005", "A")]
    config = {
        "output_name": "three",
        "space": "mni",
        "nifti_file_pattern": None,
        "diff_pairs": [],
        "subjects": [
            {"subject_id": s, "simulation_name": "M1", "group": g} for s, g in rows
        ],
    }
    data = {
        s: _write(
            _niftis(project, s, "M1") / MNI_FILE.format(sim="M1"), _volume(10 + k)
        )
        for k, (s, _) in enumerate(rows)
    }
    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = Path(_result(events)["output_dir"])
    mean = {
        g: np.mean([_read(data[s]) for s, gg in rows if gg == g], axis=0)
        for g in ("A", "B", "C")
    }
    for a, b in (("A", "B"), ("A", "C"), ("B", "C")):
        np.testing.assert_allclose(
            _read(out / f"difference_{a}_minus_{b}.nii.gz"),
            mean[a] - mean[b],
            atol=1e-6,
        )
    assert _result(events)["differences"] == ["A - B", "A - C", "B - C"]
    assert len([p for p in out.iterdir() if p.name.startswith("difference_")]) == 3
    _check_written(out, events)


def test_subject_space_reads_the_subject_file_not_the_mni_decoy(project, tmp_path):
    config = _fixture_config("subject-space")
    subject_data = {}
    for k, row in enumerate(config["subjects"]):
        sid, sim = row["subject_id"], row["simulation_name"]
        folder = _niftis(project, sid, sim)
        subject_data[sid] = _write(
            folder / SUBJECT_FILE.format(sim=sim), _volume(20 + k)
        )
        _write(folder / MNI_FILE.format(sim=sim), _volume(20 + k) + 100.0)  # decoy

    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = Path(_result(events)["output_dir"])
    for row in config["subjects"]:
        np.testing.assert_allclose(
            _read(out / f"average_{row['group']}.nii.gz"),
            _read(subject_data[row["subject_id"]]),
            rtol=1e-6,
        )
    recorded = json.loads((out / "config.json").read_text())
    assert recorded["space"] == "subject"
    assert (
        recorded["nifti_file_pattern"]
        == "grey_{simulation_name}_TI_subject_TI_max.nii.gz"
    )


def test_an_mti_simulation_is_read_from_mti_niftis(project, tmp_path):
    config = _fixture_config("mni-space")
    first, second = config["subjects"]
    sim = second["simulation_name"]
    _write(
        _niftis(project, first["subject_id"], sim) / MNI_FILE.format(sim=sim),
        _volume(1),
    )
    mti_root = _niftis(project, second["subject_id"], sim, mti=True).parent
    (mti_root / "mesh").mkdir()
    mti_file = _write(
        mti_root / "niftis" / f"grey_{sim}_mTI_MNI_MNI_mTI_max.nii.gz", _volume(2)
    )
    _write(
        _niftis(project, second["subject_id"], sim) / MNI_FILE.format(sim=sim),
        _volume(2) + 100.0,  # a 2-pair file the mTI run never wrote
    )

    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = Path(_result(events)["output_dir"])
    np.testing.assert_allclose(
        _read(out / f"average_{second['group']}.nii.gz"), _read(mti_file), rtol=1e-6
    )


def test_one_group_on_two_grids_fails_naming_the_second_subject(project, tmp_path):
    config = _fixture_config("single-group")
    first, second = config["subjects"]
    sim = first["simulation_name"]
    _write(
        _niftis(project, first["subject_id"], sim) / SUBJECT_FILE.format(sim=sim),
        _volume(3),
    )
    _write(
        _niftis(project, second["subject_id"], sim) / SUBJECT_FILE.format(sim=sim),
        _volume(4, shape=(6, 6, 7, 1)),
    )
    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 1
    result = _result(events)
    assert result["success"] is False
    assert f"Subject {second['subject_id']} " in result["error"]
    assert [e["code"] for e in events if e["type"] == "exit"] == [1]


def test_a_missing_file_fails_with_the_path_preflight_reports(project, tmp_path):
    from tit.jobs.preflight import preflight

    config = _fixture_config("mni-space")
    first, second = config["subjects"]
    sim = first["simulation_name"]
    _write(
        _niftis(project, first["subject_id"], sim) / MNI_FILE.format(sim=sim),
        _volume(5),
    )

    (missing,) = preflight("nifti_average", config, str(project))
    expected = (
        project
        / "derivatives"
        / "SimNIBS"
        / f"sub-{second['subject_id']}"
        / "Simulations"
        / sim
        / "TI"
        / "niftis"
        / MNI_FILE.format(sim=sim)
    )
    assert missing.expected_path == str(expected)

    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 1
    error = _result(events)["error"]
    assert error.startswith(f"NIfTI file not found: {missing.expected_path}")


_SHIFTED = AFFINE.copy()
_SHIFTED[:3, 3] += 10.0
#: The second group's grid: the same shape 10 mm away, or one more voxel along x.
OTHER_GRIDS = {
    "shifted-affine": (SHAPE, _SHIFTED),
    "other-shape": ((6, 6, 7, 1), AFFINE),
}


@pytest.mark.xfail(
    strict=True,
    reason="load_grouped_subjects_ti_toolbox checks the grid within a group only; "
    "tit/stats/nifti.py is owned elsewhere",
)
@pytest.mark.parametrize("grid", sorted(OTHER_GRIDS))
def test_two_groups_on_different_grids_fail_naming_the_subject(project, tmp_path, grid):
    config = _fixture_config("subject-space")  # Group1: one subject, Group2: another
    first, second = config["subjects"]
    assert first["group"] != second["group"]
    sim = first["simulation_name"]
    shape, affine = OTHER_GRIDS[grid]
    _write(
        _niftis(project, first["subject_id"], sim) / SUBJECT_FILE.format(sim=sim),
        _volume(6),
    )
    _write(
        _niftis(project, second["subject_id"], sim) / SUBJECT_FILE.format(sim=sim),
        _volume(7, shape=shape),
        affine,
    )
    proc, events = _run(project, config, tmp_path)
    assert proc.returncode == 1
    result = _result(events)
    assert result["success"] is False
    assert f"Subject {second['subject_id']} " in result["error"]
