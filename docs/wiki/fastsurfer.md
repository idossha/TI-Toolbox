---
layout: wiki
title: FastSurfer / FreeSurfer
permalink: /wiki/fastsurfer/
---

FastSurfer provides segmentation; optional FreeSurfer provides full reconstruction and finer
subregion labels. For the overall workflow, see [Pre-processing]({{ site.baseurl }}/wiki/pre-processing/).

## FastSurfer segmentation

TI-Toolbox runs segmentation-only mode (`--seg_only`) from the subject's T1w image.
It does not reconstruct cortical surfaces. CHARM and FastSurfer are independent stages after
input conversion; neither requires the other's output.

Results are written under `derivatives/fastsurfer/sub-<id>/mri/`:

- `aparc.DKTatlas+aseg.deep.mgz`: native parcellation.
- `aparc.DKTatlas+aseg.deep.nii.gz`: NIfTI copy for volume readers and the viewer.
- `aparc.DKTatlas+aseg.deep_labels.txt`: region-label sidecar.

## FreeSurfer reconstruction and subregions

Enable **FreeSurfer** on the Pre-processing page. In **Settings → Pre-processing**, choose
full reconstruction (`recon-all`), thalamic nuclei, and/or hippocampal/amygdala subregions.
All three are selected by default. Subregions require a completed FreeSurfer reconstruction,
from this run or an existing result; FastSurfer's segmentation-only output is not sufficient.
A FreeSurfer license is required.

FreeSurfer runs in a temporary worker and stores results in `derivatives/freesurfer/sub-<id>/`.
The worker is removed when computation ends; the outputs and downloaded image remain for reuse.
The T1-only subregion pipeline uses the upstream
[Python subregion tools](https://surfer.nmr.mgh.harvard.edu/fswiki/SubregionSegmentation).

## Configure once, use across projects

Open **Settings → Pre-processing** to configure FastSurfer and FreeSurfer. These are user preferences, not project settings. Pre-processing keeps the subject and pipeline choices; computation settings live here.

Thread defaults and shared resource controls are described in [Pre-processing settings]({{ site.baseurl }}/wiki/pre-processing/#pre-processing-settings). Container CPU limits are respected. You can enter a thread limit for each tool or clear it to return to automatic. Changes apply to new jobs, not jobs already running. The job scheduler still controls when work can start.

## Enable Apple GPU

On an Apple Silicon Mac, choose **Enable Apple GPU** in Settings. One dialog explains installation, project access and third-party software terms. Choose **Enable Apple GPU** in that dialog to authorize setup; Cancel makes no change. TI-Toolbox installs FastSurfer and its dependencies in your TI-Toolbox user directory. No administrator access or global Python installation is required.

The preference remains enabled across local projects and app restarts. TI-Toolbox reuses the installation and starts the worker for the current local project. Turn it off from the same Settings section. Disabling stops native computation; the installation remains available for later use.

```text
Docker manages the job → Mac GPU runs FastSurfer → Results return to the project
```

### Third-party software and release source

FastSurfer is third-party scientific software developed by Deep-MI. TI-Toolbox's managed
installation uses source pinned to an official FastSurfer release, not a development branch or
unofficial fork. The current integration uses [FastSurfer v2.5.4](https://github.com/Deep-MI/FastSurfer/releases/tag/v2.5.4).
Source archives, installer tooling and model checkpoints are checked against pinned SHA-256
checksums. Python dependencies are installed separately in the managed runtime. This is a
TI-Toolbox-managed setup, not the upstream macOS `.pkg` installer.

FastSurfer and its dependencies retain their upstream licenses. TI-Toolbox provides no warranty
for third-party software, its scientific accuracy or fitness for a particular purpose, and its
maintainers accept no responsibility for use of FastSurfer or its results. You are responsible for
reviewing the applicable licenses and validating outputs for your research. This notice does not
replace those licenses or override rights that applicable law does not allow to be excluded.

Consult the [official release notes](https://github.com/Deep-MI/FastSurfer/releases) for known
issues and the [upstream installation guide](https://deep-mi.org/FastSurfer/stable/overview/INSTALL.html)
for FastSurfer's own setup instructions. The permissions below describe TI-Toolbox's managed integration.

### Permissions

Installation downloads software using your normal user permissions. During each computation, FastSurfer runs in a macOS sandbox: it may read the open project, its runtime and required system files, write its job staging and temporary files, and has no network access. Completed outputs are published into the project's FastSurfer derivatives directory.

A user-wide preference does not grant access to every project at once. Switching projects ends the old worker; the new worker is limited to the newly opened project. Remote connections and browser-only sessions do not install software on your Mac.

The managed runtime is under:

```text
~/Library/Application Support/ti-toolbox-desktop/runtimes/
```

## Other computers

On systems with a usable NVIDIA GPU exposed to Docker, FastSurfer prefers the container GPU. The image includes CUDA-enabled PyTorch; the host must supply compatible NVIDIA drivers and Docker GPU access. The launcher checks actual GPU computation before granting access to the project container. There is no Apple-native installation on Windows, Linux or Intel Macs.

If no GPU route is available, the job log explains the CPU fallback. An explicitly requested unavailable GPU fails instead of silently changing devices. FreeSurfer remains a separate optional pipeline; enabling Apple GPU accelerates FastSurfer, not FreeSurfer recon-all.

See the [upstream FastSurfer installation guide](https://deep-mi.org/FastSurfer/stable/overview/INSTALL.html).
