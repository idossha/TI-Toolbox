"""An analysis produces what the simulation did not save, says so, then analyses it (2026-10-30).

What this pins
    * ``Analyzer.volume_fields_read``: an analysis of a modulation field reads the field and the
      ``hf_peak`` / ``hf_sar`` its carrier metrics need; a carrier field reads itself; TI_normal
      (a surface field) reads only the carriers; a request ``select_field_file`` refuses reads
      nothing;
    * ``Analyzer(...)`` asks ``tit.volume_fields`` for exactly those, in its space -- the field
      mesh for a mesh analysis, the tissue's subject-space NIfTIs for a voxel one -- says each
      production on its own logger before reading anything, and the result's
      ``on_demand_note`` (``results.csv``) carries the same sentences, beside carrier metrics
      computed from the produced fields;
    * an analysed field that cannot be produced fails the analysis with
      ``FieldUnavailableError`` naming what is missing (and the log handler is not left
      behind); carriers that cannot be produced only leave their reason for ``carrier_note``;
    * in voxel space the selector is asked first: a NIfTI it finds is analysed as it is, a
      NIfTI-only archive included; Auto on a carrier-only run is ``hf_peak``;
    * the group tools' NIfTI loader produces a missing simulator NIfTI before it reads.

Where the expected values come from: the call arguments are the design (the docstrings name
them); the carrier numbers are the hand ratios of ``tests/test_analyzer_carrier_focality.py``'s
authored surface. The production itself is ``tests/test_sim_fields_on_demand.py`` (host) and
``tests/numerical/test_sim_fields_on_demand_real.py`` (real SimNIBS).

Reproduce: ``.venv/bin/python -m pytest tests/test_analyzer_on_demand.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit.analyzer.analyzer import Analyzer
from tit.volume_fields import FieldUnavailableError

SID, SIM = "001", "M1"
CARRIERS = ["hf_peak", "hf_sar"]


@pytest.mark.parametrize(
    "space, field, read",
    [
        ("mesh", None, ["TI_max", *CARRIERS]),
        ("voxel", "mTI_max", ["mTI_max", *CARRIERS]),
        ("mesh", "TI_avg", ["TI_avg", *CARRIERS]),
        ("mesh", "TI_normal", CARRIERS),
        ("voxel", "TI_normal", []),  # select_field_file refuses: mesh only
        ("voxel", "hf_peak", ["hf_peak"]),
        ("mesh", "hf_power_density", ["hf_power_density"]),
        ("mesh", "magnE", []),  # not an analyzer field
        ("surface", "TI_max", []),
    ],
)
def test_what_an_analysis_reads(space, field, read) -> None:
    assert Analyzer.volume_fields_read(space, field) == read


def _construct(space, tissue="GM", field=None, found=True, **ensure):
    """``Analyzer.__init__`` with the producer replaced and the field file resolved.

    *found*: whether the voxel selector finds the analysed NIfTI before anything is produced.
    """
    calls = []

    def produce(name):
        def fake(sid, sim, fields, **kwargs):
            calls.append((name, sid, sim, list(fields), kwargs.get("tissue", "-")))
            for notice in ensure.get(name, []):
                kwargs["say"](notice)
            return (
                ensure.get(name, []) if name == "mesh" else ({}, ensure.get(name, []))
            )

        return fake

    answers = [(Path("/sim/TI/niftis/grey_M1_TI_subject_x.nii.gz"), field or "TI_max")]
    if not found:
        answers.insert(0, FileNotFoundError("no NIfTI yet"))
    with (
        patch("tit.volume_fields.ensure_mesh_fields", produce("mesh")),
        patch("tit.volume_fields.ensure_niftis", produce("voxel")),
        patch("tit.analyzer.analyzer.select_field_file", side_effect=answers * 2),
        patch("tit.analyzer.analyzer.add_file_handler"),
    ):
        analyzer = Analyzer(SID, SIM, space=space, tissue_type=tissue, field=field)
    return analyzer, calls


def test_a_mesh_analysis_produces_into_the_field_mesh_and_says_so_first(
    init_pm, caplog
) -> None:
    notice = "hf_peak and hf_sar were not saved for M1; computing them from the channel fields and saving them to M1_TI.msh."
    with caplog.at_level(logging.INFO, logger="tit.analyzer.analyzer"):
        analyzer, calls = _construct("mesh", mesh=[notice])
    # The analysed field first (it must be there), then the carriers its metrics read.
    assert calls == [
        ("mesh", SID, SIM, ["TI_max"], "-"),
        ("mesh", SID, SIM, CARRIERS, "-"),
    ]
    assert analyzer._on_demand == (notice, notice)
    said = [r.getMessage() for r in caplog.records]
    assert said.index(notice) < next(
        i for i, m in enumerate(said) if m.startswith("Analyzer initialised")
    )


@pytest.mark.parametrize(
    "tissue, expected", [("GM", "grey"), ("WM", "white"), ("both", None)]
)
def test_a_voxel_analysis_produces_its_tissue_niftis(init_pm, tissue, expected) -> None:
    _, calls = _construct("voxel", tissue=tissue, field="TI_avg", found=False)
    assert calls == [
        ("voxel", SID, SIM, ["TI_avg"], expected),
        ("voxel", SID, SIM, CARRIERS, expected),
    ]


def test_a_nifti_the_selector_finds_is_analysed_as_it_is(init_pm) -> None:
    # Found (an older or renamed file too): nothing produced for it; its carriers are asked for.
    _, calls = _construct("voxel", field="TI_avg", found=True)
    assert calls == [("voxel", SID, SIM, CARRIERS, "grey")]


def test_everything_saved_produces_nothing_and_notes_nothing(init_pm) -> None:
    analyzer, _ = _construct("mesh")
    assert analyzer._on_demand == ()


def _run_record(sim_dir: Path, *, fields=("TI_max",), carrier_only=False) -> None:
    from tests.field_mesh import write_field_mesh

    (sim_dir / "documentation").mkdir(parents=True)
    (sim_dir / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "subject_id": SID,
                "conductivity": "scalar",
                "electrode_pairs": [["a", "b"], ["c", "d"]],
                "carrier_only": carrier_only,
            }
        )
    )
    write_field_mesh(sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh", fields)


@pytest.mark.parametrize("space", ["mesh", "voxel"])
def test_an_analysed_field_that_cannot_be_produced_fails_naming_what_is_missing(
    init_pm, space
) -> None:
    sim_dir = Path(init_pm.simulation(SID, SIM))
    _run_record(sim_dir, fields=())  # nothing saved, and no channel meshes
    handlers = list(logging.getLogger("tit").handlers)
    with pytest.raises(FieldUnavailableError) as failed:
        Analyzer(SID, SIM, space=space)
    message = str(failed.value)
    assert (
        "TI_max was not saved for M1, and the channel meshes it is computed" in message
    )
    assert (
        str(sim_dir / "high_Frequency" / "mesh" / f"{SID}_TDCS_1_scalar.msh") in message
    )
    assert logging.getLogger("tit").handlers == handlers  # its log file is closed again


def test_carriers_that_cannot_be_produced_leave_the_reason_not_a_failure(
    init_pm,
) -> None:
    sim_dir = Path(init_pm.simulation(SID, SIM))
    _run_record(sim_dir)  # TI_max saved; no channel meshes for the carriers
    with patch("tit.analyzer.analyzer.add_file_handler"):
        analyzer = Analyzer(SID, SIM, space="mesh")
    assert set(analyzer._carrier_reasons) == set(CARRIERS)
    assert "channel meshes they are computed from are missing" in (
        analyzer._carrier_reasons["hf_peak"]
    )


def test_a_nifti_only_archive_is_analysed_with_the_carrier_reason(init_pm) -> None:
    # The field mesh is gone; the analysed NIfTI is there. The carriers cannot be produced.
    niftis = Path(init_pm.simulation(SID, SIM)) / "TI" / "niftis"
    niftis.mkdir(parents=True)
    (niftis / f"grey_{SIM}_TI_subject_TI_max.nii.gz").write_bytes(b"nii")
    with patch("tit.analyzer.analyzer.add_file_handler"):
        analyzer = Analyzer(SID, SIM, space="voxel")
    assert analyzer.field_path == niftis / f"grey_{SIM}_TI_subject_TI_max.nii.gz"
    assert "has no field mesh" in analyzer._carrier_reasons["hf_sar"]


def test_auto_on_a_carrier_only_run_is_hf_peak(init_pm) -> None:
    from tit.analyzer.field_selector import default_field

    sim_dir = Path(init_pm.simulation(SID, SIM))
    _run_record(sim_dir, fields=("hf_peak", "hf_sar"), carrier_only=True)
    assert default_field(SID, SIM) == "hf_peak"
    with patch("tit.analyzer.analyzer.add_file_handler"):
        analyzer = Analyzer(SID, SIM, space="mesh")  # Auto: no field
    assert analyzer.field_name == "hf_peak" and analyzer._on_demand == ()


def test_the_note_and_the_carrier_metrics_reach_results_csv(tmp_path: Path) -> None:
    # The surface as the producer leaves it: hf_peak / hf_sar mapped onto it by msh2cortex.
    x = np.arange(10.0)
    roi = x <= 3.5
    ti = np.where(roi, 2.0, 1.0)
    hf = np.where(roi, 3.0, 1.0)
    analyzer = object.__new__(Analyzer)
    analyzer.space, analyzer.field_name, analyzer.tissue_type = "mesh", "TI_max", "GM"
    analyzer.field_path = tmp_path / "M1_TI.msh"
    analyzer.output_dir = str(tmp_path / "out")
    analyzer._pm = SimpleNamespace(ensure=lambda p: Path(p).mkdir(parents=True) or p)
    analyzer._is_mti = False
    analyzer._surface_mesh = SimpleNamespace(
        nodes=SimpleNamespace(node_coord=np.c_[x, np.zeros(10), np.zeros(10)]),
        field={
            "TI_max": SimpleNamespace(value=ti),
            "hf_peak": SimpleNamespace(value=hf),
            "hf_sar": SimpleNamespace(value=2.0 * hf**2),
        },
        nodes_areas=lambda: np.ones(10),
    )
    analyzer._surface_mesh_path = tmp_path / "M1_TI_central.msh"
    analyzer._get_normal_stats = lambda *a: None
    analyzer._on_demand = ("hf_peak and hf_sar were not saved for M1; computing them.",)

    r = analyzer.analyze_sphere((1.5, 0.0, 0.0), 2.0)

    # Unit areas: ROI nodes 0..3 at 3 V/m, the other six at 1 -> GM mean 18/10.
    assert r.hf_focality == pytest.approx(3.0 / 1.8)
    assert r.carrier_note is None
    assert r.on_demand_note == analyzer._on_demand[0]
    with open(tmp_path / "out" / "results.csv", newline="") as fh:
        row = {line["Metric"]: line["Value"] for line in csv.DictReader(fh)}
    assert row["on_demand_note"] == analyzer._on_demand[0]


def test_a_saved_analysis_writes_no_note(tmp_path: Path) -> None:
    analyzer = object.__new__(Analyzer)  # never produced anything: the class default
    assert analyzer._on_demand == ()


def test_the_group_loader_produces_a_missing_nifti_before_it_reads(init_pm) -> None:
    from tit.stats.nifti import load_subject_nifti_ti_toolbox

    produced = []

    def ensure(sid, sim, path, say):
        produced.append(Path(path).name)
        say(f"{Path(path).name} written")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"nii")
        return [f"{Path(path).name} written"]

    img = SimpleNamespace(get_fdata=lambda dtype=None: np.zeros((2, 2, 2)))
    with (
        patch("tit.volume_fields.ensure_nifti_file", ensure),
        patch("tit.stats.nifti.nib.load", return_value=img),
    ):
        data, _, path = load_subject_nifti_ti_toolbox(SID, SIM)
    assert produced == [f"grey_{SIM}_TI_MNI_MNI_TI_max.nii.gz"]
    assert data.shape == (2, 2, 2) and Path(path).name == produced[0]


def test_the_group_loader_fails_naming_what_cannot_produce_the_nifti(init_pm) -> None:
    from tit.stats.nifti import load_subject_nifti_ti_toolbox

    _run_record(Path(init_pm.simulation(SID, SIM)))
    with pytest.raises(FieldUnavailableError, match="TDCS_1_scalar.msh"):
        load_subject_nifti_ti_toolbox(
            SID, SIM, "grey_{simulation_name}_TI_MNI_MNI_hf_sar.nii.gz"
        )
