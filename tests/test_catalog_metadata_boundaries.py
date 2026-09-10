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
    assert catalog.subject_info_matrix(pm)["rows"] == []


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
def test_simulation_overlay_leaf_alias(tree, internal):
    pm, root, outside = tree
    target = (root if internal else outside) / "overlay.nii.gz"
    target.touch()
    leaf = Path(
        pm.simulation("001", "simA"),
        "TI",
        "montage_imgs",
        "electrode_overlay_subject.nii.gz",
    )
    leaf.parent.mkdir(parents=True)
    leaf.symlink_to(target)
    overlay = next(
        x for x in catalog.electrode_overlays(pm, "001", "simA") if x["mode"] == "TI"
    )
    assert overlay["exists"] is internal


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
