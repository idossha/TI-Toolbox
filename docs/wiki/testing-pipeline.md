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
- **Uses SimNIBS Docker image** - the same image developers use locally
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

#### 1. SimNIBS Docker Image
The pipeline uses the full SimNIBS production image:

- **Image**: `idossha/simnibs:v2.1.3`
- **Contains**:
  - SimNIBS 4.5 (electromagnetic field simulations)
  - FreeSurfer 7.4.1 (brain surface reconstruction)
  - Python 3.11 with all scientific packages
  - pytest and BATS testing frameworks
  - All system utilities (curl, wget, jq, unzip, etc.)
  - TI-Toolbox code (mounted from PR)

**This is the SAME image developers use locally!**

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
- `SIMNIBS_IMAGE`: Override SimNIBS image version (default: `idossha/simnibs:v2.1.3`)

### Benefits of Local Testing
- ✅ **Perfect parity**: Same Docker image as CI (`idossha/simnibs:v2.1.3`)
- ✅ **Complete testing**: All tests run (unit + integration)
- ✅ **Fast feedback**: Test before pushing to GitHub
- ✅ **Predictable**: If it passes locally, it passes in CI
- ✅ **No local setup**: SimNIBS, FreeSurfer, all tools in container

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
# 2. Pulls idossha/simnibs:v2.1.3 (if needed)
# 3. Mounts your local code into container
# 4. Runs: ./tests/run_tests.sh inside container
# 5. Displays results
```

### CI/CD Testing (CircleCI)
```bash
# CircleCI does:
# 1. Checkout PR code
# 2. Pull idossha/simnibs:v2.1.3
# 3. Mount PR code into container
# 4. Run: ./tests/run_tests.sh --verbose
# 5. Store artifacts and report results
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

## Maintaining the SimNIBS Image

### For Maintainers

The testing uses the production SimNIBS image. To update:

1. **Modify** `development/blueprint/Dockerfile.simnibs`
2. **Build** the new image:
   ```bash
   docker build -f development/blueprint/Dockerfile.simnibs \
     -t idossha/simnibs:v2.1.4 .
   ```
3. **Test** locally:
   ```bash
   SIMNIBS_IMAGE=idossha/simnibs:v2.1.4 ./tests/test.sh
   ```
4. **Push** to Docker Hub:
   ```bash
   docker push idossha/simnibs:v2.1.4
   docker tag idossha/simnibs:v2.1.4 idossha/simnibs:latest
   docker push idossha/simnibs:latest
   ```
5. **Update** version in `.circleci/config.yml`:
   ```yaml
   SIMNIBS_IMAGE="idossha/simnibs:v2.1.4"
   ```

### When to Rebuild
- SimNIBS version update
- Adding testing tools (pytest, bats, etc.)
- System dependency changes
- TI-Toolbox integration changes

### Image Details
- **Repository**: `idossha/simnibs`
- **Current Version**: `v2.1.3`
- **Base**: Ubuntu 22.04
- **Size**: ~15-20 GB (includes SimNIBS, FreeSurfer, all tools)

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
