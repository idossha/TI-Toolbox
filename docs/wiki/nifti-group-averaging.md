---
layout: wiki
title: NIfTI Group Averaging
permalink: /wiki/nifti-group-averaging/
---

The NIfTI Group Averaging extension provides comprehensive tools for computing group averages and statistical comparisons of NIfTI files organized by experimental groups. This extension is particularly useful for temporal interference (TI) stimulation studies where researchers need to compare field distributions across multiple subjects and experimental conditions.

## Workflow Example

### Basic Group Analysis

1. **Launch Extension**: Settings → Extensions → "NIfTI Group Averaging"
2. **Configure Subjects**:
   - Subject 001: Simulation "stim_A", Group "Treatment"
   - Subject 002: Simulation "stim_A", Group "Treatment"
   - Subject 003: Simulation "stim_B", Group "Control"
   - Subject 004: Simulation "stim_B", Group "Control"
3. **Set Parameters**:
   - Analysis name: `treatment_vs_control`
   - NIfTI pattern: default
   - Difference pairs: automatic (all pairs)
4. **Run Analysis**: Generate group averages and differences

### Output Structure

Results are saved to `derivatives/ti-toolbox/nifti_average/{analysis_name}/`:

```
treatment_vs_control/
├── average_Treatment.nii.gz              # Group average for Treatment
├── average_Control.nii.gz                # Group average for Control
├── difference_Treatment_minus_Control.nii.gz    # Treatment - Control
├── config.json                           # Complete analysis configuration
└── analysis_log.txt                      # Processing details
```

## Results Visualization

The group difference analysis provides visual output showing statistical comparisons between experimental groups:

<img src="{{ site.baseurl }}/assets/imgs/freeview/group_diff_nifti.png" alt="Group Difference Visualization" style="width: 80%; max-width: 600px;">

*Figure: group differences in electric field distributions*

## CSV Configuration Management

### Import Format

**Required Columns:**
- `subject_id`: Subject identifier (without 'sub-' prefix)
- `simulation_name`: Simulation directory name
- `group`: Group assignment label

**Example CSV:**
```csv
subject_id,simulation_name,group
001,HIPP_L_stim,Treatment
002,HIPP_L_stim,Treatment
003,HIPP_R_stim,Control
004,HIPP_R_stim,Control
005,HIPP_L_stim,Treatment
```

### Export Functionality

- **Complete Configuration**: All subject-group assignments
- **Analysis Ready**: Formatted for re-import or sharing
- **Documentation**: Serves as analysis record
