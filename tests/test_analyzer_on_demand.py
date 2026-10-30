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
    * missing channel meshes fail the analysis with ``FieldUnavailableError`` naming them, and
      the analyzer's log file handler is not left behind;
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


def _construct(space, tissue="GM", field=None, **ensure):
    """``Analyzer.__init__`` with the producer replaced and the field file resolved."""
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

    with (
        patch("tit.volume_fields.ensure_mesh_fields", produce("mesh")),
        patch("tit.volume_fields.ensure_niftis", produce("voxel")),
        patch(
            "tit.analyzer.analyzer.select_field_file",
            return_value=(Path("/sim/TI/x"), field or "TI_max"),
        ),
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
    assert calls == [("mesh", SID, SIM, ["TI_max", *CARRIERS], "-")]
    assert analyzer._on_demand == (notice,)
    said = [r.getMessage() for r in caplog.records]
    assert said.index(notice) < next(
        i for i, m in enumerate(said) if m.startswith("Analyzer initialised")
    )


@pytest.mark.parametrize(
    "tissue, expected", [("GM", "grey"), ("WM", "white"), ("both", None)]
)
def test_a_voxel_analysis_produces_its_tissue_niftis(init_pm, tissue, expected) -> None:
    _, calls = _construct("voxel", tissue=tissue, field="TI_avg")
    assert calls == [("voxel", SID, SIM, ["TI_avg", *CARRIERS], expected)]


def test_everything_saved_produces_nothing_and_notes_nothing(init_pm) -> None:
    analyzer, _ = _construct("mesh")
    assert analyzer._on_demand == ()


def _run_record(sim_dir: Path) -> None:
    (sim_dir / "documentation").mkdir(parents=True)
    (sim_dir / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "subject_id": SID,
                "conductivity": "scalar",
                "electrode_pairs": [["a", "b"], ["c", "d"]],
            }
        )
    )
    mesh = sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh"
    mesh.parent.mkdir(parents=True)
    mesh.write_text(
        "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n1\n1 0 0 0\n$EndNodes\n"
        '$Elements\n0\n$EndElements\n$ElementData\n1\n"TI_max"\n1\n0.0\n3\n0\n1\n0\n'
        "$EndElementData\n"
    )


@pytest.mark.parametrize("space", ["mesh", "voxel"])
def test_missing_channel_meshes_fail_the_analysis_naming_them(init_pm, space) -> None:
    sim_dir = Path(init_pm.simulation(SID, SIM))
    _run_record(sim_dir)
    handlers = list(logging.getLogger("tit").handlers)
    with pytest.raises(FieldUnavailableError) as failed:
        Analyzer(SID, SIM, space=space)
    message = str(failed.value)
    assert message.startswith(
        "hf_peak and hf_sar were not saved for M1, and the channel meshes they are "
        "computed from are missing: "
    )
    assert (
        str(sim_dir / "high_Frequency" / "mesh" / f"{SID}_TDCS_1_scalar.msh") in message
    )
    assert logging.getLogger("tit").handlers == handlers  # its log file is closed again


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
