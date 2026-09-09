# Testing strategy and evidence

[CONTRIBUTING](../../CONTRIBUTING.md) owns setup and workflow; [ARCHITECTURE](ARCHITECTURE.md)
owns behavior, [BENCHMARKS](BENCHMARKS.md) performance, and [ROADMAP](ROADMAP.md) remaining
acceptance work. This file owns test layers, fixtures, commands and verification limits.

## Strategy

Run the smallest meaningful regression checks during implementation and the full gate for a release
candidate. A full gate includes desktop static/unit tests, host Python, real-library numerical tests,
repository guards, hidden mock e2e, relevant real-container workflows and a final normal build.
Workflow or packaging changes add their specialized checks. Report numbers, skips and unrun legs;
a local success does not establish hosted CI, security review or artifact acceptance.

| Layer | What it proves | What it cannot prove |
|---|---|---|
| Desktop units and static checks | UI/state logic, types, lint | Actual drawing, native shell or scientific execution |
| Host pytest | API, jobs, config, path logic with controlled fixtures | SimNIBS and other mocked library behavior |
| Container numerical tests | Independent numerical claims against real libraries | A complete production workflow unless explicitly executed |
| Mock Electron e2e | Integrated UI requests, layout/pixels, interaction | Real server/scientific outputs |
| Real e2e and smoke matrix | Actual container/API jobs and produced artifacts | Other datasets/platforms, or completion when only start/cancel ran |
| Packaged acceptance | Runtime assets and actual installer launch | A different source/image/package pairing |

## Commands

Run from the repository root unless a command says otherwise. Use the host environment installed
by CONTRIBUTING. `tests/conftest.py` mocks SimNIBS, Blender and several scientific/plotting packages;
NumPy is real and some tests restore SciPy. Never infer real-library success from a host run.

```bash
.venv/bin/python -m pytest tests/ -q
cd desktop
npm run typecheck
npm run lint
npx vitest run
```

In an existing development/test container with this checkout mounted:

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

`tests/numerical/conftest.py` restores real libraries and reloads tested modules. Changes to the
scientific core require independent numerical coverage; use authored fixtures/reference calculations,
not expected values copied from the implementation. A real-library test with stubbed FEM is an
interface test, not a completed simulation. Published-output changes also need release-note guidance.

Repository guards:

```bash
python3 dev/route_import_guard.py
python3 dev/contracts_check.py
```

The import guard prevents heavy scientific imports during route registration. The contract guard
regenerates outputs in a temporary directory and checks byte drift against the authored contract.
Fix drift with `cd desktop && npm run gen`; never hand-edit generated output. Contract warnings
must be reported rather than counted as zero.

### Hidden end-to-end tests

Serialize every Playwright run under the shared `/tmp/tit-e2e.lock` and coordinate build ownership;
its mock server port and `desktop/out/` are shared. Do not start another build/test workload beside
measurement-sensitive GUI tests. The quiet-check wrapper monitors visibility; the caller must still
coordinate the shared lock. Never kill all Playwright processes to recover one run.

```bash
cd desktop
TIT_E2E_OFFSCREEN=1 npm run e2e:quiet
```

For a selected real spec against an existing container, set the copied dataset, server and session
credentials in the process environment (never commit or print the token):

```bash
TIT_E2E_PROJECT_HOST=/absolute/path/to/copied/project \
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/<spec>.spec.ts
```

Use `--project=real`: the space form can consume the spec path as another project. Do not use
`npm run e2e` for real-server runs, because its prehook rebuilds the shared output. Build scene
hooks before scene specs (`npm run pree2e` includes both gallery and scene hooks); a narrower real
scene build can use `VITE_SCENE_HOOKS=1 npx electron-vite build`. Gallery tests also need
`VITE_INCLUDE_GALLERY=1`. `electron-vite build --mode` does not make `import.meta.env.DEV` true.
Restore `npm run build` after tests so the shared server no longer serves the hook-enabled bundle.

A quiet monitor exit 2 is inconclusive, not a pass. Keep functional assertions and native
visibility/focus certification separate. Do not rerun solely to replace unresolved shared-host
process attribution with a more convenient result.

### Real-container smoke tests

Use a copied representative BIDS project; never substitute a maintainer dataset for destructive
fixtures. [dev/smoke.sh](../../dev/smoke.sh) drives `tests/smoke/` through HTTP:

```bash
dev/smoke.sh --list
dev/smoke.sh <row-id-or-kind>
dev/smoke.sh
dev/smoke.sh --full <row>
```

Select `TIT_SMOKE_CONTAINER` when multiple stacks exist. Heavy rows wait for an idle queue; never
run competing FEM jobs under emulation. Fresh output namespaces and cleanup manifests live under
`tests/smoke/artifacts/`; `--keep` preserves generated artifacts. State whether each check completed
computation or only tested start/cancel. Real UI specs can record payloads for replay.

Before restarting a backend, inspect running/queued jobs. After reload, wait for health and probe
behavior proving the new source loaded; immediate health may still come from the old process.
Recreating changes the token. Neither restart nor recreation is safe for active jobs by default.

### Workflows, packages and final build

```bash
actionlint                                  # when workflows change
cd desktop && npm run verify:package        # after creating the package under test
cd desktop && npm run build                 # final frontend step
```

Artifact construction and signed/internal publication are in [RELEASING](RELEASING.md). A package
validator checks bundled content; actual first-launch acceptance must use the distributed pairing
without source/UI mounts. A later source fix invalidates claims based only on an earlier image.

## Fixtures and failure diagnosis

- Use deterministic synthetic fixtures and assert observable behavior. Real paths and symlinks need
  Linux/container checks; case-insensitive host results are insufficient.
- Use `tests/numerical/` for real SciPy/SimNIBS claims. Full scientific jobs use the smoke harness or
  real e2e with a copied project; numerical unit success is not equivalent to a completed FEM run.
- `tests/test_blender_process_boundary.py` enables real Blender through `TIT_TEST_BLENDER_BIN`.
  Report its skip when the executable is unavailable. Validate export and reopen separately from
  scientific-environment imports.
- An isolated `tests/test_scene_guide.py` pass diagnoses order-dependent state leakage; it never
  waives a failed full suite. Scope mock changes so subsequent tests restore real module state.
- `docs-shots.spec.ts` rewrites tracked screenshots. Use it only when that output is intended;
  review generated changes rather than treating a passing capture as permission to replace images.
- Existing seeded project notebooks do not automatically update when the template changes. Use a
  fresh fixture or deliberately migrate the example when testing a repaired template.
- The older [test-script reference](../../tests/README_TESTING.md) documents shell runner options;
  it does not replace these desktop, numerical and artifact acceptance layers.

## Recorded verification and remaining gaps — 2026-09-09

These dated observations are retained for scope, not presented as fresh checks of later edits.
Local `/tmp` and ignored `dist/internal/` receipts may expire; committed suites above are the
reproduction surface. Keep only results that close a milestone or explain a remaining gap.

### Development closeout checks — 2026-09-09

The clean internal image from source `b06b4493bea5aa4834c107fe60301fcd9075afe1` was
`sha256:01d66ed257f0341f8467e31e9cd4d1dc3197cefb448812ded00e05931fffa5b6`.
Its selected baked numerical/boundary/Blender run passed 223 tests with one skip; the functional
mock suite passed 364 with one skip. Receipts: `dist/internal/baked-develop-tests.log` and
`mock-e2e-current-contract.log`. Later source/UI changes are not certified by that image.

### Clean baked candidate progress — 2026-09-09

The earlier `e3bee214` image's real run passed 42 tests and excluded docs-shots, scene-atlas-border
and scene-electrodes. Subsequent security fixes make it historical evidence only. The native
monitor exited 2 despite no attributed test-descendant failure. Receipt:
`dist/internal/real-final-baked-receipt.json`. A subsequent packaged Browse → Start repaired the
missing YAML dependency but paired a dirty-source app with an earlier image; final installer
acceptance remains separate.

| Latest scoped check | Recorded result / evidence |
|---|---|
| Host suite before subsequent UI/dev changes | 4,788 passed, 46 skipped, 21 deselected; `/tmp/tit-loader-host-tests.log` |
| Forms/mapping/folder desktop units | 1,568 passed / 123 files; `/tmp/tit-touchup-final-unit.log` |
| Dev attach regression suites | 98 Python and 66 desktop checks passed; live `pnpm dev:web` verified actual checkout/import identity and healthy proxy |
| Overwrite integration | 221 passed; `/tmp/tit-overwrite-integrated.log`; temporary outputs only |
| Real SESSION overwrite guard | 1 passed, FEM stubbed; `tests/numerical/test_sim_overwrite.py`; no full simulation claim |
| Overwrite UI | 44 focused units, 7 selection e2e, final rerun/policy follow-up 17 passed; native monitor exit 2 remained inconclusive |
| Route/contract guards | 24 route modules; 114 operations / 136 schemas, 244 existing contract warnings |
| Plugin process/tools | Three offline process tests; 14 tools / 15 selftest calls; no full native-client conversation claim |
| Montage image regression | 17 container tests including real PNG pixels and atomic failure; `/tmp/tit-montage-container-tests.log` |

No local result clears hosted security alerts, certifies another artifact revision or establishes
publication. Outstanding platform/security/manual gates live in [ROADMAP](ROADMAP.md).
