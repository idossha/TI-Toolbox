"""Space, tissue and field of a simulation NIfTI never depend on what the simulation is called.

What this pins (2026-10-22, package p04 "nifti-space-classifier")
    Simulation names are free text under ``tit.paths.NAME_RE``, so ``MNI_target``,
    ``hippo_MNI``, ``grey_matter`` or ``TDCS_vs_TI`` are legal. Readers used to classify a
    simulation NIfTI by substrings anywhere in its name: ``"_MNI" in name`` meant MNI space,
    a ``grey_`` start meant grey matter, ``"TDCS" in name`` meant a carrier. For those names
    the voxel analyzer raised ``FileNotFoundError`` although the subject-space file existed,
    the preflight called it missing, the catalog listed subject files as MNI, and the viewer
    put them in the wrong scene or dropped the TI_max layer. One table of names runs here
    against every reader: ``select_field_file``, the preflight, ``catalog`` (space and
    tissue), ``viewspec._in_space``, ``viewspec._ti_max_layers`` and ``viewspec._hf_layers``.

Where the expected values come from
    The writer's naming rule (``tests/test_sim_output_naming_contract.py``, checked against
    Dataset 000 there): ``<tissue_><sim>_<TI|mTI>_subject_<field>.nii.gz`` is the subject
    file, ``..._MNI_MNI_<field>.nii.gz`` the MNI copy, ``grey_``/``white_``/none is GM/WM/both.

Reproduce
    .venv/bin/python -m pytest tests/test_nifti_space_classifier.py -q -p no:cacheprovider

Deliberately elsewhere
    Field names in the catalog listing: ``tests/test_catalog_sim_fields.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.test_sim_output_naming_contract import (
    carrier_labels,
    envelope_base,
    nifti_name,
    write_simulation,
)
from tit import catalog
from tit.paths import get_path_manager, is_valid_name

#: Legal names (``tit.paths.NAME_RE``) that contain a token some reader matched on.
SIM_NAMES = (
    "plain",
    "MNI_target",
    "hippo_MNI",
    "x_MNI_MNI_y",
    "grey_matter",
    "white_x",
    "L_MNI_target",
    "MNI",
    "TDCS_vs_TI",
    "subject_A",
    "TI",
)
TISSUES = {"GM": "grey", "WM": "white", "both": None}


def test_the_names_are_legal_simulation_names():
    assert all(is_valid_name(name) for name in SIM_NAMES)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("sim", SIM_NAMES)
def test_voxel_selection_and_preflight_pick_the_subject_file(project, sim, mode):
    from tit.analyzer.field_selector import select_field_file
    from tit.jobs.preflight import _analyzer_field

    write_simulation(project, "101", sim, mode)
    niftis = Path(get_path_manager().simulation("101", sim)) / mode / "niftis"
    envelope = "TI_max" if mode == "TI" else "mTI_max"
    for tissue_type, tissue in TISSUES.items():
        for field in (None, "TI_max", "hf_peak"):
            want = envelope if field in (None, "TI_max") else field
            expected = niftis / nifti_name(
                envelope_base(sim, mode, tissue), "subject", want
            )
            path, name = select_field_file(
                "101", sim, "voxel", tissue_type=tissue_type, field=field
            )
            assert (path, name) == (expected, want), (tissue_type, field)
            config = {"tissue_type": tissue_type, "field": field}
            assert (
                _analyzer_field(get_path_manager(), "101", sim, "voxel", config) == []
            )


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("sim", SIM_NAMES)
def test_catalog_and_viewer_agree_with_the_writer_on_space_and_tissue(
    project, sim, mode
):
    from tit.viewspec import _hf_layers, _in_space, _ti_max_layers

    written = write_simulation(project, "101", sim, mode)
    detail = catalog.simulation_detail(get_path_manager(), "101", sim)
    listed = {n["path"]: n for n in detail["niftis"]}
    envelope = "TI_max" if mode == "TI" else "mTI_max"

    for (tissue, space, field), path in written["envelope"].items():
        entry = listed[str(path)]
        assert (entry["space"], entry["tissue"], entry["field"]) == (
            space,
            tissue,
            field,
        )
        for scene in ("subject", "mni"):
            assert _in_space(path.name, scene, is_mesh=False) is (scene == space)

    for scene in ("subject", "mni"):
        layers = _ti_max_layers(str(written["sim_dir"]), scene)
        assert {layer["path"] for layer in layers} == {
            str(written["envelope"][(tissue, scene, envelope)])
            for tissue in TISSUES.values()
        }
        visible = [layer["path"] for layer in layers if layer["visible"]]
        assert visible == [str(written["envelope"][("grey", scene, envelope)])]
        carriers = {
            str(written["hf"][(label, scene)])
            for label in carrier_labels(mode, 2 if mode == "TI" else 4)
        }
        assert {
            layer["path"] for layer in _hf_layers(str(written["sim_dir"]), scene)
        } == carriers
        for path in carriers:
            assert listed[path]["space"] == scene
            assert _in_space(os.path.basename(path), scene, is_mesh=False)


@pytest.mark.parametrize(
    "sid", ["101", "normal01", "TDCS", "MNI152"], ids=lambda s: f"sid-{s}"
)
def test_carrier_space_comes_from_its_trailing_tokens(project, sid):
    """A subject id is part of a carrier's name too (``MNI152_TDCS_1_vn_subject_magnE``)."""
    from tit.viewspec import _in_space

    written = write_simulation(project, sid, "plain", "TI", cond="vn")
    for (label, space), path in written["hf"].items():
        info = catalog.classify_sim_nifti(path.name)
        assert info == {
            "kind": "carrier",
            "field": "magnE",
            "space": space,
            "tissue": None,
        }
        assert _in_space(path.name, "mni", is_mesh=False) is (space == "mni")
