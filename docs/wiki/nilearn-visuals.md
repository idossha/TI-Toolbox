---
layout: wiki
title: Nilearn Visuals
permalink: /wiki/nilearn-visuals/
---

The Nilearn Visuals extension creates publication-ready visualizations of temporal interference (TI) and multipolar (mTI) stimulation fields using the Nilearn neuroimaging library. It averages the chosen simulations in MNI space and draws the result as a multi-slice figure with atlas outlines and as a glass-brain figure, both saved as PDF files.

## Key Features

- **Group Averaging**: Average across subject/simulation pairs. TI and mTI simulations can be averaged together, and a single pair is a complete visualization
- **Multiple View Types**: Sagittal, coronal and axial slices, and glass brain projections
- **Atlas Integration**: Outline every region of a chosen atlas over the field for anatomical reference. The atlases ship with TI-Toolbox and work offline
- **Data-Driven Thresholding**: The display range comes from the averaged field by default. You can also give cutoffs in V/m or as percentiles
- **High-Resolution Output**: Publication-quality PDF files

## User Interface

Turn the extension on in **Settings ▸ Extensions ▸ Nilearn visuals** (a reload applies the change), then open **Extensions ▸ Nilearn visuals** in the sidebar.

### Subject-Simulation Selection

The **Subjects** table holds the pairs that go into the group average, one **Subject** and one **Simulation** per row:

- **Add pair**: add a row, then pick its subject and one of that subject's simulations
- **Clear all**: reset the table to a single empty row

All rows run as one job. A row without a subject or without a simulation blocks the run.

### Visualization Parameters

#### Output Configuration
- **Output ▸ Sub-directory name** (required): the folder created inside `derivatives/ti-toolbox/nilearn_visuals/` for this run's files

#### Atlas and Region
- **Visualization parameters ▸ Atlas selection**: the atlas whose regions are outlined on the slice figure (see [Atlas Options](#atlas-options))
- **Visualization parameters ▸ Region selection**: **All regions** is the only choice. Every region of the chosen atlas is outlined; picking specific regions is not available

#### Threshold Settings
- **Visualization parameters ▸ percentile checkbox** (*Give cutoffs as percentiles (0–100) of the field's non-zero voxels instead of V/m*): off, the cutoffs are in V/m; on, they are percentiles. Switching it clears both values, because a number typed in one unit means nothing in the other
- **Minimum cutoff**: field values below it are hidden. Empty means the 95th percentile of the averaged field's non-zero voxels
- **Maximum cutoff**: the top of the colour bar. Empty means the 99.9th percentile of the averaged field's non-zero voxels

Both cutoffs start empty, and each can be left empty on its own. Click **Generate images** to queue the job.

## Workflow Example

### Basic Group Visualization

1. **Check the inputs**: every simulation is read as its MNI-space NIfTI, written by the job when the simulation did not (see [File Format Requirements](#file-format-requirements))
2. **Open tool**: enable **Nilearn visuals** in **Settings ▸ Extensions**, then select it under **Extensions** in the sidebar
3. **Configure Subjects**: use **Add pair** and choose a subject and a simulation for each row
4. **Set Parameters**:
   - **Sub-directory name**: `hippocampus_stimulation`
   - **Atlas selection**: Harvard-Oxford (subcortical)
   - Cutoffs: leave both empty for the data-driven range
5. **Generate Images**: click **Generate images** to process

### Output Structure

Results are saved to `derivatives/ti-toolbox/nilearn_visuals/{sub-directory}/`, where N is the number of pairs:

```
hippocampus_stimulation/
├── group_averaged_5_subjects.nii.gz          # Averaged NIfTI file
├── group_averaged_5_subjects_parameters.txt  # Pairs, cutoff range, atlas key
├── group_averaged_5_subjects_multiple_views.pdf    # Multi-slice view with atlas outlines
└── group_averaged_5_subjects_glass_brain.pdf       # Glass brain view
```

## Technical Details

### Data Processing Pipeline

1. **Data Loading**: Load each pair's MNI grey-matter field NIfTI (see [File Format Requirements](#file-format-requirements))
2. **Group Averaging**: Compute the voxelwise mean across all pairs. The pairs must share one voxel grid; otherwise the job stops and names the subject that differs
3. **Cutoff Resolution**: Turn the cutoffs into a display range in V/m (see [Thresholding Strategies](#thresholding-strategies))
4. **Atlas Overlay**: Add outlines of the selected atlas to the slice figure
5. **Visualization Generation**: Create the multi-slice and glass-brain PDFs using Nilearn

### Thresholding Strategies

The job works on the non-zero voxels of the averaged field. Below the minimum the field is hidden; the colour bar runs from the minimum to the maximum.

#### Default (Empty Cutoffs)
- An empty minimum is the 95th percentile and an empty maximum is the 99.9th percentile of the averaged field's non-zero voxels
- This works for any field strength. Typical TI group fields peak around 0.1–0.2 V/m, so a fixed 0.3 V/m cutoff would hide the whole field and give blank figures
- The job log prints `Field range: …` (the range and percentiles of the averaged field) and `Display range: a–b V/m`, followed by `(data-driven default)` when the minimum was left empty

#### Absolute Mode
- The percentile checkbox is off, so the values are in V/m
- Useful for comparing across different studies or protocols with the same display range
- Choose values from your own field's range. The `Field range` line of an earlier run shows it

#### Percentile Mode
- The percentile checkbox is on, so the values are percentiles 0–100 of the averaged field's non-zero voxels. They are not a percentage of the maximum
- Example: 95 to 99.9 shows the strongest 5% of field values without the top 0.1%
- Pro Tip: Never set the upper cutoff to the 100th percentile, as the peak voxel can be an outlier

#### Checks
- A minimum at or above the maximum fails the job, and the message gives the averaged field's range
- A minimum at or above the field's peak, with a maximum above it, still runs but logs a warning that the figures will be blank

### Atlas Options

The atlases ship with TI-Toolbox: they are MNI atlases in `resources/atlas/`, the same files the ROI picker offers (see [Brain Atlases]({{ site.baseurl }}/wiki/atlases/) for their sources and licences), so nothing is downloaded and the outlines draw offline. If an atlas cannot be loaded, the job log says why and the PDF is drawn without outlines.

| Panel label | Atlas | Regions | Notes |
|---|---|---|---|
| Harvard-Oxford (subcortical) (default) | `HarvardOxford-sub-maxprob-thr25-1mm` | 21 | Includes left and right cerebral cortex and white matter, the lateral ventricles and the brain stem |
| Harvard-Oxford (cortical) | `HarvardOxford-cortl-maxprob-thr25-1mm` | 96 | 48 cortical regions, each split into left and right; no subcortical structures |
| Schaefer 2018 (400 parcels) | `Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm` | 400 | 7 networks |

## Example Results

### Visualization Types

The extension generates two high-resolution PDFs:

- **Multi-slice view** (`_multiple_views.pdf`): 3 rows by 7 slices, with sagittal slices at x = −60 to 60, coronal slices at y = −80 to 70 and axial slices at z = −30 to 70. The field uses the "hot" colour map and the atlas outlines are drawn in cool colours, so they are not mistaken for field
- **Glass brain** (`_glass_brain.pdf`): four views of the field

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/nilearn-visuals/nilearn_visuals_multiple_views.png" alt="Multi-slice view of a simulated field with Harvard-Oxford subcortical atlas outlines" style="max-width: 100%; height: auto;">
  <em>Multi-slice view for an example subject with the default cutoffs and atlas. Only the field above the 95th percentile is shown, so the display range is data-driven (here 0.07–0.12 V/m), and the outlines are the Harvard-Oxford subcortical regions</em>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/nilearn-visuals/nilearn_visuals_glass_brain.png" alt="Glass-brain view of a simulated field in four projections: left, coronal, right and axial" style="max-width: 100%; height: auto;">
  <em>Glass-brain view, the page of the glass-brain PDF, for the same example simulation (L_Insula) as the multi-slice view: its grey-matter TI_max field in MNI space with the default cutoffs. Each view projects the field through the whole brain; only values above the 95th percentile (0.0718 V/m) are drawn, and the colour bar tops out at the 99.9th percentile (0.12 V/m). The grey part of the colour bar is the hidden range below the minimum cutoff. The glass brain has no atlas outlines; its lines are Nilearn's brain schematic</em>
</div>

### File Format Requirements

- **MNI-space NIfTIs are written when needed**: every simulation is read as its MNI-space field NIfTI. A simulation writes it when **Simulator ▸ Job settings ▸ Output files ▸ Also in MNI space** is ticked; otherwise the job writes it from the field mesh the first time, says so in its output and keeps it ([Fields computed on demand]({{ site.baseurl }}/wiki/simulator/#fields-computed-on-demand)). A simulation that cannot provide it is refused before the job starts, naming what is missing
- **TI runs** read `TI/niftis/grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz` from the simulation folder
- **mTI runs**, recognised by an `mTI/mesh/` folder, read `mTI/niftis/grey_{simulation_name}_mTI_MNI_MNI_mTI_max.nii.gz`
- **Mixing**: TI and mTI runs can be averaged together
- **Grid**: all pairs must be on the same voxel grid; otherwise the job names the subject that differs
- **Data Type**: Floating-point values representing field intensity in V/m
