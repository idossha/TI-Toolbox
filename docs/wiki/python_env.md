---
layout: wiki
title: Python Environment
permalink: /wiki/python_env/
---

TI-Toolbox runs inside a container that already has SimNIBS. `simnibs_python` is SimNIBS's own
bundled interpreter, and it is where the `tit` package is installed — every simulation,
optimization and analysis runs under it.

### Where you actually type Python

| | How to get there | What it is |
|---|---|---|
| **Notebooks, in the app** | The **Notebooks** page | JupyterLab-style notebooks running against a kernel *inside the container*, so `import tit` works with no setup. This is the normal way to script the toolbox in v3. |
| **Terminal, in the app** | The terminal pane on any run page | A shell inside the container. `simnibs_python -m tit.sim config.json` and friends. |
| **`docker exec`** | `docker exec -it ti-toolbox-<hash>-tit-1 bash` | The same shell from your own terminal. `tit launch --status` prints the container's name. |
| **Your host** | `pip install tit` | **Only the launcher.** `tit launch` starts the container; the science needs SimNIBS, which is in the image, not on your host. |

> The `tit` you install on the host with `pip install tit` is the same package, but a host
> interpreter almost never has SimNIBS, so `from tit.sim import run_simulation` will fail there.
> That is expected: on the host, `tit` is a launcher; in the container, it is the toolbox.
> See [the command-line launcher]({{ site.baseurl }}/installation/bash-cli/).

If you want to add a package for a new feature, follow the steps below.

### Environment Management

| Task | Command |
|------|---------|
| Check location | `which simnibs_python` |
| List installed packages | `simnibs_python -m pip list` |
| Install package | `simnibs_python -m pip install <package>` |


### Key Points

- **Containerized Setup**: The upcoming environment is defined in
  `container/blueprint/Dockerfile.ti-toolbox`, with scientific dependency constraints in
  `container/blueprint/runtime-constraints.txt`. Scientific preparation uses SimNIBS 4.6
  with NumPy 2.3.5. Montage rendering runs pinned standalone Blender 4.4.3 in a background
  process with its own Python environment; do not install `bpy` into SimNIBS or downgrade
  scientific NumPy to satisfy Blender. See [Blender Integration]({{ site.baseurl }}/wiki/blender/).
  Final candidate image acceptance remains pending; see the
  [full-net montage memory guidance]({{ site.baseurl }}/wiki/blender/#full-net-montage-memory)
  before allocating container resources.

- **Script executions**: Inside the container, run scripts with `simnibs_python script.py`, not `python`.

- **Changes do not survive a rebuild**: `simnibs_python -m pip install <package>` installs into the running container only. To keep it, add it to the Dockerfile and rebuild (`container/blueprint/build.sh`), or install it at the top of the notebook that needs it.

### Import Patterns

Since v2.2.4 the `tit.core` sub-package no longer exists. Modules that used to live under `tit.core` are now top-level within the `tit` package:

| Old import (removed) | New import |
|----------------------|------------|
| `from tit.core.paths import PathManager` | `from tit.paths import PathManager` |
| `from tit.core.constants import ...` | `from tit.constants import ...` |
| `from tit.core.calc import ...` | `from tit.calc import ...` |
| `from tit.core.errors import ...` | `from tit.errors import ...` |

**One-liner imports for common operations:**

```python
# Core (logging auto-initializes on import — no setup needed)
from tit import get_path_manager, paths, constants

# Simulation
from tit.sim import SimulationConfig, Montage, run_simulation, load_montages

# Optimization
from tit.opt import FlexConfig, run_flex_search
from tit.opt import ExConfig, run_ex_search

# Analysis
from tit.analyzer import Analyzer, run_group_analysis

# Statistics
from tit.stats import run_group_comparison, GroupComparisonConfig
from tit.stats import run_correlation, CorrelationConfig

# Preprocessing
from tit.pre import run_pipeline
```

All imports are eager — SimNIBS and nibabel are always available in the Docker environment.

### JSON Config Modules

Each major module can be invoked as a subprocess accepting a JSON config file:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.opt.mex    config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
simnibs_python -m tit.source     config.json
simnibs_python -m tit.blender    config.json
```

Config files are generated programmatically via `tit.config_io.write_config_json()`. See the [Scripting page]({{ site.baseurl }}/wiki/scripting/) for details.

### Running the toolbox from outside the app

The container's server has an HTTP API, so a script on your host can drive it without importing
`tit` at all — start it, then talk to it:

```bash
tit launch --project ~/datasets/000 --no-open       # prints the URL; the token is in the container
docker inspect ti-toolbox-<hash>-tit-1 \
  --format '{% raw %}{{range .Config.Env}}{{println .}}{{end}}{% endraw %}' | grep TIT_SERVER_TOKEN
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/jobs
```

The full route list is at `/api/openapi.json` on a running server. For anything heavier than a
status check, write a notebook in the app instead — it is already inside the container, with the
project mounted and `tit` importable.
