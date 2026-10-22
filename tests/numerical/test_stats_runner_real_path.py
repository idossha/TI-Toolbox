"""A stats job's real path: desktop config -> ``python -m tit.stats`` -> files -> Results detail (p23).

Each run is the job runner as the server starts it: a subprocess on the JSON config the desktop
builders emit (``tests/fixtures/desktop_configs/panels-stats``: every key as sent, with the rows
swapped for a 3-vs-3 design or a 6-subject correlation, 19 permutations and one worker), plus
the ``project_dir`` envelope and ``TIT_EVENTS_FILE``. The subjects are real NIfTI files on a
shared grid, with a zero outer shell (no field there) and one planted 3x3x3 block.

Pins, for both modes and both cluster statistics:

* the folder written is the ``/api/plan/stats`` ``output_dir``, the documented
  ``derivatives/ti-toolbox/stats/<mode>/<analysis_name>``, and the name in the job's lock key
  (``tit.jobs.locks.keys_for``);
* the files are the mode's entries of ``catalog._STATS_FILE_LABELS`` plus one run log, and are
  exactly the runner's artifact events; the correlation's ``permutation_details.txt`` lists 19
  permutations;
* ``difference_map`` equals the responders' mean minus the non-responders' (``np.mean`` over the
  input files read back here); ``pvalues_map`` (``-log10 p``) lies in ``[-1e-9, 10]`` and is 0 in
  the zero shell, where nothing can be tested; the significant-voxel mask is 0/1 and inside the
  testable region;
* ``catalog.group_stats_detail`` reads status ``ok``, the groups with their exact subject ids,
  and "Significant clusters" equal to the result event's count; for a mass run "Cluster
  threshold" equals the summary's threshold line.

Known gap, xfail(strict): for a size run the catalog shows no "Cluster threshold" -- its log
regex wants "<value> <word> units" and the engine logs "12.00 voxels" (``tit/catalog.py``,
owned elsewhere).

Run (container): ``simnibs_python -m pytest tests/numerical/test_stats_runner_real_path.py -q``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "desktop_configs" / "panels-stats"
SHAPE = (8, 8, 8, 1)
AFFINE = np.diag([-2.0, 2.0, 2.0, 1.0])
AFFINE[:3, 3] = [90.0, -126.0, -72.0]
BLOCK = (slice(2, 5), slice(2, 5), slice(2, 5))
EFFECTS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

#: The ``_STATS_FILE_LABELS`` entries each volume runner writes when clusters form (its
#: docstring's output list); the run log ``<mode>_analysis_<ts>.log`` comes on top.
EXPECTED = {
    "group_comparison": {
        "average_responders.nii.gz",
        "average_non_responders.nii.gz",
        "difference_map.nii.gz",
        "pvalues_map.nii.gz",
        "significant_voxels_mask.nii.gz",
        "permutation_null_distribution.pdf",
        "cluster_size_mass_correlation.pdf",
        "analysis_summary.txt",
        "permutation_details.txt",
    },
    "correlation": {
        "correlation_map.nii.gz",
        "correlation_map_thresholded.nii.gz",
        "t_statistics_map.nii.gz",
        "pvalues_map.nii.gz",
        "significant_voxels_mask.nii.gz",
        "average_efield.nii.gz",
        "permutation_null_distribution.pdf",
        "cluster_size_mass_correlation.pdf",
        "analysis_summary.txt",
        "permutation_details.txt",
    },
}
RUNS = [(m, s) for m in ("group_comparison", "correlation") for s in ("mass", "size")]


def _volume(rng: np.random.Generator, block_value: float | None) -> np.ndarray:
    data = np.zeros(SHAPE)
    data[1:7, 1:7, 1:7, 0] = 0.1 + 0.05 * rng.random((6, 6, 6))
    if block_value is not None:
        data[BLOCK + (0,)] = block_value + 0.02 * rng.random((3, 3, 3))
    return data


def _write(project: Path, sid: str, data: np.ndarray) -> Path:
    import nibabel as nib

    folder = project / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / "M1"
    folder = folder / "TI" / "niftis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "grey_M1_TI_MNI_MNI_TI_max.nii.gz"
    nib.save(nib.Nifti1Image(data.astype(np.float32), AFFINE), str(path))
    return path


def _read(path: Path) -> np.ndarray:
    import nibabel as nib

    return np.squeeze(np.asarray(nib.load(str(path)).get_fdata(), dtype=np.float64))


def _config(mode: str, stat: str) -> tuple[dict, dict[str, float]]:
    """The desktop-built config with this run's rows; returns (config, value-by-subject)."""
    fixture = (
        "classification-2-groups"
        if mode == "group_comparison"
        else "correlation-3-rows"
    )
    (job,) = json.loads((CORPUS / f"{fixture}.json").read_text())["jobs"]
    config = dict(job["config"])
    ids = [f"{i:03d}" for i in range(1, 7)]
    if mode == "group_comparison":
        config["subjects"] = [
            {"subject_id": s, "simulation_name": "M1", "response": int(i < 3)}
            for i, s in enumerate(ids)
        ]
        block = {s: (1.0 if i < 3 else None) for i, s in enumerate(ids)}
    else:
        config["subjects"] = [
            {"subject_id": s, "simulation_name": "M1", "effect_size": e, "weight": 1}
            for s, e in zip(ids, EFFECTS)
        ]
        block = {s: 0.2 * e for s, e in zip(ids, EFFECTS)}
    config.update(
        analysis_name=f"real_{mode}_{stat}",
        cluster_stat=stat,
        n_permutations=19,
        n_jobs=1,
    )
    return config, block


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Run each (mode, statistic) once on its own project; cache what the tests read."""
    cache: dict = {}

    def get(mode: str, stat: str) -> dict:
        if (mode, stat) in cache:
            return cache[(mode, stat)]
        root = tmp_path_factory.mktemp(f"{mode}_{stat}")
        project = root / "project"
        project.mkdir()
        (project / "dataset_description.json").write_text("{}")
        config, block = _config(mode, stat)
        rng = np.random.default_rng(20261022)
        inputs = {s: _write(project, s, _volume(rng, v)) for s, v in block.items()}
        cfg = root / "stats.json"
        cfg.write_text(json.dumps({**config, "project_dir": str(project)}))
        events_file = root / "events.jsonl"
        env = {
            **os.environ,
            "TIT_EVENTS_FILE": str(events_file),
            "PYTHONPATH": str(REPO),
            "TIT_NO_TELEMETRY": "1",
        }
        env.pop("TIT_JOB_ID", None)
        proc = subprocess.run(
            [sys.executable, "-m", "tit.stats", str(cfg)],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        events = [json.loads(line) for line in events_file.read_text().splitlines()]
        cache[(mode, stat)] = {
            "proc": proc,
            "events": events,
            "project": project,
            "config": config,
            "inputs": inputs,
        }
        return cache[(mode, stat)]

    return get


def _result(run: dict) -> dict:
    (result,) = [e for e in run["events"] if e["type"] == "result"]
    return result["outputs"]


@pytest.mark.parametrize("mode,stat", RUNS)
def test_the_runner_writes_the_planned_folder_and_the_modes_files(runs, mode, stat):
    from tit.catalog import _STATS_FILE_LABELS
    from tit.jobs.locks import keys_for
    from tit.paths import get_path_manager
    from tit.server.routes.plan import PlanRequest, plan

    run = runs(mode, stat)
    assert run["proc"].returncode == 0, run["proc"].stderr[-3000:]
    result = _result(run)
    assert result["success"] is True
    out = Path(result["output_dir"])
    name = run["config"]["analysis_name"]
    assert out == run["project"] / "derivatives" / "ti-toolbox" / "stats" / mode / name

    get_path_manager(str(run["project"]))
    (job,) = plan("stats", PlanRequest(config=run["config"], subject_ids=[])).jobs
    assert job.output_dir == str(out)
    write_keys = [
        r.resource for r in keys_for("stats", [], run["config"]) if r.mode == "write"
    ]
    assert write_keys == [f"project:stats:{mode}/{name}"]

    on_disk = set(os.listdir(out))
    logs = {
        n for n in on_disk if re.fullmatch(rf"{mode}_analysis_\d{{8}}_\d{{6}}\.log", n)
    }
    assert len(logs) == 1
    assert EXPECTED[mode] <= set(_STATS_FILE_LABELS)
    assert on_disk - logs == EXPECTED[mode]
    artifacts = {e["path"] for e in run["events"] if e["type"] == "artifact"}
    assert artifacts == {str(out / n) for n in on_disk}

    if mode == "correlation":
        lines = (out / "permutation_details.txt").read_text().splitlines()
        assert len([ln for ln in lines if ln.startswith("Permutation ")]) == 19


@pytest.mark.parametrize("mode,stat", RUNS)
def test_maps_are_right_where_the_field_is_and_silent_where_it_is_not(runs, mode, stat):
    run = runs(mode, stat)
    out = Path(_result(run)["output_dir"])
    testable = np.zeros(SHAPE[:3], dtype=bool)
    testable[1:7, 1:7, 1:7] = True  # the zero shell holds no field in any subject

    log_p = _read(out / "pvalues_map.nii.gz")
    assert log_p.min() >= -1e-9 and log_p.max() <= 10
    assert np.all(log_p[~testable] == 0)
    sig = _read(out / "significant_voxels_mask.nii.gz")
    assert set(np.unique(sig)) <= {0.0, 1.0}
    assert not np.any(sig[~testable])

    if mode == "group_comparison":
        rows = run["config"]["subjects"]
        resp = [
            _read(run["inputs"][r["subject_id"]]) for r in rows if r["response"] == 1
        ]
        non = [
            _read(run["inputs"][r["subject_id"]]) for r in rows if r["response"] == 0
        ]
        np.testing.assert_allclose(
            _read(out / "difference_map.nii.gz"),
            np.mean(resp, axis=0) - np.mean(non, axis=0),
            atol=1e-6,
        )


@pytest.mark.parametrize("mode,stat", RUNS)
def test_the_results_detail_reads_what_the_run_reported(runs, mode, stat):
    from tit.catalog import group_stats_detail
    from tit.paths import get_path_manager

    run = runs(mode, stat)
    config = run["config"]
    detail = group_stats_detail(
        get_path_manager(str(run["project"])), mode, config["analysis_name"]
    )
    assert detail["status"] == "ok"
    rows = config["subjects"]
    if mode == "group_comparison":
        expected_groups = [
            (
                config["group1_name"],
                [r["subject_id"] for r in rows if r["response"] == 1],
            ),
            (
                config["group2_name"],
                [r["subject_id"] for r in rows if r["response"] == 0],
            ),
        ]
    else:
        expected_groups = [("subjects", [r["subject_id"] for r in rows])]
    assert [(g["name"], g["subjects"]) for g in detail["groups"]] == expected_groups
    assert [g["n"] for g in detail["groups"]] == [
        len(ids) for _, ids in expected_groups
    ]
    results = {r["label"]: r["value"] for r in detail["results"]}
    assert (
        int(results["Significant clusters"]) == _result(run)["n_significant_clusters"]
    )


@pytest.mark.parametrize(
    "mode,stat",
    [
        pytest.param(
            m,
            s,
            marks=(
                [
                    pytest.mark.xfail(
                        strict=True,
                        reason="catalog log regex misses a size run's threshold line "
                        "('12.00 voxels', no 'units'); tit/catalog.py is owned elsewhere",
                    )
                ]
                if s == "size"
                else []
            ),
        )
        for m, s in RUNS
    ],
)
def test_the_results_detail_shows_the_summarys_cluster_threshold(runs, mode, stat):
    from tit.catalog import group_stats_detail
    from tit.paths import get_path_manager

    run = runs(mode, stat)
    out = Path(_result(run)["output_dir"])
    summary = (out / "analysis_summary.txt").read_text()
    match = re.search(r"Cluster (?:mass|size) threshold: ([-\d.]+)", summary)
    assert match, summary
    detail = group_stats_detail(
        get_path_manager(str(run["project"])), mode, run["config"]["analysis_name"]
    )
    results = {r["label"]: r["value"] for r in detail["results"]}
    assert float(results["Cluster threshold"]) == pytest.approx(
        float(match.group(1)), abs=0.06
    )
