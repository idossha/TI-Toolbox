---
layout: wiki
title: Simulator
permalink: /wiki/simulator/
---

The Simulator computes the full FEM temporal interference field. It sits between the optimizers and the analyzer: take a montage from the montage list or from a [flex-search]({{ site.baseurl }}/wiki/flex-search/) or [ex-search]({{ site.baseurl }}/wiki/ex-search/) result, or placed by hand and simulate it here. Then, quantify the resulting field with the [Analyzer]({{ site.baseurl }}/wiki/analyzer/). It can be invoked programmatically via `run_simulation()` or through a JSON config entrypoint.

## User Interface

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/UI/UI_sim.png" alt="Simulator User Interface" style="width: 100%; max-width: 600px;">
</div>

- **Subject Selection**: Choose from available pre-processed subjects; multiple subjects can be queued for batch processing
- **Montage Source**: Per-job drop-down — `Montage`, `Flex-Search`, or `Freehand` (see [Montage Sources](#montage-sources))
- **Simulation Mode**: Unipolar/multipolar with per-channel current inputs
- **EEG Net**: Dropdown selection of available electrode configurations
- **Conductivity Model**: Four anisotropy types (`scalar`, `vn`, `dir`, `mc`) with configurable bounds (see [Conductivity and Anisotropy](#conductivity-and-anisotropy))
- **Output Fields**: Checkboxes for `TI_max` (default), `TI_avg`, `hf_peak` and `hf_sar`; at least one must be selected
- **Real-time Logging**: Simulation progress and status updates

---

## Montage Sources

The simulator supports three primary montage source types:

### 1. Montage List

Pre-defined electrode configurations organized by EEG net and stimulation mode:

- **Unipolar Montages**: Standard TI — 4 electrodes forming 2 channels
- **Multipolar Montages**: mTI — 8 electrodes forming 4 channels, for higher focality
- **EEG Net Compatibility**: Automatically filtered based on selected electrode configuration
- **Management**: Add, remove, and refresh montage collections

### 2. Flex Mode

Automatic integration with the flex-search optimizer.

- **Optimize**: Start by running the optimizer based on your needs
- **Simulate**: Move to the simulator and use the automatic montage available from the flex-search
- **Run Identity**: Flex-search-derived simulations keep their unique run IDs on disk, while the UI shows concise display names and hover metadata so repeated simulations are easier to distinguish without long folder labels.

### 3. Free-Hand

Mode that allows exploration of untraditional montages

- **Flexible Positioning**: Manual electrode placement for specialized protocols
- **Extension**: Open up the `electrode placement` extension to freely place electrodes on subjects

### Available EEG Nets

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/eeg_nets_available.png" alt="Available EEG Nets" style="width: 100%; max-width: 800px;">
</div>

The TI-Toolbox automatically co-registers these EEG electrode nets to head models during preprocessing, so no manual registration step is needed — the same pre-aligned nets serve simulation, flex-search electrode mapping, and leadfield generation. The GUI scans `eeg_positions/` directories for available configurations, refreshes montage lists when the selected net changes, and displays only montages compatible with that net.

---

## Simulation Modes

### Unipolar Mode

- **Configuration**: Single active electrode with dedicated return path
- **Current Settings**: Two current inputs (active and return electrodes)
- **Applications**: Focal stimulation with clear current flow direction
- **Montage Compatibility**: Works with unipolar montage collections

### Multipolar Mode (mTI)

Standard TI uses 4 electrodes forming 2 **channels** (a channel = one electrode pair driven by one current source); the two channels share one carrier — e.g. 2.000 and 2.010 kHz around a 2 kHz carrier — and their beat is the TI envelope. Multipolar temporal interference (mTI) doubles this: 8 electrodes form 4 channels, and each two channels share a carrier (e.g. channels 1 & 2 near 2 kHz, channels 3 & 4 near 4 kHz). Each carrier produces its own beat, and the beats combine into one modulation envelope.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/uti_mti_albantakis2026.png" alt="Unipolar vs multipolar TI: montage, peak HF field, and AM field" style="width: 100%; max-width: 750px;">
  <em>Unipolar (top, A–C) vs. multipolar (bottom, D–F) TI targeting the same deep ROI. Left: electrode montage — two channels at 8 mA each vs. four channels at 5 mA each. Middle: peak high-frequency field. Right: the amplitude-modulated (AM) envelope field that actually drives neurons. The multipolar montage trades some ROI intensity (mean 1.00 vs. 1.45 V/m) for a more focal envelope (focality 1.40 vs. 1.17) and a lower per-channel current. Adapted from <a href="https://doi.org/10.1176/appi.ajp.20250873">Albantakis &amp; Tononi 2026</a>, <i>American Journal of Psychiatry</i>.</em>
</div>

- **Configuration**: Any even number of channels, 4 or more — i.e. 8+ electrodes (capped at 26 channels, labelled A–Z)
- **Current Settings**: One current input per channel (see [Simulator Behavior for mTI](#simulator-behavior-for-mti) below)
- **Applications**: Distributed stimulation, field steering, and complex targeting
- **Montage Compatibility**: Works with multipolar montage collections

For the envelope field math behind these quantities see [Envelope Math and Critical Values]({{ site.baseurl }}/wiki/analyzer/#envelope-math-and-critical-values) on the Analyzer page.

#### How the Toolbox Detects mTI

TI vs. mTI is not a setting -- it is inferred purely from how many channels (electrode pairs, in the code's wording) a montage has. `Montage.simulation_mode` (`tit/sim/config.py`) does this:

- **2 channels** -> `SimulationMode.TI`
- **4 or more channels** -> `SimulationMode.MTI`
- **0, 1, or 3 channels** -> raises `ValueError("Invalid number of electrode pairs: {n}. Expected 2 (TI) or 4+ (mTI).")`

There is no odd-channel-count mTI: an mTI montage must have an even number of channels (every carrier needs two), and `mTISimulation` additionally caps it at 26 channels (see [Simulator Behavior for mTI](#simulator-behavior-for-mti) below).

Montages are persisted in `montage_list.json` under separate keys per EEG net:

```
data["nets"][eeg_net]["multi_polar_montages"][name] = [[e1,e2],[e3,e4],[e5,e6],[e7,e8]]
data["nets"][eeg_net]["uni_polar_montages"][name]   = [[e1,e2],[e3,e4]]
```

`upsert_montage(..., mode="M")` writes to `multi_polar_montages`; `mode="U"` writes to `uni_polar_montages`. When a montage is loaded by name, `load_montages` resolves it as `multi.get(name) or uni[name]` -- if the same name exists in both dictionaries, the multi-polar entry wins.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/multipolar.png" alt="Multipolar Montage Example">
  <em>A multipolar montage: 8 electrodes forming 4 channels on 2 carriers.</em>
</div>

#### Carrier Wiring (`channels`)

Carrier wiring is the choice of **which channels share a carrier**. By default, the envelope functions (`get_mTI_vectors`/`get_TI_avg` in `tit/calc.py`) assign channels to carriers **positionally**: channels 1 & 2 share the first carrier, channels 3 & 4 the second, and so on. The `channels` parameter overrides this assignment explicitly -- note the naming clash: despite its name, each entry of the parameter describes one **carrier**, not one channel:

```
channels = [(group_a, group_b), ...]   # one entry per carrier
```

Each carrier entry is a `(group_a, group_b)` pair of lists of integer indices into `fields` (one field per channel). Per carrier, $$\mathbf{E}_a = \sum_{i \in \texttt{group\_a}} \mathbf{E}_i$$ and $$\mathbf{E}_b = \sum_{i \in \texttt{group\_b}} \mathbf{E}_i$$ -- channels listed in the same group run at the same frequency, so their fields sum coherently (an empty `group_b` sums to zeros -- a non-beating carrier that contributes kHz power but no beat). The summed field pairs from all carriers are fed to the same $$K$$-carrier envelope. `channels=None` reproduces positional pairing byte-identically -- it is not an approximation of the explicit form, it _is_ the explicit form `[([0],[1]), ([2],[3]), ...]`.

For a 4-channel montage, `MTI_CHANNEL_ARCHITECTURES` (`tit/opt/config.py`) exposes two named choices (the GUI labels below are quoted verbatim and predate this page's channel/carrier vocabulary):

| Label                              | `channels` value     | Meaning                                                                                                                                              |
| ---------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Two independent channels (default) | `None`               | Channels 1 & 2 share one carrier, channels 3 & 4 a second -- two independent beats (the standard mTI wiring)                                         |
| Four pairs, two carriers           | `[([0, 2], [1, 3])]` | All four channels share **one** carrier: channels 1 & 3 sum at one frequency, channels 2 & 4 at the other, producing a single beat (Lee et al. 2022) |

`channels=[([0, 2], [1, 3])]` is algebraically exactly $$\mathrm{TI}\!\left( \mathbf{E}_0 + \mathbf{E}_2, \; \mathbf{E}_1 + \mathbf{E}_3 \right)$$ -- summing the channel fields before taking the single-carrier ($$K = 1$$) envelope, rather than taking a 2-carrier envelope over four independent channel fields. The two wirings are **not** interchangeable. The toolbox's regression test on random fields (`tests/test_calc_mti.py`) asserts that they differ by more than 5% in over half of all mesh elements; the figure recorded alongside that assertion for the montage tested is about 92% of elements, and the GUI help text notes differences of up to 6x in places.

**Important:** `Montage.channels` can only be set from a `tit.sim` JSON config or directly in Python (`tit/sim/__main__.py:_build_channels`). `load_montages` never reads a `channels` value from `montage_list.json`, and `tit/gui/simulator_tab.py` never sets `Montage.channels` at all -- so **every mTI simulation launched from the GUI runs with `channels=None` (positional pairing -- each two consecutive channels share a carrier)**. The mex-search tab's "Carrier Wiring" combo is the one place in the GUI that does expose this choice, but only for mex-search candidates, not for simulator runs -- see [Multipolar (mTI) Mode on the Ex-Search page]({{ site.baseurl }}/wiki/ex-search/#multipolar-mti-mode).

The kHz-exposure safety metrics `hf_peak`/`hf_sar` are unaffected by `channels`: they always sum over every channel's field regardless of how channels are assigned to carriers for the envelope. Their math lives under [Safety Metrics on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#safety-metrics).

#### Simulator Behavior for mTI

`mTISimulation` (`tit/sim/mTI.py`) builds one SimNIBS TDCS list per channel, each driven at `config.intensities[i]` mA (converted to A). `SimulationConfig.intensities` defaults to `[1.0, 1.0]`; for mTI, validation requires `len(config.intensities) >= montage.num_pairs` -- one current value per channel, not two. The GUI's job-card current placeholder switches from `1.0,1.0` to `1.0,1.0,1.0,1.0` when the montage mode is multipolar.

On disk, the mTI mesh spells the modulation-depth field `mTI_max` -- the same quantity `TI_max` names on a standard TI mesh, just a different on-disk name for the multipolar case.

**TI_normal is not computed for mTI.** Standard TI derives it from SimNIBS's 2-field `TI.get_dirTI`; the multi-carrier analogue would need the $$K$$-carrier envelope evaluated at a _fixed_ direction (the surface normal) rather than maximized over direction, and while `tit.calc` has that primitive internally, it is only exposed as a private helper today -- exposing it publicly, and updating `tit/analyzer/field_selector.py` (which resolves the normal mesh under `TI/mesh/` unconditionally), is deferred.

**fsaverage projection is skipped for mTI.** `SimulationConfig.map_to_fsavg` defaults to `True`, but the projection step returns early for any montage whose `simulation_mode != TI`, logging "fsaverage projection: skipping %s (mTI not yet supported)".

mTI supports an arbitrary even number of channels, **capped at 26** (A-Z channel labelling); more than 26 channels raises `ValueError`. Post-processing:

1. Loads and crops all N high-frequency meshes to brain tissue (`BRAIN_TISSUE_TAG_RANGES = ((1, 100), (1001, 1100))`).
2. Computes an intermediate per-carrier TI vector field for each consecutive channel pair (`{montage}_TI_AB.msh`, `{montage}_TI_CD.msh`, ...) via the plain single-carrier `get_TI_vectors` -- these are saved for inspection only and are **not** recombined into the final result (that would be the deprecated recursive path).
3. Computes the final envelope over all N channel fields jointly via `get_mTI_vectors(e_fields, channels=montage.channels)`, written as `mTI_max`; optionally `TI_avg`, `hf_peak`, `hf_sar` per `output_fields`.
4. Extracts GM/WM crops (`grey_{montage}_mTI.msh`, `white_{montage}_mTI.msh`), generates a central cortical surface via `msh2cortex`, and converts meshes to NIfTI.

Per-channel high-frequency meshes are renamed `TDCS_1..N` -> `TDCS_A..Z` when moved into `high_Frequency/mesh/`, matching the A-Z channel labelling used everywhere else in the mTI output.

**References:** Albantakis, L. & Tononi, G. (2026). Precision neuromodulation in psychiatry: focus on temporal interference stimulation. _American Journal of Psychiatry_. doi:10.1176/appi.ajp.20250873. Lee, S. et al. (2022). Multipair transcranial temporal interference stimulation for deep brain targeting. _Frontiers in Neuroscience_.

---

## Output Fields

`SimulationConfig.output_fields` gates which volume-mesh fields are computed and written -- it defaults to `["TI_max"]` **only**. `TI_avg` and the safety fields (`hf_peak`, `hf_sar`) must be opted into; the four selectable names are exactly `("TI_max", "TI_avg", "hf_peak", "hf_sar")` (`const.SELECTABLE_OUTPUT_FIELDS`). The gating skips the _computation_, not just the write -- unrequested fields are never evaluated. In the GUI (shared by TI and mTI), output fields are checkboxes with only `TI_max` pre-checked; submitting with none checked is rejected with "Select at least one output field."

What each field _means_ — the beat-envelope modulation depth, the direction-averaged envelope, and the carrier-exposure safety metrics — is documented once, under [Quantities of Interest on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#quantities-of-interest).

---

## Conductivity and Anisotropy

The `conductivity` string field on `SimulationConfig` (or the GUI dropdown) selects one of four tissue conductivity models:

| Type              | Code     | Description                                             | Requirements                              |
| ----------------- | -------- | ------------------------------------------------------- | ----------------------------------------- |
| Scalar            | `scalar` | Isotropic, piecewise-constant (default)                 | None — used when no DTI data is available |
| Volume Normalized | `vn`     | Normalized tensors scaled by tissue conductivity        | DTI tensor                                |
| Direct            | `dir`    | Direct linear rescaling of diffusion tensor eigenvalues | DTI tensor                                |
| Mean Conductivity | `mc`     | Isotropic but spatially varying, from tensor volumes    | DTI tensor                                |

The anisotropic models account for fiber orientation, giving more realistic modeling of white matter tracts. Two additional `SimulationConfig` parameters bound them: `aniso_maxratio` (default: 10.0, maximum ratio between eigenvalues) and `aniso_maxcond` (default: 2.0, maximum conductivity value).

### DTI Data Preparation

The TI-Toolbox provides integrated DTI processing via QSIPrep and QSIRecon; the pipeline extracts diffusion tensors and converts them to the format required by SimNIBS. For anisotropic simulation, the following file must exist in the m2m directory:

```
derivatives/SimNIBS/sub-{id}/m2m_{id}/
└── DTI_coregT1_tensor.nii.gz    # 4D tensor (X, Y, Z, 6)
```

For complete DTI processing instructions, see the [Diffusion Processing]({{ site.baseurl }}/wiki/diffusion-processing/) documentation; for the underlying theory, see the [SimNIBS dwi2cond documentation](https://simnibs.github.io/simnibs/build/html/documentation/command_line/dwi2cond.html).

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/dti_CC.png" alt="DTI Eigen Vectors - Corpus Callosum" style="width: 80%; max-width: 500px;">
</div>
<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/dti_spinal.png" alt="DTI Eigen Vectors - Spinal Cord" style="width: 80%; max-width: 500px;">
</div>

<em>Gmsh visualizations showing white and gray matter with overlaid eigen vectors that scale conductivity in anisotropic simulations. Top: Corpus callosum region showing organized fiber directions. Bottom: Spinal cord region with longitudinal fiber orientation.</em>

---

## Output Layout and CLI

```
derivatives/SimNIBS/sub-{ID}/Simulations/{montage}/
├── documentation/config.json            # provenance snapshot used by the report
├── high_Frequency/{mesh,niftis,analysis} # per-channel SimNIBS outputs
├── TI/                                   # standard TI (2 channels)
│   ├── mesh/{montage}_TI.msh, grey_*.msh, white_*.msh
│   ├── niftis/{montage}_TI_subject_TI_max.nii.gz (+ _MNI_ when MNI export is on)
│   ├── montage_imgs/{montage}_highlighted_visualization.png
│   └── surface_overlays/
└── mTI/                                  # multipolar TI (4+ channels)
    ├── mesh/{montage}_mTI.msh            # mTI_max / TI_avg / hf_peak / hf_sar (selected)
    ├── mesh/grey_{montage}_mTI.msh, white_{montage}_mTI.msh
    ├── mesh/surfaces/                    # central cortical surface (msh2cortex)
    ├── niftis/                           # mesh -> NIfTI conversion
    └── montage_imgs/                     # combined_montage_visualization.png
```

NIfTI exports are written in subject space, and in MNI space when MNI export is enabled — ROI inputs elsewhere in the toolbox accept either space, with automatic transformation between them.

The GUI writes a JSON config and runs `simnibs_python -m tit.sim config.json`; the same command works from a shell (see [Scripting]({{ site.baseurl }}/wiki/scripting/) for the `SimulationConfig` fields).

## Report generation

Simulation reports are generated by the desktop GUI workflow after a simulation run. Programmatic simulation via `run_simulation()` or JSON config writes simulation outputs, but does not automatically create the HTML report unless the reporting API/GUI path is invoked separately. For more info see [Reports]({{ site.baseurl }}/wiki/reports/)
