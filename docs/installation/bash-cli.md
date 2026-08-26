---
layout: installation
title: Python Loader / CLI Entrypoint
permalink: /installation/bash-cli/
---

The Python loader is the command-line way to start the TI-Toolbox containers. It is the same
Docker stack the [desktop application]({{ site.baseurl }}/wiki/desktop-app/) launches, without the
launcher window.

## Installation Steps

### Step 1: Download Required Files

Download both files into the **same folder**:

- **[loader.py](https://github.com/idossha/TI-toolbox/blob/main/loader.py)** — launch script (Python 3, standard library only)
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** — Docker service definitions (`idossha/simnibs:v2.4.0` and `idossha/ti-toolbox_freesurfer:v7.4.1`)

`loader.py` refuses to start if `docker-compose.yml` is not next to it.

## Usage

### Basic Launch

```bash
python3 loader.py
# or skip the project-directory prompt:
python3 loader.py --project-dir /path/to/my_project
```

`--project-dir` is the only command-line option. The script then:

1. **Checks the host** — Docker is installed, the daemon is running, and Docker Compose v2 is available. On macOS it also checks XQuartz/`xhost`; on Windows it reminds you to start an X server (VcXsrv) with "Disable access control" checked.
2. **Asks for the project directory** — the folder that will be mounted into the container as `/mnt/<project_name>`. The answer is remembered in `.default_paths.user` next to `loader.py`, so the next launch only asks you to confirm it. An empty folder is initialised as a new BIDS project.
3. **Pulls the Docker images** on first run (several GB) and starts the services with `docker compose up -d`. Older FreeSurfer data volumes from previous image versions are pruned automatically.
4. **Initialises the project inside the container** (creates `code/ti-toolbox/config/`, `sourcedata/`, `derivatives/SimNIBS/` and `derivatives/freesurfer/`).
5. **Attaches you to a shell** inside `simnibs_container`. When you `exit` that shell, the loader runs `docker compose down` and stops both containers.

### Inside the container

You land in `bash` as root. Your project is at `/mnt/<project_name>` and SimNIBS 4.6 (`simnibs_python`, gmsh), FreeSurfer 7.4.1, dcm2niix, Blender (as the `bpy` Python module) and the `tit` package are available.

Two shell aliases are defined:

```bash
GUI        # simnibs_python -m tit.gui.main   → the main TI-Toolbox window (needs an X server)
NOTEBOOK   # JupyterLab on http://localhost:8888 (no token; served from /mnt)
```

There are no other toolbox-specific shell commands. Every pipeline is a Python module that takes a JSON config as its only argument, exactly what the GUI writes before launching a job:

```bash
simnibs_python -m tit.pre       config.json   # pre-processing (dcm2niix, CHARM, recon-all)
simnibs_python -m tit.sim       config.json   # TI / mTI simulation
simnibs_python -m tit.opt.flex  config.json   # flex-search
simnibs_python -m tit.opt.ex    config.json   # ex-search
simnibs_python -m tit.opt.mex   config.json   # multipolar ex-search
simnibs_python -m tit.analyzer  config.json   # ROI / field analysis
simnibs_python -m tit.stats     config.json   # group statistics
simnibs_python -m tit.source    config.json   # EEG forward model / fsaverage mapping
simnibs_python -m tit.blender   config.json   # Blender renders
```

See the [Scripting]({{ site.baseurl }}/wiki/scripting/) page for the config formats and for calling the same functions from Python directly.

### Quick check

```bash
simnibs_python -c "import tit; print(tit.__version__)"
GUI
```

If the version prints and the GUI window appears, you are good to go.

### Attaching a second terminal

The loader keeps the containers running only while its shell is open. To open another shell in parallel (for example to run a script while the GUI is up):

```bash
docker exec -it simnibs_container bash
```
