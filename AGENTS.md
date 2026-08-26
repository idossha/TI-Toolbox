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
├── package/          # Electron desktop app (Docker orchestration, X11)
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
│   ├── gui/          # PyQt5 GUI (runs in Docker)
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
| `tit/gui/main.py` | GUI application main window |
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

## GUI Architecture

The GUI runs inside Docker with X11 forwarding:
- **Main Window**: `tit/gui/main.py` - Tab container
- **Large Tabs**: analyzer_tab.py (147KB), flex_search_tab.py (145KB)
- **Components**: Reusable widgets in `tit/gui/components/`
- **Extensions**: Plugin system in `tit/gui/extensions/`

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
