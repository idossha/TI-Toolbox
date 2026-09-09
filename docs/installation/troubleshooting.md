---
layout: installation
title: Troubleshooting
permalink: /installation/troubleshooting/
---

All known problems and their verified fixes — Docker, launcher, desktop interface, preprocessing, diffusion, optimization, analysis — live in one place:

## → [Troubleshooting Archive]({{ site.baseurl }}/wiki/troubleshooting/)

It is maintained from [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions/categories/q-a): ask there first; confirmed solutions are promoted into the archive with a link back to the thread.

### Reporting a problem

Include: OS and version, TI-Toolbox version, the exact command or GUI action, the full error text, and the relevant log from `<project>/derivatives/ti-toolbox/logs/`.

From your selected checkout, inspect the project's container without guessing its name:

```bash
python3 loader.py --project /path/to/project --status
python3 loader.py --project /path/to/project --logs
```

Remove session tokens and private project data before sharing logs.
