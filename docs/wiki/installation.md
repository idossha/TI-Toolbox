---
layout: installation
title: Quick Start
permalink: /installation/
---

Get from download to your first project in three steps. Docker runs the scientific tools; the desktop app brings them together.

<nav id="install" class="install-flow" aria-label="Installation steps">
  <a href="#docker"><span>1</span> Start Docker</a>
  <a href="#download"><span>2</span> Install TI-Toolbox</a>
  <a href="#project"><span>3</span> Open a project</a>
</nav>

<p class="install-requirements"><strong>Before you begin:</strong> 32 GB RAM, 4 CPU cores and 20 GB free disk space, plus room for your project. Recommended: 64 GB RAM and 8+ cores. <a href="{{ site.baseurl }}/installation/dependencies/">Full requirements →</a></p>

<section class="install-step" aria-labelledby="docker" markdown="1">
## 1. Start Docker {#docker}

Choose your system for setup instructions. No separate SimNIBS or X11 installation is needed.

<div class="install-platforms">
  <details>
    <summary>macOS</summary>
    <p>Install <a href="https://www.docker.com/products/docker-desktop/">Docker Desktop</a> for your Mac’s chip, open it and wait until the engine is running.</p>
    <p>Apple menu → About This Mac shows whether you have Apple Silicon or Intel. Scientific processing runs under emulation on Apple Silicon.</p>
    <a href="{{ site.baseurl }}/installation/macos/">macOS setup help →</a>
  </details>
  <details>
    <summary>Windows</summary>
    <p>Install <a href="https://www.docker.com/products/docker-desktop/">Docker Desktop</a> with its WSL2 backend, open it and wait until the engine is running.</p>
    <a href="{{ site.baseurl }}/installation/windows/">Windows / WSL2 setup help →</a>
  </details>
  <details>
    <summary>Linux</summary>
    <p>Install <a href="https://docs.docker.com/engine/install/">Docker Engine</a> and Docker Compose for your distribution. Start the engine and check that your account can run <code>docker version</code>.</p>
    <a href="{{ site.baseurl }}/installation/linux/">Linux setup help →</a>
  </details>
</div>
</section>

<section class="install-step" aria-labelledby="download" markdown="1">
## 2. Install TI-Toolbox {#download}

Choose the download for your computer.

{% include downloads.html %}

<details class="install-help">
  <summary>How do I install the downloaded file?</summary>
  <ul>
    <li><strong>macOS:</strong> open the DMG, drag TI-Toolbox to Applications, then open it.</li>
    <li><strong>Windows:</strong> run the EXE installer, then open TI-Toolbox from the Start menu.</li>
    <li><strong>Linux:</strong> install the DEB using your package manager, or mark the AppImage executable and run it.</li>
  </ul>
</details>
</section>

<section class="install-step" aria-labelledby="project" markdown="1">
## 3. Open a project {#project}

<ol class="install-project">
  <li><strong>Open TI-Toolbox</strong><br>Keep Docker running.</li>
  <li><strong>Choose your project folder</strong><br>Use Browse or enter its full path, then select <strong>Open project</strong>.</li>
  <li><strong>Let the first launch finish</strong><br>The toolbox downloads its scientific environment. This needs internet access and may take a while.</li>
</ol>

Your project stays on your machine. Use **Switch project** in Overview to open another folder; closing the desktop app stops its container and preserves your files.

<a class="btn btn--primary" href="{{ site.baseurl }}/wiki/overview/">Explore your workspace →</a>
<a class="btn btn--secondary" href="{{ site.baseurl }}/wiki/example-data/">Try example data →</a>
</section>

## Other ways to launch

<details class="install-help" markdown="1">
<summary>Use a terminal or browser instead</summary>

Download [loader.py](https://raw.githubusercontent.com/idossha/TI-Toolbox/main/loader.py) and
[docker-compose.yml](https://raw.githubusercontent.com/idossha/TI-Toolbox/main/docker-compose.yml) into the same folder, keeping their filenames unchanged. Open a terminal there and run:

```bash
python3 loader.py
```

Requires Python 3.11+ and Docker. The launcher downloads and opens the desktop app; add `--browser` to use your browser instead. A browser session keeps running after its tab closes. Inside WSL2 the launcher always uses your Windows browser; the desktop app on Windows is the installer above.

The [command-line guide]({{ site.baseurl }}/installation/bash-cli/) covers the Bash launcher, project paths, existing sessions and stopping a container.
</details>

<a id="internal-colleague-testing"></a>

- **Cluster without Docker:** follow the [HPC / Apptainer guide]({{ site.baseurl }}/installation/hpc-apptainer/).
- **Build from source:** follow the [developer setup]({{ site.baseurl }}/wiki/development/#source-setup).
- **Something went wrong:** see [troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/).
