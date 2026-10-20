---
layout: releases
title: Releases
permalink: /releases/
---

User-facing highlights and upgrade guidance. For the detailed technical record, see the
[Changelog]({{ site.baseurl }}/releases/changelog/).

## Latest: v3.1.1 — October 20, 2026

A patch release: a new **EEG caps** panel applies an EEG cap to an existing head model without
rebuilding it and shows how each net sits on the scalp. The GSN-HydroCel-128 and BioSemi-64, -128
and -256 caps are corrected (they put central electrodes in a hole; re-apply them in the panel),
and the simulation report is written again.

#### Download Links

**Desktop App (v3.1.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v3.1.1/TI-Toolbox-3.1.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v3.1.1/TI-Toolbox-3.1.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v3.1.1/TI-Toolbox-3.1.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v3.1.1/TI-Toolbox-3.1.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v3.1.1/ti-toolbox_3.1.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/ti-toolbox:v3.1.1`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/#install).

[v3.1.1 release notes, including which EEG caps to re-apply]({{ site.baseurl }}/releases/v3.1.1/) ·
[v3.1.0 release notes, including which fsaverage outputs to re-run]({{ site.baseurl }}/releases/v3.1.0/) ·
[v3.0.2 release notes, including who must re-run DTI simulations]({{ site.baseurl }}/releases/v3.0.2/) ·
[v3.0.0 release notes and upgrade guidance from 2.x]({{ site.baseurl }}/releases/v3.0.0/#upgrading-from-2x)

---

## Getting help

See [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/),
[GitHub issues](https://github.com/idossha/TI-Toolbox/issues), or
[Discussions](https://github.com/idossha/TI-Toolbox/discussions).
