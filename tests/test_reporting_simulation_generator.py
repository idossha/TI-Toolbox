#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/reporting/simulation_report_generator.py

Focus on:
- parameter/montage APIs
- default conductivities
- report generation writes HTML without requiring real SimNIBS outputs
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_simulation_report_basic_apis_and_generate(tmp_path: Path):
    from tit.reporting.simulation_report_generator import SimulationReportGenerator

    def fake_run(cmd, capture_output, text, timeout):
        s = " ".join(cmd)
        if "simnibs_python" in s:
            return SimpleNamespace(returncode=0, stdout="4.5.0\n")
        if cmd[:2] == ["python", "--version"]:
            return SimpleNamespace(returncode=0, stdout="Python 3.11.0\n")
        return SimpleNamespace(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=fake_run):
        gen = SimulationReportGenerator(str(tmp_path), simulation_session_id="sess123")

    # Defaults
    defaults = gen._get_default_conductivities()
    assert 1 in defaults and 2 in defaults
    assert defaults[1]["name"]

    # Parameter APIs
    gen.add_simulation_parameters(
        conductivity_type="scalar",
        simulation_mode="U",
        eeg_net="GSN-HydroCel-185",
        intensity_ch1=2.0,
        intensity_ch2=2.0,
        quiet_mode=True,
    )
    assert gen.report_data["simulation_parameters"]["simulation_mode_text"] == "Unipolar"
    assert gen.report_data["simulation_parameters"]["intensity_ch1_a"] == 0.002

    gen.add_electrode_parameters(shape="rect", dimensions=[10, 20], thickness=4.0)
    assert gen.report_data["electrode_parameters"]["area_mm2"] == 200

    with pytest.raises(ValueError):
        gen.add_montage(montage_name=None, name=None, electrode_pairs=[("A", "B")])

    gen.add_montage(montage_name="m1", electrode_pairs=[("A", "B"), ("C", "D")], montage_type="unipolar")
    assert gen.report_data["montages"][0]["num_pairs"] == 2

    # Generate minimal report
    out = tmp_path / "sim_report.html"
    with patch.object(gen, "_add_imagemagick_warning", return_value=None):
        out_path = gen.generate_report(str(out))
    assert out_path == str(out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<html" in text.lower()
    assert "TI-Toolbox Simulation Report" in text


