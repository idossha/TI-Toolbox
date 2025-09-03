# TI-Toolbox Classifier Atlas Validation

## Overview

The TI-Toolbox Classifier now enforces strict validation for brain atlases to ensure only properly dimensioned and validated atlases are used. This prevents dimension mismatches and ensures consistent results.

## Validated Atlases

The classifier **only** accepts these two validated atlases:

### 1. Harvard-Oxford Cortical Atlas
- **Name**: `HarvardOxford-cort-maxprob-thr0-1mm`
- **Description**: Harvard-Oxford Cortical Atlas (48 ROIs)
- **Files Required**:
  - `HarvardOxford-cort-maxprob-thr0-1mm.nii.gz`
  - `HarvardOxford-cort-maxprob-thr0-1mm.txt`

### 2. MNI Glasser HCP Atlas
- **Name**: `MNI_Glasser_HCP_v1.0`
- **Description**: MNI Glasser HCP Atlas (360 ROIs)
- **Files Required**:
  - `MNI_Glasser_HCP_v1.0.nii.gz`
  - `MNI_Glasser_HCP_v1.0.txt`

## Required Location

All atlas files **must** be located in:
```
/ti-toolbox/assets/atlas/
```

The atlas manager will search in this order:
1. `/ti-toolbox/assets/atlas/` (primary - Docker mount)
2. `{project_dir}/assets/atlas/` (secondary - development)
3. `{ti-toolbox-install}/assets/atlas/` (tertiary - installation)

## Validation Features

### 1. Atlas Name Validation
```python
# Only these names are accepted
SUPPORTED_ATLASES = {
    "HarvardOxford-cort-maxprob-thr0-1mm": {...},
    "MNI_Glasser_HCP_v1.0": {...}
}
```

### 2. File Path Validation
- Atlas manager prioritizes `/ti-toolbox/assets/atlas/`
- Uses exact validated filenames
- Logs the path where atlas is found

### 3. Runtime Validation
- Validates atlas name at classifier initialization
- Provides clear error messages for unsupported atlases
- Lists supported atlases in error messages

## Usage

### Command Line Interface
The CLI automatically restricts atlas choices:
```bash
python cli.py train --atlas HarvardOxford-cort-maxprob-thr0-1mm --project-dir /path/to/project --response-file responses.csv
python cli.py train --atlas MNI_Glasser_HCP_v1.0 --project-dir /path/to/project --response-file responses.csv
```

### Python API
```python
from ti_classifier import TIClassifier

# This will work
classifier = TIClassifier(
    project_dir="/path/to/project",
    atlas_name="HarvardOxford-cort-maxprob-thr0-1mm"
)

# This will raise ValueError
classifier = TIClassifier(
    project_dir="/path/to/project", 
    atlas_name="unsupported_atlas"  # ERROR!
)
```

## Verification Tools

### 1. Atlas Verification Script
Run this to check if atlases are properly installed:
```bash
cd classifier/
python verify_atlases.py
```

This script will:
- Check if `/ti-toolbox/assets/atlas/` exists
- Verify all required atlas files are present
- Test loading each atlas with AtlasManager
- Report dimensions and ROI counts
- Show sample ROI labels

### 2. Environment Check
```bash
cd classifier/
python check_environment.py
```

## Error Handling

### Unsupported Atlas Name
```
ValueError: Unsupported atlas 'invalid_name'. 
Supported atlases: ['HarvardOxford-cort-maxprob-thr0-1mm', 'MNI_Glasser_HCP_v1.0']
```

### Missing Atlas Files
```
WARNING: Atlas not found in expected locations. 
Expected: /ti-toolbox/assets/atlas/HarvardOxford-cort-maxprob-thr0-1mm.nii.gz
```

## Benefits

1. **Prevents Dimension Errors**: Only atlases with correct dimensions are allowed
2. **Consistent Results**: Ensures all users work with the same validated atlases
3. **Clear Error Messages**: Helpful feedback when atlases are missing or incorrect
4. **Docker Compatibility**: Prioritizes standard Docker mount paths
5. **Development Friendly**: Falls back to project-relative paths for development

## Integration with Other Components

### FSL ROI Extractor
- Uses validated atlas names for FSL commands
- Ensures consistent ROI extraction across subjects

### Plotting Module
- ROI importance plots use validated ROI labels
- Consistent brain region naming across visualizations

### QA Reporter
- Atlas information includes validation status
- Reports which validated atlas is being used

## Maintenance

To add a new atlas (requires code changes):

1. Add entry to `SUPPORTED_ATLASES` in `atlas_manager.py`
2. Add choice to CLI parser in `cli.py`
3. Place atlas files in `/ti-toolbox/assets/atlas/`
4. Test with `verify_atlases.py`
5. Update documentation

## Troubleshooting

### "Atlas not found" errors
1. Check if files exist: `ls /ti-toolbox/assets/atlas/`
2. Verify filenames match exactly (case-sensitive)
3. Run verification script: `python verify_atlases.py`

### "Unsupported atlas" errors
1. Check spelling of atlas name
2. Use only supported atlas names
3. Run `AtlasManager.get_supported_atlases()` to see valid options

### Docker mount issues
1. Ensure `/ti-toolbox/assets/atlas/` is properly mounted
2. Check Docker volume configuration
3. Verify file permissions in container
