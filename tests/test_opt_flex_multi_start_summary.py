#!/usr/bin/env simnibs_python
"""
More coverage for tit/opt/flex/multi_start.py

Covers:
- run_single_optimization success + IndexError handling
- create_multistart_summary_file / create_single_optimization_summary_file write
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.mark.unit
def test_run_single_optimization_success_and_indexerror():
    from tit.opt.flex.multi_start import run_single_optimization

    logger = MagicMock()

    opt = MagicMock()
    opt.optim_funvalue = 1.23
    out = run_single_optimization(opt, cpus=2, logger=logger)
    opt.run.assert_called_once_with(cpus=2)
    assert out == 1.23

    opt2 = MagicMock()
    opt2.run.side_effect = IndexError("postproc")
    opt2.optim_funvalue = 9.99
    out2 = run_single_optimization(opt2, cpus=None, logger=logger)
    assert out2 == float("inf")


@pytest.mark.unit
def test_summary_file_writers(tmp_path: Path):
    from tit.opt.flex.multi_start import (
        create_multistart_summary_file,
        create_single_optimization_summary_file,
    )

    args = SimpleNamespace(
        subject="001",
        goal="target",
        postproc="maxTI",
        roi_method="spherical",
        eeg_net="GSN-HydroCel-185",
        electrode_shape="ellipse",
        dimensions="8,8",
        thickness=4.0,
        current=2.0,
        run_final_electrode_simulation=True,
        skip_final_electrode_simulation=False,
        non_roi_method="everything_else",
        thresholds="0.2,0.5",
        enable_mapping=False,
        disable_mapping_simulation=False,
        max_iterations=None,
        population_size=None,
        cpus=None,
    )

    start = time.time() - 1.0
    vals = np.array([1.0, float("inf"), 0.5])
    best_idx = 2
    valid_runs = [(1, 1.0), (3, 0.5)]
    failed_runs = [2]

    ms = tmp_path / "multi.txt"
    create_multistart_summary_file(
        summary_file=str(ms),
        args=args,
        n_multistart=3,
        optim_funvalue_list=vals,
        best_opt_idx=best_idx,
        valid_runs=valid_runs,
        failed_runs=failed_runs,
        start_time=start,
    )
    assert ms.exists()
    assert "MULTI-START OPTIMIZATION SUMMARY" in ms.read_text()

    ss = tmp_path / "single.txt"
    create_single_optimization_summary_file(
        str(ss), args=args, function_value=0.5, start_time=start
    )
    assert ss.exists()
    assert "OPTIMIZATION SUMMARY" in ss.read_text()
