# TI-Toolbox Testing Guide

Complete guide for running tests locally and in CI/CD.

---

## Quick Start

### **From Your Host Machine** (Recommended for Local Development)

```bash
# Run all tests with your local code
./tests/test.sh

# Run all tests and generate coverage.xml (written to repo root)
./tests/test.sh --coverage

# Run only unit tests (fast)
./tests/test.sh --unit-only

# Run with verbose output
./tests/test.sh --verbose
```

**What it does:**
- Uses TI-Toolbox test image (`idossha/ti-toolbox-test:latest`), built from `container/blueprint/Dockerfile.test`
- Image contains SimNIBS + pytest + BATS + all testing tools
- The image also bakes in ErnieExtended and `test_montage` data, copied at runtime to `/mnt/test_projectdir`
- Mounts your local code into the container at `/ti-toolbox`
- Tests your current changes (not code from GitHub)
- Runs all tests: unit + integration

**⚠️ Important:** Integration tests require the Docker container environment. Do NOT run `./tests/test_simulator_runner.sh` or `./tests/test_analyzer_runner.sh` directly on your host machine - they will fail. Always use `./tests/test.sh` which handles the Docker setup automatically.

---

### **Inside Docker Container** (Advanced - For Development Container Users)

If you're already working inside the development Docker container:

```bash
# Inside the development container
cd /development  # or wherever your code is mounted

# Run all tests
./tests/run_tests.sh

# Run only unit tests
./tests/run_tests.sh --unit-only
```

**Note:** This approach is for users who have their development environment running in Docker with code mounted at `/development`.

---

## The Two Scripts

| Script | Where | Purpose |
|--------|-------|---------|
| **`test.sh`** | Host machine | **PRIMARY SCRIPT** - Starts Docker, mounts local code, runs all tests |
| **`run_tests.sh`** | Inside container | Core test runner (called by test.sh and CI/CD) |

**For local development, always use `test.sh` from your host machine.**

---

## test.sh (Local Testing)

**Purpose:** Test your local changes from your host machine

```bash
./tests/test.sh [OPTIONS]
```

### Options
- `-h, --help` - Show help message
- `-u, --unit-only` - Run only unit tests (fast ~2 min)
- `-i, --integration-only` - Run only integration tests
- `-v, --verbose` - Show detailed output
- `-s, --skip-setup` - Skip test project setup
- `-n, --no-cleanup` - Keep test directories after tests

### Environment Variables
- `TEST_IMAGE` - Override test image (default: `idossha/ti-toolbox-test:latest`)

### Examples

```bash
# Quick unit tests
./tests/test.sh --unit-only

# Full test suite with verbose output
./tests/test.sh --verbose

# Use specific test image version
TEST_IMAGE=idossha/ti-toolbox-test:v1.0.0 ./tests/test.sh

# Run integration tests only (skip unit tests)
./tests/test.sh --integration-only
```

---

## run_tests.sh (Core Runner)

**Purpose:** Actually runs the tests (inside container)

**Used by:**
- `test.sh` (wraps this)
- CircleCI (calls directly)
- Manual testing inside container

```bash
./tests/run_tests.sh [OPTIONS]
```

### Options
Same as `test.sh` above

### When to use directly
- You're already inside a development Docker container (with code mounted at `/development`)
- Running in CI/CD pipeline (CircleCI)
- **NOT for running individual integration test scripts** - those require the full container environment

---

## Test Types

### Unit Tests (~2 minutes)
- **Analyzer** (157 tests): Analysis algorithms, data processing
- **Simulator** (3 tests): Simulation parameter handling  
- **Flex-Search** (4 tests): Optimization algorithms

**Total: 164 tests**

**Requirements:** Python, pytest, numpy, scipy, pandas, nibabel, matplotlib
(All included in SimNIBS image)

### Integration Tests
- **CI data checks**: `tests/test_ci_data_integration.py` runs only in the `Dockerfile.test` image, uses `/mnt/test_projectdir`, and calls real `simnibs_python` subprocesses so pytest's unit-test mocks are bypassed.
- **dcm2niix environment check**: verifies the real `dcm2niix` binary and fixture layout are available in the CI image.
- **Simulation artifact/report integration**: generates a report from pre-baked `ernie_extended/test_montage` SimNIBS outputs.
- **Analyzer integration**: runs voxel analysis on the pre-baked NIfTI outputs with the real nibabel/numpy stack.
- **Lightweight module-flow tests**: additional integration tests exercise orchestration with local fakes for fast host-side development.

**Requirements:** SimNIBS, test fixture data, FreeSurfer-related files, BATS
(All included in the `Dockerfile.test` image)

### Comprehensive Release-Gate Integration

The default CircleCI suite is intentionally fast and mostly validates wiring plus
pre-baked outputs. Before tagging a release, run the heavy computational entry
point:

```bash
tests/run_comprehensive_integration.sh --keep-work
```

This script uses only data available inside the testing environment. It uses the
same `idossha/ti-toolbox-test:latest` image built from
`container/blueprint/Dockerfile.test`, copies `/mnt/test_projectdir` to an
isolated work directory, sets `TIT_RUN_COMPREHENSIVE=1`, and runs:

1. real DICOM conversion through `dcm2niix`
2. real SimNIBS CHARM on the converted anatomical image
3. real TI simulation on the ErnieExtended fixture
4. real flex-search with the focality objective
5. real leadfield generation
6. real ex-search with a pooled six-electrode candidate set
7. real Analyzer runs in both mesh and voxel modes

Useful partial commands during debugging:

```bash
# Exercise simulation/optimization/analysis without DICOM or CHARM
tests/run_comprehensive_integration.sh --skip-dicom --skip-charm --keep-work

# Exercise DICOM + CHARM only, skipping later optimization phases
tests/run_comprehensive_integration.sh --skip-flex --skip-leadfield-ex --keep-work
```

`--dicom-source /path/to/dicoms` exists only as a debugging override. Clean
release-gate runs should not require host data outside the test image.

---

## CI/CD (CircleCI)

### Automatic Testing
- **Triggers:** Every pull request to `main` branch
- **Image:** `idossha/ti-toolbox-test:latest` (static test image built from `container/blueprint/Dockerfile.test`)
- **Contains:** SimNIBS, pytest, BATS, testing tools, and pre-baked ErnieExtended/test_montage data
- **Tests:** ALL tests (unit + integration)
- **Duration:** depends on Docker host and cache state

### What CircleCI Runs

```yaml
# Pulls test image (SimNIBS + testing tools + fixture data)
docker pull idossha/ti-toolbox-test:latest

# CircleCI uses the same host-side wrapper as local testing
TEST_IMAGE=ti-test:latest bash ./tests/test.sh --verbose --coverage
```

**Same image, same tests, same script as local testing!**

The test image is static and contains:
- SimNIBS 4.5
- pytest and BATS
- All system dependencies
- Your PR code is mounted at runtime

---

## Developer Workflow

```
┌─────────────────────────────────────┐
│ 1. Make changes to TI-Toolbox code │
│    (on your host machine)           │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 2. Test locally (from host)         │
│    ./tests/test.sh --unit-only      │
│                                     │
│    ✓ Docker pulls test image       │
│    ✓ Mounts your local code        │
│    ✓ Runs tests inside container   │
└─────────────────────────────────────┘
                 ↓
           ✓ Tests pass?
                 ↓
┌─────────────────────────────────────┐
│ 3. Full test before committing     │
│    ./tests/test.sh --verbose       │
│                                     │
│    ✓ Runs unit + integration tests │
│    ✓ Same environment as CI/CD     │
└─────────────────────────────────────┘
                 ↓
           ✓ Tests pass?
                 ↓
┌─────────────────────────────────────┐
│ 4. Commit and push                  │
│    git commit & push                │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 5. Create PR on GitHub              │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 6. CircleCI runs automatically      │
│    Same tests, same environment     │
└─────────────────────────────────────┘
                 ↓
           ✓ Tests pass?
                 ↓
┌─────────────────────────────────────┐
│ 7. Ready to merge!                  │
└─────────────────────────────────────┘
```

**⚠️ Important:** Always run tests from your host machine using `./tests/test.sh`. Do NOT run individual test runner scripts (`test_simulator_runner.sh`, `test_analyzer_runner.sh`) directly - they require the container environment.

---

## Troubleshooting

### "Docker is not running"
**Solution:** Start Docker Desktop

### "Test image not found"
**Solution:** Script will automatically pull it, or manually:
```bash
docker pull idossha/ti-toolbox-test:latest
```

### "Permission denied" on scripts
**Solution:** The test script automatically fixes this, but you can manually:
```bash
chmod +x CLI/*.sh tests/*.sh
```

### Tests pass locally but fail in CI
**Very unlikely now** - both use same image and scripts!

If it happens:
- Check CircleCI logs
- Ensure using same test image version
- Check for network issues (test data downloads)

### Integration tests fail
This is normal during development - integration tests catch real bugs!
- Check the error messages
- Fix bugs in TI-Toolbox code (not test infrastructure)
- Re-run tests

---

## Test Results & Artifacts

### Local Testing
- Results printed to console
- Use `--verbose` flag for detailed output
- Test data in `/tmp/test_projectdir` (cleaned up unless `--no-cleanup`)

### CI Testing
- Results on GitHub PR status
- Detailed logs in CircleCI dashboard
- Artifacts stored for 30 days

---

## Best Practices

### During Development
```bash
# Quick validation (fast, ~2 minutes)
./tests/test.sh --unit-only

# Before each commit (full suite, ~20 minutes)
./tests/test.sh --verbose
```

### Before Creating PR
```bash
# Full test suite with verbose output
./tests/test.sh --verbose

# Ensure all tests pass
# Then commit and push to GitHub
```

### ⚠️ Common Mistakes to Avoid

**DON'T run integration tests directly on host:**
```bash
# ❌ This will FAIL on macOS/Windows
./tests/test_simulator_runner.sh

# ❌ This will FAIL - missing SimNIBS
simnibs_python -m pytest tests/test_ti_simulator.py
```

**DO use the test wrapper:**
```bash
# ✅ This works correctly - mounts code into container
./tests/test.sh

# ✅ For unit tests only (faster during development)
./tests/test.sh --unit-only
```

### Adding New Tests
1. Create `test_*.py` file in `tests/` directory
2. Follow pytest conventions
3. Test locally: `./tests/test.sh`
4. Update this README if adding new categories

---

## Advanced Usage

### Run Specific Test File
```bash
# Inside container
cd /workspace
simnibs_python -m pytest tests/test_analyzer.py -v
```

### Keep Test Data for Inspection
```bash
./tests/test.sh --no-cleanup
# Test data remains in /tmp/test_projectdir
```

### Skip Test Setup (Reuse Existing Data)
```bash
./tests/test.sh --skip-setup
# Uses existing test project data
```

### Use Different Test Image Version
```bash
TEST_IMAGE=idossha/ti-toolbox-test:v1.0.0 ./tests/test.sh
```

### Run BATS Tests Directly
BATS (Bash Automated Testing System) tests validate output file structure and content:

```bash
# Run individual BATS test files
bats tests/test_simulator_outputs.bats
bats tests/test_analyzer_outputs.bats

# Run with verbose output
bats --verbose tests/test_simulator_outputs.bats

# Run specific test by name
bats --filter "Simulator outputs exist" tests/test_simulator_outputs.bats
```

**What BATS tests validate:**
- **Simulator outputs**: File structure, mesh files, field files, log files
- **Analyzer outputs**: Analysis directories, mesh analysis files, CSV outputs

---

## Summary

### Local Testing (PRIMARY METHOD)
```bash
./tests/test.sh              # Full test suite (~20 min)
./tests/test.sh --unit-only  # Fast unit tests (~2 min)
./tests/test.sh --verbose    # With detailed output
```

**✅ Always use `test.sh` from your host machine - it handles Docker automatically**

### Inside Development Container (ADVANCED)
```bash
./tests/run_tests.sh         # If already in dev container
./tests/run_tests.sh --unit-only  # Unit tests only
```

**⚠️ Only use this if you're working inside a Docker development container with code mounted at `/development`**

### CI/CD
- Automatic on every PR to `main`
- Uses same test image as local (`idossha/ti-toolbox-test:latest`)
- Mounts PR code and runs `run_tests.sh`
- Full test coverage (unit + integration)

**Key Principle:** If tests pass locally with `./tests/test.sh`, they'll pass in CI! 🎯

---

## Need Help?

- Use `--help` flag: `./tests/test.sh --help`
- Check logs with `--verbose` flag
- Ensure Docker is running
- Verify you're in TI-Toolbox root directory
- Check CircleCI dashboard for CI logs

---

## File Reference

- **`tests/test.sh`** - Local testing wrapper (run from host)
- **`tests/run_tests.sh`** - Core test runner (runs in container)
- **`tests/setup_test_projectdir.sh`** - Sets up test data
- **`tests/test_*_runner.sh`** - Integration test runners
- **`tests/test_*.bats`** - Output validation tests
- **`tests/test_*.py`** - Unit test files
