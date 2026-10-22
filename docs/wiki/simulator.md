---
layout: wiki
title: Simulator
permalink: /wiki/simulator/
---

The Simulator computes the full FEM temporal interference field. It sits between the optimizers and the analyzer: take a montage from the montage list or from a [flex-search]({{ site.baseurl }}/wiki/flex-search/) or [ex-search]({{ site.baseurl }}/wiki/ex-search/) result, or placed by hand and simulate it here. Then, quantify the resulting field with the [Analyzer]({{ site.baseurl }}/wiki/analyzer/). It can be invoked programmatically via `run_simulation()` or through a JSON config entrypoint.

## In the application

<img src="{{ site.baseurl }}/assets/imgs/v3/simulator-run-page.png" alt="The Simulator page: one row per simulation job, with the selected montage drawn on the packaged guide head in the Scene pane" style="width: 100%; max-width: 1000px;">
<em>The Simulator (⌘3). One row is one job. The pane draws the active row's montage: a named montage on the packaged guide head, a free-hand or optimised (XYZ) placement on the subject's own head.</em>

- **Jobs**: one row per simulation, each with its own **Subject** and **Source**: `Montage`, `Flex result` or `Free-hand` (see [Montage Sources](#montage-sources)). Line 2 of a row lists its channels (electrode pairs), each with its own current field in mA. **Add job** adds a row; the copy button duplicates one.
- **TI or mTI**: not a control. It is read off the number of pairs: 2 pairs run standard TI, 4, 6, 8 … run mTI (see [How the Toolbox Detects mTI](#how-the-toolbox-detects-mti)).
- **Montages**: **New montage**, the pencil **Edit** on a Montage row, and **Manage montages**, which deletes saved montages and free-hand placements (see [Montage Sources](#montage-sources)). **New placement** opens the [free-hand placement editor]({{ site.baseurl }}/wiki/electrode-placement/).
- **Job settings**: electrodes, conductivity, output fields, the carrier-only control and standard-space outputs, per job (see [Job settings](#job-settings)).
- **Real-time Logging**: Simulation progress and status updates

---

## Montage Sources

A job row's **Source** says where its electrodes come from:

### 1. Montage List

Named montages saved per EEG net. Pick the row's **EEG net**, then a **Montage**; the list shows only that net's montages.

- **Standard TI**: 2 pairs (4 electrodes, 2 channels)
- **mTI**: an even number of 4 or more pairs (8, 12, … electrodes)
- **New montage**: choose a net, name the montage and pick its electrode pairs from the net's labels, or click electrodes in the pane to fill the pairs. Its polarity (TI or mTI) is shown, not chosen.
- **Edit**: the pencil on a Montage row opens that montage in the same editor, which can also delete it.
- **Manage montages**: delete saved montages (per net) and [free-hand placements]({{ site.baseurl }}/wiki/electrode-placement/) (per subject), one at a time or several at once. Existing simulation results are kept.

### 2. Flex Mode

A finished [flex-search]({{ site.baseurl }}/wiki/flex-search/) run of the row's subject. Pick the **Flex run**, then its **Placement**:

- **Optimised (XYZ)**: the run's own free electrode positions, drawn on the subject's head.
- **An EEG net**: any of the subject's nets. The positions are mapped onto that net when you choose it (see [Electrode mapping]({{ site.baseurl }}/wiki/electrode-mapping/)).

The row starts with the run's own currents (its optimised current split when the ratio search ran), which you can edit. Flex-derived simulations keep a unique run ID in their folder name, while the table shows a short display name.

### 3. Free-Hand

A placement you clicked onto the subject's scalp or typed in, saved per subject: pick the **Free-hand set**. **New placement** opens the [placement editor]({{ site.baseurl }}/wiki/electrode-placement/).

### Ex-search results and evaluated candidates

To simulate an [ex-search]({{ site.baseurl }}/wiki/ex-search/) result, open the run in **Results ▸ Evaluated candidates**, select a candidate and press **Use in Simulator**. This works for Ex and mEx runs as well as Flex runs. An Ex or mEx candidate arrives as a Montage row on its net with the candidate's currents; a Flex candidate arrives as a Flex row whose **Placement** can snap it to a net. Nothing runs until you press **Run simulation**.

### Available EEG Nets

Pre-processing places every EEG net in the image on the head model, so no manual registration step is needed; the same nets serve montages, flex-search electrode mapping and leadfield generation. A row lists the nets in the subject's `m2m_<id>/eeg_positions/`.

| Shipped by | Nets |
| ---------- | ---- |
| TI-Toolbox | `GSN-HydroCel-128`, `GSN-HydroCel-185`, `GSN-HydroCel-256`, `BioSemi-64-10-10`, `BioSemi-128-A1`, `BioSemi-256-A1` |
| SimNIBS    | `EEG10-10_UI_Jurak_2007`, `EEG10-10_Cutini_2011`, `EEG10-10_Neuroelectrics`, `EEG10-20_Okamoto_2004`, `EEG10-20_extended_SPM12`, `easycap_BC_TMS64_X21` |

To add a net to a head model that already exists, such as a cap corrected in a later release or your own MNI cap, use the [EEG caps]({{ site.baseurl }}/wiki/eeg-caps/) panel instead of re-running pre-processing. The GSN-HydroCel-128 and BioSemi caps were corrected in v3.1.1; re-apply them to head models built earlier.

---

## Job settings

Open a job's settings with the row's settings button, or double-click the row. A new row starts from the settings you configured last.

- **Electrodes**: **Shape** (Ellipse or Rectangle), **Dimensions** (width × height, mm) and **Gel thickness**. Defaults: ellipse, 8 × 8 mm, 4 mm gel.
- **Conductivity**: the **Model** and, for the anisotropic models, its bounds (see [Conductivity and Anisotropy](#conductivity-and-anisotropy)). **Edit values…** overrides the per-tissue conductivities for this job only.
- **Output fields**: see [Output Fields](#output-fields) and [Carrier-only control](#carrier-only-control).
- **Standard-space outputs**: **Generate MNI NIfTI outputs** (off by default) also writes the fields and the T1 in MNI space. The MNI-space group tools read these files: [cluster permutation testing]({{ site.baseurl }}/wiki/cluster-permutation-testing/), [NIfTI group averaging]({{ site.baseurl }}/wiki/nifti-group-averaging/) and [Nilearn visuals]({{ site.baseurl }}/wiki/nilearn-visuals/). **Map fields to fsaverage** (off by default in the app; `map_to_fsavg` defaults to `True` in Python) projects the fields to fsaverage5 after simulation, for TI and mTI alike. The result is `fsaverage/sub-<id>_sim-<sim>_space-fsaverage5_fields.msh` in the simulation folder, a surface mesh you can open in the Viewer or Gmsh (see [Extensions]({{ site.baseurl }}/wiki/extension/)).

---

## Simulation Modes

### Unipolar Mode

- **Configuration**: Two electrode pairs (four electrodes), forming two channels whose slightly different frequencies produce the TI envelope
- **Current Settings**: One current magnitude per channel; each channel has an active and return electrode
- **Applications**: Standard two-channel temporal interference stimulation
- **Montage Compatibility**: Works with unipolar montage collections

### Multipolar Mode (mTI)

Multipolar temporal interference (mTI) uses 8 or more electrodes: each two channels (electrode pairs) share a carrier, and the carriers' phase-aligned beats combine into one modulation envelope (Botzanowski et al. 2025). Channels and carriers are explained under [Quantities of Interest on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#quantities-of-interest).

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

TI vs. mTI is not a setting: it is read off how many channels (electrode pairs) a montage has.

- **2 channels**: standard TI
- **4, 6, 8 … channels**: mTI, up to 26 channels (labelled A–Z)
- **A single pair or an odd number of pairs** is rejected: every carrier needs two channels. The error reads "Expected an even number of electrode pairs, at least 2 (2 = TI, 4 or more = mTI)".

Saved montages are kept per EEG net, with TI and mTI montages listed separately.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/simulator/multipolar.png" alt="Multipolar Montage Example">
  <em>A multipolar montage: 8 electrodes forming 4 channels on 2 carriers.</em>
</div>

#### Channels and Carriers

The assignment is always positional: each two consecutive electrodes in the montage compose a channel, and each two consecutive channels compose a carrier. For an 8-electrode montage that means channels A & B share the first carrier and channels C & D the second — there is no wiring choice to make.

The kHz-exposure safety metrics `hf_peak`/`hf_sar` include every channel field under the shipped positional wiring (one field per carrier). Their math lives under [Safety Metrics on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#safety-metrics).

#### Simulator Behavior for mTI

Each channel is driven at its own current: an mTI row shows one current field per channel on line 2 of the job row.

On disk, the mTI mesh spells the modulation-depth field `mTI_max`: the same quantity `TI_max` names on a standard TI mesh, under a different name for the multipolar case.

**TI_normal is computed for mTI too**: the same multi-carrier envelope evaluated along the cortical surface normal, written as `{montage}_mTI_normal.msh` in `mTI/mesh/`. **fsaverage projection covers mTI as well**: it reads the modulation depth from the mTI central surface (`mTI_max`) and derives `hf_peak`/`hf_sar` from all channel meshes.

An mTI simulation:

1. Crops every channel's high-frequency mesh to brain tissue. The channel meshes are in `high_Frequency/mesh/`, named by channel letter (`TDCS_A`, `TDCS_B`, …).
2. Writes an intermediate per-carrier envelope for each two consecutive channels (`{montage}_TI_AB.msh`, `{montage}_TI_CD.msh`, …). These are for inspection only and are **not** recombined into the final result: a recursive TI-of-TI recombination is not a valid envelope.
3. Computes the final envelope over all channel fields jointly, written as `mTI_max`, plus `TI_avg`, `hf_peak` and `hf_sar` when selected.
4. Extracts grey- and white-matter crops (`grey_{montage}_mTI.msh`, `white_{montage}_mTI.msh`) and a central cortical surface, and converts the meshes to NIfTI.

**References:** Albantakis, L. & Tononi, G. (2026). Precision neuromodulation in psychiatry: focus on temporal interference stimulation. _American Journal of Psychiatry_. doi:10.1176/appi.ajp.20250873. Botzanowski, B. et al. (2025). Focal control of non-invasive deep brain stimulation using multipolar temporal interference. _Bioelectronic Medicine_ 11(1):7.

---

## Output Fields

The **Output fields** in a job's settings choose which volume-mesh fields are computed and written, for TI and mTI alike: `TI_max` (ticked by default), `TI_avg`, `hf_peak` and `hf_sar`. At least one must be ticked ("Select at least one output field."). An unticked field is never computed, not merely left unwritten. From Python the same choice is `SimulationConfig.output_fields`, default `["TI_max"]`.

What each field _means_ — the beat-envelope modulation depth, the direction-averaged envelope, and the carrier-exposure safety metrics — is documented once, under [Quantities of Interest on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#quantities-of-interest).

## Carrier-only control (ΔF = 0) {#carrier-only-control}

A carrier-only control delivers the same two kHz carriers as a TI montage but at the **same** frequency and in phase (e.g. 15,000 / 15,000 Hz instead of 15,000 / 15,010 Hz), so there is no interference beat. Use it for carrier-only or sham-style control conditions: the tissue receives kHz exposure without an envelope.

Without a beat the two carriers add coherently into one fixed field, so the exposure metrics become $$\mathrm{hf\_peak} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert$$ and $$\mathrm{hf\_sar} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert^2$$ rather than the TI worst case $$\max(\lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert)$$ (Cassarà et al. 2025, _Bioelectromagnetics_: Part I 46(2), e22542; Part II 46(1), e22536). The envelope fields `TI_max`, `TI_avg` and `TI_normal` are undefined and are not computed. The derivation and a worked example are under [Carrier-only controls on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#carrier-only-controls).

- **In the application**: open a job's settings (the row's **Job settings** button) and tick **Carrier-only control (ΔF = 0, coherent carriers)** under *Output fields*. `hf_peak` and `hf_sar` are selected, and `TI_max`/`TI_avg` are disabled while it is on. The checkbox is disabled for mTI (4 or more pairs) montages; an mTI row seeded from a carrier-only job runs as ordinary mTI.
- **From Python or a JSON config**:

```python
from tit.sim import SimulationConfig, run_simulation

cfg = SimulationConfig(
    subject_id="101",
    montages=montages,              # 2-pair TI montages only
    intensities=[1.0, 1.0],
    carrier_only=True,
    output_fields=["hf_peak", "hf_sar"],
)
run_simulation(cfg)
```

`SimulationConfig` rejects `carrier_only=True` with any envelope output field or with an mTI montage, and `POST /api/validate/sim` reports the same errors. The run records `carrier_only` and `output_fields` in `documentation/config.json`, so a result says how it was computed.

---

## Conductivity and Anisotropy

**Conductivity ▸ Model** in a job's settings (`conductivity` on `SimulationConfig`) selects one of four tissue conductivity models:

| Type              | Code     | Description                                             | Requirements                              |
| ----------------- | -------- | ------------------------------------------------------- | ----------------------------------------- |
| Scalar            | `scalar` | Isotropic, piecewise-constant (default)                 | None — used when no DTI data is available |
| Volume Normalized | `vn`     | Normalized tensors scaled by tissue conductivity        | DTI tensor                                |
| Direct            | `dir`    | Direct linear rescaling of diffusion tensor eigenvalues | DTI tensor                                |
| Mean Conductivity | `mc`     | Isotropic but spatially varying, from tensor volumes    | DTI tensor                                |

The anisotropic models account for fiber orientation, giving more realistic modeling of white matter tracts. Two bounds apply to them, shown in the job's settings once an anisotropic model is chosen: **Max ratio** (`aniso_maxratio`, default 10, maximum ratio between eigenvalues) and **Max conductivity** (`aniso_maxcond`, default 2 S/m).

### DTI Data Preparation

The TI-Toolbox provides integrated DTI processing: QSIPrep preprocesses the diffusion data and the DTI step fits the tensor with DIPY and writes it in the format SimNIBS reads. For anisotropic simulation, the following file must exist in the m2m directory:

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

<em>White and gray matter with overlaid eigen vectors that scale conductivity in anisotropic simulations. Top: Corpus callosum region showing organized fiber directions. Bottom: Spinal cord region with longitudinal fiber orientation.</em>

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

NIfTI exports are written in subject space by default. Enable **Generate MNI NIfTI outputs** beside the fsaverage option in job settings to also export MNI fields and the MNI anatomical reference — ROI inputs elsewhere in the toolbox accept either space, with automatic transformation between them.

The app runs each job as `simnibs_python -m tit.sim config.json` in the container; the same command works from a shell (see [Scripting]({{ site.baseurl }}/wiki/scripting/) for the `SimulationConfig` fields).

## Report generation

Every simulated montage writes a simulation report, from the app, `run_simulation()` or a JSON config alike: the grey-matter envelope and where its maximum is, the montage on the EEG cap with its dose (on nets with a cap diagram; see [Montage Visualizer]({{ site.baseurl }}/wiki/montage_visualizer/)), and the envelope in three planes. Rebuild one without re-simulating with `simnibs_python -m tit.reporting.generators.simulation <project> <subject> <simulation>`. See [Reports]({{ site.baseurl }}/wiki/reports/).
