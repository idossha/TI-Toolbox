---
name: ti-toolbox
description: Orientation for the Temporal Interference Toolbox (TI-Toolbox, Python package `tit`). Use whenever the user mentions TI-Toolbox, TI stimulation simulation/optimization, SimNIBS-based TI workflows, flex-search, ex-search, mTI, the v3 desktop app, or a BIDS project with derivatives/SimNIBS. Explains how the toolbox runs, where docs live, and which MCP tools to call.
user-invocable: false
---

# TI-Toolbox — Agent Orientation

**TI-Toolbox** simulates, optimizes and analyzes temporal-interference (TI) brain
stimulation on subject-specific head models. It wraps SimNIBS, FastSurfer/FreeSurfer
and (optionally) QSIPrep/QSIRecon. Docs: https://idossha.github.io/TI-Toolbox/ ·
Repo: https://github.com/idossha/TI-Toolbox · Cite: Haber et al. 2025,
*Brain Stimulation*, doi:10.1016/j.brs.2025.103016.

## What v3 is (this is the single most common thing to get wrong)

Three pieces, and only three:

1. **An Electron desktop app on the host** — `desktop/` (Electron main/preload +
   React + TypeScript strict + Vite). It is a *shell*: it starts the container and
   then loads the UI over HTTP from it. It owns host lifecycle only.
2. **A FastAPI job server inside the Docker image** — `tit.server`, in
   `idossha/ti-toolbox`. It owns the job model (queue, dependencies, locks, resource
   budget, live events, cancellation) and serves the React bundle at `/`.
3. **The `tit` Python package** — the only place scientific logic lives, still
   usable directly from scripts and notebooks.

**The PyQt5 GUI (`tit/gui/`) was deleted in v3.0.0.** `tit` imports no Qt. The core
image ships **no X11 and no FreeSurfer**. Never cite `tit/gui/**`; if a user's
question assumes it, say it is gone and point at the desktop app or the Python API.

The wire contract between (1) and (2) is `contracts/openapi.yaml` — a frozen
interface. Origin is `http://127.0.0.1:8765`; WebSockets are `/ws/system`,
`/ws/jobs`, `/ws/tetravox` and `/ws/kernels/{id}`. The bearer token lives only in
the container's own environment (`TIT_SERVER_TOKEN`) and is never written to the
host — there is nothing for a user to paste.

## Ground rules (read before answering anything)

1. **Everything scientific runs inside Docker.** `idossha/ti-toolbox` has SimNIBS
   4.x, Python 3.11 (`simnibs_python`), numpy 1.26, nibabel, scipy and `tit`. It has
   **no FSL, no ANTs, no X11, no FreeSurfer**. The host Python cannot import `tit`
   with SimNIBS. The user's project is mounted at `/mnt/<project>/`.
2. **Do not guess API signatures.** Dataclass fields change between releases. Call
   `read_source_file` (`tit/sim/config.py`, `tit/opt/config.py`) or `find_symbol`
   and quote what you find.
3. **Do not guess what the user has on disk.** Call `inspect_project` with their
   project root before diagnosing "my simulation doesn't show up".
4. **Two doc sets, two audiences.** `docs/wiki/` is the user-facing site — use
   `search_wiki` / `read_wiki_page`. `docs/dev/` is the developer source of truth,
   is *not* published, ; its index defines document ownership — use `read_dev_doc`.
5. Check `get_toolbox_version` / `read_changelog` when behaviour may depend on version.

## MCP tools (server `ti-toolbox`)

| Need | Tool |
|------|------|
| First call in a session | `get_quick_facts` |
| Which user-facing page covers X? | `search_wiki`, `list_wiki_pages` |
| Read a wiki page / one section | `read_wiki_page(page, section?)` |
| How is it built / verified / decided? | `read_dev_doc(name, section?)` |
| How do I run it? | `list_launch_paths` |
| Exact class/function definition | `find_symbol` (local checkout) or `read_source_file` |
| Grep the source | `search_source` (local checkout) |
| What data does the user have? | `inspect_project(project_root, subject?)` |
| Montages, pipelines, viewer scenes, free-hand electrodes | `read_project_config(project_root, name, where?, subject?)` |
| What changed in vX.Y.Z? | `read_changelog(version)` |
| Which versions are shipped? | `get_toolbox_version` |

If the MCP server is unavailable, fetch the same Markdown from
`https://raw.githubusercontent.com/idossha/TI-Toolbox/main/docs/wiki/<slug>.md`.

## The rail — ten rows, ten digits, counting from ⌘0

`Overview` ⌘0 · `Pre-processing` ⌘1 · `Simulator` ⌘2 · `Optimizer` ⌘3 ·
`Analyzer` ⌘4 · `Pipeline` ⌘5 · `Notebooks` ⌘6 · `Results` ⌘7 · `Viewer` ⌘8 ·
`Jobs` ⌘9. **Settings is not a rail row** and takes no digit; `⌘,` is its only
chord. Also `⌘K` command palette, `⌘J` jobs panel, `⌘⏎` the action bar's primary
action. Optimizer is *one* page — flex and ex are a Method cell in its jobs table,
not separate pages. Viewer has sub-items (Menu, Tetravox); ⌘8 lands on Menu.

## Wiki map (slugs)

- Orientation: `overview`, `desktop-app`, `jobs`, `notebooks`, `pipelines`, `results`
- Workflow: `pre-processing`, `diffusion-processing`, `simulator`, `flex-search`,
  `ex-search`, `analyzer`, `reports`, `visualizers`, `scripting`, `example-notebook`
- Tools: `atlases`, `montage_visualizer`, `electrode-mapping`, `electrode-placement`,
  `nilearn-visuals`, `cluster-permutation-testing`, `nifti-group-averaging`,
  `tissue-analyzer`, `quick-notes`, `blender`, `logging`
- Dev / agents: `extension`, `testing-pipeline`, `python_env`, `agent-plugin`,
  `ai-assistant`, `troubleshooting`

**There is no `mti` page.** mTI is a section of `simulator`. Call `list_wiki_pages`
rather than guessing a slug.

## The pipeline in one paragraph

**Pre-process** (DICOM/NIfTI → `sub-<id>/anat` → FastSurfer/FreeSurfer →
SimNIBS CHARM head mesh `m2m_<id>`) → **Optimize** electrode positions
(**flex-search**: differential evolution over the scalp, a *local* optimum;
**ex-search**: exhaustive over a leadfield and candidate pool, a global optimum
*within the discretisation it was given*; **mex-search**: multipolar variant) →
**Simulate** a montage (2 pairs = TI, 4+ even = mTI; fields `TI_max`, optional
`TI_avg`/`TI_normal`, exposure `hf_peak`/`hf_sar`) → **Analyze** (spherical or atlas
ROI stats in mesh or voxel space, group analysis) → **Stats** (cluster-based
permutation, volumetric MNI or fsaverage surface) → **Report** (HTML). The
Simulator is not an optimiser; say so when a user treats it as one.

## On-disk layout (BIDS + derivatives + the v3 `code/` tree)

```
<project>/
  sourcedata/<id>/                       raw DICOM
  sub-<id>/anat/sub-<id>_T1w.nii.gz      raw NIfTI (+T2w, ct)
  code/ti-toolbox/
    config/*.json                        montage_list.json, EEG nets, settings
    jobs/<id>/{spec,status}.json, events.jsonl, stdout.log     the v3 job store
    notebooks/                           examples/ is the only subdirectory
    pipelines/<name>.json                + runs/<pipeline>/<node>.<port>.json
    viewer/<kind>.tetravox.json          scenes written by POST /api/view/open
  derivatives/
    freesurfer/sub-<id>/                 recon-all
    qsiprep/, qsirecon/                  diffusion (optional, sibling containers)
    SimNIBS/sub-<id>/
      m2m_<id>/                          head model (<id>.msh, eeg_positions/,
                                         segmentation/, surfaces/, stim_configs/)
      leadfields/                        for ex-search
      Simulations/<montage>/TI/{mesh,niftis} + Analyses/{Mesh,Voxel}/ + fsaverage/
      flex-search/<run>/ , ex-search/<run>/ , m-ex-search/<run>/
    ti-toolbox/{reports,stats,logs,tissue_analysis}/
```

The job store lives **inside the project** so a notebook and a restarted server see
the same jobs; `.bidsignore` carries `code/ti-toolbox/jobs/`. Path logic lives in
`tit/paths.py` (`get_path_manager(project_root, subject)`) — never hand-build a path.
**The run name is the directory**: a second flex/ex run under the same name
overwrites the first in place.

## How it is run

Four ways, one run spec. The spec is the root **`docker-compose.yml`** (one service,
`tit`; no FreeSurfer service, no X11) and it has four readers: the Electron app, the
`tit launch` loader, `loader.py`/`loader.sh`, and the dev overrides in `dev/loader/`.

```bash
# users, no Electron — all three are the same thing
./loader.sh   --project ~/datasets/000            # bootstrap that also finds a Python
python loader.py --project ~/datasets/000         # bootstrap from a checkout
tit launch    --project ~/datasets/000            # the installed form (tit/cli.py)
#   ... --status | --logs [--follow] | --stop | --port | --image | --no-open

# developers
cd desktop && npm run dev        # container + Vite (HMR) + Electron, connected
cd desktop && npm run dev:web    # the same without Electron, http://127.0.0.1:5173/
```

The host needs CPython ≥ 3.11 and the `docker` CLI — **not** SimNIBS, Node or
Electron. The first start pulls ~2.3 GB. Call `list_launch_paths` for the details.

## Entry points for scripts

```bash
simnibs_python -m tit.sim       config.json   # simulation
simnibs_python -m tit.opt.flex  config.json   # flex-search
simnibs_python -m tit.opt.ex    config.json   # ex-search
simnibs_python -m tit.opt.mex   config.json   # multipolar ex-search
simnibs_python -m tit.analyzer  config.json
simnibs_python -m tit.stats     config.json
simnibs_python -m tit.pre       config.json
simnibs_python -m tit.source    config.json   # fsaverage projection
```
The server runs exactly these commands, so anything the UI does is reproducible
from a script. Python-level usage is in the `ti-scripting` skill.

## Jobs, and what a failure means

Kinds: `pre sim flex flex_adaptive flex_pareto ex mex leadfield analyzer stats
source blender nifti_average nilearn tools project_init report`.
States: `queued running succeeded failed cancelled skipped lost`.
Failure `error.type` values and the wording the UI shows:

| type | label |
|------|-------|
| `preflight` | Preflight check failed |
| `lock_wait` | Waiting on a lock |
| `budget_wait` | Waiting on the resource budget |
| `runner_failed` | Runner failed |
| `oom_suspected` | Likely out of memory |
| `cancelled` | Cancelled |
| `skipped` | Skipped |
| `lost` | **Lost (server restarted mid-run)** |
| `docker_unavailable` | Docker is unavailable |
| `kind_error` | Invalid job configuration |

`lost` means the server restarted while the job was running: the job is over and
will not resume. A job stuck at `running` with no process behind it is freed with
`POST /api/jobs/{id}/force`, which lands it in `lost`.

## Common user pitfalls to check first

**For any error message, first call `read_wiki_page("troubleshooting")`** (or
`search_wiki` with the error text). That page is the maintainer-verified archive of
known problems, causes and fixes; prefer its answer over your own diagnosis.

- Running host `python` instead of `simnibs_python` inside the container.
- Montage names must match `montage_list.json` exactly; EEG net names are real
  filenames (e.g. `GSN-HydroCel-185.csv`).
- ex-search needs a pre-computed leadfield for the same EEG net.
- Anisotropic conductivity (`vn`/`dir`/`mc`) needs QSIRecon-derived tensors.
- `TI_normal` is **mesh-only**; voxel analysis of it is an error by design.
- An mTI simulation run before `TI_normal` support existed has no normal mesh —
  requesting it raises `FileNotFoundError`; re-run the simulation.
- The first run fails with an image-not-found error on a pre-release checkout where
  the tag is not published yet: build it with `container/blueprint/build.sh --tag
  <image>`, or pass `--image` with a tag they already have.
- Support channels: GitHub Issues/Discussions, Discord (links in README).
