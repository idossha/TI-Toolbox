---
layout: wiki
title: Testing Pipeline
permalink: /wiki/testing-pipeline/
---

# TI-Toolbox Testing Pipeline

This document describes the comprehensive testing pipeline used by the TI-Toolbox project, including CircleCI integration, test structure, and execution flow.

## Overview

The TI-Toolbox uses a multi-layered testing approach that combines unit tests, integration tests, and automated CI/CD through CircleCI. The testing pipeline ensures code quality, functionality, and reliability across all components of the toolbox.

<div class="image-row-natural">
  <div class="image-container-natural">
    <img src="{{ site.baseurl }}/wiki/assets/testing/graphical_abstract_revised.png" alt="Complete TI-Toolbox Tech-stack">
    <em>Complete TI-Toolbox Tech-stack</em>
  </div>
  <div class="image-container-natural">
    <img src="{{ site.baseurl }}/wiki/assets/testing/Ti-ToolboxCICD.png" alt="TI-Toolbox CI/CD Pipeline">
    <em>TI-Toolbox CI/CD Pipeline</em>
  </div>
</div>

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

Developers can run the complete test suite locally with the exact same environment as CI.

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
- ✅ **Fast feedback**: Test before pushing to GitHub
- ✅ **Predictable**: If it passes locally, it passes in CI
- ✅ **No local setup**: SimNIBS, pytest, BATS, all tools in container
- ✅ **Static image**: Only rebuild when dependencies change
- ✅ **Tests your code**: Your local changes are mounted into container and tested

### ⚠️ Common Mistakes to Avoid

**DON'T run integration tests directly:**
```bash
# ❌ These will FAIL on your host machine (macOS/Windows/Linux)
./tests/test_simulator_runner.sh
./tests/test_analyzer_runner.sh

# ❌ Unit tests need SimNIBS environment
simnibs_python -m pytest tests/test_ti_simulator.py
```

**DO use the test wrapper:**
```bash
# ✅ This works - automatically sets up Docker and runs tests
./tests/test.sh

# ✅ For quick validation during development
./tests/test.sh --unit-only
```

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

#### Test Runners (Run Inside Container Only)
- `test_simulator_runner.sh`: Executes full simulation workflows
  - ⚠️ Designed to run INSIDE Docker container only
  - Called automatically by `test.sh` and `run_tests.sh`
- `test_analyzer_runner.sh`: Runs complete analysis pipelines
  - ⚠️ Designed to run INSIDE Docker container only
  - Called automatically by `test.sh` and `run_tests.sh`

#### Output Validation (`tests/test_*.bats`)
- `test_simulator_outputs.bats`: Validates simulation outputs
- `test_analyzer_outputs.bats`: Validates analysis results

## Test Execution Flow

### Local Testing (Primary Method)
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

### Development Container Testing (Advanced)
If you're working inside a Docker development container with code mounted at `/development`:
```bash
# From inside the development container
cd /development
./tests/run_tests.sh

# The script detects the mounted code and uses it
# Priority: /development → current dir → /ti-toolbox (baked-in)
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

**Locally (when using `./tests/test.sh`):**
- **`/tmp/test_projectdir/`**: Temporary BIDS project directory (automatically cleaned up)
  - Use `--no-cleanup` flag to keep for inspection
- Test output is displayed to console
  - Use `--verbose` flag for detailed output

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

#### 5. Tests pass locally but fail in CI
- This should be extremely rare (both use same image and scripts)
- Check CircleCI logs for details
- Verify test image versions match
- Check for network issues (test data downloads from OSF)

#### 6. Integration tests fail when run directly
- **Expected!** Integration tests require Docker container environment
- Use `./tests/test.sh` instead of running test scripts directly
- Individual integration test scripts (`test_*_runner.sh`) are designed for container use only

#### 7. Need to test changes to Docker image
- Build locally: `docker build -f development/blueprint/Dockerfile.test -t ti-toolbox-test:local .`
- Use custom image: `TEST_IMAGE=ti-toolbox-test:local ./tests/test.sh`
- This uses your local `development/blueprint/Dockerfile.test` changes

#### 8. Want to inspect test data after tests complete
- Use `--no-cleanup` flag: `./tests/test.sh --no-cleanup`
- Test project will remain in `/tmp/test_projectdir`
- Manually clean up when done: `rm -rf /tmp/test_projectdir`

## Additional Resources

- **Local Testing Wrapper**: `tests/test.sh`
- **Core Test Runner**: `tests/run_tests.sh`
- **Testing Guide**: `tests/README_TESTING.md`
- **CircleCI Guide**: `.circleci/README_CIRCLECI.md`
- **CircleCI Configuration**: `.circleci/config.yml`
- **SimNIBS Dockerfile**: `development/blueprint/Dockerfile.simnibs`
