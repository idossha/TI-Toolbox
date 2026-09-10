---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

Start with the [quick start]({{ site.baseurl }}/installation/) to choose the desktop app or
command-line launcher. This page covers macOS setup.

## Docker Desktop

Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) for your
Mac's architecture, start it, and wait for the engine to be ready. No XQuartz or separate
X11 server is required.

The Bash launcher needs no Python; Docker Desktop includes Compose. The Python launcher needs Python 3.11+. Use an absolute project path such as
`/Users/you/datasets/project-copy` in the installation commands or the desktop Overview project field.

## Apple Silicon and Intel

The image is `linux/amd64`. Intel Macs run that architecture directly; Apple Silicon Macs
use Docker's amd64 emulation. Expect longer FEM solves and segmentation under emulation.
The [pre-processing guide]({{ site.baseurl }}/wiki/pre-processing/) records measured runtime
coverage. Select the desktop build for your Mac's host architecture independently of the
container architecture.

## Packaged app

A DMG contains the desktop application; drag it to Applications and launch it with Docker
running. Artifact availability is recorded on the installation page. If macOS blocks an
installer, report its filename, checksum, and exact message to the maintainer.
