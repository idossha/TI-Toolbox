---
layout: wiki
title: Troubleshooting Archive
permalink: /wiki/troubleshooting/
---

The **single source of truth** for known problems, their causes and their verified fixes — for people and for AI assistants alike.

**How it works**

1. **Ask first on [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions/categories/q-a)** (Q&A). Use the form: OS, toolbox version, what you ran, the exact error, and the log from `<project>/derivatives/ti-toolbox/logs/`.
2. **Verified solutions are promoted here** by a maintainer, with a link back to the discussion. Only entries that were reproduced or confirmed by the reporter land on this page.
3. **AI assistants** using the [TI-Toolbox plugin]({{ site.baseurl }}/wiki/ai-assistant/) read this page through `search_wiki` / `read_wiki_page("troubleshooting")` — so a fix recorded here is a fix your assistant knows about.

Entry format: **Applies to → Situation → Error → Cause → Fix → Source**. Search the page (Ctrl/Cmd-F) for the error text.

---

## Docker

### Docker image store is corrupted — `blob sha256:… not found`

**Applies to:** any OS; seen on Ubuntu / EC2.
**Situation:** launching the toolbox (or any `docker images` call) after an interrupted pull, a full disk, or a reboot mid-download.
**Error:**
```
Error response from daemon: rpc error: code = NotFound desc = blob sha256:9e03764f… expected at /var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/…: not found
subprocess.CalledProcessError: Command '['docker', 'images', '--format', …]' returned non-zero exit status 1.
```
**Cause:** containerd's image metadata references a layer blob that no longer exists on disk. Metadata and blobs are written separately, so an interrupted pull or an out-of-space write leaves a dangling reference; every command that lists images then aborts. Not a toolbox bug.
**Fix:**
1. Check disk space first: `df -h /var/lib/docker` — a full disk is the usual trigger; you need ~25 GB free for the images.
2. Try `sudo docker system prune -af && docker pull idossha/simnibs:<version>`.
3. If prune fails with the same error, reset the store (destroys *all* local images/containers/volumes — project data is untouched, it lives outside Docker):
   ```bash
   sudo systemctl stop docker docker.socket containerd
   sudo rm -rf /var/lib/docker /var/lib/containerd
   sudo systemctl start containerd docker
   ```
   then relaunch; images are re-pulled and the FreeSurfer volume is re-seeded.
**Source:** maintainer-verified, 2026-08-26.

### `Error: simnibs service is not running. Please check your docker-compose.yml and container logs.`

**Applies to:** any OS, `python3 loader.py`.
**Situation:** images pull fine, "Starting services…", then this line.
**Cause:** `docker compose up` failed or the container exited immediately. Loaders before `2026-08-26` swallowed compose's own error, so the real reason was invisible. Common ones: port **8888** already in use (another Jupyter/toolbox instance); an **arm64 host** (Apple Silicon without Rosetta, AWS Graviton) running the `linux/amd64` image with no emulation → `exec format error`; a bind-mount source that does not exist; the Docker daemon out of disk.
**Fix:**
1. Update `loader.py` (`git pull`) — it now prints compose's error, the container status and its last log lines.
2. Otherwise run by hand: `docker ps -a --filter name=simnibs_container` and `docker logs --tail 50 simnibs_container`.
3. Port clash: `docker ps` → stop the container using 8888, or `sudo lsof -i :8888`.
4. `exec format error` / `platform mismatch`: use an x86-64 machine, or install emulation (`docker run --privileged --rm tonistiigi/binfmt --install amd64`) — expect it to be slow.
**Source:** maintainer-verified, 2026-08-26.

### FreeSurfer container stuck in a `Restarting` loop / `nu_correct: Command not found` (Windows)

**Applies to:** Windows 11, WSL2, Docker Desktop, desktop app (v2.2.x).
**Situation:** `simnibs_container` runs but `freesurfer_container` restarts forever; launcher times out after 300 s.
**Error:** `nu_correct: Command not found`, `Failed to launch: Command timed out after 300000 milliseconds: docker compose … up --build -d`.
**Cause:** Docker Desktop/WSL configuration edge case with the desktop launcher; the FreeSurfer image is only used as a data volume, so a restarting container is not itself fatal.
**Fix:** Launch with `python3 loader.py` (docker compose) instead of the desktop app; re-download the current `loader.py` and `docker-compose.yml`. v2.3.1+ launchers report the real error instead of timing out.
**Source:** [#71](https://github.com/idossha/TI-Toolbox/discussions/71).

### `unknown shorthand flag: 'f'` / `docker: unknown command: docker compose` (Windows)

**Applies to:** Windows, running the loader from a shell.
**Cause:** the `docker compose` v2 plugin is not available in that shell — Docker Desktop's WSL integration is off for the distro.
**Fix:** Docker Desktop → Settings → Resources → WSL Integration → enable your distro → Apply & Restart; verify with `docker compose version`. The desktop app is unaffected.
**Source:** [#65](https://github.com/idossha/TI-Toolbox/discussions/65).

### Docker not running / images not downloading / first launch takes very long

**Applies to:** any OS, first run of a new version.
**Cause:** the SimNIBS image is 5–10 GB and is pulled on the first launch of every new version; a Docker daemon that is not running or a slow connection looks like a hang.
**Fix:** start Docker Desktop (`sudo systemctl start docker` on Linux) and wait for it to be green; watch the pull in Docker Desktop → Images; ensure ≥20 GB free disk; pull manually with `docker pull idossha/simnibs:<version>` if needed. A window that only appears after several minutes on a first launch is normal ([#118](https://github.com/idossha/TI-Toolbox/discussions/118)).

### Simulations/CHARM slow or killed — insufficient Docker memory

**Applies to:** macOS and Windows (Docker Desktop VM).
**Error:** `charm: line 2: … Killed` during meshing, or silent slowness / OOM.
**Cause:** Docker Desktop's VM memory limit (not the machine's RAM) is too low; CHARM needs well over 8 GB.
**Fix:** Docker Desktop → Settings → Resources → Memory: 32 GB recommended, 16 GB minimum; close other heavy apps; validate with the bundled `ernie` example.
**Source:** [#119](https://github.com/idossha/TI-Toolbox/discussions/119), [Dependencies]({{ site.baseurl }}/installation/dependencies/).

---

## Launcher (`loader.py`, desktop app)

### `ModuleNotFoundError: No module named 'tit'` from `dev/loader/loader_dev.py`

**Applies to:** developers running the dev loader with the host `python3`.
**Cause:** the host Python does not have the `tit` package installed; the loader imported it for project initialisation.
**Fix:** fixed in commit `6681fd2b` (the loader now adds the checkout to `sys.path`) — `git pull` and rerun.
**Source:** maintainer-verified, 2026-08-26.

### Container cannot find the project / subject not listed in the GUI (Linux terminal)

**Applies to:** Linux, launching the container by hand.
**Cause:** the container was started without `loader.py`, so `PROJECT_DIR_NAME` and the `/mnt/<project>` bind mount were never set; or the toolbox was launched against a different project than the one holding the subject.
**Fix:** always launch with `python3 loader.py` and point it at the project; verify inside the container with `echo $PROJECT_DIR_NAME` and `ls /mnt/`. One project per session — relaunch to switch. Jupyter: open `http://localhost:8888` in the host browser.
**Source:** [#95](https://github.com/idossha/TI-Toolbox/discussions/95).

### `loader.sh` not found

**Cause:** the bash loader was replaced by `loader.py`.
**Fix:** use `python3 loader.py` (repository root).
**Source:** [#84](https://github.com/idossha/TI-Toolbox/discussions/84).

### Dev loader aborts with `unbound variable` on first run (`dev/loader/loader_dev.sh`)

**Cause:** `${!var}` under `set -u` with no `.default_paths.dev` yet.
**Fix:** fixed in `8e3a996d`; `git pull`.

---

## GUI display (X11)

### No GUI on macOS — Qt XCB / `could not connect to display` / Qt5Agg error

**Applies to:** macOS (Sequoia, Tahoe), XQuartz.
**Cause:** X11 forwarding not configured on the host: XQuartz must allow network clients and Docker must be allowed by `xhost`; `DISPLAY` inside the container must be `host.docker.internal:0`.
**Fix:**
1. Install **XQuartz 2.7.7** (not newer), log out and back in, launch XQuartz.
2. XQuartz → Preferences → Security → *Allow connections from network clients*.
3. Launch with `python3 loader.py` — it sets `DISPLAY` and runs `xhost` for you. Never `docker run` by hand.
4. If it still fails, run the legacy helper once: `bash dev/deprecated/config_sys.sh`, then relaunch.
CLI tools work regardless of X11.
**Source:** [#55](https://github.com/idossha/TI-Toolbox/discussions/55), [#70](https://github.com/idossha/TI-Toolbox/discussions/70).

### No GUI on Linux

**Fix:** `xhost +local:docker`; check `echo $DISPLAY` (set `export DISPLAY=:0` if empty); launch via `loader.py`.

### No GUI on Windows

**Fix:** VcXsrv must be running (system tray) with *Multiple windows*, *Start no client*, and **Disable access control checked**; restart VcXsrv; check Windows Firewall is not blocking it. The first launch of a new version can take several minutes while images pull ([#118](https://github.com/idossha/TI-Toolbox/discussions/118)).

### Gmsh / Freeview windows misbehave on macOS 26+

**Cause:** known X11 regressions on macOS 26 with these two viewers.
**Fix:** use the NIfTI Visualizer tab for NIfTI outputs; open `.msh` files in a host-installed Gmsh if needed.

---

## Preprocessing (DICOM → NIfTI, CHARM, recon-all)

### DICOM import crashes on projects seeded from macOS (`._*` AppleDouble files)

**Applies to:** any project copied from a Mac (Finder, external drive), v≤2.3.2.
**Error:** `PermissionError: [Errno 1] Operation not permitted` from `Path.is_file()` while scanning `sourcedata/`.
**Cause:** macOS writes `._<name>` sidecar files onto non-APFS media; inside the container (Python 3.11) `stat` on them raises EPERM, which pathlib propagates. Cannot reproduce on a modern host Python (3.13+ swallows it).
**Fix:** fixed in v2.4.0 (PR #133 — dotfiles are filtered by name before any `stat`). On older versions: `dot_clean -m sourcedata/` on the Mac, or `find sourcedata -name '._*' -delete`.

### DICOMs silently skipped: `CT/` vs `ct/` (case-sensitive container)

**Cause:** the container filesystem is case-sensitive; an auto-scaffolded lowercase `ct/` shadowed the user's populated `CT/`. Invisible on macOS/Windows hosts, which are case-insensitive.
**Fix:** fixed in v2.4.0 (non-empty case-variant is preferred). Keep one spelling per modality folder.

### Zipped DICOM folder not converted; empty `T1w/dicom/` created

**Applies to:** v2.3.0.
**Fix:** v2.3.1+ accepts `.zip/.tar/.tar.gz/.tgz` in the modality folder or its `dicom/` subfolder and rediscovers `.dcm/.dicom` recursively. Workaround on v2.3.0: unpack into `sourcedata/sub-<id>/T1w/dicom/`.
**Source:** [#90](https://github.com/idossha/TI-Toolbox/discussions/90).

### `recon-all output already exists` on a fresh project

**Applies to:** v2.3.1.
**Cause:** the pipeline pre-created an empty `derivatives/freesurfer/sub-<id>/` that the existence check then tripped on.
**Fix:** fixed (empty dirs are ignored). On old versions delete the empty folder, or choose *skip/replace existing outputs*.
**Source:** [#122](https://github.com/idossha/TI-Toolbox/discussions/122).

### `recon-all` fails with `ERROR! FOV=282.000 > 256`

**Cause:** FreeSurfer's 256 mm field-of-view limit — typical for templates such as MNI152.
**Fix:** recon-all is optional (it only adds FreeSurfer atlases); disable it for templates, or crop/conform the volume first.
**Source:** [#94](https://github.com/idossha/TI-Toolbox/discussions/94).

### Preprocessing appears frozen for many hours

**Expected runtimes:** CHARM ≈ 1–1.5 h, recon-all ≈ 4 h+. Check the System Monitor tab and `<project>/derivatives/ti-toolbox/logs/`. If it really is stuck, test with the bundled `ernie` NIfTI to rule out a bad input volume.
**Source:** [#93](https://github.com/idossha/TI-Toolbox/discussions/93).

### Optimizer says `.msh file not found` right after preprocessing "completed"

**Cause:** the CHARM step did not actually finish, so no head mesh exists in `m2m_<id>/`.
**Fix:** open the preprocessing report / CHARM log, fix the cause (usually memory — see Docker above), re-run the m2m step.
**Source:** [#121](https://github.com/idossha/TI-Toolbox/discussions/121).

### v2.3.0 (SimNIBS 4.6 transition) — `Labeling.nii.gz not found`, `simnibs_python` not in `$PATH`, `subject_atlas: unrecognized arguments: -m`, `ValueError: NoneType copy mode not allowed`

**Cause:** SimNIBS 4.5→4.6 changed the labeling filename case, the `simnibs_python` path and `subject_atlas`'s CLI, and 4.6 calls `np.nan_to_num(copy=None)` which numpy 1.26 rejects.
**Fix:** all fixed in v2.3.1; the numpy issue is patched into the image at build time (`resources/patches/patch_nan_to_num.py`). Upgrade; on Linux the desktop app had to be reinstalled to get the Docker socket mount for QSIPrep.
**Source:** [#80](https://github.com/idossha/TI-Toolbox/discussions/80).

---

## Diffusion (QSIPrep / QSIRecon)

### QSIPrep crashes with `TypeError: must be real number, not NoneType` (TotalReadoutTime)

**Applies to:** QSIPrep 26.0.0 (and every version since 2019), any DWI sidecar lacking `TotalReadoutTime`.
**Cause:** upstream bug in `qsiprep/interfaces/epi_fmap.py` — the value is read with a bare `.get()` and formatted into an FSL `acqp` line; the code path runs under `--hmc-model eddy` even with no fieldmap. Reported four times upstream, never fixed.
**Fix:** v2.4.1+ runs a pre-flight that derives `TotalReadoutTime` (or writes a provably inert fallback when there is no fieldmap and a single PE direction) before the container starts. Manually: add `"TotalReadoutTime"` and `"PhaseEncodingDirection"` to `sub-<id>/dwi/sub-<id>_dwi.json`.

### DWI has no `.bval`/`.bvec` — pre-flight warning, or QSIPrep fails immediately

**Cause:** the DICOM series was not a diffusion acquisition (e.g. a 2-volume clinical b=0 scan), or the gradient table did not travel with the NIfTI.
**Fix:** the pre-flight checks that the table exists, parses, matches the NIfTI's volume count and has enough distinct b>100 directions. If it does not, the data cannot be processed by QSIPrep; verify the acquisition. Tip: in a QSIPrep log, count the `…_b0-NN.nii.gz` files listed by `gather_inputs` against `dim[4]` to see the b-table content.

### QSIRecon: `Path should point to a file (or symlink of file): .`

**Cause:** the FreeSurfer license was mounted as `-v None:/opt/…` because `FS_LICENSE` was unset, or the container-internal license path was passed where Docker-out-of-Docker needs the *host* path.
**Fix:** fixed in v2.4.0; set `LOCAL_FS_LICENSE=/host/path/license.txt` (host path) when running Docker-out-of-Docker; `FS_LICENSE` is the fallback.
**Source:** [#81](https://github.com/idossha/TI-Toolbox/discussions/81).

### QSIRecon `dsi_studio_gqi` — `Cannot set the undefined 'plot_reports' attribute`

**Cause:** upstream QSIRecon bug in the `dsi_studio_gqi` spec.
**Fix:** v2.3.1+ uses QSIRecon 26.0.0 (`--input-type qsiprep`) with the toolbox's own recon YAML; older `dsi_studio_*` specs are not used.
**Source:** [#81](https://github.com/idossha/TI-Toolbox/discussions/81), [#80](https://github.com/idossha/TI-Toolbox/discussions/80).

### QSIRecon refuses to rerun: "output already exists" although nothing was reconstructed

**Cause:** QSIRecon 26 writes results to `<out>/derivatives/qsirecon-<suffix>/sub-<id>/`; `<out>/sub-<id>/` holds only logs/figures, and the old guard looked there.
**Fix:** fixed in `d0dd7834` (post-v2.4.0); delete `<out>/sub-<id>/` on older versions.

### QSI preflight: `Host project directory does not exist: C:/…` (Windows)

**Cause:** the pre-flight checked host-path visibility from inside the container, which never works on Windows.
**Fix:** fixed in v2.3.2; upgrade.
**Source:** [#122](https://github.com/idossha/TI-Toolbox/discussions/122).

### `Failed to pull pennlinc/qsiprep: failed to connect to the docker API at unix:///var/run/docker.sock` (Linux desktop app)

**Cause:** the compiled Linux desktop build did not mount the Docker socket.
**Fix:** delete and reinstall the desktop app (v2.3.1+ mounts the socket).
**Source:** [#80](https://github.com/idossha/TI-Toolbox/discussions/80).

---

## Optimization (flex-search, ex-search, mex-search)

### Cortical atlas dropdown is empty in flex-search

**Cause:** flex-search uses per-subject `.annot` files from `subject_atlas`, not the MNI NIfTI atlases; a preprocessing refactor (v2.2.3) stopped generating them.
**Fix:** v2.2.4+ creates them during m2m. For existing subjects, inside the container:
```bash
subject_atlas -m /mnt/<project>/derivatives/SimNIBS/sub-XXX/m2m_XXX -a DK40 \
  -o /mnt/<project>/derivatives/SimNIBS/sub-XXX/m2m_XXX/segmentation   # also a2009s, HCP_MMP1
```
**Source:** [#72](https://github.com/idossha/TI-Toolbox/discussions/72).

### Focality step 2/2: `'FlexSearchTab' object has no attribute 'volume_atlas_display_map'`

**Applies to:** v2.2.4. **Fix:** upgrade to v2.3.0+.
**Source:** [#89](https://github.com/idossha/TI-Toolbox/discussions/89).

### ROI looks incomplete in Gmsh

**Cause:** Gmsh shows only surfaces by default; or the ROI is mostly white matter while only GM was enabled.
**Fix:** Gmsh → Tools → Visibility → tick *Surfaces* and *Volumes* → Apply; or re-run with GM+WM.
**Source:** [#117](https://github.com/idossha/TI-Toolbox/discussions/117).

### Ex-search fails immediately — no leadfield

**Cause:** exhaustive search needs a pre-computed leadfield for the *same EEG net* as the montage.
**Fix:** run the leadfield step for that net first (`derivatives/SimNIBS/sub-<id>/leadfields/`).

### mTI + Atlas ROI in ex-search "completed successfully" with zero runs

**Applies to:** post-v2.4.0 main before `2fff5d8d`.
**Cause:** the GUI tried to read a synthetic `atlas_<labels>.csv` and swallowed the error.
**Fix:** fixed in `2fff5d8d`; upgrade.

### Flex-search current-ratio search: exported field does not match `current_split` in `flex_meta.json`

**Applies to:** main between `2af87c7d` and `58d946c0`.
**Cause:** the split was applied to attributes SimNIBS's FEM never reads (`ElectrodeArrayPair.current`) instead of the per-electrode `ele_current`; the final solve ran at 1:1.
**Fix:** fixed in `58d946c0`; re-run affected optimizations.

### Flex-search report missing EEG mapping / electrode configuration

**Cause:** report generation bug (v2.3.x).
**Fix:** the electrode name/coordinate files under the flex-search output feed the simulator directly regardless of the report; fixed in a later release.
**Source:** [#94](https://github.com/idossha/TI-Toolbox/discussions/94).

---

## Simulation & analysis

### Analyzer: `TI_normal is a surface (mesh) field and is not exported to NIfTI`

**Cause:** by design — `TI_normal` only exists on the cortical surface.
**Fix:** select *Space = mesh* for `TI_normal`; use `TI_max` (or `mTI_max`) for voxel analyses.

### Analyzer "Field" selector had no effect / voxel analysis silently used `TI_avg`

**Applies to:** main between `976dac6f` and `a70a62cf`.
**Cause:** the field choice never reached the backend, and the default picked the alphabetically-first NIfTI (`_TI_avg` sorts before `_TI_max`).
**Fix:** fixed in `a70a62cf`; re-run analyses made with `TI_avg` enabled.

### Older mTI outputs are not found by the analyzer (`TI_Max`)

**Cause:** as of `5734fe37` the multipolar envelope is named `mTI_max` (unipolar stays `TI_max`); files written earlier are named `…_TI_Max`.
**Fix:** re-run the mTI simulation, or rename `*_TI_Max.*` → `*_mTI_max.*` under `Simulations/<montage>/`.

### Analyzer simulation list empty for some subjects (v2.4.0)

**Cause:** a PyQt5 quirk — an empty `QComboBox` is falsy, so a `None`-guard skipped populating the list whenever the first subject had no simulations.
**Fix:** fixed in v2.4.1; switch the subject and back on v2.4.0.

### Bilateral targets with a unipolar montage

Not possible with two pairs; use a large sphere covering both targets if focality is not critical, or mTI.
**Source:** [#89](https://github.com/idossha/TI-Toolbox/discussions/89).

### Comparing two simulations

NIfTI Visualizer tab → group mode → load both volumes.

---

## Developer & scripting gotchas

These bite anyone scripting against `tit` or contributing code.

| Symptom | Cause / Fix |
|---|---|
| Script works on the host, fails in the container (or vice-versa) | The container is Python 3.11, numpy 1.26, case-sensitive FS; the host is not. **Verify in the container**: `docker run --rm -v "$PWD:/ti-toolbox" -w /ti-toolbox idossha/ti-toolbox-test:latest sh -c 'simnibs_python -m pytest tests -q'`. |
| `pytest` INTERNALERROR `Read-only file system: tests/logs/pytest.log` | `pytest.ini` writes a log; mount the repo **writable** (not `:ro`). |
| `python: not found` in the test container | Use `simnibs_python`. |
| Test container is very slow on Apple Silicon | It is amd64 and runs under emulation; expect ~1 min for the suite, minutes for real SimNIBS scenarios. |
| `nibabel` `save()` to `.nii.gz` fails on a Docker bind mount | Write the `.nii` then gzip with the stdlib `gzip` module. |
| `ModuleNotFoundError: fsl / ants` | The SimNIBS container ships **no FSL and no ANTs** — only Python, nibabel, numpy, scipy (+ SimpleITK). |
| `mne` missing in the container | Not installed by default; pin `mne~=1.5` (numpy 1.26 compatible) in `container/blueprint/Dockerfile.simnibs`. |
| `if some_combo and …` guard silently skips | PyQt5 `QComboBox.__len__` makes an empty combo falsy; use `is not None`. |
| `atlas2subject(split_labels=True)` labels misaligned | SimNIBS 4.6 bug; the image applies `resources/atlas2subject/patch_atlas2subject.py` at build time. |
| `np.nan_to_num(copy=None)` ValueError | SimNIBS 4.6 + numpy 1.x; patched at build (`resources/patches/patch_nan_to_num.py`). |
| `dcm2niix` produced zero NIfTIs | `-r` means **rename**, not recurse; recursion depth is `-d 9`. |
| Math does not render on the docs site | Kramdown only parses `$$…$$` (inline and display); single `$…$` is ignored. No bare `\|` inside math in a table cell. |
| NiiVue label atlas renders grayscale / washes the slice | `colormapLabel` as a load option is ignored — call `vol.setColormapLabel(cm)` and set `vol.alphaThreshold = true`, then `updateGLVolume()`. |
| Release script left `dev/loader/docker-compose.dev.yml` on the old tag | `dev/update/update_version.py` does not know that file; bump its `idossha/simnibs:vX` tag by hand. |
| Ex/mex config with `roi_names=[]` and no atlas | Now a `ValueError`; previously every montage scored 0. |

---

## Reporting something new

Open a [Q&A discussion](https://github.com/idossha/TI-Toolbox/discussions/new?category=q-a) and include: OS + version, TI-Toolbox version (Help → About, or `docker images`), the exact command or GUI action, the full error text, and the relevant file from `<project>/derivatives/ti-toolbox/logs/`. Once the fix is confirmed, a maintainer adds it here and links the thread. Also see [Discord](https://discord.gg/KKdjJk8f) for quick questions.
