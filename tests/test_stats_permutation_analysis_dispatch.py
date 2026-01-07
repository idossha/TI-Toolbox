#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/stats/permutation_analysis.py

We cover:
- CSV config parsing (group_comparison + correlation) including edge cases
- run_analysis dispatch (group vs correlation) with heavy work mocked
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.mark.unit
def test_prepare_config_from_csv_group_comparison(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    csv_path = tmp_path / "cfg.csv"
    df = pd.DataFrame(
        [
            {"subject_id": "sub-001", "simulation_name": "simA", "response": 1},
            {"subject_id": "002", "simulation_name": "simB", "response": 0},
        ]
    )
    df.to_csv(csv_path, index=False)

    cfgs = pa.prepare_config_from_csv(str(csv_path), analysis_type="group_comparison")
    assert cfgs[0]["subject_id"] == "001"
    assert cfgs[1]["subject_id"] == "002"
    assert cfgs[0]["response"] in (0, 1)


@pytest.mark.unit
def test_prepare_config_from_csv_correlation_handles_missing_and_weights(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    csv_path = tmp_path / "cfg.csv"
    df = pd.DataFrame(
        [
            {"subject_id": 101.0, "simulation_name": "simA", "effect_size": 0.5, "weight": 2.0},
            {"subject_id": "sub-102", "simulation_name": "simB", "effect_size": 1.5, "weight": 1.0},
            {"subject_id": None, "simulation_name": "simC", "effect_size": 1.0},  # skipped
        ]
    )
    df.to_csv(csv_path, index=False)

    cfgs = pa.prepare_config_from_csv(str(csv_path), analysis_type="correlation")
    assert len(cfgs) == 2
    assert cfgs[0]["subject_id"] == "101"  # float -> int -> str
    assert cfgs[0]["weight"] == 2.0
    assert cfgs[1]["subject_id"] == "102"


@pytest.mark.unit
def test_prepare_config_from_csv_errors_on_missing_required_cols(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    csv_path = tmp_path / "cfg.csv"
    pd.DataFrame([{"subject_id": "001"}]).to_csv(csv_path, index=False)

    with pytest.raises(ValueError):
        pa.prepare_config_from_csv(str(csv_path), analysis_type="group_comparison")
    with pytest.raises(ValueError):
        pa.prepare_config_from_csv(str(csv_path), analysis_type="correlation")


@pytest.mark.unit
def test_run_analysis_dispatches_to_correct_worker(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    # Mock logger setup so run_analysis can proceed without logging_util
    fake_logger = MagicMock()
    with patch.object(pa, "setup_logging", return_value=(fake_logger, str(tmp_path / "log.txt"))), \
         patch.object(pa, "get_path_manager", return_value=None), \
         patch.object(pa, "_run_group_comparison_analysis", return_value={"ok": "group"}) as run_group, \
         patch.object(pa, "_run_correlation_analysis", return_value={"ok": "corr"}) as run_corr:

        out1 = pa.run_analysis([], "name1", config={"analysis_type": "group_comparison"})
        assert out1["ok"] == "group"
        run_group.assert_called_once()

        out2 = pa.run_analysis([], "name2", config={"analysis_type": "correlation"})
        assert out2["ok"] == "corr"
        run_corr.assert_called_once()



