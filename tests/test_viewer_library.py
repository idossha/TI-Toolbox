"""Saved compositions, saved scenes, and the Menu's composition tree.

``tit/server/routes/viewer_library.py``. Three features, and what can go silently wrong in each:

1. **A saved scene must end in ``.tetravox.json``.** The Tetravox app routes any other suffix as a
   *dataset* and tries to read the JSON as a volume — nothing errors on this side, the picture is
   just wrong at the far end (the same trap ``tests/test_view_open.py`` guards for the scene an
   Open writes). A thumbnail must be a real PNG, because this route writes bytes into a person's
   project and "it decoded" is not the same as "it is an image".
2. **A composition must survive its project changing under it.** It stores ids, not resolved
   layers, so reloading it next month re-resolves against whatever is on disk then.
3. **The tree must never claim a file that is not there**, and must never read a voxel — it is
   redrawn as a person clicks.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import zlib
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager
from tit.server.routes import viewer_library as lib


@pytest.fixture(autouse=True)
def _reset():
    reset_path_manager()
    yield
    reset_path_manager()


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch) -> PathManager:
    """``ernie`` with anatomy, one simulation and one analysis run."""
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    seg = os.path.join(m2m, "segmentation")
    os.makedirs(seg)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")
    Path(m2m, "T2_reg.nii.gz").write_bytes(b"t2")
    Path(m2m, "ernie.msh").write_bytes(b"$MeshFormat")
    Path(seg, "labeling.nii.gz").write_bytes(b"lab")
    Path(seg, "labeling_LUT.txt").write_text("1 GM 0 255 0 255\n")

    surfaces = os.path.join(m2m, "surfaces")
    os.makedirs(surfaces)
    for name in ("lh.central.gii", "lh.pial.gii", "rh.white.gii", "lh.sphere.gii"):
        Path(surfaces, name).write_bytes(b"gii")
    # The parcellations SimNIBS writes for those surfaces, in the directory it actually writes
    # them to — two away from the geometry, which is why nothing had ever offered them.
    for name in ("lh.ernie_DK40.annot", "rh.ernie_DK40.annot", "lh.ernie_a2009s.annot"):
        Path(seg, name).write_bytes(b"annot")

    sim = pm.simulation("ernie", "L_Insula")
    niftis = os.path.join(sim, "TI", "niftis")
    mesh = os.path.join(sim, "TI", "mesh")
    os.makedirs(niftis)
    os.makedirs(mesh)
    for name in (
        "L_Insula_TI_subject_TI_max.nii.gz",
        "grey_L_Insula_TI_subject_TI_max.nii.gz",
        "L_Insula_TI_MNI_MNI_TI_max.nii.gz",
    ):
        Path(niftis, name).write_bytes(b"x")
    Path(mesh, "grey_L_Insula_TI.msh").write_bytes(b"$MeshFormat")

    run = os.path.join(sim, "Analyses", "Voxel", "cortical_lh.insula_DK40")
    os.makedirs(run)
    Path(run, "roi_mask.nii.gz").write_bytes(b"roi")
    Path(run, "summary.csv").write_text("a,b\n")  # not a volume: must not be offered

    resources = tmp_path / "resources_atlas"
    resources.mkdir()
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(resources))
    return pm


def png_bytes(width: int = 1, height: int = 1) -> bytes:
    """A real 1x1 PNG, built here rather than pasted as a base64 blob.

    Built so the test says what it is: a signature, an IHDR, one compressed scanline and an IEND.
    A pasted blob would assert the same thing while telling a reader nothing about why the route
    accepts it (and nothing about why it rejects the near-miss below).
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def png_data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes()).decode()


SCENE = {"version": 2, "datasets": [], "layers": [{"id": "L0", "kind": "volume"}]}


# ── saved scenes ─────────────────────────────────────────────────────────────


def test_a_saved_scene_gets_the_suffix_the_tetravox_app_routes_on(pm: PathManager) -> None:
    """``.tetravox.json``, or the app reads the scene as a volume and says nothing."""
    result = lib.save_scene("my view", {"scene": SCENE})
    assert result["path"].endswith(".tetravox.json")
    assert os.path.isfile(result["path"])
    assert json.loads(Path(result["path"]).read_text()) == SCENE


def test_the_scene_is_written_verbatim(pm: PathManager) -> None:
    """The whole point of saving a scene rather than a composition is that it is a *record*.

    A server that re-derived any part of it — a window, a camera — would be recording something
    other than what the person was looking at.
    """
    scene = {
        **SCENE,
        "cursor": [-56.3, 40.5, -34.5],
        "layers": [{"id": "L0", "scale": {"kind": "heat", "min": 0.0867, "max": 0.1394}}],
    }
    result = lib.save_scene("exact", {"scene": scene})
    assert json.loads(Path(result["path"]).read_text()) == scene


def test_a_scene_carries_a_thumbnail_and_metadata_under_one_stem(pm: PathManager) -> None:
    """Three files, one stem — so a person moving the scene knows what belongs with it."""
    result = lib.save_scene(
        "with a picture",
        {"scene": SCENE, "thumbnail": png_data_url(), "subject": "ernie", "simulation": "L_Insula"},
    )
    assert result["has_thumbnail"] is True
    stem = os.path.join(lib.saved_scene_dir(), result["slug"])
    assert Path(f"{stem}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    meta = json.loads(Path(f"{stem}.meta.json").read_text())
    assert meta["subject"] == "ernie" and meta["simulation"] == "L_Insula"


def test_a_thumbnail_that_is_not_a_png_is_dropped_not_written(pm: PathManager) -> None:
    """This route writes bytes into someone's project; "it decoded" is not "it is an image".

    Dropped rather than refused: a scene worth keeping is still worth keeping without its picture.
    """
    not_a_png = "data:image/png;base64," + base64.b64encode(b"GIF89a and then some").decode()
    result = lib.save_scene("sneaky", {"scene": SCENE, "thumbnail": not_a_png})
    assert result["has_thumbnail"] is False
    assert not os.path.isfile(os.path.join(lib.saved_scene_dir(), f"{result['slug']}.png"))
    assert os.path.isfile(result["path"]), "the scene itself is still saved"


def test_a_thumbnail_that_is_not_a_data_url_is_dropped(pm: PathManager) -> None:
    for value in ("https://example.com/x.png", "data:image/svg+xml;base64,PHN2Zz4=", "", None, 7):
        assert lib._thumbnail_bytes(value) is None


def test_an_oversized_thumbnail_is_dropped(pm: PathManager, monkeypatch) -> None:
    """A project directory must not quietly become a photo album."""
    monkeypatch.setattr(lib, "_MAX_THUMBNAIL_BYTES", 8)
    assert lib._thumbnail_bytes(png_data_url()) is None


def test_a_scene_with_no_layers_is_refused(pm: PathManager) -> None:
    """An empty scene reopens as a black window, which is worse than not having saved it."""
    from fastapi import HTTPException

    for body in ({}, {"scene": {}}, {"scene": {"layers": []}}, {"scene": "not an object"}):
        with pytest.raises(HTTPException) as excinfo:
            lib.save_scene("empty", body)
        assert excinfo.value.status_code == 422


def test_scenes_list_newest_first_without_returning_the_documents(pm: PathManager) -> None:
    """One scene document is megabytes; the Menu only needs to draw a row."""
    lib.save_scene("older", {"scene": SCENE})
    lib.save_scene("newer", {"scene": SCENE})
    rows = lib.list_scenes()["scenes"]
    assert {r["name"] for r in rows} == {"older", "newer"}
    assert all("scene" not in r for r in rows)
    assert all("bytes" in r and "has_thumbnail" in r for r in rows)


def test_reading_one_scene_returns_the_document(pm: PathManager) -> None:
    lib.save_scene("round trip", {"scene": SCENE})
    assert lib.read_scene("round trip")["scene"] == SCENE


def test_deleting_a_scene_takes_its_thumbnail_and_metadata_with_it(pm: PathManager) -> None:
    result = lib.save_scene("bye", {"scene": SCENE, "thumbnail": png_data_url()})
    lib.delete_scene("bye")
    stem = os.path.join(lib.saved_scene_dir(), result["slug"])
    for suffix in (".tetravox.json", ".png", ".meta.json"):
        assert not os.path.isfile(f"{stem}{suffix}")


def test_a_missing_scene_is_a_404_not_a_silent_success(pm: PathManager) -> None:
    from fastapi import HTTPException

    for call in (lambda: lib.read_scene("nope"), lambda: lib.delete_scene("nope")):
        with pytest.raises(HTTPException) as excinfo:
            call()
        assert excinfo.value.status_code == 404


@pytest.mark.parametrize("name", ["../escape", "..", ".hidden", "", "a" * 81, "/etc/passwd"])
def test_a_name_that_would_become_a_different_file_is_refused(pm: PathManager, name: str) -> None:
    """Strict rather than sanitising: the person will look for the name they typed."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        lib.save_scene(name, {"scene": SCENE})
    assert excinfo.value.status_code == 422


def test_a_traversing_name_never_escapes_the_scenes_directory(pm: PathManager) -> None:
    """The refusal above is the mechanism; this is the property it exists for."""
    from fastapi import HTTPException

    for name in ("../../../../tmp/pwned", "..\\..\\pwned"):
        try:
            result = lib.save_scene(name, {"scene": SCENE})
        except HTTPException:
            continue
        assert os.path.dirname(os.path.abspath(result["path"])) == os.path.abspath(lib.saved_scene_dir())


def test_the_default_scene_name_says_what_it_is_of(pm: PathManager) -> None:
    name = lib.suggest_scene_name(subject="ernie", simulation="L_Insula", field="TI_max")["name"]
    assert name.startswith("ernie_L_Insula_TI_max_")
    # Server-side so the name does not depend on which client saved it, and the date is the
    # project's clock rather than a browser's.
    assert name.split("_")[-1].isdigit() and len(name.split("_")[-1]) == 8
    # Whatever is missing, the result is still a usable file name.
    assert lib.suggest_scene_name()["name"]
    assert "/" not in lib.suggest_scene_name(subject="a/b")["name"]


# ── compositions ─────────────────────────────────────────────────────────────


def test_a_composition_round_trips_with_its_name_and_a_timestamp(pm: PathManager) -> None:
    body = {"subject": "ernie", "space": "subject", "inputs": ["/x/T1.nii.gz"]}
    saved = lib.save_composition("mine", body)
    assert saved["subject"] == "ernie" and saved["inputs"] == ["/x/T1.nii.gz"]
    assert saved["saved_at"] and saved["version"] == 1

    listed = lib.list_compositions()["compositions"]
    assert len(listed) == 1 and listed[0]["name"] == "mine"
    assert listed[0]["inputs"] == ["/x/T1.nii.gz"]


def test_a_composition_stores_ids_not_resolved_layers(pm: PathManager) -> None:
    """This is what makes it the *reproducibility* artefact rather than a second scene.

    It is not re-resolved on save, so reloading it against a project whose simulation has been
    re-run picks up the new outputs — "show me the same thing, from the current data".
    """
    saved = lib.save_composition("ids", {"inputs": ["/gone/missing.nii.gz"]})
    assert saved["inputs"] == ["/gone/missing.nii.gz"], "a missing input is stored, not dropped"


def test_an_unknown_key_in_a_composition_is_kept(pm: PathManager) -> None:
    """The tree's vocabulary will grow; a server that rejected new keys would make every Menu
    change a two-repository change."""
    saved = lib.save_composition("future", {"somethingNew": {"deep": [1, 2]}})
    assert saved["somethingNew"] == {"deep": [1, 2]}


def test_one_unreadable_composition_does_not_empty_the_list(pm: PathManager) -> None:
    """A hand-edited file must not hide the person's other work."""
    lib.save_composition("good", {"subject": "ernie"})
    os.makedirs(lib.composition_dir(), exist_ok=True)
    Path(lib.composition_dir(), "broken.json").write_text("{not json")
    Path(lib.composition_dir(), "notes.txt").write_text("ignored")
    names = [c["name"] for c in lib.list_compositions()["compositions"]]
    assert names == ["good"]


def test_deleting_a_composition_that_is_not_there_is_a_404(pm: PathManager) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        lib.delete_composition("never existed")
    assert excinfo.value.status_code == 404


def test_listing_before_anything_is_saved_is_empty_not_an_error(pm: PathManager) -> None:
    assert lib.list_compositions() == {"compositions": []}
    assert lib.list_scenes() == {"scenes": []}


# ── the composition tree ─────────────────────────────────────────────────────


def test_the_tree_has_a_branch_per_stage(pm: PathManager) -> None:
    tree = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])
    assert tree["available"] is True
    labels = {n["label"] for n in tree["anatomy"]}
    # The head model is labelled by what it is, not by the subject id its file is named after: a
    # row reading "ernie" among "T1" and "T2_reg" says nothing about which of them it is.
    assert {"T1", "T2_reg", "Head mesh (ernie)"} <= labels
    assert [s["name"] for s in tree["simulations"]] == ["L_Insula"]
    assert [a["name"] for a in tree["analyses"]] == ["cortical_lh.insula_DK40"]


def test_exactly_one_anatomy_input_starts_ticked(pm: PathManager) -> None:
    """A scene with no anatomy under it is a field floating in black."""
    tree = viewspec.viewer_tree("ernie", "subject")
    on = [n for n in tree["anatomy"] if n["default_on"]]
    assert [n["label"] for n in on] == ["T1"]


def test_the_grey_matter_field_is_the_one_that_starts_ticked(pm: PathManager) -> None:
    """The whole-head copy is mostly skull and CSF, where the number is not what is reported."""
    sim = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])["simulations"][0]
    on = [f for f in sim["fields"] if f["default_on"]]
    assert len(on) == 1 and on[0]["name"].startswith("grey_")


def test_a_subject_space_tree_does_not_offer_the_mni_copies(pm: PathManager) -> None:
    """Two volumes in different spaces in one scene is a misregistration nobody asked for."""
    subject = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])["simulations"][0]
    assert all("_MNI_" not in f["name"] for f in subject["fields"])
    mni = viewspec.viewer_tree("ernie", "mni", ["L_Insula"])["simulations"][0]
    assert all("_subject_" not in f["name"] for f in mni["fields"])
    assert any("_MNI_" in f["name"] for f in mni["fields"])


def test_meshes_are_offered_in_both_spaces(pm: PathManager) -> None:
    """There is no MNI mesh, so hiding them in MNI mode would be hiding a real option."""
    for space in ("subject", "mni"):
        sim = viewspec.viewer_tree("ernie", space, ["L_Insula"])["simulations"][0]
        assert [m["name"] for m in sim["meshes"]] == ["grey_L_Insula_TI.msh"]


def test_the_tree_offers_only_files_a_scene_can_use(pm: PathManager) -> None:
    """A CSV is not a volume; a registration sphere is a ball, not anatomy."""
    tree = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])
    outputs = [n["name"] for a in tree["analyses"] for n in a["outputs"]]
    assert outputs == ["roi_mask.nii.gz"]
    assert all(".sphere." not in n["name"] for n in tree["anatomy"])
    assert any(n["name"] == "lh.central.gii" for n in tree["anatomy"])


def test_analyses_are_listed_only_for_the_simulations_asked_for(pm: PathManager) -> None:
    """A subject with a dozen simulations has a dozen Analyses directories; listing all of them
    turns a menu into a file browser."""
    assert viewspec.viewer_tree("ernie", "subject", ["L_Insula"])["analyses"]
    assert viewspec.viewer_tree("ernie", "subject", ["something else"])["analyses"] == []
    # No selection at all means "all of them", which is what a freshly opened Menu shows.
    assert viewspec.viewer_tree("ernie", "subject")["analyses"]


def test_every_node_carries_a_stable_id_and_a_size(pm: PathManager) -> None:
    """The id is the container path: a composition saved today has to resolve against a project
    that has since gained or lost files, and the only thing that survives that is the file name."""
    tree = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])
    for node in tree["anatomy"]:
        assert node["id"] == node["path"] and os.path.isabs(node["id"])
        assert node["available"] is True and node["bytes"] is not None
        assert node["kind"] in ("volume", "label-volume", "surface", "mesh")


def test_a_gii_sheet_is_a_surface_and_only_the_msh_is_a_mesh(pm: PathManager) -> None:
    """Maintainer, 2026-09-07: a mesh is a tetrahedral FEM; a surface is a triangular 2-D sheet.

    The Anatomy branch used to chip `lh.central`, `lh.pial` and `lh.white` as MESH beside the real
    `Head mesh (ernie)`, because the rule behind the chip was `endswith((".msh", ".gii"))`.
    """
    anatomy = viewspec.viewer_tree("ernie", "subject")["anatomy"]
    by_name = {node["name"]: node for node in anatomy}
    assert [name for name, node in by_name.items() if node["kind"] == "mesh"] == [
        "ernie.msh"
    ]
    for name in ("lh.central.gii", "lh.pial.gii", "rh.white.gii"):
        assert by_name[name]["kind"] == "surface", name
    assert by_name["labeling.nii.gz"]["kind"] == "label-volume"
    assert by_name["T1.nii.gz"]["kind"] == "volume"


def test_a_surface_carries_its_attachments_matched_by_hemisphere(pm: PathManager) -> None:
    """SimNIBS writes the `.annot` files two directories from the geometry, which is why nothing
    offered them: the tree looks in `segmentation/` as well as `surfaces/`."""
    anatomy = viewspec.viewer_tree("ernie", "subject")["anatomy"]
    left = next(node for node in anatomy if node["name"] == "lh.central.gii")
    names = [item["name"] for item in left["attachments"]]
    assert names and all(name.startswith("lh.") for name in names)
    assert all(
        item["kind"] in ("annotation", "morph", "surface-data")
        for item in left["attachments"]
    )
    # A volume has no attachments key at all: only a surface can carry one.
    volume = next(node for node in anatomy if node["name"] == "T1.nii.gz")
    assert "attachments" not in volume



def test_an_unknown_subject_says_why_rather_than_returning_an_empty_tree(pm: PathManager) -> None:
    """"No head model" and "no simulations" are different problems, and the Menu must say which."""
    tree = viewspec.viewer_tree("nobody", "subject")
    assert tree["available"] is False
    assert "head model" in (tree["reason"] or "")
    assert tree["anatomy"] == [] and tree["simulations"] == []

    none_chosen = viewspec.viewer_tree(None, "subject")
    assert none_chosen["available"] is False and none_chosen["reason"] == "no subject chosen"


def test_the_tree_reads_no_voxels(pm: PathManager, monkeypatch) -> None:
    """It is redrawn as a person clicks, so it must be `listdir` and `stat` and nothing more.

    Enforced by making any volume read explode: the fixture's files are not real NIfTIs anyway, so
    a `nibabel` import here could only be a mistake this test exists to catch.
    """
    import sys
    import types

    def _boom(*_args, **_kwargs):
        raise AssertionError("the composition tree read a volume")

    monkeypatch.setitem(sys.modules, "nibabel", types.SimpleNamespace(load=_boom))
    monkeypatch.setattr(viewspec, "_volume_stats", _boom)
    monkeypatch.setattr(viewspec, "_volume_bounds", _boom)

    tree = viewspec.viewer_tree("ernie", "subject", ["L_Insula"])
    assert tree["available"] is True and tree["simulations"]
