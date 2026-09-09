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
docs/dev/       how this software is built and why — current developer references
docs/wiki/      the user-facing site (published); docs/wiki/gui.md is deprecated
agent-plugin/   installable skills + a read-only MCP server for AI clients
```

## Where things are written down

[docs/dev/README.md](docs/dev/README.md) owns the document map and update policy.
Keep architecture, UI design, development commands, release work and historical rationale separate.
Revise current-state pages rather than appending work logs. Record significant decisions in
DECISIONS.md alongside meaningful milestones, and contract changes in contracts/CHANGES.md.
User-visible numerical corrections belong in the applicable release page, not a separate audit file.

## The gate

Run checks appropriate to the change, and the full gate for a release candidate. Report actual results. Exact commands and their caveats:
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

Use isolated runs of `tests/test_scene_guide.py` to diagnose order-dependent failures;
an isolated pass does not waive a failed full suite (see `docs/dev/CONTRIBUTING.md` §2.2).

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

A change to numerical behavior in `tit/stats`, `tit/analyzer`, `tit/calc`, `tit/fields` or `tit/sim` needs:

1. a test in `tests/numerical/` running against the **real** libraries (the host `tests/conftest.py`
   mocks scipy/nibabel/…), asserting the claim independently rather than retyping the
   implementation; and
2. if any published result moves, an entry in the applicable `docs/releases/` page — what was
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
- **Guide coordinates are not subject coordinates.** Optimizer/Analyzer use reference anatomy;
  Simulator subject-space placement requires its subject-specific geometry. Never save guide picks
  as subject coordinates.
- **`--project=real`, not `--project real`** — Playwright's flag is variadic and swallows the spec
  path. And never `npm run e2e` for a real-server run: `pree2e` force-rebuilds `out/`.
- **`electron-vite build` ignores `--mode`**; it hardcodes `NODE_ENV=production`, so
  `import.meta.env.DEV` is always false in a build. That is why gallery and scene hooks are gated
  by `VITE_INCLUDE_GALLERY` / `VITE_SCENE_HOOKS` instead.
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
any MCP client five skills (orientation, scripting API, TI domain knowledge, codebase conventions)
plus a read-only MCP server that searches the wiki, reads `tit` source, finds symbols and inspects
a user's project directory. In Claude Code:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```
