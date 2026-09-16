# Shell test runners

[docs/dev/TESTING.md](../docs/dev/TESTING.md) owns the test strategy, the gate commands and the
known gaps. This file covers only the two shell runners that live in this directory.

The host wrapper `tests/test.sh`, the BATS suites and `container/blueprint/Dockerfile.test` were
removed with the v2 tree; the `idossha/ti-toolbox-test:latest` image is now pulled, not built here
(see `.circleci/config.yml`).

## `tests/run_tests.sh`

Runs **inside** a container that has the checkout mounted at `/ti-toolbox`. It installs
`/ti-toolbox[test]` into `simnibs_python` and runs pytest against the real scientific libraries.

```bash
docker exec -w /ti-toolbox <container> tests/run_tests.sh [--verbose] [--coverage] [pytest args…]
```

`--coverage` writes `/tmp/coverage/coverage.xml`.

On the host, where the heavy libraries are mocked by `tests/conftest.py`, run pytest directly:

```bash
python3 -m pytest tests/ -q
```

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
