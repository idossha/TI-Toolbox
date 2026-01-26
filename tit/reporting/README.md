# TI-Toolbox Reportlet-Based Reporting System

## Overview

A modular, NiPreps-inspired reporting system for TI-Toolbox that generates self-contained HTML reports across preprocessing, simulation, and flex-search modules.

**Key Principles:**
- Reportlet abstraction (reusable visual/content components)
- Self-contained HTML with embedded base64 images
- BIDS-compliant output structure
- Modern, clean design

---

## Architecture

```
Reportlet (base)              Report Assembler           HTML Output
     │                              │                        │
     ├── MetadataReportlet    ─────►│◄───── Sections ──────► │ <header>
     ├── ImageReportlet       ─────►│                        │ <nav> TOC
     ├── TableReportlet       ─────►│                        │ <main>
     ├── TextReportlet        ─────►│                        │   └── sections
     ├── ErrorReportlet       ─────►│                        │ <footer>
     └── ReferencesReportlet  ─────►│                        │
```

---

## File Structure

```
tit/reporting/
├── __init__.py                    # Public API
│
├── core/                          # Core infrastructure
│   ├── __init__.py
│   ├── protocols.py               # Reportlet protocol, enums
│   ├── base.py                    # Base reportlet classes
│   ├── assembler.py               # ReportAssembler, ReportSection
│   └── templates.py               # CSS/JS templates
│
├── reportlets/                    # Specialized reportlets
│   ├── __init__.py
│   ├── metadata.py                # ConductivityTableReportlet, ProcessingStepReportlet
│   ├── images.py                  # SliceSeriesReportlet, MontageImageReportlet
│   ├── text.py                    # MethodsBoilerplateReportlet
│   └── references.py              # TIToolboxReferencesReportlet
│
└── generators/                    # Module-specific generators
    ├── __init__.py
    ├── base_generator.py          # BaseReportGenerator ABC
    ├── preprocessing.py           # PreprocessingReportGenerator
    ├── simulation.py              # SimulationReportGenerator
    └── flex_search.py             # FlexSearchReportGenerator
```

---

## Integration Status

| Module | Status | Location |
|--------|--------|----------|
| Simulator (CLI) | ✅ Integrated | `tit/sim/simulator.py` |
| Simulator (GUI) | ✅ Integrated | `tit/gui/simulator_tab.py` |
| Flex-Search | ✅ Integrated | `tit/opt/flex/flex.py` |
| Preprocessing | ✅ Integrated | `tit/pre/structural.py` |

---

## Usage Examples

### Basic Report Assembly

```python
from tit.reporting import (
    ReportAssembler,
    MetadataReportlet,
    TableReportlet,
)

# Create assembler
assembler = ReportAssembler(title='My Report')

# Add a section
section = assembler.add_section('summary', 'Summary')

# Add reportlets
section.add_reportlet(MetadataReportlet(
    data={'Subject': '001', 'Session': 'test'},
    display_mode='cards',
    columns=2
))

section.add_reportlet(TableReportlet(
    data=[{'Name': 'Test', 'Value': 42}],
    title='Results'
))

# Render and save
assembler.save('/path/to/report.html')
```

### Simulation Report

```python
from tit.reporting import SimulationReportGenerator

gen = SimulationReportGenerator(
    project_dir='/path/to/project',
    subject_id='001',
)

gen.add_simulation_parameters(
    conductivity_type='scalar',
    simulation_mode='TI',
    intensity_ch1=2.0,
)

gen.add_electrode_parameters(
    shape='circular',
    dimensions='10x10 mm',
    thickness=2.0,
)

gen.add_subject(
    subject_id='001',
    m2m_path='/path/to/m2m_001',
    status='completed',
)

gen.add_montage(
    montage_name='motor_cortex',
    electrode_pairs=[{'electrode1': 'F3', 'electrode2': 'F4'}],
)

gen.add_simulation_result(
    subject_id='001',
    montage_name='motor_cortex',
    status='completed',
)

report_path = gen.generate()
```

### Flex-Search Report

```python
from tit.reporting import FlexSearchReportGenerator

gen = FlexSearchReportGenerator(
    project_dir='/path/to/project',
    subject_id='001',
)

gen.set_configuration(
    optimization_target='mean_field',
    n_candidates=100,
)

gen.set_roi_info(
    roi_name='hippocampus',
    roi_type='atlas',
)

gen.add_search_result(
    rank=1,
    electrode_1a='F3',
    electrode_1b='F4',
    electrode_2a='P3',
    electrode_2b='P4',
    score=0.95,
)

gen.set_best_solution(
    electrode_pairs=[('F3', 'F4'), ('P3', 'P4')],
    score=0.95,
)

report_path = gen.generate()
```

### Preprocessing Report

```python
from tit.reporting import PreprocessingReportGenerator

gen = PreprocessingReportGenerator(
    project_dir='/path/to/project',
    subject_id='001',
)

gen.add_processing_step(
    step_name='DICOM Conversion',
    description='Convert DICOM files to NIfTI format',
    status='completed',
)

gen.add_processing_step(
    step_name='SimNIBS charm',
    description='Create head mesh model for simulations',
    status='completed',
)

gen.scan_for_data()  # Auto-detect input/output files
report_path = gen.generate()
```

---

## BIDS Output Structure

```
project_dir/
└── derivatives/
    └── ti-toolbox/
        └── reports/
            ├── dataset_description.json
            └── sub-{id}/
                ├── pre_processing_report_{timestamp}.html
                ├── simulation_report_{timestamp}.html
                └── flex_search_report_{timestamp}.html
```

---

## CSS Design

- **Header**: Gradient `#667eea` → `#764ba2` (purple)
- **Cards**: Grid layout with `#f8f9fa` background
- **Status**: Green (completed), Red (failed), Gray (skipped)
- **Tables**: Clean borders, alternating rows
- **Boilerplate**: Monospace font, light background, copy button
- **Responsive**: Single column on mobile

---

## Default References

The system includes default citations for:
- Temporal Interference (Grossman et al., 2017)
- SimNIBS (Thielscher et al., 2015; Saturnino et al., 2019)
- FreeSurfer (Fischl, 2012)
- QSIPrep (Cieslak et al., 2021)
- dcm2niix (Li et al., 2016)

---

## API Summary

```python
from tit.reporting import (
    # Core
    ReportAssembler,
    ReportMetadata,
    ReportSection,

    # Base Reportlets
    MetadataReportlet,
    ImageReportlet,
    TableReportlet,
    TextReportlet,
    ErrorReportlet,
    ReferencesReportlet,

    # Specialized Reportlets
    SliceSeriesReportlet,
    MontageImageReportlet,
    ConductivityTableReportlet,
    ProcessingStepReportlet,
    MethodsBoilerplateReportlet,
    TIToolboxReferencesReportlet,
    DEFAULT_CONDUCTIVITIES,

    # Generators
    SimulationReportGenerator,
    FlexSearchReportGenerator,
    PreprocessingReportGenerator,
    create_flex_search_report,
    create_preprocessing_report,

    # Constants
    REPORTS_BASE_DIR,
    BIDS_VERSION,
)
```
