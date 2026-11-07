---
layout: wiki
title: Network analysis
permalink: /wiki/tractography-analysis/
---

Two ways to read a TI field along a network's streamlines: assess one simulation, or rank the montages of an ex-search run. Every quantity is a field descriptor, not a prediction of activation, and none is marked as preferred.

## What you need

- The subject's [tractography]({{ site.baseurl }}/wiki/tractography/).
- To assess: a simulation of the subject. To rank: a two-channel ex-search run and a [network mask]({{ site.baseurl }}/wiki/tractography-targets/).

## Assess a simulation

On **Extensions ▸ 3D visual exporter ▸ Networks**, press **Assess connections**. It samples the simulation's fields along every streamline. It also runs by itself when a [render]({{ site.baseurl }}/wiki/tractography-renders/) needs it.

The outputs are in `Simulations/<sim>/tract/`:

| File | Contents |
|---|---|
| `all.trx` | Streamlines with the fields along them, about 0.4 GB at 200,000 seeds |
| `edges.json` | Each edge's regions, streamline count and summary statistics |
| `connectome_<metric>.npz` | One region-by-region matrix per metric |
| `summary.json`, `streamline_metrics.npz`, `profiles.npz` | Whole-run summary, per-streamline values, per-edge profiles along the tract |

## Rank an ex-search run

On **Results**, open a two-channel ex-search run and use **Rank on a network**: choose one of the subject's current network masks and the montages to score, then press **Rank montages**. All montages of the run is the default, shown with the count and an estimated time. Top N by composite index is quicker, and can leave out what this ranking would put first.

The table shows each quantity's median over streamlines of each streamline's mean, its mean over all points, and the ranks by `ti_along` and by `ti_max`. Every row is in `tractography/ranking_<name>.csv`.

## The quantities

`t` is the streamline's unit tangent at a point, and `E1`, `E2` are the two channels' fields.

| Name | Definition | Units |
|---|---|---|
| `ti_along` | The TI envelope of the channel fields along `t`. For two channels, `2 min(\|E1·t\|, \|E2·t\|)` | V/m |
| `ti_max` | The envelope's maximum over all directions | V/m |
| `ti_avg` | The envelope averaged over all directions | V/m |
| `align_index` | `ti_along / ti_avg`, per streamline as the ratio of their arc-length means. Above 1, more envelope along the streamline than along a random direction | none |
