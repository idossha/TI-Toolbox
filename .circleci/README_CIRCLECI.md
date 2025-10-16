# CircleCI Configuration for TI-Toolbox

## Overview

The TI-Toolbox uses CircleCI for continuous integration testing on all pull requests. The pipeline uses the **same SimNIBS Docker image** that developers use locally, ensuring complete parity between local and CI testing.

## How It Works

### 1. **Trigger**
- Automatically runs on every pull request to `main` branch
- Does NOT run on direct commits to `main` or `master`
- This encourages proper PR workflow

### 2. **Image**
- **Uses:** `idossha/ti-toolbox-test:latest`
- **Contains:** SimNIBS 4.5, pytest, BATS, all testing tools
- **Static:** Only rebuilt when dependencies change
- **Same as:** What developers use locally for testing

### 3. **Testing**
- Checks out PR branch code
- Mounts PR code into SimNIBS container
- Runs: `./tests/run_tests.sh --verbose`
- **All tests run:** Unit tests + Integration tests

### 4. **Results**
- Test artifacts stored in CircleCI
- Pass/fail status visible on GitHub PR
- Detailed logs available in CircleCI dashboard

## Developer Workflow

```
┌─────────────────────────────────────────────────────┐
│ 1. Developer: Clone TI-Toolbox repo                │
│    git clone https://github.com/idossha/TI-Toolbox │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 2. Developer: Make changes locally                  │
│    - Edit code                                      │
│    - Add features                                   │
│    - Fix bugs                                       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 3. Developer: Test locally with SimNIBS            │
│    ./tests/test.sh                                  │
│                                                     │
│    ✓ Same environment as CI                        │
│    ✓ All tests (unit + integration)                │
│    ✓ Fast feedback                                 │
└─────────────────────────────────────────────────────┘
                        ↓
              ┌─────────────────┐
              │ Tests Pass? ✓   │
              └─────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 4. Developer: Commit and push                       │
│    git add .                                        │
│    git commit -m "Add new feature"                 │
│    git push origin feature-branch                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 5. Developer: Create PR on GitHub                   │
│    feature-branch → main                            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 6. CircleCI: Automatically triggered                │
│    - Pulls idossha/ti-toolbox-test:latest          │
│    - Checks out PR code                            │
│    - Mounts code into container                    │
│    - Copies TI-Toolbox extensions to SimNIBS      │
│    - Runs: ./tests/run_tests.sh                    │
└─────────────────────────────────────────────────────┘
                        ↓
              ┌─────────────────┐
              │ Tests Pass? ✓   │
              └─────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 7. Maintainer: Review and merge PR                  │
│    ✓ Tests passed                                   │
│    ✓ Code reviewed                                 │
│    ✓ Ready to merge                                │
└─────────────────────────────────────────────────────┘
```

## Key Benefits

### ✅ **Complete Parity**
- Local tests = CI tests
- Same Docker image
- Same test scripts
- Same results

### ✅ **Full Test Coverage**
- Unit tests (analyzer, simulator, flex-search)
- Integration tests (actual simulations)
- Output validation (BATS tests)
- Complete end-to-end testing

### ✅ **Fast Feedback**
- Test locally before pushing
- Know if PR will pass CI
- No surprises

### ✅ **Single Source of Truth**
- One Docker image (`ti-toolbox-test:latest`)
- One test script (`run_tests.sh`)
- Static image, code mounted at runtime
- Easy to maintain

## Configuration Details

### File: `.circleci/config.yml`

#### Executors
```yaml
vm-docker:
  machine:
    image: ubuntu-2204:current
    docker_layer_caching: false
```
Uses Ubuntu 22.04 VM with Docker support.

#### Commands

**`common-setup`**
- Checks out PR code from GitHub

**`prepare-test-image`**
- Pulls `idossha/ti-toolbox-test:latest` from Docker Hub
- Tags as `ti-test:latest`
- Image contains SimNIBS + testing tools (static)

#### Jobs

**`build-and-run-tests`**
1. Checks out PR code
2. Pulls test image (`ti-toolbox-test:latest`)
3. Creates test directories
4. Mounts PR code into container at `/ti-toolbox` (matches production)
5. Script copies TI-Toolbox extensions to SimNIBS
6. Runs `./tests/run_tests.sh --verbose`
7. Stores test artifacts

#### Workflows

**`pull_request_workflow`**
- Triggers on all branches **except** `main` and `master`
- Runs `build-and-run-tests` job

## Test Execution in CI

```bash
# What CircleCI runs:
docker run --rm \
  -v "${WORKSPACE}:/ti-toolbox" \             # PR code (matches production)
  -v /tmp/test_projectdir:/mnt/test_projectdir \  # Test data
  -v /tmp/test-results:/tmp/test-results \    # Results
  -w /ti-toolbox \                            # Working directory
  ti-test:latest \                            # Test image (SimNIBS + tools)
  bash -c './tests/run_tests.sh --verbose'

# Inside run_tests.sh:
# - Copies ElectrodeCaps_MNI from PR code to SimNIBS
# - Copies tes_flex_optimization from PR code to SimNIBS
# - Runs all tests
```

## What Gets Tested

### Unit Tests (~2 minutes)
- **Analyzer Tests** (157 tests)
  - Mesh analysis algorithms
  - Voxel analysis algorithms
  - Group analysis capabilities
  
- **Simulator Tests** (3 tests)
  - TI simulation parameters
  - Multi-target TI parameters
  
- **Flex-Search Tests** (4 tests)
  - Optimization algorithms

### Integration Tests (~15-20 minutes)
- **Test Project Setup**
  - Downloads ErnieExtended data from OSF
  - Creates BIDS-compliant structure
  
- **Simulator Integration**
  - Runs actual electromagnetic simulations
  - Tests montage configurations
  - Validates output files
  
- **Analyzer Integration**
  - Runs complete analysis pipelines
  - Tests spherical ROI analysis
  - Validates analysis outputs
  
- **BATS Validation**
  - Validates simulation output files exist
  - Validates analysis output files exist
  - Checks file structure

## Artifacts

Test results are stored as CircleCI artifacts:
- `/tmp/test-results/` - All test outputs
- Viewable in CircleCI dashboard
- Available for debugging

## Troubleshooting

### Tests Pass Locally but Fail in CI

**Unlikely now** - both use same image and scripts!

If it happens:
1. Check CircleCI logs for details
2. Verify SimNIBS image version matches
3. Check for network issues (OSF downloads)

### CI Takes Too Long

**Expected:** Full integration tests take ~20-25 minutes
- Pulling SimNIBS image: ~5 minutes (first time)
- Downloading test data: ~5 minutes
- Running simulations: ~10 minutes
- Analysis and validation: ~2-3 minutes

**Optimization options:**
- Use Docker layer caching (currently disabled for consistency)
- Cache test data downloads
- Run unit tests first, fail fast

### Rebuilding the Test Image

**When to rebuild:**
- SimNIBS version update (e.g., v4.5.0 → v4.6.0)
- System dependencies change (apt packages)
- Testing tools update (pytest, bats)
- Python packages update (numpy, scipy, etc.)

**Do NOT rebuild for:**
- TI-Toolbox code changes (mounted at runtime)
- ElectrodeCaps changes (copied from mounted code)
- tes_flex_optimization changes (copied from mounted code)

**To rebuild:**
```bash
docker login
docker build -f development/blueprint/Dockerfile.test -t idossha/ti-toolbox-test:latest .
docker push idossha/ti-toolbox-test:latest
```

CircleCI automatically uses the updated image on next PR.

## Comparison: Old vs New

### Old Approach
```
❌ Minimal CI image (Dockerfile.ci.min)
❌ Only unit tests in CI
❌ Integration tests skipped
❌ Different from local testing
❌ Multiple Docker images to maintain
❌ Image changed with every SimNIBS update
```

### New Approach (Current)
```
✅ Static test image (ti-toolbox-test:latest)
✅ All tests in CI (unit + integration)
✅ Complete test coverage
✅ Identical to local testing
✅ Single Docker image
✅ Code mounted at runtime (no rebuild for code changes)
✅ Only rebuild when dependencies change
✅ Simpler maintenance
```

## Maintenance

### Updating Tests
1. Add/modify tests in `tests/` directory
2. Test locally: `./tests/test.sh`
3. Push to PR
4. CI automatically runs same tests

### Updating Test Image
1. Modify `Dockerfile.test` (for dependency changes only)
2. Build: `docker build -f development/blueprint/Dockerfile.test -t idossha/ti-toolbox-test:latest .`
3. Push to Docker Hub: `docker push idossha/ti-toolbox-test:latest`
4. CircleCI automatically uses updated image
5. **Note:** No rebuild needed for TI-Toolbox code changes (mounted at runtime)

### Updating Test Scripts
1. Modify `tests/run_tests.sh` (core runner)
2. Test locally: `./tests/test.sh`
3. Push to PR
4. CI uses updated script automatically

## Performance Metrics

| Metric | Value |
|--------|-------|
| **Total CI Time** | ~20-25 minutes |
| **Image Pull** | ~5 minutes (cached after first run) |
| **Test Data Download** | ~5 minutes |
| **Unit Tests** | ~2 minutes |
| **Integration Tests** | ~15 minutes |
| **Docker Image Size** | ~15-20 GB |

## Cost Considerations

- **Compute:** ~25 minutes per PR
- **Storage:** Docker layer caching disabled (consistency > speed)
- **Network:** Pulls ~20GB image + test data per run

**Optimization:** Enable Docker layer caching if costs are a concern

## Summary

The new CircleCI setup provides **complete test coverage** with **perfect parity** between local and CI environments. Developers test with the exact same tools and scripts as CI, eliminating surprises and ensuring high code quality.

**Key Principle:** If it passes locally, it will pass in CI! 🎯

