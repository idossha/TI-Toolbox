# AGENTS.md — TI-Toolbox

Entry point for any AI coding agent working in this repository. Read this fully before your first
edit. Everything else is in [`docs/dev/`](docs/dev/README.md) — link to it, never restate it.

## What this is

**TI-Toolbox** is a research platform for temporal-interference (TI) brain-stimulation simulation,
optimization and analysis, built on SimNIBS. As of **v3.0.0** it is three pieces:

- an **Electron desktop app** on the host (`desktop/`, React + TypeScript strict + Vite),
- a **FastAPI job server** (`tit/server`) inside one Docker image (`idossha/ti-toolbox`), owning the
  job model — queue, dependencies, locks, budget, live events, cancellation,
- the **`tit` Python package** — the only place scientific logic lives, still usable from scripts.

The PyQt5 GUI (`tit/gui/`) was **deleted** in v3.0.0. `tit` imports no Qt; the core image ships no
X11 and no FreeSurfer. Wire contract: `contracts/openapi.yaml`.

## Repo map

```
desktop/        Electron main/preload + React renderer; the UI bundle tit.server serves
tit/            the science core (paths, sim, opt, analyzer, stats, calc, fields, pre, reporting)
tit/server/     FastAPI app + routes; tit/jobs/ is the job engine
contracts/      openapi.yaml is the one hand-written contract; generated/ is build output (npm run gen)
tests/          host pytest (heavy libs mocked); tests/numerical/ runs the real ones
dev/            scripts only: build_contracts (+build_schema/build_contract), contracts_check, route_import_guard, smoke.sh
container/      image blueprints and build.sh
docs/dev/       how this software is built and why — nine files, the source of truth
docs/wiki/      the user-facing site (published); docs/wiki/gui.md is deprecated
agent-plugin/   installable skills + a read-only MCP server for AI clients
```

## Where things are written down

`docs/dev/` is the source of truth, and it is **nine files** —
[`docs/dev/README.md`](docs/dev/README.md) is its map and reading order. Do not add a tenth.

| Question | File |
|---|---|
| How is it built? What must I not break? | `docs/dev/ARCHITECTURE.md` (§8 the pipelines, §9 DWI) |
| How do I run and verify it? | `docs/dev/CONTRIBUTING.md` (§2 the gate, §2.6 the smoke harness) |
| Why is it like this? | `docs/dev/DECISIONS.md` — its ADR index is what "ADR row N" means |
| What happened, and what bit us? | `docs/dev/HISTORY.md` |
| What is the UI contract? | `docs/dev/DESIGN.md` |
| Every measured number | `docs/dev/BENCHMARKS.md` |
| How does it ship, and what is still open? | `docs/dev/RELEASE.md` (§A ship, §B open) |
| What did v2.x get numerically wrong? | `docs/dev/SCIENTIFIC-CORRECTIONS.md` |

**Where a new fact goes.** A measurement or a gate result → `BENCHMARKS.md`, with the command. A
decision → `DECISIONS.md` as **Decision / Why / Cost / Revisit if**, plus the `ARCHITECTURE.md` edit
in the same commit. Something not done, and why → `RELEASE.md` §B. What happened in a program → a
dated section of `HISTORY.md`. A contract change → `contracts/CHANGES.md`.

**Never write a per-lane note file, and never add a file to `docs/dev/`.** About 120 accumulated in eleven days, each citing the others,
and no reader could tell which were still true. Record numbers and decisions; delete your scratch.

## The gate

Run all of it and **report the numbers, not "green"**. Exact commands and their caveats:
[`docs/dev/CONTRIBUTING.md` §2](docs/dev/CONTRIBUTING.md).

```
cd desktop && npm run typecheck && npm run lint && npx vitest run
python3 -m pytest tests/ -q                                  # repo root, heavy libs mocked
docker exec -w /ti-toolbox <c> simnibs_python -m pytest tests/numerical -q   # real libraries
python3 dev/route_import_guard.py && python3 dev/contracts_check.py
cd desktop && TIT_E2E_OFFSCREEN=1 npm run e2e:quiet          # full mock suite, under the lock
cd desktop && npx playwright test --project=real …           # against the dev container
actionlint                      # if you touched .github/workflows
npm run verify:package          # if you touched packaging
npm run build                   # LAST, always
```

`tests/test_scene_guide.py` has one known order-dependent failure in a full run that passes
standalone; confirm it in isolation rather than reporting a red.

## Working in a shared worktree

Several agents may be in one worktree at once. Each of these cost a lane real work.

- **Stage only your own files.** `git add -A` swept another lane's uncommitted work into the wrong
  commit three times in one day.
- **Never `git stash`.** It takes every other lane's work with it.
- **Never revert or discard someone else's working-tree changes.**
- **One Playwright run at a time**, guarded by `/tmp/tit-e2e.lock` — runs share the mock server on
  8790 and one `out/`. Never `pkill -f "playwright test"`; it kills whoever else is mid-gate.
- **`pnpm run pree2e` before any scene spec** (`VITE_SCENE_HOOKS=1`), and a plain `npm run build`
  **last**: the dev container serves `desktop/out/renderer` straight from the worktree, so a plain
  build dropped mid-session makes another lane's specs time out 30 s later with no hint why.
- **Never recreate the maintainer's dev container.** It bind-mounts the worktree for both `tit` and
  the UI bundle; a recreated one serves the image's baked copies and mints a new token that
  invalidates every other lane's session. A plain `docker restart` keeps the token.

## Science integrity

Any change to `tit/stats`, `tit/analyzer`, `tit/calc`, `tit/fields` or `tit/sim` needs **both**:

1. a test in `tests/numerical/` running against the **real** libraries (the host `tests/conftest.py`
   mocks scipy/nibabel/…), asserting the claim independently rather than retyping the
   implementation; and
2. if any published result moves, an entry in `docs/dev/SCIENTIFIC-CORRECTIONS.md` — what was
   wrong, which versions, which outputs move and by how much, how a user spots an affected result,
   and whether to re-run or rescale.

## Gotchas that cost us

- **Never run two FEM simulations in parallel** under emulation. The smoke harness enforces it
  itself: any `heavy` row blocks on `GET /api/jobs` until nothing is running or queued.
- **nibabel's gzip save fails on bind mounts** in the container. Write a plain `.nii` and gzip it
  with the standard library.
- **Verify path and filesystem behaviour in the container** (Python 3.11, case-sensitive), never on
  the macOS host. It is the only place a path bug reproduces honestly.
- **The Viewer's scene file suffix is `.tetravox.json`**, written to
  `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. Not `.json`.
- **Guide coordinates are not subject coordinates.** The run-page panes draw packaged reference
  anatomy; a subject switch must produce zero guide requests and the same canvas.
- **`--project=real`, not `--project real`** — Playwright's flag is variadic and swallows the spec
  path. And never `npm run e2e` for a real-server run: `pree2e` force-rebuilds `out/`.
- **`electron-vite build` ignores `--mode`**; it hardcodes `NODE_ENV=production`, so
  `import.meta.env.DEV` is always false in a build. That is why gallery and scene hooks are gated
  by `VITE_INCLUDE_GALLERY` / `VITE_SCENE_HOOKS` instead.
- **An empty `QComboBox` is falsy** — legacy code and ported logic must test `is not None`.
- The maintainer-verified list of user-visible problems and fixes is
  [`docs/wiki/troubleshooting.md`](docs/wiki/troubleshooting.md). Consult it before diagnosing a
  reported error; add an entry when a new one is confirmed.

## Conventions

- `black tit/` before committing Python; type hints and Google-style docstrings on public APIs.
- Custom exceptions from `tit/errors.py`; `logging.getLogger(__name__)` per module, and
  `setup_logging()` only at entry points (it adds no handlers of its own).
- Every pipeline module exposes `simnibs_python -m tit.<module> config.json` (`sim`, `opt.flex`,
  `opt.ex`, `opt.mex`, `analyzer`, `stats`, `pre`), with `tit/config_io.py` doing the
  (de)serialisation via `_type` discriminators. All paths go through
  `get_path_manager(project_root, subject_id)` — never hand-built.
- Commit titles state the defect or the new truth, not the activity:
  `fix(analyzer): voxel focality volumes in cm^3, geometry from the affine`.

## The agent plugin

An installable plugin under [`agent-plugin/`](agent-plugin/README.md) gives Claude Code, Codex and
any MCP client four skills (orientation, scripting API, TI domain knowledge, codebase conventions)
plus a read-only MCP server that searches the wiki, reads `tit` source, finds symbols and inspects
a user's project directory. In Claude Code:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```
