"""Project metadata must not disclose external names, presence or sizes.

Authored temporary trees distinguish root and leaf symlinks; internal aliases are
positive controls. Run: python3 -m pytest tests/test_catalog_metadata_boundaries.py -q
"""

from pathlib import Path

import pytest

from tit import catalog
from tit.jobs import eta
from tit.paths import PathManager


def test_unconfigured_project_has_no_subject_metadata(monkeypatch):
    monkeypatch.delenv("PROJECT_DIR_NAME", raising=False)
    pm = PathManager()
    assert catalog.subject_ids(pm) == []
    assert catalog.list_subjects(pm) == []


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    pm = PathManager(project_dir=str(root))
    Path(pm.m2m("001")).mkdir(parents=True)
    return pm, root, outside


@pytest.mark.parametrize("internal", [False, True])
def test_atlas_directory_alias(tree, internal):
    pm, root, outside = tree
    target = root / "alias-target" if internal else outside
    target.mkdir(exist_ok=True)
    (target / "lh.private.annot").touch()
    Path(pm.m2m("001"), "segmentation").symlink_to(target, target_is_directory=True)
    ids = [a["id"] for a in catalog.atlases(pm, "001", kind="cortical")]
    assert ("private" in ids) is internal


@pytest.mark.parametrize("internal", [False, True])
def test_simulation_figure_leaf_alias(tree, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "montage.png"
    target.touch()
    leaf = Path(
        pm.simulation("001", "simA"),
        "TI",
        "montage_imgs",
        "simA_highlighted_visualization.png",
    )
    leaf.parent.mkdir(parents=True)
    leaf.symlink_to(target)
    figures = catalog.simulation_figures(pm, "001", "simA")
    assert bool(figures) is internal


def test_simulation_networks_lists_trx_stems_and_finished_renders(tree):
    pm, _root, _outside = tree
    Path(pm.simulation("001", "simA")).mkdir(parents=True)
    assert catalog.simulation_networks(pm, "001", "simA") == {
        "own_assessed": [],
        "networks": [],
        "assessed": [],
        "has_edges": False,
        "renders": [],
    }
    assert catalog.simulation_networks(pm, "001", "absent") is None

    tract = Path(pm.simulation("001", "simA"), "tract")
    tract.mkdir(parents=True)
    for name in ("cst_lh.trx", "all.trx", "edges.json"):
        (tract / name).touch()
    out = Path(pm.ti_toolbox(), "visual_exports", "sub-001", "simA", "networks", "net")
    (out / "bundle_ti_max").mkdir(parents=True)
    for name in (
        "ti_max_lateral.png",
        "ti_max_turntable.mp4",
        "network.json",
        "a.html",
    ):
        (out / name).touch()
    (out / "bundle_ti_max" / "not_a_render.png").touch()

    found = catalog.simulation_networks(pm, "001", "simA")
    assert found["networks"] == ["all", "cst_lh"]
    # Each with what it shows; neither a kept bundle nor the viewer page is a render.
    assert {
        r["name"]: (r["kind"], r["network"], r["colour"], r["view"])
        for r in found["renders"]
    } == {
        "ti_max_lateral.png": ("image", "net", "ti_max", "lateral"),
        "ti_max_turntable.mp4": ("video", "net", "ti_max", "turntable"),
    }


@pytest.mark.parametrize("internal", [False, True])
def test_simulation_network_render_leaf_alias(tree, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "render.png"
    target.touch()
    Path(pm.simulation("001", "simA")).mkdir(parents=True)
    out = Path(pm.ti_toolbox(), "visual_exports", "sub-001", "simA", "networks", "net")
    out.mkdir(parents=True)
    (out / "ti_max_lateral.png").symlink_to(target)
    renders = catalog.simulation_networks(pm, "001", "simA")["renders"]
    assert bool(renders) is internal


@pytest.mark.parametrize("internal", [False, True])
def test_subject_root_alias(tree, internal):
    pm, root, outside = tree
    target = root / "alias-target" if internal else outside
    target.mkdir(exist_ok=True)
    (target / "sub-099").mkdir()
    Path(pm.fastsurfer()).parent.mkdir(parents=True, exist_ok=True)
    Path(pm.fastsurfer()).symlink_to(target, target_is_directory=True)
    assert ("099" in catalog.subject_ids(pm)) is internal


@pytest.mark.parametrize("internal", [False, True])
def test_eta_mesh_leaf_alias(tree, monkeypatch, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "mesh"
    # Sparse authored size has an exact expected ratio, without reading mesh contents.
    with target.open("wb") as f:
        f.truncate(2 * eta.REFERENCE_MESH_BYTES)
    Path(pm.m2m("001"), "001.msh").symlink_to(target)
    monkeypatch.setattr("tit.get_path_manager", lambda: pm)
    assert eta.mesh_scale("001") == (2.0 if internal else 1.0)


def test_simulation_directory_and_leaf_metadata(tree):
    pm, root, outside = tree
    sim = Path(pm.simulation("001", "simA"))
    (sim / "TI").mkdir(parents=True)
    (outside / "private_TI_max.nii.gz").touch()
    (sim / "TI" / "niftis").symlink_to(outside, target_is_directory=True)
    assert catalog.simulation_detail(pm, "001", "simA")["niftis"] == []
    (sim / "TI" / "niftis").unlink()
    (sim / "TI" / "niftis").mkdir()
    (sim / "TI" / "niftis" / "private_TI_max.nii.gz").symlink_to(
        outside / "private_TI_max.nii.gz"
    )
    assert catalog.simulation_detail(pm, "001", "simA")["niftis"] == []


def test_simulation_detail_lists_the_fsaverage_projection(tree):
    """The Results pane lists the projection beside the simulation's other meshes."""
    pm, root, outside = tree
    (Path(pm.simulation("001", "simA")) / "TI").mkdir(parents=True)
    fsavg = Path(pm.sim_fsaverage("001", "simA"))
    fsavg.mkdir()
    msh = fsavg / "sub-001_sim-simA_space-fsaverage5_fields.msh"
    for path in (msh, Path(f"{msh}.opt"), msh.with_suffix(".json")):
        path.touch()
    assert catalog.simulation_detail(pm, "001", "simA")["meshes"] == [
        {"path": str(msh), "kind": "fsaverage"}
    ]


def test_sourcedata_and_ct_leaf_metadata(tree):
    pm, root, outside = tree
    (outside / "scan").touch()
    raw = Path(pm.sourcedata_subject("002"), "T1w")
    raw.mkdir(parents=True)
    (raw / "scan.dcm").symlink_to(outside / "scan")
    assert "002" not in catalog.sourcedata_only_subject_ids(pm)
    anat = Path(pm.bids_anat("001"))
    anat.mkdir(parents=True)
    (anat / "sub-001_ct.nii").symlink_to(outside / "scan")
    assert catalog._has_ct(pm, "001") is False


@pytest.mark.parametrize("internal", [False, True])
def test_leadfield_leaf_alias(tree, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "matrix"
    target.write_bytes(b"1234567")
    leaf = Path(pm.leadfields("001"), "001_net_leadfield.hdf5")
    leaf.parent.mkdir(parents=True)
    leaf.symlink_to(target)
    found = catalog.list_leadfields(pm, "001")
    assert len(found) == int(internal)
    if internal:
        assert found[0]["net"] == "net"
        assert found[0]["size_bytes"] == 7


@pytest.mark.parametrize("internal", [False, True])
def test_surface_attachment_leaf_alias(tree, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "attachment"
    target.touch()
    surface = root / "lh.pial"
    surface.touch()
    leaf = root / "lh.thickness"
    leaf.symlink_to(target)
    found = catalog.surface_attachments(str(surface), project_root=str(root))
    assert (str(leaf) in found) is internal


@pytest.mark.parametrize("internal", [False, True])
def test_eta_cap_leaf_alias(tree, monkeypatch, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "cap"
    target.write_text("Electrode,0,0,0,E1\nElectrode,1,2,3,E2\n")
    leaf = Path(pm.eeg_positions("001"), "cap.csv")
    leaf.parent.mkdir(parents=True)
    leaf.symlink_to(target)
    monkeypatch.setattr("tit.get_path_manager", lambda: pm)
    assert eta.electrode_count("001", "cap") == (2 if internal else None)
