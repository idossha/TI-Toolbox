---
layout: wiki
title: Command Line Interface
permalink: /wiki/cli/
---

The TI-Toolbox CLI supports three complementary workflows:

- **Interactive mode**: Guided, prompt-based configuration -- ideal for exploration and first-time runs
- **Direct mode**: Fully specified command-line flags -- better for scripts and advanced control
- **JSON config mode**: Each major module has a `__main__.py` entry point that accepts a JSON config file -- used by the GUI and for reproducible runs

## Interactive vs Direct Mode

### Interactive Mode

```bash
# Run command with no arguments for guided prompts
simulator
```

The CLI will guide you through:
- Subject selection
- Framework choice (montage/flex)
- EEG cap selection
- Montage configuration
- Parameter setup

### Direct Mode

```bash
# All parameters specified explicitly
simulator \
  --sub 101 \
  --framework montage \
  --eeg GSN-HydroCel-185.csv \
  --montages my_montage \
  --intensity 2.0
```

Mode selection is automatic:
- **No arguments** -> Interactive mode
- **Any arguments present** -> Direct mode

## JSON Config Entry Points

Each major module can be invoked as a subprocess with a JSON config file. This is the pattern the GUI uses to run operations in separate processes:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
```

Each `__main__.py` reads the JSON file, reconstructs typed config dataclasses, and calls the corresponding `run_*` function.

### Config Serialization (`tit/config_io.py`)

The `tit/config_io.py` module handles serialization of typed config dataclasses to JSON and back. It supports:

- **Enum fields** -- serialized as their `.value`
- **Nested dataclasses** -- recursively serialized
- **Union-typed fields** -- uses a `_type` discriminator to identify the concrete class (e.g., `SphericalROI`, `AtlasROI`, `LabelMontage`, `XYZMontage`)

```python
from tit.config_io import write_config_json, read_config_json

# Serialize a config dataclass to a temp JSON file
path = write_config_json(my_flex_config, prefix="flex")

# Read it back as a plain dict
data = read_config_json(path)
```

The `_type` discriminator pattern allows `__main__.py` entry points to reconstruct the correct dataclass variant from a plain JSON dict. For example, an ROI field in the JSON might look like:

```json
{
  "_type": "SphericalROI",
  "center": [-45.0, 0.0, 0.0],
  "radius": 5.0
}
```

### How the GUI Uses This

The GUI tabs build config dataclasses, serialize them via `write_config_json()`, then launch:

```
simnibs_python -m tit.<module> /tmp/flex_abc123.json
```

in a `QThread`. Stdout from the subprocess is captured by `BaseProcessThread` and displayed in the tab's console widget.

## Available Commands

| Command | Description | Interactive | Direct Examples |
|---------|-------------|-------------|---------|
| `pre_process` | Preprocessing pipeline | `pre_process` | `pre_process --subs 101 --run-recon --create-m2m` |
| `flex_search` | Electrode optimization | `flex_search` | `flex_search --subject 101 --roi-method spherical` |
| `create_leadfield` | Generate leadfield matrices | `create_leadfield` | `create_leadfield --sub 101 --eeg cap.csv` |
| `ex_search` | Leadfield-based optimization | `ex_search` | `ex_search --sub 101 --lf leadfield.hdf5 --pool` |
| `simulator` | Run TI simulations | `simulator` | `simulator --sub 101 --montages my_montage` |
| `analyzer` | Analyze single subject results | `analyzer` | `analyzer --sub 101 --sim montage --coordinates 0 0 0` |
| `group_analyzer` | Analyze multiple subjects | `group_analyzer` | `group_analyzer --subs 101,102 --sim montage` |
| `cluster_permutation` | Statistical analysis | `cluster_permutation` | `cluster_permutation --csv data.csv --name analysis` |
| `blender` | Create visualizations | `blender` | `blender --subject 101 --simulation montage` |

## Getting Help

All commands support detailed help via the `-h` or `--help` flag:

```bash
# Get command-specific help
simulator -h
analyzer --help
blender -h
```