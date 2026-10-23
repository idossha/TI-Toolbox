---
layout: wiki
title: Troubleshooting
permalink: /wiki/troubleshooting/
---

The **single source of truth** for known problems, their causes and their verified fixes — for people and for AI assistants alike.

**How it works**

1. **Ask first on [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions/categories/q-a)** (Q&A); a confirmed toolbox bug then goes to [GitHub Issues](https://github.com/idossha/TI-Toolbox/issues). Include the OS and version, the TI-Toolbox version (**Help ▸ About**), the exact command or interface action, the full error text, and the relevant log (see [Where are the logs](#where-are-the-logs)). Remove session tokens and private project data before sharing. [Discord](https://discord.gg/KKdjJk8f) is there for quick questions.
2. **Verified solutions are promoted here** by a maintainer, with a link back to the discussion. Only entries that were reproduced or confirmed by the reporter land on this page.
3. **AI assistants** using the [TI-Toolbox plugin]({{ site.baseurl }}/wiki/ai-assistant/) read this page through `search_wiki` / `read_wiki_page("troubleshooting")` — so a fix recorded here is a fix your assistant knows about.

The page has two parts. **Part 1** covers problems you resolve with a step of your own — Docker settings, your machine, your data, upstream tools, and toolbox fixes that need more than an upgrade — and explains them fully. **Part 2** is a compact list of toolbox bugs that have already been fixed: if you hit one, the answer is *upgrade*. Search the page (Ctrl/Cmd-F) for your error text.

---

# Part 1 — Environment problems (Docker, machine, data, upstream tools)


## Where are the logs

- **Per-run logs:** `<project>/derivatives/ti-toolbox/logs/sub-<id>/`.
- **Job consoles:** `<project>/code/ti-toolbox/jobs/<job id>/stdout.log`. In the app, select the job
  in **Jobs** and open **Raw log**, which shows all of it; its folder button opens the job's results
  folder, or the job's own folder (**Open job folder**) when it has none. Finished job records older
  than 30 days, or beyond the newest 200, are deleted when the server starts.
- **Desktop app log (`main.log`):** macOS `~/Library/Logs/TI-Toolbox/main.log`; Windows
  `%APPDATA%\ti-toolbox-desktop\logs\main.log`; Linux `~/.config/ti-toolbox-desktop/logs/main.log`.
- **Container:** for launcher or container problems, run these commands from the selected checkout
  so the container name is resolved from the project instead of guessed:

  ```bash
  python3 loader.py --project /path/to/project --status
  python3 loader.py --project /path/to/project --logs
  ```

## Desktop application

### What should happen when I close the app or switch projects?

Closing the desktop app stops the project's container. If jobs are running or queued, it asks
first; **Stop jobs and quit** cancels them. Project files are kept. To change projects without
quitting, use **Switch project** in Overview.

### Native TetraVox is not installed or does not open

Open **Settings ▸ Viewer** and use **Retry setup**, then retry opening the scene. TI-Toolbox
installs its own copy of the latest compatible TetraVox from the official GitHub release and
launches only that copy; a TetraVox you installed yourself is not used. Updates go through
TI-Toolbox too: **Settings ▸ Viewer** offers **Update to X**, and TetraVox's own update window
hands the update to TI-Toolbox to install. A checksum mismatch means nothing was installed; retry the
verified download instead of unpacking an archive into the runtime directory yourself. Platforms
without an official package (for example Linux on arm64) report that TI-Toolbox has none.

Browser-only sessions cannot start native applications. Download the prepared scene and open it
manually in TetraVox on a machine where its dataset paths exist. A remote server's scene file does
not copy the underlying volumes or meshes to your computer.

## Docker

### Docker image store is corrupted — `blob sha256:… not found`

**Situation:** launching the toolbox (or any `docker images` call) after an interrupted pull, a full disk, or a reboot mid-download. Seen on Ubuntu / EC2.
**Error:**
```
Error response from daemon: rpc error: code = NotFound desc = blob sha256:9e03764f… expected at /var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/…: not found
```
**Cause:** containerd's image metadata references a layer blob that no longer exists on disk. Metadata and blobs are written separately, so an interrupted pull or an out-of-space write leaves a dangling reference; every command that lists images then aborts. Not a toolbox bug.
**Fix:**
1. Check disk space first: `df -h /var/lib/docker` — a full disk is the usual trigger.
2. Try `sudo docker system prune -af && docker pull --platform linux/amd64 idossha/ti-toolbox:v3.1.2`.
3. If prune fails with the same error, reset the store (destroys *all* local images/containers/volumes — project data is untouched, it lives outside Docker):
   ```bash
   sudo systemctl stop docker docker.socket containerd
   sudo rm -rf /var/lib/docker /var/lib/containerd
   sudo systemctl start containerd docker
   ```
   then relaunch; the image is downloaded again.
**Source:** maintainer-verified, 2026-08-26.

### `unknown shorthand flag: 'f'` / `docker: unknown command: docker compose` / `ti-toolbox: install the Docker Compose plugin` (Windows)

**Applies to:** Windows, running the loader from a shell.
**Cause:** the `docker compose` v2 plugin is not available in that shell — Docker Desktop's WSL integration is off for the distro. `loader.sh` reports this as `ti-toolbox: install the Docker Compose plugin`.
**Fix:** **Docker Desktop ▸ Settings ▸ Resources ▸ WSL Integration** → enable your distro → Apply & Restart; verify with `docker compose version`. The desktop app is unaffected.
**Source:** [#65](https://github.com/idossha/TI-Toolbox/discussions/65).

### Docker not running, or the app cannot start its container

The desktop app shows one of these messages when it cannot start the project's container. A
first launch of a new version also downloads the image before the server starts, which can take
a while on a slow connection or a nearly full disk.

- **"Docker was not found on this machine…"** — install Docker Desktop (macOS/Windows) or Docker
  Engine (Linux). On Windows with Docker Desktop installed, update TI-Toolbox (see Part 2, v3.0.1)
  and check which `Docker endpoint` `main.log` names.
- **"Docker is installed but not running…"** — start Docker Desktop (`sudo systemctl start docker`
  on Linux), wait until it reports running, and try again.
- **"Permission denied talking to the Docker socket…"** — on Linux run
  `sudo usermod -aG docker $USER`, then log out and back in; on macOS restart Docker Desktop.
- **"This container engine is not supported yet. … Podman is not supported."** — install Docker
  Desktop or Docker Engine and make it the active engine.
- **"The TI-Toolbox image could not be downloaded…"** — check the connection and free disk space,
  or pull it by hand: `docker pull --platform linux/amd64 idossha/ti-toolbox:v3.1.2`.
- **"The container started but its server never answered"** — read the container log
  (`--logs`, see [Where are the logs](#where-are-the-logs)); low Docker memory is a common cause
  (see the next entry).
- **"…most likely busy rather than broken"** (attaching to a running container) — the server is
  busy with a cold scene build or a heavy job; wait and try again, or raise
  `TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS`.
- **"The container exited while starting up"** — the text in brackets is the container's own
  reason. `exec format error` means the host cannot run the linux/amd64 image: on an arm64 Linux
  machine install emulation (`docker run --privileged --rm tonistiigi/binfmt --install amd64`, and
  expect it to be slow) or use an x86-64 machine.

Follow the [installation guide]({{ site.baseurl }}/installation/) for the matching image.

### CHARM killed / simulations slow — insufficient Docker memory

**Applies to:** macOS and Windows (Docker Desktop VM).
**Error:** `charm: line 2: … Killed` during meshing.
**Cause:** Docker Desktop's VM memory limit (not the machine's RAM) is too low; CHARM needs well over 8 GB.
**Fix:** **Docker Desktop ▸ Settings ▸ Resources ▸ Memory**: at least 20 GB, 32 GB recommended; close other heavy apps; then quit and reopen TI-Toolbox so it plans jobs with the new limit. Validate with `ernie`, downloaded from **Help ▸ Example data**. Then re-run the head-model (m2m) step.
**How jobs use the memory:** a job that reserves more memory than the container has (a montage export reserves 16 GB) does not wait forever: it runs alone, once no other job is running, and may still run out of memory. Its log says so before it starts: `needs about 16 GB of memory, more than the 7.8 GB this container has: it will run alone, once no other job is running, and may still run out of memory (give Docker more memory to avoid that)`. FreeSurfer refuses to start below 16 GiB of container memory (`FreeSurfer requires at least 16 GiB of available container memory.`).
**Source:** [#119](https://github.com/idossha/TI-Toolbox/discussions/119), [#121](https://github.com/idossha/TI-Toolbox/discussions/121), [Dependencies]({{ site.baseurl }}/installation/dependencies/).

### Preprocessing appears frozen for many hours

**Check progress:** open [Jobs]({{ site.baseurl }}/wiki/jobs/) to inspect the stage and live log. CHARM and FastSurfer can run for a long time, especially under emulation on Apple Silicon; a quiet interval alone does not establish that a job is stuck.
**CHARM frozen on a many-core machine:** before v3.0.2, `charm` could hang forever partway through on machines with many CPU cores, with an OpenBLAS thread-metadata warning in the log. Update to v3.0.2 or later, cancel the job and run it again.
**Source:** [#93](https://github.com/idossha/TI-Toolbox/discussions/93).

## GUI display (X11, v2 only)

v3 needs no X11, XQuartz or VcXsrv; for display problems with the v2 GUI, see [Legacy v2 users]({{ site.baseurl }}/wiki/legacy-v2/).

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

### EEG net has a hole / central electrodes on one point

**Applies to:** head models built before v3.1.1 with GSN-HydroCel-128, BioSemi-64, BioSemi-128 or BioSemi-256.
**Cause:** these four caps were in the wrong coordinate frame, so charm put their central electrodes on one point of the scalp (43 GSN-HydroCel-128 electrodes collapsed into a hole). v3.1.1 ships corrected caps.
**Fix:** upgrading alone is not enough: the subject keeps the wrong positions in `m2m_<id>/eeg_positions/` until the cap is re-applied. Enable **Settings ▸ Extensions ▸ EEG caps**, open **EEG caps**, tick the affected cap and press **Apply selected** (choose **Replace and rerun** when asked), or **Re-apply all**, for each subject that uses it. Then re-run the simulations and optimizations that used those nets. See [EEG Caps]({{ site.baseurl }}/wiki/eeg-caps/).

### Bilateral target with a unipolar montage

Flex-search and ex-search accept a union of regions or spheres picked as one target, for example
the left and right hippocampus. A single TI pair still has one focal maximum, so a union target
trades focality between the sites; an mTI montage is the alternative.
**Source:** [#89](https://github.com/idossha/TI-Toolbox/discussions/89).

## Upstream tools (QSIPrep, QSIRecon, SimNIBS)

### QSIPrep crashes with `TypeError: must be real number, not NoneType` (TotalReadoutTime)

**Applies to:** QSIPrep 26.0.0 and every version since 2019; any DWI sidecar lacking `TotalReadoutTime`.
**Cause:** upstream bug in `qsiprep/interfaces/epi_fmap.py` — the value is read with a bare `.get()` and formatted into an FSL `acqp` line; the code path runs under `--hmc-model eddy` even with no fieldmap. Reported four times upstream, never fixed.
**Fix:** the toolbox pre-flight (since v2.5.0) derives `TotalReadoutTime` or writes a provably inert fallback before the container starts. Manually: add `"TotalReadoutTime"` and `"PhaseEncodingDirection"` to `sub-<id>/dwi/sub-<id>_dwi.json`.

### QSIPrep stops at `synthseg` on an Apple Silicon Mac ("TensorFlow library was compiled to use AVX instructions")

**Applies to:** QSIPrep 26.0.0 on any arm64 Docker host (M-series Macs), under Rosetta or QEMU emulation.
**Cause:** QSIPrep's anatomical workflow runs `mri_synthseg`, whose TensorFlow build requires AVX instructions; emulation does not provide them, so the node fails and the run stops.
**Fix:** run QSIPrep on an x86-64 Linux or Windows machine and copy `derivatives/qsiprep/sub-<id>/` into the project; the DTI step then runs on the Mac. Since v3.0.2 the toolbox refuses to start QSIPrep on an arm64 Docker host with this explanation instead of failing mid-run.

### QSIRecon `dsi_studio_gqi` — `Cannot set the undefined 'plot_reports' attribute`

**Cause:** upstream QSIRecon bug in the connectivity node of its built-in `dsi_studio_gqi` spec.
**Fix:** nothing to do in TI-Toolbox. `dsi_studio_gqi` is the default spec, and the toolbox runs it through its own scalar-only recon YAML, which has no connectivity node and so avoids the bug. Running QSIRecon's built-in spec yourself can still hit it.
**Source:** [#81](https://github.com/idossha/TI-Toolbox/discussions/81).

### SimNIBS 4.6 quirks the image handles for you

The `atlas2subject(split_labels=True)` label misalignment is patched into the image at build time (`resources/atlas2subject/`); if you install SimNIBS 4.6 outside the container you get it unpatched. SimNIBS 4.6's own `np.nan_to_num(..., copy=None)` needs NumPy 2: the image ships NumPy 2.3.5 and runs it unmodified. In a SimNIBS environment whose NumPy was pulled below 2 (for example by `pip install bpy`), every MNI-space NIfTI warp fails with `ValueError: NoneType copy mode not allowed`.

### Warping E or J to MNI fails with `Unable to avoid copy while creating an array as requested`

**Applies to:** images v3.0.0–v3.1.1, when you run `subject2mni` / `mni2subject` on a mesh with `E` or `J` or on a 3-component NIfTI, or `run_simnibs` with `map_to_MNI`.

**Cause:** a build-time patch written for the old NumPy 1 environment turned SimNIBS's `nan_to_num(copy=None)` into `copy=False`, which NumPy 2 refuses whenever a copy is needed.

**Fix:** update to v3.1.2 or later. TI-Toolbox's own simulation, analyzer, search and EEG-cap outputs only warp scalar fields and were never affected.

### Ex-search needs a leadfield

Exhaustive search requires a pre-computed leadfield for the *same EEG net* as the montage (`derivatives/SimNIBS/sub-<id>/leadfields/`). Run that step first.

### `TI_normal` cannot be analysed in voxel space

By design — `TI_normal` only exists on the cortical surface. Select *Space = mesh* for it; use `TI_max` (or `mTI_max`) for voxel analyses.

---

# Part 2 — Toolbox bugs already fixed: upgrade

These entries record fixes to older versions. Older-version workarounds are retained for
reference; use the [installation guide]({{ site.baseurl }}/installation/) for current setup.

| Symptom | Fixed in | Note / workaround on older versions | Source |
|---|---|---|---|
| Flex-search report not written for a **Mean** or **Max** goal: `could not convert string to float: ''` | v3.1.2 | the search results are unchanged; after upgrading, rebuild the report with `simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run folder>` (for example from a **Notebooks** cell) | [Changelog]({{ site.baseurl }}/releases/changelog/) |
| Simulation report not written: `matmul: Input operand 1 has a mismatch in its core dimension 0` | v3.1.1 | simulation outputs are unchanged; after upgrading, re-run the simulation to get its report | [v3.1.1]({{ site.baseurl }}/releases/v3.1.1/) |
| Flex-search refuses the skin-visualization net: *"Could not queue the search. Missing inputs: Skin visualization EEG net …"* | v3.1.0 (image of 2026-10-12) | untick **Optimizer ▸ Solver ▸ Skin visualization ▸ Plot EEG net electrodes**; the search still runs | [changelog]({{ site.baseurl }}/releases/changelog/) |
| Flex-search fails with `Please define TESoptimize.threshold for focallity optimization!` (Threshold-based focality, Adaptive or Multi-threshold) | v3.1.0 (image of 2026-10-12) | choose **Fixed thresholds** (e.g. `0.2,0.5`) or **Threshold-free focality** | [changelog]({{ site.baseurl }}/releases/changelog/) |
| Flex-/ex-search report fails with `Cannot work out file type of ".../lh.<atlas>.annot"` for a cortical-atlas target | v3.1.0 | rebuild with `simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run>` (`ex_search` for ex-search) | [v3.1.0]({{ site.baseurl }}/releases/v3.1.0/) |
| FreeSurfer stops at once on Windows: "LOCAL_PROJECT_DIR must be an absolute host path." | v3.1.0 | | [v3.1.0]({{ site.baseurl }}/releases/v3.1.0/) |
| Surface cluster permutation stops and names a missing fsaverage `.msh` | v3.1.0 (changed) | older `_fields.npz` projections are no longer read: re-run the fsaverage projection (Simulator **Map fields to fsaverage**) | [v3.1.0]({{ site.baseurl }}/releases/v3.1.0/) |
| Apple Silicon: the app stops with "no matching manifest for linux/arm64/v8" instead of downloading the image | v3.0.1 | `docker pull --platform linux/amd64 idossha/ti-toolbox:<version>` | [v3.0.1]({{ site.baseurl }}/releases/v3.0.1/) |
| Windows: "Docker was not found on this machine" while Docker Desktop runs with the `desktop-linux` context | v3.0.1 | | [v3.0.1]({{ site.baseurl }}/releases/v3.0.1/) |
| "The bilateral CIT168 atlas was replaced by …" / "The bilateral Harvard-Oxford cortical atlas was replaced by …" for a config naming the old file | v3.0.1 (renamed) | use the named lateralized file and pick both sides when you want both | [Brain Atlases]({{ site.baseurl }}/wiki/atlases/) |
| "The Morel atlas is no longer shipped (CC BY-NC-SA)" | v3.0.0 (removed) | pick another thalamic target, or import the atlas yourself as a custom mask | [Brain Atlases]({{ site.baseurl }}/wiki/atlases/) |
| `loader.py` hides the real `docker compose` error behind "simnibs service is not running" | v2.5.0 | | |
| Analyzer "Field" dropdown had no effect; voxel analysis silently used `TI_avg` | v2.5.0 | re-run analyses made with `TI_avg` enabled | |
| mTI outputs named `TI_Max` not found by the analyzer (field renamed `mTI_max`; outputs from ≤ v2.4.0 are named `TI_Max`) | v2.5.0 | rename `*_TI_Max.*` → `*_mTI_max.*`, or re-run | |
| Flex-search current-ratio search: final field at 1:1 while `flex_meta.json` claims the optimised split | v2.5.0 | re-run affected optimisations | |
| Ex-search mTI + Atlas ROI "completed successfully" with zero runs | v2.5.0 | | |
| Ex/mex config with `roi_names=[]` and no atlas scored every montage 0 (now a `ValueError`) | v2.5.0 | | |
| QSIRecon refuses to rerun ("output already exists") although nothing was reconstructed | v2.5.0 | delete `<out>/sub-<id>/` (logs only) | |
| Analyzer simulation list empty when the first subject has no simulations | v2.4.0 | switch subject and back | |
| DICOM import crashes with `PermissionError: [Errno 1]` on `._*` files | v2.4.0 | delete the `._*` files (Part 1) | PR #133 |
| DICOMs silently skipped when `CT/` and `ct/` both exist | v2.4.0 | keep one spelling | |
| QSIRecon: `Path should point to a file: .` (license mounted as `None`) | v2.4.0 | automatic license mount | [#81](https://github.com/idossha/TI-Toolbox/discussions/81) |
| QSI preflight: `Host project directory does not exist: C:/…` on Windows | v2.3.2 | | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| `recon-all output already exists` on a fresh project (empty dir pre-created) | v2.3.2 | delete the empty `derivatives/freesurfer/sub-<id>/` | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| DWI DICOMs never converted (only T1w/T2w) | v2.3.2 | | [#122](https://github.com/idossha/TI-Toolbox/discussions/122) |
| Zipped DICOM folder ignored; empty `T1w/dicom/` created | v2.3.1 | unpack into `sourcedata/sub-<id>/T1w/dicom/` | [#90](https://github.com/idossha/TI-Toolbox/discussions/90) |
| `Labeling.nii.gz not found`, `simnibs_python` not in `$PATH`, `subject_atlas: unrecognized arguments: -m`, `NoneType copy mode not allowed` (SimNIBS 4.6 transition) | v2.3.1 | | [#80](https://github.com/idossha/TI-Toolbox/discussions/80) |
| Linux desktop app: QSIPrep `failed to connect to the docker API at unix:///var/run/docker.sock` | v2.3.1 | reinstall the desktop app | [#80](https://github.com/idossha/TI-Toolbox/discussions/80) |
| Flex-search report missing EEG mapping / electrode configuration | v2.3.1 | the electrode CSVs feed the simulator regardless | [#94](https://github.com/idossha/TI-Toolbox/discussions/94) |
| Focality step 2/2: `'FlexSearchTab' object has no attribute 'volume_atlas_display_map'` | v2.3.0 | | [#89](https://github.com/idossha/TI-Toolbox/discussions/89) |
| Cortical atlas dropdown empty in flex-search (`.annot` files not generated) | v2.2.4 | inside the container: `subject_atlas -m /mnt/<project>/derivatives/SimNIBS/sub-X/m2m_X -a DK40 -o …/m2m_X/segmentation` | [#72](https://github.com/idossha/TI-Toolbox/discussions/72) |
