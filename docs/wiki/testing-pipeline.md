---
layout: wiki
title: Testing Pipeline
permalink: /wiki/testing-pipeline/
---

# TI-Toolbox Testing Pipeline

This document describes the comprehensive testing pipeline used by the TI-Toolbox project, including CircleCI integration, test structure, and execution flow.

## Overview

The TI-Toolbox uses a multi-layered testing approach that combines unit tests, integration tests, and automated CI/CD through CircleCI. The testing pipeline ensures code quality, functionality, and reliability across all components of the toolbox.

![TI-Toolbox CI/CD Pipeline](wiki/assets/testing/Ti-ToolboxCICD.svg)

## What is CircleCI?

CircleCI is a continuous integration and continuous deployment (CI/CD) platform that automatically builds, tests, and deploys code when changes are pushed to the repository. For the TI-Toolbox, CircleCI:

- **Automatically triggers** on every pull request to the main branch
- **Uses static test image** - `idossha/ti-toolbox-test:latest`
- **Runs ALL tests** - both unit and integration tests (complete coverage)
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
- TI-Toolbox extensions copied from PR code to SimNIBS
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

## Local Testing

Developers can run the complete test suite locally with the exact same environment as CI:

### Quick Start
```bash
# Run all tests (unit + integration)
./tests/test.sh

# Run only unit tests (fast ~2 min)
./tests/test.sh --unit-only

# Run with verbose output
./tests/test.sh --verbose

# Run only integration tests
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
- ✅ **Fast feedback**: Test before pushing to GitHub
- ✅ **Predictable**: If it passes locally, it passes in CI
- ✅ **No local setup**: SimNIBS, pytest, BATS, all tools in container
- ✅ **Static image**: Only rebuild when dependencies change

## Test Structure

### Unit Tests Location: `tests/`

The unit tests are organized by component:

#### Analyzer Tests
- `test_analyzer.py`: Core analyzer functionality
- `test_mesh_analyzer.py`: Mesh-based analysis methods
- `test_voxel_analyzer.py`: Voxel-based analysis methods
- `test_group_analyzer.py`: Group-level analysis capabilities

#### Simulator Tests
- `test_ti_simulator.py`: Traditional TI simulation methods
- `test_mti_simulator.py`: Multi-target TI simulation methods

#### Flex-Search Tests
- `test_flex_search.py`: Flexible search optimization algorithms

### Integration Tests

#### Test Setup (`tests/setup_test_projectdir.sh`)
Creates a complete BIDS-compliant test project structure:
- Downloads ErnieExtended dataset from SimNIBS
- Sets up proper directory structure (`sourcedata/`, `derivatives/`, `code/`)
- Creates montage configurations for multiple EEG nets
- Downloads test simulation data
- Configures proper permissions

#### Test Runners
- `test_simulator_runner.sh`: Executes full simulation workflows
- `test_analyzer_runner.sh`: Runs complete analysis pipelines

#### Output Validation (`tests/test_*.bats`)
- `test_simulator_outputs.bats`: Validates simulation outputs
- `test_analyzer_outputs.bats`: Validates analysis results

## Test Execution Flow

### Local Testing
```bash
# From your machine (TI-Toolbox root directory)
./tests/test.sh

# What happens:
# 1. Script checks Docker is running
# 2. Pulls idossha/ti-toolbox-test:latest (if needed)
# 3. Mounts your local code into container at /workspace
# 4. Copies TI-Toolbox extensions to SimNIBS
# 5. Runs: ./tests/run_tests.sh inside container
# 6. Displays results
```

### CI/CD Testing (CircleCI)
```bash
# CircleCI does:
# 1. Checkout PR code
# 2. Pull idossha/ti-toolbox-test:latest
# 3. Mount PR code into container at /workspace
# 4. Script copies extensions (ElectrodeCaps, tes_flex) to SimNIBS
# 5. Run: ./tests/run_tests.sh --verbose
# 6. Store artifacts and report results
```

### Inside Container (run_tests.sh)
```bash
# This is what actually runs the tests:

# 1. Unit Tests (simnibs_python -m pytest)
simnibs_python -m pytest tests/test_analyzer.py    # 157 tests
simnibs_python -m pytest tests/test_simulator.py   # 3 tests
simnibs_python -m pytest tests/test_flex_search.py # 4 tests

# 2. Integration Tests
bash tests/setup_test_projectdir.sh         # Downloads test data
bash tests/test_simulator_runner.sh          # Runs simulations
bash tests/test_analyzer_runner.sh           # Runs analyses

# 3. Validation
bats tests/test_simulator_outputs.bats       # Validates files
bats tests/test_analyzer_outputs.bats        # Validates outputs
```

## Test Data Management

### ErnieExtended Dataset
- **Source**: SimNIBS
- **Purpose**: Standardized test subject for simulations
- **Structure**: Complete SimNIBS mesh model with anatomical data

### Test Montages
- **Configuration**: Multiple EEG electrode nets (10-20, 10-10, GSN)
- **Types**: Unipolar and multipolar montages
- **Validation**: Ensures compatibility across different electrode configurations

### Simulation Data
- **Source**: Archive.org test datasets
- **Content**: Pre-computed field distributions for validation
- **Usage**: Baseline comparisons for new simulations

## Artifact Collection

The pipeline collects and stores test artifacts:

**In CircleCI:**
- **analyzer-results/**: Unit test results for analyzer components
- **simulator-results/**: Unit test results for simulator components  
- **flexsearch-results/**: Unit test results for flex-search components
- **integration-results/**: Integration test outputs and validation results

**Locally (when using `run_tests_locally.sh`):**
- **test-results/**: All test outputs saved to this directory
- **test_projectdir/**: Temporary BIDS project directory (cleaned up unless `--no-cleanup` is used)

## Maintaining the Test Image

### For Maintainers

The testing uses a static test image. To update:

1. **Modify** `development/blueprint/Dockerfile.test`
2. **Build and push**:
   ```bash
   docker login
   docker build -f development/blueprint/Dockerfile.test \
     -t idossha/ti-toolbox-test:latest .
   docker push idossha/ti-toolbox-test:latest
   ```
3. **Test** locally:
   ```bash
   TEST_IMAGE=idossha/ti-toolbox-test:latest ./tests/test.sh
   ```
4. CircleCI will automatically use the updated image on next PR

### When to Rebuild
- **SimNIBS version update** (e.g., v4.5.0 → v4.6.0)
- **System dependency changes** (new apt packages)
- **Testing tool updates** (pytest, bats versions)
- **Python package updates** (numpy, scipy, etc.)

**Do NOT rebuild for:**
- TI-Toolbox code changes (code is mounted at runtime)
- ElectrodeCaps changes (copied from mounted code)
- tes_flex_optimization changes (copied from mounted code)

### Image Details
- **Repository**: `idossha/ti-toolbox-test`
- **Current Version**: `latest`
- **Base**: Ubuntu 22.04
- **Size**: ~15-20 GB (includes SimNIBS 4.5, testing tools)
- **Contents**: SimNIBS, pytest, BATS, system utilities
- **Excludes**: TI-Toolbox code (mounted at runtime)

## Troubleshooting

### Common Issues

#### 1. Docker image availability
- **CI**: Falls back to local build if DockerHub pull fails
- **Local**: Use `--build` flag to build locally instead of pulling

#### 2. Test data downloads
- ErnieExtended data is fetched from OSF during test setup
- Script includes fallback URLs and validation
- Network issues are handled gracefully with clear error messages

#### 3. Permission problems
- Tests run as root in Docker containers to avoid permission issues
- Local test directories are automatically created with proper permissions

#### 4. "Docker is not running"
- Start Docker Desktop
- Verify with: `docker info`

#### 5. Tests fail locally but pass in CI
- Pull latest image: remove `--no-pull` flag
- Check Docker has enough resources (memory, disk space)
- Use `--verbose` flag to see detailed output

#### 6. Need to test changes to Docker image
- Build locally: `./tests/run_tests_locally.sh --build`
- This uses your local `Dockerfile.ci.min` changes

## Additional Resources

- **Local Testing Wrapper**: `tests/test.sh`
- **Core Test Runner**: `tests/run_tests.sh`
- **Testing Guide**: `tests/README_TESTING.md`
- **CircleCI Guide**: `.circleci/README_CIRCLECI.md`
- **CircleCI Configuration**: `.circleci/config.yml`
- **SimNIBS Dockerfile**: `development/blueprint/Dockerfile.simnibs`
