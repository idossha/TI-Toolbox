---
layout: wiki
title: NIfTI Group Averaging
permalink: /wiki/nifti-group-averaging/
---

The NIfTI Group Averaging extension provides comprehensive tools for computing group averages and statistical comparisons of NIfTI files organized by experimental groups. This extension is particularly useful for temporal interference (TI) stimulation studies where researchers need to compare field distributions across multiple subjects and experimental conditions.

## Overview

NIfTI Group Averaging addresses the common need in neuroimaging research to aggregate data across subjects while maintaining group distinctions. The extension provides an intuitive interface for organizing subjects into experimental groups, computing group averages, and calculating differences between groups, all while following BIDS-compliant data organization.

## Key Features

- **Flexible Group Assignment**: Assign subjects to custom experimental groups
- **Automatic Averaging**: Compute group means across multiple subjects
- **Pairwise Comparisons**: Calculate differences between any group pairs
- **CSV Import/Export**: Batch configuration management for large studies
- **Memory Efficient**: Streaming processing for large datasets
- **BIDS Integration**: Automatic data discovery and organized output

## User Interface

### Subject Configuration

The extension provides a comprehensive interface for managing subject-group assignments:

#### Subject List Management
- **Add Subjects**: Manually configure individual subject-simulation pairs
- **Quick Add**: Batch operations for large datasets
- **Remove Subjects**: Clean interface for managing configurations
- **Scrollable Display**: Handle studies with many subjects

#### Group Assignment
- **Custom Group Names**: User-defined group labels (Treatment, Control, etc.)
- **Dynamic Dropdowns**: Group lists update automatically
- **Validation**: Ensures balanced group assignments

### Analysis Configuration

#### File Pattern Specification
- **NIfTI Pattern**: Customizable file naming patterns
- **Default Template**: `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
- **Variable Substitution**: Automatic subject and simulation name insertion

#### Difference Calculations
- **Automatic Pairwise**: All possible group differences computed by default
- **Custom Pairs**: User-specified comparisons (e.g., "Treatment-Control")
- **Flexible Syntax**: Support for complex comparison specifications

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

## Technical Details

### Data Processing Pipeline

1. **Subject Discovery**: Load subject list from TI-Toolbox project structure
2. **File Pattern Matching**: Locate NIfTI files using configurable patterns
3. **Group Organization**: Sort subjects into user-defined groups
4. **Memory-Efficient Loading**: Stream data to handle large datasets
5. **Group Averaging**: Compute means across subjects within each group
6. **Difference Calculation**: Perform pairwise group subtractions
7. **Output Generation**: Save results in organized directory structure

### Memory Management

The extension uses efficient memory management strategies:

- **Streaming I/O**: Load one file at a time to minimize memory usage
- **Data Type Optimization**: Use float32 for computational efficiency
- **Garbage Collection**: Explicit cleanup after processing each group
- **Scalable Processing**: Handle studies with 100+ subjects

### Group Difference Computation

**Pairwise Comparisons:**
- **Automatic Mode**: All possible group pairs (A-B, A-C, B-C for 3 groups)
- **Custom Mode**: User-specified pairs only
- **Naming Convention**: `{Group1}_minus_{Group2}.nii.gz`

**Example for 3 groups (A, B, C):**
```
Automatic mode generates:
- difference_A_minus_B.nii.gz
- difference_A_minus_C.nii.gz
- difference_B_minus_C.nii.gz

Custom mode "A-B, A-C" generates:
- difference_A_minus_B.nii.gz
- difference_A_minus_C.nii.gz
```

## Advanced Usage

### Large-Scale Studies

**Managing Many Subjects:**

1. **CSV Preparation**: Create subject configuration file
   ```csv
   subject_id,simulation_name,group
   001,stim_A,Treatment
   002,stim_A,Treatment
   003,stim_B,Control
   004,stim_B,Control
   ```

2. **Batch Import**: Load entire study configuration at once
3. **Validation**: Review group assignments before processing
4. **Parallel Processing**: Extension handles large datasets efficiently

### Custom Analysis Scenarios

#### Longitudinal Studies
```
Timepoint1_GroupA, Timepoint1_GroupB, Timepoint2_GroupA, Timepoint2_GroupB
- Compare same subjects across timepoints
- Assess group differences at each timepoint
- Track changes within and between groups
```

#### Multi-Site Studies
```
Site1_Treatment, Site1_Control, Site2_Treatment, Site2_Control
- Control for site-specific effects
- Compare treatment effects across sites
- Assess overall treatment efficacy
```

#### Dose-Response Analysis
```
Low_Dose, Medium_Dose, High_Dose, Placebo
- Examine dose-dependent field changes
- Compare each dose level to placebo
- Identify optimal stimulation parameters
```

## Integration with Other Tools

### Analysis Pipeline Integration

**Complete TI Stimulation Workflow:**

1. **Individual Simulations**: Generate TI fields for each subject
2. **Group Averaging**: Combine subjects into experimental groups
3. **Statistical Testing**: Use CBP extension for significance testing
4. **Visualization**: Create publication figures with Nilearn Visuals
5. **Reporting**: Document findings with Quick Notes

### Data Flow Example

```
Raw Simulations (N=24 subjects)
    ↓
Group Averaging (Treatment:12, Control:12)
    ↓
Statistical Testing (CBP: p<0.05 cluster correction)
    ↓
Visualization (Nilearn: publication figures)
    ↓
Manuscript (integrated results and methods)
```

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

## Performance and Scalability

### Computational Requirements

**Typical Performance:**
- **Small Study** (10 subjects, 2 groups): ~30 seconds
- **Medium Study** (50 subjects, 3 groups): ~5 minutes
- **Large Study** (100+ subjects): ~15-30 minutes

**System Requirements:**
- **RAM**: 4-16 GB depending on dataset size
- **Storage**: ~500 MB per average NIfTI file
- **CPU**: Multi-core recommended for large datasets

### Optimization Strategies

**Memory Efficiency:**
- Process one subject at a time during loading
- Use float32 precision for calculations
- Explicit garbage collection between operations
- Streaming file I/O to minimize memory footprint

**Processing Speed:**
- Automatic CPU core detection and utilization
- Parallel file operations where possible
- Efficient NIfTI I/O with nibabel
- Minimal data copying during computations

## Troubleshooting

### Common Issues

**"No subjects configured"**
- Ensure at least one subject-simulation pair is added
- Check that subject IDs exist in the project
- Verify simulation directories are present

**"File not found" errors**
- Confirm NIfTI file pattern matches actual filenames
- Check that simulations completed successfully
- Verify BIDS directory structure

**Memory errors**
- Reduce number of subjects processed simultaneously
- Check available RAM (minimum 4GB recommended)
- Process in smaller batches if needed

**Empty output files**
- Verify input NIfTI files contain valid data
- Check coordinate systems are consistent
- Ensure all subjects have matching file patterns

### Data Validation

**Pre-Analysis Checks:**

1. **File Existence**: Confirm all expected NIfTI files exist
2. **Data Integrity**: Verify files contain valid numerical data
3. **Coordinate Systems**: Ensure all files use consistent MNI space
4. **Group Balance**: Check for reasonable group sizes (avoid N=1 groups)

**Post-Analysis Validation:**

1. **Output Verification**: Check that output files were created
2. **Data Range**: Verify output values are in expected range
3. **File Size**: Ensure output files are appropriately sized
4. **Visual Inspection**: Load results in visualization software

## Output Data Interpretation

### Average Files

**Group Average NIfTI:**
- **Content**: Mean field intensity across all subjects in group
- **Units**: V/m (same as input simulation files)
- **Use**: Representative field distribution for the group
- **Analysis**: Input for statistical testing or visualization

### Difference Files

**Group Difference NIfTI:**
- **Content**: Group1 - Group2 voxelwise differences
- **Interpretation**: Positive values = Group1 > Group2
- **Statistical Context**: Effect size map (not significance)
- **Visualization**: Heat maps showing group differences

### Configuration Files

**Analysis Metadata:**
- **config.json**: Complete analysis parameters and subject list
- **Reproducibility**: Enables exact replication of analysis
- **Documentation**: Records all analysis settings

## Best Practices

### Study Design Considerations

**Group Size Guidelines:**
- **Minimum**: 3-5 subjects per group for reliable averages
- **Recommended**: 8+ subjects per group for stable results
- **Optimal**: 12+ subjects per group for robust statistics

**Group Assignment:**
- **Balance**: Equal group sizes when possible
- **Randomization**: Random assignment to minimize confounding
- **Blinding**: Blind group assignment during data collection

### Quality Control

**Data Screening:**
- **Outlier Detection**: Check for subjects with extreme values
- **Data Completeness**: Ensure all subjects have complete data
- **Preprocessing**: Verify consistent preprocessing across subjects
- **Artifact Checking**: Review for motion or other artifacts

**Analysis Validation:**
- **Result Inspection**: Visually check output files
- **Sensitivity Analysis**: Test with different parameters
- **Cross-validation**: Compare with manual calculations
- **Documentation**: Record all analysis decisions

## Future Developments

**Planned Enhancements:**

- **Statistical Integration**: Built-in t-tests and effect size calculations
- **Interactive Visualization**: Real-time result preview during processing
- **Advanced Group Operations**: Within-subject designs and mixed models
- **Quality Metrics**: Automated outlier detection and data quality reports
- **Workflow Templates**: Pre-configured setups for common study designs
- **Cloud Integration**: Support for distributed processing of large datasets
