"""Blender preflight reports exactly the inputs each export mode's runner would fail on.

What this pins (2026-10-22): ``preflight("blender", cfg)`` -- the check ``POST /api/jobs``
answers 422 with before a job exists -- returns a finding exactly when that mode's runner
raises on a missing or unusable input, naming the path the runner names; and a runner that
refuses does so before it writes a file. Before this, ``_check_blender`` only checked that the
simulation folder existed: a montage of an XYZ (free-hand) simulation was queued and died with
``KeyError 'eeg_net'`` after writing its STLs, and an mTI simulation passed preflight and failed
reading the TI surface it never wrote.

Where the expected values come from: the RUNNER is the oracle. Each mode's own entry point runs
with only the heavy I/O replaced (``read_msh``, ``atlas2subject``, the Blender subprocess, the
meshing calls) and its outcome is recorded; preflight must agree with it. A handful of outcomes
the spec fixes regardless of either side (an XYZ montage refuses; an mTI region export runs;
vectors need the carrier meshes and the run's config.json) are asserted outright, so two sides
that drift together still fail.

Simulation trees: (a) a labelled 2-pair run; (b) an XYZ run, with the ``config.json`` shape of
Dataset 000 ``sub-101/20260919_131736_879_1`` (``eeg_net: null``, coordinate pairs); (c) an mTI
run; (d) a 2-pair run without its high-frequency meshes; (e) a 2-pair run without
``documentation/config.json``; (f) an mTI run without its central surface.

Host leg. Reproduce:
``.venv/bin/python -m pytest tests/test_blender_preflight_matches_runner.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.blender import montage_publication, region_exporter, vector_field_exporter
from tit.blender.config import (
    MontageConfig,
    RegionConfig,
    SubcorticalConfig,
    VectorConfig,
)
from tit.jobs.preflight import preflight

pytestmark = pytest.mark.unit

SID = "001"
NET = "GSN-HydroCel-185.csv"


class _Reached(Exception):
    """The runner got past every input it opens; the next step is real computation."""


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _write_config(sim: Path, record: dict) -> None:
    doc = sim / "documentation" / "config.json"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(json.dumps(record))


LABELLED = {
    "simulation_mode": "TI",
    "montage_mode": "net",
    "eeg_net": NET,
    "conductivity": "scalar",
    "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
}
#: sub-101/20260919_131736_879_1's documentation/config.json keys that matter here.
XYZ = {
    "simulation_mode": "TI",
    "montage_mode": "flex_free",
    "eeg_net": None,
    "conductivity": "scalar",
    "electrode_pairs": [
        [[72.1, 10.5, -19.1], [75.6, 0.9, -24.3]],
        [[-80.0, 19.2, -78.6], [-77.3, 30.0, -73.3]],
    ],
    "is_xyz_montage": True,
}


def _ti_tree(sim: Path, *, hf: bool = True, record: dict | None = LABELLED) -> None:
    name = sim.name
    _touch(sim / "TI" / "mesh" / f"{name}_TI.msh")
    _touch(sim / "TI" / "mesh" / "surfaces" / f"{name}_TI_central.msh")
    _touch(sim / "TI" / "niftis" / f"{name}_TI_subject_TI_max.nii.gz")
    if hf:
        for i in (1, 2):
            _touch(sim / "high_Frequency" / "mesh" / f"{SID}_TDCS_{i}_scalar.msh")
    if record is not None:
        _write_config(sim, record)


def _mti_tree(sim: Path, *, surface: bool = True) -> None:
    name = sim.name
    _touch(sim / "mTI" / "mesh" / f"{name}_mTI.msh")
    (sim / "TI" / "mesh" / "surfaces").mkdir(parents=True)
    if surface:
        _touch(sim / "mTI" / "mesh" / "surfaces" / f"{name}_mTI_central.msh")
    for c in "ABCD":
        _touch(sim / "high_Frequency" / "mesh" / f"{SID}_TDCS_{c}_scalar.msh")
    _write_config(sim, {**LABELLED, "simulation_mode": "mTI"})


TREES = {
    "a_labelled": lambda sim: _ti_tree(sim),
    "b_xyz": lambda sim: _ti_tree(sim, record=XYZ),
    "c_mti": lambda sim: _mti_tree(sim),
    "d_no_hf": lambda sim: _ti_tree(sim, hf=False),
    "e_no_config": lambda sim: _ti_tree(sim, record=None),
    "f_mti_no_surface": lambda sim: _mti_tree(sim, surface=False),
}
MODES = ["RegionConfig", "VectorConfig", "MontageConfig", "SubcorticalConfig"]


@pytest.fixture
def project(init_pm, tmp_project):
    m2m = Path(init_pm.m2m(SID))
    _touch(m2m / f"{SID}.msh")
    _touch(m2m / "segmentation" / "labeling.nii.gz")
    net = Path(init_pm.eeg_positions(SID)) / NET
    net.parent.mkdir(parents=True, exist_ok=True)
    net.write_text("Electrode,0,0,90,E1\nElectrode,40,0,80,E2\nElectrode,-40,0,80,E3\n")
    return tmp_project


def _patch_heavy_io(monkeypatch) -> None:
    """Replace what reads mesh/volume CONTENT or starts Blender; path logic stays real."""
    surface = SimpleNamespace(field={"TI_max": None, "mTI_max": None})
    monkeypatch.setattr(region_exporter, "read_msh", lambda path: surface)

    def atlas(*args, **kwargs):
        raise _Reached("atlas2subject")

    monkeypatch.setattr(region_exporter, "atlas2subject", atlas)

    carrier = SimpleNamespace(field={"E": None})

    def barycenters(mesh):
        raise _Reached("barycenters")

    monkeypatch.setattr(
        vector_field_exporter, "_get_surface_face_barycenters", barycenters
    )

    tri = SimpleNamespace(
        elm=SimpleNamespace(
            elm_type=np.array([2]), node_number_list=np.array([[1, 2, 3, 0]])
        ),
        nodes=SimpleNamespace(node_coord=np.eye(3)),
    )
    import simnibs  # the host conftest's mock, shared by the vector and montage modules

    monkeypatch.setattr(
        simnibs, "read_msh", lambda path: carrier if "_TDCS_" in str(path) else tri
    )
    monkeypatch.setattr(
        montage_publication.be_utils,
        "extract_scalp_from_msh",
        lambda path, skin_tag=1005: (np.eye(3), np.array([[0, 1, 2]])),
    )
    monkeypatch.setattr(montage_publication, "read_electrodes", lambda path: iter([]))

    def blender(*args, **kwargs):
        raise _Reached("blender")

    monkeypatch.setattr(montage_publication.subprocess, "run", blender)

    import tit.tools.nifti_to_mesh as n2m

    monkeypatch.setattr(
        n2m,
        "nifti_to_mesh",
        lambda i, o, **k: {
            "output_file": o,
            "vertices": 3,
            "faces": 1,
            "removed_components": 0,
        },
    )
    monkeypatch.setattr(
        n2m,
        "nifti_to_field_ply",
        lambda m, f, o, **k: {
            "output_file": o,
            "vertices": 3,
            "faces": 1,
            "field_min": 0.0,
            "field_max": 1.0,
        },
    )


def _config(mode: str, sim: str) -> dict:
    return {"_type": mode, "subject_id": SID, "simulation_name": sim}


def _run(mode: str, sim: str) -> BaseException | None:
    """The mode's runner on *sim*; the exception it refuses with, or None."""
    from tit.blender.montage_publication import run_montage
    from tit.blender.region_exporter import run_regions
    from tit.blender.subcortical_exporter import run_subcortical
    from tit.blender.vector_field_exporter import run_vectors

    runners = {
        "RegionConfig": lambda: run_regions(RegionConfig(SID, sim, format="stl")),
        "VectorConfig": lambda: run_vectors(VectorConfig(SID, sim)),
        "MontageConfig": lambda: run_montage(MontageConfig(SID, sim)),
        "SubcorticalConfig": lambda: run_subcortical(SubcorticalConfig(SID, sim)),
    }
    try:
        runners[mode]()
    except _Reached:
        return None
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        return exc
    return None


def _written(project: Path) -> list[Path]:
    root = project / "derivatives" / "ti-toolbox" / "visual_exports"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("tree", sorted(TREES))
def test_preflight_finds_something_exactly_when_the_runner_refuses(
    project, monkeypatch, tree, mode
):
    sim = tree
    TREES[tree](
        project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / sim
    )
    _patch_heavy_io(monkeypatch)

    found = preflight("blender", _config(mode, sim), str(project))
    refusal = _run(mode, sim)

    assert bool(found) == (
        refusal is not None
    ), f"{tree} x {mode}: preflight {[m.to_dict() for m in found]}; runner {refusal!r}"
    if refusal is not None:
        named = [m.expected_path for m in found if m.expected_path in str(refusal)]
        assert named, f"{tree} x {mode}: runner names none of {found} in {refusal!r}"
        assert _written(project) == [], f"{tree} x {mode}: wrote before refusing"


#: Outcomes the spec fixes on its own (True = the runner refuses / preflight finds something).
SPEC = {
    ("a_labelled", "RegionConfig"): False,
    ("a_labelled", "VectorConfig"): False,
    ("a_labelled", "MontageConfig"): False,
    ("a_labelled", "SubcorticalConfig"): False,
    ("b_xyz", "MontageConfig"): True,  # no recorded net to place
    ("b_xyz", "RegionConfig"): False,  # regions never read the net
    ("c_mti", "RegionConfig"): False,
    ("c_mti", "VectorConfig"): False,
    ("c_mti", "MontageConfig"): False,
    ("d_no_hf", "VectorConfig"): True,  # vectors interpolate the carrier fields
    ("d_no_hf", "RegionConfig"): False,
    ("e_no_config", "VectorConfig"): True,  # conductivity names the carrier meshes
    ("e_no_config", "MontageConfig"): True,  # the recorded net and pairs
    ("e_no_config", "RegionConfig"): False,
    ("f_mti_no_surface", "RegionConfig"): True,
    ("f_mti_no_surface", "VectorConfig"): True,
    ("f_mti_no_surface", "SubcorticalConfig"): False,  # volumes, not surfaces
}


@pytest.mark.parametrize("case", sorted(SPEC), ids=lambda c: f"{c[0]}-{c[1]}")
def test_spec_outcomes(project, monkeypatch, case):
    tree, mode = case
    TREES[tree](
        project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / tree
    )
    _patch_heavy_io(monkeypatch)
    assert bool(preflight("blender", _config(mode, tree), str(project))) is SPEC[case]
    assert (_run(mode, tree) is not None) is SPEC[case]


def test_xyz_montage_finding_says_why(project):
    TREES["b_xyz"](
        project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / "b_xyz"
    )
    (found,) = preflight("blender", _config("MontageConfig", "b_xyz"), str(project))
    assert "This simulation has no recorded EEG net." in found.what
    assert found.expected_path.endswith("b_xyz/documentation/config.json")


@pytest.mark.parametrize("mode", ["RegionConfig", "VectorConfig", "MontageConfig"])
def test_mti_preflight_names_the_mti_surface_and_only_it(project, mode):
    """The one file an mTI run without its surface lacks, spelled from the mTI layout."""
    sim = project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / "Deep"
    TREES["f_mti_no_surface"](sim)
    found = preflight("blender", _config(mode, "Deep"), str(project))
    assert [m.expected_path for m in found] == [
        str(sim / "mTI" / "mesh" / "surfaces" / "Deep_mTI_central.msh")
    ]
