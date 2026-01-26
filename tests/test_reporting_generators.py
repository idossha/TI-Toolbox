#!/usr/bin/env python3
"""
Unit tests for report generators in tit/reporting.
"""

from pathlib import Path

import pytest


def _stub_versions(monkeypatch):
    from tit.reporting.generators.base_generator import BaseReportGenerator

    def _collect(self):
        self.software_versions = {"python": "3.x", "ti_toolbox": "test"}

    monkeypatch.setattr(BaseReportGenerator, "_collect_software_versions", _collect)


@pytest.mark.unit
def test_simulation_report_generator_writes_report(tmp_path, monkeypatch):
    from tit.reporting import SimulationReportGenerator

    _stub_versions(monkeypatch)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    gen = SimulationReportGenerator(
        project_dir=project_dir,
        simulation_session_id="session-1",
        subject_id="001",
    )
    gen.add_simulation_parameters(
        conductivity_type="scalar",
        simulation_mode="TI",
        intensity_ch1=2.0,
        intensity_ch2=1.5,
    )
    gen.add_electrode_parameters(
        shape="rectangular",
        dimensions="10x10 mm",
        thickness=2.0,
    )
    gen.add_subject(subject_id="001", m2m_path="/tmp/m2m_001", status="completed")
    gen.add_montage(
        montage_name="central_montage",
        electrode_pairs=[("Fz", "Pz"), ("C3", "C4")],
    )
    gen.add_simulation_result(
        subject_id="001",
        montage_name="central_montage",
        status="completed",
        duration=12.5,
        metrics={"peak": 0.8},
    )

    report_path = gen.generate()

    assert report_path.exists()
    html = report_path.read_text()
    assert "TI Simulation Report" in html
    assert "Simulation Parameters" in html

    desc_path = project_dir / "derivatives/ti-toolbox/reports/dataset_description.json"
    assert desc_path.exists()


@pytest.mark.unit
def test_preprocessing_report_generator_writes_report(tmp_path, monkeypatch):
    from tit.reporting import PreprocessingReportGenerator

    _stub_versions(monkeypatch)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    gen = PreprocessingReportGenerator(project_dir=project_dir, subject_id="001")
    gen.add_processing_step(
        step_name="DICOM Conversion",
        description="Convert DICOM to NIfTI",
        status="completed",
        duration=4.2,
    )
    gen.add_processing_step(
        step_name="SimNIBS charm",
        description="Create head mesh",
        status="completed",
        duration=15.0,
    )
    gen.add_output_data(
        "SimNIBS m2m",
        [str(project_dir / "derivatives" / "simnibs" / "sub-001" / "m2m_001")],
    )

    report_path = gen.generate()

    assert report_path.exists()
    html = report_path.read_text()
    assert "Preprocessing Report" in html
    assert "Processing Steps" in html


@pytest.mark.unit
def test_flex_search_report_generator_writes_report(tmp_path, monkeypatch):
    from tit.reporting import FlexSearchReportGenerator

    _stub_versions(monkeypatch)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    gen = FlexSearchReportGenerator(project_dir=project_dir, subject_id="001")
    gen.set_configuration(
        electrode_net="GSN-HydroCel-185",
        optimization_target="mean_field",
        n_candidates=10,
        selection_method="best",
    )
    gen.set_roi_info(roi_name="Hippocampus", roi_type="atlas")
    gen.add_search_result(
        rank=1,
        electrode_1a="F3",
        electrode_1b="F4",
        electrode_2a="P3",
        electrode_2b="P4",
        score=0.95,
    )
    gen.set_best_solution(
        electrode_pairs=[{"electrode1": "F3", "electrode2": "F4"}],
        score=0.95,
        metrics={"mean_field": 0.75},
        montage_image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==",
    )

    report_path = gen.generate()

    assert report_path.exists()
    html = report_path.read_text()
    assert "Flex-Search Optimization Report" in html
    assert "Optimal Solution" in html
