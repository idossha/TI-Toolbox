"""Every shipped MNI atlas names one hemisphere per label (DECISIONS § 2026-09-23).

What it pins: picking a region in an MNI atlas targets ONE side. Before
2026-09-23 Harvard-Oxford cortical (48 labels) and CIT168 (16) gave each
structure a single label value spanning both hemispheres, so choosing
"Putamen" in the ROI picker selected -- and optimized for -- both putamens.

Where the numbers come from: the shipped volumes themselves, read here with a
stdlib + numpy NIfTI-1 reader (nibabel is mocked in this suite), world x from
the header's sform rows. A label is "bilateral" when more than 1 % of its
voxels lie on each side of the midline, ignoring the |x| <= 2 mm slab that
maxprob maps smear across. The only labels allowed to be bilateral are the
midline structures named in ``MIDLINE`` (read from each atlas's own LUT).

Reproduce: ``pytest tests/test_atlas_laterality.py``. How the lateralized
atlases are made: ``dev/build_lateralized_atlases.py``.
"""

from __future__ import annotations

import gzip
import json
import re
import struct
from pathlib import Path

import numpy as np
import pytest

from tit.atlas.constants import mni_resources_dir

RESOURCES = Path(mni_resources_dir())

#: Anatomy that genuinely sits on the midline, so one label legitimately spans x = 0.
MIDLINE = re.compile(r"vermis|brain-?stem|third-ventricle|fourth-ventricle|fornix", re.I)

_DTYPES = {2: "u1", 4: "<i2", 8: "<i4", 16: "<f4", 64: "<f8", 256: "i1", 512: "<u2", 768: "<u4"}


def _labels_and_world_x(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """``(label per labelled voxel, its world x in mm)`` from a gzipped NIfTI-1."""
    raw = gzip.decompress(path.read_bytes())
    dim = struct.unpack_from("<8h", raw, 40)
    datatype = struct.unpack_from("<h", raw, 70)[0]
    vox_offset = int(struct.unpack_from("<f", raw, 108)[0]) or 352
    sform_code = struct.unpack_from("<h", raw, 254)[0]
    assert sform_code > 0, f"{path.name} has no sform"
    srow_x = np.array(struct.unpack_from("<4f", raw, 280), dtype=np.float64)
    shape = tuple(dim[1:4])
    data = np.frombuffer(raw, dtype=_DTYPES[datatype], count=int(np.prod(shape)), offset=vox_offset)
    data = data.reshape(shape, order="F")
    ijk = np.argwhere(data > 0)
    x = ijk @ srow_x[:3] + srow_x[3]
    return np.rint(data[tuple(ijk.T)]).astype(int), x


def _names(lut: Path) -> dict[int, str]:
    out = {}
    for line in lut.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            out[int(parts[0])] = parts[1]
    return out


def _entries() -> list[dict]:
    return json.loads((RESOURCES / "manifest.json").read_text())["atlases"]


@pytest.mark.unit
def test_there_are_atlases_to_check():
    assert len(_entries()) >= 7


@pytest.mark.unit
@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_no_label_spans_both_hemispheres_except_midline_anatomy(entry):
    labels, x = _labels_and_world_x(RESOURCES / entry["file"])
    names = _names(RESOURCES / entry["labels"])
    bilateral = []
    for value in np.unique(labels):
        mask = labels == value
        left = int((x[mask] < -2).sum())
        right = int((x[mask] > 2).sum())
        if min(left, right) > 0.01 * mask.sum():
            name = names.get(int(value), f"label {value}")
            if not MIDLINE.search(name):
                bilateral.append(f"{value} {name}")
    assert bilateral == [], f"{entry['id']}: labels on both sides of x = 0: {bilateral}"
