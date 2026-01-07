#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/cli/utils.py

Covers env parsing, CSV label loading, and project discovery helpers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_bool_env_parsing(monkeypatch):
    from tit.cli.utils import bool_env

    monkeypatch.delenv("X", raising=False)
    assert bool_env("X", default=True) is True

    monkeypatch.setenv("X", "1")
    assert bool_env("X") is True
    monkeypatch.setenv("X", "true")
    assert bool_env("X") is True
    monkeypatch.setenv("X", "yes")
    assert bool_env("X") is True
    monkeypatch.setenv("X", "off")
    assert bool_env("X") is False


@pytest.mark.unit
def test_env_required(monkeypatch):
    from tit.cli.utils import env_required

    monkeypatch.delenv("REQ", raising=False)
    with pytest.raises(RuntimeError):
        env_required("REQ")
    monkeypatch.setenv("REQ", "ok")
    assert env_required("REQ") == "ok"


@pytest.mark.unit
def test_load_eeg_cap_labels_prefers_label_columns(tmp_path: Path):
    from tit.cli.utils import load_eeg_cap_labels

    p = tmp_path / "cap.csv"
    # use lowercase header to match the parser's preferred candidates
    p.write_text("label,X,Y,Z\nFp1,0,0,0\nFp1,0,0,0\nFz,0,0,0\n")
    labels = load_eeg_cap_labels(p)
    assert labels == ["Fp1", "Fz"]


@pytest.mark.unit
def test_discover_simulations_and_fields(tmp_path: Path):
    from tit.cli.utils import discover_simulations, discover_fields

    proj = tmp_path
    base = proj / "derivatives" / "SimNIBS" / "sub-001" / "Simulations"
    sim1 = base / "simA" / "TI" / "mesh"
    sim1.mkdir(parents=True)
    (sim1 / "E.msh").write_text("m")

    sim2 = base / "simB" / "TI" / "niftis"
    sim2.mkdir(parents=True)
    (sim2 / "E.nii.gz").write_text("n")

    sims = discover_simulations(proj, "001")
    assert sims == ["simA", "simB"]

    mesh_fields = discover_fields(proj, "001", "simA", "mesh")
    assert len(mesh_fields) == 1
    assert mesh_fields[0].name.endswith(".msh")

    nifti_fields = discover_fields(proj, "001", "simB", "niftis")
    assert len(nifti_fields) == 1
    assert nifti_fields[0].name.endswith(".nii.gz")


