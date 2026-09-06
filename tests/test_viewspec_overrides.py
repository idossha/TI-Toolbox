"""Scene overrides and extras — the Viewer page's composition panel, on the wire (VM).

``dev/notes/v3-native-panes-external-viewer/VM.md``.  Every control the page
shows has to land in the scene file, or the control is a lie; these tests are
that claim, knob by knob.  The load-bearing one is the last section: **absent
overrides means byte-identical output**, because that is what makes the whole
addition safe for every caller that predates it.
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
