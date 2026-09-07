# AGENTS.md — TI-Toolbox

Context for any AI coding agent (Claude Code, Codex, Cursor, Copilot, ...) working on TI-Toolbox.
Install the [agent plugin](agent-plugin/README.md) for skills + an MCP server that reads the wiki/source and inspects projects.

## Project Overview

**TI-Toolbox** (Temporal Interference Toolbox) is a neuroscience research platform for brain stimulation simulation, optimization, and analysis. It enables researchers to simulate temporal interference (TI) stimulation, optimize electrode placements, and analyze electromagnetic field distributions in the brain.

- **Package Name**: `tit` (import as `from tit.module import ...`)
- **Version**: 2.2.x
- **Repository**: https://github.com/idossha/TI-toolbox
- **Python Version**: 3.9+
- **Primary Environment**: Docker containers (SimNIBS, FreeSurfer)

## Architecture at a Glance

```
TI-Toolbox
├── desktop/          # v3 Electron desktop app + web UI (Docker orchestration)
├── tit/              # Python package (all scientific code)
│   ├── paths.py      # PathManager singleton (BIDS path resolution)
│   ├── constants.py  # Project-wide constants
│   ├── errors.py     # Custom exception classes
│   ├── logger.py     # Logging setup (setup_logging, add_file_handler)
│   ├── pre/          # Preprocessing (DICOM, FreeSurfer, CHARM)
│   ├── sim/          # TI/mTI simulation engine
│   ├── opt/          # Optimization (flex-search, exhaustive)
│   ├── analyzer/     # Field analysis and ROI statistics
│   ├── stats/        # Permutation testing, group analysis
│   ├── server/       # FastAPI HTTP server the Electron desktop app drives
│   ├── <module>/__main__.py  # JSON-config runners: simnibs_python -m tit.<module> config.json
│   ├── reporting/    # HTML report generation
│   ├── plotting/     # Visualization utilities
└── docs/             # MkDocs API documentation
```

## Critical Files to Know

| File | Purpose |
|------|---------|
| `tit/paths.py` | BIDS-compliant path resolution singleton |
| `tit/sim/simulator.py` | Main simulation entry point |
| `tit/analyzer/analyzer.py` | Primary analysis tool (unified Analyzer class) |
| `tit/opt/flex/flex.py` | Differential evolution optimization |
| `tit/opt/ex/ex_search.py` | Exhaustive search optimization |
| `tit/server/app.py` | FastAPI app the desktop app drives |
| `tit/config_io.py` | JSON config (de)serialisation used by all `__main__` runners |
| `docker-compose.yml` | Multi-container orchestration |
| `pyproject.toml` | Package configuration |

## Key Patterns

### PathManager (Singleton)
All path operations go through PathManager for BIDS compliance:
```python
from tit import get_path_manager
pm = get_path_manager(project_root, subject_id)
mesh_path = pm.get_head_mesh()
```

### JSON Config Runners
Every pipeline module exposes `python -m tit.<module> config.json` (`sim`, `opt.flex`,
`opt.ex`, `opt.mex`, `analyzer`, `stats`, `pre`). The GUI builds the config dataclass,
serialises it with `tit/config_io.py`, and runs that command in the container.

### Dataclass Configuration
Configuration uses typed dataclasses throughout:
```python
@dataclass
class SimulationConfig:
    subject: str
    montage: str
    intensity: float = 1.0
```

### Code Formatting
```bash
black tit/
```

### Adding a New Runner
1. Add a `__main__.py` to the module that loads the config via `tit/config_io.py`
2. Wire the GUI tab to write the same JSON and call `simnibs_python -m tit.<module>`

### Adding a New Report Generator
1. Create generator in `tit/reporting/generators/`
2. Inherit from `BaseReportGenerator`
3. Use reportlets from `tit/reporting/reportlets/`

## Data Flow

### BIDS-Compliant Project Structure
```
project_root/
├── sourcedata/              # Raw DICOM
├── sub-{subject}/
│   └── anat/               # Anatomical NIfTI
├── derivatives/
│   ├── SimNIBS/sub-{subject}/
│   │   ├── m2m_{subject}/  # Head mesh
│   │   └── Simulations/    # TI outputs
│   ├── freesurfer/         # recon-all outputs
│   └── ti-toolbox/
│       ├── reports/        # HTML reports
│       └── analysis/       # Results
└── code/ti-toolbox/config/ # Metadata
```

### Simulation Pipeline
1. Input: m2m directory + montage config + intensities
2. Process: Run SimNIBS (pair1, pair2, [pair3, pair4])
3. Post-process: Calculate TI_max, TI_normal, mTI fields
4. Output: Mesh files, NIfTI, surface overlays

### Analysis Pipeline
1. Input: Field mesh/NIfTI + atlas + ROI spec
2. Process: Extract values, calculate statistics
3. Output: CSV, histograms, visualizations

## Simulation Types

- **TI (2-pair)**: Standard temporal interference with 2 electrode pairs
- **mTI (4-pair)**: Multi-channel TI with 4 electrode pairs
- Auto-detection based on montage configuration

## UI Architecture

The v3 Electron desktop app (`desktop/`) replaced the PyQt5 GUI, which was
deleted in v3.0.0; it talks to `tit.server` over HTTP and `tit/` imports no Qt.

## Docker Containers

| Container | Purpose |
|-----------|---------|
| `idossha/simnibs:v2.2.x` | SimNIBS + GUI + tools |
| `idossha/ti-toolbox_freesurfer:v7.4.1` | FreeSurfer only |
| `idossha/ti-toolbox-test:latest` | Static test environment |

## Important Conventions

1. **Black formatting** - Run `black` before committing
2. **Type hints** - Use throughout, especially in public APIs
3. **Docstrings** - Google style for public functions
4. **Error handling** - Use custom exceptions from `tit/errors.py`
5. **Logging** - Use stdlib `logging` with `getLogger(__name__)` in each module; call `setup_logging()` at entry points only

## Common Pitfalls

The maintainer-verified list of known problems, causes and fixes is `docs/wiki/troubleshooting.md` (published at https://idossha.github.io/TI-Toolbox/wiki/troubleshooting/). Consult it before diagnosing a user-reported error, and add an entry there when a new one is confirmed.

1. **PathManager initialization** - Must be initialized before use
2. **Docker context** - Most heavy computation happens in containers
3. **X11 forwarding** - GUI requires proper display setup
4. **SimNIBS imports** - Use lazy loading pattern in opt/
5. **Large tab files** - GUI tabs are monolithic; careful with changes

## External Dependencies

- **SimNIBS 4.5+** - Finite element simulation
- **FreeSurfer 7.4+** - Cortical reconstruction
- **dcm2niix** - DICOM conversion
- **QSIPrep/QSIRecon** - Diffusion preprocessing
- **Gmsh** - Mesh generation

## Quick Reference: Module Imports

```python
# Core
from tit import get_path_manager
from tit import setup_logging, add_file_handler
from tit import paths, constants

# Simulation
from tit.sim import SimulationConfig, run_simulation, load_montages

# Analysis
from tit.analyzer import Analyzer, run_group_analysis

# Optimization
from tit.opt import FlexConfig, SphericalROI, run_flex_search

# Statistics
from tit.stats import run_group_comparison, GroupComparisonConfig

# Preprocessing
from tit.pre import run_pipeline

# Reporting
from tit.reporting import ReportAssembler
from tit.reporting.generators import SimulationReportGenerator
```

## Development source of truth — `docs/dev/`

Everything about how this software is built and why lives in `docs/dev/`. Read the one that
matches your question; do not restate its content anywhere else.

| File | What it holds |
|---|---|
| `docs/dev/ARCHITECTURE.md` | How it is built — the contract. Changing a rule needs a DECISIONS entry in the same commit. |
| `docs/dev/DECISIONS.md` | Why. Append-only; new entries as **Decision / Why / Cost / Revisit if**. |
| `docs/dev/ROADMAP.md` | What is next, and the gate table. |
| `docs/dev/BENCHMARKS.md` | Every measured number, once. |
| `docs/dev/HISTORY.md` | What happened per program, with the gotchas that exist nowhere else. |
| `docs/dev/DESIGN.md` | The desktop UI contract (with `design-notes.md`, `wireframes.md`). |
| `docs/dev/ADR.md` | The numbered table the code cites as "ADR row N". |
| `docs/dev/RUNBOOK.md` | How to run the smoke harness. |
| `docs/dev/requirements/` | Dated asks, verbatim. Later wins over earlier. |
| `docs/dev/SPIKES.md` | Verdicts of work that was never shipped. |

**Where a new fact goes.** A measurement → `BENCHMARKS.md`. A decision → `DECISIONS.md` (plus the
`ARCHITECTURE.md` edit, same commit). A gate result → the `ROADMAP.md` table, with the command that
produced it. What happened in a program → `HISTORY.md`. **Never write a per-lane note file** —
about 120 of them accumulated in eleven days, each citing the others, and no reader could tell
which were still true.

## Working in a shared worktree

Several agents may be in one worktree at once. These are not style preferences; each one cost a
lane real work.

- **Stage only your own files.** `git add -A` swept another lane's uncommitted work into the wrong
  commit three times in one day — the content was right, the attribution was not.
- **Never `git stash`.** It takes every other lane's work with it.
- **One Playwright run at a time**, guarded by `/tmp/tit-e2e.lock`. Runs share the mock server on
  8790 and one `out/`, so a second run's build lands under an executing suite. Never
  `pkill -f "playwright test"` — it kills whoever else is mid-gate.
- **`pnpm run pree2e` before any scene spec** (`VITE_SCENE_HOOKS=1`), and a plain `pnpm run build`
  **last**: the dev container serves `desktop/out/renderer` straight from the worktree, so a plain
  build before a real run makes specs time out 30 s later with no hint why.
- **Verify path and filesystem behaviour in the container** (Python 3.11, case-sensitive), never on
  the macOS host.
- **Never recreate the maintainer's dev container.** It bind-mounts the worktree for both `tit` and
  the UI bundle; a recreated one from the plain `docker run` line serves the image's baked copies
  instead.

## Gate checklist

Run all of it, and report the numbers rather than "green":

```
npm run typecheck && npm run lint          # in desktop/
npx vitest run                             # in desktop/
python3 -m pytest tests/ -q                # repo root
python3 dev/route_import_guard.py && python3 dev/contracts_check.py
TIT_E2E_OFFSCREEN=1 npm run e2e:quiet      # full mock suite, serial, under the lock
npx playwright test --project=real …       # against the dev container
pnpm run build                             # LAST
```

`tests/test_scene_guide.py` has one known order-dependent failure in a full run that passes
standalone; confirm it in isolation rather than treating it as a red.

## Development Workflow

1. **Feature development**: Discuss in issue before implementing
4. **Documentation**: Update relevant README if behavior changes
5. **Version bumps**: Update `pyproject.toml` and changelog

## CI/CD

- **CircleCI** - Automatic test runs on PR
- **codecov** - Coverage tracking
- **Docker Hub** - Container registry at `idossha/`

## Getting Help

- Check module-specific READMEs in each directory
- API docs in `docs/api_mkdocs/`
