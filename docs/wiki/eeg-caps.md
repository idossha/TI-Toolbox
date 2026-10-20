---
layout: wiki
title: EEG Caps
permalink: /wiki/eeg-caps/
---

The **EEG caps** panel puts EEG nets on a head model that already exists, without re-running
charm, and lets you check how a net sits on the subject's scalp. Turn it on in
**Settings &#9656; Extensions &#9656; EEG caps**; it then has its own row under Extensions.

## Apply a cap

1. Pick a subject that has a head model (`m2m_<id>`).
2. The **Caps** table lists every MNI cap the image ships, plus any you added to this project.
   **Source** says where a cap comes from: **TI-Toolbox** (the GSN-HydroCel and BioSemi caps
   TI-Toolbox ships), **SimNIBS** (SimNIBS's own caps), **uploaded** (added to this project), or
   **subject only** (a net on the subject with no MNI file to re-apply from). Each cap has a
   status, **not on subject** or **on subject**, and the date a cap on the subject was
   applied. After an image update that corrects a cap, re-apply it; the inspection below flags a
   cap whose electrodes collapsed.
3. Tick the caps you want and press **Apply selected**, or **Re-apply all** to refresh every cap
   already on the subject.

Applying does exactly what charm does at the end of a head-model build: the MNI cap is warped onto
this head and projected onto the scalp, and written to `m2m_<id>/eeg_positions/<cap>.csv` (with a
`.geo` for Gmsh). It takes a few seconds per cap. If a cap is already on the subject, the panel asks
first: **Skip** keeps the existing file, **Replace and rerun** overwrites it.

Use this after updating TI-Toolbox when a release fixes a cap (for example the GSN-HydroCel-128
and BioSemi caps in v3.1.1): re-apply the cap instead of rebuilding the head model.

### Add your own cap

**Add MNI cap…** takes a CSV in MNI millimetres with one electrode per row,
`Electrode,x,y,z,name` (`ReferenceElectrode` and `Fiducial` rows are also accepted), the format of
SimNIBS's `ElectrodeCaps_MNI` files. The file is checked, stored in
`code/ti-toolbox/eeg_caps/`, and can then be applied to any subject in the project. A file name
that one of the image's caps already uses is refused; rename your file.

## Inspect a net

Click a cap that is on the subject (or choose it under **Net**). The right pane draws its
electrodes on the subject's scalp, and the panel shows:

- a summary: electrode count, median and minimum spacing to the nearest neighbour, and the
  largest distance from an electrode to the scalp;
- a **warning** when two electrodes are closer than 2 mm (they collapsed onto one point — the sign
  of a cap in the wrong coordinate space) or when a label appears twice; collapsed electrodes are
  drawn in red;
- a sortable table of every electrode: **Label**, **Nearest electrode**, **Spacing to nearest
  (mm)** and **Distance to scalp (mm)**. Click a row to ring its electrode in the 3-D view.

**Compare with** draws a second net in orange and adds, for each electrode, the nearest electrode
of the other net and the distance between them — a quick way to see how two caps' sites correspond
on this head.

The **(i)** at the top right of the **Caps** and **Inspect** cards opens a short version of this
page in the app.
