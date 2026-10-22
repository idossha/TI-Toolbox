# Shell test runners

[docs/dev/TESTING.md](../docs/dev/TESTING.md) owns the test strategy, the gate commands and the
known gaps. This file covers only the two shell runners that live in this directory.

The BATS suites and `container/blueprint/Dockerfile.test` were removed with the v2 tree. Three
files still belong to the retired `idossha/ti-toolbox-test:latest` image, which no CI job pulls any
more: `tests/test.sh` (the host wrapper that starts it), `tests/run_comprehensive_integration.sh`
(below) and `tests/test_ci_data_integration.py`, whose ten tests skip everywhere because only that
image had `/mnt/test_projectdir`.

## `tests/run_tests.sh`

Runs **inside** a container that has the checkout mounted at `/ti-toolbox`. It installs
`/ti-toolbox[test]` into `simnibs_python` and runs pytest against the real scientific libraries.

```bash
docker exec -w /ti-toolbox <container> tests/run_tests.sh [--verbose] [--coverage] [pytest args…]
```

`--coverage` writes `/tmp/coverage/coverage.xml`.

On the host, where the heavy libraries are mocked by `tests/conftest.py`, run pytest with the
contributor virtual environment and exclude the numerical suite:

```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/numerical
```

`tests/numerical/conftest.py` restores the real libraries, so numerical tests are a separate
leg rather than part of this mocked host run: CI runs its `host_numerical` modules on the host,
the nightly `numerical-image` job and `build-and-smoke-image` run the whole directory in the
image, and `dev/run_realdata_tests.sh` runs the Dataset 000 tests (docs/dev/TESTING.md, "Daily
CI and the local release gate").

## `tests/run_comprehensive_integration.sh`

The heavy release-gate pipeline — real DICOM conversion, CHARM, a simulation, flex focality, a
leadfield, ex-search and mesh/voxel analysis — run from the host against
`idossha/ti-toolbox-test:latest`, using only the data baked into that image.

```bash
tests/run_comprehensive_integration.sh [--keep-work]
```

It copies `/mnt/test_projectdir` into an isolated work directory and sets
`TIT_RUN_COMPREHENSIVE=1`. Expect a long run; never start two FEM simulations in parallel under
emulation.
