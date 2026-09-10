---
layout: installation
title: HPC Deployment (Apptainer/Singularity)
permalink: /installation/hpc-apptainer/
---

The [installation guide]({{ site.baseurl }}/installation/) describes the supported Docker
runtime. An Apptainer deployment is a separate integration: the desktop app's Docker engine
management does not launch a SIF image.

## Availability

The existing Apptainer recipe is for an older environment and is **not validated for v3**.
Use the [SSH browser launcher]({{ site.baseurl }}/installation/bash-cli/#over-ssh) on remote
machines that allow Docker.

Cluster administrators evaluating Apptainer should see the
[developer deployment notes]({{ site.baseurl }}/wiki/development/#apptainer-and-clusters).
