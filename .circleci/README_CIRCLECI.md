# CircleCI Configuration for TI-Toolbox

## Overview

TI-Toolbox uses CircleCI for continuous integration testing on all branches. The pipeline uses the **same SimNIBS Docker image** that developers use locally, ensuring complete parity between local and CI testing.

## How It Works

### 1. **Trigger**
- Automatically runs on every push to any branch
- Covers both PRs and main branch (for Codecov trend tracking)

### 2. **Image**
- **Uses:** `idossha/ti-toolbox-test:latest`
- **Contains:** SimNIBS 4.5, pytest, pytest-cov, all testing tools
- **Static:** Only rebuilt when dependencies change

### 3. **Testing**
- Checks out branch code
- Mounts code into SimNIBS container
- Runs: `./tests/run_tests.sh --verbose --coverage`
- **545 unit tests** covering all modules

### 4. **Coverage**
- Coverage report uploaded to Codecov via `codecov-cli`
- Component-level flags for core, simulator, analyzer, optimizer, stats, etc.
- PR comments show coverage diff

### 5. **Results**
- Test artifacts stored in CircleCI
- JUnit XML results for CircleCI test insights
- Pass/fail status visible on GitHub PR

## Developer Workflow

```
1. Make changes locally
2. Test locally:  ./tests/test.sh --verbose --coverage
3. Commit and push
4. CircleCI runs automatically
5. Codecov reports coverage on PR
```

## Test Execution in CI

```bash
# Host (CircleCI VM) runs:
TEST_IMAGE=ti-test:latest bash ./tests/test.sh --verbose --coverage

# test.sh mounts repo into container and calls:
./tests/run_tests.sh --verbose --coverage

# run_tests.sh runs inside Docker:
pip install -e /ti-toolbox
python -m pytest -v --cov=tit --cov-report=xml:/tmp/coverage/coverage.xml --junitxml=/tmp/test-results/results.xml
```

## What Gets Tested

- **545 unit tests** across 22 test files (~0.5s locally)
- Modules: calc, logger, paths, constants, errors, config_io
- Simulation: config, utils, TI pipeline, mTI pipeline
- Optimization: config, manifest
- Analyzer: full coverage including group analysis
- Statistics: config, CSV loaders
- Preprocessing: structural pipeline
- Reporting: assembler + all reportlets
- Atlas, scripts, GUI imports, integration

## Configuration Files

| File | Purpose |
|------|---------|
| `.circleci/config.yml` | CircleCI pipeline definition |
| `codecov.yml` | Codecov coverage thresholds and flags |
| `pytest.ini` | Pytest configuration and markers |
| `tests/test.sh` | Host-side Docker wrapper |
| `tests/run_tests.sh` | In-container test runner |
| `tests/conftest.py` | Shared fixtures and dependency mocks |

## Rebuilding the Test Image

**When to rebuild:**
- SimNIBS version update
- System dependencies change
- Testing tools update (pytest, pytest-cov)
- Python packages update

**Do NOT rebuild for:**
- TI-Toolbox code changes (mounted at runtime)

```bash
docker build -f development/blueprint/Dockerfile.test -t idossha/ti-toolbox-test:latest .
docker push idossha/ti-toolbox-test:latest
```

## Troubleshooting

### Tests Pass Locally but Fail in CI
Both use the same image and scripts, so this is unlikely. If it happens:
1. Check CircleCI logs
2. Verify SimNIBS image version matches
3. Look for environment-specific issues

### Missing `pytest-cov` in Docker Image
If `--coverage` fails, the test image needs `pytest-cov` installed. Rebuild with it included.
