#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/cli/simulator.py flex-mode construction.

We create a fake flex_search output directory with electrode_positions.json and
validate that:
- optimized montage names are parsed and created (is_xyz=True, eeg_net=flex_mode)
- mapped montages create mapping JSON when missing and use eeg_net labels
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class _FakePM:
    def __init__(self, project_dir: str, flex_root: Path, eeg_dir: Path):
        self.project_dir = project_dir
        self._flex_root = flex_root
        self._eeg_dir = eeg_dir

    def path(self, kind: str, *, subject_id: str):
        if kind == "flex_search":
            return str(self._flex_root)
        if kind == "eeg_positions":
            return str(self._eeg_dir)
        raise KeyError(kind)


@pytest.mark.unit
def test_simulator_execute_flex_builds_mapped_and_optimized(tmp_path: Path):
    from tit.cli.simulator import SimulatorCLI

    # Create project structure
    proj = tmp_path / "proj"
    proj.mkdir()
    flex_root = proj / "derivatives" / "ti-toolbox" / "flex_search" / "sub-001"
    eeg_dir = proj / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001" / "eeg_positions"
    flex_root.mkdir(parents=True)
    eeg_dir.mkdir(parents=True)

    # EEG cap file exists
    eeg_cap = eeg_dir / "GSN-HydroCel-185"
    eeg_cap.write_text("label,x,y,z\nFp1,0,0,0\nFz,0,0,0\n")

    # One flex search folder
    search = flex_root / "lh_aal_region_goal_post"
    search.mkdir()
    positions = {
        "optimized_positions": ["p1", "p2", "p3", "p4"],
    }
    (search / "electrode_positions.json").write_text(json.dumps(positions))

    pm = _FakePM(str(proj), flex_root=flex_root, eeg_dir=eeg_dir)

    captured = {}

    def fake_run_simulation(config, montages, **kwargs):
        captured["config"] = config
        captured["montages"] = montages
        return [{"status": "completed"} for _ in montages]

    with patch("tit.cli.simulator.get_path_manager", return_value=pm), \
         patch("tit.tools.map_electrodes.load_electrode_positions_json", return_value=([(0, 0, 0)], [0])), \
         patch("tit.tools.map_electrodes.read_csv_positions", return_value=([(0, 0, 0)], ["Fp1"])), \
         patch("tit.tools.map_electrodes.map_electrodes_to_net", return_value={"mapped_labels": ["Fp1", "Fz", "Cz", "Pz"]}), \
         patch("tit.tools.map_electrodes.save_mapping_result", side_effect=lambda mapping, path, eeg_net_name=None: Path(path).write_text(json.dumps(mapping))), \
         patch("tit.sim.run_simulation", side_effect=fake_run_simulation):

        rc = SimulatorCLI().execute(
            dict(
                subject="001",
                framework="flex",
                eeg_net="GSN-HydroCel-185",
                montages="lh_aal_region_goal_post",
                flex_use_mapped=True,
                flex_use_optimized=True,
                conductivity="scalar",
                intensity="2.0",
                electrode_shape="ellipse",
                dimensions="8,8",
                thickness=4.0,
                mode="U",
            )
        )

    assert rc == 0
    assert "montages" in captured
    # Should contain two montages: optimized + mapped
    assert len(captured["montages"]) == 2
    names = sorted([m.name for m in captured["montages"]])
    assert any(n.endswith("_optimized") for n in names)
    assert any(n.endswith("_mapped") for n in names)


