"""Integration checks for the CircleCI/Dockerfile.test data environment.

These tests are intentionally subprocess-based: the normal pytest ``conftest``
installs MagicMock stand-ins for heavy neuroimaging packages so fast unit tests
can run outside Docker.  The subprocesses below import TI-Toolbox with the real
``simnibs_python`` environment from ``container/blueprint/Dockerfile.test`` and
use the pre-baked data copied to ``/mnt/test_projectdir`` by
``entrypoint_test.sh``.
"""

import os
import shutil
import subprocess
import sys
import textwrap

import pytest

TEST_PROJECT = "/mnt/test_projectdir"
TEST_SUBJECT = "ernie_extended"
TEST_SIMULATION = "test_montage"


def _in_ci_test_image() -> bool:
    return os.path.isdir(TEST_PROJECT) and shutil.which("simnibs_python") is not None


def _run_real_python(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run *script* with real simnibs_python, outside pytest's import mocks."""
    return subprocess.run(
        ["simnibs_python", "-c", textwrap.dedent(script)],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=True,
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_data,
    pytest.mark.skipif(
        not _in_ci_test_image(),
        reason="requires Dockerfile.test image with /mnt/test_projectdir data",
    ),
]


def test_ci_dcm2niix_available_and_fixture_layout():
    """Validate the real dcm2niix binary and CI fixture mount are available."""
    result = subprocess.run(
        ["dcm2niix", "--version"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    # Some dcm2niix builds print a valid version and return a non-zero code.
    assert "version" in (result.stdout + result.stderr).lower()
    assert os.path.exists(
        f"{TEST_PROJECT}/derivatives/SimNIBS/sub-{TEST_SUBJECT}/m2m_{TEST_SUBJECT}/{TEST_SUBJECT}.msh"
    )


def test_ci_real_simulation_artifacts_generate_report():
    """Generate a simulation report from pre-baked real SimNIBS outputs."""
    script = f"""
    from pathlib import Path
    from tit.paths import get_path_manager
    from tit.reporting.generators.simulation import SimulationReportGenerator

    pm = get_path_manager({TEST_PROJECT!r})
    sim_dir = Path(pm.simulation({TEST_SUBJECT!r}, {TEST_SIMULATION!r}))
    assert (sim_dir / 'TI' / 'mesh' / f'{TEST_SIMULATION}_TI.msh').exists(), sim_dir
    assert (sim_dir / 'TI' / 'niftis').is_dir(), sim_dir

    gen = SimulationReportGenerator(project_dir={TEST_PROJECT!r}, subject_id={TEST_SUBJECT!r})
    gen.add_subject({TEST_SUBJECT!r}, m2m_path=str(Path(pm.m2m({TEST_SUBJECT!r}))), status='completed')
    gen.add_montage({TEST_SIMULATION!r}, [['Fp1', 'Fp2'], ['C3', 'C4']], montage_type='TI')
    out = Path(gen.generate(Path({TEST_PROJECT!r}) / 'derivatives' / 'ti-toolbox' / 'reports' / 'ci_test_simulation_report.html'))
    assert out.exists(), out
    assert 'ci_test_simulation_report.html' in out.name
    print(out)
    """

    result = _run_real_python(script)
    assert "ci_test_simulation_report.html" in result.stdout


def test_ci_real_voxel_analysis_on_precomputed_nifti():
    """Run Analyzer on the pre-baked NIfTI using real nibabel/numpy stack."""
    script = f"""
    from pathlib import Path
    import numpy as np
    import nibabel as nib
    from tit.paths import get_path_manager
    from tit.analyzer import Analyzer

    pm = get_path_manager({TEST_PROJECT!r})
    nifti = Path(pm.simulation({TEST_SUBJECT!r}, {TEST_SIMULATION!r})) / 'TI' / 'niftis' / 'grey_test_montage_TI_subject_TI_max.nii.gz'
    assert nifti.exists(), nifti

    img = nib.load(str(nifti))
    data = np.asanyarray(img.dataobj)
    voxel = np.unravel_index(np.nanargmax(data), data.shape[:3])
    center = nib.affines.apply_affine(img.affine, voxel).tolist()

    analyzer = Analyzer({TEST_SUBJECT!r}, {TEST_SIMULATION!r}, space='voxel', tissue_type='GM')
    result = analyzer.analyze_sphere(tuple(float(x) for x in center), radius=3.0)
    assert result.n_elements > 0, result
    assert result.roi_max > 0, result

    analysis_dir = Path(pm.simulation({TEST_SUBJECT!r}, {TEST_SIMULATION!r})) / 'Analyses'
    csvs = list(analysis_dir.rglob('results.csv'))
    assert csvs, analysis_dir
    print(result.roi_max, csvs[-1])
    """

    result = _run_real_python(script)
    assert "results.csv" in result.stdout
