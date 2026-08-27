---
layout: wiki
title: Multipolar TI (mTI)
permalink: /wiki/mti/
---

Multipolar temporal interference (mTI) generalizes standard 2-pair TI to four or more electrode pairs, driven by independent high-frequency carriers whose beat pattern is combined into one modulation envelope. This page covers the field math, how mTI is wired through the simulator and analyzer, and multipolar exhaustive search (mex-search). For montage sources, the simulator GUI, and standard TI post-processing, see [Simulator]({{ site.baseurl }}/wiki/simulator/); for 2-pair exhaustive search, see [Ex-Search]({{ site.baseurl }}/wiki/ex-search/); for field analysis, see [Analyzer]({{ site.baseurl }}/wiki/analyzer/).

<img src="{{ site.baseurl }}/assets/imgs/simulator/uTI_mTI.png" alt="Unipolar vs multipolar TI" style="width: 80%; max-width: 300px;">
<em>Left column unipolar (two channels) right column multipolar (four channels). Panels A,D: target and electrode montage. Panels B,E: high frequency fields. Panels C,F: modulation fields.</em>

## What mTI Is, and How the Toolbox Detects It

TI vs. mTI is not a setting -- it is inferred purely from how many electrode pairs a montage has. `Montage.simulation_mode` (`tit/sim/config.py`) does this:

- **2 pairs** -> `SimulationMode.TI`
- **4 or more pairs** -> `SimulationMode.MTI`
- **0, 1, or 3 pairs** -> raises `ValueError("Invalid number of electrode pairs: {n}. Expected 2 (TI) or 4+ (mTI).")`

There is no odd-pair-count mTI: an mTI montage must have an even number of pairs, and `mTISimulation` additionally caps it at 26 pairs (see [Simulator Behavior for mTI](#simulator-behavior-for-mti) below).

Montages are persisted in `montage_list.json` under separate keys per EEG net:

```
data["nets"][eeg_net]["multi_polar_montages"][name] = [[e1,e2],[e3,e4],[e5,e6],[e7,e8]]
data["nets"][eeg_net]["uni_polar_montages"][name]   = [[e1,e2],[e3,e4]]
```

`upsert_montage(..., mode="M")` writes to `multi_polar_montages`; `mode="U"` writes to `uni_polar_montages`. When a montage is loaded by name, `load_montages` resolves it as `multi.get(name) or uni[name]` -- if the same name exists in both dictionaries, the multi-polar entry wins.

![Multipolar Montage Example]({{ site.baseurl }}/assets/imgs/simulator/multipolar.png)
<em>A multipolar montage: 8 electrodes arranged in 4 channels (4 electrode pairs).</em>

## Field Math and Critical Values

The envelope for any number of coherent-beat electrode pairs reduces to two sufficient statistics of the fields' projections onto a candidate direction $$\mathbf{n}$$. For pair $$k$$, the signed projections of its two carrier fields are

$$
a_k = \mathbf{E}_{ka} \cdot \mathbf{n},
\qquad
b_k = \mathbf{E}_{kb} \cdot \mathbf{n}
$$

from which the carrier power $$P$$ and the coherent phasor sum $$Q$$ follow:

$$
P = \frac{1}{2} \sum_k \left( a_k^2 + b_k^2 \right),
\qquad
Q = \left\lvert \sum_k a_k b_k \, e^{i \psi_k} \right\rvert
$$

and the modulation depth is

$$
\mathrm{MD} = \sqrt{2} \left( \sqrt{P + Q} - \sqrt{P - Q} \right)
$$

$$\psi_k$$ is a per-pair envelope phase offset (radians), `None` by default (all pairs phase-aligned, $$\psi_k = 0$$, the standard case). $$P - Q$$ and $$P + Q$$ are clamped to $$\ge 0$$ before the square roots to absorb floating-point round-off. This is implemented in `tit/calc.py`, whose public API is exactly five functions:

| Function | Purpose |
|---|---|
| `get_TI_vectors(E1, E2)` | Exact $$K = 1$$ closed form (2 pairs) |
| `get_mTI_vectors(fields, channels=None, psi=None)` | $$K \ge 1$$ envelope; the verified $$N > 2$$ replacement |
| `get_TI_avg(fields, channels=None, psi=None)` | Direction-averaged modulation depth |
| `get_magnitude_am(fields)` | Direction-free AM envelope of $$\lVert \mathbf{E}(t) \rVert$$ (Botzanowski et al. 2025) |
| `get_nTI_vectors(fields)` | **Deprecated.** Delegates to `get_mTI_vectors` |

**`get_mTI_vectors`** is the function that mTI simulation and mex-search both call. It takes `fields = [E_1a, E_1b, ..., E_Ka, E_Kb]`, $$2K$$ arrays of shape `(N, 3)`, and returns `(N, 3)` modulation-amplitude vectors whose norm is $$\mathrm{MD}$$.

- **$$K = 1$$** dispatches exactly to `get_TI_vectors`, an exact closed form (Hirata et al. 2024, sign-agnostic):

  $$
  \mathrm{MD} =
  \begin{cases}
  2 \min\!\left( \lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert \right)
    & \text{if } \min\!\left( \lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert \right) \le \sqrt{\lvert \mathbf{E}_1 \cdot \mathbf{E}_2 \rvert} \\[8pt]
  \dfrac{2 \lVert \mathbf{E}_1 \times \mathbf{E}_2 \rVert}
        {\min\!\left( \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert \right)}
    & \text{otherwise}
  \end{cases}
  $$

  In the first case the envelope lies along the smaller field's own (sign-corrected) direction; in the second it is evaluated at the component of the smaller field perpendicular to whichever of $$\mathbf{E}_1 - \mathbf{E}_2$$ / $$\mathbf{E}_1 + \mathbf{E}_2$$ has the smaller norm. No direction search is needed at $$K = 1$$.
- **$$K \ge 2$$** has no closed form and is solved by a direction search: a coarse 192-point Fibonacci-sphere sweep (`num_directions=192`), followed by 3 rounds of local patch refinement around up to 6 angularly-diverse coarse-sweep seeds (`_REFINE_N_ROUNDS=3`, `_REFINE_N_SEEDS=6`, minimum seed separation `_REFINE_MIN_SEED_ANGLE_DEG=25.0`, 16 points per patch, initial half-angle $$2.0/\sqrt{192}$$ radians shrinking by `0.4` each round). Elements are processed in chunks of `16384` to bound memory. `get_TI_avg` reuses the same coarse sweep but averages the envelope over all 192 sampled directions instead of taking the per-element argmax, and skips refinement (refinement only sharpens a single best direction, which an average does not need) -- it is element-wise $$\le \mathrm{TI}_{\max}$$.

**`get_nTI_vectors` is deprecated and physically invalid for $$N > 2$$.** It represents the old approach of recombining pairwise envelopes recursively -- $$\mathrm{TI}\!\left( \mathrm{TI}(\mathbf{E}_1, \mathbf{E}_2), \mathrm{TI}(\mathbf{E}_3, \mathbf{E}_4), \ldots \right)$$ -- feeding an already-modulated envelope vector back into a formula that was derived only for two carrier fields. Measured against the verified envelope on random fields, this recursive form has a signed mean error of **+38.6% (range -90% to +416%) at $$N = 4$$**, and **+103% at $$N = 8$$**. Calling it emits a `DeprecationWarning` and delegates to `get_mTI_vectors` -- so the deprecated call still returns the correct answer, it just should not be relied on for its own (wrong) formula going forward.

## Carrier Wiring (Channels)

By default, `get_mTI_vectors`/`get_TI_avg` pair fields **positionally**: field 0 with field 1, field 2 with field 3, and so on -- each electrode pair is its own independent carrier. The `channels` parameter overrides this grouping explicitly:

```
channels = [(group_a, group_b), ...]
```

Each channel is a `(group_a, group_b)` pair of integer indices into `fields`. Per channel, $$\mathbf{E}_a = \sum_{i \in \texttt{group\_a}} \mathbf{E}_i$$ and $$\mathbf{E}_b = \sum_{i \in \texttt{group\_b}} \mathbf{E}_i$$ (an empty `group_b` sums to zeros -- a non-beating carrier that contributes to $$P$$ but not $$Q$$). The summed pairs from all channels are concatenated in channel order and fed to the same K-pair envelope. `channels=None` reproduces positional consecutive pairing byte-identically -- it is not an approximation of the explicit form, it *is* the explicit form `[([0],[1]), ([2],[3]), ...]`.

For a 4-pair montage, `MTI_CHANNEL_ARCHITECTURES` (`tit/opt/config.py`) exposes two named choices:

| Label | `channels` value | Meaning |
|---|---|---|
| Two independent channels (default) | `None` | Pairs 1&2 form one TI channel, pairs 3&4 form a second, independent TI channel |
| Four pairs, two carriers | `[([0, 2], [1, 3])]` | All four pairs share two carriers -- pairs 1&3 vs. 2&4 (Lee et al. 2022) |

`channels=[([0, 2], [1, 3])]` is algebraically exactly $$\mathrm{TI}\!\left( \mathbf{E}_0 + \mathbf{E}_2, \; \mathbf{E}_1 + \mathbf{E}_3 \right)$$ -- summing carriers before taking the $$K = 1$$ envelope, rather than taking a 4-pair envelope over four independent carriers. The two wirings are **not** interchangeable. The toolbox's regression test on random fields (`tests/test_calc_mti.py`) asserts that they differ by more than 5% in over half of all mesh elements; the figure recorded alongside that assertion for the montage tested is about 92% of elements, and the GUI help text notes differences of up to 6x in places.

**Important:** `Montage.channels` can only be set from a `tit.sim` JSON config or directly in Python (`tit/sim/__main__.py:_build_channels`). `load_montages` never reads a `channels` value from `montage_list.json`, and `tit/gui/simulator_tab.py` never sets `Montage.channels` at all -- so **every mTI simulation launched from the GUI runs with `channels=None` (positional/independent-dyad pairing)**. The mex-search tab's "Carrier Wiring" combo (see [GUI Walkthrough](#gui-walkthrough)) is the one place in the GUI that does expose this choice, but only for mex-search candidates, not for simulator runs.

`hf_peak`/`hf_sar` (safety metrics, below) are unaffected by `channels`: they always sum over every carrier field regardless of how carriers are grouped for the envelope.

## Simulator Behavior for mTI

`mTISimulation` (`tit/sim/mTI.py`) builds one SimNIBS TDCS list per pair, each driven at `config.intensities[i]` mA (converted to A). `SimulationConfig.intensities` defaults to `[1.0, 1.0]`; for mTI, validation requires `len(config.intensities) >= montage.num_pairs` -- one current value per pair, not two. The GUI's job-card current placeholder switches from `1.0,1.0` to `1.0,1.0,1.0,1.0` when the montage mode is multipolar.

**Output fields.** `SimulationConfig.output_fields` gates which volume-mesh fields are computed and written -- it defaults to `["TI_max"]` **only**. `TI_avg` and the safety fields (`hf_peak`, `hf_sar`) must be opted into; the four selectable names are exactly `("TI_max", "TI_avg", "hf_peak", "hf_sar")` (`const.SELECTABLE_OUTPUT_FIELDS`). The gating skips the *computation*, not just the write -- unrequested fields are never evaluated. In the GUI (shared by TI and mTI), output fields are checkboxes with only `TI_max` pre-checked; submitting with none checked is rejected with "Select at least one output field."

On disk, the mTI mesh spells the modulation-depth field `mTI_max` -- the same quantity `TI_max` names on a 2-pair TI mesh, just a different on-disk name for the 4-pair case.

**TI_normal is not computed for mTI.** Standard TI derives it from SimNIBS's 2-field `TI.get_dirTI`; the N-pair analogue would need the coherent K-pair envelope evaluated at a *fixed* direction (the surface normal) rather than maximized over direction, and while `tit.calc` has that primitive internally, it is only exposed as a private helper today -- exposing it publicly, and updating `tit/analyzer/field_selector.py` (which resolves the normal mesh under `TI/mesh/` unconditionally), is deferred.

**fsaverage projection is skipped for mTI.** `SimulationConfig.map_to_fsavg` defaults to `True`, but the projection step returns early for any montage whose `simulation_mode != TI`, logging "fsaverage projection: skipping %s (mTI not yet supported)".

mTI supports an arbitrary even number of pairs, **capped at 26** (A-Z pair labelling); more than 26 pairs raises `ValueError`. Post-processing:

1. Loads and crops all N high-frequency meshes to brain tissue (`BRAIN_TISSUE_TAG_RANGES = ((1, 100), (1001, 1100))`).
2. Computes intermediate 2-pair TI vector fields for adjacent pairs (`{montage}_TI_AB.msh`, `{montage}_TI_CD.msh`, ...) via the plain $$K = 1$$ `get_TI_vectors` -- these are saved for inspection only and are **not** recombined into the final result (that would be the deprecated recursive path).
3. Computes the final envelope over all N carrier fields jointly via `get_mTI_vectors(e_fields, channels=montage.channels)`, written as `mTI_max`; optionally `TI_avg`, `hf_peak`, `hf_sar` per `output_fields`.
4. Extracts GM/WM crops (`grey_{montage}_mTI.msh`, `white_{montage}_mTI.msh`), generates a central cortical surface via `msh2cortex`, and converts meshes to NIfTI.

Output layout, under `derivatives/SimNIBS/sub-{id}/Simulations/{montage}/`:

```
mTI/mesh/{montage}_mTI.msh          # mTI_max / TI_avg / hf_peak / hf_sar (selected)
mTI/mesh/grey_{montage}_mTI.msh     # GM crop
mTI/mesh/white_{montage}_mTI.msh    # WM crop
mTI/mesh/surfaces/                  # central cortical surface (msh2cortex)
mTI/niftis/                         # mesh -> NIfTI conversion
mTI/montage_imgs/                   # combined_montage_visualization.png
```

Per-pair high-frequency meshes are renamed `TDCS_1..N` -> `TDCS_A..Z` when moved into `high_Frequency/mesh/`, matching the A-Z pair labelling used everywhere else in the mTI output.

## Safety Metrics

Two carrier-exposure safety metrics (`tit/fields.py`, Cassarà et al. 2025) are computed directly from the N per-pair carrier E-fields, independent of the modulation-depth envelope:

**`hf_peak`** (Eq. 3) is the worst-case instantaneous peak carrier field: carriers run at mutually incommensurate frequencies, so every relative phase combination occurs over time, and the true worst case is the max over sign choices,

$$
\mathrm{hf\_peak} = \max_{\mathbf{s}} \left\lVert \sum_i s_i \mathbf{E}_i \right\rVert,
\qquad s_i \in \{ +1, -1 \}
$$

At $$N = 2$$ this is exactly $$\max\!\left( \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \; \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert \right)$$. Up to `EXACT_SIGN_ENUM_MAX_FIELDS = 8` fields, this is solved by exact sign enumeration ($$2^{N-1}$$ combinations -- 128 at $$N = 8$$). Above 8 fields the combinatorics blow up (measured ~44.6s for $$N = 12$$'s 2048 combinations at 200k elements vs. ~2.0s at $$N = 8$$), so a `4000`-direction Fibonacci-sphere sweep picks the best-sampled support direction and evaluates the exact, realizable vector sum for the sign pattern it implies. This sweep fallback is still a lower bound on the true max over all $$2^{N-1}$$ sign combinations -- since only the sampled directions' implied patterns are tried -- and is therefore **slightly non-conservative**.

**`hf_sar`** is the incoherent sum of carrier powers, in $$(\mathrm{V/m})^2$$ -- carriers are incoherent, so their power adds rather than their amplitudes:

$$
\mathrm{hf\_sar} = \sum_i \lVert \mathbf{E}_i \rVert^2
$$

This is a field-domain heating proxy, **not** calibrated SAR: the actual calibration is $$\tfrac{\sigma}{2\rho} \cdot \mathrm{hf\_sar}$$, requiring the per-tissue conductivity $$\sigma$$ and density $$\rho$$ that the toolbox does not apply.

Both metrics always sum over **every** carrier field regardless of `channels` -- carrier exposure does not depend on how pairs are grouped into TI channels for the envelope -- and both are **opt-in**: neither is in `SimulationConfig.output_fields`'s default (`["TI_max"]`), so a run must explicitly request `hf_peak`/`hf_sar` to get them written.

## Multipolar Exhaustive Search (mex-search)

`tit/opt/mex/` extends [ex-search]({{ site.baseurl }}/wiki/ex-search/) to four bipolar pairs (eight electrodes), scored with the same verified `get_mTI_vectors` envelope used by the simulator -- explicitly **not** a recursive envelope-of-envelopes. The public API is `run_m_ex_search(config: MExConfig) -> MExResult`, re-exported from `tit.opt` alongside `run_ex_search`/`run_flex_search`.

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
| `channels` | `None` (positional pairing; see [Carrier Wiring](#carrier-wiring-channels)) |
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

**Effect of carrier wiring.** Re-running a 16-candidate subset with `channels = [[[0,2],[1,3]]]` (four pairs sharing two carriers) keeps the same ranking but raises the envelope ~1.45× (best montage `F7_P7 <> F5_CP3 <> F3_P3 <> AF7_P9`: TImean_ROI 0.307 → 0.444 V/m, focality 1.96 → 1.78). This is why `channels` must be chosen deliberately (see [Carrier Wiring](#carrier-wiring-channels)).

<div class="image-row">
  <div class="image-container">
    <img src="{ site.baseurl }/assets/imgs/mti/mex_scatter_independent.png" alt="mex-search, independent channels (16 candidates)">
    <em>Independent channels (16 candidates)</em>
  </div>
  <div class="image-container">
    <img src="{ site.baseurl }/assets/imgs/mti/mex_scatter_twocarrier.png" alt="mex-search, two carriers (16 candidates)">
    <em>Four pairs, two carriers (same 16)</em>
  </div>
</div>

**Cost.** Scoring one 4-pair candidate with the verified N>2 envelope is a per-element direction search (192-direction sweep plus local refinement), not a closed form like 2-pair ex-search. The search is evaluated on ROI ∪ GM only by a fused numba kernel (`tit/_mti_kernel.py`, all cores) and candidates are distributed over forked worker processes (`n_jobs`, default all cores − 1): on a 12-core machine this is ~1–2 s per candidate, i.e. a few hundred candidates in ~10 min The first call pays ~10 s of JIT compilation, cached afterwards. There is no current-ratio sweep in mex-search; each run uses a single `current_mA`.

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

## GUI Walkthrough

The [Ex-Search]({{ site.baseurl }}/wiki/ex-search/) tab hosts both TI and mTI search behind a single **Search Mode** combo: "TI (2-pair)" (default) and "mTI (4-pair)". Selecting mTI:

- Hides the Bucketed/All Combinations radio buttons and switches the electrode panel to eight free-text fields, **E1+ .. E4-** (2 columns x 4 rows). mTI is bucket-only -- there is no all-combinations page, since pool permutations over eight positions are combinatorially far larger than TI's four.
- Switches the current-configuration panel to a **Pair Current (mA)** spinbox (range 0.1-10.0, default 2.0, step 0.1), a **Carrier Wiring** combo (the two `MTI_CHANNEL_ARCHITECTURES` choices from [Carrier Wiring](#carrier-wiring-channels)), and a **Force left/right symmetry** checkbox (unchecked by default) that enables a symmetry-pairing combo -- "Within each pair" / "Cross pairs (E1<->E3, E2<->E4)" -- once checked.
- Disables the **Combine ROIs** checkbox only. Both ROI types are available: `MExConfig` carries `roi_names` and `roi_atlas` exactly as `ExConfig` does, so an mTI run can target a sphere, an atlas region, or an atlas region alone. Combining stays TI-only because the multipolar run path processes selected spheres one at a time.
- Retitles the box "mTI Configuration" and relabels the run/stop buttons "Run mTI Search"/"Stop mTI Search".

The shared **ROI Radius** spinbox (range 1.0-10.0 mm, default 3.0) applies to both modes.

Validation before an mTI run requires all eight bucket fields to be non-empty ("Please enter valid electrodes for all eight mTI bucket categories (E1..E4, +/-)"), plus at least one ROI selected. The confirmation dialog reports per-bucket electrode counts, pair current, carrier wiring, an upper-bound search-space size (`Search Space: up to <product of the 8 bucket sizes> eight-electrode combinations`, before the distinctness filter), and the ROI list.

## Analyzer Behavior for mTI

The [Analyzer]({{ site.baseurl }}/wiki/analyzer/) detects an mTI simulation purely from the presence of `{simulation}/mTI/mesh/` on disk -- there is no separate analyzer mode to select, and the same `Analyzer` class handles both TI and mTI.

- `TI_max` and `mTI_max` are treated as aliases for the same quantity: whichever spelling is requested, the analyzer resolves it to the on-disk name the detected simulation type actually wrote (`mTI_max` for mTI, `TI_max` for TI).
- `TI_normal` is **unavailable for mTI**: requesting it raises `FileNotFoundError` ("TI_normal is only computed for standard 2-pair TI simulations"), since mTI never writes a normal-component mesh (see [Simulator Behavior for mTI](#simulator-behavior-for-mti)). Consequently `normal_mean`, `normal_max`, and `normal_focality` are always absent (`None`) from mTI analysis results.

## References and Attribution

- Grossman, N. et al. (2017). Noninvasive deep brain stimulation via temporally interfering electric fields. *Cell*, 169(6), 1029-1041.
- Hirata, A. et al. (2024). Electric field envelope focality with linear alignment montage. *Computers in Biology and Medicine*, 178, 108697.
- Cassarà, A.M. et al. (2025). Recommendations for the safe application of temporal interference stimulation, Parts I-II. *Bioelectromagnetics*, 46(2). doi:10.1002/bem.22542.
- Botzanowski, B. et al. (2025). Focal control of non-invasive deep brain stimulation using multipolar temporal interference. *Bioelectronic Medicine*, 11(1), 7.
- Lee, S. et al. (2022). Multipair transcranial temporal interference stimulation for deep brain targeting. *Frontiers in Neuroscience*.

The $$K \ge 2$$ envelope, the Fibonacci-sphere direction sampling, and `get_magnitude_am` were ported into `tit/calc.py` from collaborator Larissa Albantakis's branch `alba/mTI_testing`. The multipolar exhaustive search combination logic (`tit/opt/mex/logic.py`) and the generalized electrode-bucket loader (`tit/opt/ex/buckets.py`) were ported from her branch `alba/ex-search-multipolar`.
