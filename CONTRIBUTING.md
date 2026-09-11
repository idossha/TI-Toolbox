# Contributing to TI-Toolbox

This guide owns contributor setup, daily development and pull requests. See
[TESTING](docs/dev/TESTING.md) for verification, [ARCHITECTURE](docs/dev/ARCHITECTURE.md) for
system constraints, [RELEASING](docs/dev/RELEASING.md) for shipping, and
[AGENTS.md](AGENTS.md) for the documentation map and shared-checkout rules.

## Propose a change

Discuss substantial new features with the maintainers before implementation to avoid duplicate
work and incompatible designs. Bug fixes can proceed directly: describe expected/actual behavior,
reproduction steps, environment and relevant logs in the issue or PR. Keep interactions respectful.
Do not include credentials or private subject data in reports.

Fork the repository and clone over SSH:

```bash
git clone git@github.com:YOUR-USERNAME/TI-Toolbox.git
cd TI-Toolbox
git remote add upstream git@github.com:idossha/TI-Toolbox.git
```

## Development environment

The host runs Electron/Vite; Docker runs FastAPI and the SimNIBS scientific environment. Install
Docker and Node matching `desktop/package.json` (currently Node ≥22.12), then use a local image
and a BIDS project. Use a copied project for tests that create or replace outputs.

```bash
cd desktop
npm install
# .env.dev is optional for desktop; choose the project in Overview
npm run dev                        # welcome Overview; choose a project in the app
# npm run dev:web                  # container + Vite at http://127.0.0.1:5173/
# npm run dev:down                 # stops/removes this project's container
```

To develop and manually test the desktop Overview before packaging, run `npm run dev`
from `desktop/`. It builds the local app and opens Overview without starting Docker or
automatically connecting. Type a project path or use Browse, open a project, then use Switch project
to choose the next directory before confirming the switch. Closing the app stops its container and exits.
This uses the built UI rather than Vite hot reload; rerun after source changes.

`pnpm dev:web` / `pnpm dev` use the same scripts. Inspect locally available image tags with
`docker images idossha/ti-toolbox`; obtain or build a missing image first using
[RELEASING](docs/dev/RELEASING.md). For one run, use
`npm run dev:web -- --project /absolute/path/to/project`. For persistent browser-development
defaults, copy `desktop/.env.dev.example` to `desktop/.env.dev` and set `TIT_DEV_PROJECT_DIR`.

With `dev:web`, Vite supplies frontend HMR and authenticates proxied API/WebSocket requests; no token copying is
needed. By default the launched checkout is mounted at `/ti-toolbox`, first on the Python import
path, and changes under `tit/` trigger server reload. Python dependency, system-package and
entrypoint changes require an image rebuild. With `dev:web`, `TIT_DEV_MOUNT_REPO=0` tests baked scientific code.
The container's own browser URL serves `desktop/out/renderer`, so frontend edits there require
a fresh build; Vite on port 5173 serves live frontend source.

Close the Electron window to stop its container and exit. Ctrl-C in browser development stops
Vite and leaves the container available for the next attach. Every running TI-Toolbox session
requires an explicit Attach or Recreate choice; Attach keeps its existing project, image and
mounts unchanged. Configuration differences never authorize automatic replacement. Check jobs before backend changes: reload can interrupt work. A container
recreate changes its token; a plain restart preserves the token but still interrupts its processes.

The standard manual test entry point is `bash dev/loader/loader_dev.sh`. It mounts the present checkout over the container code. The Bash dev loader opens Electron by default so Apple GPU consent is available; use `--browser` explicitly for browser testing. Browser sessions cannot install host software.

Choose the execution mode explicitly:

| Mode | Command | Code used |
|---|---|---|
| Run the built image | `bash loader.sh` or `python3 loader.py` | Image contents |
| Develop inside Docker | `bash dev/loader/loader_dev.sh` or `python3 dev/loader/loader_dev.py` | The launched checkout/worktree mounted at `/ti-toolbox` |
| Desktop development | From `desktop/`: `npm run dev` | Local Electron/renderer build + mounted backend after project selection |
| Docker + live frontend | From `desktop/`: `npm run dev:web` | Mounted backend + Vite frontend |
| Host-only development | From `desktop/`: `npm run dev:host` | Local Python API + Vite browser; no container |

Both Bash entry points require Docker Compose and curl, **not host Python**. Both Python entry
points require Python 3.11+. With no arguments the loaders ask for a project and, when a TI-Toolbox container is running,
an Attach/Recreate decision; explicit
`--project`, `--image`, `--port`, `--no-open`, `--status`, `--logs` and `--stop` stay scriptable.
New sessions created by dev loaders use their own checkout, including a branch or worktree;
Attach preserves the selected session instead. Build the checkout frontend
with `npm --prefix desktop run build` after edits, or use Vite for live changes. A missing local
bundle never silently falls back to the image's UI.

Host-only setup, from the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
cd desktop
pnpm install
pnpm dev:host --project /absolute/path/to/project
```

Host mode uses `.venv` when present, otherwise `python3`; `TIT_DEV_PYTHON` overrides the interpreter.
The API binds to localhost, selects a free port, and stops with Ctrl-C. It is useful for UI/API
work; scientific jobs require the relevant tools installed on the host. Docker remains the
reproducible scientific environment. The test extra must not replace the image's SimNIBS pins.

## Development workflow

### 1. Choose the branch and pull-request target

Create a short-lived topic branch in your fork from `upstream/main`. Use a descriptive,
lowercase name such as `feature/electrode-search`, `fix/job-deletion`, or `docs/setup-guide`.
Submit a pull request against `main`, unless a maintainer requests another target.

```bash
git fetch upstream
git switch -c feature/electrode-search upstream/main
```

You can use a separate worktree to isolate concurrent changes. Preserve uncommitted work when
switching branches, and coordinate with anyone sharing your checkout. Do not rewrite published
history. Remove your topic branch after its pull request is merged.

For release procedures, see [Building and releasing](docs/dev/RELEASING.md).

### Make, verify and submit the change

Keep changes scoped, preserve existing conventions and add independent regression coverage.
Run the relevant [TESTING](docs/dev/TESTING.md) layers; a release candidate requires the full gate.
Report actual counts, failures, skips and unrun checks. Do not push or merge failing work.

Stage only files you own. Never stash, discard another contributor's edits, force-switch branches
or kill shared test processes. GUI runs share build output and ports: coordinate and serialize
them under `/tmp/tit-e2e.lock` as described in TESTING. Restore a plain renderer build after e2e.

Use commit titles describing the defect or new behavior, without AI co-author trailers:

```bash
git add path/to/changed-file
git commit -m "fix(analyzer): preserve voxel intensity units"
git push origin your-branch-name
```

Open a focused PR against the branch being maintained. Explain the problem, final behavior,
validation and material limitations; link the issue and fill the repository template. Address
review feedback and required checks before merge. A PR does not itself authorize publication.

## Code and documentation conventions

Python uses type hints, Google-style public API docstrings, project exceptions from `tit/errors.py`
and module loggers. Run `black` on changed Python files. Scientific logic stays in `tit`; paths go
through PathManager. Use existing shared frontend controls and strict TypeScript.

Changes to `tit/stats`, `tit/analyzer`, `tit/calc`, `tit/fields` or `tit/sim` require real-library
numerical coverage. If published outputs change, document affected workflows/versions and rerun
or rescaling guidance in the relevant [release note](docs/releases/v3.0.0.md#scientific-corrections).

Update the relevant user guide for behavior changes and the architecture/decision record for
consequential design changes. [AGENTS.md](AGENTS.md) assigns document ownership; avoid duplicating
facts or adding session logs. Consolidate accepted requirements into ARCHITECTURE, decisions into
DECISIONS, verification limits into TESTING and remaining work into ROADMAP; do not add dated
requirement files or duplicate development plans. Use [Discussions](https://github.com/idossha/TI-Toolbox/discussions)
for design/help and GitHub issues for reproducible defects. Sensitive reports can go to
`ihaber@wisc.edu`.
