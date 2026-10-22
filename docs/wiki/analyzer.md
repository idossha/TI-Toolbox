---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer is the last step of the pipeline: after a montage has been optimized ([flex-search]({{ site.baseurl }}/wiki/flex-search/), [ex-search]({{ site.baseurl }}/wiki/ex-search/)) and [simulated]({{ site.baseurl }}/wiki/simulator/), it turns the finished simulation into numbers — descriptive statistics of the field inside a region of interest and across the whole brain, in mesh or voxel space. One `Analyzer` class handles both spaces, and `run_group_analysis()` runs the same analysis across subjects.

This page is also where the toolbox's field quantities are defined once for everyone: the optimizer and simulator pages link here for what `TI_max`, `TI_normal`, `TI_avg`, `hf_peak` and `hf_sar` mean and how the envelope math works.

## Overview

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/analyzer-page.png" alt="The Analyzer page: one row analysing subject 101's L_Insula simulation on the mesh, with a 10 mm MNI sphere as its target" style="width: 100%; max-width: 1000px;">
  <em>The Analyzer (⌘4). One row is one analysis, and each row owns its own target.</em>
</div>

---

## Quantities of Interest

Two words carry all of the structure on this page. A **channel** is one pair of electrodes driven by one current source at one kHz frequency. Two channels at slightly offset frequencies **share a carrier** and produce one beat: standard TI is 4 electrodes forming 2 channels on one carrier (e.g. 2.000 and 2.010 kHz around a 2 kHz carrier), and mTI is 8 electrodes forming 4 channels on two carriers (e.g. 2 kHz and 4 kHz — each pair of channels shares one).

Neither channel's kHz field modulates neurons on its own; the quantity the TI community cares about is the **amplitude of the low-frequency beat** that the two channels sharing a carrier produce where their fields overlap. Everything the analyzer reports is a spatial statistic of that one quantity, so it helps to see it once in the time domain and once in the spatial domain.

### Time domain: what a single value of `TI_max` is

<div class="image-container" style="max-width: 800px;">
  <video controls muted playsinline style="width: 100%; border-radius: 8px;" preload="metadata">
    <source src="{{ site.baseurl }}/assets/videos/TI_timeDomain.mp4" type="video/mp4">
  </video>
  <em>The kHz fields of two channels sharing a carrier, each too fast to modulate neurons on its own, sum where they overlap into a field whose amplitude beats at the difference frequency. The peak-to-trough swing of that envelope is the modulation depth -- the single number <code>TI_max</code> stores at every mesh node or voxel.</em>
</div>

- **`TI_max`** (V/m) -- the modulation depth of the beat envelope, maximised over direction at every mesh node or voxel. It is the default field of every simulation and of every analysis, and what "TImax" / "TInorm" mean in papers and in this toolbox's optimizers. For one carrier (two channels) it is the closed form $$2\min(\lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert)$$ when the fields are near-aligned, and smaller otherwise (Grossman et al. 2017; exact form under [Envelope Math and Critical Values](#envelope-math-and-critical-values) below).
- **`TI_normal`** (V/m, mesh only) -- the same envelope measured along the local cortical surface normal, i.e. the component that runs along the apical dendrites of pyramidal cells. It is always $$\le$$ `TI_max`, can be much smaller where the field is tangential to the cortex (see below), and is written for both TI and mTI runs (for mTI via `get_TI_dir`, the same envelope evaluated along the surface normal).
- **`TI_avg`, `hf_peak`, `hf_sar`** -- optional extra fields (direction-averaged envelope; carrier-exposure safety metrics). They are defined below ([Envelope Math](#envelope-math-and-critical-values) and [Safety Metrics](#safety-metrics)); the analyzer treats them as any other field, each in its own units.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_fig4c_ti_normal.png" alt="TI_normal as the projection of TI_max onto the surface normal" style="width: 100%; max-width: 700px;">
  <em>At each surface node, <code>TI_normal</code> is the component of the <code>TI_max</code> envelope along the local surface normal \(\hat{n}\): where the field runs along \(\hat{n}\) (left) the two are nearly equal, and where it runs tangential to the cortex (right) <code>TI_normal</code> collapses even though <code>TI_max</code> is unchanged. Figure 4C from <a href="https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext">Haber et al. 2026</a>.</em>
</div>

### Multipolar (mTI): more carriers, same quantity

With four channels on two carriers (8 electrodes) — or more — `mTI_max` is still the same beat-envelope modulation depth: each carrier's two channels beat exactly as in standard TI, and the carriers, being mutually incoherent, add **powers**, not amplitudes:

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/mti_envelope_time.png" alt="mTI time domain: per-carrier envelopes vs the joint envelope" style="width: 100%; max-width: 900px;">
  <em>Time domain of an mTI field (4 channels, 2 carriers) at one point, all projections colinear for clarity: carrier 1's two channels carry 0.5 + 0.5 V/m, carrier 2's an unequal 0.3 + 0.7 V/m (so its beat never reaches zero). Alone, each carrier's modulation depth is 1.00 and 0.60 V/m (top, middle; <code>get_TI_vectors</code>). With all four channels together (bottom), the two carriers are mutually incoherent, so the joint envelope adds their <strong>powers</strong>, not their amplitudes: <code>get_TI_vectors</code> gives MD = 1.01 V/m. Every larger quantity in the panel is a different thing: the dotted sum of per-carrier envelopes (peaking at 2.00 V/m) is not a physical envelope; a recursive TI-of-TI recombination would report an unphysical 1.20 V/m; and the worst-case instantaneous peak of the summed channel fields <code>hf_peak</code> = 2.00 V/m is a safety quantity, not a modulation depth. The dashed running-RMS magnitude is the power view of the same field (its square relates to <code>hf_sar</code> = 1.08 (V/m)²; see <a href="#safety-metrics">Safety Metrics</a>). All values verified against <code>tit.calc</code>/<code>tit.fields</code> for this exact scenario.</em>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/mti_envelope_3d.png" alt="mTI directional envelope surface in 3D vector space" style="width: 100%; max-width: 900px;">
  <em>The same idea in vector space. At each mesh element the four channels' E-fields are vectors (A), and the modulation depth depends on the direction \(\hat{n}\) it is measured along: sweeping \(\hat{n}\) over the sphere and plotting \(r(\hat{n}) = \mathrm{MD}(\hat{n})\) from the \((P, Q)\) formulas gives the directional envelope surface (B). <code>mTI_max</code> is the radius of this surface's farthest point -- exactly what <code>get_TI_vectors</code> finds with its 192-direction Fibonacci sweep plus local refinement (0.89 V/m along \(\hat{n}^{*}\) here, verified against the toolbox for these vectors). <code>TI_avg</code> is the average radius of the same surface over all sampled directions.</em>
</div>

The two subsections below give the formulas behind these figures -- the $$(P, Q)$$ sufficient statistics, the exact one-carrier closed form, and the safety metrics. How montages are detected as TI vs. mTI is a simulation mechanic covered on the [Simulator page]({{ site.baseurl }}/wiki/simulator/).

### Envelope Math and Critical Values

The envelope for any number of carriers $$K$$ reduces to two sufficient statistics of the channel fields' projections onto a candidate direction $$\mathbf{n}$$. For carrier $$k$$, the signed projections of its two channels' fields are

$$
a_k = \mathbf{E}_{ka} \cdot \mathbf{n},
\qquad
b_k = \mathbf{E}_{kb} \cdot \mathbf{n}
$$

from which the carrier power $$P$$ and the coherent phasor sum $$Q$$ follow:

$$
P = \frac{1}{2} \sum_k \left( a_k^2 + b_k^2 \right),
\qquad
Q = \left\lvert \sum_k a_k b_k \, e^{i \psi_k} \right\rvert
$$

and the modulation depth is

$$
\mathrm{MD} = \sqrt{2} \left( \sqrt{P + Q} - \sqrt{P - Q} \right)
$$

$$\psi_k$$ is a per-carrier envelope phase offset (radians), `None` by default (all carriers phase-aligned, $$\psi_k = 0$$, the standard case). This is implemented in `tit/calc.py`, whose public API is exactly three functions:

| Function                                    | Purpose                                                                                 |
| ------------------------------------------- | --------------------------------------------------------------------------------------- |
| `get_TI_vectors(fields, psi=None)`         | Modulation-amplitude vectors for $$K \ge 1$$ carriers ($$K = 1$$ exact closed form, $$K \ge 2$$ direction search) |
| `get_TI_avg(fields, psi=None)`              | Direction-averaged modulation depth                                                     |
| `get_TI_dir(fields, directions, psi=None)` | Envelope along a fixed per-element direction; backs `TI_normal` for mTI                 |

**`get_TI_vectors`** is the one envelope function; standard TI simulation, mTI simulation and mex-search all call it. It takes `fields = [E_1a, E_1b, ..., E_Ka, E_Kb]` -- one array of shape `(N, 3)` per channel, ordered so that consecutive fields are the two channels sharing a carrier -- and returns `(N, 3)` modulation-amplitude vectors whose norm is $$\mathrm{MD}$$.

- **$$K = 1$$** (one carrier: standard TI) is solved by an exact closed form (Hirata et al. 2024, _Computers in Biology and Medicine_ 178, 108697; sign-agnostic):

  $$
  \mathrm{MD} =
  \begin{cases}
  2 \min\!\left( \lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert \right)
    & \text{if } \min\!\left( \lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert \right) \le \sqrt{\lvert \mathbf{E}_1 \cdot \mathbf{E}_2 \rvert} \\[8pt]
  \dfrac{2 \lVert \mathbf{E}_1 \times \mathbf{E}_2 \rVert}
        {\min\!\left( \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert \right)}
    & \text{otherwise}
  \end{cases}
  $$

  In the first case the envelope lies along the smaller field's own (sign-corrected) direction; in the second it is evaluated at the component of the smaller field perpendicular to whichever of $$\mathbf{E}_1 - \mathbf{E}_2$$ / $$\mathbf{E}_1 + \mathbf{E}_2$$ has the smaller norm. No direction search is needed at $$K = 1$$.

- **$$K \ge 2$$** (multiple carriers: mTI) has no closed form and is solved by a direction search: a 192-direction Fibonacci-sphere sweep, then local refinement around the best few directions. `get_TI_avg` averages the envelope over the same 192 directions instead of taking the maximum (no refinement), so it is element-wise $$\le \mathrm{TI}_{\max}$$.

The same modulation depth $$\mathrm{MD}(\mathbf{n}) = \sqrt{2}\left(\sqrt{P + Q} - \sqrt{P - Q}\right)$$ answers three different questions, and the three functions differ only in what they do with the direction $$\mathbf{n}$$:

- **`get_TI_vectors`** — maximise over $$\mathbf{n}$$: the strongest modulation any neuron at that point could see, whatever its orientation. This is `TI_max` / `mTI_max`, and what the optimizers score.
- **`get_TI_dir`** — evaluate at a *given* $$\mathbf{n}$$: the modulation seen along one specific orientation. With $$\mathbf{n}$$ set to the cortical surface normal this is `TI_normal`, the component along pyramidal-cell dendrites.
- **`get_TI_avg`** — average over all $$\mathbf{n}$$: what a randomly-oriented neuron sees on average. This is `TI_avg`, and it is always $$\le$$ `TI_max`.

Two tempting shortcuts are **not** valid and are deliberately not offered: summing the per-carrier envelopes (carriers are mutually incoherent, so their *powers* add, not their amplitudes — the dotted trace in the time-domain figure above overshoots the physical envelope) and recombining per-carrier envelopes recursively as TI-of-TI (an envelope is not a field; feeding one back into the one-carrier formula is physically invalid).

### Safety Metrics

Two carrier-exposure safety metrics (`tit/fields.py`, Cassarà et al. 2025, _Bioelectromagnetics_ 46(2), doi:10.1002/bem.22542) are computed directly from the N per-channel E-fields, independent of the modulation-depth envelope:

**`hf_peak`** (Eq. 3) is the worst-case instantaneous peak of the summed kHz field: the channels run at mutually incommensurate frequencies, so every relative phase combination occurs over time, and the true worst case is the max over sign choices,

$$
\mathrm{hf\_peak} = \max_{\mathbf{s}} \left\lVert \sum_i s_i \mathbf{E}_i \right\rVert,
\qquad s_i \in \{ +1, -1 \}
$$

At $$N = 2$$ this is exactly $$\max\!\left( \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \; \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert \right)$$. Up to 8 fields every one of the $$2^{N-1}$$ sign combinations is evaluated exactly. Above 8 fields a sweep over sampled directions picks the sign patterns to evaluate; that is a lower bound on the true maximum and therefore **slightly non-conservative**.

**`hf_sar`** is the incoherent sum of the channel-field powers, in $$(\mathrm{V/m})^2$$ -- power adds rather than amplitude:

$$
\mathrm{hf\_sar} = \sum_i \lVert \mathbf{E}_i \rVert^2
$$

This is a field-domain heating proxy, **not** calibrated SAR: the actual calibration is $$\tfrac{\sigma}{2\rho} \cdot \mathrm{hf\_sar}$$, requiring the per-tissue conductivity $$\sigma$$ and density $$\rho$$ that the toolbox does not apply.

Under the shipped positional wiring, each field is one carrier, so both metrics include **every** channel field. Shared-frequency fields require coherent vector summation first; the one place the toolbox models that is the carrier-only control below. Both metrics are **opt-in**: neither is in `SimulationConfig.output_fields`'s default (`["TI_max"]`), so a run must explicitly request `hf_peak`/`hf_sar` to get them written.

#### Carrier-only controls (ΔF = 0) {#carrier-only-controls}

A carrier-only control drives both pairs of a 2-pair montage at the **same** frequency (e.g. 15,000 / 15,000 Hz), phase-locked and in phase, so there is no beat and no envelope. The two carriers then add into one fixed field $$\mathbf{E}_1 + \mathbf{E}_2$$ that oscillates at the carrier frequency, and the TI worst case above — which is only reached because two different frequencies sweep through every relative phase — never occurs. Following Cassarà et al. 2025 Part II (_Bioelectromagnetics_ 46(1), e22536, doi:10.1002/bem.22536; p. 8: "coherent field superposition was used for identical frequencies"), the carriers are summed coherently:

$$
\mathrm{hf\_peak} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert,
\qquad
\mathrm{hf\_sar} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert^2
$$

instead of $$\max\!\left( \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert \right)$$ and $$\lVert \mathbf{E}_1 \rVert^2 + \lVert \mathbf{E}_2 \rVert^2$$. For `hf_peak` the two agree where the carrier fields are within 90° of each other and differ where they are not; `hf_sar` gains the cross term $$2\,\mathbf{E}_1 \cdot \mathbf{E}_2$$ (up to twice the TI value for aligned carriers, down to zero for opposed equal ones). With $$\lVert \mathbf{E}_1 \rVert = 1$$ and $$\lVert \mathbf{E}_2 \rVert = 0.8$$ V/m at 120°, the TI worst case is 1.56 V/m while the carrier-only peak is 0.92 V/m. "In phase" means what the simulation's sign convention defines: each pair's first electrode is driven positive at the same instant.

`TI_max`, `TI_avg` and `TI_normal` are undefined without a beat and are **not computed**; a carrier-only run writes only `hf_peak` and/or `hf_sar`. How to set one up, in the app or from Python, is under [Carrier-only control on the Simulator page]({{ site.baseurl }}/wiki/simulator/#carrier-only-control).

### Spatial domain: how the analyzer summarises a field

Once `TI_max` exists at every node or voxel, an analysis reduces it to a handful of spatial statistics -- intensity inside the target, intensity everywhere else, and how concentrated the hot spot is:

| Quantity                      | `AnalysisResult` field                              | What it tells you                                                                                                                                                                                                                                     |
| ----------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intensity in the ROI**      | `roi_mean` (also `roi_max`, `roi_min`)              | Area/volume-weighted mean `TI_max` inside the target. The number to compare against dose thresholds and between montages.                                                                                                                             |
| **Intensity outside the ROI** | `gm_mean` (also `gm_max`)                           | Mean over the **entire grey matter** in mesh space, and over the selected **Tissue** in voxel space. This is the analyzer's fixed non-ROI; the optimizers additionally accept a user-defined avoidance region.                                       |
| **Focality**                  | `roi_focality`                                      | `roi_mean / gm_mean`. 1 means the target is no hotter than the average cortex; higher is more selective. Same definition as ex-search's `Focality`.                                                                                                   |
| **Normal component**          | `normal_mean`, `normal_max`, `normal_focality`      | The three statistics above recomputed on `TI_normal` (mesh only).                                                                                                                                                                                     |
| **Hot-spot level**            | `percentile_95`, `percentile_99`, `percentile_99_9` | Field value below which 95 / 99 / 99.9 % of the grey-matter area (mesh) or of the selected tissue's volume (voxel) lies. `percentile_99_9` is a robust "peak" that ignores single outlier elements.                                                  |
| **Hot-spot size**             | `focality_50_area` ... `focality_95_area`           | Grey-matter area in $$\mathrm{cm}^2$$ (mesh), or selected-tissue volume in $$\mathrm{cm}^3$$ (voxel), at or above 50 / 75 / 90 / 95 % of `percentile_99_9`. A small `focality_50_area` means a compact hot spot; a large one means the field is spread out, regardless of where the ROI is. |

Two things trip people up: the percentile and area metrics describe the whole grey matter (or, in voxel space, the whole selected tissue) and do not depend on the ROI at all, and every statistic is computed on whichever field you selected, in that field's units -- selecting `hf_sar` gives you means of a power-like quantity in $$(\mathrm{V/m})^2$$, not a field strength.

---

## Defining the ROI

An analysis needs a target. Open a row's **Job settings** and choose one of four target types: **Cortical**, **Subcortical**, **Spherical** or **NIfTI mask** (below, under [Custom NIfTI mask targets](#custom-nifti-mask-targets)). Each row owns its own target.

**Spherical ROI Analysis**

- Each row of the **X / Y / Z / Radius** table is one sphere; **Add sphere** adds another, the bin icon removes one
- Coordinates are in **Subject** or **MNI** space; MNI centres are transformed into each subject's anatomy automatically
- Several spheres in one row run as **separate analyses**, one per sphere, never as a union; the row's target line ends in "(separate jobs)". In a group run, each sphere is its own group job
- A union of spheres is Python-only: `analyzer.analyze_spheres([(x, y, z, r), ...])` measures them as one ROI (overlapping spheres are not double-counted). Its output folder is named `spheres<N>_...`, and long unions are shortened to the first sphere plus a hash

**Cortical Analysis (Region Union)**

- Analyze one or more atlas regions as a single combined ROI — passing more than one region name unions their masks into one target, and the result's region name is the selected names joined with `+`
- **Combine regions into one ROI** (under the target, on by default): untick it to run one analysis per selected region instead of a union. In a group run, each region is then its own group job
- In mesh space, a bare region name (e.g. `cuneus`) expands to both hemispheres (`lh.cuneus` + `rh.cuneus`)
- **Cortical** lists the subject's surface atlases: `DK40`, `a2009s`, `HCP_MMP1`. In **Voxel** space the same names read volume parcellations: `DK40` reads the DKT volume (FastSurfer's `aparc.DKTatlas+aseg.deep.mgz`, or FreeSurfer's `aparc.DKTatlas+aseg.mgz`), `a2009s` reads `aparc.a2009s+aseg.mgz`, which only a FreeSurfer `recon-all` run writes, and `HCP_MMP1` has no volume version, so a voxel analysis of it stops with an error — analyze it in **Mesh** space. See [FreeSurfer reconstruction and subregions]({{ site.baseurl }}/wiki/fastsurfer/#freesurfer-reconstruction-and-subregions) for which run writes which file
- No surface atlas exists in MNI space; the shipped MNI atlases, the cortical ones included, are label volumes and are used through **Subcortical**

**Subcortical Analysis**

- Choose a volume atlas and one or more of its regions. **Combine regions into one ROI** works as for cortical regions, in single and group runs
- **Subject** space offers the subject's own label volumes: charm's `segmentation/labeling.nii.gz` (whole thalamus, hippocampus, amygdala, …), the FastSurfer and FreeSurfer volumes, including FreeSurfer's hippocampal-amygdala and thalamic-nuclei subfields, and any label volume placed in `m2m_<id>/masks/` (listed as `masks/<file>`)
- **MNI** space offers the atlases shipped with TI-Toolbox (CIT168, MASSP 2021, Harvard-Oxford cortical and subcortical, Cerebellum, Glasser HCP-MMP1.0, Schaefer 2018). The selected regions are transformed into each subject's anatomy with the subject's own registration, exactly as an MNI mask is
- Measure deep structures in **Voxel** space. A deep structure has no cortical surface, so in **Mesh** space the job stops with "… does not overlap the gray-matter surface; analyze it in voxel space instead"
- A region named exactly as an atlas label gets that label, before any longer label containing the name ("subiculum" is not "parasubiculum")
- Results go to `Analyses/<Mesh|Voxel>/subcortical_<region>_<atlas>/`. Python: `analyzer.analyze_subcortical(atlas, region, coordinate_space="subject")`

**Tissue Selection**

- **Job settings ▸ Space options ▸ Tissue** (Gray matter / White matter / GM + WM) applies to **voxel space only** — it is disabled and fixed to gray matter whenever the row's Space is Mesh. The target itself has no tissue or volumetric-evaluation control in the Analyzer
- In voxel mode, the tissue choice selects which field file is loaded by filename prefix (`grey_` for GM, `white_` for WM, no prefix for GM + WM) and builds the corresponding tissue mask

---

## Mesh-Based Analysis

When `space="mesh"`, the `Analyzer` works with SimNIBS mesh files and provides high-resolution analysis of field data on brain surfaces.

### Features

- **Surface Mesh Generation**: Automatic creation of gray matter surface meshes via `msh2cortex` (cached per instance)
- **Atlas Integration**: Support for SimNIBS native atlases (DK40, a2009s, HCP_MMP1)
- **3D Visualization**: Generation of mesh files for 3D viewing

### Cortical ROI Analysis

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_max.png" alt="TI Max Field in ROI">
    <em>TInorm field distribution in ROI (Left Insula)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_normal.png" alt="TI Normal Field in ROI">
    <em>TInormal field distribution in ROI (Left Insula)</em>
  </div>
</div>

### Spherical ROI Analysis

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_max.png" alt="Spherical TI_max Analysis">
    <em>Spherical ROI analysis showing TI_max field distribution within a 10mm radius sphere at coordinates (-31.3, 24.0, -37.0)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_normal.png" alt="Spherical TI_normal Analysis">
    <em>Spherical ROI analysis showing TI_normal field distribution for the same target region, demonstrating directional field components</em>
  </div>
</div>

---

## Voxel-Based Analysis

When `space="voxel"`, the `Analyzer` handles NIfTI format files and integrates with FreeSurfer atlases for detailed volumetric analysis.

### Features

- **NIfTI Support**: Direct analysis of .nii, .nii.gz, .mgz files
- **FreeSurfer Integration**: Automatic atlas region extraction and resampling
- **Visualization Overlays**: Generation of ROI-specific NIfTI overlays

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_voxel_montage_1.png" alt="Spherical TI_max Analysis">
    <em>Right Hippocampus ROI analysis showing TI_max field distribution given a 1mA:1mA stimualtion</em>
  </div>
</div>

---

### What an analysis writes

One folder per analysis, under `Analyses/<Mesh|Voxel>/<name>/`, holding the data, the
field-distribution histogram and **exactly one scene**:

| File | What it is |
|---|---|
| `results.csv` | every statistic in the [AnalysisResult](#analysisresult-fields), one row each |
| `analysis.json` | the target and settings the run used |
| `roi_overlay.msh` + `.msh.opt` (mesh) | the central surface with `<field>_ROI` node data: the field at the ROI's nodes, exactly `0` everywhere else (and `TI_normal_ROI` when the run had a normal field) |
| `roi_overlay.nii.gz` (voxel) | the field, zero outside the ROI, on the field's own grid |
| `histogram.png` | the field distribution over the whole grey matter (mesh) or the whole selected tissue (voxel) — area-weighted (mesh) or volume-weighted (voxel) — with every bar coloured by the fraction of it inside the ROI (blue → red, colour bar), the ROI mean and the focality cutoffs (50/75/90/95 % of the GM 99.9th percentile) marked, and a whole-head / ROI stats box |
| `scene.tetravox.json` | a Tetravox scene of the overlay: in voxel space the field over your `T1.nii.gz`; in mesh space the whole cortex translucent with the ROI's field coloured on top, cursor on the ROI, colour bar on |
| `scene.png` | a picture of that scene, when Tetravox is installed on the machine running the app |

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_lh.insula_whole_head_roi_histogram.png" alt="Analyzer field-distribution histogram" style="width: 100%; max-width: 850px;">
  <em>Example field-distribution histogram, including target statistics and whole-grey-matter focality thresholds (v2 example, which counted nodes; v3 weights each bar by area or volume).</em>
</div>

The scene is a few kilobytes and points at the overlay and the T1 — nothing is copied. Open it
from the job's **Artifacts** tab (**Open in Tetravox**) or by double-clicking the file.

### AnalysisResult Fields

Every analysis call returns an `AnalysisResult` dataclass. Its statistics are exactly the quantities in the [Quantities of Interest](#quantities-of-interest) table, under the same names (`roi_mean`, `gm_mean`, `roi_focality`, `normal_*`, `percentile_*`, `focality_*_area`). The remaining fields identify and size the analysis:

- `field_name`, `region_name`, `space` ("mesh"/"voxel"), `analysis_type` ("spherical"/"cortical"/"subcortical"/"mask")
- `n_elements`: mesh nodes or voxels in the ROI
- `total_area_or_volume`: ROI area (mesh, $$\mathrm{mm}^2$$) or volume (voxel, $$\mathrm{mm}^3$$)
- The `normal_*` fields are `None` in voxel space, and for runs that predate `TI_normal` support for their mode -- see [mTI Analyses](#mti-analyses)

> **Voxel-space `focality_*_area` values written by v2.3.0-v2.5.0 are 10x too large** --
> they were computed in "cm^2" from a volume. v3.0.0 reports them in $$\mathrm{cm}^3$$;
> see [release notes]({{ site.baseurl }}/releases/v3.0.0/#scientific-corrections) (SCI-03) for whether to re-run or rescale.

---

## mTI Analyses

The analyzer handles multipolar (mTI) simulations with the same `Analyzer` class, the same `analyze_sphere` / `analyze_cortex` / `analyze_spheres` calls, and the same ROI types — there is no mTI mode to select. The only signal it uses is whether `{simulation}/mTI/mesh/` exists on disk.

### What it reads

| Space | mTI source                                               | Standard TI source                      |
| ----- | -------------------------------------------------------- | --------------------------------------- |
| Mesh  | `mTI/mesh/surfaces/{sim}_mTI_central.msh` (field values) | `TI/mesh/surfaces/{sim}_TI_central.msh` |
| Voxel | `mTI/niftis/` (`grey_` / `white_` prefix per tissue)     | `TI/niftis/`                            |

An mTI run also writes the intermediate per-carrier envelopes (`TI_AB`, `TI_CD`, ...) into `TI/mesh/`. Those are **not** what the analyzer reads and are not the mTI result — each is only the two-channel envelope of one carrier on its own.

### What `mTI_max` means for the statistics

`mTI_max` is the joint modulation depth over **all** $$K$$ carriers at once, maximised over direction -- the same "beat envelope" quantity as `TI_max`, just with more carriers in the sum. The math and the safety metrics are documented under [Quantities of Interest](#envelope-math-and-critical-values) above. What matters for analysis is:

- `TI_max` and `mTI_max` are aliases. Whichever spelling is requested, the analyzer resolves it to the on-disk name the detected simulation type actually wrote, so the Field selector lists it once.
- `TI_avg`, `hf_peak` and `hf_sar` can be selected when the run wrote them and go through the identical ROI machinery, each in its own units (see [Quantities of Interest](#quantities-of-interest)).

### TI_normal

`TI_normal` is computed for mTI: the simulator evaluates the $$K$$-carrier envelope along the cortical surface normal (`get_TI_dir`) and writes `{simulation}_mTI_normal.msh` under `mTI/mesh/`. The analyzer resolves that mesh when `TI_normal` is requested for an mTI run, and the `normal_*` statistics (`normal_mean`, `normal_max`, `normal_focality`) are populated the same way as for standard TI. For mTI simulations run before this support existed, the normal mesh is absent — requesting `TI_normal` raises `FileNotFoundError`, and the `normal_*` statistics are `None`; re-run the simulation to get them.

---

## Group Analysis

`run_group_analysis()` runs one analysis — one simulation, space, field and target — over several subjects and returns a `GroupResult`. In the app it is the Analyzer's **Combine into one group analysis** switch: each row contributes its subject, and the run is refused, with the difference named, unless every row has the same simulation, space, field and target.

- **One simulation for every subject.** It is a simulation folder name each subject has (the same montage simulated in each). Rows with different simulations are refused; to compare montages within one subject, run ordinary single analyses, one row per montage.
- MNI coordinates, MNI masks and MNI atlases are transformed into each subject's own anatomy automatically; a group mask must be in MNI space.
- Several spheres, or several regions with **Combine regions into one ROI** unticked, give one group job per sphere or region.

Each run writes its own folder; each subject's own results also go to its `Analyses/` folder, as for a single analysis:

```
derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>_<YYYYMMDD>_<HHMMSS>/
├── group_summary.csv               # one row per subject plus an AVERAGE row
├── group_comparison.pdf            # 2×2 bars per subject: ROI mean, max, focality, normal mean
└── group_analysis_<timestamp>.log
```

Group runs are listed under **Results ▸ Group ▸ Group analyses**. Group analyses from earlier
versions shared one folder, `derivatives/ti-toolbox/logs/group_analysis/`, where each run replaced
the last; those files stay where they are.

---

## Looking at a mesh analysis

When an analysis finishes, open it from [Results]({{ site.baseurl }}/wiki/results/) — the mesh and
the NIfTI outputs both open in TetraVox, the separate desktop viewer the app installs and launches
(see [Viewer]({{ site.baseurl }}/wiki/visualizers/)). Every target type — sphere, atlas region or
mask — writes the same overlay and scene.

> **What's new in v3.** 2.x launched **Gmsh** as a separate X11 program to inspect a mesh result,
> and **Freeview** for a NIfTI one. Both are gone — the container ships neither, and there is no
> X11 anywhere. Viewing is TetraVox, a separate desktop viewer the app installs and launches.
>
> Two more changes to the Analyzer itself: **each row of the jobs table owns its own target**, so
> one submission can analyse different ROIs across subjects; and a **group** run is refused unless
> every row agrees on simulation, space, field and target, with the disagreement named — it is
> never silently resolved to the first row.
>
> Full list: [the v3.0.0 release notes]({{ site.baseurl }}/releases/v3.0.0/).

There is no separate "whole head" analysis type — the Analyzer's `analysis_type` is `spherical`, `cortical`, `subcortical` or `mask`; the whole-GM statistics (`gm_mean`, `gm_max`, the percentiles and focality areas) and the ROI-vs-grey-matter `histogram.png` come with every analysis (mesh or voxel).


## Custom NIfTI mask targets

Choose **NIfTI mask** in a job's Target editor and import a `.nii` or `.nii.gz` file.
All positive voxels belong to the target. Declare **Subject** or **MNI** explicitly:
subject masks retain their coordinates, while MNI masks use the subject's nonlinear m2m
registration and nearest-neighbor sampling. Group analysis requires an MNI mask, registered
separately for each subject.

Mesh analysis samples the mask at gray-matter surface nodes and reports surface-area statistics.
Voxel analysis samples it onto the subject field grid and intersects it with the tissue selected
in the job settings, retaining volume statistics. An empty overlap fails with a clear error.
The script equivalent is `analyzer.analyze_mask(mask_path, coordinate_space="mni")`;
job JSON uses `analysis_type="mask"`, `mask_path`, and `coordinate_space`.

### Target preview

The Scene pane follows the active job. Cortical atlas regions remain clickable. Masks,
subcortical regions and spheres show a read-only target extent on subject anatomy; edit the
target in its form. This previews the geometry, before the analysis applies its tissue and
mesh settings. Incomplete targets or unavailable registration show an explanatory message.
