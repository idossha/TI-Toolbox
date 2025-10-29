# Flex-Search: Flexible TI Stimulation Optimization

A modular Python tool for optimizing temporal interference (TI) stimulation electrode placement using SimNIBS. Supports multiple ROI definitions and optimization strategies with robust multi-start capabilities.

## Features

- **Multiple ROI Methods**: Spherical, cortical atlas-based, and subcortical volume-based
- **Optimization Goals**: Mean, max, or focality-based targeting
- **Multi-start Optimization**: Robust results through multiple optimization runs
- **MNI Coordinate Support**: Automatic transformation to subject space
- **EEG Cap Mapping**: Optional mapping to standard electrode positions
- **Comprehensive Logging**: Structured logging with progress tracking

## Module Structure

```
flex-search/
├── flex.py              # Main orchestration script
├── flex_config.py       # Configuration and optimization setup
├── flex_log.py          # Logging utilities and progress tracking
├── roi.py               # ROI configuration (spherical/atlas/subcortical)
├── multi_start.py       # Multi-start optimization logic
└── flex-search.py       # Command-line wrapper
```

## Usage

### Basic Command

```bash
python -m flex_search \
  --subject 101 \
  --goal mean \
  --postproc max_TI \
  --roi-method spherical \
  --eeg-net EGI_template \
  --radius 12.5 \
  --current 2.0
```

### Multi-start Optimization

```bash
python -m flex_search \
  --subject 101 \
  --goal mean \
  --postproc max_TI \
  --roi-method spherical \
  --eeg-net EGI_template \
  --radius 12.5 \
  --current 2.0 \
  --n-multistart 5
```

## Required Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--subject` | Subject ID | `101` |
| `--goal` | Optimization goal | `mean`, `max`, `focality` |
| `--postproc` | Post-processing method | `max_TI`, `dir_TI_normal`, `dir_TI_tangential` |
| `--roi-method` | ROI definition method | `spherical`, `atlas`, `subcortical` |
| `--eeg-net` | EEG cap template | `EGI_template` |
| `--radius` | Electrode radius (mm) | `12.5` |
| `--current` | Electrode current (mA) | `2.0` |

## ROI Configuration

### Spherical ROI

Requires environment variables:
- `ROI_X`, `ROI_Y`, `ROI_Z`: Coordinates (subject or MNI space)
- `ROI_RADIUS`: Sphere radius in mm
- `USE_MNI_COORDS`: Set to `true` for MNI coordinates (optional)

### Atlas-based ROI

Requires environment variables:
- `ATLAS_PATH`: Path to surface atlas file (.annot)
- `ROI_LABEL`: Integer label value
- `SELECTED_HEMISPHERE`: `lh` or `rh`

### Subcortical ROI

Requires environment variables:
- `VOLUME_ATLAS_PATH`: Path to volume atlas (.nii.gz, .mgz)
- `VOLUME_ROI_LABEL`: Integer label value

## Optional Arguments

### Performance & Stability
- `--n-multistart N`: Number of optimization runs (default: 1)
- `--max-iterations N`: Maximum iterations for differential evolution
- `--population-size N`: Population size for differential evolution
- `--cpus N`: Number of CPU cores to use

### Focality Goal
- `--thresholds VALUES`: Comma-separated threshold values
- `--non-roi-method METHOD`: `everything_else` or `specific`

### Electrode Mapping
- `--enable-mapping`: Map to nearest EEG cap positions
- `--disable-mapping-simulation`: Skip simulation with mapped electrodes

### Output Control
- `--skip-final-electrode-simulation`: Skip final electrode simulation

## Output Structure

```
derivatives/SimNIBS/sub-{subject}/flex_search/{roi_name}_{goal}_{postproc}/
├── fields_summary.txt              # Field strength summary
├── optimization_summary.txt        # Single run summary
├── multistart_optimization_summary.txt  # Multi-start summary (if n>1)
├── {subject}_TI_fields/           # TI field results
└── leadfield/                     # Leadfield data
```

## Logging

Logs are saved to:
```
derivatives/ti-toolbox/logs/sub-{subject}/flex_search_{subject}_{timestamp}.log
```

Log levels controlled by `TI_LOG_LEVEL` environment variable:
- `DEBUG`: Detailed information (default when `DEBUG_MODE=true`)
- `INFO`: Standard progress information (default)
- `WARNING`: Warnings only
- `ERROR`: Errors only

## Example Workflows

### Single Subject, Spherical ROI

```bash
export PROJECT_DIR=/path/to/project
export SUBJECT_ID=101
export ROI_X=50
export ROI_Y=10
export ROI_Z=40
export ROI_RADIUS=15

python -m flex_search \
  --subject 101 \
  --goal mean \
  --postproc max_TI \
  --roi-method spherical \
  --eeg-net EGI_template \
  --radius 12.5 \
  --current 2.0
```

### Multi-subject with MNI Coordinates

```bash
export PROJECT_DIR=/path/to/project
export ROI_X=50
export ROI_Y=10
export ROI_Z=40
export ROI_RADIUS=15
export USE_MNI_COORDS=true

for subject in 101 102 103; do
  export SUBJECT_ID=$subject
  python -m flex_search \
    --subject $subject \
    --goal mean \
    --postproc max_TI \
    --roi-method spherical \
    --eeg-net EGI_template \
    --radius 12.5 \
    --current 2.0 \
    --n-multistart 3
done
```

### Atlas-based ROI with Focality

```bash
export PROJECT_DIR=/path/to/project
export SUBJECT_ID=101
export ATLAS_PATH=/path/to/lh.101_DK40.annot
export ROI_LABEL=1022
export SELECTED_HEMISPHERE=lh

python -m flex_search \
  --subject 101 \
  --goal focality \
  --postproc max_TI \
  --roi-method atlas \
  --eeg-net EGI_template \
  --radius 12.5 \
  --current 2.0 \
  --thresholds 0.5,0.8 \
  --non-roi-method everything_else \
  --n-multistart 5
```

## Best Practices

1. **Use Multi-start**: For robust results, use `--n-multistart 3` or higher
2. **MNI Coordinates**: For multi-subject studies, use MNI coordinates with `USE_MNI_COORDS=true`
3. **Log Everything**: Keep `DEBUG_MODE=false` for clean console output; detailed logs go to file
4. **Monitor Progress**: Console shows tree-style progress updates with timing
5. **Check Summaries**: Review `multistart_optimization_summary.txt` for detailed statistics

## Dependencies

- SimNIBS (with Python API)
- NumPy
- Python 3.8+

## See Also

- [ROI Configuration Guide](../docs/wiki/roi-configuration.md)
- [Multi-start Optimization Guide](../docs/wiki/multi-start.md)
- [Full Documentation](../docs/wiki/flex-search.md)

