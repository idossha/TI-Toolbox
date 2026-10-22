"""Cortical region export writes exactly the regions asked for, or refuses by name.

What this pins (2026-10-22): ``RegionConfig.regions`` -- "Region names to export. Empty means all
regions." (its docstring) -- with a non-empty list exports only those regions. A name that
matches no atlas key (wrong case ``lh.Insula``, a name from another atlas) used to empty the
selection, and the export loop read an empty selection as "no filter" and wrote EVERY region.
Now it is a ``ValueError`` naming the unmatched entries and listing the available keys, raised
before any region is written. A bare ``insula`` still expands to both hemispheres
(``_resolve_selected``'s docstring) and ``lh.insula`` exports exactly one.

Where the expected values come from: the atlas keys are the four this fake atlas holds; the
expected export sets follow from the docstrings above, not from the exporter. Both the STL and
the PLY path run every case.

Host leg (``read_msh``/``atlas2subject`` replaced by fakes; the per-region writers record names).
Reproduce: ``.venv/bin/python -m pytest tests/test_blender_region_selection.py -q -p no:cacheprovider``
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from tit.blender import region_exporter
from tit.blender.config import RegionConfig

pytestmark = pytest.mark.unit

N_LH = N_RH = 6
KEYS = {"lh.insula", "lh.precentral", "rh.insula", "rh.precentral"}


def _mask(n: int, idx: list[int]) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    m[idx] = True
    return m


@pytest.fixture
def exported(monkeypatch, tmp_path):
    """Run one format's export with fakes; return ``run(fmt, regions) -> names written``."""
    field = SimpleNamespace(value=np.full(N_LH + N_RH, 0.5))
    mesh = SimpleNamespace(field={"TI_max": field})
    monkeypatch.setattr(region_exporter, "read_msh", lambda path: mesh)
    monkeypatch.setattr(
        region_exporter,
        "atlas2subject",
        lambda m2m, atlas, split_labels=True: {
            "lh": {"insula": _mask(N_LH, [0, 1]), "precentral": _mask(N_LH, [2, 3])},
            "rh": {"insula": _mask(N_RH, [0, 1]), "precentral": _mask(N_RH, [4, 5])},
        },
    )
    written: list[str] = []

    def record(mesh, atlas, region_name, *args, **kwargs):
        written.append(region_name)
        return True

    monkeypatch.setattr(region_exporter, "_export_region_stl", record)
    monkeypatch.setattr(region_exporter, "_export_region_ply", record)

    def run(fmt: str, regions: list[str]) -> list[str]:
        written.clear()
        cfg = RegionConfig(
            subject_id="001",
            simulation_name="sim",
            format=fmt,
            regions=regions,
            skip_whole_gm=True,
        )
        cfg.output_dir = str(tmp_path / fmt)
        cfg.m2m_dir = str(tmp_path / "m2m_001")
        if fmt == "stl":
            region_exporter._run_stl_export(cfg, "surface.msh")
        else:
            region_exporter._run_ply_export(cfg, "surface.msh")
        return list(written)

    run.written = written
    return run


FORMATS = ["stl", "ply"]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    "regions, unmatched",
    [
        (["lh.Insula"], "lh.Insula"),  # wrong case
        (["lh.nonexistent"], "lh.nonexistent"),  # not in this atlas
        (["lh.insula", "G_front_sup"], "G_front_sup"),  # one typo among good names
    ],
)
def test_unmatched_names_refuse_by_name_and_export_nothing(
    exported, fmt, regions, unmatched
):
    with pytest.raises(ValueError) as info:
        exported(fmt, regions)
    message = str(info.value)
    assert repr(unmatched) in message
    for key in KEYS:  # the available keys are listed, so the user can correct the name
        assert key in message
    # Nothing was written -- the run did not reach a single region writer.
    assert exported.written == []


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_bare_name_selects_both_hemispheres(exported, fmt):
    assert sorted(exported(fmt, ["insula"])) == ["lh.insula", "rh.insula"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_hemisphere_key_selects_exactly_one_region(exported, fmt):
    assert exported(fmt, ["lh.insula"]) == ["lh.insula"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_an_empty_list_exports_every_region(exported, fmt):
    assert sorted(exported(fmt, [])) == sorted(KEYS)


def test_resolve_selected_lists_every_unmatched_entry():
    with pytest.raises(ValueError) as info:
        region_exporter._resolve_selected(["lh.Insula", "insula", "foo"], KEYS)
    message = str(info.value)
    assert "'lh.Insula'" in message and "'foo'" in message
    assert "'insula'" not in message.split("Available")[0]
