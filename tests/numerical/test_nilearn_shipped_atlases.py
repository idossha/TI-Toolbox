"""Nilearn Visuals outlines atlases TI-Toolbox ships in resources/atlas/, with no download.

Pins, 2026-10-23. Up to v3.1.2 the image build fetched the outline atlases with nilearn into
``/opt/nilearn_data``; now :func:`tit.plotting.nilearn.atlases.atlas_path` returns label
volumes the repository already ships for ROI picking. For every key of
:data:`~tit.plotting.nilearn.atlases.ATLASES`:

1. the keys are the three saved configs name (``harvard_oxford``, ``harvard_oxford_sub``,
   ``schaefer_2018``);
2. ``atlas_path(key)`` is the file ``resources/atlas/manifest.json`` lists under that
   atlas's ``id``, read here with :mod:`json`, and the file exists;
3. the volume (real nibabel) holds integer labels, and its non-zero label values are exactly
   the non-zero indices of the label table the manifest names (its ``labels`` file, parsed
   here), so every region drawn has a name and no named region is missing;
4. that is the published region count: Harvard-Oxford cortical, lateralized, 48 structures x
   2 hemispheres = 96 (FSL's HarvardOxford-Cortical-Lateralized.xml); Harvard-Oxford
   subcortical 21 (FSL's HarvardOxford-Subcortical.xml); Schaefer 2018, 400 parcels (CBIG's
   400-parcel release) -- and the manifest's ``regions`` says the same;
5. ``atlas_path`` opens no socket and imports no nilearn: with ``socket`` patched to raise
   and ``nilearn`` unimportable, every key still resolves.

Needs only real numpy/nibabel (``host_numerical``); the host suite mocks nibabel.
Reproduce:
  host:      ``.venv/bin/python -m pytest tests/numerical/test_nilearn_shipped_atlases.py -q -m host_numerical``
  container: ``simnibs_python -m pytest tests/numerical/test_nilearn_shipped_atlases.py -q``
Deliberately elsewhere: the outlines drawn on a real field
(``tests/numerical/test_nilearn_render_realdata.py``), the panel offering exactly these keys
(``tests/test_nilearn_visuals.py``), the manifest's own rules (``tests/test_atlas_manifest.py``).
"""

from __future__ import annotations

import json
import os
import socket
import sys

import numpy as np
import pytest

from tit.atlas.constants import mni_resources_dir
from tit.plotting.nilearn.atlases import ATLASES, atlas_path

pytestmark = pytest.mark.host_numerical

#: Published region counts (see the module docstring).
_REGIONS = {"harvard_oxford": 96, "harvard_oxford_sub": 21, "schaefer_2018": 400}


def _manifest_entry(key: str) -> dict:
    with open(
        os.path.join(mni_resources_dir(), "manifest.json"), encoding="utf-8"
    ) as f:
        entries = json.load(f)["atlases"]
    (entry,) = [e for e in entries if e["id"] == ATLASES[key][1]]
    return entry


def _table_labels(path: str) -> set[int]:
    """The non-zero indices of a FreeSurfer-style label table (``index name R G B A``)."""
    labels = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            fields = line.split()
            if fields and not fields[0].startswith("#") and int(fields[0]) != 0:
                labels.add(int(fields[0]))
    return labels


def test_the_keys_are_the_ones_saved_configs_name():
    assert set(ATLASES) == set(_REGIONS)


@pytest.mark.parametrize("key", sorted(_REGIONS))
def test_the_path_is_the_manifests_file_in_resources(key):
    entry = _manifest_entry(key)
    path = atlas_path(key)
    assert path == os.path.join(mni_resources_dir(), entry["file"])
    assert os.path.isfile(path)


@pytest.mark.parametrize("key", sorted(_REGIONS))
def test_the_volume_has_integer_labels_and_exactly_its_tables_regions(key):
    import nibabel as nib

    entry = _manifest_entry(key)
    data = np.asanyarray(nib.load(atlas_path(key)).dataobj)
    assert data.ndim == 3
    assert np.array_equal(data, np.round(data)), "labels are not integers"
    assert data.min() == 0
    in_volume = {int(v) for v in np.unique(data[data > 0])}
    in_table = _table_labels(os.path.join(mni_resources_dir(), entry["labels"]))
    assert in_volume == in_table
    assert len(in_table) == _REGIONS[key] == entry["regions"]


def test_atlas_path_opens_no_socket_and_imports_no_nilearn(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("atlas_path reached for the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for name in [m for m in sys.modules if m.split(".")[0] == "nilearn"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "nilearn", None)  # any import of it raises

    for key in sorted(_REGIONS):
        assert os.path.isfile(atlas_path(key)), key
