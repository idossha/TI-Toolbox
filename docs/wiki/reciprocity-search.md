---
layout: wiki
title: Reciprocity Search
permalink: /wiki/reciprocity-search/
---

Reciprocity Search is the toolbox's **instant** montage optimizer: it reads a montage straight out of a precomputed leadfield, with no FEM solve and no sweep. On ernie's thalamus it lands within 1% of the exhaustive optimum, and the search itself takes milliseconds.

## The idea

The reciprocity theorem says the leadfield column of electrode *i*, evaluated at your target, **is** the scalp potential a unit current dipole at that target would produce at electrode *i*. So the best bipolar pair for a target direction `d` is not something you search for — it is

```
best pair = argmax_i (F_i · d)  minus  argmin_i (F_i · d)
```

where `F_i` is electrode *i*'s field at the target. Every pair on the net is ranked in one vectorised subtraction. Because TI needs two or more channels, the top-ranked pairs are then combined — every combination that shares no electrode — and each combination is scored with the same verified envelope the other optimizers use (`tit.calc.get_TI_vectors`, Grossman's closed form at two channels, the multipolar envelope at four).

## When to use it

| | Cost per candidate | Search space | Use it when |
|---|---|---|---|
| [Flex-Search]({{ site.baseurl }}/wiki/flex-search/) | one FEM solve (minutes) | any scalp position | you want free placement and can spend hours |
| [Ex-Search]({{ site.baseurl }}/wiki/ex-search/) | milliseconds, but thousands of them | every montage on the net | you want the exhaustive optimum within a net |
| **Reciprocity Search** | milliseconds, a few hundred of them | the top-ranked pairs only | you want a good montage now, or a starting point to refine |

Reciprocity search is **not exhaustive by construction** — it only ever evaluates combinations of the `top_k` best-ranked pairs. Treat it as the fast first answer: run it, then confirm or refine with ex-search or a full simulation.

## What you give it

| Field | Meaning |
|---|---|
| `leadfield_hdf` | the same leadfield file ex-search uses (one subject, one EEG net) |
| `target` | either a **point** (`xyz`, `space` = subject or MNI, `radius_mm`) or an **ROI** — the same ROI object the other optimizers take: a `SphericalROI` or a `SubcorticalROI` (atlas + labels). A cortical `.annot` surface region is refused: the leadfield mesh holds volume elements only. |
| `direction` | leave empty to maximise the envelope in any direction, or give `[dx, dy, dz]` to maximise it along that axis |
| `objective` | **Intensity** (rank by ROI mean) or **Focality** (rank by `roi_mean^(1+w) / p95` of non-ROI grey matter, with weight *w*) |
| `n_channels` | 2 (TI) or 4 (mTI). The contract allows 2–4, but 3 is refused: the verified envelope is defined for an even number of channels. |
| `current_mA` | current per channel |
| `top_k` | how many reciprocity-ranked pairs to combine. Empty uses 40 (2 channels) or 20 (4 channels). At most 1 000 candidates are ever evaluated, worst-ranked first to go. |
| `gm_subsample` | grey-matter elements sampled outside the ROI for the background percentile (default 100 000, fixed seed) |

An ROI target uses the **mean** field over the ROI, never a single centroid element — in the validation study the centroid variant ranked 75th among candidate montages where the ROI-mean variant ranked 3rd.

## What you get

A run directory under `derivatives/SimNIBS/sub-<id>/recip-search/<run name>/`:

| File | Contents |
|---|---|
| `summary.json` | the config, the target centroid and element count, the winning montage, timings |
| `candidates.csv` | every evaluated montage, ranked, with `roi_mean`, `roi_max`, `roi_min`, `gm_mean`, `gm_p95`, `focality_tf` |
| `reciprocity_scores.csv` | every electrode pair's reciprocity score and rank, and whether it was kept |
| `montage.json` | the winning montage's electrodes and currents |
| `run_config.json`, `final_output.csv` | the ex-search shape, so the run lists in Results and replays into the Simulator like an ex run |
| `fig1_reciprocity_topomap.png` | the reciprocity map over the cap, with the chosen pairs drawn on it |
| `fig2_candidate_landscape.png` | where the winner sits among the evaluated candidates |
| `fig3_summary.png` | ROI intensity against background for the top montages |

The metrics are **leadfield estimates with point electrodes**, exactly like ex-search's — good for ranking montages against each other, not a substitute for a full simulation. The background percentile comes from the grey-matter subsample, not from every element.

## Worked example: ernie's thalamus

Subject `ernie`, net EEG10-10 (76 electrodes, 2 850 pairs, reference Cz), target both thalami (`labeling.nii.gz`, labels 10 and 49), 2 channels at 1 mA each, no direction constraint.

The target resolves to 14 484 mesh elements, centroid `(2.2, 10.4, 17.3)` mm. The whole run — reading the leadfield for the 114 484 evaluation elements, ranking all 2 850 pairs, and scoring every montage — takes **36 s** end to end in the v3.0.0 container on an emulated Apple-silicon Mac:

| Stage | Time |
|---|---|
| leadfield subset read (114 484 elements × 76 electrodes) | 19.3 s |
| reciprocity map over 2 850 pairs | **0.021 s** |
| 580 two-channel candidates evaluated | 11.2 s (0.019 s each) |

Top of `candidates.csv`, at 1 mA per channel:

| Rank | Montage | ROI mean | ROI max | non-ROI GM p95 |
|---|---|---|---|---|
| 1 | Fz–I1 / F2–Iz | **246.7 mV/m** | 619.3 mV/m | 292.9 mV/m |
| 2 | Fz–Iz / F2–I2 | 245.9 mV/m | 575.6 mV/m | 292.1 mV/m |
| 3 | Fz–I1 / F2–I2 | 244.9 mV/m | 584.8 mV/m | 283.2 mV/m |

The exhaustive search over all 2 850 pairs on the same leadfield finds 246.7 mV/m — the same montage family, after minutes of sweeping instead of 11 seconds.

Two variations on the same target:

- **Focality** (weight 0.5) picks F1–I1 / F2–PO10 instead: ROI mean 235.1 mV/m with the background p95 down to 260.5 mV/m — less dose in the target, less everywhere else.
- **Four channels** (mTI, default `top_k` = 20 → 150 disjoint montages, 24.9 s) picks F2–I1 / Fz–PO9 / AFz–I2 / F1–Iz at 339.1 mV/m ROI mean, 388.4 mV/m background p95.

## Related

- [Ex-Search]({{ site.baseurl }}/wiki/ex-search/) — the exhaustive optimizer over the same leadfield
- [Flex-Search]({{ site.baseurl }}/wiki/flex-search/) — free electrode placement
- [Simulator]({{ site.baseurl }}/wiki/simulator/) — run the chosen montage as a full simulation
