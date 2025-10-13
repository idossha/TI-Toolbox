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

- **Automatically triggers** on every push to the main branch
- **Builds Docker images** with all necessary dependencies
- **Runs comprehensive test suites** including unit and integration tests
- **Provides detailed reports** on test results and code coverage
- **Ensures consistency** across different environments

## Pipeline Configuration

The testing pipeline is configured in `.circleci/config.yml` and consists of:

### Parameters
- `use_dockerhub_images`: Pulls pre-built images from DockerHub (default: true)

### Executors
- **vm-docker**: Uses Ubuntu 22.04 with Docker layer caching disabled for consistent builds

### Key Components

#### 1. Component Images
The pipeline builds or pulls several specialized Docker images:

- **SimNIBS** (`idossha/simnibs:v2.1.2`): For electromagnetic field simulations
- **FSL** (`idossha/ti-toolbox_fsl:v6.0.7.18`): For neuroimaging analysis
- **FreeSurfer** (`idossha/ti-toolbox_freesurfer:v7.4.1`): For brain surface reconstruction
- **MATLAB Runtime** (`idossha/matlab:20th`): For MATLAB-based computations
- **CI Runner** (`ci-runner:latest`): Custom image containing the TI-Toolbox and test environment

#### 2. Test Execution Strategy
The pipeline uses a two-phase approach:

**Phase 1: Unit Tests**
- Analyzer unit tests
- Simulator unit tests  
- Flex-search unit tests

**Phase 2: Integration Tests**
- Full end-to-end simulation workflows
- Complete analysis pipelines
- Output validation using BATS (Bash Automated Testing System)

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

### 1. Environment Setup
```bash
# Pull or build component images
docker pull idossha/simnibs:v2.1.2
docker pull idossha/ti-toolbox_fsl:v6.0.7.18
# ... other images

# Build CI runner with TI-Toolbox
docker build -f development/blueprint/Dockerfile.ci -t ci-runner:latest .
```

### 2. Unit Test Execution
```bash
# Analyzer tests
pytest tests/test_analyzer.py tests/test_mesh_analyzer.py tests/test_voxel_analyzer.py tests/test_group_analyzer.py

# Simulator tests  
pytest tests/test_ti_simulator.py tests/test_mti_simulator.py

# Flex-search tests
pytest tests/test_flex_search.py
```

### 3. Integration Test Execution
```bash
# Setup test environment
bash tests/setup_test_projectdir.sh

# Run simulation pipeline
bash tests/test_simulator_runner.sh

# Run analysis pipeline
bash tests/test_analyzer_runner.sh

# Validate outputs
bats tests/test_simulator_outputs.bats
bats tests/test_analyzer_outputs.bats
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

The pipeline collects and stores test artifacts(within the runner):

- **analyzer-results/**: Unit test results for analyzer components
- **simulator-results/**: Unit test results for simulator components  
- **flexsearch-results/**: Unit test results for flex-search components
- **integration-results/**: Integration test outputs and validation results

### Common Issues
1. **Docker image availability**: Falls back to local builds if DockerHub images unavailable
2. **Test data downloads**: Handles network issues gracefully
3. **Permission problems**: Ensures proper file permissions in test environment
