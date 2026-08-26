---
layout: wiki
title: Testing Pipeline
permalink: /wiki/testing-pipeline/
---

## Overview

The TI-Toolbox uses a two-tier testing approach: a fast unit test suite (pytest, runs anywhere) and Docker-based integration tests (CircleCI). The unit test suite was rebuilt from scratch in v2.2.4 and has grown since; it runs 2,463 tests (v2.4.0) in under a minute without Docker or any heavy dependencies.

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/development/testing_graphical_abstract_revised.png" alt="Complete TI-Toolbox Tech-stack">
        <p>Complete TI-Toolbox Tech-stack</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/development/testing_Ti-ToolboxCICD.png" alt="TI-Toolbox CI/CD Pipeline">
        <p>TI-Toolbox CI/CD Pipeline</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
    </div>
  </div>
</div>

## Unit Test Suite (pytest)

### At a Glance

- **2,463 tests** across 77 modules (v2.4.0), completes in well under a minute
- Runs on any machine with Python 3.11+ -- no Docker, no SimNIBS, no GPU
- All heavy dependencies are mocked at import time via `conftest.py`

### Mocking Strategy (`tests/conftest.py`)

The test suite must run outside Docker where SimNIBS, FreeSurfer, and scientific libraries are unavailable. `conftest.py` uses `pytest_configure()` to inject `MagicMock` modules into `sys.modules` before any `tit` imports occur.

**Mocked packages:**
- `simnibs` (including `simulation.sim_struct`, `mesh_tools.mesh_io`, `utils.transformations`, `utils.file_finder`, `eeg.forward`)
- `mne` (including `io`, `channels`, `coreg`, `transforms`, `datasets`)
- `bpy`
- `scipy` (`optimize`, `spatial`, `spatial.transform`)
- `nibabel`, `nibabel.freesurfer`
- `h5py`
- `matplotlib` (`pyplot`, `backends.backend_pdf`, `lines`)
- `pandas`
- `joblib`
- `nilearn` (`plotting`, `image`)
- `trimesh`

`numpy` is **not** mocked -- it is a real, lightweight dependency and is used directly in vector-math tests (e.g. `test_calc.py`).

The mock hierarchy is built so that dotted imports (e.g., `from matplotlib.lines import Line2D`) resolve correctly -- child mocks are wired as attributes of their parent mocks.

### Key Fixtures

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `_reset_path_manager` | autouse (every test) | Resets the `PathManager` singleton after each test to prevent cross-test contamination |
| `tmp_project` | function | Creates a minimal BIDS-compliant directory tree under `tmp_path` |
| `init_pm` | function | Initializes a `PathManager` pointed at `tmp_project` |

The `tmp_project` fixture creates this layout:

```
tmp_path/
├── sub-001/anat/
├── derivatives/
│   ├── SimNIBS/sub-001/m2m_001/segmentation/
│   ├── SimNIBS/sub-001/Simulations/
│   ├── freesurfer/sub-001/
│   └── ti-toolbox/
├── code/ti-toolbox/config/
└── sourcedata/
```

### Coverage Areas

| Area | Test modules |
|------|--------------|
| Core | `test_constants.py`, `test_paths.py`, `test_config_io.py`, `test_logger*.py`, `test_telemetry.py` |
| Simulation | `test_sim_*.py` (config, TI/mTI field math, montage loading, visualizer) |
| Optimization | `test_opt_*.py` (flex/ex/mex configs, engines, leadfields, ROI handling, focality goals) |
| Pre-processing | `test_pre*.py` incl. `test_pre_qsi_*.py` (DICOM ingestion, CHARM, recon-all, QSIPrep/QSIRecon, DTI extraction) |
| Analysis & statistics | `test_analyzer*.py`, `test_atlas*.py`, `test_stats_*.py` (volume and fsaverage-surface permutation tests) |
| Visualisation & reporting | `test_blender_*.py`, `test_plotting*.py`, `test_reporting*.py`, `test_report_previews.py` |
| Source / EEG forward | `test_source.py` |
| GUI & tooling | `test_gui_imports.py`, `test_scripts.py`, `test_agent_plugin_mcp.py`, `test_integration.py` |

### Running Tests Locally

```bash
# From the repository root, no Docker required -- conftest mocking handles everything
pytest tests/ -v

# Same suite inside the CI image (requires Docker)
./tests/test.sh
```

---

## CI/CD (CircleCI)

### What is CircleCI?

CircleCI is a continuous integration platform that automatically runs the test suite on every pull request. For the TI-Toolbox, CircleCI:

- **Automatically triggers** on every pull request to the main branch
- **Uses static test image** -- `idossha/ti-toolbox-test:latest`
- **Runs the pytest suite** inside the container
- **Provides detailed reports** on test results and artifacts

### Pipeline Configuration

The testing pipeline is configured in `.circleci/config.yml`:

- **Executor**: Ubuntu 22.04 VM with Docker
- **Pull Requests**: Tests automatically run on all branches when a PR is created/updated
- **Direct Commits**: Tests do NOT run on direct commits to `main` or `master`
- **Coverage**: `test.sh --verbose --coverage` produces `coverage.xml`, uploaded to Codecov (the job fails without `CODECOV_TOKEN`)

### TI-Toolbox Test Image

- **Image**: `idossha/ti-toolbox-test:latest`
- **Contains**: Ubuntu 22.04, SimNIBS 4.6, Python 3.11, meshio/nilearn/trimesh/seaborn/scikit-image/bpy, pytest + pytest-cov (no mne — `tit.source` is tested against the mock)
- **No TI-Toolbox code** -- PR code is mounted at runtime

### Test Execution Flow

**Local:**
```bash
pytest tests/ -v
# Runs pytest directly -- fast, no Docker needed

./tests/test.sh
# Wrapper that runs the same suite inside idossha/ti-toolbox-test:latest
```

**CI/CD:**
```bash
# CircleCI does:
# 1. Checkout PR code
# 2. Pull idossha/ti-toolbox-test:latest
# 3. Mount PR code into container
# 4. Run pytest inside container
# 5. Store artifacts and report results
```

---
