"""The image's bundled nilearn atlases load offline from a read-only cache, as built (p35).

Pins, 2026-10-22. ``container/blueprint/Dockerfile.ti-toolbox`` runs
``tit/plotting/nilearn/atlases.py --prune`` with ``NILEARN_DATA=/opt/nilearn_data``: it
fetches the four outline atlases, checks their sha256 and deletes every other NIfTI the
archives unpacked plus empty directories. This guards that step. With the network blocked,
for every key of :data:`tit.plotting.nilearn.atlases.ATLASES`:

1. ``atlas_path(key)`` resolves inside ``$NILEARN_DATA`` (the fetcher found the file and
   downloaded nothing);
2. the file's sha256, computed here with :mod:`hashlib`, is the one in the table;
3. the label image is integer-valued with its largest label below 200, the contour levels
   ``range(1, 200)`` that ``NilearnVisualizer._create_multi_slice_plot_with_atlas`` draws;
4. it has the published number of regions: Harvard-Oxford cortical 48 and subcortical 21
   (FSL's atlas XML), Schaefer 2018 100 parcels (the 100-parcel release), AAL3v2 at least
   166 non-zero labels (Rolls et al. 2020: 170 labels, four of them empty);
5. ``NilearnVisualizer._load_atlas(key)`` returns an image and prints no "skipped".

And the cache itself: no empty directory survived the prune (a fetch would try to delete
it, a write), and loading every atlas writes nothing under it (paths and mtimes compared),
so a read-only cache cannot matter. Jobs run as root in the image, where ``os.access``
always says writable; the literal not-writable check runs only for a non-root user.

Skips with a reason when ``/opt/nilearn_data`` is absent: images up to
idossha/ti-toolbox:v3.1.1 predate the bundled atlases.
Run in the image: ``docker run --rm -v <tree>:/ti-toolbox -w /ti-toolbox
idossha/ti-toolbox:<tag> -lc 'simnibs_python -m pytest tests/numerical/test_nilearn_offline_atlases.py -q -p no:cacheprovider'``.
Verified 2026-10-22 on v3.1.1 with the Dockerfile step reproduced in a throwaway container
for the three atlases whose hosts answered (www.gin.cnrs.fr, AAL3's, refused connections).
"""

from __future__ import annotations

import hashlib
import importlib
import os
import socket
import sys
from pathlib import Path

import numpy as np
import pytest

_BUNDLED = Path("/opt/nilearn_data")
pytestmark = pytest.mark.skipif(
    not _BUNDLED.is_dir(),
    reason="skipping: image predates the bundled nilearn atlases (/opt/nilearn_data absent)",
)

#: Published region counts (see the module docstring); AAL3v2 is a lower bound.
_REGIONS = {"harvard_oxford": 48, "harvard_oxford_sub": 21, "schaefer_2018": 100}
_AAL3_MIN = 166
_SWAP = ("nilearn", "pandas", "joblib", "sklearn")


def _root(key: str) -> str:
    return key.split(".")[0]


def _blocked(*_args, **_kwargs):
    raise OSError("network blocked by test_nilearn_offline_atlases")


@pytest.fixture(scope="module")
def atlases(real_numeric_stack):
    """Real nilearn, ``atlases`` and ``visualizer`` bound to it, NILEARN_DATA, no network."""
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if _root(k) in _SWAP}
    names = ("tit.plotting.nilearn.atlases", "tit.plotting.nilearn.visualizer")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("NILEARN_DATA", str(_BUNDLED))
        mp.setattr(socket.socket, "connect", _blocked)
        mp.setattr(socket, "getaddrinfo", _blocked)
        try:
            importlib.import_module("nilearn.datasets")
            mods = [importlib.reload(importlib.import_module(n)) for n in names]
            yield {"atlases": mods[0], "visualizer": mods[1]}
        finally:
            for key in [k for k in sys.modules if _root(k) in _SWAP]:
                del sys.modules[key]
            sys.modules.update(saved)
            for name in names:
                try:
                    importlib.reload(sys.modules[name])
                except Exception:  # pragma: no cover - restoring the mocked stack
                    pass


def _keys():
    from tit.plotting.nilearn.atlases import ATLASES

    return sorted(ATLASES)


def test_every_atlas_key_is_checked():
    assert set(_keys()) == {*_REGIONS, "aal"}


@pytest.mark.parametrize("key", _keys())
def test_the_atlas_resolves_in_the_cache_with_its_recorded_checksum(atlases, key):
    path = Path(os.path.realpath(atlases["atlases"].atlas_path(key)))
    assert path.is_relative_to(_BUNDLED.resolve()), path
    expected = atlases["atlases"].ATLASES[key][4]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("key", _keys())
def test_the_label_image_has_integer_labels_below_200_and_its_regions(atlases, key):
    import nibabel as nib

    data = np.asarray(nib.load(atlases["atlases"].atlas_path(key)).get_fdata())
    assert np.array_equal(data, np.round(data)), "labels are not integers"
    assert data.min() >= 0 and data.max() < 200
    regions = np.unique(data[data > 0]).size
    if key == "aal":
        assert regions >= _AAL3_MIN
    else:
        assert regions == _REGIONS[key]


@pytest.mark.parametrize("key", _keys())
def test_the_visualizer_loads_it_without_skipping(atlases, key, capsys):
    img, name = atlases["visualizer"].NilearnVisualizer()._load_atlas(key)
    out = capsys.readouterr().out
    assert img is not None and name == atlases["atlases"].ATLASES[key][0], out
    assert "skipped" not in out


def test_the_prune_left_no_empty_directories():
    empty = [
        str(root)
        for root, dirs, files in os.walk(_BUNDLED)
        if not dirs and not files and Path(root) != _BUNDLED
    ]
    assert empty == []


def _tree(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in [root, *root.rglob("*")]}


def test_loading_every_atlas_writes_nothing_to_the_cache(atlases):
    before = _tree(_BUNDLED)
    for key in _keys():
        atlases["atlases"].atlas_path(key)
        img, _ = atlases["visualizer"].NilearnVisualizer()._load_atlas(key)
        assert img is not None, key
    assert _tree(_BUNDLED) == before


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="skipping: running as root, which can write anywhere; the no-writes test "
    "above covers the read-only cache",
)
def test_the_cache_is_read_only_for_a_non_root_user():
    writable = [
        str(root) for root, _, _ in os.walk(_BUNDLED) if os.access(root, os.W_OK)
    ]
    assert writable == []
