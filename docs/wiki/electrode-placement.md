---
layout: wiki
title: Free Electrode Placement
permalink: /wiki/electrode-placement/
---

Not every montage comes from an EEG net. **Free-hand placement** lets you put electrodes wherever
you want on a subject's scalp by clicking them into place, and then run a simulation from that
configuration like any other montage.

Placement happens on the [Simulator]({{ site.baseurl }}/wiki/simulator/): you click in its 3-D pane, and a
saved placement is a **Free-hand** source you can pick in a job row.

<img src="{{ site.baseurl }}/assets/imgs/v3/simulator-freehand.png" alt="The free-hand placement editor for subject 101: E1+ and E1- placed on the head with their coordinates filled in the table" style="width: 100%; max-width: 1000px;">
<em>Two positions placed. The selected row (E1-) is labelled in the pane, and its dot carries a ring.</em>

## Placing electrodes

1. On the Simulator, press **New placement**. The editor opens with four rows already named
   `E1+`, `E1-`, `E2+`, `E2-` — the plan, before anything is clicked.
2. Choose the **subject** and give the configuration a **name**.
3. **Select a row**, then **click the head** in the pane. That row takes the point you clicked, in
   that subject's own millimetres. Clicking again _moves_ it rather than adding another.
4. Select the next row and click again. Each row has its own colour, and each dot is labelled.
