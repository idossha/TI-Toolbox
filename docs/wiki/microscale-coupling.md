---
layout: wiki
title: Microscale Coupling
permalink: /wiki/microscale-coupling/
---

The **Microscale Coupling** module (`tit.microscale`) bridges the macroscale
electric field that the Simulator computes and the response of individual
cortical neurons. It answers a question the field-magnitude maps cannot:

> Given my TI/mTI montage, **how strongly — and in what sign — does the field
> polarize cortical neurons across a region, accounting for both intensity and
> orientation?**

The headline product is a **subthreshold cortical polarization map**: a per-vertex
estimate of the somatic membrane polarization `ΔVm` (in mV) that the field
induces over the cortical surface, refined on a NEURON-simulated subsample.

> **Status: experimental, research-grade.** This is an optional module
> (single-neuron scale). It is the right tool for *targeting and dose* questions
> about direct polarization. It does **not** predict action potentials, behaviour,
> or network-level effects — see [Scope & caveats](#scope--caveats).

---

## Why polarization, and not spike counts

It is tempting to ask "will my montage make neurons fire?" For realistic,
scalp-deliverable TI the honest answer — backed by the modeling literature — is
**no, not directly**, and a tool that reported spike counts at these field
strengths would be misleading. The numbers:

| Quantity | Value | Source |
|---|---|---|
| Scalp-deliverable TI envelope field at a human deep target | **~0.1 – 0.6 V/m** | Rampersad et al. 2019 |
| L5 pyramidal firing threshold, low-frequency (10 Hz) | **16.9 – 47.4 V/m** | Wang et al. 2022 |
| L5 pyramidal firing threshold, kHz / TIS / AM-HFS | **75 – 230 V/m** | Wang et al. 2022 |
| Conduction **block** (suprathreshold TIS) | **≳ 1700 V/m** | Wang et al. 2022 |

The deliverable field is **two-to-three orders of magnitude below** the threshold
for direct spiking. The only single-cell regime that is suprathreshold (block)
requires fields that **cannot be delivered through the scalp**, and would
*inhibit* rather than drive. So the physically meaningful readout is the
**subthreshold polarization** — fractions of a millivolt — which this module maps.

Reporting absolute spike counts/thresholds is also unreliable with the built-in
cells: they use NEURON's classic Hodgkin-Huxley channels, which Wang et al. 2022
explicitly call *"ill suited"* to kHz transcranial stimulation. The single-cell
demonstrator (`simulate_response` / `find_threshold`) is therefore kept only as a
fenced, library-only function — **not** a pipeline mode — and faithful thresholds
require registering a validated multi-channel cell (see
[Realistic cells](#plugging-in-realistic-cells)).

---

## The physics

Under the **quasi-static approximation** — valid for transcranial stimulation up
to ≥10 kHz, where tissue is resistive and the FEM field is independent of neuron
dynamics (Bossetti et al. 2008; Wang et al. 2024) — coupling a macroscale field
to a neuron is a short recipe (Aberra et al. 2018, 2020; Wang et al. 2022):

1. **Sample** the E-field vector at the soma. The neuron (tens–hundreds of µm) is
   small relative to the millimetre scale over which the macroscopic field varies,
   so it sees a locally **near-uniform** field.
2. **Integrate** the field along the morphology into a *quasipotential*
   `Ve(c) = −E · l_c`, where `l_c` is each compartment's displacement from the
   soma. (Injected into NEURON's `extracellular` mechanism for the refinement.)
3. For the central estimate, take the **first-order somatic polarization**, which
   is linear in the field component along the somatodendritic axis:

   ```
   ΔVm = coupling · E_normal
   ```

### The coupling constant

`coupling = 0.27 mV/(V/m)` is the value Radman et al. 2009 measured for a
representative **layer-5 pyramidal soma** at near-optimal orientation.

- It is **not a population mean** — across 51 cortical cells Radman et al. report
  a polarization length spanning roughly **−0.29 to +0.49** mV/(V/m). Bikson et
  al. 2004 measured **0.12** for hippocampal CA1. Treat `0.27` as a central value
  in a **~0.1–0.5 range**; it is exposed as the `polarization_coupling` parameter
  so you can substitute your own.
- It is the **somatic** value. Dendritic and axonal tips polarize *more*.
- Using **`E_normal`** (the field projected on the cortical surface normal) assumes
  the somatodendritic axis is aligned with that normal. This holds well at gyral
  crowns; on gyral walls and in sulci the axis tilts away, and tangential
  components (~15% effect on thresholds; Weise et al. 2023) are neglected.

### Units — the silent failure mode

- SimNIBS meshes are in **mm**; NEURON morphologies in **µm**. The sampler owns
  the conversion; a 1000× slip would misplace the cell in the wrong tissue.
- SimNIBS `E` is in **V/m**, and `1 V/m == 1 mV/mm`, so dotting the field with a
  displacement in mm yields the potential directly in **mV** — exactly NEURON's
  `e_extracellular` unit.

---

## The pipeline

`run_population` (CLI mode `polarization`) is a **two-tier** estimate over an
**unconnected** population of L5 pyramidal neurons — the accepted standard for
direct-polarization questions (Aberra et al. 2018, 2020; Seo & Jun 2017;
Shirinpour et al. 2021):

1. **Analytic central map (all vertices, no NEURON).** `ΔVm = coupling · E_normal`
   for *every* vertex of the TI central surface — cheap and vectorized. This is
   the headline map.
2. **NEURON refinement (a subsample).** At `n_subsample` representative vertices it
   places `n_clones × n_azimuth` cells (clones = morphological variants; azimuths
   = rotations about the cortical normal to marginalize the unconstrained
   tangential angle) and solves the cable model. This characterizes how morphology
   and orientation **spread** the polarization around the analytic value (the
   `amplification` factor) — it does **not** move the central estimate. There is
   **no synaptic connectivity**.

Set `n_subsample: 0` for an analytic-only run (instant, no NEURON needed).

---

## Usage

### GUI

Open the **Microscale** extension. Select one or more subjects and a completed
simulation, choose the neuron model and the coupling constant, optionally set a
cluster threshold on `TI_normal` (0 = whole surface), set the NEURON refinement
(subsample / clones / azimuths), and click **Run polarization map**.

### Command line (JSON config)

```bash
simnibs_python -m tit.microscale config.json
```

```json
{
  "mode": "polarization",
  "project_dir": "/mnt/my_project",
  "subject_ids": ["101"],
  "sim_name": "L_Insula",
  "model": "l5_pyramidal",
  "cluster_normal_field": "TI_normal",
  "cluster_threshold": null,
  "n_subsample": 50,
  "n_clones": 5,
  "n_azimuth": 6,
  "polarization_coupling": 0.27
}
```

### Python API

```python
from tit import get_path_manager
from tit.microscale import PopulationConfig, run_population

get_path_manager("/mnt/my_project")
cfg = PopulationConfig(
    sim_name="L_Insula",
    cluster_threshold=0.15,   # V/m on TI_normal; None = whole surface
    n_subsample=30,
)
result = run_population("101", cfg)
print(result["summary"])
```

The pure analytic map needs neither NEURON nor SimNIBS:

```python
import numpy as np
from tit.microscale import analytic_polarization_map, DEFAULT_COUPLING_MV_PER_VM

e_normal = np.array([0.1, -0.2, 0.3])           # V/m per vertex
dvm = analytic_polarization_map(e_normal, DEFAULT_COUPLING_MV_PER_VM)  # mV
```

---

## Outputs

Written to `derivatives/SimNIBS/sub-<id>/microscale/<sim>/`:

| File | Contents |
|---|---|
| `…_polarization.msh` | ΔVm as a node field on the TI central surface — loads in **gmsh** / the SimNIBS viewer alongside `TI_normal` |
| `…_polarization.gii` | ΔVm as a **GIFTI** overlay — loads in **FreeView** / Connectome Workbench |
| `…_summary.csv` | the readable region table: ΔVm mean / median / 5th–95th percentile / peak, peak \|E_normal\|, and the **subthreshold margin** (how far the peak field sits below the firing threshold) |
| `…_polarization.npz` | the full arrays: analytic map (all vertices), cluster indices, and the NEURON-subsample ΔVm + amplification distribution |
| `…_polarization.png` | the default two-panel figure: the cortical patch colored by ΔVm next to the ΔVm histogram, annotated with the threshold margin |
| `…_population.png` | a standalone **meso-scale population** figure — **one L5 pyramidal cell per vertex** of the analyzed ROI (the thresholded cluster, or a window around the field focus when the whole surface is analyzed), oriented to the local normal and colored by neurite type. Capped at `max_cells` (default 2500) for the densest ROIs; `render_population` |
| `…_polarization.gif` | a **time-domain animation** at the focus — the neuron colored by the instantaneous applied quasipotential Ψ, the **rotating** TI field vector, and the carrier oscillation filling its 10 Hz beat envelope (`render_video`) |

The surface overlays are best-effort and skip gracefully if the surface or a
dependency is missing. The `.msh`/`.gii` files use the same conventions as the
rest of the toolbox so the polarization map drops into your existing viewers. The
two extra figures are on by default; disable with `render_population=False` /
`render_video=False`.

### TI envelope vs. the two high-frequency fields

A montage is two electrode pairs, each driven at a slightly different kHz carrier
(e.g. 2000 and 2010 Hz). SimNIBS reports two things you can couple to:

- the **TI envelope** (`TI_max`, `TI_normal`) — the amplitude-modulation *depth*
  of the combined field, a **static** scalar;
- the two **HF pair fields** (`TDCS_1`, `TDCS_2`) — each carrier's vector field.

The **polarization map uses the TI envelope's normal component** (`TI_normal`):
it is the standard subthreshold quantity, it is what the rest of the toolbox
visualizes, and a static map needs a single amplitude per vertex.

The **time-domain video uses the two HF fields**, because the defining features
of TI — the resultant field *rotating* over the beat, and the *envelope*
emerging from the superposition — exist only in the two carriers. The envelope is
*derived* from them and has no time axis, so it cannot show the oscillation. In
short: **envelope for the static map, the two carriers for anything temporal.**
(And per Mirzakhalili et al. 2020, whether a real neuron *follows* that envelope
depends on active-channel rectification — which is why the video shows the
applied drive, not a claimed membrane response.)

### Optional publication figure

A *populated-gyrus* render — many L5 cells embedded in a named GM region, oriented
to the cortical normal and colored by neurite type — is available via
`render_population_region` with a typed `RegionSpec` (atlas label / MNI sphere /
binary mask):

```python
from tit.microscale import RegionSpec, render_population_region
render_population_region(
    "101", cfg, out_dir,
    RegionSpec(kind="atlas", atlas="DK40", label="insula", hemi="lh"), "insula",
)
```

---

## Interpreting results — what to expect

- **ΔVm of fractions of a mV** at scalp-realistic fields. This is the correct,
  physical regime — not a sign of weak coupling.
- **Do not expect predicted firing.** If a run reports spikes, you are either
  using unrealistically high fields or the fenced single-cell demonstrator.
- The map shows **where** the field couples most strongly — gyral crowns,
  orientation-dependent — which is useful for **relative targeting and focality
  comparisons** between montages.
- **Sign matters.** ΔVm is signed: positive = depolarizing (toward firing),
  negative = hyperpolarizing. The diverging colormap centers on zero.
- The **subthreshold margin** in the summary (e.g. "≈ 60× below threshold") is the
  honest framing of magnitude.

---

## Scope & caveats

What an unconnected, subthreshold-polarization model **can** claim:

- The direct, first-order polarization of individual cells given field intensity
  and orientation.
- Which regions / orientations couple most strongly (relative targeting).

What it **cannot** claim (out of scope):

- **Action potentials / behaviour** at realistic fields.
- **Network-level effects** — oscillation entrainment, recruitment into slow
  waves, plasticity, or the TI-selectivity mechanism that depends on network and
  membrane time constants (Esmaeilpour et al. 2021). Those need a *connected*
  network and are a separate, larger problem.
- **Envelope demodulation.** A passive membrane does *not* demodulate the kHz TI
  envelope; following it requires active ion-channel rectification (Mirzakhalili
  et al. 2020), which the default cells do not faithfully reproduce.
- **Absolute thresholds** from the built-in vanilla-HH cells (Wang et al. 2022).

---

## Plugging in realistic cells

The built-in `l5_pyramidal` is procedurally generated and license-free. Realistic
Blue Brain / Aberra cortical reconstructions are licensed CC-BY-NC-SA
(non-commercial) and are therefore **not bundled**. Load any SWC reconstruction
(e.g. from NeuroMorpho.org), or register a validated multi-channel cell — required
for any trustworthy *absolute* threshold:

```python
from tit.microscale.models import load_swc_cell, register_model
cell = load_swc_cell("my_neuron.swc")            # ad hoc
register_model(spec, lambda: load_swc_cell("my_neuron.swc"))   # named model
```

---

## Key API

| Symbol | Purpose |
|---|---|
| `PopulationConfig` | configuration for the polarization-map pipeline |
| `run_population(sid, cfg)` | run the pipeline; write the outputs |
| `analytic_polarization_map(e_normal, coupling)` | the closed-form ΔVm map (pure NumPy) |
| `region_summary(result)` | the region-level statistics dict |
| `RegionSpec` | atlas / sphere / mask region for the populated-gyrus figure |
| `uniform_quasipotential`, `place_morphology`, `sample_at` | NEURON-free coupling primitives |
| `load_swc_cell`, `register_model` | plug in realistic cells |
| `simulate_response`, `find_threshold` | *experimental* single-cell demonstrator (not quantitatively faithful) |

Full signatures are in the [API Reference](../api/).

---

## References

1. Bossetti, Birdno & Grill (2008). Analysis of the quasi-static approximation for calculating potentials generated by neural stimulation. *J. Neural Eng.* 5(1):44–53. [doi:10.1088/1741-2560/5/1/005](https://doi.org/10.1088/1741-2560/5/1/005)
2. Bikson et al. (2004). Effects of uniform extracellular DC electric fields on excitability in rat hippocampal slices in vitro. *J. Physiol.* 557(1):175–190. [doi:10.1113/jphysiol.2003.055772](https://doi.org/10.1113/jphysiol.2003.055772)
3. Radman, Ramos, Brumberg & Bikson (2009). Role of cortical cell type and morphology in subthreshold and suprathreshold uniform electric field stimulation in vitro. *Brain Stimul.* 2(4):215–228. [doi:10.1016/j.brs.2009.03.007](https://doi.org/10.1016/j.brs.2009.03.007)
4. Aberra, Peterchev & Grill (2018). Biophysically realistic neuron models for simulation of cortical stimulation. *J. Neural Eng.* 15(6):066023. [doi:10.1088/1741-2552/aadbb1](https://doi.org/10.1088/1741-2552/aadbb1)
5. Aberra, Wang, Grill & Peterchev (2020). Simulation of transcranial magnetic stimulation in head model with morphologically-realistic cortical neurons. *Brain Stimul.* 13(1):175–189. [doi:10.1016/j.brs.2019.10.002](https://doi.org/10.1016/j.brs.2019.10.002)
6. Wang, Aberra, Grill & Peterchev (2022). Responses of model cortical neurons to temporal interference stimulation and related transcranial alternating current stimulation modalities. *J. Neural Eng.* 19(6):066047. [doi:10.1088/1741-2552/acab30](https://doi.org/10.1088/1741-2552/acab30)
7. Mirzakhalili, Barra, Capogrosso & Lempka (2020). Biophysics of Temporal Interference Stimulation. *Cell Systems* 11(6):557–572. [doi:10.1016/j.cels.2020.10.004](https://doi.org/10.1016/j.cels.2020.10.004)
8. Shirinpour et al. (2021). Multi-scale modeling toolbox for single neuron and subcellular activity under transcranial magnetic stimulation (NeMo-TMS). *Brain Stimul.* 14(6):1470–1482. [doi:10.1016/j.brs.2021.09.004](https://doi.org/10.1016/j.brs.2021.09.004)
9. Seo & Jun (2017). Multi-scale computational models for electrical brain stimulation. *Front. Hum. Neurosci.* 11:515. [doi:10.3389/fnhum.2017.00515](https://doi.org/10.3389/fnhum.2017.00515)
10. Esmaeilpour et al. (2021). Temporal interference stimulation targets deep brain regions by modulating neural oscillations. *Brain Stimul.* 14(1):55–65. [doi:10.1016/j.brs.2020.11.007](https://doi.org/10.1016/j.brs.2020.11.007)
11. Weise et al. (2023). Directional sensitivity of cortical neurons towards TMS-induced electric fields. *Imaging Neuroscience* 1:1–22. [doi:10.1162/imag_a_00036](https://doi.org/10.1162/imag_a_00036)
12. Rampersad et al. (2019). Prospects for transcranial temporal interference stimulation in humans: a computational study. *NeuroImage* 202:116124. [doi:10.1016/j.neuroimage.2019.116124](https://doi.org/10.1016/j.neuroimage.2019.116124)
13. Grossman et al. (2017). Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields. *Cell* 169(6):1029–1041. [doi:10.1016/j.cell.2017.05.024](https://doi.org/10.1016/j.cell.2017.05.024)
14. Wang et al. (2024). Quasistatic approximation in neuromodulation. *J. Neural Eng.* 21(4):041002. [doi:10.1088/1741-2552/ad625e](https://doi.org/10.1088/1741-2552/ad625e)
