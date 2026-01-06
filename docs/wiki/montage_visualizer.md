---
layout: wiki
title: Montage Visualizer
permalink: /wiki/montage_visualizer/
---

The Montage Visualizer is a tool for creating visual representations of electrode montages on EEG net images. It supports both unipolar and multipolar temporal interference (TI) stimulation configurations. It is automatically integrated as part of the simulation pipeline of the TI-Toolbox.

## Simulation Modes

Unipolar montages use **4 electrodes** arranged in **2 channels**. 

![Unipolar Montage Example]({{ site.baseurl }}/assets/imgs/simulator/unipolar.png)

Multipolar montages use **8 electrodes** arranged in **4 channels**.

![Multipolar Montage Example]({{ site.baseurl }}/assets/imgs/simulator/multipolar.png)

## Supported EEG Networks

- **GSN-HydroCel Systems**: GSN-HydroCel-185.csv, GSN-HydroCel-256.csv
- **10-10 Systems**: EEG10-10_UI_Jurak_2007.csv, EEG10-10_Cutini_2011.csv, EEG10-20_Okamoto_2004.csv, EEG10-10_Neuroelectrics.csv

## Visual Features

### Electrode Rings
- **Size**: 40px radius rings centered on electrode positions
- **Colors**: 8 distinct professional colors (blue, red, green, purple, orange, cyan, chocolate, violet)
- **Design**: Hollow circles with 6px stroke width for clear visibility

### Connection Lines
- **Style**: Smooth quadratic Bezier curves forming natural arches
- **Color**: Matches corresponding electrode ring colors
- **Width**: 3px stroke
- **Offset**: Lines start/end 15px away from electrode centers to avoid overlap