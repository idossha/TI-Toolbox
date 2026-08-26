<div align="center">

<img src="docs/assets/imgs/icon.png" alt="TI-Toolbox" width="140">

# Temporal Interference Toolbox

[![Docker Pulls](https://img.shields.io/docker/pulls/idossha/simnibs?cacheSeconds=86400)](https://hub.docker.com/r/idossha/simnibs)
[![GitHub Release](https://img.shields.io/github/v/release/idossha/TI-toolbox?cacheSeconds=3600)](https://github.com/idossha/TI-toolbox/releases)
[![GitHub License](https://img.shields.io/github/license/idossha/TI-toolbox?cacheSeconds=86400)](https://github.com/idossha/TI-toolbox/blob/main/LICENSE)
[![codecov](https://codecov.io/gh/idossha/TI-toolbox/branch/main/graph/badge.svg)](https://codecov.io/gh/idossha/TI-toolbox)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/KKdjJk8f)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21627945.svg)](https://doi.org/10.5281/zenodo.21627945)

[![Windows Support](https://img.shields.io/badge/Windows-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/windows.md)
[![macOS Support](https://img.shields.io/badge/macOS-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/macos.md)
[![Linux Support](https://img.shields.io/badge/Linux-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/linux.md)

</div>

Releases, guides, and wiki please see: [https://idossha.github.io/TI-Toolbox/](https://idossha.github.io/TI-Toolbox/)

> **Note**: Latest macOS versions (26/Tahoe+) may have GUI compatibility issues with Gmsh and FreeView. See [installation docs](https://idossha.github.io/TI-Toolbox/installation/) for details.

## How to Cite

If you use TI-Toolbox in your research, please cite the journal article:

> Haber, I., Jackson, A., Thielscher, A., Hai, A., & Tononi, G. (2025). TI-Toolbox: An Open-Source Software for Temporal Interference Stimulation Research. _Brain Stimulation_. https://doi.org/10.1016/j.brs.2025.103016

If you additionally need to reference the exact software version used in your
analysis, cite the Zenodo archive alongside the article.

The concept DOI [10.5281/zenodo.21627945](https://doi.org/10.5281/zenodo.21627945)
always resolves to the latest release; each release also receives its own
version-specific DOI, listed on that page.

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff); GitHub renders it
under "Cite this repository" in the sidebar.

## AI coding agents

An installable plugin under [`agent-plugin/`](agent-plugin/) teaches Claude Code, Codex and any MCP client the toolbox (wiki, Python API, project layout) and ships a read-only MCP server that can inspect your project directory. In Claude Code:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

See [`agent-plugin/README.md`](agent-plugin/README.md) for Codex and other clients.

## Contact

The TI-Toolbox goes through rapid development and we appreciate any feedback from our users.

Please contact us via our [GitHub Issues](https://github.com/idossha/TI-toolbox/issues), [GitHub Discussions](https://github.com/idossha/TI-toolbox/discussions), [Discord](https://discord.gg/KKdjJk8f), or [email](mailto:ihaber@wisc.edu).
