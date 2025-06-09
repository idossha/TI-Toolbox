# TI-Toolbox Reports

The TI-Toolbox generates two types of comprehensive HTML reports:

1. Preprocessing Reports
2. Simulation Reports

## Viewing Reports

Reports are saved in the project's `derivatives/reports` directory and can be viewed in any modern web browser. The HTML format allows for:

- Easy navigation through sections
- Interactive exploration of processing steps
- Quick access to file listings
- Clear visualization of errors and warnings

## Preprocessing Reports

Preprocessing reports provide a detailed overview of the anatomical data processing pipeline for each subject.

### Report Content

1. **Header**
   - Subject ID (e.g., "sub-010")
   - Generation timestamp
   - Project directory

2. **Summary Section**
   - Subject Information
     - Subject ID
     - BIDS Subject ID
     - Project Directory
   - Input Data Overview
     - Number of T1-weighted images
     - Number of T2-weighted images
     - Total input files
   - Processing Status
     - Number of completed steps
     - Error count
     - Warning count

3. **Input Data Section**
   - T1-weighted images
     - File count
     - List of input files
   - T2-weighted images
     - File count
     - List of input files
   - DICOM files
     - File count
     - List of input files

4. **Processing Steps Section**
   - DICOM Conversion
     - Status (completed/failed/skipped)
     - Parameters used
     - Tool information
   - SimNIBS m2m Creation
     - Status
     - Parameters
     - Tool information
   - Atlas Segmentation
     - Status
     - Parameters
     - Tool information

5. **Output Data Section**
   - NIfTI Files
     - File count
     - List of output files
   - SimNIBS m2m Files
     - File count
     - List of output files
   - Atlas Segmentation Files
     - File count
     - List of output files

6. **Software Information**
   - SimNIBS version
   - dcm2niix version
   - Other tool versions

7. **Methods Section**
   - Publication-ready boilerplate text
   - Detailed methodology description

8. **Errors and Warnings**
   - Error messages with timestamps
   - Warning messages with timestamps

## Simulation Reports

Simulation reports document the transcranial stimulation simulation results.

### Report Content

1. **Header**
   - Simulation session ID
   - Generation timestamp
   - Project directory

2. **Summary Section**
   - Simulation Session Information
   - Subject Overview
   - Processing Status
   - Montage Information

3. **Simulation Parameters**
   - Conductivity settings
   - Simulation mode (unipolar/multipolar)
   - EEG net configuration
   - Current intensities

4. **Electrode Parameters**
   - Shape and dimensions
   - Thickness
   - Configuration details

5. **Subjects Section**
   - Subject IDs
   - m2m paths
   - Processing status

6. **Montages Section**
   - Montage names
   - Electrode pairs
   - Montage types

7. **Results Section**
   - Output files
   - Processing duration
   - Status information

8. **Visualizations**
   - Brain visualizations
   - NIfTI visualizations

9. **Software Information**
   - Software versions
   - Tool configurations

10. **Methods Section**
    - Publication-ready boilerplate text
    - Detailed methodology description

11. **Errors and Warnings**
    - Error messages with timestamps
    - Warning messages with timestamps

## Report Features

Both report types include:

- Interactive HTML interface
- Collapsible sections
- File listings with counts
- Status indicators
- Modern styling
- Publication-ready methodology text
- Error and warning tracking
- Software version information


