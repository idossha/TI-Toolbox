"""End-to-end integration tests for lightweight preprocessing/simulation/analysis flows.

These tests exercise module boundaries without requiring SimNIBS, FreeSurfer, or
real DICOM/NIfTI data. External binaries and heavy neuroimaging objects are
represented by small local fakes so the public pipeline functions still run.
"""

import logging
import os
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


@pytest.mark.integration
def test_dicom_archive_to_nifti_flow(tmp_project, monkeypatch):
    """run_dicom_to_nifti extracts an archive and invokes dcm2niix end-to-end."""
    from tit.pre.dicom2nifti import run_dicom_to_nifti

    subject_id = "001"
    modality_dir = tmp_project / "sourcedata" / f"sub-{subject_id}" / "T1w"
    modality_dir.mkdir(parents=True)
    archive = modality_dir / "series.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("nested/image001.dicom", "fake-dicom")

    fake_bin = tmp_project / "bin"
    fake_bin.mkdir()
    dcm2niix = fake_bin / "dcm2niix"
    dcm2niix.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "name = sys.argv[sys.argv.index('-f') + 1]\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / f'{name}.nii.gz').write_text('fake-nifti')\n"
        "(out / f'{name}.json').write_text('{}')\n",
        encoding="utf-8",
    )
    dcm2niix.chmod(dcm2niix.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dicom_to_nifti(
        str(tmp_project),
        subject_id,
        logger=logging.getLogger("test.dicom.integration"),
    )

    assert (tmp_project / "sub-001" / "anat" / "sub-001_T1w.nii.gz").exists()
    assert (
        modality_dir
        / "dicom"
        / "extracted_archives"
        / "series.zip"
        / "nested"
        / "image001.dicom"
    ).exists()


@pytest.mark.integration
def test_simulation_orchestration_creates_expected_outputs(init_pm, tmp_project):
    """run_simulation wires config, directory setup, SimNIBS call, and result output."""
    from tit.sim import Montage, SimulationConfig, run_simulation
    from tit.sim.TI import TISimulation

    montage = Montage(
        name="test_montage",
        mode=Montage.Mode.NET,
        electrode_pairs=[("C3", "C4"), ("F3", "F4")],
        eeg_net="freehand",  # visualization is explicitly skipped
    )
    config = SimulationConfig(
        subject_id="001",
        conductivity="scalar",
        intensities=[1.0, 1.0],
        montages=[montage],
    )

    def fake_post_process(self, dirs):
        out = Path(dirs["ti_mesh"]) / f"{self.montage.name}_TI.msh"
        out.write_text("fake mesh", encoding="utf-8")
        return str(out)

    progress = []
    with (
        patch("tit.sim.base.run_simnibs") as run_simnibs,
        patch.object(TISimulation, "_post_process", fake_post_process),
    ):
        results = run_simulation(
            config,
            logger=logging.getLogger("test.sim.integration"),
            progress_callback=lambda current, total, name: progress.append(
                (current, total, name)
            ),
        )

    run_simnibs.assert_called_once()
    assert results == [
        {
            "montage_name": "test_montage",
            "montage_type": "TI",
            "status": "completed",
            "output_mesh": str(
                tmp_project
                / "derivatives"
                / "SimNIBS"
                / "sub-001"
                / "Simulations"
                / "test_montage"
                / "TI"
                / "mesh"
                / "test_montage_TI.msh"
            ),
        }
    ]
    assert progress == [(0, 1, "test_montage"), (1, 1, "Complete")]
    assert (
        tmp_project
        / "derivatives"
        / "SimNIBS"
        / "sub-001"
        / "Simulations"
        / "test_montage"
        / "documentation"
        / "config.json"
    ).exists()


@pytest.mark.integration
def test_voxel_analyzer_sphere_writes_results(init_pm, tmp_project):
    """Analyzer voxel sphere flow selects a NIfTI, computes stats, and writes CSV."""
    from tit.analyzer import Analyzer

    nifti_dir = (
        tmp_project
        / "derivatives"
        / "SimNIBS"
        / "sub-001"
        / "Simulations"
        / "analysis_sim"
        / "TI"
        / "niftis"
    )
    nifti_dir.mkdir(parents=True)
    field_path = nifti_dir / "grey_analysis_sim_TI_max.nii.gz"
    field_path.write_text("fake nifti", encoding="utf-8")

    data = np.zeros((5, 5, 5), dtype=float)
    data[2, 2, 2] = 2.0
    data[2, 2, 3] = 1.0

    class FakeHeader:
        def get_zooms(self):
            return (1.0, 1.0, 1.0)

    class FakeImage:
        affine = np.eye(4)
        header = FakeHeader()

        def get_fdata(self):
            return data

    with patch("nibabel.load", return_value=FakeImage()):
        analyzer = Analyzer(
            "001",
            "analysis_sim",
            space="voxel",
            tissue_type="GM",
        )
        result = analyzer.analyze_sphere(center=(2.0, 2.0, 2.0), radius=1.1)

    assert result.space == "voxel"
    assert result.analysis_type == "spherical"
    assert result.roi_max == 2.0
    assert result.n_elements == 2

    csv_files = list(
        (
            tmp_project
            / "derivatives"
            / "SimNIBS"
            / "sub-001"
            / "Simulations"
            / "analysis_sim"
            / "Analyses"
        ).rglob("results.csv")
    )
    assert len(csv_files) == 1
    assert "roi_max" in csv_files[0].read_text(encoding="utf-8")
