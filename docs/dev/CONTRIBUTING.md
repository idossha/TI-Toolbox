# Contributing — how to develop, verify and record

The working manual for anyone (human or agent) writing code in this repository. Process for
outside contributors — branches, discussions, pull requests — is the top-level
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#1-choose-the-branch-and-pull-request-target).
Use `release/X.Y.Z` for stabilization and short-lived topic branches for changes; that policy
owns branch names and PR targets. Everything about *how the software is built and why* is
in this directory; start at [`README.md`](README.md).

---

## 1. The development environment

TI-Toolbox is three pieces: an **Electron app** on your host (`desktop/`), a **FastAPI server**
(`tit/server`) inside a Docker container, and the **`tit` science core** the server runs jobs from.
Use the real container with the current checkout for manual testing. The browser loop is the
simplest starting point; the desktop loop uses the same backend.

```bash
cd desktop
npm install                       # Electron is downloaded from GitHub on install
cp .env.dev.example .env.dev      # then set TIT_DEV_PROJECT_DIR to your BIDS project
npm run dev:web                   # container + live UI: http://127.0.0.1:5173/
# Or: npm run dev                 # same backend + Vite + Electron, already connected
npm run dev:down                  # stop and remove *this project's* container only
```

`pnpm dev:web` and `pnpm dev` run the same scripts if you use pnpm. Set
`TIT_DEV_IMAGE_TAG` in `.env.dev` to the image you have installed; inspect available tags with
`docker images idossha/ti-toolbox`. A missing local image must be built or obtained first.
Use `npm run dev:web -- --project /path/to/project` for a one-run project override.

**Which edits are live?** UI edits appear through Vite HMR. Python source is mounted from the
checkout you launch, with `/ti-toolbox` first on the Python import path. Changes to Python
dependencies, system packages or the container entrypoint still require an image rebuild;
a source mount cannot install those dependencies.

Development behavior:

- **There is no token to read, paste or export.** The Vite proxy (`desktop/scripts/devProxy.ts`)
  stamps `Authorization: Bearer <token>` and rewrites `Origin` on every proxied `/api`, `/auth` and
  `/ws` request. So the browser needs no cookie, no `?token=`, and no `TIT_DEV_ORIGINS` allowlist.
- **The worktree is bind-mounted, so Python is live.** With `TIT_DEV_MOUNT_REPO=1` (the default) the
  repository is mounted at `/ti-toolbox` with `PYTHONPATH=/ti-toolbox`, so an edit under `tit/sim`,
  `tit/opt`, `tit/analyzer`… is live for the *next job* with nothing to restart. The same flag sets
  `TIT_SERVER_RELOAD=1`, so an edit under `tit/server/**` or `tit/jobs/**` restarts the server on
  its own (the watch is scoped to `tit/`).
  Set `TIT_DEV_MOUNT_REPO=0` to test the image's baked-in `tit`, which is what a user gets.
- **The container also serves the *UI* from the worktree** (`desktop/out/renderer`). A stale or
  wrongly-flagged build is therefore what a real-server e2e run sees — see §2.5.
- **A recreate mints a new bearer token and kills in-flight jobs; a plain `docker restart` does
  not.** `npm run dev` refuses to recreate a container with jobs in flight and names them. Before
  restarting the server for a `tit/server/**` change, check `GET /api/jobs` is empty first
  (§2.6, "Restart rule").

`Ctrl-C` stops Vite and Electron and leaves the container running, so the next `npm run dev`
attaches after checking the container configuration. A stale checkout mount is a mismatch,
not a successful attach; an unreadable job list prevents automatic replacement.

**Without Node.** `dev/loader/loader_dev.py` (and `loader_dev.sh` beside it) start the same dev
container from Python alone — same options as the root `loader.py`, plus `--build`, `--image` and
`--web`. They are the developer's equivalents of the two user entry points at the repository root,
and they set exactly the three overrides in `dev/loader/docker-compose.dev.yml`: the worktree
mounted at `/ti-toolbox`, `TIT_SERVER_RELOAD=1`, and the locally built renderer. `--web` hands over
to `npm run dev:web` rather than reimplementing the loop, so there is still one implementation of
container + Vite + Electron. Prefer `python3 dev/loader/loader_dev.py --web` (or the Bash wrapper
with `--web`) for live UI edits. Without `--web`, run `npm --prefix desktop run build` first and
again after frontend edits: the Python-only path serves the built renderer, not Vite. It will
not silently substitute the image’s old UI when a local build is missing. The stack itself
is defined once, in the root `docker-compose.yml`.

---

## 2. The gate

Run checks appropriate to the changed behavior; run the full gate for a release candidate.
Report executed checks and failures explicitly. A local pass does not certify hosted CI or packaging.

### 2.1 Frontend static checks and units

```bash
cd desktop
npm run typecheck                 # tsc over tsconfig.node.json and tsconfig.web.json
npm run lint                      # eslint .
npx vitest run                    # unit suite
```

### 2.2 Python tests on the host

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest tests/ -q
```

An existing uv-managed environment can use `uv pip install --python .venv/bin/python -e '.[test]'`.
The `test` extra is host-only; it does not alter the container's SimNIBS dependency environment.

`tests/conftest.py` mocks SimNIBS, `bpy`, `matplotlib`, `scipy`, `nibabel`, `h5py`, `pandas`,
`joblib` and `nilearn`. NumPy is real, and several statistics tests explicitly restore SciPy;
the host therefore needs the `test` extra rather than only pytest. Real-library numerical and
SimNIBS checks still run in the container. Durations are recorded in BENCHMARKS.md.

If `tests/test_scene_guide.py` fails only in the full run, use an isolated run to diagnose
fixture or module-state leakage. An isolated pass does not turn a failing full suite green.

### 2.3 Numerical tests with the real libraries — in the container

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

`tests/numerical/` swaps the real `scipy`/`nibabel` back in and reloads the modules under test, so
it checks numerical claims such as cluster masses, permutation p-values and affine determinants.
Use it for changes to numerical behavior (§3).

### 2.4 Repository guards

```bash
python3 dev/route_import_guard.py     # no server route may import a heavy science module at import time
python3 dev/contracts_check.py        # contracts/generated/ is not stale, and the live app covers
                                      # contracts/openapi.yaml (contracts/README.md)
```

`contracts_check` regenerates every `contracts/generated/` output plus
`desktop/src/renderer/api/schema.d.ts` into a temp dir and fails on any byte of drift. If it does,
the fix is always the one regeneration command — never a hand-edit of a generated file:

```bash
cd desktop && npm run gen             # -> contracts/generated/*, src/renderer/api/schema.d.ts
```

### 2.5 End-to-end, offscreen, under the lock

```bash
cd desktop
TIT_E2E_OFFSCREEN=1 npm run e2e:quiet        # full mock suite, serial, offscreen
```

Then the real-server subset against your dev container:

```bash
TIT_E2E_PROJECT_HOST=/absolute/path/to/copied/project TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/<spec>.spec.ts
```

- **`--project=real`, not `--project real`.** Playwright's `--project` is variadic, so the space
  form swallows the spec path as a second, nonexistent project.
- **Never `npm run e2e` for a real-server run**: its `pree2e` hook force-rebuilds `out/` and races
  any other lane's build.
- **The three `scene-*` real specs need `VITE_SCENE_HOOKS=1 npx electron-vite build` first**, and a
  plain `npm run build` again afterwards. A plain build correctly strips `window.__scene` /
  `__scenePane` — `import.meta.env.DEV` is false for every `electron-vite build`, `--mode`
  notwithstanding — so without the flag those three specs time out 30 s later with no hint why:

  | Spec | Build flags |
  |---|---|
  | `tests/e2e/real/scene-{simulator,optimizer,analyzer}.spec.ts` | `VITE_SCENE_HOOKS=1` |
  | `tests/e2e/scene.spec.ts` (offscreen, mounts the gallery's scene page) | `VITE_INCLUDE_GALLERY=1 VITE_SCENE_HOOKS=1` |
  | `tests/e2e/gallery.spec.ts` | `VITE_INCLUDE_GALLERY=1` |
  | everything else | plain `npm run build` |

  `npm run e2e`'s `pree2e` hook sets both, which is why the default suite works untouched — and is
  still not what to use for a real-server run.
- E2E is **offscreen/headless by default on this machine**. `scripts/e2e-quiet-check.sh` proves no
  window reached the screen; report its PASS.

### 2.6 Real-container smoke tests

[`dev/smoke.sh`](../../dev/smoke.sh) drives HTTP tests in `tests/smoke/`; real Playwright
specs can record the same payloads for replay. Use a copied representative project.

```bash
dev/smoke.sh --list                 # discover stacks without running jobs
dev/smoke.sh <row-id-or-kind>       # selected checks
dev/smoke.sh                       # complete matrix
dev/smoke.sh --full <row>           # complete a long job instead of start/cancel
```

With multiple stacks, select `TIT_SMOKE_CONTAINER` explicitly. Heavy rows wait for an idle queue;
never run competing FEM simulations under emulation. Payloads use a fresh output namespace.
Results and cleanup manifests are written under `tests/smoke/artifacts/`; record whether a check
completed computation or only exercised start/cancel. `--keep` retains generated test artifacts.

Before restarting a shared backend, verify no jobs are running or queued through `/api/jobs`.
Wait for `/api/health`, then probe behavior that proves the changed code loaded. A health response
alone may come from the pre-reload process. Recreating also changes the token; restarting does not.

### 2.7 Workflows and packaging

```bash
actionlint                                   # if you touched .github/workflows
cd desktop && npm run verify:package         # if you touched packaging
cd desktop && npm run build                  # LAST — always
```

**After frontend/e2e work, restore a normal build last.** The dev container serves
`desktop/out/renderer` straight from the worktree, so a plain build dropped in the middle of a
session leaves someone else's e2e run timing out 30 seconds later with no hint why.

---

## 3. Shared checkout and scientific changes

Coordinate edits and test runs in the launched checkout. Stage only owned files; do not stash,
discard another contributor's changes, kill shared test processes or recreate an active container.
Serialize Playwright under `/tmp/tit-e2e.lock` because runs share build output and server ports.
Check for running/queued jobs before server changes; use a copied project for destructive tests.

Changes to numerical behavior need independent tests against real libraries in
`tests/numerical/`. If existing published outputs change, describe the affected versions,
workflows and any re-run/rescaling action in the relevant release page, with a short changelog link.
Formatting or UI-only edits do not make numerical claims.

Follow the root [contribution guide](../../CONTRIBUTING.md) for branches and pull requests.
Use focused commits whose title states the change, without AI co-author trailers.
Documentation ownership and update policy are in [README.md](README.md).
