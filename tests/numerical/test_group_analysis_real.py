"""Group analysis with the real pandas and matplotlib: honest summaries, own folders, own logs (2026-10-22).

What this pins
    1. ``group_summary.csv`` of three voxel subjects has one row per subject and an AVERAGE
       row equal to the arithmetic mean of the subjects' own ``results.csv`` values (read
       back from each subject's analysis folder, averaged here).
    2. A voxel analysis has no normal component: its ``Normal_*`` cells are empty, not
       ``0.000``, and the comparison PDF has no "Normal Mean" panel. Its simulation saved
       ``hf_peak`` equal to ``TI_max``, so ``TI_Selectivity`` is exactly 1.
    3. A mesh group where one subject has no normal mesh: that subject's ``Normal_*`` cells
       are empty and the AVERAGE is the mean of the subjects that have them (not dragged
       down by a 0), and the PDF keeps the Normal Mean panel.
    4. A one-subject group's AVERAGE is that subject.
    5. Two runs of the same analysis started in the same second (``time.strftime`` frozen)
       write two folders, both named by the simulation, space, target, field and tissue.
    6. Each subject's analyzer log holds its own analysis only: no "Analyzing subject <next>"
       line (each Analyzer added a file handler that was never removed).

Where the numbers come from
    Authored NIfTI fields (values below) and the per-subject results.csv files the same run
    wrote, averaged with ``statistics.fmean``; the summary is written with ``%.3f``, so the
    comparison tolerance is half its last digit. Mesh normal statistics are authored
    ``AnalysisResult`` values.

Run (in the image; pandas and matplotlib are real there, and the runs happen in a
subprocess because tests/conftest.py mocks pandas in-process)::

    simnibs_python -m pytest tests/numerical/test_group_analysis_real.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SIM = "M1"
SUBJECTS = ("101", "102", "103")
CENTER, RADIUS = (9.0, 9.0, 9.0), 4.0
STAMP = "20261022_010203"

_SCRIPT = r"""
import json, sys, time
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
time.strftime = lambda fmt, *a: __import__("os").environ["P33_STAMP"]

from tit.paths import get_path_manager
get_path_manager(str(root))
from tit.analyzer import group
from tit.analyzer.analyzer import AnalysisResult

titles = []
real_savefig = group.plt.savefig
def savefig(path, *a, **k):
    titles.append([ax.get_title() for ax in group.plt.gcf().axes])
    return real_savefig(path, *a, **k)
group.plt.savefig = savefig

out = {}
if mode == "voxel":
    runs = []
    for subjects in (["101", "102", "103"], ["101", "102", "103"], ["101"]):
        res = group.run_group_analysis(
            subject_ids=subjects, simulation="M1", space="voxel", tissue_type="WM",
            analysis_type="spherical", center=(9.0, 9.0, 9.0), radius=4.0,
            coordinate_space="subject", field="TI_max",
        )
        runs.append({"csv": str(res.summary_csv_path), "pdf": str(res.comparison_plot_path)})
    out["runs"] = runs
else:
    def result(normal):
        return AnalysisResult(
            field_name="TI_max", region_name="r", space="mesh", analysis_type="cortical",
            roi_mean=0.2, roi_max=0.4, roi_min=0.1, roi_focality=1.5, gm_mean=0.1, gm_max=0.9,
            normal_mean=normal, normal_max=None if normal is None else 2 * normal,
            normal_focality=None if normal is None else 1.25,
        )
    df = group._build_summary_df({"101": result(0.3), "102": result(None), "103": result(0.5)})
    path = root / "mesh_summary.csv"
    df.to_csv(path, index=False, float_format="%.3f")
    group._generate_comparison_plot(df, root)
    out["csv"] = str(path)
    out["pdf"] = str(root / "group_comparison.pdf")
out["titles"] = titles
print("RESULT " + json.dumps(out))
"""


def _run(root: Path, mode: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(REPO), "P33_STAMP": STAMP}
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(root), mode],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    text = done.stdout + done.stderr
    if "No module named 'pandas'" in text or "No module named 'matplotlib'" in text:
        pytest.skip("skipping: needs real pandas and matplotlib (run in the image)")
    assert done.returncode == 0, text
    line = next(l for l in done.stdout.splitlines() if l.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _project(tmp_path: Path) -> Path:
    """Three voxel subjects: 10^3 grids of 2 mm voxels, a different field each."""
    import nibabel as nib

    project = tmp_path / "project"
    for k, sid in enumerate(SUBJECTS):
        base = project / "derivatives" / "SimNIBS" / f"sub-{sid}"
        niftis = base / "Simulations" / SIM / "TI" / "niftis"
        niftis.mkdir(parents=True)
        m2m = base / f"m2m_{sid}"
        m2m.mkdir(parents=True)
        (m2m / f"{sid}.msh").write_bytes(b"")
        field = np.zeros((10, 10, 10), dtype=np.float32)
        field[2:8, 2:8, 2:8] = np.linspace(0.1, 1.0, 216).reshape(6, 6, 6) * (k + 1)
        affine = np.diag([2.0, 2.0, 2.0, 1.0])
        # The default fields, so the analyses have nothing to produce on demand.
        for prefix in ("grey_", "white_"):
            for name in ("TI_max", "hf_peak", "hf_sar"):
                nib.save(
                    nib.Nifti1Image(field, affine),
                    str(niftis / f"{prefix}{SIM}_TI_subject_{name}.nii"),
                )
    return project


def _rows(path: Path) -> dict[str, dict[str, str]]:
    with open(path, newline="") as fh:
        return {row["Subject"]: row for row in csv.DictReader(fh)}


def _subject_results(project: Path, sid: str) -> dict[str, float]:
    analyses = project / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / SIM
    (path,) = list((analyses / "Analyses").rglob("results.csv"))
    with open(path, newline="") as fh:
        rows = {r[0]: r[1] for r in csv.reader(fh) if r and r[0] != "Metric"}
    return {
        "ROI_Mean": float(rows["roi_mean"]),
        "ROI_Max": float(rows["roi_max"]),
        "ROI_Min": float(rows["roi_min"]),
        "ROI_Focality": float(rows["roi_focality"]),
        "GM_Mean": float(rows["gm_mean"]),
        "GM_Max": float(rows["gm_max"]),
    }


def _is_pdf(path: Path) -> bool:
    data = path.read_bytes()
    return data.startswith(b"%PDF") and b"%%EOF" in data[-1024:]


@pytest.fixture(scope="module")
def voxel_runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("group")
    project = _project(tmp)
    return project, _run(project, "voxel")


def test_average_row_is_the_mean_of_each_subjects_own_results(voxel_runs) -> None:
    project, out = voxel_runs
    rows = _rows(Path(out["runs"][0]["csv"]))
    assert list(rows) == [*SUBJECTS, "AVERAGE"]
    per_subject = {sid: _subject_results(project, sid) for sid in SUBJECTS}
    for key in per_subject[SUBJECTS[0]]:
        values = [per_subject[sid][key] for sid in SUBJECTS]
        for sid, value in zip(SUBJECTS, values):
            assert float(rows[sid][key]) == pytest.approx(value, abs=5e-4), (sid, key)
        assert float(rows["AVERAGE"][key]) == pytest.approx(
            statistics.fmean(values), abs=5e-4
        ), key
    # The three authored fields differ, so the average is not any one subject's value.
    assert len({rows[sid]["ROI_Mean"] for sid in SUBJECTS}) == 3


def test_voxel_normal_cells_are_empty_and_the_pdf_has_no_normal_panel(
    voxel_runs,
) -> None:
    _, out = voxel_runs
    rows = _rows(Path(out["runs"][0]["csv"]))
    for row in rows.values():
        assert (row["Normal_Mean"], row["Normal_Max"], row["Normal_Focality"]) == (
            "",
            "",
            "",
        )
        # The fixture's hf_peak is its TI_max field, so the two focalities are one ratio.
        assert row["TI_Selectivity"] == "1.000"
    pdf = Path(out["runs"][0]["pdf"])
    assert _is_pdf(pdf)
    titles = out["titles"][0]
    assert sorted(t for t in titles if t) == [
        "ROI Focality",
        "ROI Max (V/m)",
        "ROI Mean (V/m)",
    ]


def test_one_subject_average_is_that_subject(voxel_runs) -> None:
    project, out = voxel_runs
    rows = _rows(Path(out["runs"][2]["csv"]))
    assert list(rows) == ["101", "AVERAGE"]
    own = _subject_results(project, "101")
    for key, value in own.items():
        assert float(rows["AVERAGE"][key]) == pytest.approx(value, abs=5e-4)


def test_same_second_runs_get_their_own_folders_named_by_what_they_analysed(
    voxel_runs,
) -> None:
    _, out = voxel_runs
    first, second = (Path(r["csv"]).parent for r in out["runs"][:2])
    assert first != second
    assert first.parent == second.parent
    assert first.name.endswith(STAMP) and second.name.endswith(f"{STAMP}_2")
    for folder in (first, second):
        # simulation, space, target (centre and radius), tissue: the inputs of the run
        name = folder.name
        assert name.startswith(f"{SIM}_voxel_sphere_x9.00_y9.00_z9.00_r4.0_")
        assert "_WM_" in name
        assert (folder / "group_summary.csv").is_file()


def test_each_subject_log_holds_only_its_own_analysis(voxel_runs) -> None:
    project, _ = voxel_runs
    logs = project / "derivatives" / "ti-toolbox" / "logs"
    for k, sid in enumerate(SUBJECTS):
        files = sorted((logs / f"sub-{sid}").glob("analyzer_*.log"))
        assert files, f"sub-{sid} has an analyzer log"
        text = "".join(f.read_text() for f in files)
        assert f"subject={sid}" in text
        for other in SUBJECTS[k + 1 :]:
            assert f"Analyzing subject {other}" not in text, (sid, other)
            assert f"subject={other}" not in text, (sid, other)


def test_mesh_subject_without_normals_is_left_out_of_the_normal_average(
    tmp_path,
) -> None:
    out = _run(tmp_path, "mesh")
    rows = _rows(Path(out["csv"]))
    assert rows["102"]["Normal_Mean"] == ""
    assert float(rows["AVERAGE"]["Normal_Mean"]) == pytest.approx(
        statistics.fmean([0.3, 0.5]), abs=5e-4
    )
    assert float(rows["AVERAGE"]["Normal_Max"]) == pytest.approx(
        statistics.fmean([0.6, 1.0]), abs=5e-4
    )
    assert float(rows["AVERAGE"]["ROI_Mean"]) == pytest.approx(0.2, abs=5e-4)
    assert _is_pdf(Path(out["pdf"]))
    assert "ROI Normal Mean (V/m)" in out["titles"][0]
