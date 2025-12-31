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

- **Containerized Setup**: The environment is defined in `container/blueprint/Dockerfile.simnibs`, which installs SimNIBS v4.5.0 and additional Python packages (meshio, nilearn, PyOpenGL-accelerate, trimesh, seaborn) required for TI-Toolbox functionality.

- **Script executions**: All python scripts should be executed using the `simnibs_python script.py`.
