"""``POST /api/view/open`` — the scene file the host Tetravox desktop app opens.

V2 (``dev/notes/v3-native-panes-external-viewer-plan.md``).  Three properties
are worth a test each, and each is a way the feature can fail *silently*:

1. **The file name ends in ``.tetravox.json``.**  Measured in the Tetravox repo
   at 0.3.11: ``packages/app/src/main/menu.ts::isScenePath`` is
   ``/\\.tetravox\\.json$/i`` and ``electron-builder.yml`` claims exactly that
   compound extension.  Any other suffix -- the plan's own working name
   ``.tvx.json`` included -- is routed as a *dataset* and the app tries to read
   the JSON as a volume.  Nothing errors on this side; the picture is just
   wrong at the far end.
2. **Every dataset path is a filesystem path, not a URL.**  The embed fetched
   ``/api/files/raw/...`` back through this origin.  A desktop app on the host
   opens files.  A scene that still carried URLs would load an empty viewer.
3. **The document is still a valid ViewSpec v2** after the rewrite -- asserted
   against ``contracts/tetravox-viewspec-v2.schema.json``, the same schema
   ``tests/test_viewspec_scene.py`` holds the URL form to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager
from tit.server.routes import viewers

jsonschema = pytest.importorskip(
    "jsonschema",
    reason=(
        "jsonschema is not a runtime dependency; install with "
        "`python3 -m pip install --user --break-system-packages jsonschema` "
        "to run this test file"
    ),
)

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
    """``ernie`` with a T1 and a labelled atlas — enough for ``kind=subject``."""
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


def _open(monkeypatch, host_root: str | None, **body):
    monkeypatch.setattr(
        "tit.server.host_path.host_project_dir", lambda _container: host_root
    )
    return viewers.view_open({"kind": "subject", "subject": "ernie", **body})


# ── the name ─────────────────────────────────────────────────────────────────


def test_the_scene_file_uses_the_extension_the_tetravox_app_actually_claims(
    pm: PathManager, monkeypatch
) -> None:
    result = _open(monkeypatch, None)
    assert result["name"].endswith(".tetravox.json")
    # Not the plan's working name, which the app classifies as data.
    assert not result["name"].endswith(".tvx.json")
    assert os.path.isfile(result["path"])
    assert os.path.dirname(result["path"]) == viewers.viewer_scene_dir()
    assert result["path"].endswith(
        os.path.join("code", "ti-toolbox", "viewer", result["name"])
    )


def test_opening_twice_overwrites_rather_than_accumulating(
    pm: PathManager, monkeypatch
) -> None:
    first = _open(monkeypatch, None)
    second = _open(monkeypatch, None)
    assert first["path"] == second["path"]
    directory = viewers.viewer_scene_dir()
    assert os.listdir(directory) == [first["name"]]


def test_no_partial_file_is_left_behind(pm: PathManager, monkeypatch) -> None:
    """The app may be watching the path from a previous Open; half a JSON
    document is a parse error on screen, so the write is rename-in-place."""
    _open(monkeypatch, None)
    assert not any(
        n.endswith(".partial") for n in os.listdir(viewers.viewer_scene_dir())
    )


# ── the paths ────────────────────────────────────────────────────────────────


def test_every_dataset_path_is_a_host_file_path_not_an_api_url(
    pm: PathManager, tmp_path: Path, monkeypatch
) -> None:
    result = _open(monkeypatch, "/Users/me/datasets/000")
    written = json.loads(Path(result["path"]).read_text())
    assert written == result["scene"]
    assert written["datasets"], "the fixture must produce at least one dataset"
    for dataset in written["datasets"]:
        for key in ("path", "absPath"):
            assert not dataset[key].startswith("/api/"), dataset
            assert dataset[key].startswith("/Users/me/datasets/000/"), dataset
        for sidecar in (dataset.get("sidecars") or {}).values():
            assert sidecar["path"].startswith("/Users/me/datasets/000/"), sidecar
    assert result["host_path"].startswith("/Users/me/datasets/000/code/ti-toolbox/")


def test_an_unknowable_host_root_falls_back_to_container_paths_and_says_so(
    pm: PathManager, tmp_path: Path, monkeypatch
) -> None:
    """Browser mode downloads the file; the honest answer is the container path
    and ``host_path: null``, not a guess at the host's own layout."""
    result = _open(monkeypatch, None)
    assert result["host_path"] is None
    for dataset in result["scene"]["datasets"]:
        assert dataset["path"].startswith(str(tmp_path)), dataset
        assert not dataset["path"].startswith("/api/")


def test_a_windows_host_root_keeps_the_hosts_own_separator(
    pm: PathManager, monkeypatch
) -> None:
    result = _open(monkeypatch, r"C:\Users\me\data")
    assert result["host_path"].startswith(r"C:\Users\me\data\code\ti-toolbox\viewer")
    for dataset in result["scene"]["datasets"]:
        assert dataset["path"].startswith(r"C:\Users\me\data\\") or dataset[
            "path"
        ].startswith(r"C:\Users\me\data" + "\\")


# ── still a ViewSpec ─────────────────────────────────────────────────────────


def test_the_written_document_is_a_valid_viewspec_v2(
    pm: PathManager, monkeypatch
) -> None:
    result = _open(monkeypatch, "/Users/me/datasets/000")
    errors = sorted(
        _VALIDATOR.iter_errors(result["scene"]), key=lambda e: list(e.absolute_path)
    )
    assert not errors, "\n".join(
        f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
    )


def test_the_url_form_of_the_same_scene_is_untouched(
    pm: PathManager, monkeypatch
) -> None:
    """``GET /api/view/{kind}`` still answers with URLs -- localising is the
    open route's own step, not a change to ``build_view``."""
    _open(monkeypatch, "/Users/me/datasets/000")
    spec = viewspec.build_view("subject", subject="ernie")
    assert spec is not None
    assert all(
        d["path"].startswith("/api/files/raw/") for d in spec["scene"]["datasets"]
    )


# ── the two addressings (VE) ─────────────────────────────────────────────────


def test_view_keeps_the_urls_the_embed_fetches_and_scene_does_not(
    pm: PathManager, monkeypatch
) -> None:
    """One response, two languages: ``view`` for the iframe, ``scene`` for the file."""
    result = _open(monkeypatch, "/Users/me/datasets/000")
    assert result["view"]["datasets"], "the scene resolved to no datasets at all"
    for dataset in result["view"]["datasets"]:
        assert dataset["path"].startswith("/api/files/raw/")
        assert dataset["absPath"].startswith("/api/files/raw/")
    for dataset in result["scene"]["datasets"]:
        assert not dataset["path"].startswith("/api/")
        assert dataset["path"].startswith("/Users/me/datasets/000/")


def test_both_addressings_are_the_same_resolution(pm: PathManager, monkeypatch) -> None:
    """Same datasets, same order, same layers -- only the paths differ.

    This is the property the single ``build_view`` call exists for.  Resolving twice would let a
    job finishing between the two calls put a file in one document and not the other, and then the
    list the page shows, the file on disk and the picture on screen would disagree with nothing to
    say which was right.
    """
    result = _open(monkeypatch, "/Users/me/datasets/000")
    view, scene = result["view"], result["scene"]
    assert [d["id"] for d in view["datasets"]] == [d["id"] for d in scene["datasets"]]
    assert [d["name"] for d in view["datasets"]] == [d["name"] for d in scene["datasets"]]
    assert view["layers"] == scene["layers"]


def test_the_embed_addressing_is_also_a_valid_viewspec_v2(
    pm: PathManager, monkeypatch
) -> None:
    result = _open(monkeypatch, "/Users/me/datasets/000")
    errors = sorted(
        _VALIDATOR.iter_errors(result["view"]), key=lambda e: list(e.absolute_path)
    )
    assert not errors, "\n".join(
        f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
    )


def test_a_dry_run_still_answers_with_both(pm: PathManager, monkeypatch) -> None:
    """The Viewer page's file list is a dry run, and Open is the same call without the flag.

    If ``view`` were only built on a real write, the page would resolve one document for the list
    and the server a different one for the picture.
    """
    result = _open(monkeypatch, "/Users/me/datasets/000", dry_run=True)
    assert result["dry_run"] is True
    assert not os.path.exists(result["path"])
    assert result["view"]["datasets"]
    assert all(d["path"].startswith("/api/files/raw/") for d in result["view"]["datasets"])


# ── refusals ─────────────────────────────────────────────────────────────────


def test_an_unknown_kind_is_a_422_and_writes_nothing(
    pm: PathManager, monkeypatch
) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        viewers.view_open({"kind": "nonsense"})
    assert excinfo.value.status_code == 422
    assert not os.path.isdir(viewers.viewer_scene_dir())


def test_an_unknown_subject_is_a_404_and_writes_nothing(
    pm: PathManager, monkeypatch
) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        viewers.view_open({"kind": "subject", "subject": "nobody"})
    assert excinfo.value.status_code == 404
    assert not os.path.isdir(viewers.viewer_scene_dir())
