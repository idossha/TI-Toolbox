---
layout: wiki
title: Flex Search Electrode Optimization
permalink: /wiki/flex-search/
---

**References:**
- [Original Paper: Weise K, Madsen KH, Worbs T, Knösche TR, Korshøj A, Thielscher A. A Leadfield-Free Optimization Framework for Transcranially Applied Electric Currents](https://www.sciencedirect.com/science/article/pii/S0010482525009990)

- [SimNIBS Implementation: Leadfield-free TES Optimization Tutorial](https://simnibs.github.io/simnibs/build/html/tutorial/tes_flex_opt.html#tes-flex-opt)

- [Haber, I., Jackson, A., Thielscher, A., Hai, A., & Tononi, G. TI-Toolbox: An Open-Source Software for Temporal Interference Stimulation Research. Brain Stimulation](https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext)


## Overview

Flex Search uses differential evolution optimization to determine the best electrode positions for TI stimulation. The public API is `run_flex_search(config: FlexConfig) -> FlexResult`, with all configuration expressed through type-safe dataclasses and enums.

**Core capabilities:**
- **Optimization Goals** (`OptGoal` enum): `mean`, `max`, `focality` (threshold-based ROC), or `focality_tf` (threshold-free focality)
- **Post-processing Methods** (`FieldPostproc` enum): `max_TI`, `dir_TI_normal`, or `dir_TI_tangential`
- **ROI Definition** (`ROISpec`): `SphericalROI`, `AtlasROI`, or `SubcorticalROI` dataclasses
- **Anisotropy Support**: Four conductivity models (`scalar`, `vn`, `dir`, `mc`) with configurable max ratio and conductivity
- **Multi-start Optimization**: Run multiple optimization iterations and automatically select the best result
- **Structured Output**: Every run writes a `flex_meta.json` manifest for downstream consumption

## User Interface


<img src="{{ site.baseurl }}/assets/imgs/UI/UI_flex.png" alt="Flex Search Interface" style="width: 80%; max-width: 700px;">

The interface provides comprehensive controls for:
- **Basic Parameters**: Subject selection, optimization goal, and post-processing method
- **Electrode Parameters**: Radius and current settings
- **ROI Definition**: Multiple methods for defining target regions
- **Stability Options**: Iteration limits, population size, and CPU utilization
- **Mapping Options**: EEG net electrode mapping capabilities

## Mean TI Field Optimization Demonstration

We demonstrate the effectiveness of flex-search by optimizing electrode positions for the same target ROI using different post-processing methods. The target was the left insula (region 35 of the DK40 atlas) with the goal of maximizing the mean TI field.

### Optimization Setup
- **Subject**: 102
- **Target ROI**: Left insula (DK40 atlas, region 35)
- **Goal**: Maximize mean field in ROI
- **Electrode**: 4mm radius, 8mA current

### Results: Maximum TI Field Optimization

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_max_TI_field.png" alt="Maximum TI Field">
    <em>Maximum TI field distribution showing optimization results</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_max_TI_ROI.png" alt="Maximum TI ROI Targeting">
    <em>ROI targeting analysis for maximum TI field optimization</em>
  </div>
</div>

**Optimization Summary:**

| Metric | Value |
|--------|--------|
| Final Goal Value | -2.320 |
| Duration | 25.1 minutes |
| Peak Field (99.9%) | 4.17 V/m |
| Median ROI Field | 2.21 V/m |

## Focality Optimization with Dynamic Thresholding

The focality optimization goal is a multi-objective function balancing ROI targeting with out-of-ROI field minimization:

### Non-ROI Definition Methods
- **Everything Else**: Uses the complement of the ROI (everything outside the target region)
- **Specific Region**: Define a custom non-ROI using the same methods as ROI definition (spherical, atlas, subcortical)

### Focality Thresholds - Critical for Optimization Success

As described in the [original paper](https://www.sciencedirect.com/science/article/pii/S0010482525009990), focality optimization is fundamentally a **constrained multi-objective problem** where:

- **Target Region (ROI)**: Field strength must exceed specified thresholds
- **Avoidance Region (Non-ROI)**: Field strength must remain below specified thresholds
- **Optimization Goal**: Maximize field intensity in ROI while minimizing field spread outside ROI

#### Threshold Configuration Options

- **Single Threshold**: Binary classification where field must be below threshold in non-ROI and above threshold in ROI
- **Dual Thresholds**: Independent thresholds for each region, allowing asymmetric optimization constraints
- **Dynamic Adaptation**: Thresholds automatically adjust based on field distribution characteristics during optimization

<img src="{{ site.baseurl }}/assets/imgs/flex-search/focality_thresholds.png" alt="Focality Threshold Analysis" style="width: 70%; max-width: 400px;">

**Focality optimization analysis**: Comparative evaluation of threshold strategies reveals critical insights: threshold selection profoundly impacts results, with relative thresholds (50% of peak) yielding 75% higher focality than fixed thresholds, while 80% thresholds reduce focality by 37%, compared to fixed thresholds (0.1V/m and 0.3V/m) highlighting the importance of threshold optimization for precise neuromodulation. Dynamic % based thresholds were derived automatically from an intial pass of mean TImax search and applied to the upper bound only. The lower bound was kept at 20% from that value. *Data regarding focality thresholds and optimization performance comes from the supplementary information of the [TI-Toolbox reference](https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext).*

## Threshold-Free Focality Optimization

The `focality_tf` goal targets the same objective as the ROC goal above -- concentrate the field in the ROI and keep it out of the non-ROI -- without asking the user to commit to a field threshold in advance. Instead of counting elements above and below a cutoff, it scores the ratio of the ROI field to the upper tail of the non-ROI field:

**focality_tf** = mean(E<sub>ROI</sub>)<sup>1+w</sup> / p95(E<sub>non-ROI</sub>)

Larger is better; the optimizer minimizes its negative. The denominator uses the 95th percentile rather than the mean or the maximum, so the score is driven by the hot spots that actually matter for off-target stimulation while staying insensitive to a handful of extreme elements.

### The Intensity Weight

The exponent `w` is the `intensity_weight` parameter (range `[0, 1]`, default `0.0`) and controls the trade-off between focality and on-target strength:

- **`intensity_weight = 0.0`** -- balanced "tail" form. The ROI field enters linearly, so a montage that halves the off-target field is worth as much as one that doubles the on-target field. This is the default.
- **`intensity_weight = 1.0`** -- intensity-first. The ROI field is squared, so the objective strongly prefers solutions that deliver field to the target even at the cost of some spread.
- Intermediate values interpolate between the two.

### Why Threshold-Free Matters

The ROC goal's result depends entirely on a threshold that the user has to choose before the optimization runs, and the [threshold analysis above](#focality-thresholds---critical-for-optimization-success) shows how much that choice moves the outcome. The deeper problem is that a threshold pair which is well-calibrated for one target can be **jointly infeasible for another**: if no montage on the scalp can simultaneously push the ROI above the lower bound and hold the non-ROI below the upper bound, every candidate scores identically, the objective landscape goes flat, and differential evolution has no gradient to follow. This is most likely exactly where optimization is needed most -- deep targets.

`focality_tf` has no such failure mode. It is a continuous ratio, so it always ranks one candidate above another and always hands the optimizer a usable landscape, whatever the depth of the target.

<img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_objective-comparison.png" alt="Optimization goal comparison" style="width: 80%; max-width: 700px;">

**Focality versus on-target intensity for each optimization goal, measured across subjects and deep targets.** In our tests all threshold-free objectives outperformed both ROC threshold settings on focality (AUC), and the ROC goal failed outright at targets where its thresholds were jointly infeasible. This does not make `focality` obsolete -- where a defensible and attainable threshold exists, it optimizes precisely the criterion the user cares about -- but it does mean the threshold has to be validated for the target at hand.

### When to Use Which

| | `focality` (ROC) | `focality_tf` (threshold-free) |
|---|---|---|
| **Thresholds required** | Yes -- `thresholds` must be set | No |
| **What is scored** | ROC separation of ROI and non-ROI elements at the chosen cutoff | mean ROI field over the 95th percentile of the non-ROI field |
| **Behavior at deep targets** | Can degenerate to a flat landscape if the thresholds are jointly infeasible | Stays graded; always ranks candidates |
| **Intensity trade-off** | Implicit in the threshold choice | Explicit via `intensity_weight` |
| **Use when** | You have a threshold you can defend and that the target can actually reach -- e.g. derived from a prior mean TI<sub>max</sub> pass | You do not want to commit to a threshold up front, or the target is deep enough that feasibility is in doubt |

Both goals use the same ROI and non-ROI setup, so switching between them requires no change to the region definitions. One restriction applies only to `focality_tf`: it cannot be run with `detailed_results=True` (see [Detailed Results](#detailed-results)).

## Current-Ratio Optimization

By default the two TI channels carry equal current. The `optimize_current_ratio` flag opts into searching that split as well: the **total** injected current is held constant and divided between the two channels, with `ratio_levels` (default `21`) setting the density of the grid, which spans **1:3 to 3:1**. The total defaults to `2 x current_mA` and can be set explicitly with `ratio_total_mA`.

### What Each Channel Carries

Holding the *total* fixed means the *per-channel* current necessarily moves. Over the 1:3 to 3:1 grid each channel spans a quarter to three quarters of the total -- that is, **0.5x to 1.5x the configured `current_mA`** (the GUI's *Electrode Current*). With the default total of `2 x current_mA` and `current_mA = 2.0`, a channel is driven anywhere between `1.0 mA` and `3.0 mA`, with the pair always summing to `4.0 mA`. `current_mA` is therefore the center of the searched range, not a per-channel ceiling: choose it (or set `ratio_total_mA` directly) so that the 1.5x end is still within the dose you intend to deliver.

The grid always contains the balanced 1:1 split -- `ratio_levels` is rounded up to the next odd number so the midpoint of the sweep is the exact even split. Enabling the ratio search therefore cannot return a worse solution than the equal-current montage it would otherwise have used.

### Why the Split Matters

The TI envelope amplitude is capped by the weaker of the two channels -- for co-linear fields the modulation depth is `2 * min(|E1|, |E2|)`. The split therefore does two things at once: it **scales** the envelope, because the ceiling moves with the weaker channel, and it **steers** it, because the locus where the two channels balance shifts toward the weaker one. Published TI montages essentially never have their optimum at 1:1, so leaving the split fixed gives up a free axis of the search space.

<img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_current-ratio.png" alt="Current ratio effect on the TI envelope" style="width: 80%; max-width: 700px;">

**How the two-channel current split scales and steers the TI envelope.** Because the envelope is bounded by the weaker channel, an unequal split trades peak amplitude against the position of the interference locus.

### Searched Jointly, Not Afterwards

The ratio is optimized **jointly with electrode placement**, not applied as a post-hoc refinement. Every candidate placement is scored at its own best split, so the optimizer sees the landscape it will actually be evaluated on. Running a ratio sweep after the fact would only refine a montage that had already been selected under a 1:1 assumption -- a different, and worse, optimum.

The joint search costs almost nothing. The FEM is linear, so for a fixed electrode placement the per-channel fields simply scale with the injected current: evaluating an additional split is a rescale of the already-computed fields and a re-combination of the envelope, with no new FEM solve. Candidate splits are ranked on a deterministic subsample of the non-ROI, and only the winning split is re-scored on the full non-ROI, so the several-million-element non-ROI is traversed once per evaluation rather than once per split.

Current-ratio optimization works with **any** goal (`mean`, `max`, `focality`, `focality_tf`). The winning split is applied to the final electrode simulation, so the fields written to disk are the ones the objective actually scored, and it is recorded in the run manifest (`flex_meta.json`).

### Python Usage

```python
from tit.opt import FlexConfig, run_flex_search

config = FlexConfig(
    subject_id="101",
    goal="focality_tf",           # threshold-free focality
    postproc="max_TI",
    current_mA=2.0,
    intensity_weight=0.0,         # 0 = balanced, 1 = intensity-first
    electrode=FlexConfig.ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],
        gel_thickness=4.0,
    ),
    roi=FlexConfig.SphericalROI(
        x=-35.0, y=5.0, z=5.0,
        radius=10.0,
        use_mni=True,
    ),
    non_roi_method="everything_else",
    optimize_current_ratio=True,  # search the channel split jointly
    ratio_total_mA=4.0,           # defaults to 2 * current_mA
    ratio_levels=21,              # grid density, spanning 1:3 .. 3:1
)

result = run_flex_search(config)
print(f"Best value: {result.best_value:.4f}")
```

Note that `thresholds` is not used by `focality_tf` and can be omitted; it remains required for the ROC-based `focality` goal.

### Detailed Results

`detailed_results=True` cannot be combined with the current-ratio search or with the `focality_tf` goal. Both install a Python callable as the optimization goal, and SimNIBS cannot serialize a callable into its detailed-results HDF5 file, so requesting the combination raises an error before the run starts rather than failing partway through. Leave `detailed_results` at its default of `False` -- the GUI does not expose it -- and read run metadata from `flex_meta.json` instead.

## Multi-Start Optimization

Flex Search supports multi-start optimization to ensure robust and reliable results by running multiple optimization iterations and selecting the best solution:

- **Multiple Runs**: Configure the number of optimization runs (default: 1, recommended: 3-5 for critical applications)
- **Best Solution Selection**: Automatically selects the optimization run with the lowest function value
- **Comprehensive Reporting**: Generates multi-start summary files with run-by-run analysis

<img src="{{ site.baseurl }}/assets/imgs/flex-search/multi-start.png" alt="Multi-Start Optimization Strategy" style="width: 50%; max-width: 400px;">

**Multi-start optimization validation**: Analysis demonstrates that running multiple independent optimizations with different random seeds yields superior solutions compared to single runs; 4.18% improvement in mean TImax. While statistically significant, the modest gains should be weighed against the increased computational cost. *Data regarding multi-start optimization performance comes from the supplementary information of the [TI-Toolbox reference](https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext).*

## Electrode Mapping and Target Accessibility

The transition from unconstrained optimization solutions to practical electrode montages represents a critical step in clinical translation. While genetic algorithms can identify theoretically optimal electrode positions anywhere on the scalp, its transition to clinical application may be difficult. Our electrode mapping algorithm bridges this gap by finding the best approximation of optimized positions using available electrode sites. For this study, we utilized the inner 185 electrodes of the GSN-HydroCel-256 system (EGI/Philips), which provides high-density coverage. A combinatorial optimization method that solves the assignment problem in polynomial time. By minimizing the total Euclidean distance between optimized and standard positions, this approach ensures good representation of the intended field distribution while maintaining practical feasibility.

<img src="{{ site.baseurl }}/assets/imgs/flex-search/mapping_distance.png" alt="Electrode Mapping Distance Analysis" style="width: 70%; max-width: 600px;">

**Electrode mapping challenges**: Analysis of optimized electrode positions reveals depth-dependent mapping distances across anatomical targets, with subcortical structures like the hippocampus requiring significantly larger electrode separations (11.74 ± 5.33 mm) compared to cortical regions like the insula (7.30 ± 1.38 mm) or spherical ROIs (8.01 ± 1.43 mm). This pattern reflects the fundamental challenge of targeting deep brain structures with scalp electrodes, where optimal montages often requires large distances between electrodes which may be positioned on the lower scalp that does not have dense electrode coverage. *Data regarding electrode mapping distances comes from the supplementary information of the [TI-Toolbox reference](https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext).*

## Reports and mapped electrode labels

Flex-search reports include the selected optimized configuration, subject-space optimized coordinates, and mapped EEG-net labels/positions when `electrode_mapping.json` is produced. Ranked rows show mapped labels for the selected mapped solution; rows without mapping data are intentionally left unlabeled rather than guessing electrode names. If optional montage or field-map images are unavailable, the report includes an explicit note and the tables remain the source of truth.

For template/MNI workflows, confirm that the selected EEG net is available and that final mapped-electrode simulation is enabled if you need report imagery from the practical mapped montage.

## Output Manifest (`flex_meta.json`)

Every flex-search run writes a `flex_meta.json` file to the output folder. This manifest is the single source of truth for run metadata -- downstream consumers (simulator tab, GUI) read this instead of parsing folder names.

The manifest contains:
- Run configuration (goal, postproc, electrode, ROI, anisotropy)
- Result summary (success, best value, all function values)
- Timestamps and labels for display

## Advanced Features

### Anisotropy Support

Flex-search passes anisotropy parameters directly to SimNIBS, enabling optimization with direction-dependent tissue conductivity. The `anisotropy_type` parameter accepts four models:

| Type | Description |
|------|-------------|
| `scalar` | Isotropic, piecewise-constant conductivity (default) |
| `vn` | Volume-normalized anisotropic tensors |
| `dir` | Direct linear rescaling of diffusion tensor eigenvalues |
| `mc` | Mean conductivity (isotropic but spatially varying) |

Additional parameters `aniso_maxratio` (default: 10.0) and `aniso_maxcond` (default: 2.0) control the anisotropy bounds.

### Valid Skin Region Validation

Flex-search optimization is constrained to valid skin regions where electrodes can be safely placed. The green region represents the valid skin area for electrode placement during optimization, while red "x" marks indicate HD-EEG electrodes that fall outside this valid region.

<img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin.png" alt="Valid Skin Region" style="width: 80%; max-width: 600px;">

If electrode positions fall outside the valid skin region, the valid skin region can be manipulated through preprocessing, or ex-search can be used as an alternative since it is not constrained by skin region limitations.

### Valid Skin Region Margin

The flex-search skin constraint can be adjusted directly from scripts or from the GUI. `skin_region_margin_mm` applies a signed millimeter margin to the default SimNIBS valid skin region: negative values constrict the region, positive values expand it. The default is `0.0`, which preserves the standard SimNIBS mask.

For positive margins, `avoid_landmark_regions=True` keeps fiducial-derived ear and orbital exclusion zones invalid. This guard uses scalp landmarks only (`Nz`, `LPA`, and `RPA`) and does not depend on eye tissue labels.

<img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin_region_margin_landmark_guarded.png" alt="Valid skin region margin comparison" style="width: 100%; max-width: 1200px;">
