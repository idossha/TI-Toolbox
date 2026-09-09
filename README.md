<div align="center">

<img src="docs/assets/imgs/icon.png" alt="TI-Toolbox" width="140">

# Temporal Interference Toolbox

[![Published Release](https://img.shields.io/github/v/release/idossha/TI-toolbox?label=published%20release&cacheSeconds=3600)](https://github.com/idossha/TI-toolbox/releases)
[![GitHub License](https://img.shields.io/github/license/idossha/TI-toolbox?cacheSeconds=86400)](https://github.com/idossha/TI-toolbox/blob/main/LICENSE)
[![codecov](https://codecov.io/gh/idossha/TI-toolbox/branch/main/graph/badge.svg)](https://codecov.io/gh/idossha/TI-toolbox)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/KKdjJk8f)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21627945.svg)](https://doi.org/10.5281/zenodo.21627945)

[![Windows Support](https://img.shields.io/badge/Windows-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/windows.md)
[![macOS Support](https://img.shields.io/badge/macOS-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/macos.md)
[![Linux Support](https://img.shields.io/badge/Linux-Supported-success)](https://github.com/idossha/TI-toolbox/blob/main/docs/installation/linux.md)

</div>

**Development line: 3.0.0 (internal testing).** The current runtime version is recorded in
[`desktop/package.json`](desktop/package.json) and [`tit/__init__.py`](tit/__init__.py).
The release badge above tracks published releases; this branch has not been publicly released.
For remaining work, see the [development roadmap](docs/dev/ROADMAP.md).

Releases, guides, and wiki please see: [https://idossha.github.io/TI-Toolbox/](https://idossha.github.io/TI-Toolbox/)

TI-Toolbox combines an Electron desktop application, one Docker image for the scientific environment, and the `tit` Python API. Start with the [installation guide](https://idossha.github.io/TI-Toolbox/installation/) and [desktop guide](https://idossha.github.io/TI-Toolbox/wiki/desktop-app/). For development, see [CONTRIBUTING.md](CONTRIBUTING.md).

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

## Preview the documentation locally

From this repository’s root, run `bash docs/serve.sh`, then open
**http://127.0.0.1:4000/** once the server is ready. Stop it with **Ctrl+C**.
See [local documentation setup](docs/README.md#open-the-docs-locally) for prerequisites
and an alternative port.

## AI coding agents

The [agent integration](agent-plugin/README.md) provides Markdown skills and a read-only MCP
server for TI-Toolbox documentation, source lookup and project inspection. Use it from Codex,
Claude Code or another client that supports local MCP servers; agents without MCP can read
the skills directly. See the [setup instructions](agent-plugin/README.md) for each connection method.

## Contact

The TI-Toolbox goes through rapid development and we appreciate any feedback from our users.

Known problems and verified fixes are collected in the [Troubleshooting Archive](https://idossha.github.io/TI-Toolbox/wiki/troubleshooting/) — check it first. Otherwise contact us via our [GitHub Issues](https://github.com/idossha/TI-toolbox/issues), [GitHub Discussions](https://github.com/idossha/TI-toolbox/discussions), [Discord](https://discord.gg/KKdjJk8f), or [email](mailto:ihaber@wisc.edu).

See [CONTRIBUTING](CONTRIBUTING.md) for development, [AGENTS](AGENTS.md#where-things-are-written-down)
for the documentation map, and [CHANGELOG](docs/dev/CHANGELOG.md) for changes by release.
