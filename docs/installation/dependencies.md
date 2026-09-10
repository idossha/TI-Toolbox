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
| Browser via Bash | Docker + Compose, curl, git for a checkout; no Python |
| Browser via Python | Docker, Python 3.11+, git for a checkout |

No X11 server or separate FreeSurfer license is required for the core workflow. Additional
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
