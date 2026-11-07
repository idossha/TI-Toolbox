---
layout: wiki
title: Tractography
permalink: /wiki/tractography/
---

Tractography tracks a subject's whole brain from their diffusion data and builds a network: the streamlines between each pair of atlas regions. A pair of regions is an **edge**. The optimizers can then [target a network]({{ site.baseurl }}/wiki/tractography-targets/), and a simulation can be [measured along it]({{ site.baseurl }}/wiki/tractography-analysis/) and [rendered]({{ site.baseurl }}/wiki/tractography-renders/).

So far this has been run end to end on one subject.

## What you need

- [QSIPrep]({{ site.baseurl }}/wiki/diffusion-processing/) output and a charm head model for the subject. QSIRecon is not needed.

## Run it

On **Pre-processing**, tick **Tractography** in the **Diffusion** section. It runs in the same Run, after QSIPrep and charm when those are ticked too. **Configure…** sets the atlas (DK40 by default) and the number of seeds (200,000 by default).

The step fits constrained spherical deconvolution, tracks probabilistically with charm's tissues constraining where a streamline may go, and labels each streamline's two ends with the atlas plus the subject's subcortical labels. The Optimizer's **Network** target offers the same step for a subject with no network.

## What you get

In `derivatives/SimNIBS/sub-<id>/tractography/`:

| File | Contents |
|---|---|
| `tractogram.trx` | The streamlines, in the head model's world coordinates |
| `tractogram_acpc.tck` | The same streamlines in QSIPrep's ACPC space |
| `network.npz`, `network.json` | Each streamline's two regions, and the record of how they were assigned |
| `connectome_count.npz` | Streamlines per pair of regions |
| `qc.json` | The tracking run's checks |

A count depends on the tractography and is not a connection strength. With skip existing outputs, the tractogram is kept and the network is rebuilt only if you changed the atlas; replacing tracks again. A new network makes the masks built from the old one stale.

## From a script

`simnibs_python -m tit.tract config.json` runs the stages a `TractConfig` names, in order: `track`, `network`, `assess`, `target`.
