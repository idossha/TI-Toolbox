"""A flex search's own EEG-net mapping is found by the Simulator and plans (2026-10-21).

What this pins: a flex search run with **Map to EEG net** (``enable_mapping``) gets its mapping
from SimNIBS (``resources/map-electrodes/tes_flex_optimization.py``), which writes
``<run>/electrode_mapping.json``; every reader (``tit.catalog._flex_mappings`` -> the Simulator's
flex rows and Results, ``tit.sim.montage_sources.resolve_flex_montage`` -> plans and agent steps)
looked only for ``electrode_mapping_<net>.json``, so the run showed as never mapped.
``run_flex_search`` now renames the file to that one name, and runs made before keep working
because the readers also take the old name, named by its ``eeg_net`` field.

Where the values come from: the mapping files are authored here in the shape the SimNIBS patch
writes (``mapped_labels``, ``channel_array_indices``, ``eeg_net``); groundTruth: authored.
The Hungarian mapping itself is tested in its own module and must not run here.

Reproduce: .venv/bin/python -m pytest tests/test_flex_mapping_filename.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if isinstance(sys.modules.get("numpy"), MagicMock):  # see tests/test_opt_flex.py
    del sys.modules["numpy"]

from tit import catalog
from tit.opt.config import FlexConfig
from tit.paths import PathManager
from tit.sim import montage_sources

NET = "GSN-HydroCel-185.csv"
SIMNIBS_MAPPING = {
    "mapped_labels": ["E10", "E20", "E30", "E40"],
    "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
    "eeg_net": NET,
}
PAIRS = [["E10", "E20"], ["E30", "E40"]]


@patch("tit.opt.flex.manifest.write_manifest")
@patch("tit.opt.flex.flex.create_valid_skin_region_visualization")
@patch("tit.opt.flex.flex.builder")
@patch("tit.opt.flex.flex.get_path_manager")
def test_a_mapped_search_leaves_its_mapping_under_the_net_name(
    mock_gpm, mock_builder, _viz, _manifest, tmp_path
):
    pm = MagicMock()
    pm.logs.return_value = str(tmp_path / "logs")
    pm.m2m.return_value = str(tmp_path / "m2m")
    pm.eeg_positions.return_value = str(tmp_path / "m2m" / "eeg_positions")
    (tmp_path / "m2m" / "eeg_positions").mkdir(parents=True)
    (tmp_path / "m2m" / "001.msh").touch()
    (tmp_path / "m2m" / "eeg_positions" / NET).touch()
    mock_gpm.return_value = pm

    opt = MagicMock(_accepted_candidate_valid=True, _accepted_candidate_id="fixture")
    opt.optim_funvalue = -0.02

    def simnibs_run(**_):
        Path(opt.output_folder, "electrode_mapping.json").write_text(
            json.dumps(SIMNIBS_MAPPING)
        )

    opt.run.side_effect = simnibs_run
    mock_builder.build_optimization.return_value = opt

    from tit.opt.flex.flex import run_flex_search

    run_dir = tmp_path / "run"
    config = FlexConfig(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=-42, y=-20, z=55, radius=10),
        n_multistart=1,
        enable_mapping=True,
        eeg_net="GSN-HydroCel-185",
        output_folder=str(run_dir),
    )
    assert run_flex_search(config).success is True

    assert not (run_dir / "electrode_mapping.json").exists()
    assert (run_dir / "electrode_mapping_GSN-HydroCel-185.json").is_file()
    assert catalog._flex_mappings(str(run_dir)) == [{"eeg_net": NET, "pairs": PAIRS}]


def test_a_run_from_before_the_rename_is_read_by_its_eeg_net(tmp_path):
    (tmp_path / "electrode_mapping.json").write_text(json.dumps(SIMNIBS_MAPPING))
    assert catalog._flex_mappings(str(tmp_path)) == [{"eeg_net": NET, "pairs": PAIRS}]


def test_a_nets_own_file_wins_over_the_old_name(tmp_path):
    (tmp_path / "electrode_mapping.json").write_text(json.dumps(SIMNIBS_MAPPING))
    own = {**SIMNIBS_MAPPING, "mapped_labels": ["E1", "E2", "E3", "E4"]}
    (tmp_path / "electrode_mapping_GSN-HydroCel-185.json").write_text(json.dumps(own))
    assert catalog._flex_mappings(str(tmp_path)) == [
        {"eeg_net": NET, "pairs": [["E1", "E2"], ["E3", "E4"]]}
    ]


def test_an_old_name_without_its_net_is_ignored(tmp_path):
    unnamed = {k: v for k, v in SIMNIBS_MAPPING.items() if k != "eeg_net"}
    (tmp_path / "electrode_mapping.json").write_text(json.dumps(unnamed))
    assert catalog._flex_mappings(str(tmp_path)) == []


def test_a_plan_uses_the_old_name_without_remapping(tmp_path, monkeypatch):
    pm = PathManager(project_dir=str(tmp_path))
    run_dir = Path(pm.flex_search_run("101", "run1"))
    run_dir.mkdir(parents=True)
    (run_dir / "electrode_mapping.json").write_text(json.dumps(SIMNIBS_MAPPING))

    def must_not_remap(*_args, **_kwargs):
        raise AssertionError("the run's own mapping was ignored and re-computed")

    monkeypatch.setattr(
        "tit.tools.map_electrodes.map_electrodes_to_net", must_not_remap
    )
    montage = montage_sources.resolve_flex_montage(
        pm, "101", "run1", "mapped", eeg_net=NET
    )
    assert [list(p) for p in montage.electrode_pairs] == PAIRS
    assert montage.eeg_net == NET


@pytest.mark.parametrize("other_net", ["EGI_template.csv"])
def test_the_old_name_for_another_net_is_not_used(tmp_path, monkeypatch, other_net):
    """A mapping onto one net must never stand in for another: the plan re-maps instead."""
    pm = PathManager(project_dir=str(tmp_path))
    run_dir = Path(pm.flex_search_run("101", "run1"))
    run_dir.mkdir(parents=True)
    (run_dir / "electrode_mapping.json").write_text(json.dumps(SIMNIBS_MAPPING))
    with pytest.raises(ValueError, match="electrode_positions.json not found"):
        montage_sources.resolve_flex_montage(
            pm, "101", "run1", "mapped", eeg_net=other_net
        )
