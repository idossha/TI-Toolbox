---
layout: installation
title: Installation
permalink: /installation/
---

Install Docker, open TI-Toolbox, and choose your project. Use the **Desktop app** or the **CLI** below.

## 1. Install Docker

Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/) on macOS or Windows,
or [Docker Engine](https://docs.docker.com/engine/install/) on Linux.
TI-Toolbox includes its scientific tools; you do not need to install SimNIBS or an X11 server separately.

Platform help: [macOS]({{ site.baseurl }}/installation/macos/) ·
[Windows]({{ site.baseurl }}/installation/windows/) ·
[Linux]({{ site.baseurl }}/installation/linux/).

## 2. Open TI-Toolbox

### Desktop

1. Download the installer for your system from the [release page]({{ site.baseurl }}/releases/).
2. Open **TI-Toolbox**.
3. Enter your project directory or select it with **Browse**, then choose **Open project**.

Use **Switch project** in Overview to open another project. Closing the app stops its container;
your project files are preserved.

### CLI

Download **one launcher** — [loader.py](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/loader.py)
or [loader.sh](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/loader.sh) — plus
[docker-compose.yml](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/docker-compose.yml).
Keep these **two files in the same folder**, with their filenames unchanged. If a link opens as text,
use **Save As** (without adding `.txt`). No repository checkout is needed: regular launches use
the code already inside the image and mount your project data without replacing that code.

Open a terminal in that folder and run **one** launcher:

```bash
python3 loader.py
```

or, on macOS/Linux:

```bash
bash loader.sh
```

Enter your project directory when prompted; TI-Toolbox opens in your browser.
Python needs version 3.11+; Bash needs curl and Docker Compose.

If asked, choose **Recreate** (default) or **Attach** to an existing session.
Closing the browser leaves it running; see the [CLI guide]({{ site.baseurl }}/installation/bash-cli/#stop-or-check-a-session)
for stopping it.

## System requirements

Allow at least **32 GB RAM**, **4 CPU cores**, and **20 GB free disk space**, plus space for your
project. We recommend 64 GB RAM and 8 or more cores. Apple Silicon runs the scientific container
under emulation, so processing is slower than on an x86_64 machine.

FastSurfer is the recommended default for segmentation. Optional FreeSurfer provides full reconstruction,
thalamic nuclei, and hippocampal/amygdala subregions; see [Pre-processing]({{ site.baseurl }}/wiki/pre-processing/).

See [Dependencies]({{ site.baseurl }}/installation/dependencies/) for supported systems and optional tools.

## Troubleshooting

See [installation troubleshooting]({{ site.baseurl }}/installation/troubleshooting/) or the
[known issues and fixes]({{ site.baseurl }}/wiki/troubleshooting/).
For a cluster without Docker, see the [HPC guide]({{ site.baseurl }}/installation/hpc-apptainer/).

<a id="internal-colleague-testing"></a>

## Install from source

Building or testing v3? Follow the [developer setup]({{ site.baseurl }}/wiki/development/#source-setup)
for the checkout, matching image, and build commands.
