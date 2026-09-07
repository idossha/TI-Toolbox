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


# ---------------------------------------------------------------------------
# Analyzer._resample_if_needed
#
# Exercised with the real nibabel/scipy stack: the resampling contract is
# entirely about voxel-grid geometry, which the conftest MagicMocks cannot
# express. Synthetic label volumes keep the checks independent of the
# pre-baked dataset's particular grids.
# ---------------------------------------------------------------------------

_RESAMPLE_PREAMBLE = """
import numpy as np
import nibabel as nib
from tit.analyzer.analyzer import Analyzer

rng = np.random.default_rng(0)
labels = rng.integers(0, 12, size=(16, 16, 16)).astype(np.float64)
affine = np.diag([2.0, 2.0, 2.0, 1.0])
img = nib.Nifti1Image(labels, affine)
"""


def test_resample_preserves_label_values(tmp_path):
    """Resampling a parcellation must never invent a region id.

    Nearest-neighbour is the only interpolation order with this property;
    any blending produces values absent from the atlas and its lookup table.
    """
    script = _RESAMPLE_PREAMBLE + f"""
# Half-voxel grid: target centres fall between source centres, which is
# exactly where an interpolating order would blend neighbouring ids.
fine = np.diag([1.0, 1.0, 1.0, 1.0])
out = Analyzer._resample_if_needed(
    img, labels, (32, 32, 32), fine, {str(tmp_path / 'atlas.nii.gz')!r}
)
assert out.shape == (32, 32, 32), out.shape
invented = set(np.unique(out).tolist()) - set(np.unique(labels).tolist())
assert not invented, invented
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_triggers_on_affine_mismatch_alone(tmp_path):
    """Equal shapes with different affines must still resample.

    A shape-only guard silently returns a volume sampled from different
    anatomy, which reads downstream as a perfectly valid ROI mask.
    """
    script = _RESAMPLE_PREAMBLE + f"""
shifted = affine.copy()
shifted[:3, 3] += [0.0, 0.0, 8.0]
out = Analyzer._resample_if_needed(
    img, labels, labels.shape, shifted, {str(tmp_path / 'atlas.nii.gz')!r}
)
assert out.shape == labels.shape, out.shape
assert not np.array_equal(out, labels), 'affine mismatch was ignored'

from nibabel.processing import resample_from_to
truth = np.asanyarray(
    resample_from_to(img, (labels.shape, shifted), order=0).dataobj
)
assert np.array_equal(out, truth)
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_noop_on_identical_grid(tmp_path):
    """A matching shape and affine must return the input untouched."""
    script = _RESAMPLE_PREAMBLE + f"""
out = Analyzer._resample_if_needed(
    img, labels, labels.shape, affine, {str(tmp_path / 'atlas.nii.gz')!r}
)
assert out is labels
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_cache_is_grid_keyed_and_reused(tmp_path):
    """The cache key must identify the grid, not just its shape.

    Two targets sharing a shape but differing in affine must land in separate
    cache files; a repeat request must reuse the matching one.
    """
    script = _RESAMPLE_PREAMBLE + f"""
from pathlib import Path
d = Path({str(tmp_path)!r})
src = d / 'atlas.nii.gz'
nib.save(img, str(src))

a = np.diag([1.0, 1.0, 1.0, 1.0])
b = a.copy(); b[:3, 3] += [0.5, 0.0, 0.0]

first = Analyzer._resample_if_needed(img, labels, (32, 32, 32), a, src)
Analyzer._resample_if_needed(img, labels, (32, 32, 32), b, src)
cached = sorted(p.name for p in d.glob('*_resampled_*'))
assert len(cached) == 2, cached

reused = Analyzer._load_cached_resample(d / cached[0], (32, 32, 32))
assert reused is not None
again = Analyzer._resample_if_needed(img, labels, (32, 32, 32), a, src)
assert np.array_equal(again, first)
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_cache_distinguishes_similarly_named_atlases(tmp_path):
    """Atlases sharing a first dotted component must not share a cache key.

    ``aparc.DKTatlas+aseg`` and ``aparc.a2009s+aseg`` both live in a subject's
    FreeSurfer mri/ directory on the same grid; collapsing them onto one key
    would serve one atlas's labels for the other.
    """
    script = _RESAMPLE_PREAMBLE + f"""
from pathlib import Path
d = Path({str(tmp_path)!r})
grid = np.diag([1.0, 1.0, 1.0, 1.0])

names, keys = ['aparc.DKTatlas+aseg.mgz', 'aparc.a2009s+aseg.mgz'], []
for n in names:
    keys.append(Analyzer._resampled_name(d / n, (32, 32, 32), grid))
assert keys[0] != keys[1], keys
assert 'DKTatlas' in keys[0] and 'a2009s' in keys[1], keys

# and the extension never survives into the key
assert '.mgz' not in keys[0] and keys[0].endswith('.nii.gz'), keys[0]
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_cache_write_failure_is_non_fatal(tmp_path):
    """A cache that cannot be written must degrade to in-memory, not fail.

    The failure is injected rather than staged with directory permissions:
    the container runs as root, which bypasses the mode bits entirely and
    would leave this path silently unexercised.
    """
    script = _RESAMPLE_PREAMBLE + f"""
import shutil
from pathlib import Path
d = Path({str(tmp_path)!r})
src = d / 'atlas.nii.gz'
nib.save(img, str(src))

def boom(*a, **k):
    raise OSError(30, 'Read-only file system')

shutil.copy2 = boom
out = Analyzer._resample_if_needed(
    img, labels, (32, 32, 32), np.diag([1.0, 1.0, 1.0, 1.0]), src
)
assert out.shape == (32, 32, 32), out.shape
assert not list(d.glob('*_resampled_*')), 'cache should not exist'

from nibabel.processing import resample_from_to
truth = np.asanyarray(resample_from_to(
    img, ((32, 32, 32), np.diag([1.0, 1.0, 1.0, 1.0])), order=0).dataobj)
assert np.array_equal(out, truth), 'in-memory result must still be correct'
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout


def test_resample_ignores_corrupt_cache(tmp_path):
    """A truncated cache file is a miss, not a crash."""
    script = _RESAMPLE_PREAMBLE + f"""
from pathlib import Path
d = Path({str(tmp_path)!r})
src = d / 'atlas.nii.gz'
nib.save(img, str(src))
grid = np.diag([1.0, 1.0, 1.0, 1.0])

Analyzer._resample_if_needed(img, labels, (32, 32, 32), grid, src)
cached = next(d.glob('*_resampled_*'))
cached.write_bytes(b'not a nifti')

out = Analyzer._resample_if_needed(img, labels, (32, 32, 32), grid, src)
assert out.shape == (32, 32, 32)
print('OK')
    """
    assert "OK" in _run_real_python(script).stdout
