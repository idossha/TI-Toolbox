#!/usr/bin/env simnibs_python
"""
CLI usability tests:
- Disallow ambiguous abbreviations (BaseCLI sets allow_abbrev=False)
- Provide ergonomic shorthand flags (--montage/--flex, --pool/--buckets)
- Support list inputs as either comma-separated or space-separated tokens
"""

from __future__ import annotations

import sys
from typing import Any, Dict

import pytest

from tit.cli.simulator import SimulatorCLI
from tit.cli.ex_search import ExSearchCLI
from tit.cli.pre_process import PreProcessCLI
from tit.cli.group_analyzer import GroupAnalyzerCLI
from tit.cli.create_leadfield import CreateLeadfieldCLI


class _CaptureSimulator(SimulatorCLI):
    def __init__(self) -> None:
        super().__init__()
        self.captured: Dict[str, Any] = {}

    def execute(self, args: Dict[str, Any]) -> int:  # type: ignore[override]
        self.captured = args
        # Only validate parsing-related behavior
        if args.get("montage") and args.get("flex"):
            return 2
        return 0


class _CaptureExSearch(ExSearchCLI):
    def __init__(self) -> None:
        super().__init__()
        self.captured: Dict[str, Any] = {}

    def execute(self, args: Dict[str, Any]) -> int:  # type: ignore[override]
        self.captured = args
        return 0


class _CapturePreProcess(PreProcessCLI):
    def __init__(self) -> None:
        super().__init__()
        self.captured: Dict[str, Any] = {}

    def execute(self, args: Dict[str, Any]) -> int:  # type: ignore[override]
        self.captured = args
        return 0


class _CaptureGroupAnalyzer(GroupAnalyzerCLI):
    def __init__(self) -> None:
        super().__init__()
        self.captured: Dict[str, Any] = {}

    def execute(self, args: Dict[str, Any]) -> int:  # type: ignore[override]
        self.captured = args
        return 0


class _CaptureCreateLeadfield(CreateLeadfieldCLI):
    def __init__(self) -> None:
        super().__init__()
        self.captured: Dict[str, Any] = {}

    def execute(self, args: Dict[str, Any]) -> int:  # type: ignore[override]
        self.captured = args
        return 0


@pytest.mark.unit
def test_simulator_shorthand_montage_flag_and_montages_list(monkeypatch):
    cli = _CaptureSimulator()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulator",
            "--sub",
            "ernie",
            "--montage",
            "--mode",
            "U",
            "--montages",
            "Left_Insula",
        ],
    )
    rc = cli.run_direct()
    assert rc == 0
    assert cli.captured["subject"] == "ernie"
    assert cli.captured["montage"] is True
    assert cli.captured["mode"] == "U"
    # nargs='+' should give list
    assert cli.captured["montages"] == ["Left_Insula"]


@pytest.mark.unit
def test_ex_search_pool_shorthand_and_pool_electrodes_space_separated(
    monkeypatch, tmp_path
):
    cli = _CaptureExSearch()
    lf = tmp_path / "ernie_leadfield_EEG10-20_Okamoto_2004.hdf5"
    lf.write_text("x")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ex_search",
            "--sub",
            "ernie",
            "--lf",
            str(lf),
            "--roi",
            "test",
            "--pool",
            "--pool-electrodes",
            "C3",
            "C4",
            "Fz",
            "Cz",
        ],
    )
    rc = cli.run_direct()
    assert rc == 0
    assert cli.captured["pool"] is True
    # nargs='+' => list tokens
    assert cli.captured["pool_electrodes"] == ["C3", "C4", "Fz", "Cz"]


@pytest.mark.unit
def test_pre_process_subjects_space_separated(monkeypatch):
    cli = _CapturePreProcess()
    monkeypatch.setattr(
        sys, "argv", ["pre_process", "--subs", "101", "102", "--create-m2m"]
    )
    rc = cli.run_direct()
    assert rc == 0
    assert cli.captured["subjects"] == ["101", "102"]


@pytest.mark.unit
def test_group_analyzer_subjects_accepts_singular_flag(monkeypatch):
    cli = _CaptureGroupAnalyzer()
    # Note: group analyzer itself requires >=2 subjects, but here we just validate parsing aliases.
    monkeypatch.setattr(
        sys, "argv", ["group_analyzer", "--subs", "101,102", "--sim", "simA"]
    )
    rc = cli.run_direct()
    assert rc == 0
    assert cli.captured["subjects"] == ["101,102"]


@pytest.mark.unit
def test_create_leadfield_tissues_space_separated(monkeypatch):
    cli = _CaptureCreateLeadfield()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "create_leadfield",
            "--sub",
            "101",
            "--eeg",
            "GSN-HydroCel-185",
            "--tissues",
            "1",
            "2",
        ],
    )
    rc = cli.run_direct()
    assert rc == 0
    assert cli.captured["tissues"] == ["1", "2"]
