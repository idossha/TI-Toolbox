---
layout: installation
title: Linux Installation
permalink: /installation/linux/
---

Use the [installation procedure]({{ site.baseurl }}/installation/) for the source checkout,
matching Docker image, and launch commands. This page covers Linux engine access.

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
[shared-host boundary]({{ site.baseurl }}/installation/#docker-access-is-a-trust-boundary).

## Launch choices

The browser launcher needs Python 3.11+ and git. The Electron development app additionally
needs Node 22.12+ and a desktop session. Use an absolute Linux project path in the shared
installation procedure. TI-Toolbox needs no X11 forwarding into the container.

Linux x86_64 matches the image's architecture. AppImage and DEB are the desktop package
formats; package availability is listed on the installation page. For remote machines,
use the [SSH browser route]({{ site.baseurl }}/installation/bash-cli/#over-ssh).
