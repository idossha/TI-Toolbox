---
layout: wiki
title: run_tests.sh - Local Testing Script
permalink: /wiki/run_tests_script/
---

# run_tests.sh - Local Testing Script

The `run_tests.sh` script is a comprehensive local testing wrapper that replicates the CircleCI build and test process on your local machine. This script provides developers with the ability to run the complete TI-Toolbox test suite locally, ensuring code quality and functionality before pushing changes to the repository.

## Overview

The `run_tests.sh` script is located in `development/bash_dev/run_tests.sh` and serves as a local equivalent to the CircleCI testing pipeline. It builds Docker images, installs necessary packages, sets up test project directories, and runs both unit and integration tests with detailed reporting.

## What This Script Is

### A CircleCI Wrapper
The script replicates the exact same testing process that runs automatically on CircleCI when code is pushed to the repository. It ensures that:

- **Local testing matches CI testing** - Same Docker images, same test environment, same test execution
- **Consistent results** - Developers get the same test results locally as they will in CI
- **Early problem detection** - Issues are caught locally before they reach the CI pipeline

### A Comprehensive Test Suite Runner
The script orchestrates multiple types of tests:

1. **Unit Tests** - Individual component testing using pytest
2. **Integration Tests** - End-to-end workflow testing
3. **Validation Tests** - Output verification using BATS (Bash Automated Testing System)

### A Docker Environment Manager
The script handles complex Docker operations:

- **Image Management** - Pulls pre-built images from DockerHub or builds them locally
- **Resource Management** - Applies memory limits and resource constraints to prevent system issues
- **Environment Setup** - Creates isolated test environments with proper permissions

## What Happens When You Run It

### Step 1: Docker Environment Check
```
[2024-01-15 10:30:15] [INFO] Checking Docker availability...
[2024-01-15 10:30:16] [SUCCESS] Docker is available
```
- Verifies Docker is running and accessible
- Checks Docker resource allocation
- Provides recommendations for optimal performance

### Step 2: Component Images Preparation
```
[2024-01-15 10:30:16] [INFO] Attempting to pull pre-built component images from DockerHub...
[2024-01-15 10:30:45] [SUCCESS] Pulled simnibs:v2.1.2
[2024-01-15 10:30:50] [SUCCESS] Pulled fsl:v6.0.7.18
[2024-01-15 10:30:55] [SUCCESS] Pulled freesurfer:v7.4.1
[2024-01-15 10:31:00] [SUCCESS] Pulled matlab:20th
```
- Pulls specialized Docker images from DockerHub:
  - **SimNIBS** (`idossha/simnibs:v2.1.2`) - For electromagnetic field simulations
  - **FSL** (`idossha/ti-toolbox_fsl:v6.0.7.18`) - For neuroimaging analysis
  - **FreeSurfer** (`idossha/ti-toolbox_freesurfer:v7.4.1`) - For brain surface reconstruction
  - **MATLAB Runtime** (`idossha/matlab:20th`) - For MATLAB-based computations
- Falls back to local building if DockerHub images are unavailable

### Step 3: CI Runner Image Build
```
[2024-01-15 10:31:00] [INFO] Building CI runner image...
[2024-01-15 10:35:30] [SUCCESS] CI runner image built successfully
```
- Builds the main CI runner image using `Dockerfile.ci`
- Installs Python dependencies, pytest, and BATS
- Copies the TI-Toolbox codebase into the container
- Sets up proper environment variables and paths

### Step 4: Test Environment Setup
```
[2024-01-15 10:35:30] [INFO] Setting up test directories...
[2024-01-15 10:35:31] [SUCCESS] Test directories created
```
- Creates test results directory (`/tmp/test-results`)
- Creates test project directory (`/tmp/test_projectdir`)
- Sets up proper permissions for Docker volume mounting

### Step 5: Unit Tests Execution
```
[2024-01-15 10:35:31] [INFO] Running analyzer unit tests...
[2024-01-15 10:36:45] [SUCCESS] Analyzer unit tests completed successfully
[2024-01-15 10:36:45] [INFO] Running simulator unit tests...
[2024-01-15 10:37:20] [SUCCESS] Simulator unit tests completed successfully
[2024-01-15 10:37:20] [INFO] Running flex-search unit tests...
[2024-01-15 10:37:35] [SUCCESS] Flex-search unit tests completed successfully
```
- **Analyzer Unit Tests**: Tests core analyzer functionality, mesh analysis, voxel analysis, and group analysis
- **Simulator Unit Tests**: Tests TI and multi-target TI simulation methods
- **Flex-Search Unit Tests**: Tests flexible search optimization algorithms
- Each test suite runs in isolated Docker containers with resource limits

### Step 6: Test Project Setup
```
[2024-01-15 10:37:35] [INFO] Setting up test project directory...
[2024-01-15 10:38:45] [SUCCESS] Test project directory setup completed
```
- Downloads ErnieExtended dataset from SimNIBS
- Creates BIDS-compliant project structure
- Sets up montage configurations for multiple EEG nets
- Downloads test simulation data
- Configures proper directory permissions

### Step 7: Integration Tests Execution
```
[2024-01-15 10:38:45] [INFO] Running simulator integration tests...
[2024-01-15 10:42:30] [SUCCESS] Simulator integration tests completed successfully
[2024-01-15 10:42:30] [INFO] Running analyzer integration tests...
[2024-01-15 10:45:15] [SUCCESS] Analyzer integration tests completed successfully
[2024-01-15 10:45:15] [INFO] Running BATS integration tests...
[2024-01-15 10:46:00] [SUCCESS] BATS integration tests completed successfully
```
- **Simulator Integration**: Runs complete simulation workflows with real data
- **Analyzer Integration**: Executes full analysis pipelines
- **BATS Validation**: Validates output files and results using automated testing

### Step 8: Results Summary
The script provides a comprehensive summary with:
- Individual test results with timing
- Success/failure rates for unit and integration tests
- Overall test suite status
- Location of test artifacts and reports

Example output:
```
========================================
COMPREHENSIVE TEST RESULTS SUMMARY
========================================

[2025-10-15 20:11:04] [INFO] Total execution time: 31:23

UNIT TESTS SUMMARY
==================
✓ Analyzer Unit Tests     [00:07] - 157/157 (100%)
✓ Simulator Unit Tests    [00:01] - 3/3 (100%)
✓ Flex-Search Unit Tests  [00:01] - 4/4 (100%)

UNIT TESTS: ALL PASSED (3/3 - 100%)

INTEGRATION TESTS SUMMARY
============================
✓ Test Project Setup      [12:42] - SUCCESS
✓ Simulator Integration   [18:00] - SUCCESS
✓ Analyzer Integration    [00:31] - SUCCESS
✓ BATS Validation Tests   [00:01] - SUCCESS

INTEGRATION TESTS: ALL PASSED (4/4 - 100%)

OVERALL SUMMARY
=================
ALL TESTS PASSED! (7/7 - 100%)
TI-Toolbox is ready for use!

Test Artifacts:
   Results Directory: /tmp/test-results
   Project Directory: /tmp/test_projectdir

   Unit Test Reports:
     - analyzer.xml
     - flex_search.xml
     - simulator.xml
   Integration Test Reports:
     - _finished_integration.txt
     - bats_analyzer.txt
     - bats_simulator.txt
```

## How to Read the Output

### Timestamped Progress
Every log message includes a timestamp in the format `[YYYY-MM-DD HH:MM:SS]`:
```
[2024-01-15 10:30:15] [INFO] Starting TI-Toolbox loader test process...
[2024-01-15 10:30:16] [SUCCESS] Docker is available
```

### Color-Coded Status Messages
- **[INFO]** - General information and progress updates
- **[SUCCESS]** - Successful operations and completions
- **[WARNING]** - Non-critical issues or recommendations
- **[ERROR]** - Critical failures that stop execution

### Step Headers
Each major phase is clearly marked:
```
========================================
Step 5: Unit Tests Execution
========================================
```

### Comprehensive Results Summary
The final summary provides detailed information:

#### Unit Tests Summary
```
UNIT TESTS SUMMARY
==================
✓ Analyzer Unit Tests     [01:14] - 45/45 (100%)
✓ Simulator Unit Tests    [00:35] - 23/23 (100%)
✓ Flex-Search Unit Tests  [00:15] - 12/12 (100%)

UNIT TESTS: ALL PASSED (3/3 - 100%)
```

#### Integration Tests Summary
```
INTEGRATION TESTS SUMMARY
============================
✓ Test Project Setup      [01:10] - SUCCESS
✓ Simulator Integration   [03:45] - SUCCESS
✓ Analyzer Integration    [02:45] - SUCCESS
✓ BATS Validation Tests   [00:45] - SUCCESS

INTEGRATION TESTS: ALL PASSED (4/4 - 100%)
```

#### Overall Summary
```
OVERALL SUMMARY
=================
ALL TESTS PASSED! (7/7 - 100%)
TI-Toolbox is ready for use!
```

### Understanding Test Results

#### Success Indicators
- **✓** - Test passed successfully
- **ALL PASSED** - All tests in category passed
- **TI-Toolbox is ready for use!** - System ready for use

#### Failure Indicators
- **✗** - Test failed
- **PASSED (X%) - Y FAILED** - Some tests failed, review needed
- **Please review failed tests and fix issues before proceeding.** - Action required to fix issues

#### Timing Information
- **`[MM:SS]`** - Duration of each test phase
- **Total execution time** - Complete test suite runtime

#### Success Rates
- **`X/Y (Z%)`** - X tests passed out of Y total (Z% success rate)
- **`X/Y PASSED (Z%) - W FAILED`** - Detailed breakdown with failure count

## Usage Examples

### Basic Usage
```bash
# Run with default settings (pull from DockerHub)
bash development/bash_dev/run_tests.sh
```

### Build Images Locally
```bash
# Build all images locally instead of pulling from DockerHub
bash development/bash_dev/run_tests.sh --build-local
```

### Clean Up Test Files and Containers
```bash
# Remove test directories, stop containers, and exit
bash development/bash_dev/run_tests.sh --cleanup
```

### Get Help
```bash
# Show usage information and options
bash development/bash_dev/run_tests.sh --help
```

## Environment Variables

- **`USE_DOCKERHUB_IMAGES`** - Set to `false` to build images locally (default: `true`)
- **`SKIP_COMPONENT_IMAGES`** - Set to `true` to skip component image preparation (default: `false`)

## Troubleshooting

### Common Issues

#### SIGBUS (Bus Error)
If you encounter bus errors during test execution:
1. Increase Docker Desktop memory allocation to at least 4GB
2. Ensure at least 5GB free disk space
3. Close other resource-intensive applications
4. Try running with `--build-local` if DockerHub images are corrupted

#### Permission Errors
Permission errors in WSL environments are handled gracefully:
```
[WARNING] Could not set permissions on /tmp/test-results (this is usually fine)
```
These warnings are non-critical and the script will continue.

#### Docker Resource Issues
The script includes built-in resource management:
- Memory limits: 4GB per container
- CPU limits: 2 cores per container
- File descriptor limits: 65536
- Process limits: 32768

### Windows Users
- Run the script in WSL2 or Git Bash
- Ensure Docker Desktop is running with WSL2 backend
- Check that Docker Desktop has sufficient resources allocated

## Test Artifacts

After successful execution, test artifacts are available in:

- **`/tmp/test-results/`** - Contains all test reports and results
  - `analyzer.xml` - Analyzer unit test results (JUnit format)
  - `simulator.xml` - Simulator unit test results (JUnit format)
  - `flex_search.xml` - Flex-search unit test results (JUnit format)
  - `bats_simulator.txt` - Simulator integration test output
  - `bats_analyzer.txt` - Analyzer integration test output
  - `_finished_integration.txt` - Integration completion marker

- **`/tmp/test_projectdir/`** - Contains the test project with:
  - BIDS-compliant directory structure
  - ErnieExtended dataset
  - Test simulation data
  - Montage configurations

The script output will show:
```
Test Artifacts:
   Results Directory: /tmp/test-results
   Project Directory: /tmp/test_projectdir

   Unit Test Reports:
     - analyzer.xml
     - flex_search.xml
     - simulator.xml
   Integration Test Reports:
     - _finished_integration.txt
     - bats_analyzer.txt
     - bats_simulator.txt
```

## Integration with Development Workflow

### Pre-commit Testing
Run the script before committing changes:
```bash
bash development/bash_dev/run_tests.sh
```

### CI/CD Validation
The script ensures that local testing matches CI testing, preventing:
- Environment-specific failures
- Missing dependencies
- Configuration mismatches

### Debugging Failed Tests
When tests fail, the detailed output helps identify:
- Which specific test failed
- How long each phase took
- Resource allocation issues
- Environment problems

## Container Management

The script includes comprehensive container management to ensure clean execution:

### Automatic Cleanup
- **All containers are labeled** with `ti-toolbox-test` for easy identification
- **Automatic cleanup** occurs when the script ends successfully
- **Interruption handling** - Containers are cleaned up if the script is interrupted (Ctrl+C)
- **Pre-run cleanup** - Existing test containers are cleaned up before starting

### Container Labels
Each test container is labeled for easy identification:
- `ti-toolbox-test=analyzer-unit` - Analyzer unit tests
- `ti-toolbox-test=simulator-unit` - Simulator unit tests  
- `ti-toolbox-test=flex-search-unit` - Flex-search unit tests
- `ti-toolbox-test=project-setup` - Test project setup
- `ti-toolbox-test=simulator-integration` - Simulator integration tests
- `ti-toolbox-test=analyzer-integration` - Analyzer integration tests
- `ti-toolbox-test=bats-validation` - BATS validation tests

### Manual Cleanup
If you need to manually clean up containers:
```bash
# Clean up all test containers and files
bash development/bash_dev/run_tests.sh --cleanup

# Or manually remove test containers
docker ps -aq --filter "label=ti-toolbox-test" | xargs docker rm -f
```

## Best Practices

1. **Run regularly** - Execute the script frequently during development
2. **Check resources** - Ensure adequate Docker memory and disk space
3. **Review output** - Pay attention to warnings and timing information
4. **Clean up** - Use `--cleanup` to remove test artifacts when done
5. **Use local builds** - Use `--build-local` when DockerHub is unavailable
6. **Monitor containers** - The script automatically manages containers, but you can check with `docker ps`

The `run_tests.sh` script is an essential tool for maintaining code quality and ensuring the reliability of the TI-Toolbox. It provides developers with confidence that their changes will pass CI testing and maintains consistency between local and remote testing environments.
