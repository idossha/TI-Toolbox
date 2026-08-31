---
layout: wiki
title: Ex-Search TI Optimization Pipeline
permalink: /wiki/ex-search/
---

The Ex-Search module provides a high-performance, exhaustive search approach for Temporal Interference (TI) simulations. The public API is `run_ex_search(config: ExConfig) -> ExResult`.

## Overview

Ex-Search implements a true **exhaustive search** approach for Temporal Interference (TI) optimization, systematically evaluating all possible electrode combinations within user-defined constraints. Unlike sampling-based methods, ex-search guarantees finding the globally optimal montage configuration.

The implementation uses a single `ExSearchEngine` class that owns the full pipeline: leadfield loading, ROI resolution, TI field computation, and the simulation loop.

**Key Features:**

- **True Exhaustive Search**: Evaluates all electrode combinations x current ratios
- **Multiple EEG Nets**: Support for high-density (10:10) and 10-20 nets with automatic co-registration
- **ROI Analysis**: Spherical ROI definition (CSV centers, default radius 3mm) in subject or MNI coordinate space (`roi_coordinate_space`), plus volumetric atlas-region ROIs (`ExConfig.roi_atlas`) that can stand alone via an explicit empty `roi_names=[]`
- **Current Ratio Optimization**: Systematic testing of current ratios respecting channel limits
- **High-Performance Processing**: Memory-efficient in-memory calculations with real-time progress tracking
- **Comprehensive Metrics**: TImax, TImean, Focality analysis with automatic visualization

## User Interface

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/UI/UI_ex.png" alt="Flex Search Interface" style="width: 80%; max-width: 700px;">
</div>

The interface provides controls for:

- **Subject Selection**: Choose from available subjects with automatic leadfield scanning
- **Leadfield Management**: View existing leadfields, create new ones, and show electrode configurations
- **ROI Selection**: A ROI Type toggle picks between two alternative targeting mechanisms, not companions -- **Sphere** (default) uses one or more spherical ROI CSVs sized by ROI Radius, with a Coordinate Space toggle (Subject / MNI, MNI space asks for confirmation before the run) and a "Combine selected ROIs into one target" checkbox that unions the selected ROIs into a single search (output named by joining the ROI names with `+`); **Atlas** targets a volumetric subcortical atlas region on its own page, backed by the same ROI picker widget used elsewhere in the GUI, restricted to its subcortical mode. Choosing Atlas mode drops the spherical ROI entirely (`roi_names=[]`); choosing Sphere mode drops the atlas target entirely (`roi_atlas=None`)
- **Electrode Setup**: Configure E1+, E1-, E2+, E2- with support for both GSN and 10-20 formats
- **Execution Control**: Run optimization with real-time progress tracking

Atlas ROI targets are always resolved in the subject's own space -- the picker has no MNI option here, because `ExConfig.AtlasROI` has no `atlas_space` field and the engine tests element barycenters against the mask directly. `roi_name` is required even in Atlas-only mode: it is the metric-key prefix and (with the net name) part of the output-directory label, so the GUI synthesizes one from the selected atlas label(s), e.g. `atlas_17` for a single region or `atlas_17_53` when more than one is selected.

## Search Modes

Ex-Search supports two electrode assignment strategies:

### Bucketed Mode

Electrodes are pre-assigned to specific channels:

- **E1+**: Electrodes for positive channel 1
- **E1-**: Electrodes for negative channel 1
- **E2+**: Electrodes for positive channel 2
- **E2-**: Electrodes for negative channel 2

**Combinations**: $$N_1 \times N_2 \times N_3 \times N_4$$, where $$N_i$$ is the number of electrodes in bucket $$i$$.

### Pooled Mode

All electrodes are pooled together and can be assigned to any channel position, with the constraint that each electrode is used only once per montage.

**Combinations**: $$\binom{N}{4} \times 4!$$, where $$N$$ is the total number of electrodes -- every 4-electrode subset in every channel assignment.

**Trade-off**: Larger search space and longer compute time but with absolute certainty to find optimal solution with given electrode space.

### Symmetric (Bilateral) Constraint

Bucketed searches can be restricted to left/right-mirrored montages with `symmetric_bucket: true` (pool mode raises an error). The mirror map is read from the EEG-position CSV (`symmetry_eeg_csv`; inferred from the leadfield name `{subject}_leadfield_{net}.hdf5` when omitted). Two pairings:

- `symmetry_pairing: "within_pairs"` — each pair is bilateral: `E1-` must be the mirror of `E1+` and `E2-` of `E2+` (e.g. `F7_F8 <> TP7_TP8`). Write left candidates in the `+` buckets and their mirrors in the `-` buckets.
- `symmetry_pairing: "cross_pairs"` — pair 2 is the mirror of pair 1: `E2+ = mirror(E1+)`, `E2- = mirror(E1-)` (e.g. `F5_TP7 <> F6_TP8`).

A configuration whose buckets contain no mirrored partners now fails **before the leadfield is loaded** with a message naming the bucket and the mirror map, and no run directory is created (the same applies to any search that enumerates zero candidates, e.g. empty buckets or a pool with fewer than four electrodes).

Example — `within_pairs`, 7 bilateral candidates per pair × 7 current splits = 343 evaluations on sub-ernie (18 s):

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

Set **Search Mode** to _mTI (4-pair)_ to run a multipolar exhaustive search (mex-search) instead of the standard two-pair one. `tit/opt/mex/` extends ex-search to four bipolar pairs (eight electrodes), scored with the same verified `get_mTI_vectors` envelope used by the simulator -- explicitly **not** a recursive envelope-of-envelopes (see [Envelope Math]({{ site.baseurl }}/wiki/analyzer/#envelope-math-and-critical-values) on the Analyzer page for the K-pair modulation-depth math, and [Multipolar Mode on the Simulator page]({{ site.baseurl }}/wiki/simulator/#multipolar-mode-mti) for how mTI montages are detected and simulated). The public API is `run_m_ex_search(config: MExConfig) -> MExResult`, re-exported from `tit.opt` alongside `run_ex_search`/`run_flex_search`.

### mTI GUI

The Ex-Search tab hosts both TI and mTI search behind a single **Search Mode** combo: "TI (2-pair)" (default) and "mTI (4-pair)". Selecting mTI:

- Hides the Bucketed/All Combinations radio buttons and switches the electrode panel to eight free-text fields, **E1+ .. E4-** (2 columns x 4 rows). mTI is bucket-only -- there is no all-combinations page, since pool permutations over eight positions are combinatorially far larger than TI's four.
- Switches the current-configuration panel to a **Pair Current (mA)** spinbox (range 0.1-10.0, default 2.0, step 0.1), a **Carrier Wiring** combo (the two `MTI_CHANNEL_ARCHITECTURES` choices from [Carrier Wiring on the Simulator page]({{ site.baseurl }}/wiki/simulator/#carrier-wiring-channels)), and a **Force left/right symmetry** checkbox (unchecked by default) that enables a symmetry-pairing combo -- "Within each pair" / "Cross pairs (E1<->E3, E2<->E4)" -- once checked.
- Disables the **Combine ROIs** checkbox only. Both ROI types are available: `MExConfig` carries `roi_names` and `roi_atlas` exactly as `ExConfig` does, so an mTI run can target a sphere, an atlas region, or an atlas region alone. Combining stays TI-only because the multipolar run path processes selected spheres one at a time.
- Retitles the box "mTI Configuration" and relabels the run/stop buttons "Run mTI Search"/"Stop mTI Search".

The shared **ROI Radius** spinbox (range 1.0-10.0 mm, default 3.0) applies to both modes.

Validation before an mTI run requires all eight bucket fields to be non-empty ("Please enter valid electrodes for all eight mTI bucket categories (E1..E4, +/-)"), plus at least one ROI selected. The confirmation dialog reports per-bucket electrode counts, pair current, carrier wiring, an upper-bound search-space size (`Search Space: up to <product of the 8 bucket sizes> eight-electrode combinations`, before the distinctness filter), and the ROI list.

### Configuration

`MExConfig` required fields (no defaults):

| Field | Type |
|---|---|
| `subject_id` | `str` |
| `leadfield_hdf` | `str` |
| `roi_name` | `str` |
| `electrodes` | `MExConfig.BucketElectrodes` or `MExConfig.PoolElectrodes` |

Optional fields and their exact defaults:

| Field | Default |
|---|---|
| `current_mA` | `2.0` (mA on every pair) |
| `channels` | `None` (positional pairing; see [Carrier Wiring]({{ site.baseurl }}/wiki/simulator/#carrier-wiring-channels)) |
| `roi_radius` | `3.0` mm |
| `roi_names` | `None` (single-ROI behaviour driven by `roi_name`; an explicit `[]` means no spherical centers at all, which is what a purely atlas-driven target needs) |
| `roi_atlas` | `None` |
| `roi_coordinate_space` | `"subject"` (or `"mni"`) |
| `run_name` | `None` (defaults to a `%Y%m%d_%H%M%S` timestamp) |
| `symmetric_bucket` | `False` |
| `symmetry_eeg_csv` | `None` |
| `symmetry_pairing` | `"within_pairs"` (or `"cross_pairs"`) |

`current_mA <= 0` raises `ValueError`. `symmetric_bucket=True` with `PoolElectrodes` raises `ValueError` (symmetric search only supports bucket mode).

`MExConfig.BucketElectrodes` has exactly eight `list[str]` fields, in this order: `e1_plus`, `e1_minus`, `e2_plus`, `e2_minus`, `e3_plus`, `e3_minus`, `e4_plus`, `e4_minus`. `MExConfig.PoolElectrodes` has a single field, `electrodes: list[str]`.

### Candidate enumeration

- **Bucket mode** (default): the full Cartesian product of the eight buckets, keeping only tuples where all 8 electrode names are distinct (`len(set(electrodes)) == 8`).
- **Pool mode** (`PoolElectrodes`, `all_combinations=True`): `itertools.permutations(pool, 8)`. A pool of exactly 8 electrodes yields $$8! = 40{,}320$$ candidates.
- **Symmetric bucket search** (`symmetric_bucket=True`, bucket mode only): restricts candidates to those whose pairs mirror left/right, using a mirror map built from an EEG-position CSV (reflecting the x-coordinate across the midline). Two pairing schemes:
  - `within_pairs` (default): each pair's own `+`/`-` electrodes must mirror each other.
  - `cross_pairs`: additionally requires pair 1 <-> pair 3 and pair 2 <-> pair 4 to mirror.

  This collapses the search space roughly to linear in bucket size instead of the full Cartesian product.

### Scoring

For each candidate, the engine computes four leadfield fields via `TI.get_field([e_a, e_b, current_mA/1000.0], leadfield, idx_lf)` (mA converted to A), takes `vectors = get_mTI_vectors(fields, channels=config.channels)`, and scores `np.linalg.norm(vectors, axis=1)`. Per-candidate metrics (ROI-name-prefixed):

| Key | Meaning |
|---|---|
| `{roi}_TImax_ROI` | Max over ROI elements |
| `{roi}_TImean_ROI` | Volume-weighted mean over ROI elements |
| `{roi}_TImean_GM` | Volume-weighted mean over GM elements (SimNIBS tag `2`) |
| `{roi}_Focality` | `TImean_ROI` / `TImean_GM` (`0.0` if the GM mean is $$\le 0$$) |
| `{roi}_n_elements` | ROI element count |
| `current_ch1_mA` .. `current_ch4_mA` | All four set to the same `current_mA` |

If the ROI has zero elements, all four metrics are `0.0`. ROI resolution (spherical CSV centers, NIfTI/MGZ masks, atlas label selections) is inherited wholesale from the ex-search engine.

### Outputs

mex-search reuses ex-search's output pipeline, writing the following files to `derivatives/SimNIBS/sub-{id}/m-ex-search/{run_name}/`:

- `run_config.json` -- subject_id, roi_name, roi_radius, leadfield_hdf, electrode_mode (`"pool"` or `"bucket"`), electrodes, n_combinations, run_name, current_mA.
- `final_output.csv` -- one row per evaluated candidate, in **enumeration order** (not sorted). Fixed 8-column header: `Montage, Current_Ch1_mA, Current_Ch2_mA, TImax_ROI, TImean_ROI, TImean_GM, Focality, Composite_Index`, where `Composite_Index = TImean_ROI * Focality`. Currents are formatted to 1 decimal, metrics to 4. The Montage cell strips the `TI_field_`/`.msh` wrapper from the candidate key and replaces `_and_` with ` <> `.

  Note: the engine computes `current_ch3_mA`/`current_ch4_mA` too, but the CSV header has no columns for them -- only Ch1/Ch2 currents are recorded (both ex-search and mex-search share this fixed-width CSV writer).
- `montage_distributions.png` -- three histograms (dpi=300).
- `intensity_vs_focality_scatter.png` (dpi=300).
- `electrode_score_heatmap.png`, `montage_strength_map.png`, `montage_focality_map.png` -- EEG-map figures (electrode participation across the top-50 candidates; top-150 candidates drawn as four arcs each, coloured by ROI strength / focality). Written when the net's EEG-position CSV can be resolved (`symmetry_eeg_csv` or inferred from the leadfield name); regenerate for an existing run with `simnibs_python -m tit.opt.ex.results <run_dir>`.

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

A search that enumerates zero candidates (e.g. symmetric buckets without mirrored partners) fails before the leadfield is loaded, with a message naming the cause, and creates no run directory.

The candidate key/name format is `TI_field_{e1a}_{e1b}_and_{e2a}_{e2b}_and_{e3a}_{e3b}_and_{e4a}_{e4b}_I-{current_mA:.1f}mA.msh` -- no mesh file is actually written; it is only a label. Progress is logged per candidate plus a coarse estimate every 500 candidates, since bucketed 4-pair searches can reach hundreds of thousands of combinations. SIGINT/SIGTERM sets a stop flag that breaks after the current candidate, and partial results are still written.

### Example run (sub-ernie, v2.4.0)

Bucket search with 3·3·2·2·2·2·2·2 candidate electrodes for `e1_plus` … `e4_minus` → **576 four-pair candidates**, Jurak 10-10 leadfield, 5 mm ROI at MNI (−38, 5, 0), `current_mA = 1.0`, `channels = null` (two independent channels). Wall time 13.0 min on 12 cores (1.35 s per candidate with the numba kernel and the worker pool).

| Best montages (by `Composite_Index`) | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
|---|---|---|---|---|---|
| F7_P7 <> F5_CP3 <> F3_P3 <> AF7_P9 | 0.4769 | 0.3074 | 0.1571 | 1.9573 | 0.6017 |
| F7_TP7 <> F5_CP3 <> F3_P3 <> AF7_P9 | 0.4754 | 0.3009 | 0.1532 | 1.9641 | 0.5911 |
| F7_CP5 <> F5_CP3 <> F3_P3 <> AF7_P9 | 0.4810 | 0.3043 | 0.1572 | 1.9364 | 0.5893 |
| F7_P7 <> F5_P5 <> F3_CP1 <> F9_PO7 | 0.4699 | 0.3017 | 0.1568 | 1.9239 | 0.5804 |

![mex-search intensity vs focality, 576 candidates]({{ site.baseurl }}/assets/imgs/mti/mex_scatter_large.png)

*`intensity_vs_focality_scatter.png`: the 576 candidates trace the intensity–focality trade-off; the isolated low-intensity cluster on the left is the `T7`-anode family, the frontier on the upper right is where the `Composite_Index` maximum sits.*

**Symmetric (bilateral) search.** With `symmetric_bucket: true` and `symmetry_pairing: "within_pairs"` only left/right-mirrored pairs are enumerated: each pair's minus electrode must be the mirror of its plus electrode (F7–F8, CP5–CP6, …), so the buckets are written as left candidates in `e{k}_plus` and their mirrors in `e{k}_minus`. The mirror map is derived from the leadfield's EEG-position CSV (`symmetry_eeg_csv`, inferred from `{subject}_leadfield_{net}.hdf5` when omitted). Five bilateral candidates per pair → 5⁴ = 625 candidates, 13.9 min (1.33 s each):

| Best bilateral montages | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
|---|---|---|---|---|---|
| F7_F8 <> CP5_CP6 <> F1_F2 <> PO7_PO8 | 0.3910 | 0.2103 | 0.1074 | 1.9577 | 0.4117 |
| F7_F8 <> CP5_CP6 <> F1_F2 <> P9_P10 | 0.3920 | 0.2102 | 0.1073 | 1.9584 | 0.4117 |
| F5_F6 <> CP5_CP6 <> F1_F2 <> PO7_PO8 | 0.3915 | 0.2085 | 0.1057 | 1.9722 | 0.4113 |

![symmetric mex-search intensity vs focality]({{ site.baseurl }}/assets/imgs/mti/mex_scatter_symmetric.png)

*Bilateral montages reach ~⅔ of the ROI intensity of the unconstrained search for this left-lateral target (0.21 vs 0.31 V/m at similar focality) — the expected price of symmetry; `symmetry_pairing: "cross_pairs"` additionally mirrors pair 1↔3 and 2↔4.*

**Effect of carrier wiring.** Re-running a 16-candidate subset with `channels = [[[0,2],[1,3]]]` (four pairs sharing two carriers) keeps the same ranking but raises the envelope ~1.45× (best montage `F7_P7 <> F5_CP3 <> F3_P3 <> AF7_P9`: TImean_ROI 0.307 → 0.444 V/m, focality 1.96 → 1.78). This is why `channels` must be chosen deliberately (see [Carrier Wiring]({{ site.baseurl }}/wiki/simulator/#carrier-wiring-channels)).

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_independent.png" alt="mex-search, independent channels (16 candidates)">
    <em>Independent channels (16 candidates)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_twocarrier.png" alt="mex-search, two carriers (16 candidates)">
    <em>Four pairs, two carriers (same 16)</em>
  </div>
</div>

**Cost.** Scoring one 4-pair candidate with the verified N>2 envelope is a per-element direction search (192-direction sweep plus local refinement), not a closed form like 2-pair ex-search. The search is evaluated on ROI ∪ GM only by a fused numba kernel (`tit/_mti_kernel.py`, all cores) and candidates are distributed over forked worker processes (`n_jobs`, default all cores − 1): on a 12-core machine this is ~1–2 s per candidate, i.e. a few hundred candidates in ~10 min. The first call pays ~10 s of JIT compilation, cached afterwards. There is no current-ratio sweep in mex-search; each run uses a single `current_mA`.

### Running it

```
simnibs_python -m tit.opt.mex config.json
```

JSON config keys: `project_dir`, `subject_id`, `leadfield_hdf`, `roi_name`, `electrodes` (`_type`: `"BucketElectrodes"` or `"PoolElectrodes"`, plus `e1_plus`..`e4_minus` or `electrodes`), `current_mA`, `channels`, `roi_radius`, `roi_names`, `roi_atlas`, `roi_coordinate_space`, `run_name`, `n_jobs` (worker processes, default −1 = all cores − 1), `symmetric_bucket`, `symmetry_eeg_csv`, `symmetry_pairing`.

```json
{
  "project_dir": "/path/to/project",
  "subject_id": "101",
  "leadfield_hdf": "101_leadfield_EEG10-20_Okamoto_2004.hdf5",
  "roi_name": "L-Insula.csv",
  "electrodes": {
    "_type": "BucketElectrodes",
    "e1_plus": ["Fp1", "Fp2"],
    "e1_minus": ["Pz", "Oz"],
    "e2_plus": ["C3", "F3"],
    "e2_minus": ["C4", "F4"],
    "e3_plus": ["T7", "T8"],
    "e3_minus": ["O1", "O2"],
    "e4_plus": ["Fz", "Cz"],
    "e4_minus": ["P3", "P4"]
  },
  "current_mA": 2.0,
  "roi_radius": 3.0
}
```

*The multipolar exhaustive search combination logic (`tit/opt/mex/logic.py`) and the generalized electrode-bucket loader (`tit/opt/ex/buckets.py`) were ported from collaborator Larissa Albantakis's branch `alba/ex-search-multipolar`.*

---

## Supported EEG Nets

Ex-Search automatically detects and supports multiple EEG electrode configurations:  
(EEG nets autoamtically co-registered during pre-processing)

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

---

**Example Results** (`final_output.csv`, top 5 of 16,807 evaluations by `Composite_Index`; sub-ernie, EEG10-10 Jurak leadfield, 5 mm spherical ROI at MNI (−38, 5, 0), TI-Toolbox v2.4.0). Bucket search with 7 candidate electrodes per position (7⁴ = 2,401 electrode combinations) × 7 current splits (2 mA total, 0.25 mA step). Each montage's two unit-current channel fields are computed once and rescaled per split, candidates are spread over worker processes (`n_jobs`, default all cores − 1), and the closed-form TI maximum is evaluated on ROI ∪ grey matter only — the 16,807 evaluations took 13.6 min on 12 cores (0.05 s each):

| Montage           | Current_Ch1_mA | Current_Ch2_mA | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
| ----------------- | -------------- | -------------- | --------- | ---------- | --------- | -------- | --------------- |
| F7_TP9 <> F3_P1   | 1.0            | 1.0            | 0.3561    | 0.2066     | 0.0959    | 2.1553   | 0.4454          |
| F7_TP9 <> F3_PO3  | 1.0            | 1.0            | 0.3766    | 0.2103     | 0.1024    | 2.0545   | 0.4320          |
| FT7_TP9 <> FC3_P1 | 1.0            | 1.0            | 0.3637    | 0.1819     | 0.0771    | 2.3585   | 0.4291          |
| F7_TP7 <> F3_P3   | 1.0            | 1.0            | 0.3451    | 0.2109     | 0.1050    | 2.0091   | 0.4237          |
| F7_TP9 <> F3_O1   | 1.0            | 1.0            | 0.3766    | 0.2103     | 0.1047    | 2.0092   | 0.4225          |

`Focality = TImean_ROI / TImean_GM` and `Composite_Index = TImean_ROI × Focality`. The `Montage` column in the CSV also carries the current split as a suffix (e.g. `F7_CP5 <> AF7_P3_I1-1.0mA_I2-1.0mA`). Currents are written with one decimal, so a 0.25 mA step appears as 0.2/0.8/1.2/1.8 in the CSV.

![Ex-Search Distribution Analysis]({{ site.baseurl }}/assets/imgs/ex-search/ex-search_distribution.png)

_`montage_distributions.png` from the same run: TImax, TImean and focality across all 16,807 evaluations._

![Ex-Search Intensity vs Focality]({{ site.baseurl }}/assets/imgs/ex-search/intensity_vs_focality_scatter.png)

_`intensity_vs_focality_scatter.png`: every evaluation plotted as ROI mean intensity against focality, coloured by `Composite_Index`. With ~17k candidates the Pareto front emerges along the upper-right edge — no montage improves intensity without giving up focality beyond it. Equal 1.0/1.0 mA splits populate the high-intensity end; strongly unequal splits (0.2/1.8) collapse to the low-intensity cluster on the left._

---

## Pipeline Workflow

### 1. EEG Net Selection

```
[INFO] Scanning available EEG nets for subject 101...
  1. BioSemi-64-10-10.csv
  2. BioSemi-128-A1.csv
  3. BioSemi-256-A1.csv
  4. EEG10-10_Cutini_2011.csv
  5. EEG10-10_UI_Jurak_2007.csv
  6. EEG10-20_Okamoto_2004.csv
  7. GSN-HydroCel-128.csv
  8. GSN-HydroCel-185.csv        # Default selection
  9. GSN-HydroCel-256.csv
 10. easycap_BC_TMS64_X21.csv
```

### 2. Leadfield Management

- **Intelligent Detection**: Automatic scanning of existing leadfields with HDF5 validation
- **Flexible Creation**: Generate leadfields for any supported EEG net with automated naming
- **Performance Optimization**: Efficient loading of large matrices (2-20GB) with memory monitoring

### 3. Current Ratio Optimization

The optimization systematically tests current ratios respecting channel limits:

```
Example (non-default; defaults are total_current=2.0 mA, current_step=0.5 mA, no channel_limit):
For total_current=2.0mA, step=0.2mA, limit=1.6mA:
  (1.6, 0.4), (1.4, 0.6), (1.2, 0.8), (1.0, 1.0),
  (0.8, 1.2), (0.6, 1.4), (0.4, 1.6)
```

### 4. Exhaustive Search Algorithm

- **Electrode Combinations**: $$N^4$$ combinations, where $$N$$ is the number of electrodes per channel group
- **Current Ratios**: Systematic testing across user-defined current steps
- **Total Combinations**: $$N_{\text{electrode combinations}} \times N_{\text{current ratios}}$$
- **In-Memory Processing**: No intermediate mesh files, direct field extraction
- **Progress Tracking**: Real-time monitoring with ETA calculations

### 5. Analysis & Visualization Pipeline

- **Run Time**: From minutes to hours depending on leadfield size and electrode combinations
- **Metrics Calculation**: `TImax_ROI`, `TImean_ROI`, `TImean_GM`, `Focality` (`TImean_ROI`/`TImean_GM`), and `n_elements` (ROI element count). The ROI mask itself is not restricted by tissue -- it is tested against all leadfield mesh elements, and leadfields are generated with `tissues=[1, 2]` (white + grey matter), so an ROI can include WM elements. Only the focality denominator, `TImean_GM`, is filtered to grey matter (mesh element tag `2`)
- **Visualization**: every run writes five PNGs next to `final_output.csv` — `montage_distributions.png` (histograms), `intensity_vs_focality_scatter.png`, and three EEG-map figures: `electrode_score_heatmap.png` (electrode participation across the top-50 montages: colour = summed Composite Index, size = frequency), `montage_strength_map.png` and `montage_focality_map.png` (the top-150 montages drawn as arcs on the cap, coloured by `TImean_ROI` / `Focality`, best montage highlighted). The maps need the net's EEG-position CSV (resolved like `symmetry_eeg_csv`) and are skipped with a log line otherwise; they can be regenerated for an existing run with `simnibs_python -m tit.opt.ex.results <run_dir> [--eeg-csv CSV]`
- **Output Formats**: `run_config.json`, `final_output.csv`, PNG figures

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

## Technical Implementation

### Architecture

1. **Leadfield loading** via SimNIBS `TI_utils`
2. **ROI resolution**: OR-folds a mixed list of CSV centers, whole NIfTI/MGZ masks (voxel value > 0), and `(path, label)` atlas-region selections (voxel value == label) into a single region
3. **GM element identification** by tissue tag
4. **TI field computation** per montage combination
5. **Metric extraction** (TImax, TImean, Focality)

### Performance Characteristics

- **Scalability**: Handles large electrode combinations (1000+ montages) efficiently
- **Memory Usage**: Constant memory footprint regardless of combination count -- all computation is in-memory with no intermediate file I/O
- **Progress Tracking**: Real-time ETA calculation with rate monitoring
- **Graceful Interruption**: Signal handling (SIGINT/SIGTERM) for clean shutdown
