"""FastSurfer's derived NIfTI and label sidecar, written and read back with real nibabel.

``tit.pre.fastsurfer.write_derived_outputs`` turns ``aparc.DKTatlas+aseg.deep.mgz`` into a
``.nii.gz`` copy and the ``*_labels.txt`` sidecar the atlas readers cache-read. The host
suite mocks nibabel, so only here is it shown that the copy keeps the labels, the dtype
and the affine, and that ``VoxelAtlasManager`` finds the sidecar under the name it derives.

Expected values are authored: a synthetic segmentation with hand-counted labels, named
from FreeSurfer's own colour table (17 Left-Hippocampus, 53 Right-Hippocampus, 1002
ctx-lh-caudalanteriorcingulate, 2035 ctx-rh-insula).

    .venv/bin/python -m pytest tests/numerical/test_fastsurfer_derived.py -q -p no:cacheprovider
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

#: label -> (index slices, voxel count) of the authored segmentation.
REGIONS = {
    17: ((slice(0, 2), slice(0, 3), slice(0, 4)), 24),
    53: ((slice(3, 4), slice(0, 5), slice(5, 11)), 30),
    1002: ((slice(5, 8), slice(6, 9), slice(0, 3)), 27),
    2035: ((slice(9, 10), slice(11, 12), slice(0, 7)), 7),
}
NAMES = {
    17: "Left-Hippocampus",
    53: "Right-Hippocampus",
    1002: "ctx-lh-caudalanteriorcingulate",
    2035: "ctx-rh-insula",
}
SHAPE = (10, 12, 14)
ZOOMS = (1.0, 1.0, 1.2)


def _segmentation(dtype, offset=0.0):
    data = np.zeros(SHAPE, dtype=dtype)
    for label, (index, _) in REGIONS.items():
        data[index] = label + offset
    return data


def _write_mgz(mri_dir, data):
    import nibabel as nib

    from tit.pre.fastsurfer import SEG_FILENAME

    affine = np.diag([*ZOOMS, 1.0])
    affine[:3, 3] = [-5.0, -6.0, -8.4]
    mri_dir.mkdir(parents=True)
    path = mri_dir / SEG_FILENAME
    nib.save(nib.MGHImage(data, affine), str(path))
    return path


def _labels_rows(path):
    rows = {}
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        _index, seg_id, n_voxels, volume, *name = line.split()
        rows[int(seg_id)] = (int(n_voxels), float(volume), " ".join(name))
    return rows


@pytest.mark.parametrize(
    "dtype, offset",
    [
        (np.int32, 0.0),
        # Float storage a hair either side of the label: rounding, not truncation.
        (np.float32, 1e-7),
        (np.float32, -1e-4),
    ],
)
def test_derived_copy_and_sidecar_round_trip_through_the_atlas_reader(
    tmp_path, dtype, offset
):
    import nibabel as nib

    from tit.atlas.voxel import VoxelAtlasManager
    from tit.pre.fastsurfer import (
        SEG_LABELS_FILENAME,
        SEG_NIFTI_FILENAME,
        write_derived_outputs,
    )

    mri_dir = tmp_path / "derivatives" / "fastsurfer" / "sub-001" / "mri"
    mgz = _write_mgz(mri_dir, _segmentation(dtype, offset))
    source = nib.load(str(mgz))
    stored = np.asarray(source.dataobj).dtype  # MGH is big-endian on disk
    assert (stored.kind, stored.itemsize) == (np.dtype(dtype).kind, 4)

    write_derived_outputs(mri_dir, logger=logging.getLogger("fastsurfer-test"))

    nifti = nib.load(str(mri_dir / SEG_NIFTI_FILENAME))
    data = np.asarray(nifti.dataobj)
    assert np.issubdtype(nifti.get_data_dtype(), np.integer)
    assert np.issubdtype(data.dtype, np.integer)
    np.testing.assert_array_equal(data, _segmentation(np.int32))
    np.testing.assert_allclose(nifti.affine, source.affine, atol=1e-6)

    labels = mri_dir / SEG_LABELS_FILENAME
    rows = _labels_rows(labels)
    voxel_mm3 = float(np.prod(ZOOMS))
    assert set(rows) == set(REGIONS)
    for label, (_, count) in REGIONS.items():
        n_voxels, volume, name = rows[label]
        assert (n_voxels, name) == (count, NAMES[label])
        assert volume == pytest.approx(count * voxel_mm3, abs=1e-3)

    # Both atlas files are offered, and both read this sidecar instead of rebuilding it.
    manager = VoxelAtlasManager(fastsurfer_mri_dir=str(mri_dir))
    offered = dict(manager.list_atlases())
    expected = sorted(f"{NAMES[k]} (ID: {k})" for k in REGIONS)
    stamp = labels.stat().st_mtime_ns
    for name in (mgz.name, SEG_NIFTI_FILENAME):
        assert offered[name] == str(mri_dir / name)
        assert manager.list_regions(offered[name]) == expected
    assert labels.stat().st_mtime_ns == stamp


def test_rerun_leaves_existing_derived_files_alone(tmp_path):
    from tit.pre.fastsurfer import (
        SEG_LABELS_FILENAME,
        SEG_NIFTI_FILENAME,
        write_derived_outputs,
    )

    mri_dir = tmp_path / "mri"
    _write_mgz(mri_dir, _segmentation(np.int32))
    logger = logging.getLogger("fastsurfer-test")
    write_derived_outputs(mri_dir, logger=logger)
    derived = [mri_dir / SEG_NIFTI_FILENAME, mri_dir / SEG_LABELS_FILENAME]
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in derived}

    write_derived_outputs(mri_dir, logger=logger)

    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in derived} == before

    # A sidecar removed by hand is written again; the NIfTI beside it is not touched.
    derived[1].unlink()
    write_derived_outputs(mri_dir, logger=logger)
    assert set(_labels_rows(derived[1])) == set(REGIONS)
    assert derived[0].stat().st_mtime_ns == before[derived[0]][0]
