#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/reporting/preprocessing_report_generator.py

Focus on:
- version collection (mocked subprocess)
- input/output scanning (real temp filesystem)
- HTML generation writes a report
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_preprocessing_report_scans_project_and_generates_html(tmp_path: Path):
    from tit.reporting.preprocessing_report_generator import (
        PreprocessingReportGenerator,
    )

    # Fake subprocess outputs (freesurfer/simnibs_python/dcm2niix)
    def fake_run(cmd, capture_output, text, timeout):
        s = " ".join(cmd)
        if "freesurfer --version" in s:
            return SimpleNamespace(returncode=0, stdout="FreeSurfer v7.4.1\n")
        if "simnibs_python" in s:
            return SimpleNamespace(returncode=0, stdout="4.5.0\n")
        if "dcm2niix -h" in s:
            return SimpleNamespace(returncode=0, stdout="dcm2niix version v1.0\n")
        return SimpleNamespace(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=fake_run):
        gen = PreprocessingReportGenerator(str(tmp_path), "001")

    # Minimal project structure for scan_for_data
    # Inputs
    t1w = tmp_path / "sourcedata" / "sub-001" / "T1w"
    t2w = tmp_path / "sourcedata" / "sub-001" / "T2w"
    t1w.mkdir(parents=True)
    t2w.mkdir(parents=True)
    (t1w / "t1.dcm").write_text("x")
    (t2w / "t2.dcm").write_text("y")
    (tmp_path / "sourcedata" / "sub-001" / "dicoms.tgz").write_text("tgz")

    # Outputs - NIfTI
    anat = tmp_path / "sub-001" / "anat"
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").write_text("nii")

    # Outputs - FreeSurfer (only a couple key files)
    fs = tmp_path / "derivatives" / "freesurfer" / "sub-001"
    (fs / "mri").mkdir(parents=True)
    (fs / "surf").mkdir(parents=True)
    (fs / "scripts").mkdir(parents=True)
    (fs / "mri" / "T1.mgz").write_text("mgz")
    (fs / "surf" / "lh.pial").write_text("pial")
    (fs / "scripts" / "recon-all.log").write_text("log")

    # Outputs - SimNIBS m2m
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
    (m2m / "eeg_positions").mkdir(parents=True)
    (m2m / "segmentation").mkdir(parents=True)
    (m2m / "001.msh").write_text("msh")
    (m2m / "eeg_positions" / "EEG10-10.csv").write_text("csv")
    (m2m / "segmentation" / "atlas.annot").write_text("annot")
    (m2m / "charm_report.html").write_text("html")

    gen.scan_for_data()

    assert "T1w" in gen.report_data["input_data"]
    assert "T2w" in gen.report_data["input_data"]
    assert "DICOM_compressed" in gen.report_data["input_data"]

    assert "NIfTI" in gen.report_data["output_data"]
    assert "FreeSurfer" in gen.report_data["output_data"]
    assert "SimNIBS_m2m" in gen.report_data["output_data"]
    assert "Atlas_segmentation" in gen.report_data["output_data"]

    # Generate report
    out = tmp_path / "preproc.html"
    out_path = gen.generate_html_report(str(out))
    assert out_path == str(out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<html" in text.lower()
    assert "TI-Toolbox Preprocessing Report" in text
