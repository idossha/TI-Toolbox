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
5. ``NilearnVisualizer._load_atlas(key)`` returns that same file and prints no "skipped".

And the cache itself: no empty directory survived the prune (a fetch would try to delete
it, a write), and loading every atlas writes nothing under it (paths and mtimes compared),
so a read-only cache cannot matter. Jobs run as root in the image, where ``os.access``
always says writable; the literal not-writable check runs only for a non-root user.

Why a subprocess: ``tests/conftest.py`` mocks nilearn, pandas, joblib and sklearn in this
interpreter, and real nilearn imports real pandas. Swapping pandas in and out of
``sys.modules`` here broke every later module that imports real pandas
(``test_stats_csv_loaders.py``). The fetchers and ``_load_atlas`` run in
``simnibs_python -c`` (``_SCRIPT``), which reports each key's path and what loading it
printed; the checksums, labels and the cache listing are read here (hashlib, nibabel, os).

Skips with a reason only on an image that predates the bundled atlases -- no
``/opt/nilearn_data`` and no ``NILEARN_DATA=/opt/nilearn_data`` in its environment, as up to
idossha/ti-toolbox:v3.1.1. An image that declares the variable but lacks the directory fails.
Run in the image: ``docker run --rm -v <tree>:/ti-toolbox -w /ti-toolbox
idossha/ti-toolbox:<tag> -lc 'simnibs_python -m pytest tests/numerical/test_nilearn_offline_atlases.py -q -p no:cacheprovider'``.
Verified 2026-10-22 on v3.1.1 with the Dockerfile step reproduced in a throwaway container
for the three atlases whose hosts answered (www.gin.cnrs.fr, AAL3's, refused connections),
so the AAL3 lower bound (166) has not yet been measured against the bundled file.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
_BUNDLED = Path("/opt/nilearn_data")
#: Only an image that predates the cache skips: the Dockerfile step that bundles it also
#: declares ``NILEARN_DATA=/opt/nilearn_data`` (17576be2), so an image that declares it and
#: lacks the directory lost its atlases and fails here.
_PREDATES_THE_BUNDLED_ATLASES = not (
    _BUNDLED.is_dir() or os.environ.get("NILEARN_DATA") == str(_BUNDLED)
)
pytestmark = pytest.mark.skipif(
    _PREDATES_THE_BUNDLED_ATLASES,
    reason="skipping: image predates the bundled nilearn atlases (/opt/nilearn_data absent)",
)

#: Published region counts (see the module docstring); AAL3v2 is a lower bound.
_REGIONS = {"harvard_oxford": 48, "harvard_oxford_sub": 21, "schaefer_2018": 100}
_AAL3_MIN = 166

#: Resolves and loads every atlas with real nilearn, network blocked; argv: facts.json.
_SCRIPT = r"""
import contextlib, io, json, socket, sys

def _blocked(*_args, **_kwargs):
    raise OSError("network blocked by test_nilearn_offline_atlases")

socket.socket.connect = _blocked
socket.getaddrinfo = _blocked

from tit.plotting.nilearn.atlases import ATLASES, atlas_path
from tit.plotting.nilearn.visualizer import NilearnVisualizer

facts = {}
for key in sorted(ATLASES):
    entry = {}
    try:
        entry["path"] = atlas_path(key)
    except Exception as exc:
        entry["path_error"] = f"{type(exc).__name__}: {exc}"
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        img, name = NilearnVisualizer()._load_atlas(key)
    entry.update(image=None if img is None else str(img), name=name,
                 printed=printed.getvalue())
    facts[key] = entry
with open(sys.argv[1], "w") as f:
    json.dump(facts, f)
"""


def _tree(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in [root, *root.rglob("*")]}


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    """Each key's path and load report from a fresh interpreter, and the cache around it."""
    facts = tmp_path_factory.mktemp("atlases") / "facts.json"
    before = _tree(_BUNDLED)
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(facts)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={
            **os.environ,
            "NILEARN_DATA": str(_BUNDLED),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=600,
    )
    log = done.stdout + done.stderr
    assert done.returncode == 0 and facts.is_file(), log[-4000:]
    return {"keys": json.loads(facts.read_text()), "before": before, "log": log}


def _keys():
    from tit.plotting.nilearn.atlases import ATLASES

    return sorted(ATLASES)


def _path(loaded: dict, key: str) -> Path:
    entry = loaded["keys"][key]
    assert "path" in entry, entry.get("path_error")
    return Path(entry["path"])


def test_every_atlas_key_is_checked():
    assert set(_keys()) == {*_REGIONS, "aal"}


@pytest.mark.parametrize("key", _keys())
def test_the_atlas_resolves_in_the_cache_with_its_recorded_checksum(loaded, key):
    from tit.plotting.nilearn.atlases import ATLASES

    path = Path(os.path.realpath(_path(loaded, key)))
    assert path.is_relative_to(_BUNDLED.resolve()), path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ATLASES[key][4]


@pytest.mark.parametrize("key", _keys())
def test_the_label_image_has_integer_labels_below_200_and_its_regions(loaded, key):
    import nibabel as nib

    data = np.asarray(nib.load(str(_path(loaded, key))).get_fdata())
    assert np.array_equal(data, np.round(data)), "labels are not integers"
    assert data.min() >= 0 and data.max() < 200
    regions = np.unique(data[data > 0]).size
    if key == "aal":
        assert regions >= _AAL3_MIN
    else:
        assert regions == _REGIONS[key]


@pytest.mark.parametrize("key", _keys())
def test_the_visualizer_loads_it_without_skipping(loaded, key):
    from tit.plotting.nilearn.atlases import ATLASES

    entry = loaded["keys"][key]
    assert "skipped" not in entry["printed"], entry["printed"]
    assert entry["name"] == ATLASES[key][0], entry["printed"]
    assert entry["image"] == str(_path(loaded, key)), entry["printed"]


def test_the_prune_left_no_empty_directories():
    empty = [
        str(root)
        for root, dirs, files in os.walk(_BUNDLED)
        if not dirs and not files and Path(root) != _BUNDLED
    ]
    assert empty == []


def test_loading_every_atlas_writes_nothing_to_the_cache(loaded):
    assert set(loaded["keys"]) == set(_keys()), "has every atlas loaded to check"
    assert _tree(_BUNDLED) == loaded["before"]


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
