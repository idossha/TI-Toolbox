"""The catalog names every simulation NIfTI by the field and space the simulator wrote.

What this pins (2026-10-22, package p04 "catalog-sim-field-names")
    ``simulation_detail()['fields']`` feeds the Analyzer's Field dropdown and the Results tree.
    It used to take the last ``_`` token of an unrecognised name, so ``hf_peak`` came out as
    ``peak``, ``hf_sar`` as ``sar``, ``TI_avg`` as ``avg`` and ``mTI_max`` as ``max`` -- names
    the analyzer then rejected ("Unknown field: 'peak'"). High-frequency ``magnE`` volumes were
    globbed as ``*_scalar_*magnE.nii.gz``, so an anisotropic (``vn``/``dir``/``mc``) run listed
    none, in the catalog and in the viewer alike.

Where the expected values come from
    The writer model in ``tests/test_sim_output_naming_contract.py`` (``TI.py``/``mTI.py``
    field names, ``extract_fields``' tissue prefixes, mesh2nii's ``<base>_subject_<field>`` /
    ``<base>_MNI_MNI_<field>`` rule, the ``<sid>_TDCS_<i>_<cond>`` carrier names with ``A..Z``
    for mTI), checked against Dataset 000 there; the registry is ``tit.constants``. Real-data
    expectations below were read off the Dataset 000 listing (``ls .../niftis``).

Reproduce
    .venv/bin/python -m pytest tests/test_catalog_sim_fields.py -q -p no:cacheprovider
    TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest tests/test_catalog_sim_fields.py -q

Deliberately elsewhere
    Adversarial simulation names (``MNI_target``, ``grey_matter``):
    ``tests/test_nifti_space_classifier.py``. The validate route's own field check belongs to
    ``AnalyzerConfig`` (another package).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from tests.test_sim_output_naming_contract import (
    CONDUCTIVITIES,
    TISSUE_PREFIX,
    VOLUME_FIELDS,
    carrier_labels,
    envelope_base,
    nifti_name,
    write_simulation,
)
from tit import catalog
from tit.constants import get_field_names
from tit.paths import get_path_manager

#: What the old last-token rule produced; none of these is a field anything accepts.
TRUNCATED = {"peak", "sar", "avg", "max", "normal", "subject"}


def _detail(project: Path, sid: str, sim: str) -> dict:
    detail = catalog.simulation_detail(get_path_manager(str(project)), sid, sim)
    assert detail is not None
    return detail


@pytest.mark.parametrize("map_to_mni", [False, True])
@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_every_envelope_nifti_is_listed_with_the_field_space_and_tissue_written(
    tmp_path, mode, map_to_mni
):
    written = write_simulation(tmp_path, "101", "L_Insula", mode, map_to_mni=map_to_mni)
    detail = _detail(tmp_path, "101", "L_Insula")

    listed = {
        (os.path.basename(n["path"]), n["field"], n["space"], n["tissue"])
        for n in detail["niftis"]
        if n["field"] != "magnE"
    }
    expected = {
        (path.name, field, space, tissue)
        for (tissue, space, field), path in written["envelope"].items()
    }
    # 3 tissues x 4 fields x (1 or 2 spaces): the table the writer produced, nothing more.
    assert len(expected) == 3 * 4 * (2 if map_to_mni else 1)
    assert listed == expected

    registry = set(get_field_names()) | {"magnE"}
    assert set(detail["fields"]) <= registry
    assert not set(detail["fields"]) & TRUNCATED
    assert set(detail["fields"]) == set(VOLUME_FIELDS[mode]) | {"magnE"}
    assert detail["space"] == (["mni", "subject"] if map_to_mni else ["subject"])


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("field", get_field_names())
@pytest.mark.parametrize("space", ["subject", "mni"])
@pytest.mark.parametrize("tissue", list(TISSUE_PREFIX))
def test_any_registry_field_is_read_back_from_its_name(
    tmp_path, mode, field, space, tissue
):
    """The full (tissue x mode x space x registry field) table, one file at a time."""
    mode_dir = tmp_path / "Simulations" / "S" / mode
    (mode_dir / "niftis").mkdir(parents=True)
    name = nifti_name(envelope_base("S", mode, tissue), space, field)
    (mode_dir / "niftis" / name).write_bytes(b"nii")

    [entry] = catalog._mode_niftis(str(mode_dir), simulation="S")

    assert (entry["field"], entry["space"], entry["tissue"]) == (field, space, tissue)


@pytest.mark.parametrize("map_to_mni", [False, True])
@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("cond", CONDUCTIVITIES)
def test_carrier_magnE_niftis_are_listed_for_every_conductivity(
    tmp_path, cond, mode, map_to_mni
):
    from tit.viewspec import _hf_layers

    written = write_simulation(
        tmp_path, "101", "L_Insula", mode, cond=cond, map_to_mni=map_to_mni
    )
    n_pairs = 2 if mode == "TI" else 4
    detail = _detail(tmp_path, "101", "L_Insula")

    magnE = [n for n in detail["niftis"] if n["field"] == "magnE"]
    spaces = ("subject", "mni") if map_to_mni else ("subject",)
    for space in spaces:
        listed = {n["path"] for n in magnE if n["space"] == space}
        wanted = {
            str(written["hf"][(label, space)])
            for label in carrier_labels(mode, n_pairs)
        }
        assert len(wanted) == n_pairs
        assert listed == wanted
        assert all(n["tissue"] is None for n in magnE)
        # The viewer's high-frequency layers are the same files, in their own space only.
        layers = {layer["path"] for layer in _hf_layers(str(written["sim_dir"]), space)}
        assert layers == wanted
    assert len(magnE) == n_pairs * len(spaces)
    assert "magnE" in detail["fields"]


@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_every_listed_field_round_trips_through_the_analyzer(tmp_path, mode):
    """A field the catalog offers is one ``select_field_file`` opens -- the file written."""
    from tit.analyzer.field_selector import select_field_file

    written = write_simulation(tmp_path, "101", "L_Insula", mode)
    detail = _detail(tmp_path, "101", "L_Insula")
    offered = [f for f in detail["fields"] if f != "magnE"]
    assert len(offered) == 4
    for field in offered:
        for tissue, tissue_type in (("grey", "GM"), ("white", "WM"), (None, "both")):
            path, name = select_field_file(
                "101", "L_Insula", "voxel", tissue_type=tissue_type, field=field
            )
            assert path == written["envelope"][(tissue, "subject", field)]
            assert name == field


def test_detail_route_serves_registry_field_names(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    write_simulation(tmp_path, "101", "L_Insula", "TI", cond="vn")
    telemetry = tmp_path / "telemetry.json"
    monkeypatch.setattr("tit.telemetry._config_path", lambda: telemetry)
    monkeypatch.setattr("tit.telemetry._cached_config", None)
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="t")),
        base_url="http://127.0.0.1:8765",
    )
    response = client.get(
        "/api/catalog/simulations/L_Insula",
        params={"subject": "101"},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"] == sorted(["TI_max", "TI_avg", "hf_peak", "hf_sar", "magnE"])
    assert (
        sum(n["field"] == "magnE" for n in body["niftis"]) == 4
    )  # 2 carriers x 2 spaces


def test_files_the_simulator_did_not_name_are_not_offered_as_fields(tmp_path):
    written = write_simulation(tmp_path, "101", "L_Insula", "TI", map_to_mni=False)
    niftis = written["sim_dir"] / "TI" / "niftis"
    (niftis / "notes_peak.nii.gz").write_bytes(b"nii")  # a user's own file
    (niftis / "grey_L_Insula_TI_subject.nii.gz").write_bytes(b"nii")  # no field token
    detail = _detail(tmp_path, "101", "L_Insula")
    assert set(detail["fields"]) == {"TI_max", "TI_avg", "hf_peak", "hf_sar", "magnE"}
    names = {os.path.basename(n["path"]) for n in detail["niftis"]}
    assert "notes_peak.nii.gz" not in names


class _Messages(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_volumes_left_out_of_the_listing_are_named_in_the_debug_log(tmp_path):
    """A volume the catalog drops is diagnosable: the debug log names it, once per folder.

    ``grey_L_Insula_TI_MNI_TI_max`` is the one-``MNI`` spelling of the v2.0-2.2 shell loop
    (``${BASE}_MNI_<field>``); ``grey_L_Insula_TI`` a volume without a field suffix.
    """
    written = write_simulation(tmp_path, "101", "L_Insula", "TI")
    niftis = written["sim_dir"] / "TI" / "niftis"
    legacy = {"grey_L_Insula_TI_MNI_TI_max.nii.gz", "grey_L_Insula_TI.nii.gz"}
    for name in legacy:
        (niftis / name).write_bytes(b"nii")

    log = logging.getLogger("tit.catalog")
    handler, level = _Messages(), log.level
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        detail = _detail(tmp_path, "101", "L_Insula")
    finally:
        log.removeHandler(handler)
        log.setLevel(level)

    listed = {os.path.basename(n["path"]) for n in detail["niftis"]}
    assert listed == {p.name for p in written["envelope"].values()} | {
        p.name for p in written["hf"].values()
    }
    notes = [m for m in handler.messages if str(niftis) in m]
    assert len(notes) == 1, handler.messages
    assert set(notes[0].rsplit(": ", 1)[1].split(", ")) == legacy
    # The carriers' folder holds only names the simulator writes: nothing to say about it.
    hf_dir = str(written["sim_dir"] / "high_Frequency" / "niftis")
    assert not [m for m in handler.messages if hf_dir in m]


@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_the_viewer_names_every_written_volume_by_its_field(tmp_path, mode):
    """The Results tree labels ``grey_<sim>_TI_subject_TI_avg`` "GM · TI_avg (volume)".

    The label needs the field token (``_scene_field_name``): without it a volume is drawn
    as anatomy, in grayscale, under its raw file stem.
    """
    from tit.viewspec import _scene_field_name, _tree_node

    written = write_simulation(tmp_path, "101", "L_Insula", mode)
    region = {"grey": "GM · ", "white": "WM · ", None: ""}
    assert {field for _, _, field in written["envelope"]} == set(VOLUME_FIELDS[mode])
    for (tissue, _space, field), path in written["envelope"].items():
        assert _scene_field_name(path.name) == field, path.name
        assert _tree_node(str(path))["label"] == f"{region[tissue]}{field} (volume)"


# ── Dataset 000 ──────────────────────────────────────────────────────────────

_DATASET = os.environ.get("TIT_DATASET_000")
needs_dataset = pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)


def _mtimes(root: Path) -> dict:
    return {p: p.stat().st_mtime_ns for p in root.rglob("*")}


@needs_dataset
def test_dataset_000_fields_are_registry_names_and_vn_carriers_are_listed():
    root = Path(_DATASET)
    sims = root / "derivatives" / "SimNIBS"
    watched = [
        sims / "sub-ernie" / "Simulations" / "AF3_PO10_and_AF4_Oz",
        sims / "sub-101" / "Simulations" / "L_Insula",
    ]
    before = {w: _mtimes(w) for w in watched}
    pm = get_path_manager(str(root))

    # ernie ran with conductivity "vn" (documentation/config.json); its two carrier magnE
    # volumes are ernie_TDCS_{1,2}_vn_subject_magnE.nii.gz.
    ernie = catalog.simulation_detail(pm, "ernie", "AF3_PO10_and_AF4_Oz")
    on_disk = sorted(
        str(p)
        for p in (watched[0] / "high_Frequency" / "niftis").glob(
            "ernie_TDCS_*_vn_*magnE.nii.gz"
        )
    )
    assert len(on_disk) == 2
    assert (
        sorted(n["path"] for n in ernie["niftis"] if n["field"] == "magnE") == on_disk
    )
    assert ernie["fields"] == ["TI_max", "magnE"]

    # sub-101/L_Insula holds TI_max, hf_peak and hf_sar volumes plus scalar carriers.
    insula = catalog.simulation_detail(pm, "101", "L_Insula")
    assert set(insula["fields"]) == {"TI_max", "hf_peak", "hf_sar", "magnE"}
    assert insula["space"] == ["mni", "subject"]

    assert {w: _mtimes(w) for w in watched} == before
