---
layout: wiki
title: TI-Toolbox Reports
permalink: /wiki/reports/
---

The TI-Toolbox generates comprehensive HTML reports that provide detailed documentation of preprocessing and simulation workflows. These professional reports ensure reproducibility, facilitate quality control, and provide publication-ready methodology descriptions.

## Overview

The toolbox produces two types of reports:
- **Preprocessing Reports**: Document anatomical data processing pipeline for each subject
- **Simulation Reports**: Detail transcranial stimulation simulation parameters and results
- **Interactive Format**: HTML reports with collapsible sections and modern styling
- **Publication Ready**: Include boilerplate methodology text for scientific papers

## Report Features

### Professional Documentation
- **Interactive HTML Interface**: Modern, responsive design with collapsible sections
- **Comprehensive Tracking**: Complete workflow documentation from input to output
- **Error Management**: Detailed error and warning logs with timestamps
- **Software Versioning**: Complete tool version tracking for reproducibility

### Quality Control
- **Status Indicators**: Visual confirmation of processing step completion
- **File Validation**: Automatic counting and listing of input/output files
- **Parameter Documentation**: Complete record of processing parameters
- **Visual Confirmation**: Brain visualizations and NIfTI previews

## Example: Simulation Report

Below is an embedded example of a complete simulation report generated by the TI-Toolbox:

<iframe src="{{ site.baseurl }}/wiki/assets/reports/simulation_report_20250610_063527.html" 
        width="100%" 
        height="800px" 
        style="border: 1px solid #ddd; border-radius: 8px;">
</iframe>

*Interactive simulation report showing complete workflow documentation, parameters, and results*

## Preprocessing Reports

### Report Structure

| Section | Content | Purpose |
|---------|---------|---------|
| **Header** | Subject ID, timestamp, project directory | Quick identification |
| **Summary** | Processing status, file counts, error/warning counts | Overview dashboard |
| **Input Data** | T1/T2 images, DICOM files with counts | Data validation |
| **Processing Steps** | DICOM conversion, m2m creation, atlas segmentation | Workflow tracking |
| **Output Data** | NIfTI files, m2m files, atlas files | Result verification |
| **Software Info** | SimNIBS, dcm2niix, tool versions | Reproducibility |
| **Methods** | Publication-ready methodology text | Scientific documentation |
| **Errors/Warnings** | Timestamped messages | Quality control |

### Key Information Tracked

**Subject Information:**
- Subject ID and BIDS compliance
- Project directory structure
- Input data inventory (T1, T2, DICOM files)

**Processing Pipeline:**
- DICOM to NIfTI conversion status
- SimNIBS m2m head model creation
- Atlas segmentation and registration
- Parameter documentation for each step

**Quality Assurance:**
- File count verification
- Processing step completion status
- Error and warning documentation
- Software version tracking

## Simulation Reports

### Report Structure

| Section | Content | Purpose |
|---------|---------|---------|
| **Header** | Session ID, timestamp, project info | Session identification |
| **Summary** | Subject overview, montage info, processing status | Executive summary |
| **Parameters** | Conductivity, simulation mode, EEG configuration | Simulation setup |
| **Electrodes** | Shape, dimensions, thickness, configuration | Hardware specification |
| **Subjects** | Subject IDs, m2m paths, processing status | Multi-subject tracking |
| **Montages** | Electrode pairs, montage types, configurations | Stimulation protocols |
| **Results** | Output files, duration, processing status | Outcome documentation |
| **Visualizations** | Brain renders, NIfTI previews | Visual verification |
| **Methods** | Publication methodology text | Scientific documentation |

### Key Information Tracked

**Simulation Configuration:**
- Conductivity settings and tissue properties
- Simulation mode (unipolar/multipolar)
- EEG net configuration and electrode positions
- Current intensities and stimulation parameters

**Hardware Specifications:**
- Electrode shape, dimensions, and thickness
- Montage configurations and electrode pairs
- Stimulation protocols and current flow patterns

**Results Documentation:**
- Processing duration and computational metrics
- Output file generation and validation
- Visual confirmation through brain renderings
- Error tracking and quality assurance

## Report Locations

### File Organization
```
derivatives/reports/
├── preprocessing/
│   ├── sub-001_preprocessing_report.html
│   ├── sub-002_preprocessing_report.html
│   └── ...
└── simulation/
    ├── simulation_report_20250610_063527.html
    ├── simulation_report_20250611_142033.html
    └── ...
```

### Naming Convention
- **Preprocessing**: `sub-{ID}_preprocessing_report.html`
- **Simulation**: `simulation_report_{YYYYMMDD}_{HHMMSS}.html`

## Viewing and Sharing

### Browser Compatibility
- **Modern Browsers**: Chrome, Firefox, Safari, Edge
- **Responsive Design**: Adapts to different screen sizes
- **No Dependencies**: Self-contained HTML files

### Sharing Reports
- **Self-Contained**: All styling and scripts embedded
- **Portable**: Can be shared via email or cloud storage
- **Archive Safe**: HTML format ensures long-term accessibility

## Publication Integration

### Methodology Text
Both report types include publication-ready methodology sections that can be directly incorporated into scientific papers:

- **Complete Parameter Documentation**: All processing parameters documented
- **Software Version Tracking**: Ensures reproducible methodology descriptions  
- **Standard Terminology**: Uses established neuroimaging terminology
- **Citation Ready**: Includes appropriate tool and method citations

### Quality Assurance
- **Peer Review Ready**: Comprehensive documentation supports manuscript review
- **Reproducibility**: Complete parameter and version tracking
- **Transparency**: Open documentation of all processing steps

---

*Last Updated: January 2025*  
*Compatible with: TI-Toolbox v4.0+, Modern Web Browsers*


