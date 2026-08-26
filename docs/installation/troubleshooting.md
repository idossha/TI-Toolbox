---
layout: installation
title: Troubleshooting
permalink: /installation/troubleshooting/
---

All known problems and their verified fixes — Docker, launcher, X11/GUI display, preprocessing, diffusion, optimization, analysis — live in one place:

## → [Troubleshooting Archive]({{ site.baseurl }}/wiki/troubleshooting/)

It is maintained from [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions/categories/q-a): ask there first; confirmed solutions are promoted into the archive with a link back to the thread.

### Reporting a problem

Include: OS and version, TI-Toolbox version, the exact command or GUI action, the full error text, and the relevant log from `<project>/derivatives/ti-toolbox/logs/`.

```bash
uname -a; docker --version; docker compose version
docker ps -a; docker logs --tail 50 simnibs_container
```
