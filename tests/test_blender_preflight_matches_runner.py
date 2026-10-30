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
``documentation/config.json``; (f) an mTI run without its central surface; (g) a run whose
recorded net has no CSV in the subject's eeg_positions; (h) a run whose record has
``conductivity: null``; (i) a run on a subject without ``m2m/segmentation/labeling.nii.gz`` (the
sub-cortical default volume); (j) a simulation that does not exist; (k) a run with neither its
TI volume mesh nor any high-frequency mesh (nothing to cut the montage's scalp from). An explicit
sub-cortical ``nifti_path`` that is not there, and which mesh the montage cuts its scalp from
(the run's TI mesh; an mTI run's first carrier), are pinned below the table.

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


def _no_labeling_tree(sim: Path) -> None:
    from tit.paths import get_path_manager

    _ti_tree(sim)
    (Path(get_path_manager().m2m(SID)) / "segmentation" / "labeling.nii.gz").unlink()


def _no_volume_mesh_tree(sim: Path) -> None:
    _ti_tree(sim, hf=False)
    (sim / "TI" / "mesh" / f"{sim.name}_TI.msh").unlink()


TREES = {
    "a_labelled": lambda sim: _ti_tree(sim),
    "b_xyz": lambda sim: _ti_tree(sim, record=XYZ),
    "c_mti": lambda sim: _mti_tree(sim),
    "d_no_hf": lambda sim: _ti_tree(sim, hf=False),
    "e_no_config": lambda sim: _ti_tree(sim, record=None),
    "f_mti_no_surface": lambda sim: _mti_tree(sim, surface=False),
    # A net the subject's eeg_positions has no CSV for (the fixture writes only NET).
    "g_net_csv_missing": lambda sim: _ti_tree(
        sim, record={**LABELLED, "eeg_net": "GSN-HydroCel-256.csv"}
    ),
    "h_no_conductivity": lambda sim: _ti_tree(
        sim, record={**LABELLED, "conductivity": None}
    ),
    "i_no_labeling": _no_labeling_tree,
    "j_ghost": lambda sim: None,  # named, never run
    "k_no_volume_mesh": _no_volume_mesh_tree,
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
    import tit.volume_fields

    def convert(sim, mesh, base, space, fields):  # the on-demand NIfTI, as SimNIBS names it
        token = "MNI_MNI" if space == "mni" else "subject"
        for f in fields:
            _touch(sim.niftis_dir / f"{base}_{token}_{f}.nii.gz")

    monkeypatch.setattr(tit.volume_fields, "_write_niftis", convert)
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
    ("g_net_csv_missing", "MontageConfig"): True,  # the net's electrode positions
    ("g_net_csv_missing", "VectorConfig"): False,  # vectors never read the net
    ("h_no_conductivity", "VectorConfig"): True,  # it spells the carrier meshes' names
    ("h_no_conductivity", "MontageConfig"): False,
    ("h_no_conductivity", "RegionConfig"): False,
    ("i_no_labeling", "SubcorticalConfig"): True,  # its default volume
    ("i_no_labeling", "RegionConfig"): False,
    ("i_no_labeling", "MontageConfig"): False,
    ("j_ghost", "RegionConfig"): True,
    ("j_ghost", "VectorConfig"): True,
    ("j_ghost", "MontageConfig"): True,
    ("j_ghost", "SubcorticalConfig"): True,  # named, so a field-coloured PLY was asked for
    ("k_no_volume_mesh", "MontageConfig"): True,  # no tetrahedral mesh holds the scalp
    ("k_no_volume_mesh", "RegionConfig"): False,
    ("k_no_volume_mesh", "SubcorticalConfig"): False,
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


def test_an_explicit_nifti_path_that_does_not_exist_is_found_and_refused(project):
    """A sub-cortical export pointed at a volume that is not there: both sides name it."""
    from tit.blender.subcortical_exporter import run_subcortical

    nifti = str(project / "atlases" / "aseg.nii.gz")
    config = {**_config("SubcorticalConfig", ""), "nifti_path": nifti}
    found = preflight("blender", config, str(project))
    assert [m.expected_path for m in found] == [nifti]
    with pytest.raises(ValueError, match="NIfTI file not found") as refused:
        run_subcortical(SubcorticalConfig(SID, nifti_path=nifti))
    assert nifti in str(refused.value)
    assert _written(project) == []


def test_montage_without_a_volume_mesh_names_the_runs_ti_mesh(project):
    """The canonical mesh is named; the high-frequency meshes are the fallback it says."""
    sim = project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / "Bare"
    TREES["k_no_volume_mesh"](sim)
    (found,) = preflight("blender", _config("MontageConfig", "Bare"), str(project))
    assert found.expected_path == str(sim / "TI" / "mesh" / "Bare_TI.msh")
    assert "high_Frequency/mesh" in found.what


@pytest.mark.parametrize(
    "tree, source",
    [
        # tit/sim writes TI/mesh/<sim>_TI.msh; the scene cuts the scalp from it.
        ("a_labelled", "TI/mesh/a_labelled_TI.msh"),
        # An mTI run has no TI mesh; its first carrier (A) holds the same head.
        ("c_mti", f"high_Frequency/mesh/{SID}_TDCS_A_scalar.msh"),
    ],
)
def test_montage_cuts_the_scalp_from_the_runs_own_volume_mesh(
    project, monkeypatch, tree, source
):
    sim = project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / tree
    TREES[tree](sim)  # a_labelled also holds TDCS_1/2, which a sorted search finds first
    _patch_heavy_io(monkeypatch)
    cut: list[str] = []

    def scalp(path, skin_tag=1005):
        cut.append(str(path))
        return np.eye(3), np.array([[0, 1, 2]])

    monkeypatch.setattr(montage_publication.be_utils, "extract_scalp_from_msh", scalp)
    assert _run("MontageConfig", tree) is None
    assert cut[0] == str(sim / source)
