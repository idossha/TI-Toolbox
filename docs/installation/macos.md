---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

Use the [installation procedure]({{ site.baseurl }}/installation/) to choose a source ref,
load its matching image, and open the Electron app or browser interface. This page covers
macOS prerequisites and paths.

## Docker Desktop

Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) for your
Mac's architecture, start it, and wait for the engine to be ready. No XQuartz or separate
X11 server is required.

The Bash launcher needs no Python; Docker Desktop includes Compose. The Python launcher needs Python 3.11+. The Electron development
app additionally requires Node 22.12+ and git. Use an absolute project path such as
`/Users/you/datasets/project-copy` in the installation commands and `TIT_DEV_PROJECT_DIR`.

## Apple Silicon and Intel

The image is `linux/amd64`. Intel Macs run that architecture directly; Apple Silicon Macs
use Docker's amd64 emulation. Expect longer FEM solves and segmentation under emulation.
The [pre-processing guide]({{ site.baseurl }}/wiki/pre-processing/) records measured runtime
coverage. Select the desktop build for your Mac's host architecture independently of the
container architecture.

## Packaged app

A DMG contains the desktop application; drag it to Applications and launch it with Docker
running. Artifact availability is recorded on the installation page. Signing and notarization
are properties of the specific installer, not of a source checkout. If macOS blocks an
installer, report its filename, checksum, and exact message to the maintainer.
