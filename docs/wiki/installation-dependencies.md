---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

Docker Desktop exposes its memory and disk settings under **Settings ▸ Resources**. Set them to at
least the values below.

| Resource               | Needs                                                                                    |
| ---------------------- | ---------------------------------------------------------------------------------------- |
| Host RAM               | 32 GB minimum, 64 GB recommended                                                         |
| Docker memory          | At least 20 GB, 32 GB recommended. FreeSurfer and montage-export jobs each reserve 16 GB |
| Disk: base image       | 5.2 GB (`idossha/ti-toolbox:v3.1.1`)                                                     |
| Disk: FreeSurfer image | 30 GB, optional (`idossha/ti-toolbox:freesurfer-20260910`)                               |
| Disk: QSIPrep 26.0.0   | 31 GB, optional                                                                          |
| Disk: QSIRecon 26.0.0  | 19.5 GB, optional                                                                        |
| Disk: your projects    | On top of the images                                                                     |

Image sizes are uncompressed. Docker reports slightly less memory than you allocate: 32 GB shows as
about 31.3 GiB inside the container. Restart TI-Toolbox after changing Docker's memory.

![Docker resource settings]({{ site.baseurl }}/assets/imgs/installation/docker_resource.png){:style="max-width: 350px;"}

### Test Docker Installation

```bash
# Check Docker version
docker --version

# Test Docker functionality
docker run hello-world
```

---

[FreeSurfer reconstruction and subregions]({{ site.baseurl }}/wiki/fastsurfer/#freesurfer-reconstruction-and-subregions)
require a license which we ship with the toolbox, an additional image download and at least 16 GiB of available container memory which we offer through the toolbox.

Additional QSIPrep/QSIRecon workflows have their own requirements in the
[diffusion guide]({{ site.baseurl }}/wiki/diffusion-processing/).

---

**Next Steps**: Once dependencies are installed, proceed to your platform-specific installation guide:

- [Windows Installation]({{ site.baseurl }}/installation/windows/)
- [macOS Installation]({{ site.baseurl }}/installation/macos/)
- [Linux Installation]({{ site.baseurl }}/installation/linux/)
