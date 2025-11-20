# TI-Toolbox Benchmarking Suite

Comprehensive performance benchmarking for all TI-Toolbox pipeline components.

## Overview

The benchmarking suite provides automated performance testing for:

### Preprocessing & Mesh Generation
- **DICOM** - DICOM to NIfTI conversion
- **CHARM** - Head mesh (m2m) creation
- **RECON** - FreeSurfer cortical reconstruction

### Optimization & Simulation
- **Leadfield** - Leadfield matrix generation
- **Flex-Search** - TI optimization with differential evolution
- **Ex-Search** - Exhaustive TI electrode search
- **Simulator** - TI/mTI simulation execution

### Analysis Tools
- **Tissue Analyzer** - Tissue volume and thickness analysis (CSF, bone, skin)
- **Mesh Analyzer** - Surface-based field analysis (spherical ROI, cortical, whole-head)
- **Voxel Analyzer** - Volumetric NIfTI-based field analysis (spherical ROI, cortical, whole-head)

## Quick Start

```bash
# Preprocessing & Mesh Generation
python -m benchmark.dicom --config benchmark_config.yaml
python -m benchmark.charm --config benchmark_config.yaml
python -m benchmark.recon --config benchmark_config.yaml

# Optimization & Simulation
python -m benchmark.leadfield --config benchmark_config.yaml
python -m benchmark.flex --config benchmark_config.yaml
python -m benchmark.ex_search --config benchmark_config.yaml
python -m benchmark.simulator --config benchmark_config.yaml

# Analysis Tools
python -m benchmark.tissue_analyzer --config benchmark_config.yaml
python -m benchmark.mesh_analyzer --config benchmark_config.yaml
python -m benchmark.voxel_analyzer --config benchmark_config.yaml
```

## Configuration

All benchmarks use `benchmark_config.yaml` for centralized configuration.

### Key Configuration Options

```yaml
# Global settings
output_dir: /development/benchmark_results    # Where to save results and logs
keep_project: true                            # Keep temporary directories after completion
debug_mode: true                              # Enable verbose logging
```

### Per-Benchmark Configuration

Each benchmark has its own section in the config file:

**Preprocessing & Mesh Generation:**
- **dicom**: DICOM source directory, conversion script path
- **charm**: T1/T2 images, subject ID, charm script path
- **recon**: T1/T2 images, subject ID, recon-all script path, parallel option

**Optimization & Simulation:**
- **leadfield**: m2m directory, electrode CSV file, tissue types
- **flex**: m2m directory, optimization parameters, ROI settings
- **ex_search**: m2m directory, leadfield path, electrode counts, current parameters
- **simulator**: m2m directory, montage configuration, simulation parameters

**Analysis Tools:**
- **tissue_analyzer**: segmented NIfTI path, tissue types (csf, bone, skin)
- **mesh_analyzer**: field mesh path, analysis type (sphere, cortex, whole_head), ROI/atlas parameters
- **voxel_analyzer**: field NIfTI path, analysis type (sphere, cortex, whole_head), ROI/atlas parameters

See `benchmark_config.yaml` for all available options.

## Benchmark Outputs

### JSON Results

Each benchmark saves detailed JSON files with:

```json
{
  "process_name": "flex_search_multistart_1",
  "duration_seconds": 1279.15,
  "duration_formatted": "21m 19s",
  "peak_memory_mb": 28.09,
  "avg_cpu_percent": 0.11,
  "hardware_info": { ... },
  "metadata": { ... },
  "success": true
}
```

### Log Files

Detailed execution logs saved to: `{output_dir}/logs/{benchmark}_{subject}_{timestamp}.log`

### Results Files

- Timestamped: `{benchmark}_benchmark_{subject}_{timestamp}.json`
- Latest: `{benchmark}_benchmark_{subject}_latest.json`

## Ex-Search Specific

Ex-search produces additional outputs in the m2m directory:

```
/mnt/BIDS_new/derivatives/SimNIBS/sub-{id}/ex-search/xyz_{X}_{Y}_{Z}_{net_name}/
├── analysis_results.json       # All montage results
├── final_output.csv           # Spreadsheet format
└── montage_distributions.png  # Visualization
```

The benchmark JSON includes the path in `metadata.results_directory`.

## Hardware Information

All benchmarks capture:
- CPU model, cores, frequency
- Memory (total, available)
- GPU information (if available)
- Platform details
- Python version

## Command-Line Overrides

All config file values can be overridden via command-line:

```bash
python -m benchmark.flex \
  --m2m-dir /path/to/m2m_101 \
  --multistart 1,2,3 \
  --iterations 1000 \
  --cpus 4
```

## Example: Running Ex-Search Benchmark

```bash
# Using config file
python -m benchmark.ex_search --config benchmark_config.yaml

# Command-line override
python -m benchmark.ex_search \
  --m2m-dir /mnt/BIDS_new/derivatives/SimNIBS/sub-101/m2m_101 \
  --leadfield /path/to/leadfield.hdf5 \
  --n-electrodes 4 \
  --total-current 1.0 \
  --step-size 0.1
```

## Results Analysis

Benchmark results include:
- Execution time (formatted and in seconds)
- Peak memory usage
- Average CPU usage
- Success/failure status
- Detailed metadata about parameters used
- Output file locations

## Notes

- All paths in config should be absolute for container compatibility
- Benchmarks automatically detect container environment (/mnt paths)
- Debug mode logs all subprocess output for troubleshooting
- Results are always saved even if benchmark fails
