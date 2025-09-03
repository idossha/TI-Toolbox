# TI-Toolbox Classifier v2.0

Production-ready classifier for TI (Temporal Interference) field analysis following Albizu et al. (2020) methodology.

## Overview

The TI-Toolbox Classifier predicts treatment response by analyzing spatial distribution of TI electric fields in the brain using machine learning. It provides both voxel-wise and ROI-averaged analysis approaches.

## Key Features

### 🧠 **Dual Analysis Modes**
- **Voxel-wise**: Statistical analysis at individual voxel level (for large samples >50 subjects)
- **ROI-averaged**: Anatomically-informed analysis using brain atlas (recommended for <50 subjects)

### 🔬 **Robust Methodology**
- **Nested cross-validation** following Albizu et al. (2020)
- **Proper feature selection** within CV folds (prevents data leakage)
- **MNI space analysis** with comprehensive alignment verification
- **FreeSurfer integration** for atlas resampling and visualization

### 📊 **Quality Assurance**
- **Comprehensive QA reports** with atlas-field overlap analysis
- **Visual alignment verification** with before/after resampling images
- **Per-subject metrics** for alignment validation
- **Automatic error detection** for coordinate misalignment

## Quick Start

### Command Line Interface

```bash
# ROI-based analysis (recommended for small samples)
python cli.py train \
  --project-dir /path/to/project \
  --response-file responses.csv \
  --roi-features

# Voxel-wise analysis (for large samples)
python cli.py train \
  --project-dir /path/to/project \
  --response-file responses.csv \
  --resolution 2 \
  --p-threshold 0.01

# Generate QA report only
python cli.py qa \
  --project-dir /path/to/project \
  --response-file responses.csv
```

### Python API

```python
from ti_classifier import TIClassifier

# Initialize classifier
classifier = TIClassifier(
    project_dir="/path/to/project",
    resolution_mm=2,
    use_roi_features=True  # Recommended for small samples
)

# Train
results = classifier.train("responses.csv")
```

## Input Requirements

### Response File Format (CSV)
```csv
subject_id,response,simulation_name
sub-101,1,Nav_1
sub-102,0,Nav_2
sub-103,1,Nav_3
```

**Required columns:**
- `subject_id`: Subject identifier
- `response`: Binary response (1=responder, 0=non-responder)

**Optional columns:**
- `simulation_name`: Specific simulation for each subject

### NIfTI Requirements
- **MNI space**: All files must be in standard MNI152 space
- **Grey matter masked**: Recommended for optimal performance
- **Consistent resolution**: All subjects should have same voxel size
- **File naming**: `grey_{simulation}_TI_MNI_MNI_TI_max.nii.gz`

## Output Structure

```
results/
├── ti_classifier_model.pkl          # Trained model
├── performance_metrics.csv          # CV performance
├── results_summary.json             # Summary results
├── intensity_plots/                 # Current intensity analysis
├── statistical_maps/                # T-stats, p-values, weights (MNI)
├── roi_extractions/                 # Significant ROI files
├── group_averages/                  # Mean field maps
├── freeview_command.sh              # Visualization script
└── QA/                              # Quality assurance
    ├── QA.log                       # File inventory
    ├── atlas_info.txt               # Atlas details
    ├── overlap_metrics.csv          # Alignment analysis
    ├── overlap_summary.txt          # Interpretation
    └── overlay_*.png                # Visual alignment check
```

## Analysis Modes

### ROI-Averaged Features (Recommended)
**Best for:** Small samples (<50 subjects)
- **Features:** ~360 anatomical regions
- **Benefits:** Better statistical power, interpretable results
- **Speed:** Fast training
- **Robustness:** Less sensitive to alignment issues

### Voxel-wise Features
**Best for:** Large samples (>50 subjects)
- **Features:** ~300K individual voxels
- **Benefits:** Highest spatial resolution
- **Requirements:** Strict p-value thresholds, more subjects
- **Speed:** Slower but parallelized

## Quality Assurance

### Automatic Checks
- **Data consistency** validation across subjects
- **Atlas-field alignment** verification
- **Coordinate system** integrity checks
- **Overlap analysis** with clear interpretation

### Expected Metrics
- **Atlas coverage:** 60-90% (field voxels in atlas ROIs)
- **Field coverage:** 50-70% (atlas ROIs with field data)
- **Consistency:** <5% variability across subjects

## Dependencies

```bash
pip install numpy pandas scipy scikit-learn nibabel matplotlib joblib
```

**Optional (recommended):**
- FreeSurfer (for optimal atlas resampling)
- FSL (for additional neuroimaging tools)

## Citation

Methodology based on:
- Albizu et al. (2020). Machine learning and individual variability in electric characteristics predict tDCS treatment response. *Brain Stimulation*, 13(6), 1753-1764.

## Support

For issues and questions:
- Check QA reports for alignment problems
- Review overlap_summary.txt for interpretation
- Ensure FreeSurfer is available for optimal results