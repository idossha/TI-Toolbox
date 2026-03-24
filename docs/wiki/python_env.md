---
layout: wiki
title: Python Environment
permalink: /wiki/python_env/
---

The TI-Toolbox operates within a containerized environment that includes SimNIBS. The `simnibs_python` interpreter is SimNIBS's bundled Python environment that provides all libraries for TI-Toolbox operations. If you want to add a package for a new feature, follow the steps below.

### Environment Management

| Task | Command |
|------|---------|
| Check location | `which simnibs_python` |
| List installed packages | `simnibs_python -m pip list` |
| Install package | `simnibs_python -m pip install <package>` |


### Key Points

- **Containerized Setup**: The environment is defined in `container/blueprint/Dockerfile.simnibs`, which installs SimNIBS v4.6.0 and additional Python packages (meshio, nilearn, PyOpenGL-accelerate, trimesh, seaborn) required for TI-Toolbox functionality.

- **Script executions**: All python scripts should be executed using the `simnibs_python script.py`.

### Import Patterns

As of v2.2.4, the `tit.core` sub-package has been dissolved. Modules that used to live under `tit.core` are now top-level within the `tit` package:

| Old import (removed) | New import |
|----------------------|------------|
| `from tit.core.paths import PathManager` | `from tit.paths import PathManager` |
| `from tit.core.constants import ...` | `from tit.constants import ...` |
| `from tit.core.calc import ...` | `from tit.calc import ...` |
| `from tit.core.errors import ...` | `from tit.errors import ...` |

**One-liner imports for common operations:**

```python
# Core (logging auto-initializes on import — no setup needed)
from tit import paths, constants

# Simulation
from tit.sim import SimulationConfig, run_simulation, load_montages

# Optimization
from tit.opt import FlexConfig, SphericalROI, run_flex_search

# Analysis
from tit.analyzer import Analyzer, run_group_analysis

# Statistics
from tit.stats import run_group_comparison, GroupComparisonConfig

# Preprocessing
from tit.pre import run_pipeline
```

**Lazy-loading notes:**
- `run_flex_search` is eagerly imported (safe -- SimNIBS is imported inside function bodies)
- `run_ex_search` must stay lazy (engine.py imports SimNIBS at module level)
- `run_group_comparison` and `run_correlation` stay lazy (permutation.py imports nibabel at module level)

### JSON Config Modules

Each major module can be invoked as a subprocess accepting a JSON config file:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
```

Config files are generated programmatically via `tit.config_io.write_config_json()`. See the [Scripting page]({{ site.baseurl }}/wiki/scripting/) for details.
