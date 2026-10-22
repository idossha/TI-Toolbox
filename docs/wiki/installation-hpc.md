---
layout: installation
title: HPC Deployment (Apptainer/Singularity)
permalink: /installation/hpc-apptainer/
---

Apptainer/Singularity is **not validated for v3**: the desktop app's Docker engine management does
not launch a SIF image. For a remote or cluster machine that allows Docker, use the
[SSH browser launcher]({{ site.baseurl }}/installation/bash-cli/#over-ssh); the
[installation guide]({{ site.baseurl }}/installation/) describes the supported Docker runtime.

## Availability

The Apptainer recipe builds a SIF from the release Docker image, so it has the same software,
but running TI-Toolbox from it has not been validated. Cluster administrators evaluating
Apptainer should see the
[developer deployment notes]({{ site.baseurl }}/wiki/development/#apptainer-and-clusters).
