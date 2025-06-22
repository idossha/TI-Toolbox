# Ex-Search: TI Optimization Pipeline

## Overview

Ex-search is a comprehensive optimization pipeline for Temporal Interference (TI) simulations with advanced electrode optimization capabilities. The system features **unified logging**, **multiple EEG net support**, **flexible leadfield management**, and complete **Python implementation** with no MATLAB dependencies.

## 🚀 Latest Updates (January 2025)

### ✨ **Unified Logging System**
- **Single Log File**: All pipeline components now write to one shared log file
- **Centralized Output**: `ex_search_YYYYMMDD_HHMMSS.log` contains complete pipeline execution
- **Professional Formatting**: Timestamps, log levels, and structured messages
- **No More Multiple Files**: Eliminated separate `ti_sim_*.log`, `roi_analyzer_*.log`, `mesh_field_analyzer_*.log` files

### 🎯 **Enhanced EEG Net Selection**
- **Multiple Leadfield Support**: Create and use leadfields for different EEG nets
- **Intelligent Defaults**: GSN-HydroCel-185 as primary default selection
- **Flexible Electrode Support**: Both GSN format (E001, E002) and 10-20 format (Fp1, F3, C4, Cz)
- **Electrode Display**: View available electrodes for any selected leadfield with search and copy functionality

### 🔧 **GUI Enhancements**
- **Streamlined Layout**: Balanced left/right layout with optimal height distribution
- **Leadfield Management**: Visual leadfield list with file sizes and easy selection
- **ROI Analysis**: Enhanced ROI sampling with 3mm sphere analysis (TImax and TImean)
- **Error Recovery**: Improved process error handling and GUI state management

## Key Features

### 🔬 **Scientific Capabilities**
- **TI Simulation**: Temporal Interference field calculations with default 1mA current
- **ROI Analysis**: Enhanced 3mm sphere sampling around ROI coordinates
- **Field Metrics**: Volume-weighted analysis with percentiles and focality measures
- **Visualization**: Field distribution histograms with focality cutoffs

### 🛠 **Technical Features**
- **SimNIBS Compatible**: Sequential processing respects SimNIBS internal optimization
- **BIDS Compliant**: Follows BIDS derivatives structure
- **Python Implementation**: No MATLAB Runtime dependencies
- **Professional Logging**: Complete pipeline tracking and debugging

### 📊 **EEG Net Support**
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

### 📁 **New Leadfield Naming**
Leadfields use descriptive naming based on the EEG net:

**Old Format:**
```
leadfield_vol_101/101_leadfield_EGI_template.hdf5
```

**New Format:**
```
leadfield_vol_GSN-HydroCel-185/leadfield.hdf5
leadfield_vol_EGI10-20_Okamoto_2004/leadfield.hdf5
leadfield_vol_easycap_BC_TMS64_X21/leadfield.hdf5
```

## 📋 **Usage**

### GUI Workflow

1. **Subject Selection**
   - Choose from available subjects
   - Automatic leadfield scanning

2. **Leadfield Management** 
   - View existing leadfields with file sizes
   - Select leadfield for simulation
   - Create new leadfields with EEG net selection
   - Show electrodes for selected leadfield

3. **ROI Configuration**
   - Add target regions with coordinates
   - Multiple ROI support
   - Remove unwanted ROIs

4. **Electrode Setup**
   - Enter electrode configurations for E1+, E1-, E2+, E2-
   - Support for GSN format (E001, E002) and 10-20 format (Fp1, F3, C4, Cz)
   - Copy electrodes from "Show Electrodes" dialog

5. **Run Optimization**
   - Execute with selected leadfield and configurations
   - Real-time progress tracking
   - Unified log file generation

### Command Line Interface

```bash
# Set up environment
export PROJECT_DIR_NAME="your_project"

# Run the pipeline
cd TI-toolbox/CLI
./ex-search.sh
```

#### Interactive Features
```
[INFO] Scanning available EEG nets for subject 101...
  1. EGI10-10_Cutini_2011.csv
  2. EGI10-10_UI_Jurak_2007.csv
  3. EGI10-20_Okamoto_2004.csv
  4. GSN-HydroCel-185.csv
  5. GSN-HydroCel-256.csv
  6. easycap_BC_TMS64_X21.csv

[INFO] Default net: GSN-HydroCel-185.csv (option 4)
Select EEG net [Press Enter for default]: 

[INFO] Managing leadfields for subject 101...
Do you want to (C)reate new leadfield, (U)se existing, or (B)oth? [U/C/B]: U

Select leadfield for simulation: 1
[INFO] Using leadfield: GSN-HydroCel-185
```

## 🗂 **File Structure**

### Input Files
```
derivatives/SimNIBS/sub-{subject}/
├── m2m_{subject}/
│   ├── eeg_positions/           # EEG net configurations
│   │   ├── GSN-HydroCel-185.csv
│   │   ├── GSN-HydroCel-256.csv
│   │   └── EGI10-20_Okamoto_2004.csv
│   ├── ROIs/                    # Target regions
│   │   ├── roi_list.txt
│   │   ├── L_Insula.csv
│   │   └── Test3.csv
│   └── ...
├── leadfield_vol_GSN-HydroCel-185/   # Leadfield matrices
│   └── leadfield.hdf5
├── leadfield_vol_GSN-HydroCel-256/
│   └── leadfield.hdf5
└── leadfield_vol_EGI10-20_Okamoto_2004/
    └── leadfield.hdf5
```

### Output Files
```
derivatives/SimNIBS/sub-{subject}/ex-search/
├── Test3_GSN-HydroCel-185/      # ROI-specific results
│   ├── analysis/
│   │   ├── final_output.csv     # Complete results (ROI + field metrics)
│   │   ├── summary.csv          # Field analysis metrics
│   │   ├── *_histogram.png     # Volume-weighted visualizations
│   │   └── mesh_data.json      # Raw analysis data
│   └── TI_field_*.msh          # Simulation mesh files
├── L_Insula_GSN-HydroCel-185/
│   └── ... (same structure)
└── ...

derivatives/logs/sub-{subject}/
└── ex_search_20250122_143012.log    # Unified pipeline log
```

## 🔧 **Pipeline Components**

### 1. **Leadfield Management** (`leadfield.py`)
- Creates leadfield matrices for selected EEG nets
- Handles m2m directory and EEG cap file paths  
- Generates standardized `leadfield.hdf5` files
- Professional logging with progress tracking

### 2. **TI Simulation** (`ti_sim.py`)
- Environment-driven leadfield selection
- Default 1mA stimulation current with user override
- Sequential processing optimized for SimNIBS
- Real-time progress tracking with ETA estimation
- Electrode validation for both GSN and 10-20 formats

### 3. **ROI Analysis** (`roi-analyzer.py`)
- Enhanced 3mm sphere sampling around ROI coordinates
- Calculates both TImax (peak) and TImean (average) values in ROI
- 20-point sampling for statistical analysis
- Professional logging with detailed progress

### 4. **Mesh Field Analysis** (`mesh_field_analyzer.py`)
- Volume-weighted field analysis
- Percentile calculations (95%, 99%, 99.9%)
- Focality metrics (50%, 75%, 90%, 95% of 99.9 percentile)
- Field distribution histograms with ROI indicators
- Complete CSV output generation

### 5. **Unified Logging**
- Shared log file across all pipeline components
- Environment variable `TI_LOG_FILE` coordinates logging
- Professional formatting with timestamps and levels
- CLI fallback for standalone script usage

## 📊 **Logging System**

### Unified Output
All components write to a single log file: `ex_search_YYYYMMDD_HHMMSS.log`

```
[2025-01-22 14:30:12] [Ex-Search] [INFO] ================================================================================
[2025-01-22 14:30:12] [Ex-Search] [INFO] EX-SEARCH PIPELINE CONFIGURATION
[2025-01-22 14:30:12] [Ex-Search] [INFO] ================================================================================
[2025-01-22 14:30:12] [Ex-Search] [INFO] Subject ID: 101
[2025-01-22 14:30:12] [Ex-Search] [INFO] Selected EEG Net: GSN-HydroCel-185
[2025-01-22 14:30:12] [Ex-Search] [INFO] Leadfield HDF5 Path: /mnt/project/derivatives/SimNIBS/sub-101/leadfield_vol_GSN-HydroCel-185/leadfield.hdf5
[2025-01-22 14:30:12] [Ex-Search] [INFO] Number of ROIs to process: 2
[2025-01-22 14:30:15] [Ex-Search] [INFO] TI Simulation completed: 1/1 successful
[2025-01-22 14:30:25] [Ex-Search] [INFO] Enhanced ROI analysis completed with 1 simulations
[2025-01-22 14:30:35] [Ex-Search] [INFO] Final output CSV saved with 12 columns
```

### Log Levels
- **INFO**: Normal operation and progress updates
- **WARNING**: Non-critical issues that don't stop execution
- **ERROR**: Critical errors that may cause failure
- **DEBUG**: Detailed information for troubleshooting (CLI only)

## ⚡ **Performance**

### Typical Performance by EEG Net
- **GSN-HydroCel-185**: ~2GB leadfield, 2-3 min loading, 3-5 sec per simulation
- **GSN-HydroCel-256**: ~8GB leadfield, 4-6 min loading, 5-8 sec per simulation
- **EGI10-20**: ~500MB leadfield, 30-60 sec loading, 2-3 sec per simulation

### Processing Times
- **Leadfield Creation**: 5-15 minutes (depending on EEG net density)
- **TI Simulation**: 3-8 seconds per electrode combination
- **ROI Analysis**: 15-30 seconds per mesh file
- **Field Analysis**: 30-60 seconds per mesh file

## 🛠 **Requirements**

### Python Dependencies
```bash
pip install meshio numpy pandas matplotlib simnibs
```

### System Requirements
- **Memory**: 8-16GB RAM (for large leadfield matrices)
- **Storage**: 2-20GB per subject (depending on EEG net density)
- **SimNIBS**: Version 4.0+ with Python environment

## 🔍 **Troubleshooting**

### Common Issues

1. **No EEG Nets Found**
   ```
   [ERROR] No EEG net CSV files found in eeg_positions directory
   ```
   **Solution**: Ensure EEG position files exist in m2m directory

2. **Leadfield Selection Required**
   ```
   [ERROR] Please select a leadfield for simulation
   ```
   **Solution**: Select an existing leadfield or create a new one

3. **Electrode Format Issues**
   ```
   [ERROR] Please enter valid electrode names
   ```
   **Solution**: Use GSN format (E001, E002) or 10-20 format (Fp1, F3, C4, Cz)

4. **Large Leadfield Loading**
   ```
   [INFO] This may take several minutes for large leadfield matrices...
   [INFO] Leadfield loaded successfully in 187.3 seconds
   ```
   **Expected**: 2-10+ GB files require 2-5 minutes loading time

### Debug Mode
For detailed troubleshooting, check the unified log file:
```
derivatives/logs/sub-{subject}/ex_search_YYYYMMDD_HHMMSS.log
```

## 🧪 **Validation**

### Output Verification
1. **Unified Log**: Single log file with all pipeline steps
2. **Leadfield Files**: Non-zero `leadfield.hdf5` files
3. **Simulation Meshes**: `.msh` files with TImax field data
4. **Complete CSV**: `final_output.csv` with all metrics (ROI + field analysis)
5. **ROI Metrics**: Both TImax_ROI and TImean_ROI values

### Quality Checks
- All electrode combinations complete successfully
- Field values are positive and reasonable (0.1-10 V/m)
- ROI analysis shows meaningful TImax vs TImean differences
- Focality metrics show expected spatial distributions
- Volume-weighted histograms display properly

## 📈 **Migration Benefits**

### From Previous Versions
1. **Unified Logging** - Complete pipeline tracking in single file
2. **Multiple EEG Nets** - Flexibility for different electrode configurations
3. **Enhanced ROI Analysis** - 3mm sphere sampling with max/mean metrics
4. **Professional Output** - Publication-ready results and visualizations
5. **Better Organization** - Clear naming and standardized file structure

### Backward Compatibility
- **Output Format**: Compatible CSV format for existing analysis scripts
- **Mesh Files**: Standard SimNIBS mesh format (.msh)
- **Field Names**: Consistent "TImax" field naming
- **Directory Structure**: BIDS-compliant organization

## 📞 **Support**

For issues or questions:
1. Check the unified log file for detailed error messages
2. Verify EEG net files exist in subject's `eeg_positions` directory  
3. Ensure sufficient disk space for leadfield storage
4. Confirm leadfield selection before running simulations
5. Contact: ihaber@wisc.edu

---

**Last Updated**: January 2025  
**Version**: 4.0 (Unified Logging + Enhanced EEG Net Support)  
**Compatibility**: SimNIBS 4.0+, Python 3.8+ 