---
layout: wiki
title: Network targets
permalink: /wiki/tractography-targets/
---

A flex-search, ex-search or mEx-search row can target the fibres between chosen brain regions. The chosen edges are written to a mask, which the search then uses as its target.

## What you need

- The subject's [tractography]({{ site.baseurl }}/wiki/tractography/). Without it, the target offers the step.

## Run it

In an Optimizer row, set **Target** to **Network**.

1. **Choose the network.**
   - **Preset**: a set of atlas regions. See [the presets]({{ site.baseurl }}/wiki/tractography-renders/#choosing-a-network).
   - **By region**: **From** regions and, optionally, **To** regions.
   - **By connection**: seed regions, which you can click in the 3D pane, then edges from a table with `n`, the edge's streamlines, and `share`, their fraction of all labelled streamlines. Clicking a line in the 3D pane selects its edge. An edge below **Minimum streamlines per edge** cannot be chosen.
2. **Create the mask.** Set the **Voxel density threshold**, the number of chosen streamlines that must cross a voxel for it to be in the mask, and press **Create mask**.

A network target is in subject space, and flex-search evaluates it on white matter. Changing the selection disables **Run** until you create the mask again, and a mask made before its tractogram or network was rebuilt is refused when you run.

## What you get

`m2m_<id>/masks/tract-<name>.nii.gz`, with a `.json` beside it recording the selection. The search then writes its usual outputs: see [Flex Search]({{ site.baseurl }}/wiki/flex-search/) and [Ex Search]({{ site.baseurl }}/wiki/ex-search/).
