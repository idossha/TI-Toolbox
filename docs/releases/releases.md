---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.5.0 (Latest Release)

**Release Date**: August 27, 2026

#### Additions

- Multipolar exhaustive search (mex-search) — a multipolar counterpart to ex-search (`tit/opt/mex`), with a TI/mTI toggle, symmetric (bilateral) buckets, atlas-region and MNI-space ROI targeting, and a shared searchable ROI picker across ex-search and mTI.
- Threshold-free focality goal for flex-search — a new opt-in focality objective plus an opt-in current-ratio search, replacing threshold-dependent focality scoring.
- Selectable output fields — the simulator now writes only the fields you choose (TI_max by default) instead of a fixed set, with field definitions documented in the help popup.
- Custom subject masks as ROI targets — label volumes placed under `m2m_<id>/masks/` are auto-discovered and offered as subcortical ROI targets in flex/ex/mex-search and the analyzer.
- Unified TI/mTI field metrics — carrier grouping, hf_peak sign handling, and the TI/mTI metric surface were corrected and unified across calc, sim and the analyzer, closing several description/code mismatches; a literature-grounded field-metrics note documents the math.
- DWI preflight validation — gradient tables and sidecars are validated and QSIPrep node crashfiles are logged before/at container failure, catching bad DWI conversions early.
- Interactive atlas browser and multipolar TI documentation pages on the docs site, including subject-space atlas assets and a redesigned full-width docs theme with per-page subnav and KaTeX equation rendering.
- Claude Code / AI-assistant plugin (`agent-plugin/`) — an MCP server and marketplace listing so AI coding assistants understand the TI-Toolbox codebase, plus a maintainer-verified Troubleshooting Archive.
- Faster ex/mex-search — unit-current channel fields are now computed once per montage and reused across current splits, the TI/mTI envelope is evaluated on ROI∪GM only (not the whole head), and candidates run on a forked worker pool (`n_jobs`). Ex-search: 0.39 s → 0.05 s per evaluation (~8×; a 4,375-evaluation bucket search dropped from 28 min to 3 min). Mex-search: 58 s → ~1.4–2 s per candidate (~30–40×) via a fused numba kernel for the K≥2 mTI direction search.
- Zenodo DOIs added for the archived software release.

#### Fixes

- Analyzer sim-list bug fix, plus analyzer/ex-search layout cleanups (paired Tissue/Space and Field/Type controls, either/or ROI selection, dead vertical space removed).
- Ex-search now rejects empty ROI configs, tolerates header rows in MNI ROI CSVs, and fails cleanly on zero candidates instead of silently returning nothing.
- Flex-search summary.txt no longer prints a raw Python function repr on the Goal line.
- QSIPrep/QSIRecon fixes — the root BIDS dataset description is always created, a missing T1w is reported up front, QSIRecon's log directory is no longer mistaken for existing output, and a converted DWI arriving without its gradient table now warns instead of failing silently.
- DICOM import — a converted DWI missing its gradient table is now caught and reported.
- Docs — corrected stale ROI, tissue, atlas, CLI and testing-pipeline claims across the wiki, scripting, ex-search and analyzer pages; fixed release download links and a blank atlas viewer for cached scripts.
- Dev loader — `loader_dev.sh` rewritten as a working Python-free bash loader after regressions.

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.5.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.5.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.5.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.5.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/ti-toolbox_2.5.0_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

---

## Getting Help

If you encounter issues with this release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting Archive]({{ site.baseurl }}/wiki/troubleshooting/) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
5. Join the [TI-Toolbox Discord server](https://discord.gg/KKdjJk8f)
