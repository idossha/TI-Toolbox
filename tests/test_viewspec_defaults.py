"""What a scene *opens at* -- the windows, the crosshair and the zoom.

The maintainer, on the first scene the Viewer handed to Tetravox (2026-09-07): *"it launches the
selected input, but for some reason it provides it with some very strange defaults ... it would be
much more reasonable to set more logical thresholds, for example 95 to 99.9 of the electric field
and so on, plus the sizing and the location of the scans can be improved."*

Every default in that sentence is decided in :mod:`tit.viewspec`, and each one has a test here:

* a field overlay opens windowed ``[p95, p99.9]`` with its threshold at ``p95``;
* a T1 opens windowed ``[p2, p98]``, not ``[min, max]``;
* a label volume opens at its exact range, because a clipped LUT index is a wrong colour;
* a signed statistic map opens symmetric about zero on a diverging ramp;
* the crosshair lands on the field's peak, not on world ``(0, 0, 0)``;
* the 2D panes open fitted to the data, not at the engine's fixed 0.5 mm/px.

**How the expected numbers are derived.** ``nibabel`` is mocked in this repo's ``conftest``, so
these tests hand :mod:`tit.viewspec` a fake image whose voxels are ``0..100`` -- 101 values, one of
them zero. The percentiles are then exact and checkable by hand rather than read back out of the
function under test: over the 100 non-zero values ``1..100``, ``numpy``'s linear interpolation puts
the *q*-th percentile at ``1 + (q/100) * 99``. So ``p2 = 2.98``, ``p95 = 95.05``, ``p98 = 98.02``
and ``p99.9 = 99.901``.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager

# The voxels every fake volume below carries, and the percentiles they imply. Stated as literals,
# not computed with the same call the code under test makes.
VOXELS = np.arange(0, 101, dtype=float)
P2 = 2.98
P50 = 50.5
P95 = 95.05
P98 = 98.02
P99 = 99.01
P999 = 99.901
NZ_LO = 1.0
NZ_HI = 100.0


def test_the_expected_percentiles_are_what_numpy_says() -> None:
    """A guard on this file's own arithmetic.

    If ``numpy`` ever changed its default interpolation, every expectation above would be wrong
    and every test below would fail for a reason that had nothing to do with the Viewer. This
    pins the premise separately, so that failure is legible.
    """
    nonzero = VOXELS[VOXELS != 0]
    assert np.percentile(nonzero, 2) == pytest.approx(P2)
    assert np.percentile(nonzero, 50) == pytest.approx(P50)
    assert np.percentile(nonzero, 95) == pytest.approx(P95)
    assert np.percentile(nonzero, 98) == pytest.approx(P98)
    assert np.percentile(nonzero, 99) == pytest.approx(P99)
    assert np.percentile(nonzero, 99.9) == pytest.approx(P999)


@pytest.fixture(autouse=True)
def _reset():
    reset_path_manager()
    viewspec.clear_percentile_cache()
    yield
    viewspec.clear_percentile_cache()
    reset_path_manager()


class _FakeNibabel:
    """A ``nibabel`` whose ``load`` answers per path, and counts what it read.

    Volumes are ``(shape, values, affine)`` triples registered by absolute path. Anything not
    registered raises, exactly as ``nibabel`` does for a file that is not a NIfTI -- so a test
    that forgets to register a file fails loudly rather than silently exercising a fallback.
    """

    def __init__(self) -> None:
        self.volumes: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.reads: list[str] = []

    def register(
        self, path: str | Path, values: np.ndarray, affine: np.ndarray | None = None
    ) -> str:
        path = str(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # A real file, so `os.stat` (the cache key, and the sidecar's) has something to read.
        Path(path).write_bytes(b"stand-in for a NIfTI; size and mtime are what matter")
        self.volumes[path] = (
            np.asarray(values, dtype=float),
            np.eye(4) if affine is None else np.asarray(affine, dtype=float),
        )
        return path

    def load(self, path):
        path = str(path)
        if path not in self.volumes:
            raise OSError(f"not a registered fake volume: {path}")
        self.reads.append(path)
        values, affine = self.volumes[path]
        return types.SimpleNamespace(
            dataobj=values,
            get_fdata=lambda: values,
            affine=affine,
            shape=values.shape,
        )


@pytest.fixture()
def nib(monkeypatch) -> _FakeNibabel:
    fake = _FakeNibabel()
    monkeypatch.setitem(sys.modules, "nibabel", fake)
    return fake


@pytest.fixture()
def project(tmp_path: Path) -> PathManager:
    """A path manager rooted at a tmp project, so sidecars land under it and not in a real one."""
    return get_path_manager(str(tmp_path))


def cube(values: np.ndarray, side: int = 5) -> np.ndarray:
    """*values* laid into a ``side^3`` volume, **zero-padded** to fill it.

    Padded rather than tiled: every percentile in this module is taken over the *non-zero* voxels,
    so extra zeros leave the expected numbers at the top of this file exactly as stated, whereas
    repeating the values would silently reweight the distribution.
    """
    values = np.asarray(values, dtype=float).ravel()
    assert values.size <= side**3, "values do not fit in the cube"
    flat = np.zeros(side**3, dtype=float)
    flat[: values.size] = values
    return flat.reshape((side, side, side))


# ── the windows ──────────────────────────────────────────────────────────────


def test_field_overlay_opens_windowed_p95_to_p999(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """The headline default. ``[p95, p99.9]``, with the threshold at ``p95`` and ``mode: hide``.

    The old window opened at ``min = nz_lo`` -- the smallest non-zero voxel, ``5.08e-09`` V/m on
    the maintainer's own ``sub-101/L_Insula`` -- which is not a threshold, it is "everything that
    is not exactly zero", and it is why the overlay washed over the whole head.
    """
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    scale, threshold = viewspec._volume_window(path, role="field")

    assert scale["kind"] == "heat"
    assert scale["min"] == pytest.approx(P95)
    assert scale["max"] == pytest.approx(P999)
    assert scale["mid"] == pytest.approx((P95 + P999) / 2)
    assert scale["negative"] == "hide"

    assert threshold["lo"] == pytest.approx(P95)
    assert threshold["hi"] is None, "an open top: nothing above the window is deleted"
    assert threshold["mode"] == "hide", "clamp would paint the sub-threshold voxels, not hide them"


def test_t1_opens_windowed_p2_to_p98_not_min_to_max(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A T1's ``max`` is a handful of bright scalp-fat voxels.

    Windowing to it makes the brain read as uniform dark grey, which is what the maintainer's
    screenshot showed (``0..3238`` on a volume whose 98th percentile is near 900).
    """
    path = nib.register(tmp_path / "m2m" / "T1.nii.gz", cube(VOXELS))
    scale, threshold = viewspec._volume_window(path, role="base")

    assert scale == {"kind": "linear", "lo": pytest.approx(P2), "hi": pytest.approx(P98)}
    assert scale["lo"] != 0.0 and scale["hi"] != NZ_HI
    assert threshold["lo"] is None, "anatomy is not thresholded, only windowed"


def test_label_volume_keeps_its_exact_range(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A label volume is *not* percentile-windowed.

    Its voxels are integer region indices addressed through a LUT. Clipping the top 2 % would give
    two different anatomical regions the same colour -- a percentile window is the right default
    for a measurement and the wrong one for a name.
    """
    path = nib.register(tmp_path / "m2m" / "labeling.nii.gz", cube(VOXELS))
    for role in ("atlas", "electrodes"):
        scale, threshold = viewspec._volume_window(path, role=role)
        assert scale == {"kind": "linear", "lo": 0.0, "hi": NZ_HI}, role
        assert threshold["lo"] is None, role


def test_signed_statistic_map_opens_symmetric_about_zero(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A t-map's sign is its finding, so the window has to keep both tails.

    A heat window anchored at a positive percentile with ``negative: hide`` -- what a field gets --
    would delete every negative voxel, which for a paired difference map is half the result.
    """
    signed = cube(np.concatenate([VOXELS, -VOXELS]), side=8)
    path = nib.register(tmp_path / "group" / "ses_tstat.nii.gz", signed)

    assert viewspec._is_stat_map(path)
    scale, threshold = viewspec._volume_window(path, role="field")
    assert scale["kind"] == "linear", "not a heat ramp: heat has no negative half"
    assert scale["lo"] == pytest.approx(-scale["hi"])
    assert scale["hi"] > 0
    assert threshold["lo"] is None, "a symmetric window is not a floor"


def test_a_field_that_is_all_zero_falls_back_instead_of_a_zero_width_window(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """``p95 == p99.9 == 0`` is a window that shows nothing. Better to show the file's own range."""
    path = nib.register(tmp_path / "sim" / "empty_TI_max.nii.gz", np.zeros((5, 5, 5)))
    scale, _ = viewspec._volume_window(path, role="field")
    assert scale["max"] > scale["min"] or scale == {
        "kind": "heat",
        "min": 0.0,
        "mid": 0.5,
        "max": 1.0,
        "truncate": False,
        "inverse": False,
        "negative": "hide",
    }


def test_an_unreadable_volume_windows_generically_rather_than_failing(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """One bad file must not fail a whole scene -- the other layers are still worth showing."""
    missing = str(tmp_path / "sim" / "gone.nii.gz")
    os.makedirs(os.path.dirname(missing), exist_ok=True)
    Path(missing).write_bytes(b"truncated")
    scale, threshold = viewspec._volume_window(missing, role="field")
    assert scale["kind"] == "heat"
    assert threshold["lo"] is None


# ── the sidecar ──────────────────────────────────────────────────────────────


def test_the_statistics_sidecar_is_written_once_and_then_reused(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """The fix for "a lot of loading time": the second *process* pays nothing either.

    The in-process cache alone made a 16 s resolve cost 16 s once per server process -- which,
    under ``--reload`` and on every app start, is once per sitting.
    """
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))

    first = viewspec._volume_stats(path)
    assert first is not None
    assert nib.reads == [path]

    sidecar = viewspec._stats_sidecar_path(path)
    assert sidecar is not None and os.path.isfile(sidecar)
    assert os.path.dirname(sidecar) == viewspec.stats_cache_dir()

    # A new process: the in-memory cache is gone, the sidecar is not.
    viewspec.clear_percentile_cache()
    again = viewspec._volume_stats(path)
    assert nib.reads == [path], "the volume was read again despite an on-disk sidecar"
    assert again == first


def test_a_rewritten_volume_invalidates_its_sidecar(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """Keyed by ``(size, mtime_ns)``: a re-run simulation must not keep yesterday's window."""
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    viewspec._volume_stats(path)
    assert len(nib.reads) == 1

    Path(path).write_bytes(b"a different length entirely, so size and mtime both move")
    os.utime(path, ns=(0, 0))
    nib.volumes[path] = (cube(VOXELS * 2), np.eye(4))
    viewspec.clear_percentile_cache()

    refreshed = viewspec._volume_stats(path)
    assert len(nib.reads) == 2, "a changed file was answered from a stale sidecar"
    assert refreshed is not None
    assert refreshed["p95"] == pytest.approx(P95 * 2)


def test_a_corrupt_sidecar_is_a_miss_not_an_error(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A hand-edited or half-written sidecar costs one volume read, never a wrong window."""
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    viewspec._volume_stats(path)
    sidecar = viewspec._stats_sidecar_path(path)
    assert sidecar is not None
    Path(sidecar).write_text("{not json at all")
    viewspec.clear_percentile_cache()

    assert viewspec._volume_stats(path) is not None
    assert len(nib.reads) == 2


def test_a_sidecar_from_an_older_version_is_ignored(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """Otherwise a sidecar written before ``p2``/``p98`` existed would window every T1 at ``None``."""
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    viewspec._volume_stats(path)
    sidecar = viewspec._stats_sidecar_path(path)
    assert sidecar is not None
    body = json.loads(Path(sidecar).read_text())
    body["version"] = viewspec._STATS_VERSION - 1
    Path(sidecar).write_text(json.dumps(body))
    viewspec.clear_percentile_cache()

    assert viewspec._volume_stats(path) is not None
    assert len(nib.reads) == 2


def test_no_project_open_means_no_sidecar_and_no_crash(
    nib: _FakeNibabel, tmp_path: Path, monkeypatch
) -> None:
    """The statistics still work; they just do not persist. A cache is never a hard dependency."""
    monkeypatch.setattr(viewspec, "stats_cache_dir", lambda: None)
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    assert viewspec._volume_stats(path) is not None
    assert viewspec._stats_sidecar_path(path) is None


# ── the resolve does not read voxels once warm ───────────────────────────────


def test_a_warm_resolve_reads_no_voxels(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """The response-time budget, stated as the thing that actually costs the time.

    Wall-clock assertions are flaky on shared CI; "did it inflate a 70 MB gzip stream" is not. A
    resolve whose volumes are all sidecar-backed must reach the client without touching one.
    """
    paths = [
        nib.register(tmp_path / "sim" / f"L_Insula_TI_subject_TI_max_{i}.nii.gz", cube(VOXELS))
        for i in range(4)
    ]
    viewspec.prefetch_volume_stats(paths)
    assert sorted(nib.reads) == sorted(paths)

    viewspec.clear_percentile_cache()
    nib.reads.clear()
    viewspec.prefetch_volume_stats(paths)
    assert nib.reads == [], "a warm resolve re-read the volumes"

    spec = {
        "layers": [
            {"path": p, "cal_min": None, "cal_max": None, "percentile": {"lo": 95, "hi": 99.9}}
            for p in paths
        ]
    }
    viewspec.resolve_percentiles(spec)
    assert nib.reads == [], "resolve_percentiles read the volumes a second time"
    for layer in spec["layers"]:
        assert layer["cal_min"] == pytest.approx(P95)
        assert layer["cal_max"] == pytest.approx(P999)


def test_a_window_outside_the_stats_table_still_reads_the_volume(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """Correctness before speed: a p90 answered with p95 would be wrong, and wrong is worse.

    ``_volume_stats`` computes a fixed set of percentiles. A layer asking for one outside that set
    falls back to reading the volume rather than being handed the nearest neighbour.
    """
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", cube(VOXELS))
    spec = {
        "layers": [
            {"path": path, "cal_min": None, "cal_max": None, "percentile": {"lo": 5, "hi": 90}}
        ]
    }
    viewspec.resolve_percentiles(spec)
    assert nib.reads == [path]
    assert spec["layers"][0]["cal_max"] == pytest.approx(np.percentile(VOXELS[VOXELS != 0], 90))


# ── sizing and location ──────────────────────────────────────────────────────


def test_bounds_come_from_the_header_without_reading_a_voxel(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """"Never read voxels for a resolve" -- the extent is exactly what the affine already says.

    A 10x10x10 grid at 2 mm spacing spans the *outer faces* of the end voxels, so 9 gaps of 2 mm
    plus half a voxel at each end: 20 mm, from -1 to 19.
    """
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    path = nib.register(tmp_path / "m2m" / "T1.nii.gz", np.ones((10, 10, 10)), affine)

    lo, hi = viewspec._volume_bounds(path)
    assert lo == pytest.approx([-1.0, -1.0, -1.0])
    assert hi == pytest.approx([19.0, 19.0, 19.0])


def test_panes_open_fitted_to_the_data_not_at_the_engine_default(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """The engine fits a pane only when a scene has exactly one dataset, and ours never do.

    So every pane kept ``0.5`` mm/px regardless of the head in front of it -- "the head is a small
    square in each pane". The formula is the engine's own ``fitMmPerPx``: ``diag * 0.62 / px``.
    """
    bounds = ([-100.0, -100.0, -100.0], [100.0, 100.0, 100.0])
    diag = (3 * 200.0**2) ** 0.5
    assert viewspec._fit_mm_per_px(bounds, 512) == pytest.approx(diag * 0.62 / 512)

    # A bigger pane sees the same head at a finer scale: twice the pixels, half the mm each.
    assert viewspec._fit_mm_per_px(bounds, 1024) == pytest.approx(
        viewspec._fit_mm_per_px(bounds, 512) / 2
    )
    # Never zero or negative, however degenerate the data.
    assert viewspec._fit_mm_per_px(([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]), 512) == 0.05


def test_the_3d_camera_frames_the_bounding_box(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """Targeted at the head's centre and far enough back to contain it, not a fixed 350 mm."""
    bounds = ([-100.0, -50.0, -80.0], [100.0, 150.0, 120.0])
    camera = viewspec._fit_camera(
        {"fovYDeg": 35.0, "target": [0.0, 0.0, 0.0], "distance": 350.0}, bounds
    )
    assert camera["target"] == pytest.approx([0.0, 50.0, 20.0])
    assert camera["distance"] > 0
    assert camera["far"] > camera["distance"] > camera["near"]


def test_the_crosshair_lands_on_the_field_peak(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """World ``(0, 0, 0)`` is the scanner origin -- for a subject-space head, a corner of the FOV.

    The peak is where a reader looks first, and it is free: the array is already in memory for the
    percentiles, and the affine is the header's.
    """
    values = np.zeros((5, 5, 5))
    values[4, 3, 2] = 99.0
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", values, affine)

    stats = viewspec._volume_stats(path)
    assert stats is not None
    assert (stats["max_x"], stats["max_y"], stats["max_z"]) == pytest.approx((8.0, 6.0, 4.0))


def test_a_nan_does_not_become_the_peak(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """``argmax`` on an array containing a NaN answers the NaN's index, which is not the hotspot."""
    values = np.zeros((5, 5, 5))
    values[0, 0, 0] = np.nan
    values[4, 3, 2] = 99.0
    path = nib.register(tmp_path / "sim" / "TI_max.nii.gz", values, np.eye(4))

    stats = viewspec._volume_stats(path)
    assert stats is not None
    assert (stats["max_x"], stats["max_y"], stats["max_z"]) == pytest.approx((4.0, 3.0, 2.0))


# ── a mesh borrows the right sibling's window ────────────────────────────────


def test_a_gm_mesh_borrows_the_gm_volume_window_not_the_whole_head_one(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """Which sibling a mesh borrows from decides whether the surface renders at all.

    A field ``.msh`` is 24-420 MB, so its element values are never read and its window comes from
    a sibling NIfTI carrying the same field. A simulation scene holds three of those — whole-head,
    grey-matter-masked, white-matter-masked — and their ranges differ by an order of magnitude.
    Taking the first one found put the GM surface's entire value range below the bottom of its own
    ramp: the mesh rendered a uniform blue with every element under its threshold (screenshot,
    2026-09-07). It has to be the volume of the *same tissue*.
    """
    whole = cube(VOXELS * 10)  # a whole-head field, ten times the masked one's range
    masked = cube(VOXELS)
    sim = tmp_path / "sim"
    nib.register(sim / "L_Insula_TI_subject_TI_max.nii.gz", whole)
    nib.register(sim / "grey_L_Insula_TI_subject_TI_max.nii.gz", masked)
    mesh = str(sim / "grey_L_Insula_TI.msh")
    Path(mesh).write_bytes(b"$MeshFormat")

    field_volumes = [
        {"path": str(sim / "L_Insula_TI_subject_TI_max.nii.gz"), "visible": False},
        {"path": str(sim / "grey_L_Insula_TI_subject_TI_max.nii.gz"), "visible": True},
    ]
    lo, hi = viewspec._bounds_for_mesh("grey_L_Insula_TI.msh", field_volumes)
    assert lo == pytest.approx(P95)
    assert hi == pytest.approx(P999)
    # Not the whole-head window, which is where the uniform-blue surface came from.
    assert hi < P999 * 10


def test_a_mesh_with_no_tissue_prefix_falls_back_to_the_visible_field(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A whole-head mesh has no tissue to match, so it takes what the reader is looking at."""
    sim = tmp_path / "sim"
    nib.register(sim / "L_Insula_TI_subject_TI_max.nii.gz", cube(VOXELS * 10))
    nib.register(sim / "grey_L_Insula_TI_subject_TI_max.nii.gz", cube(VOXELS))
    field_volumes = [
        {"path": str(sim / "L_Insula_TI_subject_TI_max.nii.gz"), "visible": False},
        {"path": str(sim / "grey_L_Insula_TI_subject_TI_max.nii.gz"), "visible": True},
    ]
    lo, hi = viewspec._bounds_for_mesh("L_Insula_TI.msh", field_volumes)
    assert hi == pytest.approx(P999), "the visible layer's window, not the hidden one's"


def test_gray_and_grey_are_the_same_tissue(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """SimNIBS spells it both ways; a `gray_` mesh must still find its `grey_` volume."""
    assert viewspec._tissue_prefix("gray_x.msh") == viewspec._tissue_prefix("grey_x.nii.gz")
    assert viewspec._tissue_prefix("white_x.msh") == "white_"
    assert viewspec._tissue_prefix("L_Insula_TI.msh") is None


def test_no_field_volume_at_all_leaves_the_mesh_generic(
    nib: _FakeNibabel, project: PathManager, tmp_path: Path
) -> None:
    """A bare mesh (the `custom` view kind) has nothing to borrow from and must not crash."""
    assert viewspec._bounds_for_mesh("grey_x.msh", []) is None
    scale, threshold = viewspec._mesh_scale_and_threshold(None)
    assert scale == {"kind": "linear", "lo": 0.0, "hi": 1.0}
    assert threshold["hi"] is None


# ── which field a file carries ───────────────────────────────────────────────


def test_a_simulations_three_volumes_do_not_all_come_out_named_TI_max() -> None:
    """The field is the basename's **last token**, not any substring of it.

    `L_Insula_TI_subject_hf_peak.nii.gz` contains "ti" twice, and the old substring chain answered
    `TI_max` for it — so a simulation's TI_max, hf_peak and hf_sar volumes all rendered as
    "TI_max (volume)": three identical rows in the viewer's Layers list, and three identical
    checkboxes once the composition tree existed (screenshot, 2026-09-07).
    """
    sim = "L_Insula_TI_subject"
    assert viewspec._scene_field_name(f"{sim}_TI_max.nii.gz") == "TI_max"
    assert viewspec._scene_field_name(f"{sim}_hf_peak.nii.gz") == "hf_peak"
    assert viewspec._scene_field_name(f"{sim}_hf_sar.nii.gz") == "hf_sar"
    assert viewspec._scene_field_name(f"grey_{sim}_TI_normal.nii.gz") == "TI_normal"
    assert viewspec._scene_field_name("101_TDCS_1_scalar_subject_magnE.nii.gz") == "magnE"

    names = {
        viewspec._scene_field_name(f"{sim}_{token}.nii.gz")
        for token in ("TI_max", "hf_peak", "hf_sar")
    }
    assert len(names) == 3, "three different fields must not share one name"


def test_a_mesh_still_reads_its_field_from_the_hints() -> None:
    """A `.msh` genuinely carries no trailing field token, so the hint chain stays for those.

    The mesh's real field names live inside a 24-420 MB file this module never reads, which is why
    the guess exists at all.
    """
    assert viewspec._scene_field_name("grey_L_Insula_TI.msh") == "TI_max"
    assert viewspec._scene_field_name("grey_L_Insula_mTI.msh") == "mTI_max"
    assert viewspec._scene_field_name("grey_L_Insula_normal.msh") == "TI_normal"
    assert viewspec._scene_field_name("ernie_TDCS_1_scalar.msh") == "magnE"


def test_a_file_that_names_no_field_says_so() -> None:
    """`None` means "colour by tag" for a mesh and "no recognised field" for a volume — an
    analysis ROI mask must not be labelled as though it were a field map."""
    assert viewspec._scene_field_name("roi_mask.nii.gz") is None
    assert viewspec._scene_field_name("labeling.nii.gz") is None


def test_an_anatomy_volume_is_not_mistaken_for_a_field() -> None:
    """`final_tissues.nii.gz` contains "ti" — in "tissues" — and used to become a "TI_max" layer.

    The hint chain is for meshes only. A volume whose last token names no field has none, which is
    what `None` has always meant here for a volume.
    """
    for name in ("final_tissues.nii.gz", "T1.nii.gz", "T2_reg.nii.gz", "tissue_labelling.nii.gz"):
        assert viewspec._scene_field_name(name) is None, name


def test_two_electrode_pairs_do_not_get_one_name() -> None:
    """A high-frequency simulation writes one output *per pair*, and the pair number is the only
    thing that tells them apart — without it a person sees "magnE (volume)" twice, and two
    412 MB "mesh · magnE" rows, with nothing to choose between them."""
    display = lambda n: viewspec._scene_display_name(  # noqa: E731
        n, role=viewspec._scene_role(f"/x/{n}", "heat"), field_name=viewspec._scene_field_name(n)
    )
    one = display("101_TDCS_1_scalar_subject_magnE.nii.gz")
    two = display("101_TDCS_2_scalar_subject_magnE.nii.gz")
    assert one != two
    assert "pair 1" in one and "pair 2" in two


def test_a_whole_head_mesh_does_not_stutter() -> None:
    """"Mesh mesh · TI_max" reads as a bug. A mesh with no tissue prefix is the head's own."""
    name = "L_Insula_TI.msh"
    label = viewspec._scene_display_name(
        name, role="mesh", field_name=viewspec._scene_field_name(name)
    )
    assert label == "Head mesh · TI_max"
    assert viewspec._scene_display_name("grey_L_Insula_TI.msh", role="mesh", field_name="TI_max") == "GM mesh · TI_max"
