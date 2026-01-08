---
layout: wiki
title: Command Line Interface
permalink: /wiki/cli/
---

The TI-Toolbox CLI supports two complementary workflows:

- **Interactive mode**: Guided, prompt-based configuration — ideal for exploration and first-time runs who do not want GUI
- **Direct mode**: Fully specified command-line flags — better for scripts and allow advanced control

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
- **No arguments** → Interactive mode
- **Any arguments present** → Direct mode

## Available Commands

| Command | Description | Interactive | Direct Examples|
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