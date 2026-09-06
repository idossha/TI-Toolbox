"""
Shared fixtures and configuration for TI-Toolbox tests.

Mocks heavy/unavailable dependencies (simnibs, bpy) at import level
and provides BIDS-compliant temporary project structures.
"""

import gzip
import json
import math
import os
import struct
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Belt: the suite must never phone home to Google Analytics. tit.telemetry
# honours this env var in is_enabled(); set it before anything imports tit so
# every test starts from a disabled-by-default state. Some tests (notably
# tests/test_telemetry.py, which exercises the env-var mechanism itself)
# deliberately unset this for a single test — the session-wide _send_ga4
# patch below (suspenders) is what actually blocks the network call in that
# case. See ra_11 finding 2.
os.environ.setdefault("TIT_NO_TELEMETRY", "1")

# ============================================================================
# Mock unavailable dependencies before any tit imports
# ============================================================================


def _install_mock_module(name: str) -> MagicMock:
    """Insert a MagicMock into sys.modules for *name* and all dotted parents."""
    mock = MagicMock(spec=[])
    parts = name.split(".")
    for i in range(len(parts)):
        partial = ".".join(parts[: i + 1])
        if partial not in sys.modules:
            sys.modules[partial] = MagicMock() if i < len(parts) - 1 else mock
    return mock


_MOCK_PACKAGES = [
    "simnibs",
    "simnibs.simulation",
    "simnibs.simulation.sim_struct",
    "simnibs.mesh_tools",
    "simnibs.mesh_tools.mesh_io",
    "simnibs.utils",
    "simnibs.utils.transformations",
    "simnibs.utils.file_finder",
    "simnibs.eeg",
    "simnibs.eeg.forward",
    "mne",
    "mne.io",
    "mne.channels",
    "mne.coreg",
    "mne.transforms",
    "mne.datasets",
    "bpy",
    "scipy",
    "scipy.optimize",
    "scipy.spatial",
    "scipy.spatial.transform",
    "nibabel",
    "nibabel.freesurfer",
    "h5py",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.backends",
    "matplotlib.backends.backend_pdf",
    "matplotlib.lines",
    "pandas",
    "joblib",
    "nilearn",
    "nilearn.plotting",
    "nilearn.image",
    "trimesh",
]


def pytest_configure(config):
    """Mock heavy third-party packages that are unavailable outside Docker.

    Builds a hierarchy of MagicMock modules so that dotted imports
    (e.g. ``from matplotlib.lines import Line2D``) resolve correctly.
    """
    # Group packages by top-level name so children share the parent mock.
    _mocks: dict[str, MagicMock] = {}
    for pkg in _MOCK_PACKAGES:
        if pkg in sys.modules:
            continue
        parts = pkg.split(".")
        # Ensure all ancestor mocks exist
        for i in range(len(parts)):
            partial = ".".join(parts[: i + 1])
            if partial not in sys.modules and partial not in _mocks:
                _mocks[partial] = MagicMock()
                sys.modules[partial] = _mocks[partial]
            elif partial in sys.modules:
                _mocks[partial] = sys.modules[partial]
        # Wire child as attribute of parent
        for i in range(1, len(parts)):
            parent_key = ".".join(parts[:i])
            child_key = ".".join(parts[: i + 1])
            setattr(_mocks[parent_key], parts[i], _mocks[child_key])


# ============================================================================
# PathManager reset — runs after every test automatically
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_path_manager():
    """Reset the PathManager singleton after each test."""
    yield
    from tit.paths import reset_path_manager

    reset_path_manager()


# ============================================================================
# Telemetry — never let the suite make a real network call
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def _block_real_telemetry():
    """Suspenders on top of the ``TIT_NO_TELEMETRY`` belt (see top of file).

    ``tit.constants.GA4_MEASUREMENT_ID``/``GA4_API_SECRET`` are real, live
    credentials (not placeholders), so any test that flips telemetry on
    without also blocking the send — or that clears ``TIT_NO_TELEMETRY`` to
    exercise the env var itself — would otherwise POST to production Google
    Analytics (ra_11 finding 2). Patching ``_send_ga4`` at the module level
    for the whole session makes that impossible regardless of what any
    individual test does to the config or the env var.

    Tests that want to capture what *would* have been sent (most of
    ``tests/test_telemetry.py``) still work: they locally
    ``unittest.mock.patch("tit.telemetry._send_ga4", ...)`` as a context
    manager, which nests on top of this patch and restores back to this
    no-op afterwards — never to the real network call.
    """
    import tit.telemetry as telemetry

    mp = pytest.MonkeyPatch()
    mp.setattr(telemetry, "_send_ga4", lambda payload: None)
    yield
    mp.undo()


# ============================================================================
# JobManager — never let its poll thread leak across test modules
# ============================================================================


def _reset_job_manager() -> None:
    """Tear down the process-wide JobManager singleton, if one exists.

    Several test modules build a real ``JobManager`` via
    ``tit.jobs.bootstrap.get_manager()``, which starts a background poll
    thread that runs until explicitly shut down. Left alive across modules
    it both leaks and, before the telemetry thread was named (see
    ``tit/telemetry.py``), used to get erroneously joined by
    ``tests/test_telemetry.py``'s "wait for any daemon thread" helper
    (ra_11 finding 1). Prefers ``bootstrap.shutdown()``; falls back to the
    older ``reset_manager()`` name if that hasn't landed yet. A no-op when
    no manager was ever created.
    """
    try:
        from tit.jobs import bootstrap
    except ImportError:
        return
    shutdown = getattr(bootstrap, "shutdown", None)
    if shutdown is not None:
        shutdown()
        return
    reset_manager = getattr(bootstrap, "reset_manager", None)
    if reset_manager is not None:
        reset_manager()


@pytest.fixture(autouse=True, scope="module")
def _reset_job_manager_per_module():
    """Shut down any JobManager a test module created before the next one runs."""
    yield
    _reset_job_manager()


@pytest.fixture(autouse=True, scope="session")
def _reset_job_manager_at_session_end():
    """Final safety net: no JobManager poll thread should outlive the run."""
    yield
    _reset_job_manager()


# ============================================================================
# Temporary BIDS project directory
# ============================================================================


@pytest.fixture()
def tmp_project(tmp_path):
    """Create a minimal BIDS-compliant project directory tree.

    Layout::

        tmp_path/
        ├── sub-001/anat/
        ├── derivatives/
        │   ├── SimNIBS/sub-001/m2m_001/segmentation/
        │   ├── SimNIBS/sub-001/Simulations/
        │   ├── freesurfer/sub-001/
        │   └── ti-toolbox/
        ├── code/ti-toolbox/config/
        └── sourcedata/

    Returns the *tmp_path* (project root).
    """
    dirs = [
        tmp_path / "sub-001" / "anat",
        tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001" / "segmentation",
        tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "Simulations",
        tmp_path / "derivatives" / "freesurfer" / "sub-001",
        tmp_path / "derivatives" / "ti-toolbox",
        tmp_path / "code" / "ti-toolbox" / "config",
        tmp_path / "sourcedata",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    return tmp_path


@pytest.fixture()
def init_pm(tmp_project):
    """Initialize and return a PathManager pointed at *tmp_project*."""
    from tit.paths import get_path_manager

    return get_path_manager(str(tmp_project))


def _nifti1_header(n_volumes: int) -> bytes:
    """Return a 352-byte NIfTI-1 header describing an *n_volumes* 4D image.

    Written by hand because nibabel is mocked in this suite, and because the
    DWI validator reads the header fields directly rather than opening the
    image.
    """
    header = bytearray(352)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 4, 64, 64, 40, n_volumes, 1, 1, 1)
    struct.pack_into("<h", header, 70, 4)  # datatype: int16
    struct.pack_into("<h", header, 72, 16)  # bitpix
    struct.pack_into("<f", header, 108, 352.0)  # vox_offset
    header[344:348] = b"n+1\x00"
    return bytes(header)


@pytest.fixture()
def write_dwi():
    """Write a valid BIDS DWI series (NIfTI header, gradient table, sidecar).

    Returns a callable ``(dwi_dir, stem='sub-001_dwi', n_directions=6,
    n_b0=1, **sidecar)`` so a test can vary one property and leave the rest
    consistent.
    """

    def _write(
        dwi_dir,
        stem="sub-001_dwi",
        *,
        n_directions=6,
        n_b0=1,
        sidecar=None,
    ):
        dwi_dir = Path(dwi_dir)
        dwi_dir.mkdir(parents=True, exist_ok=True)
        n_volumes = n_b0 + n_directions

        with gzip.open(dwi_dir / f"{stem}.nii.gz", "wb") as handle:
            handle.write(_nifti1_header(n_volumes))

        # Distinct directions matter: the validator counts unique vectors, so a
        # repeated one would not satisfy the tensor-fitting minimum.
        vectors = [(0.0, 0.0, 0.0)] * n_b0 + [
            (math.cos(i), math.sin(i), math.sin(i) * 0.5) for i in range(n_directions)
        ]
        bvals = [0] * n_b0 + [1000] * n_directions
        (dwi_dir / f"{stem}.bval").write_text(
            " ".join(str(b) for b in bvals) + "\n", encoding="utf-8"
        )
        (dwi_dir / f"{stem}.bvec").write_text(
            "\n".join(
                " ".join(f"{vector[axis]:.6f}" for vector in vectors)
                for axis in range(3)
            )
            + "\n",
            encoding="utf-8",
        )

        metadata = {"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.05}
        if sidecar is not None:
            metadata = sidecar
        if metadata:
            (dwi_dir / f"{stem}.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )
        return dwi_dir / f"{stem}.nii.gz"

    return _write
