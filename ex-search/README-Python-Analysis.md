# Ex-Search: Python Analysis Pipeline

## Overview

The ex-search tool is a comprehensive optimization pipeline for Temporal Interference (TI) simulations that uses Python-based analysis instead of MATLAB. This updated version features **professional logging** across all components for improved tracking and debugging.

## Key Features

- **Complete Python Implementation** - No MATLAB dependencies
- **Professional Logging** - Structured logging with timestamps, levels, and file output
- **SimNIBS Compatible** - Sequential processing respects SimNIBS internal parallelization
- **Default 1mA Current** - User-friendly default stimulation parameters
- **Volume-Weighted Analysis** - Enhanced field visualization with focality metrics
- **BIDS Compliant** - Follows BIDS derivatives structure

## Logging System

### Centralized Logging
All ex-search scripts now use the project's centralized logging system:

- **Log Location**: `derivatives/logs/ex_search_YYYYMMDD_HHMMSS.log`
- **Log Levels**: INFO, WARNING, ERROR, DEBUG
- **Console Output**: Color-coded for different log levels
- **File Output**: Detailed logs with timestamps for troubleshooting

### Log File Integration
- All scripts share the same log file for complete pipeline tracking
- Environment variable `TI_LOG_FILE` links all components
- Fallback logging if environment variable not set

### Professional Output
```
[2024-11-15 14:30:12] INFO - Ex-Search Optimization Pipeline
[2024-11-15 14:30:12] INFO - Project directory: /mnt/project_name
[2024-11-15 14:30:15] INFO - Found 3 available subjects
[2024-11-15 14:30:45] INFO - Starting TI simulation for subject 101
[2024-11-15 14:32:10] INFO - Completed 016/025 - E001_E002_and_E003_E004 - ETA: 2.3m
```

## Pipeline Components

### 1. CLI Script (CLI/ex-search.sh)
**Enhanced with professional logging:**
- Structured progress reporting
- Error tracking with context
- Time-stamped pipeline execution
- Clear status messages

### 2. TI Simulation (ex-search/ti_sim.py)
**Key improvements:**
- Default 1mA stimulation current
- Progress tracking with ETA estimation
- Professional logging for all operations
- SimNIBS-compatible sequential processing

### 3. Mesh Field Analyzer (ex-search/mesh_field_analyzer.py)
**Features:**
- Volume-weighted histogram analysis
- Focality cutoff visualization (50%, 75%, 90%, 95% of 99.9 percentile)
- ROI field value indicators
- Units in cm³ for clinical relevance

### 4. ROI Analysis (ex-search/roi-analyzer.py)
**Professional logging for:**
- Mesh file processing progress
- Field extraction operations
- CSV generation and validation
- Error handling and recovery

### 5. CSV Integration (ex-search/update_output_csv.py)
**Logging improvements:**
- Column validation with clear error messages
- Merge operation tracking
- File path validation
- Data integrity checks

## Usage

### Command Line
```bash
# Set up environment
export PROJECT_DIR_NAME="your_project"

# Run the pipeline
cd TI-toolbox/CLI
./ex-search.sh
```

### Expected Output
```
[2024-11-15 14:30:12] INFO - Ex-Search Optimization Pipeline
[2024-11-15 14:30:12] INFO - ===============================
[2024-11-15 14:30:12] INFO - Project directory: /mnt/your_project
[2024-11-15 14:30:12] INFO - Timestamp: 20241115_143012

[2024-11-15 14:30:15] INFO - Scanning for available subjects...
Choose subjects:
  1. sub-101
  2. sub-102
  3. sub-103

[INPUT] Enter the numbers of the subjects to analyze (comma-separated): 1,2

[2024-11-15 14:30:45] INFO - Selected subjects for processing: 1 2
[2024-11-15 14:30:45] INFO - ==========================================
[2024-11-15 14:30:45] INFO - Processing subject: 101
[2024-11-15 14:30:45] INFO - Subject directory: /mnt/your_project/derivatives/SimNIBS/sub-101
```

## File Structure

### Input Files
```
derivatives/SimNIBS/sub-{subject}/
├── m2m_{subject}/
│   ├── ROIs/
│   │   ├── roi_list.txt
│   │   └── roi_coordinates.csv
│   └── ...
└── leadfield_{subject}/
    └── {subject}_leadfield_EGI_template.hdf5
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

## Error Handling

### Common Issues and Solutions

1. **Missing Log File**
   ```
   [ERROR] TI_LOG_FILE environment variable not set
   ```
   - **Solution**: Run via CLI script which sets logging automatically

2. **SimNIBS Compatibility**
   ```
   [ERROR] PETSC initialization failed in multiprocessing
   ```
   - **Solution**: Uses sequential processing (already implemented)

3. **Large Leadfield Loading**
   ```
   [INFO] This may take several minutes for large leadfield matrices...
   [INFO] Leadfield loaded successfully in 187.3 seconds
   ```
   - **Expected**: 2-10+ GB files require 2-5 minutes loading time

4. **ROI File Issues**
   ```
   [ERROR] ROI list file not found: /path/to/roi_list.txt
   ```
   - **Solution**: Ensure ROI creation step completed successfully

## Performance Metrics

### Typical Performance
- **Leadfield Loading**: 2-5 minutes (depends on file size)
- **Per Simulation**: 3-8 seconds (depends on mesh complexity)
- **16 Combinations**: 1-3 minutes total simulation time
- **Field Analysis**: 30-60 seconds per mesh file

### Progress Tracking
```
[INFO] Starting sequential TI simulations for 16 combinations
[INFO] Processing combination 1/16: E001-E002 and E003-E004
[INFO] Completed 001/016 - E001_E002_and_E003_E004 - ETA: 2.1m
[INFO] Completed 008/016 - E050_E051_and_E052_E053 - ETA: 1.3m
[INFO] Completed 016/016 - E100_E101_and_E102_E103 - ETA: 0.0s
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
- **Storage**: 1-5GB per subject (depending on mesh resolution)
- **SimNIBS**: Version 4.0+ with Python environment

## Validation

### Output Verification
1. **Log Files**: Check for ERROR messages in log files
2. **Mesh Files**: Verify `.msh` files contain TImax field data
3. **CSV Files**: Ensure final_output.csv contains expected columns
4. **Visualizations**: Check histogram plots for reasonable field distributions

### Quality Checks
- All combinations should complete successfully
- Field values should be positive and reasonable (typically 0.1-10 V/m)
- Focality metrics should show expected spatial distributions
- ROI analysis should show field values at target coordinates

## Troubleshooting

### Debug Mode
Set logging level to DEBUG for detailed information:
```bash
export LOG_LEVEL=DEBUG
./ex-search.sh
```

### Common Log Messages
- `[INFO] Leadfield loaded successfully` - Normal operation
- `[WARNING] Could not create optimized view` - Non-critical, continues
- `[ERROR] Failed to load leadfield` - Critical, check file paths
- `[DEBUG] Using position file` - Detailed ROI processing info

## Migration from MATLAB

### Advantages of Python Version
1. **No MATLAB License Required** - Reduces software dependencies
2. **Better Error Handling** - Clear error messages and logging
3. **Faster Processing** - Optimized Python implementation
4. **Enhanced Visualization** - Volume-weighted analysis with focality metrics
5. **Professional Logging** - Complete pipeline tracking and debugging

### Compatibility
- **Output Format**: Identical CSV format for backward compatibility
- **Mesh Files**: Same SimNIBS mesh format (.msh)
- **Field Names**: Uses "TImax" field name (not "TI_max")
- **Units**: Analysis in cm³ for clinical relevance

## Support

For issues or questions:
1. Check log files for detailed error messages
2. Verify all input files exist and are readable
3. Ensure sufficient disk space and memory
4. Contact: ihaber@wisc.edu

---

**Last Updated**: November 2024  
**Version**: 2.1 (Python + Professional Logging)  
**Compatibility**: SimNIBS 4.0+, Python 3.8+ 