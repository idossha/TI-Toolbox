---
layout: installation
title: Linux Installation
permalink: /installation/linux/
---

Start with the [quick start]({{ site.baseurl }}/installation/) to choose the desktop app or
command-line launcher. This page covers Linux setup.

## Docker Engine

Install [Docker Engine](https://docs.docker.com/engine/install/) for your distribution, then
start the service:

```bash
sudo systemctl enable --now docker
docker version
```

The launcher needs access to the engine socket. On a workstation where your account is
trusted to administer Docker, add it to the Docker group and log out and back in:

```bash
sudo usermod -aG docker "$USER"
```

Docker group access gives control of the host; see the
[shared-host guidance]({{ site.baseurl }}/wiki/development/#shared-host-docker-access).

## Launch choices

The Bash launcher needs Docker Compose and curl; the Python launcher needs Python 3.11+.
Use an absolute Linux project path, such as `/home/you/datasets/project`.
TI-Toolbox needs no X11 forwarding into the container.

Linux x86_64 matches the image's architecture. AppImage and DEB are the desktop package
formats; package availability is listed on the installation page. For remote machines,
use the [SSH browser route]({{ site.baseurl }}/installation/bash-cli/#over-ssh).
