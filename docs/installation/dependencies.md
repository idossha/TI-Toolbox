---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

The [installation guide]({{ site.baseurl }}/installation/#system-requirements) owns hardware
requirements and launch instructions. Docker runs SimNIBS, FastSurfer, the
scientific Python dependencies, and the viewer in one image.

## Host tools

| Launch route | Host requirements |
|---|---|
| Packaged desktop app | Docker Desktop on Windows/macOS, or Docker Engine on Linux |
| Browser via Bash | Docker + Compose and curl; no Python or repository download |
| Browser via Python | Docker and Python 3.11+; no repository download |

No X11 server or FreeSurfer license is required for the core FastSurfer workflow. Optional
[FreeSurfer reconstruction and subregions]({{ site.baseurl }}/wiki/pre-processing/#what-changed-from-freesurfer)
require a license, an additional image download and at least 16 GiB of available container memory. Additional
QSIPrep/QSIRecon workflows have their own requirements in the
[diffusion guide]({{ site.baseurl }}/wiki/diffusion-processing/).

Configure Docker's memory and disk allocation for the workload using the installation
requirements. Docker Desktop exposes these settings under **Resources**.

![Docker resource settings]({{ site.baseurl }}/assets/imgs/installation/docker_resource.png){:style="max-width: 350px;"}

## Verification

### Test Docker Installation
```bash
# Check Docker version
docker --version

# Test Docker functionality
docker run hello-world
```

---

**Next Steps**: Once dependencies are installed, proceed to your platform-specific installation guide:
- [Windows Installation](../windows/)
- [macOS Installation](../macos/)
- [Linux Installation](../linux/) 
