---
layout: wiki
title: Flex Search Electrode Optimization
permalink: /wiki/flex-search/
---

**References:**

- [Original Paper: Weise K, Madsen KH, Worbs T, Knösche TR, Korshøj A, Thielscher A. A Leadfield-Free Optimization Framework for Transcranially Applied Electric Currents](https://www.sciencedirect.com/science/article/pii/S0010482525009990)

- [SimNIBS Implementation: Leadfield-free TES Optimization Tutorial](https://simnibs.github.io/simnibs/build/html/tutorial/tes_flex_opt.html#tes-flex-opt)

- [Haber, I., Jackson, A., Thielscher, A., Hai, A., & Tononi, G. TI-Toolbox: An Open-Source Software for Temporal Interference Stimulation Research. Brain Stimulation](<https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext>)

## What flex-search does

Flex-search places two electrode pairs freely on the subject's valid scalp and uses differential evolution, solving the FEM for every candidate, to find the placement that best meets a goal in a target region. Unlike [ex-search]({{ site.baseurl }}/wiki/ex-search/) it is not restricted to an EEG net, and unlike ex-search it is stochastic: a finished run is the best placement it evaluated, not a proven global optimum.

- **Goals**: Mean TImax, Max TImax (99.9th percentile), threshold-free focality, threshold-based focality.
- **Field post-processing**: `max_TI` (the maximum TI envelope) or `dir_TI_normal` / `dir_TI_tangential` (its component normal or tangential to the cortical surface).
- **Conductivity**: isotropic (`scalar`) or volume-normalized anisotropic (`vn`).
- **Optional**: a joint search over the two channels' current split, several independent optimization runs, and a simulation of the winner on the free or EEG-net-mapped positions.

For scripting, the same form is `FlexConfig`; see [Scripting]({{ site.baseurl }}/wiki/scripting/#optimizer--flex-search).

## In the application

Flex-search is the **Flex** method on the **Optimizer** page (⌘2).

<img src="{{ site.baseurl }}/assets/imgs/v3/optimizer-page.png" alt="The Optimizer page: a Flex job for subject 101 with lh.rostralmiddlefrontal from DK40 as the target, highlighted in the atlas pane" style="width: 100%; max-width: 1000px;">
<em>The Optimizer. Flex is a <strong>method</strong> in a job row, not a page of its own; the atlas in the pane is the ROI you are choosing.</em>

A Flex job row has a **Target** and four form sections:

- **Objective**: goal, post-processing and, for the focality goals, the non-ROI, intensity preference and threshold mode.
- **Electrodes**: current, shape, size, gel, minimum distance and the current-ratio search.
- **Solver**: differential-evolution settings, conductivity model and the valid skin region.
- **After the search**: which simulations run on the winning placement.

## Choosing the target

The **Target** picker has four modes:

- **Cortical**: regions from a FreeSurfer `.annot` atlas, chosen by name; regions from both hemispheres can be combined into one target.
- **Subcortical**: labels from a volumetric atlas in subject or MNI space, restricted to GM, WM or both.
- **Spherical**: one or more spheres (X/Y/Z and radius, mm) in subject or MNI coordinates.
- **NIfTI mask**: a local `.nii` / `.nii.gz`; positive voxels are the target, in subject or MNI space.

A sphere is evaluated on the cortical surface unless **Volumetric evaluation** is checked. For a deep target (amygdala, hippocampus, thalamus) leave it unchecked and the sphere scores the overlying cortex instead of the structure, so check it and pick the tissue for anything off the cortical ribbon.

The Scene pane follows the active job. Cortical and subcortical regions are drawn, and clicking a region adds it to the target or removes it. A subject-space target is drawn on the subject's own head, or on the packaged reference head when the subject's head model has no copy of the atlas, which is always the case for a subcortical atlas (the pane says which head it shows); an MNI-space target is drawn on MNI152. Spherical and NIfTI-mask targets are not drawn in the pane: it offers **Open target in TetraVox** instead. For MNI atlases and the **Explode** view, see [Atlases]({{ site.baseurl }}/wiki/atlases/).

## Goals

**Mean TImax** maximizes the mean field in the ROI. **Max TImax** maximizes its 99.9th percentile, a robust peak.

**Threshold-free focality** concentrates the field in the ROI and keeps it out of the non-ROI without a field threshold. It scores the ratio of the mean ROI field to the mean non-ROI field:

$$
\texttt{focality\_tf} =
\frac{\operatorname{mean}\!\left( E_{\mathrm{ROI}} \right)^{\,1+w}}
     {\operatorname{mean}\!\left( E_{\text{non-ROI}} \right)}
$$

Larger is better. The exponent $$w$$ is **Intensity preference** (0 to 1, default 0): at 0 the score is a pure contrast, unchanged by scaling both regions equally; at 1 the ROI mean is squared, favouring a stronger target field while still penalizing spread. The mean ratio does not constrain isolated off-target hot spots, and empty, non-finite or degenerate non-ROI values are rejected rather than rewarded.

**Threshold-based focality** is SimNIBS's ROC goal: it rewards ROI coverage above an ROI threshold and penalizes non-ROI coverage above a non-ROI threshold. The thresholds are scoring targets, not enforced constraints, and a pair the target cannot reach leaves many candidates with identical scores.

## Threshold-based focality modes

Under **Threshold mode**:

- **Fixed thresholds**: enter them in V/m. One value is used as both the non-ROI maximum and the ROI minimum; two values are non-ROI maximum, ROI minimum (e.g. `0.2,0.5`).
- **Adaptive thresholds** (default): a first Mean TImax run finds the achievable ROI intensity, then a focality run uses thresholds at a share of it. Defaults: ROI 80 %, non-ROI 20 %.
- **Multi-threshold**: one Mean TImax calibration run, then one focality run per ROI × non-ROI pair of percentages. Defaults: ROI 80, non-ROI 20, 30, 40 (three runs). The form shows the number of combinations and the total cost.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/focality_thresholds.png" alt="Focality Threshold Analysis" style="width: 70%; max-width: 400px;">
</div>

**Threshold choice changes the result.** Relative thresholds (50 % of the peak from a first Mean TImax pass) gave 75 % higher focality than fixed 0.1/0.3 V/m thresholds, while 80 % thresholds reduced it by 37 %. _Data from the supplementary information of the [TI-Toolbox reference](<https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext>)._

## Non-ROI

Both focality goals compare the ROI to a **Non-ROI**:

- **Everything else** (default): the complement of the ROI.
- **Specific region**: a second picker with the same four modes.

A specific region can be a different type from the ROI (for example a sphere ROI against a cortical atlas region); each is built as what it is. Non-ROI spheres keep their own Subject/MNI space and their own surface/volumetric setting. A volumetric non-ROI is evaluated on the **ROI's tissue** when the ROI is also volumetric; against a cortical-surface ROI it uses its own tissue setting.

## Which focality goal?

|                       | Threshold-based (ROC)                                                         | Threshold-free                                                  |
| --------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Thresholds**        | Required (fixed, adaptive or multi-threshold)                                 | None                                                            |
| **What is scored**    | ROC separation of ROI and non-ROI at the chosen cutoffs                       | mean ROI field^(1 + w) / mean non-ROI field                     |
| **Failure mode**      | Flat scores when the threshold pair is unreachable, common at deep targets    | A clean separation can still mean a weak target field           |
| **Intensity trade-off** | Implicit in the thresholds                                                  | Explicit via the intensity preference                           |
| **Use when**          | You have a threshold you can defend and the target can reach                  | You do not want to commit to a threshold, or the target is deep |

Neither goal guarantees a dose. **Always read a focality score next to the ROI mean field it was computed on.** Both goals use the same ROI and non-ROI, so switching between them needs no change to the regions.

## Electrodes

Flex-search optimizes exactly **two electrode pairs**, one per TI channel.

- **Current**: per channel, mA (app default 1 mA). Each pair injects +/− this current.
- **Shape**: **Ellipse** or **Rectangle**. SimNIBS supports circular electrodes here, so an ellipse must have equal dimensions; for unequal sides use a rectangle.
- **Dimensions (x, y)** and **Gel thickness**: default 8 × 8 mm, gel 4 mm.
- **Min distance**: minimum distance between electrodes, default 5 mm.

## Current-ratio search

By default both channels carry the same current. With **Current ratio ▸ Optimize** checked, the search also chooses how a fixed **total** current is split between the channels:

- **Ratio total current**: blank means 2 × the electrode current.
- **Ratio levels** (default 21): grid density over 1:3 to 3:1, rounded up to an odd number so the 1:1 split is always included.
- Each channel then carries 25 % to 75 % of the total, i.e. 0.5× to 1.5× the configured current; choose the current so the 1.5× end is still a dose you intend to deliver.

The split is searched **jointly with placement**: every candidate is scored at its own best split, which costs a rescale of already-solved fields, not a new FEM solve. It works with every goal. The winning split is used in the final simulation and recorded as `current_split` in `flex_meta.json`.

**What it buys: usually little.** In an exhaustive leadfield search of every EEG 10-10 montage at every split (2 heads, 4 targets, 4 mA total), the best 1:1 montage was already optimal or within 0.8 % for **Mean TImax**, and within 4 % for **Threshold-free focality** at **Intensity preference** 1. Winning splits were always near 1:1 (1.9:2.1 to 2.2:1.8). With each channel capped at a fixed current, 1:1 at the cap always won.

**Why.** The envelope is capped by the weaker channel, so the best split is the one that balances the two channels at the target. Placement already does that: the best montages are balanced at 1:1, so a split only rescues montages that start out unbalanced, and those rank lower to begin with.

**Caution.** With **Threshold-free focality** at **Intensity preference** 0, the score ignores overall strength, so an extreme split can raise the score while the target field falls (by up to 70 % in the study). Use **Intensity preference** 1 with the ratio search, and check the target field of the result.

**Cost.** It adds no FEM solves. Run time rises under 1 % with **Mean TImax** and about 20 % with **Threshold-free focality**, where every split is scored against the non-ROI. A matched-seed benchmark (ernie, left insula, 4-5 seeds) showed no worse placements, and the search is unchanged when the option is off.

**When to use it:** when placement is constrained (few or fixed electrodes), or to confirm 1:1. Otherwise leave it off (the default).

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_current-ratio.png" alt="Current split versus placement" style="width: 100%; max-width: 900px;">
</div>

**Current split versus placement.** (A) The best 1:1 montage peaks at 1:1, while a weaker montage peaks off 1:1. (B) The gain of searching the split together with placement, over the best 1:1 montage, at 4 mA total.

## Solver

| Control                | App default | Notes                                                        |
| ---------------------- | ----------- | ------------------------------------------------------------ |
| **Optimization runs**  | 1           | Independent runs (1–20); the best valid one is kept          |
| **Max iterations**     | 500         | Generations of differential evolution                        |
| **Population size**    | 13          |                                                              |
| **Tolerance**          | 0.1         | Convergence tolerance                                        |
| **Mutation (min, max)**| 0.01, 0.5   |                                                              |
| **Recombination**      | 0.7         |                                                              |

The cost line under the section reads `population × generations [× runs] [× sweeps] ≈ N solves`. CPU use is set globally under **Settings ▸ Project ▸ Execution** (CPU limit), not per job.

Several runs explore different starting populations; each run's best value is listed in `flex_meta.json` (`result.all_values`, with `result.best_run_index` for the winner) and gets its own row in the report.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/multi-start.png" alt="Multi-Start Optimization Strategy" style="width: 50%; max-width: 400px;">
</div>

**Multiple runs help modestly**: the best of several independent runs improved mean TImax by 4.18 % over a single run, at a proportional cost. _Data from the supplementary information of the [TI-Toolbox reference](<https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext>)._

## Valid skin region

Electrodes are only placed on the valid skin region. In the figure, green is valid skin and red "x" marks are EEG-net electrodes outside it; turn on **Solver ▸ Skin visualization ▸ Plot EEG net electrodes** and choose a net to draw them.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin.png" alt="Valid Skin Region" style="width: 80%; max-width: 600px;">
</div>

**Solver ▸ Skin region margin** (mm, default 0) grows (positive) or shrinks (negative) the SimNIBS valid region. With a positive margin, **Landmark exclusion ▸ Avoid eye/ear landmarks** (on by default) keeps zones around the fiducials (`Nz`, `LPA`, `RPA`) invalid. If the target needs positions outside the region, adjust the margin or use ex-search, which is not limited by it.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin_region_margin_landmark_guarded.png" alt="Valid skin region margin comparison" style="width: 100%; max-width: 1200px;">
</div>

## Anisotropy

**Solver ▸ Anisotropy type** is **Isotropic (scalar)** (default) or **Volume-normalized (vn)**, which needs the subject's DTI tensor (see [Diffusion processing]({{ site.baseurl }}/wiki/diffusion-processing/)). **Anisotropy max ratio** (default 10) and **Anisotropy max conductivity** (default 2 S/m) bound the tensors.

## After the search

- **Run final electrode simulation**: simulate the winning free placement (off by default).
- **Run simulation with mapped electrodes**: map the winner onto an **EEG net template** and simulate that montage. The mapping algorithm is described in [Electrode mapping]({{ site.baseurl }}/wiki/electrode-mapping/). A finished run can also be mapped later from the Simulator (below).

## Results

Open a finished run in **Results ▸ Evaluated candidates**. Expand the preview pane for a side-by-side table and plot; the plot defaults to ROI mean intensity against recorded focality, and selecting a row or point highlights the same candidate and updates the montage preview. Outlined points are the frontier among the loaded candidates (up to 10,000), not a guaranteed global Pareto front. Read intensity alongside focality: a high ratio can still have a weak target field. **Use in Simulator** creates an editable draft of the candidate; nothing runs automatically.

**Simulating a candidate on a cap.** In the Simulator, the placement selector keeps **Optimised (XYZ)** or snaps the candidate to one of the subject's EEG nets. Snapping assigns distinct cap sites, keeps the currents and electrode settings, and shows hollow original positions with dashed displacement links (straight-line mm). Switching back restores the recorded positions. Optimization metrics describe the original candidate; evaluate a snapped montage with a new simulation.

**Report.** Every run writes a flex-search report: the target, what the score means, the optimized electrode centres with the valid-scalp figure, the dose, and one row per optimization run. It draws no EEG cap, because flex positions are free; mapped labels, when mapping ran, are in `electrode_mapping_<net>.json` (older runs wrote `electrode_mapping.json`, which is still read). See [Reports]({{ site.baseurl }}/wiki/reports/).

**`flex_meta.json`.** Every run writes this manifest to its folder; the app reads it instead of parsing folder names. It records the goal, post-processing, current, electrode, ROI and non-ROI, thresholds, intensity weight, current-ratio settings and chosen `current_split`, number of runs, minimum electrode distance, and the result (`success`, `best_value`, `best_run_index`, `all_values`). Evaluated candidates are under `candidate_history/`. See [Results]({{ site.baseurl }}/wiki/results/#on-disk) for the folder layout.

## Example outputs

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_flex-search.png" alt="Flex-search optimized electrode placement">
    <em>Free placement: electrodes anywhere on the valid scalp.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_mapping.png" alt="Optimized electrodes mapped to an EEG net">
    <em>The same placement mapped to the nearest distinct EEG-net sites.</em>
  </div>
</div>

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_max_TI_field.png" alt="Maximum TI field over the brain surface">
    <em><code>max_TI</code>: the maximum TI envelope.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_Normal_field.png" alt="Normal field component over the brain surface">
    <em><code>dir_TI_normal</code>: the component normal to the cortex.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_tangent_field.png" alt="Tangential field component over the brain surface">
    <em><code>dir_TI_tangential</code>: the component tangential to the cortex.</em>
  </div>
</div>
