#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/opt/flex/multi_start.py

Covers:
- select_best_solution edge cases
- copy_best_solution filesystem behavior
- cleanup_temporary_directories retry path
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.mark.unit
def test_select_best_solution_all_failed():
    from tit.opt.flex.multi_start import select_best_solution

    logger = MagicMock()
    vals = np.array([float("inf"), float("inf")])
    best, valid, failed = select_best_solution(vals, n_multistart=2, logger=logger)
    assert best == -1
    assert valid == []
    assert failed == [1, 2]


@pytest.mark.unit
def test_select_best_solution_picks_min_and_reports_runs():
    from tit.opt.flex.multi_start import select_best_solution

    logger = MagicMock()
    vals = np.array([1.5, float("inf"), 0.5, 2.0])
    best, valid, failed = select_best_solution(vals, n_multistart=4, logger=logger)
    assert best == 2  # index of 0.5
    assert (3, 0.5) in valid
    assert failed == [2]


@pytest.mark.unit
def test_copy_best_solution_copies_files_and_dirs(tmp_path: Path):
    from tit.opt.flex.multi_start import copy_best_solution

    logger = MagicMock()
    best = tmp_path / "best"
    out = tmp_path / "out"
    best.mkdir()
    out.mkdir()
    # file + dir
    (best / "a.txt").write_text("a")
    (best / "d").mkdir()
    (best / "d" / "b.txt").write_text("b")

    ok = copy_best_solution(str(best), str(out), logger=logger)
    assert ok is True
    assert (out / "a.txt").read_text() == "a"
    assert (out / "d" / "b.txt").read_text() == "b"


@pytest.mark.unit
def test_cleanup_temporary_directories_retries(tmp_path: Path):
    from tit.opt.flex.multi_start import cleanup_temporary_directories

    logger = MagicMock()
    d1 = tmp_path / "1"
    d2 = tmp_path / "2"
    d1.mkdir()
    d2.mkdir()

    calls = {"n": 0}

    import shutil as _shutil
    _real_rmtree = _shutil.rmtree

    def flaky_rmtree(path):
        calls["n"] += 1
        # first attempt for first dir fails, then succeeds
        if calls["n"] == 1:
            raise OSError("busy")
        return _real_rmtree(path)

    with patch("shutil.rmtree", side_effect=flaky_rmtree):
        ok = cleanup_temporary_directories([str(d1), str(d2)], n_multistart=2, logger=logger)
    assert ok is True
    assert not d1.exists()
    assert not d2.exists()


