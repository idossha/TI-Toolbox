"""A surface reaches the embed as a surface, or it does not reach it at all.

Two rules, and both are here because the *tempting* alternative fails silently.

**A surface is never sent as a mesh.** Degrading would work, in the sense that nothing errors: a
cortical sheet is a triangle-only mesh and Tetravox's engine will happily take it. It would just
arrive with a mesh's defaults — filled in 2D instead of outlined, capped clip planes for an object
with no interior, and no way to attach the parcellation that was the reason for ticking it. The
person gets a picture, and no reason to doubt it.

**A scene never spans two subjects.** Overlaying one person's field on another's anatomy produces
two brains, roughly head-shaped and roughly aligned, and a false result. There is no artefact to
notice. The real `viewer-open` spec first passed while measuring the wrong subject entirely
(`desktop/tests/e2e/real/viewer-open.spec.ts`, the "one subject per scene" block), which is what
this rule exists to make impossible rather than merely unlikely.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager
from tit.server.routes import viewers


@pytest.fixture(autouse=True)
def _reset_pm():
    reset_path_manager()
    yield
    reset_path_manager()


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch) -> PathManager:
    """Two subjects with anatomy, surfaces and the parcellations SimNIBS writes for them."""
    pm = get_path_manager(str(tmp_path))
    for sid in ("ernie", "101"):
        m2m = pm.m2m(sid)
        seg = os.path.join(m2m, "segmentation")
        surfaces = os.path.join(m2m, "surfaces")
        os.makedirs(seg)
        os.makedirs(surfaces)
        Path(m2m, "T1.nii.gz").write_bytes(b"t1" * 100)
        Path(m2m, f"{sid}.msh").write_bytes(b"$MeshFormat")
        for name in ("lh.central.gii", "rh.central.gii"):
            Path(surfaces, name).write_bytes(b"gii")
        for name in ("lh.ernie_DK40.annot", "rh.ernie_DK40.annot"):
            Path(seg, name).write_bytes(b"annot")
        Path(seg, "lh.thickness").write_bytes(b"morph")
    resources = tmp_path / "resources_atlas"
    resources.mkdir()
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(resources))
    return pm


def _scene(pm: PathManager, *files: str) -> dict:
    spec = viewspec.build_view(
        "subject", subject="ernie", space="subject", files=list(files)
    )
    assert spec is not None
    return spec["scene"]


def _paths(pm: PathManager, sid: str) -> SimpleNamespace:
    m2m = pm.m2m(sid)
    return SimpleNamespace(
        t1=os.path.join(m2m, "T1.nii.gz"),
        msh=os.path.join(m2m, f"{sid}.msh"),
        lh=os.path.join(m2m, "surfaces", "lh.central.gii"),
        rh=os.path.join(m2m, "surfaces", "rh.central.gii"),
        lh_annot=os.path.join(m2m, "segmentation", "lh.ernie_DK40.annot"),
        rh_annot=os.path.join(m2m, "segmentation", "rh.ernie_DK40.annot"),
        lh_morph=os.path.join(m2m, "segmentation", "lh.thickness"),
    )


# ── the emitted shape ────────────────────────────────────────────────────────


def test_a_bare_surface_is_a_solid_surface_layer(pm: PathManager) -> None:
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.t1, p.lh)
    layer = next(layer for layer in scene["layers"] if layer["name"] == "lh.central.gii")
    assert layer["kind"] == "surface"
    assert layer["colorMode"] == "solid"
    # Freeview yellow, which is what Tetravox's own `defaultSurfaceLayer` seeds.
    assert layer["solidColor"] == [1.0, 0.9, 0.15, 1.0]
    assert layer["contourColor"] == layer["solidColor"]
    assert layer["contoursIn2D"] is True and layer["contourWidthPx"] == 1.5
    # Visible, unlike a `.msh`: an 8 MB sheet costs nothing to draw, and one that arrived hidden
    # would mean ticking a surface and getting a picture without it in.
    assert layer["visible"] is True
    # A sheet has no interior, so no caps and no 2D fill -- both of which a mesh layer carries.
    assert layer["clip"] == {"planes": []}
    assert "fillIn2D" not in layer and "tagStyle" not in layer


def test_the_head_model_is_still_a_mesh_layer(pm: PathManager) -> None:
    """The change must not have turned every geometry into a surface."""
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.msh)
    layer = next(layer for layer in scene["layers"] if layer["name"] == "ernie.msh")
    assert layer["kind"] == "mesh"
    assert layer["clip"]["caps"] is True
    assert layer["fillIn2D"] is True


def test_no_surface_is_ever_emitted_as_a_mesh(pm: PathManager) -> None:
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.t1, p.msh, p.lh, p.rh)
    by_name = {layer["name"]: layer for layer in scene["layers"]}
    kinds = {ds["name"]: ds["kind"] for ds in scene["datasets"]}
    assert kinds["lh.central.gii"] == "surface" and kinds["ernie.msh"] == "mesh"
    assert by_name["lh.central.gii"]["kind"] == "surface"
    assert by_name["rh.central.gii"]["kind"] == "surface"
    assert by_name["ernie.msh"]["kind"] == "mesh"


# ── attachments ──────────────────────────────────────────────────────────────


def test_an_annotation_becomes_a_sidecar_field_and_the_colour_source(
    pm: PathManager,
) -> None:
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.lh, p.lh_annot)

    # One layer, not two: an attachment has no geometry, so it is not a layer at all.
    assert [layer["name"] for layer in scene["layers"]] == ["lh.central.gii"]
    assert len(scene["datasets"]) == 1

    dataset = scene["datasets"][0]
    # A surface is a mesh dataset with no tetrahedra; `surface` is the engine's alias for it, and
    # is written because a scene is also a document someone reads.
    assert dataset["kind"] == "surface"
    fields = dataset["sidecars"]["fields"]
    # Relative to the surface's own directory, and `{path}` alone. SimNIBS keeps the parcellations
    # a directory across from the geometry, so this really is a `../`.
    assert fields == [{"path": os.path.join("..", "segmentation", "lh.ernie_DK40.annot")}]

    layer = scene["layers"][0]
    assert layer["colorMode"] == "annotation"
    # A node-field *name*, never a path: the layer refers to what the worker attached.
    assert layer["annotation"] == {
        # The **file name**, extension and all -- never a stem and never a role word.
        "name": "lh.ernie_DK40.annot",
        "mode": "outline",
        "outlineWidthPx": 1.5,
    }
    # A parcellation has no continuous scale, so its colorbar would be a ramp with no meaning.
    assert layer["showColorbar"] is False


def test_a_morph_curve_becomes_an_overlay(pm: PathManager) -> None:
    p = _paths(pm, "ernie")
    layer = _scene(pm, p.lh, p.lh_morph)["layers"][0]
    assert layer["colorMode"] == "overlay"
    assert layer["overlay"] == {"name": "lh.thickness", "component": "mag"}
    assert layer["showColorbar"] is True


def test_an_annotation_wins_over_a_scalar_and_both_stay_attached(
    pm: PathManager,
) -> None:
    """One colour source at a time is the engine's rule, not ours.

    A parcellation is what a person ticks a surface *for*, so it takes the slot; the curve stays
    on the dataset and is one click away in the app's own panel.
    """
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.lh, p.lh_morph, p.lh_annot)
    layer = scene["layers"][0]
    assert layer["colorMode"] == "annotation"
    assert "overlay" not in layer
    assert len(scene["datasets"][0]["sidecars"]["fields"]) == 2


def test_an_attachment_lands_on_its_own_hemisphere(pm: PathManager) -> None:
    """The only correspondence FreeSurfer promises is the hemisphere."""
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.lh, p.rh, p.rh_annot, p.lh_annot)
    by_name = {
        layer["name"]: scene["datasets"][index]
        for index, layer in enumerate(scene["layers"])
    }
    left = by_name["lh.central.gii"]["sidecars"]["fields"]
    right = by_name["rh.central.gii"]["sidecars"]["fields"]
    assert len(left) == 1 and left[0]["path"].endswith("lh.ernie_DK40.annot")
    assert len(right) == 1 and right[0]["path"].endswith("rh.ernie_DK40.annot")
    # Relative, so neither addressing of the scene has to re-root it.
    assert not os.path.isabs(left[0]["path"])


def test_an_attachment_with_no_surface_ticked_is_dropped(pm: PathManager) -> None:
    """It would draw nothing: a `.annot` is a colour table with nowhere to go."""
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.t1, p.lh_annot)
    assert [layer["name"] for layer in scene["layers"]] == ["T1.nii.gz"]
    assert len(scene["datasets"]) == len(scene["layers"])


def test_layers_and_datasets_stay_the_same_length(pm: PathManager) -> None:
    """`tit/server/routes/viewers.py` zips them to build the file list a person reads."""
    p = _paths(pm, "ernie")
    scene = _scene(pm, p.t1, p.lh, p.lh_annot, p.rh, p.rh_annot, p.msh)
    assert len(scene["layers"]) == len(scene["datasets"]) == 4


# ── the capability switch, both ways ─────────────────────────────────────────


def _request(features: list[str] | None) -> SimpleNamespace:
    """An app whose `/api/capabilities` would report an embed with these features."""
    embed = SimpleNamespace(available=features is not None, features=features or [])
    caps = SimpleNamespace(tetravox_embed=embed)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=None)))
    return request, caps


def test_an_embed_with_surfaces_opens_them(pm: PathManager, monkeypatch) -> None:
    request, caps = _request(["volumes", "meshes", "surfaces"])
    monkeypatch.setattr(
        "tit.server.routes.viewer_library.probe_capabilities", lambda **_kw: caps
    )
    p = _paths(pm, "ernie")
    result = viewers.view_open(
        {"kind": "subject", "subject": "ernie", "files": [p.t1, p.lh], "dry_run": True},
        request,
    )
    kinds = [layer["kind"] for layer in result["view"]["layers"]]
    assert "surface" in kinds


def test_an_embed_without_surfaces_refuses_rather_than_degrading(
    pm: PathManager, monkeypatch
) -> None:
    request, caps = _request(["volumes", "meshes"])
    monkeypatch.setattr(
        "tit.server.routes.viewer_library.probe_capabilities", lambda **_kw: caps
    )
    p = _paths(pm, "ernie")
    with pytest.raises(HTTPException) as excinfo:
        viewers.view_open(
            {
                "kind": "subject",
                "subject": "ernie",
                "files": [p.t1, p.lh],
                "dry_run": True,
            },
            request,
        )
    assert excinfo.value.status_code == 422
    assert "0.4.0" in excinfo.value.detail
    assert "lh.central.gii" in excinfo.value.detail
    # The volume beside it is not the problem and is not named.
    assert "T1.nii.gz" not in excinfo.value.detail


def test_an_embed_without_surfaces_still_opens_volumes_and_meshes(
    pm: PathManager, monkeypatch
) -> None:
    request, caps = _request(["volumes", "meshes"])
    monkeypatch.setattr(
        "tit.server.routes.viewer_library.probe_capabilities", lambda **_kw: caps
    )
    p = _paths(pm, "ernie")
    result = viewers.view_open(
        {"kind": "subject", "subject": "ernie", "files": [p.t1, p.msh], "dry_run": True},
        request,
    )
    assert {layer["kind"] for layer in result["view"]["layers"]} == {"volume", "mesh"}


# ── one subject per scene ────────────────────────────────────────────────────


def test_a_scene_spanning_two_subjects_is_refused_naming_both(pm: PathManager) -> None:
    ernie, other = _paths(pm, "ernie"), _paths(pm, "101")
    with pytest.raises(HTTPException) as excinfo:
        viewers.view_open(
            {
                "kind": "subject",
                "subject": "ernie",
                "files": [ernie.t1, other.t1],
                "dry_run": True,
            }
        )
    assert excinfo.value.status_code == 422
    assert "ernie" in excinfo.value.detail and "101" in excinfo.value.detail


def test_one_subjects_own_files_are_fine(pm: PathManager) -> None:
    ernie = _paths(pm, "ernie")
    result = viewers.view_open(
        {
            "kind": "subject",
            "subject": "ernie",
            "files": [ernie.t1, ernie.msh],
            "dry_run": True,
        }
    )
    assert len(result["files"]) == 2


def test_a_file_belonging_to_no_subject_is_exempt(pm: PathManager, tmp_path) -> None:
    """The MNI template and the bundled atlases belong to nobody, and an MNI scene is *supposed*
    to mix them in with a subject's own volumes."""
    ernie = _paths(pm, "ernie")
    shared = tmp_path / "resources_atlas" / "MNI152_T1_1mm.nii.gz"
    shared.write_bytes(b"mni")
    result = viewers.view_open(
        {
            "kind": "subject",
            "subject": "ernie",
            "files": [ernie.t1, str(shared)],
            "dry_run": True,
        }
    )
    assert len(result["files"]) == 2
