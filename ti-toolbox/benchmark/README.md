# TI-Toolbox Benchmarking Suite

Measure performance of TI-Toolbox preprocessing and optimization steps with comprehensive hardware profiling.

## Quick Start

```bash
# 1. Install dependencies
pip install psutil pyyaml

# 2. Generate config file
python -m ti_toolbox.benchmark.config --generate

# 3. Edit paths in benchmark_config.yaml
nano benchmark_config.yaml

# 4. Run benchmarks
python -m ti_toolbox.benchmark charm
python -m ti_toolbox.benchmark flex
```

## Available Benchmarks

- **charm** - SimNIBS m2m creation
- **recon** - FreeSurfer cortical reconstruction  
- **dicom** - DICOM to NIfTI conversion
- **flex** - TI optimization with multi-start runs

Each measures: execution time, peak memory, CPU usage, and hardware info.

## Configuration

### Using Config File (Recommended)

Create `benchmark_config.yaml`:

```yaml
output_dir: ./benchmark_results
debug_mode: true

charm:
  ernie_data: /path/to/resources/example_data/ernie
  charm_script: /path/to/ti-toolbox/pre/charm.sh

flex:
  ernie_data: /path/to/resources/example_data/ernie
  multistart: [1, 3, 5]
  iterations: 500
  cpus: 1
```

Config file locations (searched in order):
1. `./benchmark_config.yaml`
2. `~/.ti-toolbox/benchmark_config.yaml`
3. `<toolbox-root>/benchmark_config.yaml`

### Using Command-Line

```bash
# Specify config location
python -m ti_toolbox.benchmark charm --config my_config.yaml

# Override config values
python -m ti_toolbox.benchmark flex --iterations 1000 --cpus 4

# No config file needed
python -m ti_toolbox.benchmark charm \
  --ernie-data /path/to/ernie \
  --charm-script /path/to/charm.sh \
  --output-dir ./results
```

## Usage Examples

### Charm Benchmark

```bash
# Basic
python -m ti_toolbox.benchmark charm

# Clean existing m2m first
python -m ti_toolbox.benchmark charm --clean

# Keep project files
python -m ti_toolbox.benchmark charm --keep-project
```

### Flex Benchmark

```bash
# Basic (requires charm to be run first)
python -m ti_toolbox.benchmark flex

# Custom multi-start values
python -m ti_toolbox.benchmark flex --multistart 1,5,10

# Custom parameters
python -m ti_toolbox.benchmark flex \
  --iterations 1000 \
  --popsize 20 \
  --cpus 8
```

### Recon Benchmark

```bash
# Basic
python -m ti_toolbox.benchmark recon

# With parallel processing
python -m ti_toolbox.benchmark recon --parallel
```

### DICOM Benchmark

```bash
python -m ti_toolbox.benchmark dicom \
  --dicom-source /path/to/dicom/files
```

## Configuration Parameters

### Global Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `output_dir` | `./benchmark_results` | Results directory |
| `keep_project` | `false` | Keep test project |
| `debug_mode` | `true` | Verbose output |

### Charm Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ernie_data` | Auto-detect | Path to Ernie data |
| `charm_script` | Auto-detect | Path to charm.sh |
| `clean` | `false` | Clean existing m2m |

### Flex Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ernie_data` | Auto-detect | Path to Ernie data |
| `multistart` | `[1, 3, 5]` | Multi-start values |
| `iterations` | `500` | Max iterations |
| `popsize` | `13` | Population size |
| `cpus` | `1` | Number of CPUs |
| `opt_goal` | `mean` | Optimization goal |
| `roi_center` | `[0, 0, 0]` | ROI center (mm) |
| `roi_radius` | `10.0` | ROI radius (mm) |

See `benchmark_config_example.yaml` for all parameters.

## Output

Results are saved as JSON files:

```
benchmark_results/
├── logs/
│   ├── charm_ernie_20241112_154427.log
│   └── flex_ernie_20241112_164820.log
├── charm_benchmark_ernie_latest.json
└── flex_benchmark_ernie_summary_20241112_164820.json
```

Result format:
```json
{
  "process_name": "charm_m2m_creation",
  "duration_seconds": 1575.3,
  "duration_formatted": "26m 15s",
  "peak_memory_mb": 2048.5,
  "avg_cpu_percent": 85.3,
  "hardware_info": {...},
  "success": true
}
```

## Common Options

All benchmarks support:
- `--config PATH` - Config file location
- `--output-dir PATH` - Override output directory
- `--keep-project` - Keep test files
- `--no-debug` - Less verbose output
- `--help` - Show help

## Utilities

```bash
# Generate example config
python -m ti_toolbox.benchmark.config --generate

# Show current configuration
python -m ti_toolbox.benchmark.config --show

# Generate at specific location
python -m ti_toolbox.benchmark.config --generate --output my_config.yaml
```

## Requirements

**Python packages:**
```bash
pip install psutil pyyaml
```

**External tools:**
- Charm: SimNIBS
- Recon: FreeSurfer
- DICOM: dcm2niix
- Flex: SimNIBS + completed charm m2m

## Programmatic Usage

```python
from ti_toolbox.benchmark import BenchmarkTimer, get_hardware_info

# Get hardware info
hw_info = get_hardware_info()
print(f"CPU: {hw_info.cpu_model}")

# Benchmark a process
timer = BenchmarkTimer("my_process")
timer.start()
# ... your code ...
result = timer.stop(success=True)
print(f"Duration: {result.duration_formatted}")
```

## Troubleshooting

**Config file not found:**
- Check filename is `benchmark_config.yaml`
- Use `--config` to specify path
- Run `python -m ti_toolbox.benchmark.config --show`

**PyYAML not installed:**
```bash
pip install pyyaml
```

**Path issues:**
- Use absolute paths in config file
- Verify paths exist: `ls -la /path/to/data`

**Ernie data not found:**
- Ensure directory contains `T1.nii.gz` and `T2_reg.nii.gz`

## Example Workflows

### Development Testing
```yaml
# dev_config.yaml
output_dir: /tmp/results
keep_project: true
debug_mode: true

flex:
  multistart: [1]
  iterations: 100
  cpus: 4
```

```bash
python -m ti_toolbox.benchmark flex --config dev_config.yaml
```

### Production Benchmarking
```yaml
# prod_config.yaml
output_dir: /results/benchmarks
keep_project: false
debug_mode: false

flex:
  multistart: [1, 3, 5, 10]
  iterations: 1000
  cpus: 16
```

```bash
python -m ti_toolbox.benchmark charm --config prod_config.yaml
python -m ti_toolbox.benchmark flex --config prod_config.yaml
```

### Custom Data
```bash
# Override specific paths
python -m ti_toolbox.benchmark charm \
  --ernie-data /data/my_subject \
  --output-dir ./my_results
```

## Tips

1. **Start with charm** - Flex requires charm m2m files
2. **Use debug mode** - Helpful for troubleshooting
3. **Test with fewer iterations** - Use `--iterations 100` for quick tests
4. **Multiple configs** - Create different configs for different scenarios
5. **Clean runs** - Use `--clean` for fresh benchmarks

## License

Part of TI-Toolbox. See main repository for license information.
