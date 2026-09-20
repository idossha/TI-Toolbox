---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

Configure Docker's memory and disk allocation for the workload using the installation
requirements. Docker Desktop exposes these settings under **Resources**.

![Docker resource settings]({{ site.baseurl }}/assets/imgs/installation/docker_resource.png){:style="max-width: 350px;"}

### Test Docker Installation

```bash
# Check Docker version
docker --version

# Test Docker functionality
docker run hello-world
```

---

No **X11 server required** anymore like in v1.x.x or v2.x.x.

[FreeSurfer reconstruction and subregions]({{ site.baseurl }}/wiki/pre-processing/#what-changed-from-freesurfer)
require a license which we ship with the toolbox, an additional image download and at least 16 GiB of available container memory which we offer through the toolbox.

Additional QSIPrep/QSIRecon workflows have their own requirements in the
[diffusion guide]({{ site.baseurl }}/wiki/diffusion-processing/).

---

**Next Steps**: Once dependencies are installed, proceed to your platform-specific installation guide:

- [Windows Installation](../windows/)
- [macOS Installation](../macos/)
- [Linux Installation](../linux/)
