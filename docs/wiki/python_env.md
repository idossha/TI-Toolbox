---
layout: wiki
title: Python Environment
permalink: /wiki/python_env/
---

TI-Toolbox runs inside a container that wraps around SimNIBS. `simnibs_python` is SimNIBS's own
bundled interpreter, and it is where the `tit` package is installed — every simulation,
optimization and analysis runs under it.

Where you type Python — the **Notebooks** page, or `docker exec` into the container from your own
terminal — is covered under [Where scripts run]({{ site.baseurl }}/wiki/scripting/#where-scripts-run) on the Scripting page.
A run page's **Terminal** tab is a read-only job log, not a shell. Nothing is installed on your
host: the science needs SimNIBS, which is in the image.

If you want to add a package for a new feature, follow the steps below.

### Environment Management

| Task                    | Command                                   |
| ----------------------- | ----------------------------------------- |
| Check location          | `which simnibs_python`                    |
| List installed packages | `simnibs_python -m pip list`              |
| Install package         | `simnibs_python -m pip install <package>` |

### Key Points

- **Containerized Setup**: The environment is defined in
  `container/blueprint/Dockerfile.ti-toolbox`, with scientific dependency constraints in
  `container/blueprint/runtime-constraints.txt`. Scientific preparation uses SimNIBS 4.6
  with NumPy 2.3.5. Montage rendering runs pinned standalone Blender 4.4.3 in a background
  process with its own Python environment; do not install `bpy` into SimNIBS or downgrade
  scientific NumPy to satisfy Blender. See [Blender Integration]({{ site.baseurl }}/wiki/blender/).
  See the
  [full-net montage memory guidance]({{ site.baseurl }}/wiki/blender/#full-net-montage-memory)
  before allocating container resources.

- **Script executions**: Inside the container, run scripts with `simnibs_python script.py`, not `python`.

- **Installs do not survive the container**: `simnibs_python -m pip install <package>` installs into the running container only, and closing the app stops and removes that container — so the package is gone the next time you open the project, not only after an image rebuild. To keep it, add it to the Dockerfile and rebuild (`container/blueprint/build.sh`), or install it at the top of the notebook that needs it.

The `tit` imports and the `simnibs_python -m tit.<module> config.json` runners are listed on the
[Scripting page]({{ site.baseurl }}/wiki/scripting/), which owns them.
