---
layout: wiki
title: TI-Toolbox Reports
permalink: /wiki/reports/
---

The TI-Toolbox generates HTML reports that provide detailed documentation of preprocessing and simulation workflows. These professional reports ensure reproducibility, facilitate quality control, and provide publication-ready methodology descriptions.

## Overview

The toolbox produces three types of reports:

- **Preprocessing Reports**: Document anatomical data processing pipeline for each subject
- **Simulation Reports**: Detail transcranial stimulation simulation parameters and results
- **Flex-Search Reports**: Summarise an electrode-position optimization run (goal, ROI, best montage, convergence)

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

Below is a complete simulation report generated with TI-Toolbox v2.4.0 for `sub-ernie` of the bundled example dataset (montage `E034–E020` / `E095–E070`, GSN-HydroCel-185, 1 mA per channel, MNI export enabled):

<iframe src="{{ site.baseurl }}/assets/other/simulation_report_20260826_223702.html" 
        width="100%" 
        height="800px" 
        style="border: 1px solid #ddd; border-radius: 8px;">
</iframe>

_Sections: Simulation Overview, Electrode Montages (with the montage visualizer image), Field Visualizations (Nilearn), Errors and Warnings, Methods, References, Machine-Readable Provenance_

## Report Locations

### File Organization

```
derivatives/ti-toolbox/reports/
├── dataset_description.json
├── sub-ernie/
│   ├── pre_processing_report_20260505_193859.html
│   ├── simulation_report_20260826_223702.html
│   └── flex_search_report_20260730_041200.html
└── sub-101/
    └── ...
```

Simulation report metadata is backed by the corresponding SimNIBS provenance snapshot:

```
derivatives/SimNIBS/sub-{ID}/Simulations/{montage}/documentation/config.json
```

### Naming Convention

- **Preprocessing**: `pre_processing_report_{YYYYMMDD}_{HHMMSS}.html`
- **Simulation**: `simulation_report_{YYYYMMDD}_{HHMMSS}.html`
- **Flex-Search**: `flex_search_report_{YYYYMMDD}_{HHMMSS}.html`
- Simulation reports are self-contained HTML files. Methods text, references, and machine-readable provenance are embedded in the HTML; no per-report methods/citation/provenance sidecars are written.

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

Both report types include publication-ready methodology sections that can be directly incorporated into scientific papers. Simulation reports keep this information inside the HTML report:

- **Concise Methods Text**: Simulation pair labels/currents, electrode model, conductivity mode, SimNIBS/CHARM modeling, and generated outputs are summarized as readable paragraphs
- **Software Version Tracking**: Ensures reproducible methodology descriptions
- **Standard Terminology**: Uses established neuroimaging and SimNIBS/CHARM terminology
- **Citation Ready**: DOI/URL-linked references are included in the HTML References section
- **Flex-Search Methods**: Optimization reports summarize the TI-Toolbox workflow (Haber 2026) and leadfield-free optimization principles (Weise 2024)
- **Machine-Readable Provenance**: The final HTML section embeds JSON with report parameters, warnings, output files, and software versions

### Regenerating Simulation Reports

A simulation report can be regenerated from an existing simulation directory as long as the montage's `documentation/config.json` is present. During generation, TI-Toolbox prefers saved simulation provenance over stale GUI/runtime state. If the runtime state disagrees (for example, it only contains a placeholder `E1-E2` pair while the saved provenance contains `AF3-AF4` and `C5-C6`), the report displays a warning and renders the provenance-backed pairs.

Name the subject and the montage and let the saved provenance supply the rest:

```python
from tit.reporting import SimulationReportGenerator

gen = SimulationReportGenerator(
    project_dir="/mnt/my_project",
    subject_id="001",
    simulation_session_id="regen_BU_eg2",
)
gen.add_montage("BU_eg2", [], montage_type="TI")
print(gen.generate())  # -> derivatives/ti-toolbox/reports/sub-001/simulation_report_<timestamp>.html
```

Passing empty electrode pairs leaves nothing to disagree with, so the report is rendered straight from `documentation/config.json` with no warning. Run it with `simnibs_python` inside the container.

---

_Last Updated: August 2026_
_Compatible with: TI-Toolbox v2.4.0, Modern Web Browsers_
