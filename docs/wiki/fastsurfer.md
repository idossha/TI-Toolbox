---
layout: wiki
title: FastSurfer and FreeSurfer settings
permalink: /wiki/fastsurfer/
---

## Configure once, use across projects

Open **Settings → System** to configure FastSurfer and FreeSurfer. These are user preferences, not project settings. Pre-processing keeps the subject and pipeline choices; computation settings live here.

Both tools default to **80% of the CPUs available to the computation**, rounded down with a minimum of one. Container CPU limits are respected. You can enter a thread limit for each tool or clear it to return to automatic. Changes apply to new jobs, not jobs already running. The job scheduler still controls when work can start.

## Enable Apple GPU

On an Apple Silicon Mac, choose **Enable Apple GPU** in Settings. A short explanation appears, followed by native confirmation. TI-Toolbox installs FastSurfer and its dependencies in your TI-Toolbox user directory. No administrator access or global Python installation is required.

The preference remains enabled across local projects and app restarts. TI-Toolbox reuses the installation and starts the worker for the current local project. Turn it off from the same Settings section. Disabling stops native computation; the installation remains available for later use.

```text
Docker manages the job → Mac GPU runs FastSurfer → Results return to the project
```

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

See also [Pre-processing]({{ site.baseurl }}/wiki/pre-processing/) and the [upstream FastSurfer installation guide](https://deep-mi.org/FastSurfer/stable/overview/INSTALL.html).
