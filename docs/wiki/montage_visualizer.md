---
layout: wiki
title: Montage Visualizer
permalink: /wiki/montage_visualizer/
---

# Montage Visualizer

The Montage Visualizer is a tool for creating visual representations of electrode montages on standardized head templates. It supports both unipolar and multipolar temporal interference (TI) stimulation configurations.

## Overview

Temporal interference uses high-frequency alternating currents applied through multiple electrode pairs to create low-frequency envelopes in deeper brain regions. The Montage Visualizer helps researchers visualize electrode placements and channel configurations on head templates.

## Simulation Modes

### Unipolar Mode (4 Electrodes, 2 Channels)
Unipolar montages use **4 electrodes** arranged in **2 independent channels**. Each channel consists of one electrode pair that can be independently controlled.

**Structure**:
- Channel 1: Electrode pair (anode/cathode)
- Channel 2: Electrode pair (anode/cathode)
- Total: 4 electrodes, 2 channels

**Visualization**: Creates separate images for each montage, showing electrode positions and channel connections.

### Multipolar Mode (8 Electrodes, 4 Channels)
Multipolar montages use **8 electrodes** arranged in **4 simultaneous channels**. This allows for more complex stimulation patterns with multiple independent current pathways.

**Structure**:
- Channel 1: Electrode pair
- Channel 2: Electrode pair
- Channel 3: Electrode pair
- Channel 4: Electrode pair
- Total: 8 electrodes, 4 channels

**Visualization**: Creates a combined image showing all channels overlaid on the same template.

## Supported EEG Networks

- **GSN-HydroCel Systems**: EGI_template.csv, GSN-HydroCel-185.csv, GSN-HydroCel-256.csv
- **10-10 Systems**: EEG10-10_UI_Jurak_2007.csv, EEG10-10_Cutini_2011.csv, EEG10-20_Okamoto_2004.csv, EEG10-10_Neuroelectrics.csv
- **Freehand/Flex Modes**: Arbitrary electrode positions (visualization skipped)

## Visual Features

### Electrode Rings
- **Size**: 40px radius rings centered on electrode positions
- **Colors**: 8 distinct colors (chartreuse, deepskyblue, lime, gold, hotpink, turquoise, violet, orange)
- **Design**: Hollow circles with 6px stroke width for clear visibility

### Connection Lines
- **Style**: Smooth quadratic Bezier curves forming natural arches
- **Color**: Matches corresponding electrode ring colors
- **Width**: 3px stroke
- **Offset**: Lines start/end 15px away from electrode centers to avoid overlap

## Example Visualizations

### Unipolar Montage (4 Electrodes, 2 Channels)
![Unipolar Montage Example](assets/example_unipolar_highlighted_visualization.png)

This example shows a unipolar montage with 2 channels (4 electrodes total):
- **Channel 1** (chartreuse): E010-E011
- **Channel 2** (deepskyblue): E012-E013

### Multipolar Montage (8 Electrodes, 4 Channels)
![Multipolar Montage Example](assets/combined_montage_visualization.png)

This example shows a multipolar montage with 4 channels (8 electrodes total):
- **Channel 1** (chartreuse): E010-E011
- **Channel 2** (deepskyblue): E012-E013
- **Channel 3** (lime): E014-E015
- **Channel 4** (gold): E016-E017

## Usage

### Command Line Interface

```bash
python3 montage_visualizer.py \
  --sim-mode {U|M} \
  --eeg-net EEG_NET \
  --output-dir OUTPUT_DIR \
  [--montage-file MONTAGE_FILE] \
  [--project-dir-name PROJECT_DIR_NAME] \
  [--quiet] \
  montages [montages ...]
```

### Parameters

- `--sim-mode`: Simulation mode (U for Unipolar, M for Multipolar)
- `--eeg-net`: EEG network name (e.g., EGI_template.csv)
- `--output-dir`: Directory for output visualization images
- `--montage-file`: Path to montage_list.json (auto-detected if not provided)
- `--project-dir-name`: Project directory name for resource detection
- `--quiet`: Suppress verbose output
- `montages`: List of montage names to visualize

### Example Usage

```bash
# Generate unipolar montage visualization
python3 montage_visualizer.py \
  --sim-mode U \
  --eeg-net EGI_template.csv \
  --output-dir ./output \
  example_montage

# Generate multipolar montage visualization
python3 montage_visualizer.py \
  --sim-mode M \
  --eeg-net EGI_template.csv \
  --output-dir ./output \
  example_multipolar_montage
```

## Dependencies

- **Python 3.x**
- **ImageMagick** (for image processing and composition)
- **montage_list.json** configuration file with montage definitions

## File Structure

```
resources/amv/
├── GSN-256.csv               # GSN-256 electrode coordinates
├── 10-10.csv                 # 10-10 electrode coordinates
├── GSN-256.png               # Head template image
└── pair[1-8]ring.png         # Colored ring overlay images

output/
├── [montage_name]_highlighted_visualization.png    # Unipolar mode
└── combined_montage_visualization.png              # Multipolar mode
```

## Technical Details

### Coordinate Mapping
The visualizer maps electrode labels to pixel coordinates using CSV coordinate files. Each EEG network has its own coordinate mapping for accurate electrode positioning on the template image.

### Image Processing
Uses ImageMagick's `convert` command for:
- Template image copying
- Ring overlay composition with transparency
- Connection line drawing using Bezier curves

### Resource Detection
Automatically detects resource files in the following priority order:
1. Project directory: `/mnt/{PROJECT_DIR_NAME}/code/ti-toolbox/resources/amv`
2. Development directory: `/development/resources/amv`
3. Production directory: `/ti-toolbox/resources/amv`
4. Current working directory: `./resources/amv`
