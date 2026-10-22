"""Analyses of one ROI with a different field or tissue are different folders.

What this pins (2026-10-22)
    The analysis folder used to be named by space, ROI shape and atlas only, so analysing a
    sphere for ``TI_max`` and then ``hf_peak`` (or grey and then white matter) reused one
    folder: the server's overwrite question asked to *replace* an analysis that was in fact
    another one, and when the second run wrote fewer files (``visualize`` off) the folder
    mixed the two runs -- an overlay of one field beside the numbers of another.

    The decision (recorded in the commit): the field and the tissue are part of a folder's
    identity. The default analysis -- the envelope (``TI_max``/``mTI_max``, or no field
    named) on grey matter -- keeps the name it always had, so analyses already on disk keep
    theirs; any other field adds ``_<field>``, a voxel analysis of white matter or both
    tissues adds ``_WM``/``_both``. Within one folder ``analysis.json``'s ``field_name``,
    ``results.csv``'s ``field_name`` and the overlay's values are all that one field and
    tissue, and the plan's ``exists``/``will_overwrite`` follow the same identity.

Where the expectations come from
    A synthetic 4x4x4 voxel simulation written with real nibabel: each NIfTI holds a
    hand-written formula (``1 + i + 4j + 16k``, scaled and offset per field and tissue). The
    sphere of radius 1 mm about voxel (1, 1, 1) on the identity grid holds that voxel and its
    six face neighbours (hand-listed below), so each run's ``roi_mean`` is the mean of the
    formula over those seven voxels, and the overlay must hold exactly those seven values.
    The legacy folder name is the one a run of this sphere wrote before this change.

Run: .venv/bin/python -m pytest tests/test_analysis_output_identity.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import importlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-identity"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SID, SIM = "001", "M1"
CENTER, RADIUS = (1.0, 1.0, 1.0), 1.0
#: The voxels within 1 mm of (1, 1, 1) on a 1 mm identity grid: the centre and its six faces.
ROI_VOXELS = [
    (1, 1, 1),
    (0, 1, 1),
    (2, 1, 1),
    (1, 0, 1),
    (1, 2, 1),
    (1, 1, 0),
    (1, 1, 2),
]
#: (field, tissue) -> (NIfTI the simulator writes, offset, scale) of the hand formula.
COMBOS = {
    ("TI_max", "GM"): ("grey_M1_TI_subject_TI_max.nii.gz", 0.0, 1.0),
    ("hf_peak", "GM"): ("grey_M1_TI_subject_hf_peak.nii.gz", 100.0, 2.0),
    ("TI_max", "WM"): ("white_M1_TI_subject_TI_max.nii.gz", 50.0, 3.0),
}
#: The folder this sphere's default (TI_max, GM) analysis was written to before 2026-10-22.
LEGACY_NAME = "sphere_x1.00_y1.00_z1.00_r1.0_subject"


def _formula(offset: float, scale: float) -> np.ndarray:
    i, j, k = np.indices((4, 4, 4))
    return offset + scale * (1 + i + 4 * j + 16 * k)


def _hand_mean(offset: float, scale: float) -> float:
    return float(
        np.mean([offset + scale * (1 + i + 4 * j + 16 * k) for i, j, k in ROI_VOXELS])
    )


@pytest.fixture()
def real_nibabel(monkeypatch):
    """Real nibabel in place of the suite's mock, for this test only."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "nibabel"
    }
    try:
        nib = importlib.import_module("nibabel")
    except ImportError as exc:  # pragma: no cover - the test extra installs it
        sys.modules.update(saved)
        print(f"skipping: real nibabel is not importable ({exc})")
        pytest.skip("real nibabel is not installed; pip install -e '.[test]'")
    import tit.analyzer.visualizer as visualizer

    monkeypatch.setattr(visualizer, "nib", nib)
    yield nib
    for key in [k for k in sys.modules if k.split(".")[0] == "nibabel"]:
        del sys.modules[key]
    sys.modules.update(saved)


@pytest.fixture()
def project(tmp_path: Path, real_nibabel, monkeypatch) -> Path:
    import tit.analyzer.analyzer as analyzer_mod

    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    m2m = Path(pm.m2m(SID))
    m2m.mkdir(parents=True)
    (m2m / f"{SID}.msh").write_bytes(b"")
    niftis = Path(pm.simulation(SID, SIM)) / "TI" / "niftis"
    niftis.mkdir(parents=True)
    for name, offset, scale in COMBOS.values():
        img = real_nibabel.Nifti1Image(
            _formula(offset, scale).astype(np.float32), np.eye(4)
        )
        real_nibabel.save(img, str(niftis / name))
    # matplotlib is mocked on the host; the histogram is not what is checked here.
    monkeypatch.setattr(analyzer_mod, "save_histogram", lambda **kw: None)
    monkeypatch.setenv("TIT_NO_ROI_PLATE", "1")
    return root


def _analyze(field: str, tissue: str, visualize: bool):
    from tit.analyzer import Analyzer

    analyzer = Analyzer(SID, SIM, space="voxel", tissue_type=tissue, field=field)
    return analyzer.analyze_sphere(CENTER, RADIUS, visualize=visualize)


def _results(folder: Path) -> dict[str, str]:
    with open(folder / "results.csv", newline="") as fh:
        return {row["Metric"]: row["Value"] for row in csv.DictReader(fh)}


def _folders(root: Path) -> set[Path]:
    return {p.parent for p in root.rglob("results.csv")}


def _check_folder(folder: Path, field: str, tissue: str, nib) -> None:
    _, offset, scale = COMBOS[(field, tissue)]
    meta = json.loads((folder / "analysis.json").read_text())
    rows = _results(folder)
    assert meta["field_name"] == rows["field_name"] == field
    assert meta["tissue_types"] == [tissue]
    assert float(rows["roi_mean"]) == pytest.approx(_hand_mean(offset, scale), rel=1e-6)
    overlay = np.asarray(nib.load(str(folder / "roi_overlay.nii.gz")).dataobj)
    nonzero = {tuple(int(v) for v in idx) for idx in np.argwhere(overlay > 0)}
    assert nonzero == set(ROI_VOXELS)
    expected = _formula(offset, scale)
    for idx in ROI_VOXELS:
        assert overlay[idx] == pytest.approx(expected[idx], rel=1e-6)


def test_each_field_and_tissue_keeps_its_own_folder(project, real_nibabel) -> None:
    written: dict[tuple[str, str], Path] = {}
    for field, tissue in COMBOS:
        before = _folders(project)
        _analyze(field, tissue, visualize=True)
        new = _folders(project) - before
        assert len(new) == 1, f"{field}/{tissue} reused a folder: {new or 'none new'}"
        written[(field, tissue)] = new.pop()
    for (field, tissue), folder in written.items():
        _check_folder(folder, field, tissue, real_nibabel)

    # The default analysis keeps the name it had before field and tissue were in it.
    assert written[("TI_max", "GM")].name == LEGACY_NAME
    assert written[("hf_peak", "GM")].name == f"{LEGACY_NAME}_hf_peak"
    assert written[("TI_max", "WM")].name == f"{LEGACY_NAME}_WM"

    # Re-running every combination without figures replaces each one in place: still three
    # folders, each still one field and tissue throughout.
    for field, tissue in COMBOS:
        _analyze(field, tissue, visualize=False)
    assert _folders(project) == set(written.values())
    for (field, tissue), folder in written.items():
        _check_folder(folder, field, tissue, real_nibabel)


def test_naming_the_envelope_is_the_default_analysis(project) -> None:
    from tit.analyzer import Analyzer

    _analyze("TI_max", "GM", visualize=False)
    Analyzer(SID, SIM, space="voxel").analyze_sphere(CENTER, RADIUS)  # field=None
    assert {p.name for p in _folders(project)} == {LEGACY_NAME}


@pytest.fixture()
def client(project: Path) -> TestClient:
    return TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )


def _plan(client: TestClient, field, tissue, space="voxel") -> dict:
    config = {
        "mode": "single",
        "subject_id": SID,
        "simulation": SIM,
        "space": space,
        "analysis_type": "spherical",
        "center": list(CENTER),
        "radius": RADIUS,
        "field": field,
        "tissue_type": tissue,
    }
    resp = client.post("/api/plan/analyzer", json={"config": config}, headers=BEARER)
    assert resp.status_code == 200, resp.text
    (job,) = resp.json()["jobs"]
    return job


def test_plan_exists_follows_the_same_identity(project, client) -> None:
    fresh = {combo: _plan(client, *combo) for combo in COMBOS}
    assert all(not j["exists"] and not j["will_overwrite"] for j in fresh.values())

    _analyze("TI_max", "GM", visualize=False)
    written = {p.resolve() for p in _folders(project)}
    after = {combo: _plan(client, *combo) for combo in COMBOS}
    # Only the analysis that ran exists, and the plan names its folder.
    assert {Path(os.path.realpath(after[("TI_max", "GM")]["output_dir"]))} == written
    assert after[("TI_max", "GM")]["exists"] is True
    assert after[("TI_max", "GM")]["will_overwrite"] is True
    for combo in [("hf_peak", "GM"), ("TI_max", "WM")]:
        assert after[combo]["exists"] is False, combo
        assert after[combo]["will_overwrite"] is False, combo
    # The envelope named or not, in any tissue spelling the config accepts, is one analysis.
    assert (
        _plan(client, None, "gm")["output_dir"] == after[("TI_max", "GM")]["output_dir"]
    )
    assert _plan(client, "TI_max", "GM")["exists"] is True


def test_mesh_folders_tell_fields_apart_but_not_tissues(project, client) -> None:
    ti = _plan(client, "TI_max", "GM", space="mesh")["output_dir"]
    hf = _plan(client, "hf_peak", "GM", space="mesh")["output_dir"]
    assert ti != hf and Path(hf).name == f"{Path(ti).name}_hf_peak"
    # A mesh analysis is always the grey-matter surface; the tissue setting is not used.
    assert _plan(client, "TI_max", "WM", space="mesh")["output_dir"] == ti
    # mTI_max is the same envelope under its 4-pair spelling: the default analysis too.
    assert _plan(client, "mTI_max", "GM", space="mesh")["output_dir"] == ti


def test_voxel_folder_names_for_every_tissue_and_a_field(project, client) -> None:
    base = Path(_plan(client, None, "GM")["output_dir"]).name
    assert base == LEGACY_NAME
    names = {
        tissue: Path(_plan(client, "TI_avg", tissue)["output_dir"]).name
        for tissue in ("GM", "WM", "both", "BOTH")
    }
    assert names == {
        "GM": f"{LEGACY_NAME}_TI_avg",
        "WM": f"{LEGACY_NAME}_TI_avg_WM",
        "both": f"{LEGACY_NAME}_TI_avg_both",
        "BOTH": f"{LEGACY_NAME}_TI_avg_both",
    }


def test_labels_differing_only_in_unsafe_characters_never_share_a_folder() -> None:
    from tit.paths import NAME_RE, PathManager

    names = {
        label: PathManager.cortical_analysis_name(
            whole_head=False, region=label, atlas_name="ThalamicNuclei"
        )
        for label in ("Left-MV(Re)", "Left-MV_Re_", "Left-MV,Re,")
    }
    assert len(set(names.values())) == 3
    assert all(NAME_RE.fullmatch(name) for name in names.values()), names
    # A label that is already a valid name keeps its readable folder name.
    assert names["Left-MV_Re_"] == "cortical_Left-MV_Re__ThalamicNuclei"
