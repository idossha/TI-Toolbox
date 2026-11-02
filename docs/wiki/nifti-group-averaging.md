---
layout: wiki
title: NIfTI Group Averaging
permalink: /wiki/nifti-group-averaging/
---

The NIfTI Group Averaging extension provides tools for computing group averages and statistical comparisons of NIfTI files organized by experimental groups.

## Import and export participant rows

Use **Import CSV/TSV**, **Export CSV**, or **Export TSV** below the Subjects header.
Export the current table for an editable template. The required header and an example CSV row are:

```csv
subject_id,simulation_name,group
101,L_Insula,Group1
```

## Workflow Example

### Basic Group Analysis

1. **Open tool**: **Extensions ▸ NIfTI group averaging** in the navigation rail
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

| Space                    | File read from `TI/niftis/`                       |
| ------------------------ | ------------------------------------------------- |
| **MNI volume** (default) | `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz` |
| **Subject volume**       | `grey_{simulation_name}_TI_subject_TI_max.nii.gz` |

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
