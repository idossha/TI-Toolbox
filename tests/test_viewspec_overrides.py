"""Everything ``POST /api/view/open`` gained after VX, and the guarantee it kept.

Two lanes, in one file because they are one endpoint's optional inputs and one
compatibility claim:

* **VM** (``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``) -- scene
  ``overrides`` and ``extras``.  Every control a page shows has to land in the
  scene file or the control is a lie; these tests are that claim, knob by knob.
  The UI that exposed them was withdrawn as "too much" (VM2), and the server
  half stays: it is tested, additive, and the next caller that wants a camera
  preset does not have to re-derive it.
* **VM2** (``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``) -- the
  explicit ``files`` list, which *is* the scene when it is given, and the
  ``/api/viewer/candidates`` catalogue behind the page's "+ Add…".

The load-bearing test in both halves is the same one: **absent means
byte-identical output**, because that is what makes either addition safe for
every caller that predates it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager
from tit.server.routes import viewers

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR = jsonschema.Draft202012Validator(
    json.loads(
        (REPO_ROOT / "contracts" / "tetravox-viewspec-v2.schema.json").read_text()
    )
)


@pytest.fixture(autouse=True)
def _reset_pm():
    reset_path_manager()
    yield
    reset_path_manager()


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch) -> PathManager:
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    seg_dir = os.path.join(m2m, "segmentation")
    os.makedirs(seg_dir)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1" * 100)
    Path(seg_dir, "labeling.nii.gz").write_bytes(b"lab")
    Path(seg_dir, "labeling_LUT.txt").write_text("1 GM 0 255 0 255\n")
    resources = tmp_path / "resources_atlas"
    resources.mkdir()
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(resources))
    return pm


def _scene(pm: PathManager, **kwargs) -> dict:
    spec = viewspec.build_view("subject", subject="ernie", **kwargs)
    assert spec is not None
    return spec["scene"]


# ── the compatibility guarantee ──────────────────────────────────────────────


def test_absent_overrides_and_extras_produce_byte_identical_output(
    pm: PathManager,
) -> None:
    """The whole safety argument for this feature, stated as bytes.

    Not "equivalent", not "the same fields": the same JSON document, because
    every caller that existed before overrides passes neither argument and
    must be unable to tell that they now exist.
    """
    before = json.dumps(_scene(pm), sort_keys=True)
    after = json.dumps(_scene(pm, extras=None, overrides=None), sort_keys=True)
    assert before == after
    # And an *empty* override document is the same no-op as an absent one.
    assert json.dumps(_scene(pm, overrides={}), sort_keys=True) == before


def test_an_override_naming_nothing_we_understand_changes_nothing(
    pm: PathManager,
) -> None:
    before = json.dumps(_scene(pm), sort_keys=True)
    noisy = {
        "layers": {"L99": {"opacity": 0.1}},
        "layout": "hexagons",
        "camera": "Z",
        "background": "chartreuse",
        "somethingElse": True,
    }
    assert json.dumps(_scene(pm, overrides=noisy), sort_keys=True) == before


# ── per-layer knobs ──────────────────────────────────────────────────────────


def test_layer_visibility_opacity_colormap_and_threshold_reach_the_scene(
    pm: PathManager,
) -> None:
    scene = _scene(
        pm,
        overrides={
            "layers": {
                "L1": {
                    "visible": False,
                    "opacity": 0.42,
                    "colormap": "viridis",
                    "showIn3D": True,
                    "threshold": {"lo": 0.2, "hi": 0.9},
                }
            }
        },
    )
    layer = next(la for la in scene["layers"] if la["id"] == "L1")
    assert layer["visible"] is False
    assert layer["opacity"] == pytest.approx(0.42)
    assert layer["colormap"] == "viridis"
    assert layer["showIn3D"] is True
    assert layer["threshold"]["lo"] == pytest.approx(0.2)
    assert layer["threshold"]["hi"] == pytest.approx(0.9)
    _VALIDATOR.validate(scene)


def test_opacity_is_clamped_rather_than_written_out_of_range(pm: PathManager) -> None:
    """The engine's own type says 0..1; a slider that somehow sends 4 must not
    produce a document the app refuses to open."""
    scene = _scene(pm, overrides={"layers": {"L0": {"opacity": 4}}})
    assert scene["layers"][0]["opacity"] == 1.0
    scene = _scene(pm, overrides={"layers": {"L0": {"opacity": -3}}})
    assert scene["layers"][0]["opacity"] == 0.0
    _VALIDATOR.validate(scene)


def test_a_null_threshold_bound_clears_it(pm: PathManager) -> None:
    scene = _scene(pm, overrides={"layers": {"L0": {"threshold": {"lo": None}}}})
    assert scene["layers"][0]["threshold"]["lo"] is None


def test_hiding_the_active_layer_moves_the_active_layer(pm: PathManager) -> None:
    """Otherwise the app opens with its inspector pointed at something invisible."""
    scene = _scene(pm, overrides={"layers": {"L0": {"visible": False}}})
    assert scene["activeLayerId"] != "L0"
    assert scene["activeLayerId"] in [la["id"] for la in scene["layers"] if la["visible"]]


# ── layout, camera, convention, background ───────────────────────────────────


@pytest.mark.parametrize("kind", sorted(viewspec.SCENE_LAYOUTS))
def test_every_offered_layout_lands_with_its_cells(pm: PathManager, kind: str) -> None:
    scene = _scene(pm, overrides={"layout": kind})
    assert scene["layout"]["kind"] == kind
    assert scene["layout"]["cells"] == viewspec.SCENE_LAYOUTS[kind]
    _VALIDATOR.validate(scene)


@pytest.mark.parametrize("preset", sorted(viewspec.CAMERA_PRESETS))
def test_every_camera_preset_is_a_unit_quaternion_that_lands(
    pm: PathManager, preset: str
) -> None:
    scene = _scene(pm, overrides={"camera": preset})
    rotation = scene["view3d"]["camera"]["rotation"]
    assert rotation == viewspec.CAMERA_PRESETS[preset]
    assert sum(c * c for c in rotation) == pytest.approx(1.0)
    _VALIDATOR.validate(scene)


def test_radiological_and_named_and_explicit_backgrounds(pm: PathManager) -> None:
    scene = _scene(pm, overrides={"radiological": True, "background": "light"})
    assert scene["radiological"] is True
    assert scene["background"] == viewspec.SCENE_BACKGROUNDS["light"]
    scene = _scene(pm, overrides={"background": [0.0, 0.5, 0.0, 1.0]})
    assert scene["background"] == [0.0, 0.5, 0.0, 1.0]
    _VALIDATOR.validate(scene)


# ── extras ───────────────────────────────────────────────────────────────────


def test_an_extra_the_view_already_opens_adds_nothing(pm: PathManager) -> None:
    """`kind=subject` already opens the T1 and the atlas; ticking them is a
    statement of intent, not a second copy of the same volume."""
    plain = _scene(pm)
    with_extras = _scene(pm, extras=["t1", "atlas"])
    assert [la["name"] for la in with_extras["layers"]] == [
        la["name"] for la in plain["layers"]
    ]


def test_an_unknown_extra_is_ignored(pm: PathManager) -> None:
    assert json.dumps(_scene(pm, extras=["asteroids"]), sort_keys=True) == json.dumps(
        _scene(pm), sort_keys=True
    )


# ── the route ────────────────────────────────────────────────────────────────


def test_dry_run_resolves_everything_and_writes_no_file(
    pm: PathManager, monkeypatch
) -> None:
    monkeypatch.setattr("tit.server.host_path.host_project_dir", lambda _c: None)
    result = viewers.view_open(
        {
            "kind": "subject",
            "subject": "ernie",
            "dry_run": True,
            "overrides": {"layout": "3d-only"},
        }
    )
    assert result["dry_run"] is True
    assert result["scene"]["layout"]["kind"] == "3d-only"
    assert not os.path.exists(result["path"])
    assert not os.path.isdir(viewers.viewer_scene_dir())


def test_the_route_reports_each_resolved_file_with_its_size(
    pm: PathManager, monkeypatch
) -> None:
    monkeypatch.setattr("tit.server.host_path.host_project_dir", lambda _c: None)
    result = viewers.view_open({"kind": "subject", "subject": "ernie"})
    by_name = {row["name"]: row for row in result["files"]}
    assert by_name
    t1 = next(row for row in result["files"] if row["path"].endswith("T1.nii.gz"))
    assert t1["bytes"] == 200  # b"t1" * 100
    assert t1["kind"] == "volume"


def test_the_route_passes_overrides_through_to_the_file_it_writes(
    pm: PathManager, monkeypatch
) -> None:
    monkeypatch.setattr("tit.server.host_path.host_project_dir", lambda _c: None)
    result = viewers.view_open(
        {
            "kind": "subject",
            "subject": "ernie",
            "overrides": {
                "layers": {"L0": {"opacity": 0.25}},
                "camera": "L",
                "radiological": True,
            },
        }
    )
    on_disk = json.loads(Path(result["path"]).read_text())
    assert on_disk["layers"][0]["opacity"] == pytest.approx(0.25)
    assert on_disk["view3d"]["camera"]["rotation"] == viewspec.CAMERA_PRESETS["L"]
    assert on_disk["radiological"] is True
    _VALIDATOR.validate(on_disk)


# ── presets ──────────────────────────────────────────────────────────────────


def test_a_preset_round_trips_through_the_project(pm: PathManager) -> None:
    """A composition is only worth its keystrokes if it comes back."""
    document = {
        "selection": {"kind": "simulation", "subject": "ernie"},
        "extras": ["t1"],
        "overrides": {"layout": "2x2"},
    }
    saved = viewers.save_viewer_preset("Deep target", document)
    assert saved["name"] == "Deep target"
    on_disk = Path(viewers.viewer_preset_dir()) / "Deep_target.json"
    assert on_disk.is_file()
    assert viewers.viewer_presets()["presets"] == [saved]
    assert viewers.delete_viewer_preset("Deep target")["deleted"] is True
    assert viewers.viewer_presets()["presets"] == []


def test_a_preset_name_that_cannot_become_a_file_is_refused_not_renamed(
    pm: PathManager,
) -> None:
    from fastapi import HTTPException

    for name in ("", "   ", "x" * 200):
        with pytest.raises(HTTPException) as excinfo:
            viewers.save_viewer_preset(name, {})
        assert excinfo.value.status_code == 422


def test_the_preset_directory_cannot_be_escaped(pm: PathManager) -> None:
    """Separators and dots become dashes, so the file lands in the presets
    directory whatever the name tried to say."""
    viewers.save_viewer_preset("../../escape", {})
    written = sorted(os.listdir(viewers.viewer_preset_dir()))
    assert written == ["------escape.json"]


def test_an_unparseable_preset_is_skipped_rather_than_emptying_the_menu(
    pm: PathManager,
) -> None:
    viewers.save_viewer_preset("good", {})
    Path(viewers.viewer_preset_dir(), "broken.json").write_text("{not json")
    assert [p["name"] for p in viewers.viewer_presets()["presets"]] == ["good"]


def test_listing_presets_before_any_are_saved_is_an_empty_list(pm: PathManager) -> None:
    assert viewers.viewer_presets() == {"presets": []}


# ── VM2: the file list is the scene ──────────────────────────────────────────


@pytest.fixture()
def sim(pm: PathManager) -> PathManager:
    """`ernie` with one simulation: a TI volume, a grey one and a mesh."""
    sim_dir = pm.simulation("ernie", "Thalamus")
    niftis = os.path.join(sim_dir, "TI", "niftis")
    mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    os.makedirs(niftis)
    os.makedirs(mesh_dir)
    Path(niftis, "Thalamus_TI_subject_TI_max.nii.gz").write_bytes(b"f" * 40)
    Path(niftis, "grey_Thalamus_TI_subject_TI_max.nii.gz").write_bytes(b"g" * 30)
    Path(mesh_dir, "grey_Thalamus_TI.msh").write_bytes(b"m" * 50)
    return pm


def _paths(spec: dict) -> list[str]:
    return [layer["path"] for layer in spec["layers"]]


def test_the_default_view_is_unchanged_when_no_file_list_is_sent(sim: PathManager) -> None:
    a = viewspec.build_view("simulation", subject="ernie", simulation="Thalamus")
    b = viewspec.build_view(
        "simulation", subject="ernie", simulation="Thalamus", files=None
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_the_file_list_is_authoritative_and_ordered(sim: PathManager) -> None:
    """The whole VM2 claim: these files, this order, nothing added back."""
    default = viewspec.build_view("simulation", subject="ernie", simulation="Thalamus")
    assert default is not None
    chosen = list(reversed(_paths(default)))[:2]
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="Thalamus", files=chosen
    )
    assert spec is not None
    assert _paths(spec) == chosen
    assert [d["path"] for d in spec["scene"]["datasets"]] == [
        viewspec._scene_raw_url(p) for p in chosen
    ]


def test_removing_a_file_removes_its_dataset_and_nothing_else(sim: PathManager) -> None:
    default = viewspec.build_view("simulation", subject="ernie", simulation="Thalamus")
    assert default is not None
    kept = [p for p in _paths(default) if "grey_" not in os.path.basename(p)]
    dropped = [p for p in _paths(default) if "grey_" in os.path.basename(p)]
    assert dropped, "fixture must have something to drop"
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="Thalamus", files=kept
    )
    assert spec is not None
    assert _paths(spec) == kept
    for path in dropped:
        assert viewspec._scene_raw_url(path) not in [
            d["path"] for d in spec["scene"]["datasets"]
        ]


def test_a_kept_file_keeps_the_view_type_s_own_settings(sim: PathManager) -> None:
    """Not re-derived: the *same* opacity, colormap and visibility the view gave it.

    This is why the client sends paths and not layer settings — how a file
    should look is a judgement about the data, and a client that mirrored it
    would drift from it."""
    default = viewspec.build_view("simulation", subject="ernie", simulation="Thalamus")
    assert default is not None
    by_path = {layer["path"]: layer for layer in default["layers"]}
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="Thalamus", files=list(by_path)
    )
    assert spec is not None
    for layer in spec["layers"]:
        assert layer == by_path[layer["path"]]


def test_an_added_file_is_described_from_scratch_by_its_name(sim: PathManager) -> None:
    m2m = pm_m2m = os.path.join(sim.m2m("ernie"))
    t1 = os.path.join(m2m, "T1.nii.gz")
    atlas = os.path.join(m2m, "segmentation", "labeling.nii.gz")
    mesh = os.path.join(sim.simulation("ernie", "Thalamus"), "TI", "mesh", "grey_Thalamus_TI.msh")
    spec = viewspec.build_view("subject", subject="ernie", files=[t1, atlas, mesh])
    assert spec is not None
    layers = {os.path.basename(layer["path"]): layer for layer in spec["layers"]}
    assert layers["T1.nii.gz"]["colormap"] == "grayscale"
    assert layers["labeling.nii.gz"]["colormap"] == "lut"
    assert layers["labeling.nii.gz"]["lut"].endswith("labeling_LUT.txt")
    # A mesh is 24-420 MB; it is added hidden, and the person makes it visible.
    assert layers["grey_Thalamus_TI.msh"]["visible"] is False
    assert layers["grey_Thalamus_TI.msh"]["colormap"] == "jet"
    _VALIDATOR.validate(spec["scene"])


def test_an_unresolvable_or_missing_row_is_dropped_not_fatal(sim: PathManager) -> None:
    """One stale row in a restored preset must not cost a person the scene."""
    t1 = os.path.join(sim.m2m("ernie"), "T1.nii.gz")
    spec = viewspec.build_view(
        "subject",
        subject="ernie",
        files=["/etc/passwd", os.path.join(sim.m2m("ernie"), "gone.nii.gz"), t1, t1],
    )
    assert spec is not None
    assert _paths(spec) == [t1]  # jailed out, missing out, and de-duplicated


def test_a_list_with_nothing_usable_in_it_is_a_404_not_an_empty_scene(
    sim: PathManager,
) -> None:
    assert viewspec.build_view("subject", subject="ernie", files=["/etc/passwd"]) is None


def test_the_route_writes_exactly_the_files_it_was_given(
    sim: PathManager, monkeypatch
) -> None:
    monkeypatch.setattr("tit.server.host_path.host_project_dir", lambda _c: None)
    t1 = os.path.join(sim.m2m("ernie"), "T1.nii.gz")
    result = viewers.view_open(
        {"kind": "simulation", "subject": "ernie", "simulation": "Thalamus", "files": [t1]}
    )
    on_disk = json.loads(Path(result["path"]).read_text())
    assert [d["path"] for d in on_disk["datasets"]] == [t1]
    assert [row["path"] for row in result["files"]] == [t1]
    _VALIDATOR.validate(on_disk)


# ── VM2: the "+ Add…" catalogue ──────────────────────────────────────────────


def test_the_candidates_are_real_files_with_sizes_grouped(sim: PathManager) -> None:
    found = viewspec.viewer_candidates("ernie", "Thalamus")
    by_name = {c["name"]: c for c in found}
    assert "T1.nii.gz" in by_name
    assert by_name["T1.nii.gz"]["bytes"] == 200
    assert by_name["T1.nii.gz"]["kind"] == "volume"
    assert by_name["grey_Thalamus_TI.msh"]["kind"] == "mesh"
    assert by_name["grey_Thalamus_TI.msh"]["group"] == "Simulation meshes"
    assert all(os.path.isfile(c["path"]) for c in found)
    assert len({c["path"] for c in found}) == len(found)


def test_candidates_never_offer_a_file_a_scene_cannot_read(sim: PathManager) -> None:
    """`.annot` parcellations, `.mat` matrices, logs and reports are not layers."""
    Path(sim.m2m("ernie"), "charm_log.html").write_text("<html>")
    Path(sim.m2m("ernie"), "segmentation", "lh.ernie_DK40.annot").write_bytes(b"x")
    names = [c["name"] for c in viewspec.viewer_candidates("ernie", "Thalamus")]
    assert not [n for n in names if n.endswith((".html", ".annot", ".mat", ".txt"))]


def test_an_unknown_subject_offers_nothing_rather_than_erroring(pm: PathManager) -> None:
    assert viewspec.viewer_candidates("nobody") == []
    assert viewspec.viewer_candidates(None) == []
