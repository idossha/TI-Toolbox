---
layout: wiki
title: Montage Visualizer
permalink: /wiki/montage_visualizer/
---

The Montage Visualizer (`tit/tools/montage_visualizer.py`) draws a montage's electrodes on a top-down EEG-cap diagram. It runs automatically after every simulation on a supported net; the PNG is written next to the simulation outputs, and the same picture is the cap figure in the [simulation report]({{ site.baseurl }}/wiki/reports/).

## Simulation Modes

Unipolar (standard TI) montages use **4 electrodes** arranged in **2 channels**. One image is written per montage:

![Unipolar Montage Example]({{ site.baseurl }}/assets/imgs/simulator/unipolar.png)

_Channel 1 (E1+ `E034`, E1- `E020`) and channel 2 (E2+ `E095`, E2- `E070`) on the GSN-HydroCel-185 net._

Multipolar (mTI) montages use **8 or more electrodes** arranged in **4 or more channels** and are drawn as a single combined image:

![Multipolar Montage Example]({{ site.baseurl }}/assets/imgs/simulator/multipolar.png)

_Four channels: channels 1 and 2 (blue/red) beat together, as do channels 3 and 4 (green/purple)._

## Output Location

```
derivatives/SimNIBS/sub-{ID}/Simulations/{montage}/
├── TI/montage_imgs/{montage}_highlighted_visualization.png     # unipolar
└── mTI/montage_imgs/combined_montage_visualization.png         # multipolar
```

## Supported EEG Networks

Every supported net is drawn on one diagram, `resources/amv/GSN-256.png`, through one of two label-to-pixel maps:

| Map          | EEG nets                                                                                                             |
| ------------ | -------------------------------------------------------------------------------------------------------------------- |
| `GSN-256.csv` | `GSN-HydroCel-185.csv`, `GSN-HydroCel-256.csv`                                                                       |
| `10-10.csv`  | `EEG10-10_UI_Jurak_2007.csv`, `EEG10-10_Cutini_2011.csv`, `EEG10-20_Okamoto_2004.csv`, `EEG10-10_Neuroelectrics.csv` |

Any other net has no map, so its simulations get no PNG: the log records a warning, and the simulation report lists the channels without a cap figure. That includes caps TI-Toolbox ships (`GSN-HydroCel-128`, `BioSemi-64-10-10`, `BioSemi-128-A1`, `BioSemi-256-A1`), `easycap_BC_TMS64_X21`, `EEG10-20_extended_SPM12`, caps you added yourself, and free-hand or flex-search XYZ montages, which have no net labels.

## Reading the image

Channel k is made of electrodes Ek+ and Ek-. Each channel has its own colour: a ring on each of its two electrodes and an arc between them. The arc bows toward the channel's partner (channel 1 toward channel 2, channel 3 toward channel 4), so the two channels that beat together face each other.

The legend in the bottom-left corner names the channels in montage order: `Channel 1`, `Channel 2`, and so on. The [simulation report]({{ site.baseurl }}/wiki/reports/) lists the same channels in the same colours.

## Calling It Directly

```python
from tit.tools.montage_visualizer import visualize_montage

visualize_montage(
    montage_name="my_montage",
    electrode_pairs=[["E034", "E020"], ["E095", "E070"]],
    eeg_net="GSN-HydroCel-185.csv",
    output_dir="/mnt/my_project/derivatives/scratch",
    sim_mode="U",          # "U" = one image per montage, "M" = combined image
)
```

ImageMagick (`convert`) is required; it is included in the TI-Toolbox container.
