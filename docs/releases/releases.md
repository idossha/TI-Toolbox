---
layout: releases
title: Releases
permalink: /releases/
---

User-facing highlights and upgrade guidance. For the detailed technical record, see the
[Changelog]({{ site.baseurl }}/releases/changelog/).

### v3.0.0 (Unreleased)

A new desktop workspace brings project overview, job tracking, pipelines, notebooks, and integrated
3D viewing together. Other additions include custom NIfTI targets, hardware-aware FastSurfer GPU
support, and optional FreeSurfer reconstruction and subregions.

The `idossha/ti-toolbox:v3.0.0` image is available for testing. Final installers and the GitHub release
are not published yet; **v2.5.0 remains the stable release**.

[Upcoming v3.0.0 notes]({{ site.baseurl }}/releases/v3.0.0/) ·
[Upgrade guidance]({{ site.baseurl }}/releases/v3.0.0/#upgrading-from-2x) ·
[Installation]({{ site.baseurl }}/installation/)

---

### v2.5.0 (Stable release)

**Released August 31, 2026.**

Adds multipolar exhaustive search, mTI normal-component fields and fsaverage projection, custom
subject masks, selectable simulation fields, and a threshold-free focality goal for flex-search.
Also improves exhaustive-search performance, DWI validation, and analyzer atlas resampling.

Script users should review the envelope API changes. Users of hippocampal or amygdala subfield
ROIs should review the atlas-resampling note before comparing ROI volumes.

[Complete v2.5.0 notes and downloads]({{ site.baseurl }}/releases/v2.5.0/) ·
[Installation]({{ site.baseurl }}/installation/)

---

## Getting help

See [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/),
[GitHub issues](https://github.com/idossha/TI-Toolbox/issues), or
[Discussions](https://github.com/idossha/TI-Toolbox/discussions).
