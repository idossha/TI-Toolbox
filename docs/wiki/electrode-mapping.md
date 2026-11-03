---
layout: wiki
title: Electrode Mapping
permalink: /wiki/electrode-mapping/
---

## Overview

Electrode mapping moves optimized free electrode positions onto distinct sites of an EEG net, using the Hungarian algorithm (linear sum assignment) to minimize the total distance, so a [flex-search]({{ site.baseurl }}/wiki/flex-search/) result can be delivered with a real cap. Distances are straight-line millimetres.

## In the application

Three routes map positions onto a net:

1. **Simulator**: in a job row, choose Source ▸ **Flex result**, the run, then a net in **Placement**. The positions are mapped onto that net and saved in the run folder as `electrode_mapping_<net>.json`. **Optimised (XYZ)** keeps the free positions. See [Simulator]({{ site.baseurl }}/wiki/simulator/#montage-sources).
2. **Flex-search**: **After the search ▸ Run simulation with mapped electrodes** maps the winning placement onto the net (SimNIBS's own step) and simulates it. It writes the same `electrode_mapping_<net>.json`, so the Simulator reuses it. See [Flex search]({{ site.baseurl }}/wiki/flex-search/).
3. **Results**: **Evaluated candidates ▸ Use in Simulator**, then a net in **Placement**, snaps a Flex candidate to cap sites. The view shows the original positions hollow, with dashed links to the sites. Nothing is saved.

## From Python

The same mapping helpers can be used from a script:

```python
import os
from tit.tools.map_electrodes import (
    load_electrode_positions_json,
    read_csv_positions,
    map_electrodes_to_net,
    save_mapping_result,
    log_mapping_summary,
)

opt_pos, ch_arr_idx = load_electrode_positions_json("flex-search/<run>/electrode_positions.json")
net_pos, net_labels = read_csv_positions("m2m_ernie/eeg_positions/GSN-HydroCel-185.csv")
result = map_electrodes_to_net(opt_pos, net_pos, net_labels, ch_arr_idx)
save_mapping_result(result, "flex-search/<run>/electrode_mapping_GSN-HydroCel-185.json",
                    eeg_net_name="GSN-HydroCel-185.csv")
log_mapping_summary(result)    # per-electrode distances, via the tit.tools logger
```

`save_mapping_result` needs an explicit output path; the `eeg_net` key only appears in the JSON when `eeg_net_name` is given. Saved in the run folder as `electrode_mapping_<net>.json`, as here, the mapping is offered for that net in the Simulator.

## Input Format

### electrode_positions.json

```json
{
  "optimized_positions": [
    [-85.61, -29.0, -8.56],
    [72.81, -44.38, -16.95]
  ],
  "channel_array_indices": [
    [0, 0],
    [0, 1]
  ]
}
```

### EEG Net CSV

Only the SimNIBS layout is read, the format of the nets in `m2m_<id>/eeg_positions/`: one row per position, `Type,X,Y,Z,Name[,…]`, with an optional header row (detected when its second column is not a number):

```csv
Type,X,Y,Z,Name
Electrode,-85.5,-28.9,-8.4,E1
ReferenceElectrode,0.0,85.0,0.0,REF
```

## Output Format

The tool generates a JSON file with the following structure:

```json
{
  "optimized_positions": [
    [-85.61, -29.0, -8.56],
    [72.81, -44.38, -16.95]
  ],
  "mapped_positions": [
    [-85.5, -28.9, -8.4],
    [72.9, -44.5, -17.1]
  ],
  "mapped_labels": ["E1", "E2"],
  "distances": [0.15, 0.12],
  "channel_array_indices": [
    [0, 0],
    [0, 1]
  ],
  "eeg_net": "EGI_template.csv"
}
```

## Mapping Distance and Target Depth

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/flex-search/mapping_distance.png" alt="Electrode Mapping Distance Analysis" style="width: 100%; max-width: 504px;">
</div>

**Mapping distance grows with target depth**: mapping flex-search positions onto the inner 185 electrodes of the GSN-HydroCel-256 net moved electrodes 11.74 ± 5.33 mm for the hippocampus, against 7.30 ± 1.38 mm for the insula and 8.01 ± 1.43 mm for spherical ROIs. Deep targets favour widely separated electrodes low on the head, where net coverage is sparse. _Data from the supplementary information of the [TI-Toolbox reference](<https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext>)._

## EEG Net Density Impact on Optimization Performance

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/other/net_density_impact.png" alt="Network Density Impact on TImax" style="width: 100%; max-width: 576px;">
</div>

**Impact of EEG net density on TImax intensity**: This analysis demonstrates the progressive decline in achievable TImax intensity as electrode density decreases. Starting from fully optimized electrode positions (theoretical maximum), the study shows how mapping to standardized EEG nets progressively reduces field strength: fully optimized positions achieve maximum intensity, followed by 10:5 density (high coverage), 10:10 system (standard density), and finally 10:20 system showing the greatest reduction. This highlights the trade-off between practical electrode accessibility and theoretical optimization performance.
