---
layout: wiki
title: Ex-Search TI Optimization Pipeline
permalink: /wiki/ex-search/
---

Ex-Search is the toolbox's **exhaustive** montage optimizer: it evaluates every electrode combination (× every current split) you allow, on a precomputed leadfield, and ranks the results. Unlike [Flex-Search]({{ site.baseurl }}/wiki/flex-search/), which freely positions electrodes on the scalp with a stochastic optimizer, ex-search is restricted to the electrodes of an EEG net — but within that space it is guaranteed to find the global optimum, and each candidate costs milliseconds.

## Prerequisites: Leadfield and EEG Net

Every ex-search runs against a leadfield matrix for one subject and one EEG net. An Ex job's settings dialog opens with a **Leadfield** strip: choose an **EEG net**, and the strip shows the leadfield's size if it exists, or "No leadfield for this net yet" and **Generate (≈ N min)**, which queues a leadfield job (the estimate is for that net on this machine, one FEM solve per electrode). A row with no net yet takes the subject's first computed leadfield, or the first net when none is computed. Leadfields are 2–20 GB depending on the number of electrodes. The nets are the ones pre-processing placed on the head model (see [Available EEG Nets]({{ site.baseurl }}/wiki/simulator/#available-eeg-nets)).

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_EEG10-20_Okamoto_2004_net.png" alt="EEG 10-20 Network">
    <em>EEG 10-20 Okamoto 2004 electrode configuration - widely used standard with 32 electrodes</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_GSN256_net.png" alt="GSN 256 Network">
    <em>GSN-HydroCel 256 electrode configuration - high-density net for precise targeting</em>
  </div>
</div>

Leadfields are generated with `tissues=[1, 2]` (white + grey matter).

## In the application

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/optimizer-page.png" alt="The Optimizer page: one job row whose Method column offers Flex or Ex, with the target region highlighted in the atlas pane" style="width: 100%; max-width: 1000px;">
  <em>Ex-search is the <strong>Ex</strong> method on the Optimizer page (⌘2), not a page of its own; the row shown uses Flex. An Ex row with eight electrodes runs mEx.</em>
</div>

Open an Ex job's settings from its row (the settings button, or double-click the row). The dialog has:

- **Leadfield**: the EEG net and its leadfield (see [above](#prerequisites-leadfield-and-eeg-net)).
- **Target**: **Subcortical**, **Saved** or **NIfTI mask** (see [Defining the Target](#defining-the-target-roi)).
- **Electrodes**: **Count** (4 electrodes for TI, 8 for mTI), **Search space** (**Bucketed** or **All combinations**) and the electrode buckets or pool (see [Defining the Search Space](#defining-the-search-space)). The line under the section counts the electrodes, montages, current splits and iterations.
- **Current**: **Total current**, **Step** and **Channel limit** (see [Current ratios](#current-ratios)). With 8 electrodes this section is **Carriers** instead (see [Multipolar (mTI) Mode](#multipolar-mti-mode)).

## Defining the Target (ROI)

The **Target** section offers three choices:

- **Saved** uses spherical ROIs saved for the subject: tick one or more, or create one with **Add ROI** (a new subject shows "No saved ROIs for this subject yet"). **Radius** sets the sphere (1–10 mm, default 3 mm) and **Space** says whether the centres are Subject or MNI coordinates. **Combine selected ROIs into one target** unions the selected spheres into a single Ex search; without it each selected ROI runs its own search.
- **Subcortical** selects regions from a volumetric atlas.
- **NIfTI mask** imports a local `.nii` or `.nii.gz` file into the project. Positive voxels define the target. Subject-space masks are used directly; MNI masks use the subject’s SimNIBS registration in `m2m_<subject>/toMNI`, with nearest-neighbor resampling. The conformation affine alone is not an MNI registration.

**Electrodes** is a separate section: set **Count** to four electrodes (TI) or eight (mTI), then configure the search space.

Under the hood, ROI resolution OR-folds a mixed list of CSV centers, whole NIfTI/MGZ masks (voxel value > 0), and `(path, label)` atlas-region selections (voxel value == label) into a single region.

## Defining the Search Space

### Bucketed

**Electrodes ▸ Search space ▸ Bucketed** pre-assigns electrodes to channel positions:

- **E1+**: Electrodes for positive channel 1
- **E1-**: Electrodes for negative channel 1
- **E2+**: Electrodes for positive channel 2
- **E2-**: Electrodes for negative channel 2

**Combinations**: $$N_1 \times N_2 \times N_3 \times N_4$$, where $$N_i$$ is the number of electrodes in bucket $$i$$.

### All combinations

**Electrodes ▸ Search space ▸ All combinations** pools the electrodes: any of them can be assigned to any channel position, with each electrode used only once per montage.

**Combinations**: $$\binom{N}{4} \times 4!$$, where $$N$$ is the total number of electrodes — every 4-electrode subset in every channel assignment.

**Trade-off**: Larger search space and longer compute time but with absolute certainty to find optimal solution with given electrode space.

### Symmetric (Bilateral) Constraint

Two-channel bucketed searches can be restricted to left/right-mirrored montages with `symmetric_bucket: true`, from Python or a JSON config only: the app has no control for it and always sends `false`. In the app, symmetry is offered for mEx only ([Multipolar (mTI) Mode](#multipolar-mti-mode)). The mirror map is read from the EEG-position CSV (`symmetry_eeg_csv`; inferred from the leadfield name `{subject}_leadfield_{net}.hdf5` when omitted). Two pairings:

- `symmetry_pairing: "within_pairs"` — each channel is bilateral: `E1-` must be the mirror of `E1+` and `E2-` of `E2+` (e.g. `F7_F8 <> TP7_TP8`). Write left candidates in the `+` buckets and their mirrors in the `-` buckets.
- `symmetry_pairing: "cross_pairs"` — channel 2 is the mirror of channel 1: `E2+ = mirror(E1+)`, `E2- = mirror(E1-)` (e.g. `F5_TP7 <> F6_TP8`).

### Current ratios

On top of the electrode combinations, the search systematically tests current splits between the two channels: the **Total current** divided in steps of **Step**, with neither channel above the **Channel limit**. The app starts at total 2.0 mA, step 0.2 mA and channel limit 1.6 mA; `ExConfig` defaults to total 2.0 mA, step 0.5 mA and no limit.

```
App defaults (total 2.0 mA, step 0.2 mA, limit 1.6 mA):
  (1.6, 0.4), (1.4, 0.6), (1.2, 0.8), (1.0, 1.0),
  (0.8, 1.2), (0.6, 1.4), (0.4, 1.6)
```

The line under **Electrodes** shows the montage count and the total iterations separately. For fixed balanced currents, set the channel limit to half the total current (with a step no larger than that half); there is one split and iterations equal montages.

**Total evaluations** = electrode combinations × current ratios. Each montage's two unit-current channel fields are computed once and rescaled per split — the FEM is linear, so a split costs almost nothing extra.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_ex-search_combos.png" alt="Example exhaustive-search electrode combinations" style="width: 100%; max-width: 850px;">
  <em>Example candidate electrode combinations. The final search size is determined by the selected pools or buckets, symmetry constraints, and current splits.</em>
</div>

## Running a Search

The app runs each Ex job as the module below in the container; the same works from a shell:

```
simnibs_python -m tit.opt.ex config.json
```

All computation is in-memory (no intermediate mesh files), with constant memory footprint regardless of combination count, real-time progress and ETA tracking, and graceful interruption: SIGINT/SIGTERM sets a stop flag that breaks after the current candidate, and partial results are still written. Candidates are spread over worker processes (`n_jobs`, default the **CPU limit** from **Settings ▸ Project ▸ Execution**, 70 % of the cores; larger values are capped at it). Run time ranges from minutes to hours depending on leadfield size and combination count.

## Outputs

### Metrics

Every evaluated candidate is scored on the closed-form two-channel TI envelope (`TI_max`; the math lives on the [Analyzer page]({{ site.baseurl }}/wiki/analyzer/#envelope-math-and-critical-values)). The ROI metrics use every leadfield element in the region, grey and white matter alike (the leadfield covers both); only `TImean_GM` is restricted to grey matter:

| Key               | Meaning                                                 |
| ----------------- | ------------------------------------------------------- |
| `TImax_ROI`       | Max over ROI elements                                   |
| `TImean_ROI`      | Volume-weighted mean over ROI elements                  |
| `TImean_GM`       | Volume-weighted mean over GM elements (SimNIBS tag `2`) |
| `Focality`        | `TImean_ROI / TImean_GM`                                |
| `Composite_Index` | `TImean_ROI × Focality`                                 |
| `n_elements`      | ROI element count                                       |

`Focality` here has the same definition as the analyzer's `roi_focality`, so search results and post-hoc analyses are directly comparable.

### Files

Each run writes to `derivatives/SimNIBS/sub-{id}/ex-search/{run_name}/`:

- `run_config.json` — provenance snapshot of the search configuration.
- `final_output.csv` — one row per evaluation. The `Montage` column carries the current split as a suffix (e.g. `F7_CP5 <> AF7_P3_I1-1.0mA_I2-1.0mA`); currents are written with one decimal, so a 0.25 mA step appears as 0.2/0.8/1.2/1.8 in the CSV.
- Five PNG figures: `montage_distributions.png` (histograms of TImax, TImean, focality), `intensity_vs_focality_scatter.png`, and three EEG-map figures — `electrode_score_heatmap.png` (electrode participation across the top-50 montages: colour = summed Composite Index, size = frequency), `montage_strength_map.png` and `montage_focality_map.png` (the top-150 montages drawn as arcs on the cap, coloured by `TImean_ROI` / `Focality`, best montage highlighted). The maps need the net's EEG-position CSV (resolved like `symmetry_eeg_csv`) and are skipped with a log line otherwise; regenerate them for an existing run with `simnibs_python -m tit.opt.ex.results <run_dir> [--eeg-csv CSV]`.

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/electrode_score_heatmap.png" alt="Electrode contribution heatmap">
    <em><code>electrode_score_heatmap.png</code> — which electrodes recur in the best montages (16,807-evaluation run)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/montage_strength_map.png" alt="Montage strength map">
    <em><code>montage_strength_map.png</code> — top-150 montages by ROI strength</em>
  </div>
</div>

## Example Results

_(example output from v2.4.0)_ Top 5 of 16,807 evaluations by `Composite_Index` (sub-ernie, EEG10-10 Jurak leadfield, 5 mm spherical ROI at MNI (−38, 5, 0)). Bucket search with 7 candidate electrodes per position (7⁴ = 2,401 electrode combinations) × 7 current splits (2 mA total, 0.25 mA step) — 13.6 min on 12 cores (0.05 s each):

| Montage           | Current_Ch1_mA | Current_Ch2_mA | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
| ----------------- | -------------- | -------------- | --------- | ---------- | --------- | -------- | --------------- |
| F7_TP9 <> F3_P1   | 1.0            | 1.0            | 0.3561    | 0.2066     | 0.0959    | 2.1553   | 0.4454          |
| F7_TP9 <> F3_PO3  | 1.0            | 1.0            | 0.3766    | 0.2103     | 0.1024    | 2.0545   | 0.4320          |
| FT7_TP9 <> FC3_P1 | 1.0            | 1.0            | 0.3637    | 0.1819     | 0.0771    | 2.3585   | 0.4291          |
| F7_TP7 <> F3_P3   | 1.0            | 1.0            | 0.3451    | 0.2109     | 0.1050    | 2.0091   | 0.4237          |
| F7_TP9 <> F3_O1   | 1.0            | 1.0            | 0.3766    | 0.2103     | 0.1047    | 2.0092   | 0.4225          |

![Ex-Search Distribution Analysis]({{ site.baseurl }}/assets/imgs/ex-search/ex-search_distribution.png)

_`montage_distributions.png` from the same run: TImax, TImean and focality across all 16,807 evaluations._

![Ex-Search Intensity vs Focality]({{ site.baseurl }}/assets/imgs/ex-search/intensity_vs_focality_scatter.png)

_`intensity_vs_focality_scatter.png`: every evaluation plotted as ROI mean intensity against focality, coloured by `Composite_Index`. With ~17k candidates the Pareto front emerges along the upper-right edge — no montage improves intensity without giving up focality beyond it. Equal 1.0/1.0 mA splits populate the high-intensity end; strongly unequal splits (0.2/1.8) collapse to the low-intensity cluster on the left._

### Symmetric example

_(example output from v2.4.0)_ `within_pairs`, 7 bilateral candidates per channel × 7 current splits = 343 evaluations on sub-ernie (18 s):

| Montage            | Ch1 mA | Ch2 mA | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
| ------------------ | ------ | ------ | --------- | ---------- | --------- | -------- | --------------- |
| FT7_FT8 <> TP7_TP8 | 0.8    | 1.2    | 0.4371    | 0.2290     | 0.1150    | 1.9909   | 0.4560          |
| FT7_FT8 <> CP5_CP6 | 0.8    | 1.2    | 0.4404    | 0.2285     | 0.1145    | 1.9949   | 0.4558          |
| F7_F8 <> TP7_TP8   | 0.8    | 1.2    | 0.3964    | 0.2021     | 0.0938    | 2.1540   | 0.4353          |

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/symmetric_montage_strength_map.png" alt="Symmetric ex-search montage strength map">
    <em>Top bilateral montages by ROI strength</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/symmetric_scatter.png" alt="Symmetric ex-search intensity vs focality">
    <em>Intensity vs focality, 343 evaluations</em>
  </div>
</div>

---

## Multipolar (mTI) Mode

Set **Electrodes ▸ Count ▸ 8 electrodes (mTI)** to run a multipolar exhaustive search (mEx) instead of the standard two-channel one: four pairs (eight electrodes), scored with the same verified multi-carrier envelope the simulator uses — explicitly **not** a recursive envelope-of-envelopes (see [Envelope Math]({{ site.baseurl }}/wiki/analyzer/#envelope-math-and-critical-values) on the Analyzer page for the $$K$$-carrier modulation-depth math, and [Multipolar Mode on the Simulator page]({{ site.baseurl }}/wiki/simulator/#multipolar-mode-mti) for how mTI montages are simulated). From Python it is `run_m_ex_search(MExConfig)`; see [Scripting]({{ site.baseurl }}/wiki/scripting/).

### mTI in the Optimizer

Choose the **Ex** method for a job row, open its settings and select **8 electrodes (mTI)**
under **Electrodes ▸ Count**. The default **4 electrodes (TI)** uses two channels. Selecting mTI:

- Uses eight electrode buckets, **E1+ … E4-**, from the leadfield's EEG net. mEx is bucket-only in the app; **All combinations** is offered for TI only.
- Replaces **Current** with **Carriers**: **Pair current**, the current of each of the four pairs (0.1–10 mA, default 2.0 mA per pair, i.e. 8 mA in total), and **Symmetry ▸ Force left/right symmetry** (off by default), which enables **Symmetry pairing**: **Within each pair** or **Cross pairs (E1↔E3, E2↔E4)**.
- Hides **Combine selected ROIs into one target**: the multipolar run path has no combined mode, so several selected saved ROIs run one search each. Saved spheres, subcortical regions and NIfTI masks all remain available as targets.
- Submits an `mex` job. Follow its Terminal log or stop it from Jobs.

### Candidate enumeration

- **Bucket mode** (the app's mode): the Cartesian product of the eight buckets, keeping only montages whose eight electrodes are distinct.
- **Pool mode** (Python or JSON only, `PoolElectrodes`): every 8-electrode subset, with one representative per group of montages the envelope scores identically (pairs swapped within a carrier, carriers swapped, and polarity flips that leave the envelope unchanged). A pool of exactly 8 electrodes yields 630 candidates, not $$8! = 40{,}320$$.
- **Symmetric bucket search** (**Force left/right symmetry**, `symmetric_bucket=True`, bucket mode only): only montages whose pairs mirror left/right, using a mirror map built from the net's EEG-position CSV (reflecting the x-coordinate across the midline). Two pairing schemes:
  - **Within each pair** (`within_pairs`, default): each pair's `-` electrode must mirror its `+` electrode.
  - **Cross pairs** (`cross_pairs`): pair 3 must mirror pair 1 and pair 4 must mirror pair 2. This replaces the within-pair rule; it does not add to it.

  Either way one electrode of each mirrored couple fixes the other, so for $$N$$ candidates per bucket the search shrinks from about $$N^8$$ to about $$N^4$$ montages.

### Scoring

Each candidate's four channel fields come from the leadfield at the pair current, and the score is their joint multi-carrier modulation depth. The metrics are those of two-channel ex-search ([Metrics](#metrics) above), with all four pairs at the same current. Targets are resolved as in two-channel ex-search.

### Outputs

mEx writes the same file set as ex-search to `derivatives/SimNIBS/sub-{id}/m-ex-search/{run_name}/`:

- `run_config.json` — provenance snapshot of the search configuration.
- `final_output.csv` — one row per evaluated candidate, in **enumeration order** (not sorted), with the same columns as two-channel ex-search; the `Montage` cell lists the four pairs (`F7_P7 <> F5_CP3 <> F3_P3 <> AF7_P9`). All four pairs carry the same current, so the two current columns stand for all four.
- The same five figures as two-channel ex-search, with four arcs per candidate on the montage maps; regenerate them for an existing run with `simnibs_python -m tit.opt.ex.results <run_dir>`.

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/mti/mex_electrode_score_heatmap.png" alt="mex-search electrode contribution heatmap">
    <em><code>electrode_score_heatmap.png</code>, 576-candidate run</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/mti/mex_montage_strength_map.png" alt="mex-search montage strength map">
    <em><code>montage_strength_map.png</code>, four arcs per candidate</em>
  </div>
</div>

Interruption and the failure on an empty candidate set behave exactly as in two-channel ex-search.

### Example run (sub-ernie, v2.4.0)

_(example output from v2.4.0)_ Bucket search with 3·3·2·2·2·2·2·2 candidate electrodes for `e1_plus` … `e4_minus` → **576 four-channel candidates**, Jurak 10-10 leadfield, 5 mm ROI at MNI (−38, 5, 0), `current_mA = 1.0`. Wall time 13.0 min on 12 cores (1.35 s per candidate).

| Best montages (by `Composite_Index`) | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
| ------------------------------------ | --------- | ---------- | --------- | -------- | --------------- |
| F7_P7 <> F5_CP3 <> F3_P3 <> AF7_P9   | 0.4769    | 0.3074     | 0.1571    | 1.9573   | 0.6017          |
| F7_TP7 <> F5_CP3 <> F3_P3 <> AF7_P9  | 0.4754    | 0.3009     | 0.1532    | 1.9641   | 0.5911          |
| F7_CP5 <> F5_CP3 <> F3_P3 <> AF7_P9  | 0.4810    | 0.3043     | 0.1572    | 1.9364   | 0.5893          |
| F7_P7 <> F5_P5 <> F3_CP1 <> F9_PO7   | 0.4699    | 0.3017     | 0.1568    | 1.9239   | 0.5804          |

![mex-search intensity vs focality, 576 candidates]({{ site.baseurl }}/assets/imgs/mti/mex_scatter_large.png)

_`intensity_vs_focality_scatter.png`: the 576 candidates trace the intensity–focality trade-off; the isolated low-intensity cluster on the left is the `T7`-anode family, the frontier on the upper right is where the `Composite_Index` maximum sits._

**Symmetric (bilateral) search** _(example output from v2.4.0)_. With `symmetric_bucket: true` and `symmetry_pairing: "within_pairs"` only left/right-mirrored channels are enumerated: each channel's minus electrode must be the mirror of its plus electrode (F7–F8, CP5–CP6, …), so the buckets are written as left candidates in `e{k}_plus` and their mirrors in `e{k}_minus`. Five bilateral candidates per channel → 5⁴ = 625 candidates, 13.9 min (1.33 s each):

| Best bilateral montages              | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
| ------------------------------------ | --------- | ---------- | --------- | -------- | --------------- |
| F7_F8 <> CP5_CP6 <> F1_F2 <> PO7_PO8 | 0.3910    | 0.2103     | 0.1074    | 1.9577   | 0.4117          |
| F7_F8 <> CP5_CP6 <> F1_F2 <> P9_P10  | 0.3920    | 0.2102     | 0.1073    | 1.9584   | 0.4117          |
| F5_F6 <> CP5_CP6 <> F1_F2 <> PO7_PO8 | 0.3915    | 0.2085     | 0.1057    | 1.9722   | 0.4113          |

![symmetric mex-search intensity vs focality]({{ site.baseurl }}/assets/imgs/mti/mex_scatter_symmetric.png)

_Bilateral montages reach ~⅔ of the ROI intensity of the unconstrained search for this left-lateral target (0.21 vs 0.31 V/m at similar focality) — the expected price of symmetry. `symmetry_pairing: "cross_pairs"` instead mirrors pair 1 onto pair 3 and pair 2 onto pair 4._

**Cost.** Scoring one four-channel candidate with the verified multi-carrier envelope is a per-element direction search, not a closed form like two-channel ex-search. It is evaluated on the ROI and grey matter only, with candidates spread over worker processes up to the global CPU limit: on a 12-core machine this is ~1–2 s per candidate, i.e. a few hundred candidates in ~10 min. The first run pays ~10 s of compilation, cached afterwards. There is no current-ratio sweep in mEx; every pair carries the same **Pair current**.

### Running it

```
simnibs_python -m tit.opt.mex config.json
```

The config is `MExConfig`; its fields are listed under [Scripting]({{ site.baseurl }}/wiki/scripting/).

_The multipolar exhaustive search was ported from collaborator Larissa Albantakis's branch `alba/ex-search-multipolar`._

## Scene pane

The pane follows the active job row:

- **Subcortical** targets are drawn, and clicking a region adds it to the target or removes it. A subject-space target is shown on the packaged reference head, because the subject's head model carries no copy of a volumetric atlas (the pane says which head it shows); an MNI-space target is shown on MNI152.
- **Saved** ROI and **NIfTI mask** targets are not drawn in the pane. It offers **Open target in TetraVox** instead, which opens the target on this subject in the TetraVox app.
- With an EEG net chosen, a Subcortical row's pane also draws that net's cap, each electrode coloured by the bucket it is in. Switch the pane's toolbar control from **Target** to **Electrodes**, and a click on an electrode adds it to or removes it from the active bucket: the one you last focused in the form or picked in the pane's bucket legend.

## Results

Open a finished Ex or mEx run in **Results ▸ Evaluated candidates**: a sortable table of every evaluated montage and a plot of ROI mean against focality (ROI mean / whole-GM mean). Selecting a candidate draws it on the subject's cap. **Use in Simulator** turns the selected candidate into an editable Montage row on the [Simulator]({{ site.baseurl }}/wiki/simulator/#ex-search-results-and-evaluated-candidates), with its electrodes, net and currents; nothing runs until you press **Run simulation**.

**Report.** Every Ex run writes an ex-search report: the winning montage's electrodes and dose, every montage's ROI mean against focality in one chart, the top 25 as a sortable table, and the ROI and ranking in words. Rebuild one without re-searching with `simnibs_python -m tit.reporting.generators.ex_search <project> <subject> <run name>`. mEx runs write no report. See [Reports]({{ site.baseurl }}/wiki/reports/).
