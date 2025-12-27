---
layout: wiki
title: Testing Pipeline
permalink: /wiki/testing-pipeline/
---

## Overview

The TI-Toolbox uses a multi-layered testing approach that combines unit tests, integration tests, and automated CI/CD through CircleCI. The testing pipeline ensures code quality, functionality, and reliability across all components of the toolbox.

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/wiki/testing-pipeline/testing_graphical_abstract_revised.png" alt="Complete TI-Toolbox Tech-stack">
        <p>Complete TI-Toolbox Tech-stack</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki/testing-pipeline/testing_Ti-ToolboxCICD.png" alt="TI-Toolbox CI/CD Pipeline">
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

## What is CircleCI?

CircleCI is a continuous integration and continuous deployment (CI/CD) platform that automatically builds, tests, and deploys code when changes are pushed to the repository. For the TI-Toolbox, CircleCI:

- **Automatically triggers** on every pull request to the main branch
- **Uses static test image** - `idossha/ti-toolbox-test:latest`
- **Runs ALL tests** - both unit and integration tests
- **Provides detailed reports** on test results and artifacts
- **Ensures perfect parity** between local and CI testing environments

## Pipeline Configuration

The testing pipeline is configured in `.circleci/config.yml` and consists of:

### Executors
- **vm-docker**: Uses Ubuntu 22.04 with Docker layer caching disabled for consistent builds

### Workflow Triggers
- **Pull Requests**: Tests automatically run on all branches when a PR is created/updated
- **Direct Commits**: Tests do NOT run on direct commits to `main` or `master` branches
- This approach encourages proper PR workflow and saves CI resources

### Key Components

#### 1. TI-Toolbox Test Image
The pipeline uses a static test image designed for CI/CD:

- **Image**: `idossha/ti-toolbox-test:latest`
- **Contains**:
  - Ubuntu 22.04
  - SimNIBS 4.5 (electromagnetic field simulations)
  - Python 3.11 with all scientific packages
  - pytest and BATS testing frameworks
  - All system utilities (curl, wget, jq, unzip, dos2unix, etc.)
  - **No TI-Toolbox code** (mounted from PR at runtime)

**Benefits:**
- Static image - doesn't change unless dependencies update
- PR code is mounted at runtime for testing
- TI-Toolbox extensions copied from PR code
- Same image used locally and in CI

#### 2. Test Execution
Single unified test runner:

**Entry Point**: `./tests/run_tests.sh`
- Runs inside SimNIBS container
- Tests PR code (mounted into container)
- Executes all tests: unit + integration
- Used by both local testing and CI

**Tests Run**:
- **Unit Tests** (~2 min): 164 tests (analyzer, simulator, flex-search)
- **Integration Tests** (~15-20 min): Full simulations, analysis pipelines, validation

---

## Local Testing

Developers should run the complete test suite locally with the exact same environment as CI.

**⚠️ Important:** Always use `./tests/test.sh` from your host machine. Do NOT run individual integration test scripts (`test_simulator_runner.sh`, `test_analyzer_runner.sh`) directly - they require the Docker container environment and will fail on your host.

### Quick Start
```bash
# Run all tests (unit + integration) - RECOMMENDED before committing
./tests/test.sh

# Run only unit tests (fast ~2 min) - for quick validation during development
./tests/test.sh --unit-only

# Run with verbose output - helpful for debugging test failures
./tests/test.sh --verbose

# Run only integration tests - if you've already verified unit tests
./tests/test.sh --integration-only
```

### Available Options
- `-h, --help`: Show help message
- `-u, --unit-only`: Run only unit tests (fast)
- `-i, --integration-only`: Run only integration tests
- `-v, --verbose`: Show detailed test output
- `-s, --skip-setup`: Skip test project setup (reuse existing data)
- `-n, --no-cleanup`: Keep test directories after completion

### Environment Variables
- `TEST_IMAGE`: Override test image version (default: `idossha/ti-toolbox-test:latest`)

### Benefits of Local Testing
- ✅ **Perfect parity**: Same Docker image as CI (`idossha/ti-toolbox-test:latest`)
- ✅ **Complete testing**: All tests run (unit + integration)
- ✅ **Fast feedback**: Test locally before submitting a PR
- ✅ **Predictable**: If it passes locally, it passes in CI
- ✅ **Tests your code**: Your local changes are mounted into container and tested

---

## Test Structure

### Unit Tests Location: `tests/`

The unit tests are organized by component:

#### Analyzer Tests
- `test_analyzer.py`: Core analyzer functionality
- `test_mesh_analyzer.py`: Mesh-based analysis methods
- `test_voxel_analyzer.py`: Voxel-based analysis methods
- `test_group_analyzer.py`: Group-level analysis capabilities

#### Simulator Tests
- `test_ti_simulator.py`: unipolar TI simulation
- `test_mti_simulator.py`: multipolar TI simulation

#### Flex-Search Tests
- `test_flex_search.py`: Flex-search optimization approach

### Integration Tests

#### Test Setup (`tests/setup_test_projectdir.sh`)
Creates a complete BIDS-compliant test project structure:
- Downloads ErnieExtended dataset from SimNIBS
- Sets up proper directory structure (`sourcedata/`, `derivatives/`, `code/`)
- Creates montage configurations for multiple EEG nets
- Downloads test simulation data
- Configures proper permissions


#### Output Validation (`tests/test_*.bats`)
- `test_simulator_outputs.bats`: Validates simulation outputs
- `test_analyzer_outputs.bats`: Validates analysis results


---

## Test Execution Flow

### Local Testing (Initial Test)
```bash
# From your host machine (TI-Toolbox root directory)
./tests/test.sh

# What happens:
# 1. Script checks Docker is running
# 2. Pulls idossha/ti-toolbox-test:latest (if needed)
# 3. Mounts your local code into container at /ti-toolbox
# 4. Creates test directories (/tmp/test_projectdir on host)
# 5. Runs: ./tests/run_tests.sh inside container
#    - Copies TI-Toolbox extensions (ElectrodeCaps, tes_flex) to SimNIBS
#    - Runs unit tests with pytest
#    - Sets up test project with ErnieExtended data
#    - Runs integration tests (simulator, analyzer)
#    - Validates outputs with BATS
# 6. Cleans up test directories
# 7. Displays results
```


### CI/CD Testing (CircleCI)
```bash
# CircleCI does:
# 1. Checkout PR code
# 2. Pull idossha/ti-toolbox-test:latest
# 3. Mount PR code into container at /ti-toolbox
# 4. Script copies extensions (ElectrodeCaps, tes_flex) to SimNIBS
# 5. Run: ./tests/run_tests.sh --verbose
# 6. Store artifacts and report results
```

---
