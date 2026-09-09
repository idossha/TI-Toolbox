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
One command brings up all three.

```bash
cd desktop
npm install                       # Electron is downloaded from GitHub on install
cp .env.dev.example .env.dev      # then set TIT_DEV_PROJECT_DIR to your BIDS project
npm run dev                       # container + Vite (HMR) + Electron, already connected
npm run dev:web                   # the same without Electron: http://127.0.0.1:5173/
npm run dev:down                  # stop and remove *this project's* container only
```

Four facts about this loop that are not obvious, and each of which has cost someone an afternoon:

- **There is no token to read, paste or export.** The Vite proxy (`desktop/scripts/devProxy.ts`)
  stamps `Authorization: Bearer <token>` and rewrites `Origin` on every proxied `/api`, `/auth` and
  `/ws` request — on `proxyReq` *and* `proxyReqWs`, since only the second fires for the `/ws/system`
  upgrade. So the browser needs no cookie, no `?token=`, and no `TIT_DEV_ORIGINS` allowlist.
- **The worktree is bind-mounted, so Python is live.** With `TIT_DEV_MOUNT_REPO=1` (the default) the
  repository is mounted at `/ti-toolbox` with `PYTHONPATH=/ti-toolbox`, so an edit under `tit/sim`,
  `tit/opt`, `tit/analyzer`… is live for the *next job* with nothing to restart. The same flag sets
  `TIT_SERVER_RELOAD=1`, so an edit under `tit/server/**` or `tit/jobs/**` restarts the server on
  its own (the watch is scoped to `tit/` deliberately — uvicorn's default watch root would be the
  whole mounted repository, 5 834 directories, 2 815 of them `desktop/node_modules`).
  Set `TIT_DEV_MOUNT_REPO=0` to test the image's baked-in `tit`, which is what a user gets.
- **The container also serves the *UI* from the worktree** (`desktop/out/renderer`). A stale or
  wrongly-flagged build is therefore what a real-server e2e run sees — see §2.5.
- **A recreate mints a new bearer token and kills in-flight jobs; a plain `docker restart` does
  not.** `npm run dev` refuses to recreate a container with jobs in flight and names them. Before
  restarting the server for a `tit/server/**` change, check `GET /api/jobs` is empty first
  (§2.6, "Restart rule").

`Ctrl-C` stops Vite and Electron and leaves the container running, so the next `npm run dev`
attaches in well under a second.

**Without Node.** `dev/loader/loader_dev.py` (and `loader_dev.sh` beside it) start the same dev
container from Python alone — same options as the root `loader.py`, plus `--build`, `--image` and
`--web`. They are the developer's equivalents of the two user entry points at the repository root,
and they set exactly the three overrides in `dev/loader/docker-compose.dev.yml`: the worktree
mounted at `/ti-toolbox`, `TIT_SERVER_RELOAD=1`, and the locally built renderer. `--web` hands over
to `npm run dev:web` rather than reimplementing the loop, so there is still one implementation of
container + Vite + Electron. The stack itself is defined once, in the root `docker-compose.yml`.

---

## 2. The gate

Run all of it before claiming a change is done, and **report the numbers, not "green"**.

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
it makes *numerical* claims — cluster masses, permutation p-values, affine determinants. It is the
required leg for any change to the science core (§4).

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

### 2.6 The real-container smoke harness

Two levels over one shared payload, both against a **real** dev container on Dataset 000. Level A
(`tests/smoke/`, pytest, `smoke` marker, deselected by default) drives HTTP; Level B
(`desktop/tests/e2e/real/*.spec.ts`, Playwright's `real` project) drives the UI and records the
payloads Level A replays, so the two cannot disagree about the request body.

```bash
dev/smoke.sh --list                  # every dev-stack container and its exact selector; runs nothing
dev/smoke.sh                         # the whole matrix, sequential, cleaned up
dev/smoke.sh <row-id-or-kind>...     # one row, or a kind -> every row of it
dev/smoke.sh --keep <row>...         # keep everything created, for inspection
dev/smoke.sh --full <row>...         # run long kinds to completion instead of cancelling
```

- **Discovery needs no `docker inspect`.** `--list` prints each container with its port and project.
  With more than one and no selector, the harness prints every `TIT_SMOKE_CONTAINER=<name>
  dev/smoke.sh` line and exits **2** rather than guessing.
- **A payload is retagged on every load.** A recorded payload's name-bearing field is rewritten to a
  fresh `smoke-<runid>` tag each time, not only in the session that recorded it, so a row never
  skips its own second replay with "recorded payload targets existing output(s)".
- **One FEM-class job at a time, enforced by the harness itself.** Any row with
  `behaviour == completed` or `heavy == True` (`sim`, `flex`, `leadfield`, `source`, `blender`,
  charm, FastSurfer) blocks on `GET /api/jobs` until nothing is `running`/`queued` before
  submitting. This is the rule `desktop/tests/e2e/batch.spec.ts` and `real/pipeline.spec.ts` cite.
- **The results table is a file, not an impression.** `ls -t tests/smoke/artifacts/results-*.md |
  head -1` is the newest matrix run's table; the `manifest-*.json` beside it lists every path it
  created. The run of record for the whole matrix is in [`BENCHMARKS.md`](BENCHMARKS.md).

**Restart rule** (`tit/server/**`, `tit/jobs/**`, `tit/catalog.py`):

```bash
curl -s -H "Authorization: Bearer $TOKEN" $URL/api/jobs   # must show nothing running/queued
docker restart <container>                                # only if the line above is empty
curl -s $URL/api/health                                   # poll until {"status":"ok"}
```

A plain `restart` keeps the same token and is healthy again in 2-5 s; only a *recreate* mints a new
one and kills in-flight jobs. **A 200 from `/api/health` is not evidence the new code loaded** — the
pre-reload process can still answer. Wait and probe something that reflects the change.

### 2.7 Workflows and packaging

```bash
actionlint                                   # if you touched .github/workflows
cd desktop && npm run verify:package         # if you touched packaging
cd desktop && npm run build                  # LAST — always
```

**`pnpm run build` (or `npm run build`) goes last, every time.** The dev container serves
`desktop/out/renderer` straight from the worktree, so a plain build dropped in the middle of a
session leaves someone else's e2e run timing out 30 seconds later with no hint why.

---

## 3. Working alongside other lanes

Several agents may share one worktree. These are not style preferences; each one cost a lane real
work.

- **Stage only your own files.** `git add -A` swept another lane's uncommitted work into the wrong
  commit three times in one day.
- **Never `git stash`.** It takes every other lane's work with it.
- **One Playwright run at a time**, guarded by `/tmp/tit-e2e.lock`. Runs share the mock server on
  8790 and one `out/`.
- **Never `pkill -f "playwright test"`** — it kills whoever else is mid-gate.
- **Never recreate the maintainer's dev container.** It bind-mounts the worktree for both `tit` and
  the UI bundle; one recreated from a plain `docker run` line serves the image's baked copies
  instead, and mints a new token that invalidates every other lane's session.
- **Verify path and filesystem behaviour in the container** (Python 3.11, case-sensitive), never on
  the macOS host.
- **Never revert or discard someone else's working-tree changes.**

---

## 4. The science-integrity rule

Any change to `tit/stats`, `tit/analyzer`, `tit/calc`, `tit/fields` or `tit/sim` needs:

1. a test in **`tests/numerical/`** that runs against the **real** libraries (not the host mocks)
   and asserts the numerical claim independently — not by retyping the implementation; and
2. if any published result moves, an entry in
   [`SCIENTIFIC-CORRECTIONS.md`](SCIENTIFIC-CORRECTIONS.md) saying what was wrong, which versions
   are affected, which outputs move and by how much, how a user spots an affected result, and
   whether to re-run or rescale.

A number that changes and is not written down there is indistinguishable, to a user, from a
result they can no longer trust.

---

## 5. Commit messages

One topic per commit, present tense, and a title that states **the defect or the new truth** rather
than the activity:

```
fix(analyzer): voxel focality volumes in cm^3, geometry from the affine
docs(contracts): add contracts/README.md, describe the generated/ outputs
```

Prefix with the area (`fix`, `feat`, `docs`, `test`, `ci`, `refactor`) and the module in
parentheses. The body says what was wrong and what the reader would otherwise be surprised by.
Never write "various fixes".

---

## 6. Where a new fact goes

| The thing you learned | Where it is written down | Never |
|---|---|---|
| A **measurement** (a timing, a size, a test count, a frame rate) | `BENCHMARKS.md` | a commit message, a code comment |
| A **decision** | `DECISIONS.md`, as **Decision / Why / Cost / Revisit if** — plus the `ARCHITECTURE.md` edit if it changes a rule, in the same commit | a lane note |
| A **gate result** | the gate table in `BENCHMARKS.md`, with the command that produced it | prose |
| **What happened** in a program | a dated section of `HISTORY.md` | a new file |
| A **trap that cost an hour** | that program's `HISTORY.md` gotchas, or `AGENTS.md` if every agent must know it before starting | nowhere |
| A **contract change** | `contracts/CHANGES.md` (append; never edit a past entry) | only the diff |
| **A number that moved for users** | `SCIENTIFIC-CORRECTIONS.md` and `docs/releases/changelog.md` | only the test |

**Never write a per-lane note file.** About 120 of them accumulated in eleven days, each citing the
others, and no reader could tell which were still true.
