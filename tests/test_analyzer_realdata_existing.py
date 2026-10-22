"""Every analysis already in Dataset 000 satisfies the analyzer's logical-output invariants (2026-10-22).

What this pins
    For every ``Analyses/<Mesh|Voxel>/<run>/results.csv`` under the dataset:

    1. Order statistics: ``roi_min <= roi_mean <= roi_max <= gm_max``, ``gm_mean <= gm_max``,
       ``percentile_95 <= percentile_99 <= percentile_99_9 <= gm_max`` and
       ``focality_50 >= focality_75 >= focality_90 >= focality_95 >= 0`` (a higher cutoff
       can only shrink the extent above it).
    2. ``roi_focality == roi_mean / gm_mean`` (its definition, analyzer docstring), and the ROI
       is non-empty: ``n_elements > 0`` and ``total_area_or_volume > 0``.
    3. Mesh: ``normal_max <= roi_max`` -- TI_normal is the envelope along one direction and
       TI_max its maximum over all directions (wiki analyzer.md).
    4. Voxel, recomputed from ``roi_overlay.nii.gz`` with the NIfTI-1 reader below (gzip +
       numpy, no nibabel, so it works under the host suite's mocks): the overlay's positive
       voxels are the ROI, so their count is ``n_elements``, their mean/max/min are
       ``roi_mean``/``roi_max``/``roi_min``, ``n * |det A|`` is ``total_area_or_volume``, and
       every focality volume is a whole number of voxels (``cm^3 * 1000 / voxel mm^3``).
       A spherical ROI fits its sphere: its world extent per axis is at most
       ``2r + one voxel``.
    5. The whole-tissue numbers (``gm_*``, percentiles, focality areas) do not depend on the
       ROI: every analysis of one subject/simulation/space/field/tissue reports the same ones.
    6. ``analysis.json``'s ``field_name`` is ``results.csv``'s, and the catalog
       (:func:`tit.catalog.analyses`) lists every analysis folder.

Where the numbers come from
    Nothing is retyped: order statistics, the definitions in the analyzer docstring, a
    physical inequality (3), and an independent reader of the overlay the analyzer wrote (4).

Run it (host, read-only)::

    TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest \
        tests/test_analyzer_realdata_existing.py -q -p no:cacheprovider

Unset, every test skips with a printed reason. The dataset is opened read-only and the suite
fails if any file it read changed size or mtime.

Deliberately elsewhere
    How each number is computed is the synthetic suites' job (tests/test_analyzer_full.py,
    tests/test_analyzer_focality_math.py, tests/numerical/test_sci03_sci05_analyzer_geometry.py).
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import os
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

ENV = "TIT_DATASET_000"
_ROOT = os.environ.get(ENV, "")
_HAVE = bool(_ROOT) and Path(_ROOT, "derivatives", "SimNIBS").is_dir()
if not _HAVE:
    print(f"skipping: {ENV} is unset or has no derivatives/SimNIBS")
pytestmark = pytest.mark.skipif(
    not _HAVE, reason=f"skipping: {ENV} is unset or has no derivatives/SimNIBS"
)

#: NIfTI-1 datatype code -> numpy dtype (the codes an analyzer overlay can carry).
_NIFTI_DTYPES = {
    2: np.uint8,
    4: np.int16,
    8: np.int32,
    16: np.float32,
    64: np.float64,
    256: np.int8,
    512: np.uint16,
    768: np.uint32,
}

_WHOLE_TISSUE = (
    "gm_mean",
    "gm_max",
    "percentile_95",
    "percentile_99",
    "percentile_99_9",
    "focality_50_area",
    "focality_75_area",
    "focality_90_area",
    "focality_95_area",
)


def _read_nifti1(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Voxel array (float64, x fastest) and the 3x4 ``srow`` affine of a NIfTI-1 file."""
    raw = gzip.open(path).read() if path.name.endswith(".gz") else path.read_bytes()
    endian = "<" if struct.unpack("<i", raw[:4])[0] == 348 else ">"
    dim = struct.unpack(endian + "8h", raw[40:56])
    datatype = struct.unpack(endian + "h", raw[70:72])[0]
    vox_offset = int(struct.unpack(endian + "f", raw[108:112])[0])
    slope, inter = struct.unpack(endian + "2f", raw[112:120])
    srow = np.array(struct.unpack(endian + "12f", raw[280:328]), dtype=float)
    shape = dim[1 : 1 + dim[0]]
    dtype = np.dtype(_NIFTI_DTYPES[datatype]).newbyteorder(endian)
    arr = np.frombuffer(raw, dtype=dtype, count=int(np.prod(shape)), offset=vox_offset)
    arr = arr.reshape(shape, order="F").astype(np.float64)
    if slope not in (0.0, 1.0) or inter != 0.0:
        arr = arr * (slope or 1.0) + inter
    return arr, srow.reshape(3, 4)


def _results(path: Path) -> dict[str, str]:
    with open(path, newline="") as fh:
        return {row[0]: row[1] for row in csv.reader(fh) if row and row[0] != "Metric"}


def _analysis_dirs() -> list[Path]:
    root = Path(_ROOT, "derivatives", "SimNIBS")
    return sorted(
        p.parent for p in root.glob("sub-*/Simulations/*/Analyses/*/*/results.csv")
    )


@pytest.fixture(scope="module")
def runs():
    """``(dir, results, analysis.json)`` per analysis; asserts the dataset was not written."""
    dirs = _analysis_dirs()
    assert dirs, f"has analyses to check: none under {_ROOT}/derivatives/SimNIBS"
    read = [f for d in dirs for f in sorted(d.iterdir()) if f.is_file()]
    before = {str(f): (f.stat().st_size, f.stat().st_mtime_ns) for f in read}
    out = []
    for d in dirs:
        meta_path = d / "analysis.json"
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        out.append((d, _results(d / "results.csv"), meta))
    yield out
    after = {str(f): (f.stat().st_size, f.stat().st_mtime_ns) for f in read}
    assert after == before, "the dataset changed while the suite read it"


def _f(res: dict[str, str], key: str) -> float:
    return float(res[key])


def _space(d: Path) -> str:
    return d.parent.name.lower()


def test_order_statistics_hold_for_every_analysis(runs) -> None:
    for d, res, _ in runs:
        name = str(d)
        assert (
            _f(res, "roi_min")
            <= _f(res, "roi_mean")
            <= _f(res, "roi_max")
            <= _f(res, "gm_max")
        ), name
        assert _f(res, "gm_mean") <= _f(res, "gm_max"), name
        assert (
            _f(res, "percentile_95")
            <= _f(res, "percentile_99")
            <= _f(res, "percentile_99_9")
            <= _f(res, "gm_max")
        ), name
        assert (
            _f(res, "focality_50_area")
            >= _f(res, "focality_75_area")
            >= _f(res, "focality_90_area")
            >= _f(res, "focality_95_area")
            >= 0
        ), name


def test_focality_ratio_is_roi_mean_over_tissue_mean_and_the_roi_is_not_empty(
    runs,
) -> None:
    for d, res, _ in runs:
        expected = _f(res, "roi_mean") / _f(res, "gm_mean")
        assert math.isclose(_f(res, "roi_focality"), expected, rel_tol=1e-9), str(d)
        assert int(float(res["n_elements"])) > 0, str(d)
        assert _f(res, "total_area_or_volume") > 0, str(d)


def test_mesh_normal_component_never_exceeds_the_envelope_maximum(runs) -> None:
    checked = 0
    for d, res, _ in runs:
        if _space(d) == "mesh" and "normal_max" in res:
            assert _f(res, "normal_max") <= _f(res, "roi_max"), str(d)
            checked += 1
    assert checked > 0, "has mesh analyses with normal stats to check"


def test_voxel_results_match_the_overlay_read_independently(runs) -> None:
    voxel = [(d, res, meta) for d, res, meta in runs if _space(d) == "voxel"]
    assert voxel, "has voxel analyses to check"
    for d, res, meta in voxel:
        arr, srow = _read_nifti1(d / "roi_overlay.nii.gz")
        pos = arr[arr > 0]
        voxel_mm3 = abs(float(np.linalg.det(srow[:, :3])))
        assert pos.size == int(float(res["n_elements"])), str(d)
        # The overlay is float32: its values are the analyzer's float32 field, so the CSV's
        # float64 statistics of them agree to float32 rounding of the mean (rel 1e-6).
        assert math.isclose(float(pos.mean()), _f(res, "roi_mean"), rel_tol=1e-6), str(
            d
        )
        assert math.isclose(float(pos.max()), _f(res, "roi_max"), rel_tol=1e-6), str(d)
        assert math.isclose(float(pos.min()), _f(res, "roi_min"), rel_tol=1e-6), str(d)
        assert math.isclose(
            pos.size * voxel_mm3, _f(res, "total_area_or_volume"), rel_tol=1e-6
        ), str(d)
        for key in (
            "focality_50_area",
            "focality_75_area",
            "focality_90_area",
            "focality_95_area",
        ):
            voxels = _f(res, key) * 1000.0 / voxel_mm3
            # results.csv rounds nothing, but cm^3 -> voxel count goes through two floats.
            assert abs(voxels - round(voxels)) < 1e-6 * max(1.0, voxels), (str(d), key)
        if meta.get("analysis_type") == "spherical" and meta.get("spheres"):
            radius = max(float(s[3]) for s in meta["spheres"])
            ijk = np.argwhere(arr > 0).astype(float)
            world = ijk @ srow[:, :3].T + srow[:, 3]
            extent = world.max(axis=0) - world.min(axis=0)
            step = np.linalg.norm(srow[:, :3], axis=0)
            assert np.all(extent <= 2 * radius + step + 1e-6), (str(d), extent)


def test_whole_tissue_numbers_do_not_depend_on_the_roi(runs) -> None:
    groups: dict[tuple, list] = defaultdict(list)
    for d, res, meta in runs:
        sim_dir = d.parents[2]
        tissue = tuple(meta.get("tissue_types") or ["GM"])
        groups[(str(sim_dir), _space(d), res["field_name"], tissue)].append((d, res))
    shared = [g for g in groups.values() if len(g) > 1]
    assert shared, "has two analyses of one simulation/space/field/tissue to compare"
    for group in shared:
        (d0, first), rest = group[0], group[1:]
        for d, res in rest:
            for key in _WHOLE_TISSUE:
                assert math.isclose(_f(res, key), _f(first, key), rel_tol=1e-9), (
                    str(d0),
                    str(d),
                    key,
                )


def test_analysis_json_names_the_csv_field_and_the_catalog_lists_every_folder(
    runs,
) -> None:
    from tit import catalog
    from tit.paths import PathManager

    pm = PathManager(_ROOT)
    by_sim: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d, res, meta in runs:
        assert meta, f"{d} has no analysis.json"
        assert meta["field_name"] == res["field_name"], str(d)
        sim_dir = d.parents[2]
        sid = sim_dir.parents[1].name.removeprefix("sub-")
        by_sim[(sid, sim_dir.name)].add(str(d))
    for (sid, sim), dirs in by_sim.items():
        listed = catalog.analyses(pm, sid, sim)
        assert listed is not None, (sid, sim)
        paths = {os.path.dirname(item["csv"]) for item in listed}
        assert dirs <= paths, (sid, sim, sorted(dirs - paths))
