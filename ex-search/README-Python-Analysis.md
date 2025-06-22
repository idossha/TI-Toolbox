# Ex-Search: Python Analysis Pipeline

## Overview

The ex-search tool is a comprehensive optimization pipeline for Temporal Interference (TI) simulations featuring **professional logging**, **multiple EEG net support**, and **flexible leadfield management**. This updated version provides complete Python implementation with enhanced user control and professional-grade logging.

## Key Features

- **Complete Python Implementation** - No MATLAB dependencies
- **Multiple EEG Net Support** - Choose from available nets (default: GSN-HydroCel-185)
- **Flexible Leadfield Management** - Create and manage multiple leadfields per subject
- **Professional Logging** - Structured logging with timestamps, levels, and file output
- **SimNIBS Compatible** - Sequential processing respects SimNIBS internal parallelization
- **Default 1mA Current** - User-friendly default stimulation parameters
- **Volume-Weighted Analysis** - Enhanced field visualization with focality metrics
- **BIDS Compliant** - Follows BIDS derivatives structure

## New EEG Net Selection Features

### Available EEG Nets
The tool automatically scans for available EEG nets in each subject's `eeg_positions` directory:

```
derivatives/SimNIBS/sub-{subject}/m2m_{subject}/eeg_positions/
├── EGI10-10_Cutini_2011.csv
├── EGI10-10_UI_Jurak_2007.csv
├── EGI10-20_Okamoto_2004.csv
├── GSN-HydroCel-185.csv          # Default choice
├── GSN-HydroCel-256.csv
└── easycap_BC_TMS64_X21.csv
```

### Default Selection
- **Primary Default**: GSN-HydroCel-185.csv (if available)
- **User Choice**: Select any available EEG net for leadfield creation
- **Multiple Leadfields**: Create and maintain leadfields for different nets

### New Naming Scheme
Leadfields now use descriptive naming based on the EEG net:

**Old Format:**
```
leadfield_vol_101/101_leadfield_EGI_template.hdf5
```

**New Format:**
```
leadfield_vol_GSN-HydroCel-185/leadfield.hdf5
leadfield_vol_EGI10-10_UI_Jurak_2007/leadfield.hdf5
leadfield_vol_easycap_BC_TMS64_X21/leadfield.hdf5
```

## Logging System

### Centralized Logging
All ex-search scripts use the project's centralized logging system:

- **Log Location**: `derivatives/logs/ex_search_YYYYMMDD_HHMMSS.log`
- **Log Levels**: INFO, WARNING, ERROR, DEBUG
- **Console Output**: Clean, structured messages
- **File Output**: Detailed logs with timestamps for troubleshooting

### Log File Integration
- All scripts share the same log file for complete pipeline tracking
- Environment variable `TI_LOG_FILE` links all components
- Fallback logging if environment variable not set

### Professional Output
```
[2024-11-15 14:30:12] INFO [ex-search] - Ex-Search Optimization Pipeline
[2024-11-15 14:30:15] INFO [ex-search] - Scanning available EEG nets for subject 101
[2024-11-15 14:30:16] INFO [ex-search] - Found 6 available EEG nets
[2024-11-15 14:30:16] INFO [ex-search] - Default net: GSN-HydroCel-185.csv (option 4)
[2024-11-15 14:30:45] INFO [ex-search] - Using leadfield: GSN-HydroCel-185
[2024-11-15 14:32:10] INFO [TI-Sim] - Completed 016/025 - E001_E002_and_E003_E004 - ETA: 2.3m
```

## Usage

### Command Line Interface

#### Enhanced Workflow
```bash
# Set up environment
export PROJECT_DIR_NAME="your_project"

# Run the pipeline
cd TI-toolbox/CLI
./ex-search.sh
```

#### New Interactive Features
```
[INFO] Scanning available EEG nets for subject 101...
  1. EGI10-10_Cutini_2011.csv
  2. EGI10-10_UI_Jurak_2007.csv
  3. EGI10-20_Okamoto_2004.csv
  4. GSN-HydroCel-185.csv
  5. GSN-HydroCel-256.csv
  6. easycap_BC_TMS64_X21.csv

[INFO] Default net: GSN-HydroCel-185.csv (option 4)
Select EEG net [Press Enter for default: GSN-HydroCel-185.csv]: 

[INFO] Scanning for existing leadfields for subject 101...
  1. GSN-HydroCel-185 (leadfield.hdf5)
  2. EGI10-20_Okamoto_2004 (leadfield.hdf5)

Do you want to (C)reate new leadfield, (U)se existing, or (B)oth? [U/C/B]: U

Select leadfield for simulation (enter number): 1
[INFO] Selected leadfield: GSN-HydroCel-185
[INFO] HDF5 file: /path/to/leadfield_vol_GSN-HydroCel-185/leadfield.hdf5
```

### Graphical User Interface

#### Enhanced Leadfield Management
- **Leadfield List**: Shows all available leadfields with file sizes
- **EEG Net Selection**: Dialog with available nets and default selection
- **Create New**: Simple workflow to create leadfields for any EEG net
- **Automatic Refresh**: Updates when leadfields are created or subjects change

#### GUI Workflow
1. **Select Subject** - Choose from available subjects
2. **Manage Leadfields**:
   - View existing leadfields in the list
   - Select a leadfield for simulation
   - Create new leadfields with EEG net selection
3. **Configure ROIs** - Add target regions
4. **Set Electrodes** - Enter electrode configurations
5. **Run Optimization** - Execute with selected leadfield

## File Structure

### Input Files
```
derivatives/SimNIBS/sub-{subject}/
├── m2m_{subject}/
│   ├── eeg_positions/
│   │   ├── GSN-HydroCel-185.csv
│   │   ├── GSN-HydroCel-256.csv
│   │   └── EGI10-10_UI_Jurak_2007.csv
│   ├── ROIs/
│   │   ├── roi_list.txt
│   │   └── roi_coordinates.csv
│   └── ...
├── leadfield_vol_GSN-HydroCel-185/
│   └── leadfield.hdf5
├── leadfield_vol_GSN-HydroCel-256/
│   └── leadfield.hdf5
└── leadfield_vol_EGI10-10_UI_Jurak_2007/
    └── leadfield.hdf5
```

### Output Files
```
derivatives/SimNIBS/sub-{subject}/ex-search/xyz_{x}_{y}_{z}/
├── analysis/
│   ├── final_output.csv       # ROI analysis results
│   ├── summary.csv           # Field analysis metrics
│   ├── field_histogram.png   # Volume-weighted visualization
│   └── mesh_data.json       # Raw analysis data
└── TI_field_*.msh           # Simulation mesh files

derivatives/logs/
└── ex_search_20241115_143012.log  # Complete pipeline log
```

## Pipeline Components

### 1. EEG Net Selection
**New Features:**
- Automatic scanning of available EEG nets
- GSN-HydroCel-185 as intelligent default
- User-friendly selection interface
- Validation of EEG net file existence

### 2. Leadfield Management
**Enhanced Functionality:**
- Multiple leadfields per subject
- Descriptive naming with EEG net identification
- File size display for storage management
- Create/select workflow with validation

### 3. TI Simulation (ex-search/ti_sim.py)
**Key Improvements:**
- Environment-driven leadfield selection
- Professional logging with progress tracking
- Default 1mA stimulation current
- SimNIBS-compatible sequential processing

### 4. Mesh Field Analyzer (ex-search/mesh_field_analyzer.py)
**Features:**
- Volume-weighted histogram analysis
- Focality cutoff visualization (50%, 75%, 90%, 95% of 99.9 percentile)
- ROI field value indicators
- Units in cm³ for clinical relevance

### 5. Pipeline Integration
**Professional Execution:**
- Shared logging across all components
- Environment variable coordination
- Error handling and recovery
- Progress tracking with ETA estimation

## Error Handling

### Common Issues and Solutions

1. **No EEG Nets Found**
   ```
   [ERROR] No EEG net CSV files found in: /path/to/eeg_positions
   ```
   - **Solution**: Ensure EEG positions are properly configured in m2m directory

2. **Leadfield Selection Required**
   ```
   [ERROR] Please select a leadfield for simulation
   ```
   - **Solution**: Select an existing leadfield or create a new one

3. **SimNIBS Compatibility**
   ```
   [INFO] Note: Using sequential processing for SimNIBS compatibility
   ```
   - **Expected**: Sequential processing optimized for SimNIBS internal parallelization

4. **Large Leadfield Loading**
   ```
   [INFO] This may take several minutes for large leadfield matrices...
   [INFO] Leadfield loaded successfully in 187.3 seconds
   ```
   - **Expected**: 2-10+ GB files require 2-5 minutes loading time

## Performance Metrics

### Typical Performance by EEG Net
- **GSN-HydroCel-185**: ~2GB leadfield, 2-3 min loading
- **GSN-HydroCel-256**: ~8GB leadfield, 4-6 min loading  
- **EGI10-10**: ~500MB leadfield, 30-60 sec loading
- **Per Simulation**: 3-8 seconds (depends on mesh complexity)
- **16 Combinations**: 1-3 minutes total simulation time
- **Field Analysis**: 30-60 seconds per mesh file

### Progress Tracking
```
[INFO] Creating leadfield for EEG net: GSN-HydroCel-185.csv
[INFO] Leadfield calculation completed in 8.2 minutes
[INFO] Starting sequential TI simulations for 16 combinations
[INFO] Completed 008/016 - E050_E051_and_E052_E053 - ETA: 1.3m
[INFO] TI simulation completed - Successful: 16/16
```

## Requirements

### Python Dependencies
```txt
meshio>=5.0.0
numpy>=1.20.0
pandas>=1.3.0
matplotlib>=3.5.0
simnibs>=4.0.0
```

### System Requirements
- **Memory**: 8-16GB RAM (for large leadfield matrices)
- **Storage**: 2-20GB per subject (depending on EEG net density)
- **SimNIBS**: Version 4.0+ with Python environment

## Validation

### Output Verification
1. **Log Files**: Check for ERROR messages in log files
2. **Leadfield Files**: Verify `leadfield.hdf5` files exist and are non-zero
3. **Mesh Files**: Ensure `.msh` files contain TImax field data
4. **CSV Files**: Verify final_output.csv contains expected columns
5. **EEG Net Compatibility**: Confirm electrode names match selected net

### Quality Checks
- All electrode combinations should complete successfully
- Field values should be positive and reasonable (typically 0.1-10 V/m)
- Focality metrics should show expected spatial distributions
- ROI analysis should show field values at target coordinates
- Leadfield file sizes should be reasonable for EEG net density

## Troubleshooting

### Debug Mode
Set logging level to DEBUG for detailed information:
```bash
export LOG_LEVEL=DEBUG
./ex-search.sh
```

### Common Log Messages
- `[INFO] Using leadfield: GSN-HydroCel-185` - Normal selection
- `[INFO] Leadfield loaded successfully` - Normal operation
- `[WARNING] Could not create optimized view` - Non-critical, continues
- `[ERROR] No leadfields available for simulation` - Create leadfield first
- `[DEBUG] Using position file` - Detailed ROI processing info

## Migration Guide

### From Old to New System

#### Advantages of New System
1. **Multiple EEG Net Support** - Flexibility for different electrode setups
2. **Better Organization** - Clear naming and file structure
3. **Professional Logging** - Complete pipeline tracking and debugging
4. **Enhanced Validation** - Better error handling and user guidance
5. **Future-Proof Design** - Easily extensible for new EEG nets

#### Backward Compatibility
- **Output Format**: Identical CSV format for analysis compatibility
- **Mesh Files**: Same SimNIBS mesh format (.msh)
- **Field Names**: Uses "TImax" field name consistently
- **Units**: Analysis in cm³ for clinical relevance
- **Environment Variables**: Seamless integration with existing scripts

#### Migration Steps
1. **Existing Leadfields**: Will be detected if they use old naming
2. **New Leadfields**: Created with new naming scheme automatically
3. **Scripts**: Updated to handle both old and new formats
4. **Documentation**: Complete migration guide and examples

## Support

For issues or questions:
1. Check log files for detailed error messages in `derivatives/logs/`
2. Verify EEG net files exist in subject's `eeg_positions` directory
3. Ensure sufficient disk space for leadfield storage
4. Confirm leadfield selection before running simulations
5. Contact: ihaber@wisc.edu

---

**Last Updated**: November 2024  
**Version**: 3.0 (Multiple EEG Nets + Professional Logging)  
**Compatibility**: SimNIBS 4.0+, Python 3.8+ 