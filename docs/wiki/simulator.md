---
layout: wiki
title: Simulator
permalink: /wiki/simulator/
---

The Simulator module provides temporal interference (TI) simulation capabilities, supporting multiple montage sources, electrode configurations, and simulation parameters. It can be invoked programmatically via `run_simulation()` or through a JSON config entrypoint.

## User Interface

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/UI/UI_sim.png" alt="Simulator User Interface" style="width: 100%; max-width: 600px;">
</div>

The simulator GUI provides intuitive controls for all simulation parameters:

### Main Controls
- **Subject Selection**: Choose from available pre-processed subjects
- **Montage Source**: Per-job drop-down — `Montage`, `Flex-Search`, or `Freehand`
- **Simulation Mode**: Unipolar/multipolar selection with current inputs
- **EEG Net**: Dropdown selection of available electrode configurations

### Advanced Options
- **Conductivity Model**: Four anisotropy types (`scalar`, `vn`, `dir`, `mc`) with configurable bounds
- **Current Configuration**: Individual per-pair electrode current settings
- **Batch Processing**: Multiple subject simulation queues
- **Output Fields**: Checkboxes for `TI_max` (default), `TI_avg`, `hf_peak` and `hf_sar`; at least one must be selected

### Output Management
- **Real-time Logging**: Simulation progress and status updates
- **Result Visualization**: Automatic generation of field maps and statistics
- **Data Export**: NIfTI files, electrode positions, and analysis reports
- **Readable Run Names**: Flex-search simulations keep stable storage IDs internally while the GUI shows compact display names and hover metadata for easier selection.

---

### Conductivity Types

The `conductivity` field on `SimulationConfig` controls tissue conductivity modeling:

| Type | Code | Description |
|------|------|-------------|
| Scalar | `scalar` | Isotropic, piecewise-constant (default, no DTI needed) |
| Volume Normalized | `vn` | Normalized tensors scaled by tissue conductivity |
| Direct | `dir` | Direct linear rescaling of diffusion tensor eigenvalues |
| Mean Conductivity | `mc` | Isotropic but spatially varying, from tensor volumes |

Additional parameters `aniso_maxratio` (default: 10.0) and `aniso_maxcond` (default: 2.0) on `SimulationConfig` control the anisotropy bounds.

---

## Montage Sources

The simulator supports three primary montage source types:

### 1. Montage List
Pre-defined electrode configurations organized by EEG net and stimulation mode:
- **Unipolar Montages**: The traditional two-pair electrode montage
- **Multipolar Montages**: Multiple (currently only supporting four) pairs for higher focality
- **EEG Net Compatibility**: Automatically filtered based on selected electrode configuration
- **Management**: Add, remove, and refresh montage collections

### 2. Flex Mode
Automatic integration with the flex-search optimizer.
- **Optimize**: Start by running the optimizer based on your needs
- **Simulate**: Move to the simulator and use the automatic montage available from the flex-search
- **Run Identity**: Flex-search-derived simulations keep their unique run IDs on disk, while the UI shows concise names so repeated simulations are easier to distinguish without long folder labels.

### 3. Free-Hand
Mode that allows exploration of untraditional montages
- **Flexible Positioning**: Manual electrode placement for specialized protocols
- **Extension**: Open up the `electrode placement` extension to freely place electrodes on subjects

---

## Simulation Modes

### Unipolar Mode
- **Configuration**: Single active electrode with dedicated return path
- **Current Settings**: Two current inputs (active and return electrodes)
- **Applications**: Focal stimulation with clear current flow direction
- **Montage Compatibility**: Works with unipolar montage collections

### Multipolar Mode (mTI)

Multipolar temporal interference (mTI) generalizes standard 2-pair TI to four or more electrode pairs, driven by independent high-frequency carriers whose beat pattern is combined into one modulation envelope.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/uti_mti_albantakis2026.png" alt="Unipolar vs multipolar TI: montage, peak HF field, and AM field" style="width: 100%; max-width: 750px;">
  <em>Unipolar (top, A–C) vs. multipolar (bottom, D–F) TI targeting the same deep ROI. Left: electrode montage — two pairs at 8 mA per carrier vs. four pairs at 5 mA per carrier. Middle: peak high-frequency carrier field. Right: the amplitude-modulated (AM) envelope field that actually drives neurons. The multipolar montage trades some ROI intensity (mean 1.00 vs. 1.45 V/m) for a more focal envelope (focality 1.40 vs. 1.17) and a lower per-carrier current. Adapted from <a href="https://doi.org/10.1176/appi.ajp.20250873">Albantakis &amp; Tononi 2026</a>, <i>American Journal of Psychiatry</i>.</em>
</div>

- **Configuration**: Any even number of electrode pairs, 4 or more (capped at 26, labelled A–Z)
- **Current Settings**: One current input per pair (see [Simulator Behavior for mTI](#simulator-behavior-for-mti) below)
- **Applications**: Distributed stimulation, field steering, and complex targeting
- **Montage Compatibility**: Works with multipolar montage collections

For the envelope field math behind these quantities (the verified K-pair modulation depth, `get_mTI_vectors`, and why the old recursive TI-of-TI form is invalid), see [Envelope Math and Critical Values]({{ site.baseurl }}/wiki/analyzer/#envelope-math-and-critical-values) on the Analyzer page.

#### How the Toolbox Detects mTI

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

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/multipolar.png" alt="Multipolar Montage Example">
  <em>A multipolar montage: 8 electrodes arranged in 4 channels (4 electrode pairs).</em>
</div>

#### Carrier Wiring (Channels)

By default, the envelope functions (`get_mTI_vectors`/`get_TI_avg` in `tit/calc.py`) pair fields **positionally**: field 0 with field 1, field 2 with field 3, and so on -- each electrode pair is its own independent carrier. The `channels` parameter overrides this grouping explicitly:

```
channels = [(group_a, group_b), ...]
```

Each channel is a `(group_a, group_b)` pair of integer indices into `fields`. Per channel, $$\mathbf{E}_a = \sum_{i \in \texttt{group\_a}} \mathbf{E}_i$$ and $$\mathbf{E}_b = \sum_{i \in \texttt{group\_b}} \mathbf{E}_i$$ (an empty `group_b` sums to zeros -- a non-beating carrier that contributes carrier power but no beat). The summed pairs from all channels are concatenated in channel order and fed to the same K-pair envelope. `channels=None` reproduces positional consecutive pairing byte-identically -- it is not an approximation of the explicit form, it *is* the explicit form `[([0],[1]), ([2],[3]), ...]`.

For a 4-pair montage, `MTI_CHANNEL_ARCHITECTURES` (`tit/opt/config.py`) exposes two named choices:

| Label | `channels` value | Meaning |
|---|---|---|
| Two independent channels (default) | `None` | Pairs 1&2 form one TI channel, pairs 3&4 form a second, independent TI channel |
| Four pairs, two carriers | `[([0, 2], [1, 3])]` | All four pairs share two carriers -- pairs 1&3 vs. 2&4 (Lee et al. 2022) |

`channels=[([0, 2], [1, 3])]` is algebraically exactly $$\mathrm{TI}\!\left( \mathbf{E}_0 + \mathbf{E}_2, \; \mathbf{E}_1 + \mathbf{E}_3 \right)$$ -- summing carriers before taking the $$K = 1$$ envelope, rather than taking a 4-pair envelope over four independent carriers. The two wirings are **not** interchangeable. The toolbox's regression test on random fields (`tests/test_calc_mti.py`) asserts that they differ by more than 5% in over half of all mesh elements; the figure recorded alongside that assertion for the montage tested is about 92% of elements, and the GUI help text notes differences of up to 6x in places.

**Important:** `Montage.channels` can only be set from a `tit.sim` JSON config or directly in Python (`tit/sim/__main__.py:_build_channels`). `load_montages` never reads a `channels` value from `montage_list.json`, and `tit/gui/simulator_tab.py` never sets `Montage.channels` at all -- so **every mTI simulation launched from the GUI runs with `channels=None` (positional/independent-dyad pairing)**. The mex-search tab's "Carrier Wiring" combo is the one place in the GUI that does expose this choice, but only for mex-search candidates, not for simulator runs -- see [Multipolar (mTI) Mode on the Ex-Search page]({{ site.baseurl }}/wiki/ex-search/#multipolar-mti-mode).

The carrier-exposure safety metrics `hf_peak`/`hf_sar` are unaffected by `channels`: they always sum over every carrier field regardless of how carriers are grouped for the envelope. Their math lives under [Safety Metrics on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#safety-metrics).

#### Simulator Behavior for mTI

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

**References:** Albantakis, L. & Tononi, G. (2026). Precision neuromodulation in psychiatry: focus on temporal interference stimulation. *American Journal of Psychiatry*. doi:10.1176/appi.ajp.20250873. Lee, S. et al. (2022). Multipair transcranial temporal interference stimulation for deep brain targeting. *Frontiers in Neuroscience*.

---

## Available EEG Nets

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/eeg_nets_available.png" alt="Available EEG Nets" style="width: 100%; max-width: 800px;">
</div>

The TI-Toolbox automatically co-registers the following EEG electrode nets to head models during preprocessing. These pre-aligned nets enable seamless integration with simulation workflows, electrode optimization, and leadfield calculations.

### Automatic Co-registration Benefits

- **Seamless Integration**: no manual registration steps
- **Simulation Ready**: Instant compatibility with TI field simulation workflows
- **Optimization Support**: Direct integration with flex-search tools
- **Leadfield Generation**: all available for leadfield matrix creation

### Net Detection and Management
- **Automatic Scanning**: Searches `eeg_positions/` directories for available electrode configurations
- **Dynamic Updates**: Montage lists automatically refresh based on selected EEG net
- **Compatibility Filtering**: Only compatible montages are displayed for the selected electrode configuration

---
## Anisotropy

The simulator supports four tissue conductivity models via the `conductivity` string field on `SimulationConfig`, configurable both through the GUI and programmatic API.

### Isotropic Model (`scalar`)
- **Description**: Uniform conductivity in all directions
- **Applications**: Simplified modeling, faster computation
- **Default**: Used when no DTI data is available

### Anisotropic Models (`vn`, `dir`, `mc`)
- **Description**: Direction-dependent conductivity based on DTI data
- **Requirements**: Diffusion tensor imaging (DTI) data processed through QSIPrep/QSIRecon
- **Applications**: More realistic modeling of white matter tracts
- **Processing**: Accounts for fiber orientation in field calculations

The anisotropy type is set via `SimulationConfig.conductivity` (or in the GUI dropdown). Two additional parameters control bounds:
- `aniso_maxratio` (default: 10.0) -- maximum ratio between eigenvalues
- `aniso_maxcond` (default: 2.0) -- maximum conductivity value

### DTI Data Preparation

The TI-Toolbox provides integrated DTI processing via QSIPrep and QSIRecon. The pipeline extracts diffusion tensors and converts them to the format required by SimNIBS.

#### Required Files

For anisotropic simulation, the following file must exist in the m2m directory:

```
derivatives/SimNIBS/sub-{id}/m2m_{id}/
└── DTI_coregT1_tensor.nii.gz    # 4D tensor (X, Y, Z, 6)
```

For complete DTI processing instructions, see the [Diffusion Processing]({{ site.baseurl }}/wiki/diffusion-processing/) documentation.

#### DTI Eigen Vectors Visualization

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/dti_CC.png" alt="DTI Eigen Vectors - Corpus Callosum" style="width: 80%; max-width: 500px;">
</div>
<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/dti_spinal.png" alt="DTI Eigen Vectors - Spinal Cord" style="width: 80%; max-width: 500px;">
</div>

<em>Gmsh visualizations showing white and gray matter with overlaid eigen vectors that scale conductivity in anisotropic simulations. Top: Corpus callosum region showing organized fiber directions. Bottom: Spinal cord region with longitudinal fiber orientation.</em>

These visualizations display the principal diffusion directions (eigen vectors) derived from diffusion tensor imaging (DTI) data, which are used to create direction-dependent conductivity tensors in anisotropic tissue modeling.

For additional details on DTI processing theory, see the [SimNIBS dwi2cond documentation](https://simnibs.github.io/simnibs/build/html/documentation/command_line/dwi2cond.html).

---

## Coordinate Spaces

### Subject Space
- **Definition**: Coordinates relative to individual subject anatomy
- **Origin**: Centered on subject's brain anatomy
- **Applications**: Subject-specific targeting and analysis
- **File Format**: Native FreeSurfer subject space coordinates

### MNI Space
- **Definition**: Standardized coordinate system (MNI152 template)
- **Origin**: Based on Montreal Neurological Institute template
- **Applications**: Cross-subject comparisons and group analysis
- **Transformations**: Automatic conversion between subject and MNI space

### Space Transformations
- **Automatic Conversion**: Built-in coordinate transformation utilities
- **ROI Mapping**: Support for both subject and MNI coordinate inputs
- **Visualization**: Compatible with both coordinate systems for analysis

## Output Layout and CLI

```
derivatives/SimNIBS/sub-{ID}/Simulations/{montage}/
├── documentation/config.json            # provenance snapshot used by the report
├── high_Frequency/{mesh,niftis,analysis} # per-channel SimNIBS outputs
├── TI/                                   # standard TI (2 pairs)
│   ├── mesh/{montage}_TI.msh, grey_*.msh, white_*.msh
│   ├── niftis/{montage}_TI_subject_TI_max.nii.gz (+ _MNI_ when MNI export is on)
│   ├── montage_imgs/{montage}_highlighted_visualization.png
│   └── surface_overlays/
└── mTI/                                  # multipolar TI (4+ pairs)
```

The GUI writes a JSON config and runs `simnibs_python -m tit.sim config.json`; the same command works from a shell (see [Scripting]({{ site.baseurl }}/wiki/scripting/) for the `SimulationConfig` fields).

## Report generation

Simulation reports are generated by the desktop GUI workflow after a simulation run. Programmatic simulation via `run_simulation()` or JSON config writes simulation outputs, but does not automatically create the HTML report unless the reporting API/GUI path is invoked separately.

Reports include montage tables and look for generated montage PNGs (`<montage>_highlighted_visualization.png` for TI/unipolar workflows and `combined_montage_visualization.png` for mTI). Missing montage images and optional nilearn/MNI field visualizations are reported as unavailable rather than silently omitted.
