# TI-Toolbox Testing Guide

Complete guide for running tests locally and in CI/CD.

---

## Quick Start

### **From Your Host Machine** (Recommended)

```bash
# Run all tests with your local code
./tests/test.sh

# Run only unit tests (fast)
./tests/test.sh --unit-only

# Run with verbose output
./tests/test.sh --verbose
```

**What it does:**
- Uses TI-Toolbox test image (`idossha/ti-toolbox-test:latest`)
- Image contains SimNIBS 4.5 + pytest + BATS + all testing tools
- Mounts your local code into the container
- Tests your current changes (not code from GitHub)
- Runs all tests: unit + integration

---

### **Inside Docker Container** (If Already Running)

```bash
# Inside the SimNIBS container
cd /workspace  # or wherever your code is

# Run all tests
./tests/run_tests.sh

# Run only unit tests
./tests/run_tests.sh --unit-only
```

---

## The Two Scripts

| Script | Where | Purpose |
|--------|-------|---------|
| **`test.sh`** | Host machine | Wrapper that starts Docker and runs tests |
| **`run_tests.sh`** | Inside container | Core test runner (called by test.sh and CI) |

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
- You're already inside the SimNIBS container
- Running in CI/CD
- Developing inside the container

---

## Test Types

### Unit Tests (~2 minutes)
- **Analyzer** (157 tests): Analysis algorithms, data processing
- **Simulator** (3 tests): Simulation parameter handling  
- **Flex-Search** (4 tests): Optimization algorithms

**Total: 164 tests**

**Requirements:** Python, pytest, numpy, scipy, pandas, nibabel, matplotlib
(All included in SimNIBS image)

### Integration Tests (~15-20 minutes)
- **Test Project Setup**: Downloads test data (ErnieExtended from OSF)
- **Simulator Integration**: Runs actual electromagnetic simulations
- **Analyzer Integration**: Runs complete analysis pipelines
- **Output Validation**: BATS tests verify file structure

**Requirements:** SimNIBS, FreeSurfer, BATS
(All included in SimNIBS image)

---

## CI/CD (CircleCI)

### Automatic Testing
- **Triggers:** Every pull request to `main` branch
- **Image:** `idossha/ti-toolbox-test:latest` (static test image)
- **Contains:** SimNIBS 4.5 + pytest + BATS + testing tools
- **Tests:** ALL tests (unit + integration)
- **Duration:** ~20-25 minutes

### What CircleCI Runs

```yaml
# Pulls test image (SimNIBS + testing tools)
docker pull idossha/ti-toolbox-test:latest

# Mounts PR code and runs tests
docker run -v ${WORKSPACE}:/workspace ti-test:latest \
  bash -c './tests/run_tests.sh --verbose'
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
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 2. Test locally                     │
│    ./tests/test.sh --unit-only     │
└─────────────────────────────────────┘
                 ↓
           ✓ Tests pass?
                 ↓
┌─────────────────────────────────────┐
│ 3. Full test before committing     │
│    ./tests/test.sh --verbose       │
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
# Quick validation (fast)
./tests/test.sh --unit-only

# Before each commit
./tests/test.sh --verbose
```

### Before Creating PR
```bash
# Full test suite
./tests/test.sh

# Ensure all tests pass
# Then push to GitHub
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

### Local Testing
```bash
./tests/test.sh              # Full test suite
./tests/test.sh --unit-only  # Fast unit tests
./tests/test.sh --verbose    # With detailed output
```

### Inside Container
```bash
./tests/run_tests.sh         # Full test suite
./tests/run_tests.sh --unit-only  # Fast unit tests
```

### CI/CD
- Automatic on every PR
- Uses same scripts and image as local
- Full test coverage

**Key Principle:** If tests pass locally, they'll pass in CI! 🎯

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
