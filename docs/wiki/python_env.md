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
| Install TI-Toolbox (editable) | `simnibs_python -m pip install -e /ti-toolbox` |


### Key Points

- **Containerized Setup**: The environment is defined in `container/blueprint/Dockerfile.simnibs`, which installs SimNIBS v4.5.0 and additional Python packages (meshio, nilearn, PyOpenGL-accelerate, trimesh, seaborn) required for TI-Toolbox functionality.

- **Python package name (`tit`)**: The installable Python package for TI-Toolbox is **`tit`** (not `ti-toolbox`). When `tit` is installed (e.g. via the editable install above), you can run modules with:

  - `simnibs_python -m tit.opt.flex ...`
  - `simnibs_python -m tit.opt.ex ...`

  And import from Python with:

  - `from tit.opt.flex import ...`
  - `from tit.opt.ex import ...`

- **Script executions**: All python scripts should be executed using `simnibs_python` (e.g. `simnibs_python script.py`).
