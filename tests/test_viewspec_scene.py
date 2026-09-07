"""Tests for ``tit.viewspec.to_tetravox_viewspec`` (docs/dev/HISTORY.md § 2026-09-03 (Docker streamline) §1).

The scene is the in-app viewer's whole input: which files it fetches, over
which URLs, with which colormap/scale/window and visibility -- expressed as
a real Tetravox ``ViewSpec`` v2 document (not a TI-shaped approximation of
one). Every scene built here is also validated against the hand-written
``contracts/tetravox-viewspec-v2.schema.json`` (the "does the engine's
``Engine.load()`` actually accept this" check).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager

jsonschema = pytest.importorskip(
    "jsonschema",
    reason=(
        "jsonschema is not a runtime dependency; install with "
        "`python3 -m pip install --user --break-system-packages jsonschema` "
        "to run this test file"
    ),
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "tetravox-viewspec-v2.schema.json").read_text()
)
_VALIDATOR = jsonschema.Draft202012Validator(_SCHEMA)


def assert_valid_viewspec(scene: dict) -> None:
    errors = sorted(_VALIDATOR.iter_errors(scene), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
    )


@pytest.fixture(autouse=True)
def _reset_pm():
    reset_path_manager()
    yield
    reset_path_manager()


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch) -> PathManager:
    """``ernie`` with a T1, a labelled atlas, one TI simulation and a mesh."""
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    seg_dir = os.path.join(m2m, "segmentation")
    os.makedirs(seg_dir)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1" * 100)
    Path(seg_dir, "labeling.nii.gz").write_bytes(b"lab")
    Path(seg_dir, "labeling_LUT.txt").write_text("1 GM 0 255 0 255\n")

    sim_dir = pm.simulation("ernie", "L_Insula")
    ti_niftis = os.path.join(sim_dir, "TI", "niftis")
    os.makedirs(ti_niftis)
    for name in (
        "L_Insula_TI_subject_TI_max.nii.gz",
        "grey_L_Insula_TI_subject_TI_max.nii.gz",
        "white_L_Insula_TI_subject_TI_max.nii.gz",
    ):
        Path(ti_niftis, name).write_bytes(b"x")
    overlay_dir = os.path.join(sim_dir, "TI", "montage_imgs")
    os.makedirs(overlay_dir)
    Path(overlay_dir, "electrode_overlay_subject.nii.gz").write_bytes(b"e")
    Path(overlay_dir, "electrode_overlay_subject.lut").write_text(
        "1 Channel_1 0 0 255 255\n"
    )

    mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    os.makedirs(mesh_dir)
    Path(mesh_dir, "grey_L_Insula_TI.msh").write_bytes(b"$MeshFormat")
    Path(mesh_dir, "grey_L_Insula_TI.msh.opt").write_text("// opts\n")

    resources = tmp_path / "resources_atlas"
    resources.mkdir()
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(resources))
    return pm


def scene_for(kind: str, **kwargs) -> dict:
    spec = viewspec.build_view(kind, **kwargs)
    assert spec is not None
    scene = spec["scene"]
    assert_valid_viewspec(scene)
    return scene


def layers_by_kind(scene: dict, kind: str) -> list[dict]:
    return [layer for layer in scene["layers"] if layer["kind"] == kind]


def dataset_of(scene: dict, layer: dict) -> dict:
    return next(d for d in scene["datasets"] if d["id"] == layer["datasetId"])


# ── shape / URLs ─────────────────────────────────────────────────────────────


def test_scene_is_version_2_and_schema_valid(pm: PathManager) -> None:
    scene = scene_for("subject", subject="ernie")
    assert (
        scene["version"] == 2
    )  # asserted directly too, not just via the schema's const


def test_scene_dataset_paths_are_raw_route_urls(pm: PathManager) -> None:
    """Both halves of a DatasetRef point at the same fetchable URL: this
    server's client is a same-origin iframe, so an origin-relative
    /api/files/raw/... path needs no client-side rewriting."""
    spec = viewspec.build_view("simulation", subject="ernie", simulation="L_Insula")
    scene = spec["scene"]
    for layer_path, dataset in zip(
        (layer["path"] for layer in spec["layers"]), scene["datasets"]
    ):
        expected = "/api/files/raw/" + layer_path.lstrip("/")
        assert dataset["path"] == expected
        assert dataset["absPath"] == expected
        assert dataset["fingerprint"] == ""


def test_scene_url_keeps_the_file_name_as_the_last_segment(pm: PathManager) -> None:
    """The engine derives the name, the gzip decision and volume-vs-mesh routing
    from the URL's last segment; a ``?path=`` URL would leave it reading "raw"."""
    scene = scene_for("subject", subject="ernie")
    for dataset in scene["datasets"]:
        assert dataset["path"].rsplit("/", 1)[1] == dataset["name"]


def test_scene_url_percent_encodes_odd_characters(tmp_path: Path) -> None:
    spec = {
        "space": "subject",
        "layers": [
            {
                "path": "/mnt/000/a b/T1 scan.nii.gz",
                "kind": "volume",
                "colormap": "grayscale",
                "opacity": 1.0,
                "visible": True,
            }
        ],
    }
    dataset = viewspec.to_tetravox_viewspec(spec)["datasets"][0]
    assert dataset["path"] == "/api/files/raw/mnt/000/a%20b/T1%20scan.nii.gz"


# ── the mapping ──────────────────────────────────────────────────────────────


def test_scene_volume_and_mesh_colormaps(pm: PathManager) -> None:
    scene = scene_for("simulation", subject="ernie", simulation="L_Insula")
    volumes = layers_by_kind(scene, "volume")
    meshes = layers_by_kind(scene, "mesh")
    base = next(v for v in volumes if v["name"] == "T1")
    # Curated names (FX3 item 3 / qa-neuro-researcher-notes.md #4): the bare
    # (whole-head) TI_max NIfTI is "TI_max (volume)", not the raw
    # "L_Insula_TI_subject_TI_max" pipeline basename.
    field = next(v for v in volumes if v["name"] == "TI_max (volume)")
    electrodes = next(v for v in volumes if v["name"] == "Electrodes")

    assert base["colormap"] == "gray"
    assert base["scale"]["kind"] == "linear"
    assert field["colormap"] == "turbo"
    assert field["scale"]["kind"] == "heat"
    assert electrodes["interpolation"] == "nearest"  # a LUT-coloured label volume
    assert base["interpolation"] == "linear"

    assert meshes  # the grey-matter TI mesh, from _grey_mesh_layer
    mesh = meshes[0]
    assert mesh["colormap"] == "jet"
    assert mesh["colorMode"] == "field"
    assert mesh["field"] == {"source": "elm", "name": "TI_max", "component": "mag"}


def test_scene_subject_atlas_is_nearest_and_shown_in_3d(pm: PathManager) -> None:
    scene = scene_for("subject", subject="ernie")
    volumes = scene["layers"]
    base, atlas = volumes[0], volumes[1]
    assert base["kind"] == "volume" and base["interpolation"] == "linear"
    assert base["showIn3D"] is False
    assert atlas["interpolation"] == "nearest"
    assert atlas["showIn3D"] is True
    assert atlas["labelMode"] == "fill"


def test_scene_lut_becomes_a_dataset_sidecar(pm: PathManager) -> None:
    scene = scene_for("subject", subject="ernie")
    atlas_dataset = scene["datasets"][1]
    assert atlas_dataset["sidecars"]["lut"]["path"].endswith("labeling_LUT.txt")
    assert atlas_dataset["sidecars"]["lut"]["path"].startswith("/api/files/raw/")
    assert not any(d["name"].endswith("_LUT.txt") for d in scene["datasets"])


def test_scene_field_scale_falls_back_when_the_volume_cannot_be_read(
    pm: PathManager,
) -> None:
    """The fixture NIfTIs in this file are not real gzip data; _volume_stats
    fails closed (None) and the field layer still gets a valid, documented
    placeholder heat scale rather than crashing the whole scene."""
    scene = scene_for("simulation", subject="ernie", simulation="L_Insula")
    field = next(
        v for v in layers_by_kind(scene, "volume") if v["name"] == "TI_max (volume)"
    )
    assert field["scale"] == {
        "kind": "heat",
        "min": 0.0,
        "mid": 0.5,
        "max": 1.0,
        "truncate": False,
        "inverse": False,
        "negative": "hide",
    }


def test_scene_mesh_visibility_matches_viewspec(pm: PathManager) -> None:
    """The grey-matter TI mesh is hidden by default (24-420 MB files) -- a
    real ViewSpec has no separate "lazy" flag; the embed's own host decides
    whether/when to fetch a dataset from the layer's own `visible`."""
    scene = scene_for("simulation", subject="ernie", simulation="L_Insula")
    visible = {layer["name"]: layer["visible"] for layer in scene["layers"]}
    assert visible["GM · TI_max (volume)"] is True
    assert visible["TI_max (volume)"] is False
    assert visible["WM · TI_max (volume)"] is False
    assert visible["GM mesh · TI_max"] is False  # the mesh layer


def test_scene_datasets_carry_no_bytes_field(pm: PathManager) -> None:
    """Unlike the retired TitScene, a real DatasetRef has no `bytes` field at
    all -- the embed's own loader reports dataset size once it starts a fetch."""
    scene = scene_for("subject", subject="ernie")
    assert "bytes" not in scene["datasets"][0]


def test_scene_msh_gets_the_opt_sidecar_and_field_and_clip(pm: PathManager) -> None:
    mesh = os.path.join(
        pm.simulation("ernie", "L_Insula"), "TI", "mesh", "grey_L_Insula_TI.msh"
    )
    scene = scene_for("custom", path=mesh)
    layer = scene["layers"][0]
    dataset = dataset_of(scene, layer)

    assert dataset["kind"] == "mesh"
    assert (
        dataset["sidecars"]["opt"]["path"]
        == "/api/files/raw/" + mesh.lstrip("/") + ".opt"
    )
    assert layer["kind"] == "mesh"
    assert layer["field"]["name"] == "TI_max"  # guessed from the basename
    assert layer["clip"]["planes"][0]["followCursor"] is True
    assert layer["contoursIn2D"] is True  # grey matter reads best as an outline
    assert scene["layout"]["kind"] == "3d+1"
    assert scene["layout"]["cells"] == ["view3d", "axial"]


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("grey_Thalamus_TI.msh", "TI_max"),
        ("Thalamus_normal.msh", "TI_normal"),
        ("Thalamus_mTI.msh", "mTI_max"),
        ("ernie_TDCS_1_scalar.msh", "magnE"),
        ("ernie.msh", None),
    ],
)
def test_mesh_field_guess(name: str, field: str | None) -> None:
    assert viewspec._scene_field_name(name) == field


def test_scene_ids_are_stable_across_calls(pm: PathManager) -> None:
    first = scene_for("simulation", subject="ernie", simulation="L_Insula")
    second = scene_for("simulation", subject="ernie", simulation="L_Insula")
    assert [d["id"] for d in first["datasets"]] == [d["id"] for d in second["datasets"]]
    assert [layer["id"] for layer in first["layers"]] == [
        layer["id"] for layer in second["layers"]
    ]


def test_scene_layout_is_2x2_without_a_mesh(pm: PathManager) -> None:
    scene = scene_for("subject", subject="ernie")
    assert scene["layout"] == {
        "kind": "2x2",
        "cells": ["axial", "coronal", "sagittal", "view3d"],
    }


def test_scene_active_layer_is_the_first_visible_one(pm: PathManager) -> None:
    scene = scene_for("simulation", subject="ernie", simulation="L_Insula")
    active = next(la for la in scene["layers"] if la["id"] == scene["activeLayerId"])
    assert active["visible"] is True


# ── cursor ───────────────────────────────────────────────────────────────────


def test_scene_cursor_defaults_to_the_origin(pm: PathManager) -> None:
    assert scene_for("subject", subject="ernie")["cursor"] == [0.0, 0.0, 0.0]


def test_scene_cursor_comes_from_a_spherical_analysis(pm: PathManager) -> None:
    import json as _json

    analysis_dir = os.path.join(
        pm.simulation("ernie", "L_Insula"), "Analyses", "Voxel", "sphere_run"
    )
    os.makedirs(analysis_dir)
    Path(analysis_dir, "roi_overlay.nii.gz").write_bytes(b"roi")
    Path(analysis_dir, "analysis.json").write_text(
        _json.dumps({"analysis_type": "spherical", "center": [10.0, -20.0, 30.0]})
    )

    scene = scene_for(
        "analysis", subject="ernie", simulation="L_Insula", analysis="sphere_run"
    )
    assert scene["cursor"] == [10.0, -20.0, 30.0]


def test_scene_mesh_clip_plane_offset_tracks_the_cursor(pm: PathManager) -> None:
    import json as _json

    analysis_dir = os.path.join(
        pm.simulation("ernie", "L_Insula"), "Analyses", "Voxel", "sphere_run"
    )
    os.makedirs(analysis_dir)
    Path(analysis_dir, "roi_overlay.nii.gz").write_bytes(b"roi")
    Path(analysis_dir, "analysis.json").write_text(
        _json.dumps({"analysis_type": "spherical", "center": [10.0, -20.0, 30.0]})
    )
    # the mesh layer only builds for the default TI_max field, so ask for it via `simulation`
    scene = scene_for(
        "simulation", subject="ernie", simulation="L_Insula", analysis="sphere_run"
    )
    mesh = layers_by_kind(scene, "mesh")[0]
    assert mesh["clip"]["planes"][0]["plane"]["offset"] == 10.0


# ── purity / robustness ──────────────────────────────────────────────────────


def test_scene_of_an_empty_spec_is_valid_and_empty() -> None:
    scene = viewspec.to_tetravox_viewspec({"space": "mni", "layers": []})
    assert_valid_viewspec(scene)
    assert scene["datasets"] == []
    assert scene["layers"] == []
    assert scene["activeLayerId"] is None
    assert scene["layout"] == {
        "kind": "2x2",
        "cells": ["axial", "coronal", "sagittal", "view3d"],
    }
    assert scene["version"] == 2


def test_finish_spec_attaches_both_derived_views() -> None:
    """One authority: an edited spec posted to /api/view/args gets its argv and
    its scene from the same call, so they can never describe different files."""
    spec = {
        "space": "subject",
        "layers": [
            {
                "path": "/mnt/000/T1.nii.gz",
                "kind": "volume",
                "colormap": "grayscale",
                "opacity": 1.0,
                "visible": True,
            }
        ],
    }
    finished = viewspec.finish_spec(spec)
    assert finished["freeview_args"][0].startswith("/mnt/000/T1.nii.gz:")
    assert (
        finished["scene"]["datasets"][0]["path"] == "/api/files/raw/mnt/000/T1.nii.gz"
    )
    assert_valid_viewspec(finished["scene"])


def test_every_view_kind_produces_a_schema_valid_scene(pm: PathManager) -> None:
    """A broad sweep, not just the targeted cases above."""
    for spec in (
        viewspec.build_view("subject", subject="ernie"),
        viewspec.build_view("subject", subject="ernie", space="mni"),
        viewspec.build_view("simulation", subject="ernie", simulation="L_Insula"),
        viewspec.build_view(
            "simulation", subject="ernie", simulation="L_Insula", field="magnE"
        ),
        viewspec.build_view("group"),
    ):
        assert spec is not None
        assert_valid_viewspec(spec["scene"])
