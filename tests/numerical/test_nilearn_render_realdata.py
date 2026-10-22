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

Real libraries (nilearn, matplotlib, nibabel), so this runs in the image only:
``docker run --rm -v <tree>:/ti-toolbox -w /ti-toolbox -v <dataset000>:/data/000:ro
-e TIT_DATASET_000=/data/000 idossha/ti-toolbox:<tag> -lc 'simnibs_python -m pytest
tests/numerical/test_nilearn_render_realdata.py -q -p no:cacheprovider'``.
Deliberately elsewhere: averaging on synthetic grids (``test_nilearn_group_average.py``), the
colourbar label precision (``tests/test_nilearn_colorbar_precision.py``).
"""

from __future__ import annotations

import importlib
import json
import os
import re
import socket
import sys
from pathlib import Path

import numpy as np
import pytest

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
#: Packages the host conftest mocks that real nilearn imports (pandas, joblib) or that must be
#: imported fresh against the real scipy the numerical conftest swapped in (sklearn).
_SWAP = ("nilearn", "pandas", "joblib", "sklearn")
#: Reloaded so their module-level ``nib`` / ``plt`` / ``nilearn`` bindings are the real ones.
_RELOAD = (
    "tit.plotting.nilearn.visualizer",
    "tit.plotting.nilearn.img_slices",
    "tit.plotting.nilearn.img_glass",
    "tit.plotting.nilearn.__main__",
)
#: matplotlib's ``hot``: red reaches 1 at 0.365079, blue starts rising at 0.746032.
_HOT_BAND = (0.35, 0.75)


def _root(key: str) -> str:
    return key.split(".")[0]


@pytest.fixture(scope="module")
def nilearn_stack(real_numeric_stack):
    """Real nilearn (and its pandas / joblib) for this module, and the runner bound to it."""
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if _root(k) in _SWAP}

    def put_back():
        for key in [k for k in sys.modules if _root(k) in _SWAP]:
            del sys.modules[key]
        sys.modules.update(saved)
        for name in _RELOAD:
            if name in sys.modules:
                try:
                    importlib.reload(sys.modules[name])
                except Exception:  # pragma: no cover - restoring the mocked stack
                    pass

    try:
        importlib.import_module("nilearn.plotting")
        importlib.import_module("nilearn.image")
    except Exception as exc:  # pragma: no cover - environment without real nilearn
        put_back()
        print(f"skipping: real nilearn is not importable ({exc})")
        pytest.skip(f"real nilearn is not importable here: {exc}")
    modules = {}
    for name in _RELOAD:
        modules[name.rsplit(".", 1)[1]] = importlib.reload(
            importlib.import_module(name)
        )
    yield modules
    put_back()


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


def _blocked(*_args, **_kwargs):
    raise OSError("network blocked by test_nilearn_render_realdata")


def _run_main(runner, project: Path, config: dict, tmp: Path, capsys) -> tuple:
    import logging

    path = tmp / f"{config['subdir_name']}.json"
    path.write_text(json.dumps({"project_dir": str(project), **config}))
    old_argv = sys.argv
    sys.argv = ["tit.plotting.nilearn", str(path)]
    logger = logging.getLogger("tit.plotting.nilearn")
    handlers = list(logger.handlers)
    try:
        with pytest.raises(SystemExit) as exited:
            runner.main()
    finally:
        sys.argv = old_argv
        for handler in [h for h in logger.handlers if h not in handlers]:
            logger.removeHandler(handler)
    captured = capsys.readouterr()
    return exited.value.code, captured.out + captured.err


@pytest.fixture(scope="module")
def run(nilearn_stack, tmp_path_factory):
    """One real run of the Nilearn Visuals job, with its figure and log captured."""
    from tit.config_io import deserialize_config
    from tit.paths import get_path_manager, reset_path_manager
    from tit.plotting.nilearn.config import NilearnConfig

    tmp = tmp_path_factory.mktemp("nilearn_realdata")
    project = _project(tmp)
    before_mtimes = _mtimes()
    visualizer = nilearn_stack["visualizer"]
    runner = nilearn_stack["__main__"]

    figures, displays = [], []
    real_subplots = visualizer.plt.subplots
    real_close = visualizer.plt.close
    real_plot_stat_map = visualizer.plotting.plot_stat_map

    def subplots(*args, **kwargs):
        fig, axes = real_subplots(*args, **kwargs)
        figures.append((fig, axes))
        return fig, axes

    def plot_stat_map(*args, **kwargs):
        display = real_plot_stat_map(*args, **kwargs)
        displays.append(display)
        return display

    config = {
        "subject_simulation_pairs": [
            {"subject_id": s, "simulation_name": _SIM} for s in _SUBJECTS
        ],
        "subdir_name": "insula_realdata",
        "create_glass_brain": True,
    }
    nilearn_data = _BUNDLED if _BUNDLED.is_dir() else tmp / "nilearn_data_empty"
    with pytest.MonkeyPatch.context() as mp:
        capsys = _Capture(mp)
        mp.setenv("NILEARN_DATA", str(nilearn_data))
        mp.setattr(socket.socket, "connect", _blocked)
        mp.setattr(socket, "getaddrinfo", _blocked)
        mp.setattr(visualizer.plt, "subplots", subplots)
        mp.setattr(visualizer.plt, "close", lambda *a, **k: None)
        mp.setattr(visualizer.plotting, "plot_stat_map", plot_stat_map)
        before = _files(project)
        code, log = _run_main(runner, project, config, tmp, capsys)
        written = _files(project) - before
        pm = get_path_manager(str(project))
        from tit.server.routes.plan import _plan_nilearn

        [planned] = _plan_nilearn(
            "nilearn", pm, deserialize_config(NilearnConfig, config)
        )[0]
        reset_path_manager()
    yield {
        "code": code,
        "log": log,
        "written": written,
        "planned_dir": Path(planned.output_dir),
        "figures": figures,
        "displays": displays,
        "before_mtimes": before_mtimes,
        "tmp": tmp,
        "project": project,
        "runner": runner,
        "img_glass": nilearn_stack["img_glass"],
        "close": real_close,
    }
    for fig, _ in figures:
        real_close(fig)


class _Capture:
    """``capsys`` for a module-scoped fixture: stdout/stderr into buffers via MonkeyPatch."""

    def __init__(self, mp: pytest.MonkeyPatch):
        import io

        self._out, self._err = io.StringIO(), io.StringIO()
        mp.setattr(sys, "stdout", self._out)
        mp.setattr(sys, "stderr", self._err)

    def readouterr(self):
        class _Pair:
            out = self._out.getvalue()
            err = self._err.getvalue()

        return _Pair()


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


def _hot_pixels(fig, display) -> int:
    """Pixels of *display*'s drawn slice that matplotlib's ``hot`` paints red to yellow."""
    buf = np.asarray(fig.canvas.buffer_rgba())
    height = buf.shape[0]
    total = 0
    for cut_axes in display.axes.values():
        box = cut_axes.ax.get_window_extent()
        rows = slice(max(0, int(height - box.y1)), int(np.ceil(height - box.y0)))
        cols = slice(max(0, int(box.x0)), int(np.ceil(box.x1)))
        crop = buf[rows, cols, :3].astype(int)
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
    [(fig, _axes)] = run["figures"]
    displays = run["displays"]
    assert len(displays) == 21
    fig.canvas.draw()

    lit, dark = [], []
    for display in displays:
        mode = type(display).__name__[0].lower()  # XSlicer / YSlicer / ZSlicer
        assert mode in "xyz", type(display).__name__
        [coord] = list(display.cut_coords)
        slab = _slab(data, affine, mode, coord)
        hot = _hot_pixels(fig, display)
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
    import nibabel as nib

    data, affine = mean
    _, _, peak = _cutoffs(data)
    out_dir = run["tmp"] / "glass_blank"
    out_dir.mkdir()
    img = nib.Nifti1Image(data.astype(np.float32), affine)
    blank = run["img_glass"].create_glass_brain_entry_point_group(
        img, "blank", str(out_dir), min_cutoff=2 * peak, max_cutoff=3 * peak
    )
    real = run["planned_dir"] / "group_averaged_2_subjects_glass_brain.pdf"
    assert os.path.getsize(real) > os.path.getsize(blank) > 0


def test_a_min_cutoff_above_the_peak_logs_the_blank_figure_warning(
    run, mean, tmp_path, monkeypatch, capsys
):
    _, _, peak = _cutoffs(mean[0])
    runner = run["runner"]

    def no_render(img, base, output_dir, *a, **k):
        path = Path(output_dir) / f"{base}.pdf"
        path.write_bytes(b"%PDF")
        return str(path)

    monkeypatch.setattr(runner, "create_pdf_entry_point_group", no_render)
    config = {
        "subject_simulation_pairs": [
            {"subject_id": s, "simulation_name": _SIM} for s in _SUBJECTS
        ],
        "subdir_name": "insula_blank",
        "min_cutoff": round(1.5 * peak, 4),
        "max_cutoff": round(2.0 * peak, 4),
        "create_glass_brain": False,
    }
    code, log = _run_main(runner, run["project"], config, tmp_path, capsys)
    assert code == 0, log[-2000:]
    warning = re.search(
        r"min_cutoff (\S+) V/m is at or above the field's peak (\S+)", log
    )
    assert warning, log[-2000:]
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
