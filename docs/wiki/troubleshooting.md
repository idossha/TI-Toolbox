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

The page has two parts. **Part 1** covers things outside the toolbox's control — Docker, X11, your machine, upstream tools — and explains them fully. **Part 2** is a compact list of toolbox bugs that have already been fixed: if you hit one, the answer is *upgrade*. Search the page (Ctrl/Cmd-F) for your error text.

---

# Part 1 — Environment problems (Docker, display, machine, upstream tools)


## Dev desktop shows the image's old UI

An early v3 Electron launcher handoff cleared the requested checkout before starting Docker.
The container could therefore serve its baked UI despite starting through a dev loader.

Use the updated `dev/loader/loader_dev.sh --desktop --project /path/to/project`.
Development launches now preserve the checkout mount and serve its built renderer.
If an existing container was started with the old configuration, finish its jobs before stopping
it and starting the corrected loader. Rebuild local frontend changes with
`npm --prefix desktop run build`.


## Desktop application

### What should happen when I close the app or switch projects?

Closing the desktop app stops the project's container and exits Electron. To change projects
without quitting, use Switch project in Overview, type a path or browse, and confirm the new project.
Terminal loaders open the browser by default, so they return after opening the page. With explicit
`--desktop`, the terminal waits until Electron exits, then prints “TI-Toolbox closed.” on success.

### Quit warns about active jobs when none are running

An early v3 development build counted historical `skipped` and `lost` jobs as active during
shutdown. Both are terminal states. The quit check now counts only `running` and `queued` jobs,
matching the job model; an idle session closes without a job warning. Rebuild/relaunch the updated
desktop application. No job records need to be deleted or changed.

### A `.nii.gz` mask is grayed out in the file picker

Early development builds filtered only `.nii` and the compound `.nii.gz` extension, which macOS
may not recognize in its native chooser. The picker now includes gzip files and validates that
the selected file is a `.nii` or `.nii.gz` NIfTI mask before importing. Refresh the updated UI
and reopen the picker. Unrelated gzip archives are rejected.

### Switching tabs resets a draft or 3D camera

**Applies to:** early 3.0.0 development builds.
**Cause:** route navigation unmounted pages and their embedded renderers; a shared subject selection
also changed hidden workflows. The September 4 polishing update retains visited pages and gives
each tab its own subject context. Closing/switching projects intentionally starts a new session.
**Fix:** restart the updated desktop client once. In development, use `npm run dev` from `desktop/`.
The Simulator, Optimizer and Analyzer previews also require the viewport-capable Tetravox bundle;
an older protocol-2 bundle can still show its full application chrome.

### A 3D preview never leaves "Loading"

**Cause:** older builds removed a failed iframe, cleared its error during cleanup, and immediately
loaded it again. A missing/unusable embed bundle could therefore appear to load forever.
**Fix:** the updated preview keeps the error visible and offers **Retry 3D preview**. A locally built
embed must use the installed layout: `index.html`, `assets/` and the generated `manifest.json` in
one served directory. Raw Vite `dist/` output lacks the manifest; the release installer flattens
the packaged `dist/` correctly. Do not fabricate a manifest for an unknown build.

### Analyzer stays at "Building … scene" with repeated atlas errors

**Cause:** the atlas builder accessed `TvscPayload.triangles`, but decoded meshes expose `indices`.
The frontend then retried the server's one-shot HTTP 500, starting another build; stale HTTP 202
data kept the preview at "Building". This is not evidence of a corrupt subject or a slow mesh.
**Fix:** the updated builder uses the decoded index array. Manifest/atlas failures now stop polling,
show the server's message and offer **Retry 3D preview**. Do not delete head models or cached surfaces
to work around this development defect.

If a cold atlas preview shows duplicate skin/cortex surfaces, update the desktop as well: its first
scene now waits for the required atlas instead of racing a temporary anatomy scene against it.

### Simulator shows a guide instead of the selected subject's EEG net

**Cause:** an early internal build failed to encode the tissue-label path in a subject scene
manifest. The preview fell back to reference anatomy, whose packaged nets are limited.
**Fix:** pull the rebuilt internal image and restart it, or refresh the updated development app.
Subject nets are read from the existing head model; regenerating the model is unnecessary.

### Viewer fails only for some mixed mesh/volume selections

**Cause:** a solid mesh's saved `field: null` value reached controls expecting an absent field.
If that mesh loaded first, the controls crashed and cancelled the remaining scene load.
**Fix:** use the rebuilt internal image with the compatible viewer bundle. New scenes omit the
empty field and the viewer accepts older scenes containing it; source files need no repair.

## Docker

### Docker image store is corrupted — `blob sha256:… not found` (historical recovery record)

**Historical v2 recovery record:** seen on Ubuntu / EC2. The image names, disk estimates
and FreeSurfer volume below belong to that version. For the current image, follow the
[installation guide]({{ site.baseurl }}/installation/).
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

### `Error: simnibs service is not running. Please check your docker-compose.yml and container logs.` (historical v2)

**Applies to:** any OS, `python3 loader.py`.
**Situation:** images pull fine, "Starting services…", then this line.
**Cause:** `docker compose up` failed or the container exited immediately. The usual environmental reasons: port **8888** already in use (another Jupyter or toolbox instance); an **arm64 host** (Apple Silicon without Rosetta, AWS Graviton) running the `linux/amd64` image with no emulation → `exec format error`; the Docker daemon out of disk. (Loaders before 2026-08-26 hid compose's own message — update `loader.py` to see it.)
**Fix:**
1. `git pull` so `loader.py` prints compose's error, the container status and its last log lines.
2. Or by hand: `docker ps -a --filter name=simnibs_container` and `docker logs --tail 50 simnibs_container`.
3. Port clash: stop whatever holds 8888 (`docker ps`, `sudo lsof -i :8888`).
4. `exec format error` / platform mismatch: use an x86-64 machine, or install emulation (`docker run --privileged --rm tonistiigi/binfmt --install amd64`) and expect it to be slow.
**Source:** maintainer-verified, 2026-08-26.

### `unknown shorthand flag: 'f'` / `docker: unknown command: docker compose` (Windows)

**Applies to:** Windows, running the loader from a shell.
**Cause:** the `docker compose` v2 plugin is not available in that shell — Docker Desktop's WSL integration is off for the distro.
**Fix:** Docker Desktop → Settings → Resources → WSL Integration → enable your distro → Apply & Restart; verify with `docker compose version`. The desktop app is unaffected.
**Source:** [#65](https://github.com/idossha/TI-Toolbox/discussions/65).

### FreeSurfer container stuck in a `Restarting` loop / `nu_correct: Command not found` (Windows) (historical v2)

**Applies to:** Windows 11, WSL2, Docker Desktop.
**Situation:** `simnibs_container` runs but `freesurfer_container` restarts forever; the desktop launcher times out after 300 s.
**Cause:** Docker Desktop / WSL configuration edge case on that machine. The FreeSurfer image is only used as a data volume, so a restarting container is not by itself fatal to the SimNIBS side.
**Fix:** launch with `python3 loader.py` (docker compose) instead of the desktop app; re-download the current `loader.py` and `docker-compose.yml`; then work from the GUI or CLI inside the container.
**Source:** [#71](https://github.com/idossha/TI-Toolbox/discussions/71).

### Docker not running / images not downloading / first launch takes very long

**Applies to:** any OS, first run of a new version.
**Cause:** a missing image must be loaded before the server starts. A Docker daemon that is not running, limited disk space or a slow image download can delay startup.
**Fix:** start Docker Desktop (`sudo systemctl start docker` on Linux), confirm the daemon is ready, and check the launcher progress and Docker disk usage. Follow the [installation guide]({{ site.baseurl }}/installation/) for the matching image.

### CHARM killed / simulations slow — insufficient Docker memory

**Applies to:** macOS and Windows (Docker Desktop VM).
**Error:** `charm: line 2: … Killed` during meshing; or the Optimizer later reports `.msh file not found` because the mesh was never produced.
**Cause:** Docker Desktop's VM memory limit (not the machine's RAM) is too low; CHARM needs well over 8 GB.
**Fix:** Docker Desktop → Settings → Resources → Memory: 32 GB recommended, 16 GB minimum; close other heavy apps; validate with the bundled `ernie` example. Then re-run the m2m step.
**Source:** [#119](https://github.com/idossha/TI-Toolbox/discussions/119), [#121](https://github.com/idossha/TI-Toolbox/discussions/121), [Dependencies]({{ site.baseurl }}/installation/dependencies/).

### Preprocessing appears frozen for many hours

**Check progress:** open [Jobs]({{ site.baseurl }}/wiki/jobs/) to inspect the stage and live log. CHARM and FastSurfer can run for a long time, especially under emulation on Apple Silicon; a quiet interval alone does not establish that a job is stuck. The original discussion below concerns the historical FreeSurfer workflow.
**Source:** [#93](https://github.com/idossha/TI-Toolbox/discussions/93).

## Command-line launchers

### No-argument loader exits with "no project directory given"

**Applies to:** earlier loader revisions, including the initial `release/3.0.0` candidate.
**Cause:** the launcher required an explicit project and had no terminal project prompt.
**Fix:** update the source checkout. Running `loader.py`, `loader.sh`,
`dev/loader/loader_dev.py`, or `dev/loader/loader_dev.sh` without arguments in a terminal
now prompts only for the project and remembers the last selected path. For scripts or other
noninteractive sessions, pass `--project` and any
other settings explicitly. See the [launcher reference]({{ site.baseurl }}/installation/bash-cli/#launch)
for `--interactive`, reconnect behavior, and advanced command-line options.

## Launching (historical v2)

For the current launcher, use the [installation guide]({{ site.baseurl }}/installation/).
The entry below records the old container layout.

### Container cannot find the project / subject not listed in the GUI (Linux terminal)

**Applies to:** Linux, launching the container by hand.
**Cause:** the container was started without `loader.py`, so `PROJECT_DIR_NAME` and the `/mnt/<project>` bind mount were never set; or the toolbox was launched against a different project than the one holding the subject.
**Fix:** always launch with `python3 loader.py` (repository root — `loader.sh` no longer exists) and point it at the project; verify inside the container with `echo $PROJECT_DIR_NAME` and `ls /mnt/`. One project per session — relaunch to switch. Jupyter: open `http://localhost:8888` in the host browser.
**Source:** [#95](https://github.com/idossha/TI-Toolbox/discussions/95), [#84](https://github.com/idossha/TI-Toolbox/discussions/84).

## GUI display (X11, historical v2)

> **Historical v2 instructions.** The current desktop application and command-line launcher
> use the same single-image server and browser UI, with no Qt or X11. This section records
> fixes for the removed v2 GUI; it does not apply to the
> [current command-line launcher]({{ site.baseurl }}/installation/bash-cli/).

### No GUI on macOS — Qt XCB / `could not connect to display` / Qt5Agg error

**Applies to:** macOS (Sequoia, Tahoe), XQuartz.
**Cause:** X11 forwarding not configured on the host: XQuartz must allow network clients, Docker must be allowed by `xhost`, and `DISPLAY` inside the container must be `host.docker.internal:0`.
**Fix:**
1. Install **XQuartz 2.7.7** (not newer), log out and back in, launch XQuartz.
2. XQuartz → Preferences → Security → *Allow connections from network clients*.
3. Launch with `python3 loader.py` — it sets `DISPLAY` and runs `xhost` for you. Never `docker run` by hand.
CLI tools work regardless of X11.
**Source:** [#55](https://github.com/idossha/TI-Toolbox/discussions/55), [#70](https://github.com/idossha/TI-Toolbox/discussions/70).

### No GUI on Linux

**Fix:** `xhost +local:docker`; check `echo $DISPLAY` (set `export DISPLAY=:0` if empty); launch via `loader.py`. On a headless server (cloud VM) there is no display — use the CLI / JSON runners, or SSH with `-X`.

### No GUI on Windows

**Fix:** VcXsrv must be running (system tray) with *Multiple windows*, *Start no client*, and **Disable access control checked**; restart VcXsrv; check Windows Firewall is not blocking it. The first launch of a new version can take several minutes while images pull ([#118](https://github.com/idossha/TI-Toolbox/discussions/118)).

### Gmsh / Freeview windows misbehave on macOS 26+

**Cause:** X11 regressions on macOS 26 with these two viewers.
**Fix:** use the NIfTI Visualizer tab for NIfTI outputs; open `.msh` files in a host-installed Gmsh if needed.

### ROI looks incomplete in Gmsh

**Cause:** Gmsh shows only surfaces by default; or the ROI is mostly white matter while only GM was enabled.
**Fix:** Gmsh → Tools → Visibility → tick *Surfaces* and *Volumes* → Apply; or re-run with GM+WM.
**Source:** [#117](https://github.com/idossha/TI-Toolbox/discussions/117).

## Your data

### macOS `._*` (AppleDouble) files in `sourcedata/`

**Cause:** macOS writes `._<name>` sidecars onto non-APFS media (USB drives, network shares). Inside the container they raise `Operation not permitted` on `stat`. The toolbox skips them since v2.4.0, but they still pollute directories and confuse other tools.
**Fix:** `dot_clean -m sourcedata/` on the Mac, or `find sourcedata -name '._*' -delete`.

### Folder-name case: `CT/` vs `ct/`, `T1w/` vs `t1w/`

**Cause:** the container filesystem is case-sensitive; macOS and Windows are not, so two spellings that look like one folder on your machine are two folders in the container.
**Fix:** keep exactly one spelling per modality folder, matching the [pre-processing layout]({{ site.baseurl }}/wiki/pre-processing/).

### `recon-all` fails with `ERROR! FOV=282.000 > 256`

**Applies to:** optional FreeSurfer reconstruction, including resumed legacy projects.
**Cause:** FreeSurfer's 256 mm field-of-view limit — typical for templates such as MNI152 or large-FOV clinical scans.
**Fix:** use an appropriately cropped/conformed input for FreeSurfer, preserving the intended anatomy. If your workflow does not need full reconstruction or subregions, select the recommended FastSurfer segmentation instead; see [Pre-processing]({{ site.baseurl }}/wiki/pre-processing/).
**Source:** [#94](https://github.com/idossha/TI-Toolbox/discussions/94).

### DWI has no `.bval`/`.bvec`, or the pre-flight rejects it

**Cause:** the DICOM series was not a diffusion acquisition (e.g. a 2-volume clinical b=0 scan), or the gradient table did not travel with the NIfTI.
**Fix:** the pre-flight checks that the table exists, parses, matches the NIfTI's volume count and has enough distinct b>100 directions. If it fails, QSIPrep cannot process the data either — verify the acquisition. Tip: in a QSIPrep log, count the `…_b0-NN.nii.gz` files listed by `gather_inputs` against `dim[4]` to see what the b-table actually contains.

### Bilateral target with a unipolar montage

Not possible with two pairs. Use a large sphere covering both targets if focality is not critical, or an mTI montage.
**Source:** [#89](https://github.com/idossha/TI-Toolbox/discussions/89).

## Upstream tools (QSIPrep, QSIRecon, SimNIBS)

### QSIPrep crashes with `TypeError: must be real number, not NoneType` (TotalReadoutTime)

**Applies to:** QSIPrep 26.0.0 and every version since 2019; any DWI sidecar lacking `TotalReadoutTime`.
**Cause:** upstream bug in `qsiprep/interfaces/epi_fmap.py` — the value is read with a bare `.get()` and formatted into an FSL `acqp` line; the code path runs under `--hmc-model eddy` even with no fieldmap. Reported four times upstream, never fixed.
**Fix:** the toolbox pre-flight (main, → v2.4.1) derives `TotalReadoutTime` or writes a provably inert fallback before the container starts. Manually: add `"TotalReadoutTime"` and `"PhaseEncodingDirection"` to `sub-<id>/dwi/sub-<id>_dwi.json`.

### QSIRecon `dsi_studio_gqi` — `Cannot set the undefined 'plot_reports' attribute`

**Cause:** upstream QSIRecon bug in the `dsi_studio_gqi` spec.
**Fix:** v2.3.1+ uses QSIRecon 26.0.0 (`--input-type qsiprep`) with the toolbox's own recon YAML; the `dsi_studio_*` specs are not used.
**Source:** [#81](https://github.com/idossha/TI-Toolbox/discussions/81).

### Running QSIRecon yourself: `Path should point to a file (or symlink of file): .`

**Cause:** the FreeSurfer license path handed to QSIRecon does not exist — with Docker-out-of-Docker the license must be given as a **host** path.
**Fix:** set `LOCAL_FS_LICENSE=/host/path/license.txt`; `FS_LICENSE` is the fallback. (The toolbox does this itself since v2.4.0.)

### SimNIBS 4.6 quirks the image patches for you

`np.nan_to_num(copy=None)` on numpy 1.x and `atlas2subject(split_labels=True)` label misalignment are patched into the image at build time (`resources/patches/`, `resources/atlas2subject/`). If you install SimNIBS 4.6 outside the container, you get them raw.

### Ex-search needs a leadfield

Exhaustive search requires a pre-computed leadfield for the *same EEG net* as the montage (`derivatives/SimNIBS/sub-<id>/leadfields/`). Run that step first.

### `TI_normal` cannot be analysed in voxel space

By design — `TI_normal` only exists on the cortical surface. Select *Space = mesh* for it; use `TI_max` (or `mTI_max`) for voxel analyses.

---

# Part 2 — Toolbox bugs already fixed: upgrade

These entries record fixes to older versions. The historical *main* label means the fix
was on the main branch when the entry was recorded. Older-version workarounds are retained
for reference; use the [installation guide]({{ site.baseurl }}/installation/) for current setup.

| Symptom | Fixed in | Note / workaround on older versions | Source |
|---|---|---|---|
| `dev/loader/loader_dev.py`: `ModuleNotFoundError: No module named 'tit'` | main | `git pull` | 2026-08-26 |
| `dev/loader/loader_dev.sh`: `unbound variable` on first run | main | | |
| `loader.py` hides the real `docker compose` error behind "simnibs service is not running" | main | see Part 1 for the environmental causes | |
| Analyzer "Field" dropdown had no effect; voxel analysis silently used `TI_avg` | main | re-run analyses made with `TI_avg` enabled | |
| mTI outputs named `TI_Max` not found by the analyzer (field renamed `mTI_max`) | main | rename `*_TI_Max.*` → `*_mTI_max.*`, or re-run | |
| Flex-search current-ratio search: final field at 1:1 while `flex_meta.json` claims the optimised split | main | re-run affected optimisations | |
| Ex-search mTI + Atlas ROI "completed successfully" with zero runs | main | | |
| Ex/mex config with `roi_names=[]` and no atlas scored every montage 0 (now a `ValueError`) | main | | |
| QSIRecon refuses to rerun ("output already exists") although nothing was reconstructed | main | delete `<out>/sub-<id>/` (logs only) | |
| Analyzer simulation list empty when the first subject has no simulations | v2.4.0 | switch subject and back | |
| DICOM import crashes with `PermissionError: [Errno 1]` on `._*` files | v2.4.0 | delete the `._*` files (Part 1) | PR #133 |
| DICOMs silently skipped when `CT/` and `ct/` both exist | v2.4.0 | keep one spelling | |
| QSIRecon: `Path should point to a file: .` (license mounted as `None`) | v2.4.0 | set `LOCAL_FS_LICENSE` | [#81](https://github.com/idossha/TI-Toolbox/discussions/81) |
| QSI preflight: `Host project directory does not exist: C:/…` on Windows | v2.3.2 | | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| `recon-all output already exists` on a fresh project (empty dir pre-created) | v2.3.2 | delete the empty `derivatives/freesurfer/sub-<id>/` | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| DWI DICOMs never converted (only T1w/T2w) | v2.3.2 | | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| Zipped DICOM folder ignored; empty `T1w/dicom/` created | v2.3.1 | unpack into `sourcedata/sub-<id>/T1w/dicom/` | [#90](https://github.com/idossha/TI-Toolbox/discussions/90) |
| `Labeling.nii.gz not found`, `simnibs_python` not in `$PATH`, `subject_atlas: unrecognized arguments: -m`, `NoneType copy mode not allowed` (SimNIBS 4.6 transition) | v2.3.1 | | [#80](https://github.com/idossha/TI-Toolbox/discussions/80) |
| Linux desktop app: QSIPrep `failed to connect to the docker API at unix:///var/run/docker.sock` | v2.3.1 | reinstall the desktop app | [#80](https://github.com/idossha/TI-Toolbox/discussions/80) |
| Flex-search report missing EEG mapping / electrode configuration | v2.3.1 | the electrode CSVs feed the simulator regardless | [#94](https://github.com/idossha/TI-Toolbox/discussions/94) |
| Focality step 2/2: `'FlexSearchTab' object has no attribute 'volume_atlas_display_map'` | v2.3.0 | | [#89](https://github.com/idossha/TI-Toolbox/discussions/89) |
| Cortical atlas dropdown empty in flex-search (`.annot` files not generated) | v2.2.4 | inside the container: `subject_atlas -m /mnt/<project>/derivatives/SimNIBS/sub-X/m2m_X -a DK40 -o …/m2m_X/segmentation` | [#72](https://github.com/idossha/TI-Toolbox/discussions/72) |
| `loader.sh` missing from the repository | v2.2.x | it became `loader.py` | [#84](https://github.com/idossha/TI-Toolbox/discussions/84) |

---

# Developer gotchas

For people scripting against `tit` or contributing code.

| Symptom | Cause / Fix |
|---|---|
| Script works on the host, fails in the container (or vice-versa) | The v3 scientific runtime uses SimNIBS Python and NumPy 2.3.5 on a case-sensitive filesystem; the host may differ. Verify against the current runtime with the [testing guide]({{ site.baseurl }}/wiki/development/), including real numerical tests when relevant. |
| `pytest` INTERNALERROR `Read-only file system: tests/logs/pytest.log` | `pytest.ini` writes a log; mount the repo **writable** (not `:ro`). |
| `python: not found` in the test container | Use `simnibs_python`. |
| Test container is very slow on Apple Silicon | It is amd64 under emulation; expect ~1 min for the suite, minutes for real SimNIBS scenarios. |
| `nibabel` `save()` to `.nii.gz` fails on a Docker bind mount | Write the `.nii` then gzip with the stdlib `gzip` module. |
| `ModuleNotFoundError: fsl / ants` | The SimNIBS container ships **no FSL and no ANTs** — only Python, nibabel, numpy, scipy (+ SimpleITK). |
| `mne` missing in a v3 container | The current image installs `mne>=1.5,<2` and `h5io`. Verify you are using the selected v3 image and `simnibs_python`, not another interpreter or a legacy image. |
| **V2 only:** `if some_combo and …` guard silently skips | PyQt5 `QComboBox.__len__` makes an empty combo falsy; use `is not None`. |
| `dcm2niix` produced zero NIfTIs | `-r` means **rename**, not recurse; recursion depth is `-d 9`. |
| Math does not render on the docs site | Kramdown only parses `$$…$$` (inline and display); single `$…$` is ignored. No bare `\|` inside math in a table cell. |
| NiiVue label atlas renders grayscale / washes the slice | `colormapLabel` as a load option is ignored — call `vol.setColormapLabel(cm)` and set `vol.alphaThreshold = true`, then `updateGLVolume()`. |
| **V2 only:** release script left `dev/loader/docker-compose.dev.yml` on the old tag | `dev/update/update_version.py` does not know that file; bump its `idossha/simnibs:vX` tag by hand. |

---

## Reporting something new

Open a [Q&A discussion](https://github.com/idossha/TI-Toolbox/discussions/new?category=q-a) and include: OS + version, TI-Toolbox version (Help → About, or `docker images`), the exact command or GUI action, the full error text, and the relevant file from `<project>/derivatives/ti-toolbox/logs/`. Once the fix is confirmed, a maintainer adds it here and links the thread. Also see [Discord](https://discord.gg/KKdjJk8f) for quick questions.

### Montage PNG contains the cap but no electrode overlays

Check the simulation log for `No such file or directory: convert`. Montage diagrams require
ImageMagick and the DejaVu font; both are included in the toolbox Docker image. Older internal
images omitted ImageMagick and could leave the copied blank template behind. Updated rendering
publishes the PNG only after every overlay and legend succeeds.

Existing affected diagrams can be regenerated without rerunning simulation, using the saved
`documentation/config.json` electrode pairs with `tit.tools.montage_visualizer.visualize_montage`.
The running local development container and its local internal image were repaired on 2026-09-09.

### Simulation fails on existing results after confirming overwrite

**Symptom:** `Found already existing simulation results in directory` names the montage's
`high_Frequency` directory even after choosing **Replace and rerun**. The job's stored
`overwrite` confirmation previously stopped at the scheduler and never reached SimNIBS.
Updated runners pass that confirmation to SimNIBS's supported repeated-run option; there
is no need to delete `simnibs_simulation*.mat` files manually.

In **Settings**, enable **Allow unsafe overrides** for this project, then run again and
confirm **Replace and rerun**. The permission is off by default, applies across job pages,
and does not suppress subsequent confirmations. When disabled, choose **Skip** or **Cancel**.
Use the current checkout with the development loader, or an image containing this fix.
