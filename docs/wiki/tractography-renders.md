---
layout: wiki
title: Network renders
permalink: /wiki/tractography-renders/
---

Renders a simulation's white-matter network as a PNG figure, with an optional MP4 turntable and Blender scene. Colour shows a field descriptor along the fibres, not a prediction of activation.

## What you need

- A simulation of a subject with [tractography]({{ site.baseurl }}/wiki/tractography/). Without it, the tab says what to run.
- The **3D visual exporter** extension, enabled in **Settings ▸ Extensions**.

## Run it

Open **Extensions ▸ 3D visual exporter ▸ Networks**, choose the subject, simulation and network, then press **Run export**. A simulation not yet [assessed]({{ site.baseurl }}/wiki/tractography-analysis/) is assessed first, and the render waits for it.

### Choosing a network

Each way ends in a list of region pairs, which the 3D pane draws with a streamline count.

- **Preset**: frontal, posterior and temporal thalamocortical, hippocampal-cortical, cingulate-cortical, precentral-brainstem, insular-cortical, amygdala-cortical, basal ganglia-cortical and interhemispheric cortical. A preset is a set of regions on the subject's own labels, not an anatomical claim.
- **By region**: **From** regions and, optionally, **To** regions.
- **By connection**: seed regions, then edges from their table or by clicking lines in the 3D pane.
- **Strongest here**: the top N connections of this simulation in a metric you name. None is preselected.
- **Your own file**: a TRX, TCK or TRK made for this head model, in its world coordinates in millimetres. Coordinates are never converted, and a file with no streamlines or under 95 % of its points in the head model's brain is refused. These checks cannot prove the file was made for this subject.

**Same-side thalamocortical presets.** Thalamocortical presets keep same-hemisphere connections by default, decided by the subject's atlas labels. This is a specificity convention, not a claim that crossed fibres are false. The count line, the Plan and `network.json` state what was left out, and **Include opposite-hemisphere connections** adds it back, with `_with_opposite` on the network's name. No other way of choosing is filtered.

### Options

- **Colour by**: **Fibre direction (RGB)**, the local tangent, or **TI_max** along each fibre. Tick both for one image each in one run.
- **Turntable video** and **Export .blend**, each off until you ask for it.
- **Quality**: **Fast preview** to check a choice, then **Final**.
- **Setup** lists what the render will use, with a reason for each, and replaces any one value.
- **Layers ▸ Cortex** hides the cortex in the pane only, not in the render.

## What you get

One folder per run, shown in the **Renders** tab:

```
visual_exports/sub-<id>/<sim>/networks/<datetime>/
  ti_max.png  direction.png
  ti_max_turntable.mp4  direction_turntable.mp4
  network.blend
  network.json
```

Each figure holds four panels and no text: lateral, superior, anterior and posterior. `network.json` holds the numbers, including the streamlines drawn, the median `TI_max`, `ti_along` and `align_index`, and the config to render it again: `simnibs_python -m tit.blender network.json ti_max`.
