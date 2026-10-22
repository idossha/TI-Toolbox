"""Nilearn Visuals on Dataset 000, end to end: the right average, cutoffs and non-blank figures.

Pins, 2026-10-22. ``tit.plotting.nilearn.__main__.main`` is run, as the job runs it, on a
config averaging the ``L_Insula`` MNI grey-matter ``TI_max`` fields of sub-101 and sub-LA
(Dataset 000, read through symlinks; both on the 182x218x182 1 mm MNI grid), with the network
blocked. Then:

1. it exits 0 and every file it writes is in the folder ``/api/plan/nilearn`` names
   (``tit.server.routes.plan._plan_nilearn``): the averaged NIfTI, the parameters file, the
   multi-slice PDF and the glass-brain PDF;
2. the averaged NIfTI equals ``numpy.mean`` of the two inputs read here with nibabel;
3. the parameters file's cutoff line is the 95th / 99.9th percentile of that independent
   mean's non-zero voxels (the config's documented data-driven default), and
   p95 < p99.9 <= peak;
4. the slice figure is not blank where the data says it cannot be: for each of its 21 panels,
   the panel's own cut (``display.cut_coords``, mapped to a voxel index through the inverse
   affine) is checked against the mean. A panel whose slice -- and both neighbours, so
   nilearn's rounding of the cut cannot matter -- holds voxels in the middle of the colour
   range (35-75 % between the cutoffs, where matplotlib's ``hot`` is pure red to yellow) must
   draw "hot" pixels (R > 200, B < 80); a panel with no voxel at or above the minimum cutoff
   in those slices must draw none. At least one panel of each kind is required.
   The hot band is read off matplotlib's ``hot`` segment data (R reaches 1 at 0.365, B starts
   at 0.746) -- the test's own arithmetic, not the renderer's;
5. the glass-brain PDF is larger than a blank baseline: the same call with both cutoffs above
   the field's peak;
6. a ``min_cutoff`` above the peak logs the blank-figure warning naming the peak;
7. with the image's bundled atlases (``/opt/nilearn_data``) the outlines load offline; when
   the image predates them (idossha/ti-toolbox:v3.1.1) that check skips with a reason, and
   the job is shown to succeed without outlines instead.

The dataset is never written: the mtimes of the files read are compared before and after.

Why a subprocess: ``tests/conftest.py`` mocks nilearn, pandas, joblib and sklearn in this
interpreter, and real nilearn imports real pandas. Swapping pandas in and out of
``sys.modules`` here broke every later module that imports real pandas
(``test_stats_csv_loaders.py``: "the dtype str is not supported for parsing", from a second
import of its C extensions). So the job runs in ``simnibs_python -c`` (``_SCRIPT``), which
writes the slice figure's raw pixels, each panel's cut and axes boxes, and its log; this
module computes every expected value itself (nibabel and numpy only) and asserts on those.

Real libraries (nilearn, matplotlib, nibabel), so this runs in the image only:
``docker run --rm -v <tree>:/ti-toolbox -w /ti-toolbox -v <dataset000>:/data/000:ro
-e TIT_DATASET_000=/data/000 idossha/ti-toolbox:<tag> -lc 'simnibs_python -m pytest
tests/numerical/test_nilearn_render_realdata.py -q -p no:cacheprovider'``.
Deliberately elsewhere: averaging on synthetic grids (``test_nilearn_group_average.py``), the
colourbar label precision (``tests/test_nilearn_colorbar_precision.py``).
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

ROOT = Path(__file__).resolve().parents[2]
_DATASET = os.environ.get("TIT_DATASET_000", "")
_SIM = "L_Insula"
_SUBJECTS = ("101", "LA")
_FILE = f"grey_{_SIM}_TI_MNI_MNI_TI_max.nii.gz"


def _source(sid: str) -> Path:
    return (
        Path(_DATASET)
        / "derivatives/SimNIBS"
        / f"sub-{sid}"
        / "Simulations"
        / _SIM
        / "TI/niftis"
        / _FILE
    )


_SKIP = not _DATASET or not all(_source(s).is_file() for s in _SUBJECTS)
pytestmark = pytest.mark.skipif(
    _SKIP,
    reason="skipping: TIT_DATASET_000 unset or without the sub-101 / sub-LA L_Insula "
    "MNI grey TI_max NIfTIs",
)

#: The image bakes the outline atlases here (container/blueprint/Dockerfile.ti-toolbox).
_BUNDLED = Path("/opt/nilearn_data")
#: matplotlib's ``hot``: red reaches 1 at 0.365079, blue starts rising at 0.746032.
_HOT_BAND = (0.35, 0.75)

#: Runs one phase of the job with the real stack, network blocked. argv: phase, facts.json,
#: then the phase's own arguments. Prints the job's log; writes the facts as JSON.
_SCRIPT = r"""
import json, socket, sys
from pathlib import Path

def _blocked(*_args, **_kwargs):
    raise OSError("network blocked by test_nilearn_render_realdata")

socket.socket.connect = _blocked
socket.getaddrinfo = _blocked

import matplotlib
matplotlib.use("Agg")
import numpy as np

phase, facts_path, args = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]


def run_main(config_path):
    import tit.plotting.nilearn.__main__ as runner
    sys.argv = ["tit.plotting.nilearn", config_path]
    try:
        runner.main()
    except SystemExit as exc:
        return exc.code
    return "returned without exiting"


facts = {}
if phase == "run":
    from tit.plotting.nilearn import visualizer
    figures, displays = [], []
    real_subplots = visualizer.plt.subplots
    real_plot_stat_map = visualizer.plotting.plot_stat_map

    def subplots(*a, **k):
        fig, axes = real_subplots(*a, **k)
        figures.append(fig)
        return fig, axes

    def plot_stat_map(*a, **k):
        display = real_plot_stat_map(*a, **k)
        displays.append(display)
        return display

    visualizer.plt.subplots = subplots
    visualizer.plt.close = lambda *a, **k: None  # keep the slice figure to read it back
    visualizer.plotting.plot_stat_map = plot_stat_map
    facts["code"] = run_main(args[0])
    facts["figures"] = len(figures)
    facts["panels"] = []
    if figures:
        fig = figures[0]
        fig.canvas.draw()
        rgb = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
        np.save(str(facts_path.with_suffix(".npy")), rgb)
        for display in displays:
            boxes = []
            for cut_axes in display.axes.values():
                box = cut_axes.ax.get_window_extent()
                boxes.append([float(box.x0), float(box.y0), float(box.x1), float(box.y1)])
            facts["panels"].append({
                "slicer": type(display).__name__,
                "cut_coords": [float(c) for c in display.cut_coords],
                "boxes": boxes,
            })
elif phase == "glass_blank":
    import nibabel as nib
    from tit.plotting.nilearn.img_glass import create_glass_brain_entry_point_group
    nifti, out_dir, peak = args[0], args[1], float(args[2])
    facts["path"] = create_glass_brain_entry_point_group(
        nib.load(nifti), "blank", out_dir, min_cutoff=2 * peak, max_cutoff=3 * peak
    )
elif phase == "blank_warning":
    import tit.plotting.nilearn.__main__ as runner

    def no_render(img, base, output_dir, *a, **k):
        path = Path(output_dir) / f"{base}.pdf"
        path.write_bytes(b"%PDF")
        return str(path)

    runner.create_pdf_entry_point_group = no_render
    facts["code"] = run_main(args[0])
else:
    sys.exit(f"unknown phase {phase!r}")
facts_path.write_text(json.dumps(facts))
"""


def _launch(
    phase: str, facts: Path, *args: str, nilearn_data: Path
) -> tuple[dict, str]:
    """Run ``_SCRIPT``'s *phase* in a fresh interpreter; return its facts and its log."""
    env = {
        **os.environ,
        "NILEARN_DATA": str(nilearn_data),
        "MPLBACKEND": "Agg",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, phase, str(facts), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        timeout=900,
    )
    log = done.stdout + done.stderr
    assert done.returncode == 0 and facts.is_file(), f"{phase} crashed:\n{log[-4000:]}"
    return json.loads(facts.read_text()), log


def _mtimes() -> dict[Path, int]:
    out = {}
    for sid in _SUBJECTS:
        src = _source(sid)
        out[src] = src.stat().st_mtime_ns
        out[src.parent] = src.parent.stat().st_mtime_ns
    return out


def _independent_mean() -> tuple[np.ndarray, np.ndarray]:
    """The voxelwise mean of the two inputs, read with nibabel here, and its affine."""
    import nibabel as nib

    imgs = [nib.load(str(_source(s))) for s in _SUBJECTS]
    for img in imgs[1:]:
        assert img.shape == imgs[0].shape
        np.testing.assert_allclose(img.affine, imgs[0].affine)
    mean = np.mean([img.get_fdata(dtype=np.float64) for img in imgs], axis=0)
    return mean, imgs[0].affine


def _project(root: Path) -> Path:
    project = root / "project"
    (project / "derivatives/ti-toolbox").mkdir(parents=True)
    for sid in _SUBJECTS:
        niftis = (
            project / "derivatives/SimNIBS" / f"sub-{sid}" / "Simulations" / _SIM
        ) / "TI/niftis"
        niftis.mkdir(parents=True)
        (niftis / _FILE).symlink_to(_source(sid))
    return project


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


def _pairs() -> list[dict]:
    return [{"subject_id": s, "simulation_name": _SIM} for s in _SUBJECTS]


def _write_config(tmp: Path, project: Path, config: dict) -> str:
    path = tmp / f"{config['subdir_name']}.json"
    path.write_text(json.dumps({"project_dir": str(project), **config}))
    return str(path)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One real run of the Nilearn Visuals job, with its slice figure and log captured."""
    probe = subprocess.run(
        [sys.executable, "-c", "import nilearn.plotting, matplotlib"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        print("skipping: real nilearn is not importable here (run in the image)")
        pytest.skip("real nilearn is not importable here (run in the image)")
    from tit.config_io import deserialize_config
    from tit.paths import get_path_manager, reset_path_manager
    from tit.plotting.nilearn.config import NilearnConfig
    from tit.server.routes.plan import _plan_nilearn

    tmp = tmp_path_factory.mktemp("nilearn_realdata")
    project = _project(tmp)
    before_mtimes = _mtimes()
    config = {
        "subject_simulation_pairs": _pairs(),
        "subdir_name": "insula_realdata",
        "create_glass_brain": True,
    }
    nilearn_data = _BUNDLED if _BUNDLED.is_dir() else tmp / "nilearn_data_empty"
    before = _files(project)
    facts, log = _launch(
        "run",
        tmp / "run.json",
        _write_config(tmp, project, config),
        nilearn_data=nilearn_data,
    )
    written = _files(project) - before
    try:
        pm = get_path_manager(str(project))
        [planned] = _plan_nilearn(
            "nilearn", pm, deserialize_config(NilearnConfig, config)
        )[0]
    finally:
        reset_path_manager()
    return {
        **facts,
        "log": log,
        "rgb": tmp / "run.npy",
        "written": written,
        "planned_dir": Path(planned.output_dir),
        "before_mtimes": before_mtimes,
        "tmp": tmp,
        "project": project,
        "nilearn_data": nilearn_data,
    }


@pytest.fixture(scope="module")
def mean():
    return _independent_mean()


def _cutoffs(data: np.ndarray) -> tuple[float, float, float]:
    nonzero = data[data > 0]
    return (
        float(np.percentile(nonzero, 95.0)),
        float(np.percentile(nonzero, 99.9)),
        float(nonzero.max()),
    )


def test_the_job_succeeds_and_writes_only_into_the_planned_folder(run):
    assert run["code"] == 0, run["log"][-3000:]
    base = "group_averaged_2_subjects"
    assert {p.name for p in run["written"]} == {
        f"{base}.nii.gz",
        f"{base}_parameters.txt",
        f"{base}_multiple_views.pdf",
        f"{base}_glass_brain.pdf",
    }
    assert {p.parent for p in run["written"]} == {run["planned_dir"]}
    assert run["planned_dir"] == (
        run["project"] / "derivatives/ti-toolbox/nilearn_visuals/insula_realdata"
    )


def test_the_dataset_was_not_written(run):
    assert _mtimes() == run["before_mtimes"]


def test_the_average_is_the_voxelwise_mean_of_the_two_fields(run, mean):
    import nibabel as nib

    data, affine = mean
    out = nib.load(str(run["planned_dir"] / "group_averaged_2_subjects.nii.gz"))
    assert out.shape == data.shape
    np.testing.assert_allclose(out.affine, affine)
    # Saved with the first input's float32 header: float32 rounding is the tolerance.
    np.testing.assert_allclose(out.get_fdata(), data, rtol=2e-7, atol=1e-9)


def test_the_parameters_file_states_the_data_driven_cutoffs(run, mean):
    p95, p999, peak = _cutoffs(mean[0])
    assert p95 < p999 <= peak
    text = (run["planned_dir"] / "group_averaged_2_subjects_parameters.txt").read_text()
    assert f"Cutoff range: {p95:.4f} - {p999:.4f} V/m" in text
    assert "101: L_Insula" in text and "LA: L_Insula" in text


def _hot_pixels(rgb: np.ndarray, boxes: list[list[float]]) -> int:
    """Pixels inside *boxes* (display coordinates) that ``hot`` paints red to yellow."""
    height = rgb.shape[0]
    total = 0
    for x0, y0, x1, y1 in boxes:
        rows = slice(max(0, int(height - y1)), int(np.ceil(height - y0)))
        cols = slice(max(0, int(x0)), int(np.ceil(x1)))
        crop = rgb[rows, cols].astype(int)
        total += int(np.count_nonzero((crop[..., 0] > 200) & (crop[..., 2] < 80)))
    return total


def _slab(data: np.ndarray, affine: np.ndarray, mode: str, coord: float) -> np.ndarray:
    """The voxels of the slice nearest *coord* (MNI mm) and both neighbours."""
    axis = "xyz".index(mode)
    point = np.zeros(4)
    point[axis], point[3] = coord, 1.0
    index = int(round((np.linalg.inv(affine) @ point)[axis]))
    lo, hi = max(0, index - 1), min(data.shape[axis], index + 2)
    if lo >= hi:
        return np.zeros((3, 0))
    return np.moveaxis(np.take(data, range(lo, hi), axis=axis), axis, 0)


def test_every_panel_draws_the_field_where_the_data_has_it(run, mean):
    data, affine = mean
    data = data.reshape(data.shape[:3])
    p95, p999, _ = _cutoffs(data)
    band = (p95 + _HOT_BAND[0] * (p999 - p95), p95 + _HOT_BAND[1] * (p999 - p95))
    assert run["figures"] == 1, run["log"][-3000:]
    panels = run["panels"]
    assert len(panels) == 21
    rgb = np.load(run["rgb"])

    lit, dark = [], []
    for panel in panels:
        mode = panel["slicer"][0].lower()  # XSlicer / YSlicer / ZSlicer
        assert mode in "xyz", panel["slicer"]
        [coord] = panel["cut_coords"]
        slab = _slab(data, affine, mode, coord)
        hot = _hot_pixels(rgb, panel["boxes"])
        in_band = [
            bool(((s >= band[0]) & (s <= band[1])).any()) for s in slab
        ]  # one per slice of the slab
        if len(in_band) == 3 and all(in_band):
            lit.append((mode, coord))
            assert hot > 0, f"{mode}={coord}: field in the hot band but no hot pixels"
        elif not (slab >= p95).any():
            dark.append((mode, coord))
            assert hot == 0, f"{mode}={coord}: {hot} hot pixels with no voxel >= min"
    assert lit, "no panel has field in the hot band: nothing was checked"
    assert dark, "no panel is outside the field: the blank side was not checked"


def test_the_glass_brain_shows_more_than_a_blank_render(run, mean):
    _, _, peak = _cutoffs(mean[0])
    out_dir = run["tmp"] / "glass_blank"
    out_dir.mkdir()
    facts, log = _launch(
        "glass_blank",
        run["tmp"] / "glass_blank.json",
        str(run["planned_dir"] / "group_averaged_2_subjects.nii.gz"),
        str(out_dir),
        repr(peak),
        nilearn_data=run["nilearn_data"],
    )
    blank = Path(facts["path"])
    assert blank.parent == out_dir, log[-2000:]
    real = run["planned_dir"] / "group_averaged_2_subjects_glass_brain.pdf"
    assert os.path.getsize(real) > os.path.getsize(blank) > 0


def test_a_min_cutoff_above_the_peak_logs_the_blank_figure_warning(run, mean, tmp_path):
    _, _, peak = _cutoffs(mean[0])
    config = {
        "subject_simulation_pairs": _pairs(),
        "subdir_name": "insula_blank",
        "min_cutoff": round(1.5 * peak, 4),
        "max_cutoff": round(2.0 * peak, 4),
        "create_glass_brain": False,
    }
    facts, log = _launch(
        "blank_warning",
        tmp_path / "blank_warning.json",
        _write_config(tmp_path, run["project"], config),
        nilearn_data=run["nilearn_data"],
    )
    assert facts["code"] == 0, log[-2000:]
    warning = re.search(
        r"min_cutoff (\S+) V/m is at or above the field's peak (\S+) V/m", log
    )
    assert warning, log[-2000:]
    assert float(warning.group(1)) == pytest.approx(config["min_cutoff"], abs=5e-5)
    assert float(warning.group(2)) == pytest.approx(peak, abs=5e-5)


@pytest.mark.skipif(
    not _BUNDLED.is_dir(),
    reason="skipping: this image predates the bundled nilearn atlases (/opt/nilearn_data)",
)
def test_the_atlas_outlines_load_offline_from_the_bundled_cache(run):
    assert "Atlas contours skipped" not in run["log"]
    assert "Loading Harvard-Oxford subcortical atlas" in run["log"]


@pytest.mark.skipif(
    _BUNDLED.is_dir(), reason="skipping: the bundled atlases exist, see the test above"
)
def test_without_the_bundled_atlases_the_job_still_draws_and_says_why(run):
    assert run["code"] == 0
    assert "Atlas contours skipped" in run["log"]
    assert "drawn without region outlines" in run["log"]
