---
layout: wiki
title: NIfTI Group Averaging
permalink: /wiki/nifti-group-averaging/
---

The NIfTI Group Averaging extension provides comprehensive tools for computing group averages and statistical comparisons of NIfTI files organized by experimental groups. This extension is particularly useful for temporal interference (TI) stimulation studies where researchers need to compare field distributions across multiple subjects and experimental conditions.

## Before you start

- **Turn the panel on.** Enable **NIfTI group averaging** in **Settings ▸ Extensions** and reload
  the app; a panel toggle takes effect only after a reload. It then appears under **Extensions**
  in the navigation rail.
- **Simulate with MNI outputs.** The default **Space**, **MNI volume**, reads each simulation's
  MNI-space field NIfTI, which a simulation writes only when
  **Simulator ▸ Job settings ▸ Standard-space outputs ▸ Generate MNI NIfTI outputs** is ticked.
  That option is **off by default**. When a file is missing the job is refused before it starts,
  naming the simulation to re-run with the option ticked.
- **mTI simulations work too.** They are read from the simulation's `mTI/niftis/` folder with mTI
  file names (`grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz`); a **NIfTI pattern** typed in the 2-pair
  spelling (`_TI_`) is read as `_mTI_`.

## Import and export participant rows

Use **Import CSV/TSV**, **Export CSV**, or **Export TSV** below the Subjects header.
Export the current table for an editable template. The required header and an example CSV row are:

```csv
subject_id,simulation_name,group
101,L_Insula,Group1
```

For TSV, use tabs instead of commas. Columns may be reordered, but all headers must be present
with exactly these names. Subject IDs omit `sub-`; simulation names match the project catalog.
`group` is a required group name. Quoted fields, embedded separators, UTF-8 BOM and Windows line endings are supported.
An import replaces the table only after every row validates. A malformed file leaves existing
rows unchanged. Import checks table structure and values; dataset files are checked by the job workflow.


## Workflow Example

### Basic Group Analysis

1. **Open tool**: **Extensions ▸ NIfTI group averaging** in the navigation rail (see [Before you start](#before-you-start))
2. **Configure Subjects**:
   - Subject 001: Simulation "stim_A", Group "Treatment"
   - Subject 002: Simulation "stim_A", Group "Treatment"
   - Subject 003: Simulation "stim_B", Group "Control"
   - Subject 004: Simulation "stim_B", Group "Control"
3. **Set Parameters** under **Analysis configuration**:
   - **Analysis name**: `treatment_vs_control`
   - **Space**: MNI volume
   - **NIfTI pattern**: empty (the chosen space's file)
   - **Group differences**: empty (all pairs)
4. **Run Analysis**: Generate group averages and differences

### Space and the file it reads

**Analysis configuration ▸ Space** decides which file of each simulation is averaged. Leave
**NIfTI pattern** empty to read the space's own file (it is shown as the field's placeholder):

| Space | File read from `TI/niftis/` |
|---|---|
| **MNI volume** (default) | `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz` |
| **Subject volume** | `grey_{simulation_name}_TI_subject_TI_max.nii.gz` |

A pattern you type wins; changing **Space** clears it. Each subject's own volumes are on that
subject's voxel grid, so **Subject volume** works only when every row is the same subject — for
example, comparing two montages simulated in one subject. To average across subjects, use
**MNI volume**.

### Output Structure

Results are saved to `derivatives/ti-toolbox/nifti_average/{analysis_name}/`:

```
treatment_vs_control/
├── average_Treatment.nii.gz                     # Group average for Treatment
├── average_Control.nii.gz                       # Group average for Control
├── difference_Treatment_minus_Control.nii.gz    # Treatment - Control
└── config.json                                  # Analysis name, pattern, space, each group's subjects, differences
```

## Results Visualization

Each average and difference is a NIfTI on the grid of the files it averaged. Open one in TetraVox
from the job's **Artifacts** tab (**Open in Tetravox**); see [Viewer]({{ site.baseurl }}/wiki/visualizers/).
