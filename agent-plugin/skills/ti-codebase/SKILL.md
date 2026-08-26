---
name: ti-codebase
description: TI-Toolbox codebase patterns, module graph, conventions and architecture. Use when reading or modifying source under tit/ (developers).
user-invocable: false
---

# TI-Toolbox Codebase Guide

## Module Dependency Graph

```
tit/__init__.py
  +-- tit.paths        (PathManager singleton, depends on tit.constants)
  +-- tit.constants     (pure constants, no internal deps)
  +-- tit.logger        (setup_logging, add_file_handler, add_stream_handler — no internal deps)

tit.sim
  +-- tit.sim.config    (dataclasses: SimulationConfig, ElectrodeConfig, LabelMontage, XYZMontage, etc.)
  +-- tit.sim.utils     (run_simulation, load_montages — depends on config, paths, SimNIBS)
  +-- tit.sim.simulator (main entry point — depends on utils, config, paths)

tit.opt
  +-- tit.opt.config    (FlexConfig, ExConfig, SphericalROI, AtlasROI, etc.)
  +-- tit.opt.flex.flex (run_flex_search — depends on opt.config, sim, SimNIBS, scipy)
  +-- tit.opt.ex.ex     (run_ex_search — depends on opt.config, sim, SimNIBS)

tit.analyzer
  +-- tit.analyzer.analyzer       (Analyzer class — depends on paths, SimNIBS mesh_io, nibabel)
  +-- tit.analyzer.field_selector (select_field_file helper)
  +-- tit.analyzer.group          (run_group_analysis — depends on analyzer)
  +-- tit.atlas                   (builtin_regions — re-exported from analyzer.__init__)

tit.config_io
  +-- depends on: tit.opt.config (ROI/electrode types), tit.sim.config (LabelMontage, XYZMontage)
  +-- used by: GUI tabs to serialize configs to JSON for subprocess calls

tit.gui
  +-- tit.gui.main       (MainWindow — imports all tabs, paths, logger, style)
  +-- tit.gui.*_tab      (each tab — depends on paths, config_io, Qt)
  +-- tit.gui.style      (APP_STYLESHEET, build_stylesheet, WINDOW_WIDTH/HEIGHT)
  +-- tit.gui.components (reusable widgets)
  +-- tit.gui.extensions (plugin system — dynamically loaded .py files)

tit.stats
  +-- tit.stats.config       (GroupComparisonConfig)
  +-- tit.stats.permutation  (statistical testing — depends on scipy, nibabel)

tit.pre
  +-- tit.pre.structural (run_pipeline — depends on paths, SimNIBS, FreeSurfer)

tit.reporting
  +-- tit.reporting.core.assembler    (ReportAssembler)
  +-- tit.reporting.core.protocols    (ReportMetadata, SeverityLevel)
  +-- tit.reporting.core.base         (ErrorReportlet)
  +-- tit.reporting.generators.base_generator (BaseReportGenerator — ABC)
  +-- tit.reporting.generators.*      (simulation, preprocessing, flex_search)
  +-- tit.reporting.reportlets.*      (text, images, metadata, references)
```

## Config-to-JSON-to-Subprocess Pattern (GUI Tabs)

The GUI uses a consistent pattern for running heavy operations:

1. **Build config dataclass** in the tab (e.g., `FlexConfig`, `ExConfig`, or a plain dict for analyzer)
2. **Serialize to JSON** via `tit.config_io`:
   - `serialize_config(config)` converts dataclass to dict (handles Enums via `.value`, nested dataclasses recursively, union types via `_type` discriminator)
   - `write_config_json(config, prefix="flex")` writes to a temp file and returns the path
3. **Launch subprocess** calling the module's `__main__.py` with the JSON path:
   - `simnibs_python -m tit.opt.flex config.json`
   - `simnibs_python -m tit.opt.ex config.json`
   - `simnibs_python -m tit.analyzer config.json`
4. **SimulatorTab is the exception**: it calls `run_simulation()` directly in a QThread (no subprocess)

The `_type` discriminator in `config_io` distinguishes union types during deserialization:
- ROIs: `SphericalROI`, `AtlasROI`, `SubcorticalROI`
- Electrodes: `PoolElectrodes`, `BucketElectrodes`
- Montages: `LabelMontage`, `XYZMontage`

## PathManager Singleton Pattern

**Initialization:**
```python
from tit.paths import get_path_manager
pm = get_path_manager("/path/to/project")  # sets project_dir on first call
pm = get_path_manager()                     # returns existing instance
```

**Auto-detection:** If no `project_dir` is passed, PathManager checks:
1. `PROJECT_DIR` environment variable
2. `PROJECT_DIR_NAME` env var combined with Docker mount prefix

**Key methods:**
- Zero-arg (project-level): `pm.derivatives()`, `pm.simnibs()`, `pm.config_dir()`, `pm.reports()`
- One-arg (subject): `pm.m2m(sid)`, `pm.simulations(sid)`, `pm.logs(sid)`
- Two-arg (subject+sim): `pm.simulation(sid, sim)`, `pm.ti_mesh(sid, sim)`
- Listing: `pm.list_subjects()` (m2m only), `pm.list_all_subjects()` (all locations), `pm.list_simulations(sid)`
- Utility: `pm.ensure(path)` creates dirs and returns path

**Reset in tests:**
```python
from tit.paths import reset_path_manager
reset_path_manager()  # sets global _path_manager_instance = None
```
The `conftest.py` fixture `_reset_path_manager` is `autouse=True` and runs after every test.

## Testing Strategy

**Mocked dependencies in conftest.py** (installed into `sys.modules` before any tit imports):
- `simnibs`, `simnibs.simulation`, `simnibs.simulation.sim_struct`, `simnibs.mesh_tools`, `simnibs.mesh_tools.mesh_io`, `simnibs.utils`, `simnibs.utils.transformations`
- `bpy`
- `scipy`, `scipy.optimize`, `scipy.spatial`, `scipy.spatial.transform`
- `nibabel`, `nibabel.freesurfer`
- `h5py`
- `matplotlib`, `matplotlib.pyplot`, `matplotlib.backends`, `matplotlib.backends.backend_pdf`, `matplotlib.lines`
- `pandas`
- `joblib`
- `nilearn`, `nilearn.plotting`, `nilearn.image`

**Real (not mocked):** `numpy` -- used for actual vector math in `calc.py` tests.

**Key fixtures:**
- `_reset_path_manager` (autouse) -- resets PathManager singleton after every test
- `tmp_project` -- creates a minimal BIDS directory tree under `tmp_path`
- `init_pm` -- initializes PathManager pointed at `tmp_project`

**pytest.ini settings:**
- `testpaths = tests`
- `--strict-markers` and `--strict-config` enabled
- Markers: `unit`, `integration`, `slow`, `requires_simnibs`, `requires_freesurfer`, `requires_data`, `gui`
- Log file: `tests/logs/pytest.log`

## Logger Design

**`setup_logging(level="INFO")`:**
- Gets the `"tit"` logger
- Clears all existing handlers
- Sets the level
- Sets `propagate = False` (never bubbles to root/terminal)
- Silences matplotlib/PIL loggers
- Adds NO handlers -- file-only by design

**`add_file_handler(log_file, level="DEBUG", logger_name="tit")`:**
- Creates parent dirs if needed
- Opens file in append mode
- Attaches a `FileHandler` with timestamp format to the named logger
- Returns the handler (so callers can remove it later)

**`add_stream_handler(logger_name="tit", level="INFO")`:**
- Attaches a `StreamHandler(sys.stdout)` with minimal `%(message)s` format
- Used by scripts and `__main__` entry points so `BaseProcessThread` can capture subprocess stdout for the GUI

**`get_file_only_logger(name, log_file, level="DEBUG")`:**
- Returns a standalone logger that writes ONLY to a file (no console)
- Clears any existing handlers, sets `propagate = False`
- Used for per-ROI or per-run logging

**GUI logging:** `_QtHandler(logging.Handler)` bridges logger signals to Qt console widgets (defined in GUI code, not in `tit/logger.py`).

## GUI Threading Pattern

- **QThread + signals:** Heavy operations run in QThread subclasses. Completion is signaled via Qt signals (e.g., `finished`, `analysis_completed`).
- **Never `.wait()` on main thread:** All cleanup happens via `finished` signal connections, not blocking waits.
- **`set_tab_busy()`:** `MainWindow.set_tab_busy(tab, busy, message, stop_btn)` disables all interactive widgets except the stop button and shows a status message. Re-enables on completion.
- **SimulatorTab** runs `run_simulation()` directly in QThread (best pattern -- no subprocess overhead).
- **Other tabs** (FlexSearch, ExSearch, Analyzer) serialize config to JSON and launch a subprocess via `BaseProcessThread`.

## How to Add New Components

### New Report Generator
1. Create `tit/reporting/generators/my_report.py`
2. Inherit from `BaseReportGenerator`
3. Implement required abstract methods:
   - `_get_default_title() -> str`
   - `_get_report_prefix() -> str`
   - `_build_report() -> None` (populate `self.assembler` with sections and reportlets)
4. Use existing reportlets from `tit/reporting/reportlets/` (text, images, metadata, references)
5. Call `self.generate(output_path)` to produce HTML

### New GUI Tab
1. Create `tit/gui/my_tab.py` as a `QWidget` subclass
2. Import and instantiate it in `tit/gui/main.py` inside `MainWindow.setup_ui()`
3. Add to `self.tab_widget.addTab(self.my_tab, "My Tab")`
4. For long operations: use QThread + signals, never block the main thread
5. For subprocess-based work: use the config_io JSON pattern

### New GUI Extension
1. Create `tit/gui/extensions/my_extension.py`
2. Define `EXTENSION_NAME = "My Extension"` at module level
3. Create a `QWidget` subclass -- it will be auto-discovered and loadable via the Extensions button

## Import Patterns (What Each __init__.py Exports)

**`tit/__init__.py`:**
- `setup_logging`, `add_file_handler`, `add_stream_handler` (from logger)
- `get_path_manager` (from paths)
- `paths`, `constants` (submodules)

**`tit/sim/__init__.py`:**
- Config: `SimulationConfig`, `ElectrodeConfig`, `IntensityConfig`, `LabelMontage`, `XYZMontage`, `MontageConfig`, `SimulationMode`, `ConductivityType`
- Functions: `run_simulation`, `load_montages`, `list_montage_names`, `load_montage_data`, `save_montage_data`, `ensure_montage_file`, `upsert_montage`

**`tit/opt/__init__.py`:**
- Config: `FlexConfig`, `FlexElectrodeConfig`, `FlexResult`, `ExConfig`, `ExCurrentConfig`, `ExResult`
- ROIs: `SphericalROI`, `AtlasROI`, `SubcorticalROI`
- Electrodes: `BucketElectrodes`, `PoolElectrodes`
- Enums: `OptGoal`, `FieldPostproc`, `NonROIMethod`
- Functions: `run_flex_search`, `run_ex_search`

**`tit/analyzer/__init__.py`:**
- `Analyzer`, `AnalysisResult`, `GroupResult`, `builtin_regions`, `run_group_analysis`, `select_field_file`

## File Size Warnings

Large files that require targeted line-range reads:

| File | Lines | Notes |
|------|-------|-------|
| `tit/gui/analyzer_tab.py` | 2731 | Monolithic tab -- use line-range reads |
| `tit/gui/ex_search_tab.py` | 2656 | Monolithic tab -- use line-range reads |
| `tit/gui/simulator_tab.py` | 1907 | Large but more manageable |
| `tit/gui/flex_search_tab.py` | 1725 | Large but more manageable |
| `tit/gui/nifti_viewer_tab.py` | 1330 | Medium-large |
| `tit/paths.py` | 462 | Moderate but dense -- many path methods |

All other modules are under 700 lines.
