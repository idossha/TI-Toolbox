---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.3.1 (Latest Release)

**Release Date**: May 5, 2026

A focused maintenance release for preprocessing robustness, GUI reliability, QSI container compatibility, and release-gate testing.

#### Fixes & Maintenance

- **DICOM preprocessing hardening** — DICOM discovery now searches nested `.dcm`/`.dicom` files and supports basic compressed inputs (`.zip`, `.tar`, `.tar.gz`, `.tgz`) in the documented `sourcedata/sub-{id}/{T1w,T2w}/dicom/` layout.
- **QSI containers updated** — QSIPrep and QSIRecon now target PennLINC `26.0.0`, with CLI compatibility handling for QSIPrep `concat` and QSIRecon `--input-type qsiprep`.
- **Telemetry consent persistence** — GUI telemetry consent is stored in the user-level config mount and should no longer reappear every launch once answered.
- **Launcher telemetry normalization** — host OS and architecture values are canonicalized across the Electron launcher and `loader.py`, keeping telemetry slices consistent across entrypoints.
- **GUI lifecycle reliability** — preprocessing, simulation, flex-search, ex-search, Analyzer, and NIfTI Viewer tabs now refresh dependent outputs more consistently and avoid reporting success after failed subprocesses.
- **Flex-search simulation identity** — simulator-generated flex-search runs now keep a unique storage key while showing a compact run label and hover metadata in the GUI, following the run-id/run-name split used by tools such as [MLflow](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.html).
- **Analyzer discovery improvements** — Analyzer refreshes simulation lists when shown and after simulation completion, with clearer messages when TI/mTI post-processing outputs are missing.
- **Report and visualization follow-ups** — simulation reports use clearer missing-visualization states and simulations continue when optional montage visualization cannot be generated.
- **Release-gate tests** — added Dockerfile.test-based integration checks plus a self-contained comprehensive release-gate entry point using only test-environment fixtures.

[Full release notes]({{ site.baseurl }}/releases/v2.3.1/) · [API documentation]({{ site.baseurl }}/scripting/)

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox.Setup.2.3.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/ti-toolbox_2.3.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
