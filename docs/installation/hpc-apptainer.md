---
layout: installation
title: HPC Deployment (Apptainer/Singularity)
permalink: /installation/hpc-apptainer/
---

The [installation guide]({{ site.baseurl }}/installation/) describes the supported Docker
runtime. An Apptainer deployment is a separate integration: the desktop app's Docker engine
management does not launch a SIF image.

## Existing recipe

The repository contains `container/blueprint/apptainer.def` and
`container/blueprint/apptainer_run.sh` for an earlier combined SimNIBS/FreeSurfer environment.
That recipe is not equivalent to the current Docker image's FastSurfer, server, and embedded
viewer stack. It needs migration and validation before it can be offered as an installation
path for the current application.

Cluster administrators evaluating this route should work from the selected source checkout,
confirm the cluster's container policy, and validate their scientific workloads in the resulting
runtime. Do not combine a recipe fetched independently from `main` with another source ref.
For a remote machine that allows Docker, use the
[SSH browser launcher]({{ site.baseurl }}/installation/bash-cli/#over-ssh).
