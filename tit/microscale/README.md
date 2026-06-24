# `tit.microscale` — field → neuron coupling

Optional, research-grade module that drives **NEURON multicompartment neuron
models** with the macroscale TI/mTI electric field the simulator already
computes, so you can see how neurons in an ROI respond to the exposure —
accounting for both field **intensity and orientation**, not just magnitude.

> **Status:** experimental. The single-neuron NEURON coupling path. Whole-brain
> neural-mass / TVB coupling is intentionally out of scope (it discards the
> orientation information this module is built to preserve).

## Physics

Under the **quasi-static approximation** (valid for TI at ≤10 kHz; tissue
resistive, the FEM field independent of neuron dynamics), coupling is a
four-step recipe (Aberra et al. 2020; Shirinpour et al. 2021):

1. **place** a neuron at a target, soma on the cortical surface, apical axis
   along the surface normal;
2. **sample** the E-field vector at the soma (quasi-uniform approximation);
3. **integrate** it over the morphology to a quasipotential
   `Ve(c) = −E·l_c`, where `l_c` is the compartment's displacement from the
   soma (Wang et al. 2022, eq. used verbatim here);
4. **inject** `Ve` into NEURON's built-in `extracellular` mechanism and run.

For temporal interference the cell is driven by the **two kHz carriers** (not a
precomputed envelope), superposed per compartment:

```
Ve(c, t) = A · [ (E1·l_c)·sin(2π f1 t) + (E2·l_c)·sin(2π f2 t) ]
```

The envelope demodulation then **emerges** from the active membrane, because
passive low-pass filtering alone cannot produce it (Mirzakhalili et al. 2020;
Wang et al. 2022).

### Units & coordinates (read this before trusting a result)

- SimNIBS meshes are in **mm**; NEURON morphology is in **µm**. The sampler owns
  the conversion (`mm_to_um`/`um_to_mm`). A 1000× slip silently misplaces the
  neuron.
- SimNIBS `E` is in **V/m**, and `1 V/m == 1 mV/mm`, so dotting the field with a
  displacement in mm gives the potential directly in **mV** — exactly NEURON's
  `e_extracellular` unit.

## Neuron models & licensing

Two built-in models (both license-free, built on NEURON's `hh` + `extracellular`
mechanisms — no vendored assets, no `.mod` compilation):

- **`l5_pyramidal`** (default) — a procedurally generated, branched layer-5
  pyramidal cell: soma, branched basal dendrites, apical trunk + tuft, an axon
  initial segment and a myelinated axon with nodes of Ranvier. ~50 sections;
  renders like a real reconstruction (region-colored, Shirinpour et al. 2021
  Fig. 2D style). Deterministic; see `tit.microscale.morphology.pyramidal_l5`.
- **`ball_stick`** — a minimal soma + dendrite + axon (fast; for cheap
  threshold/response sweeps).

**Load real reconstructions.** Any SWC morphology (NeuroMorpho.org, or an
Aberra/Blue Brain export) can be loaded and used identically:

```python
from tit.microscale.models import load_swc_cell, register_model
cell = load_swc_cell("my_neuron.swc")          # ad hoc
# or register it as a named model:
register_model(spec, lambda: load_swc_cell("my_neuron.swc"))
```

The realistic Blue Brain / Aberra cortical morphologies used in the literature
are licensed **CC-BY-NC-SA** (non-commercial) and are therefore **not shipped** —
the procedural `l5_pyramidal` is the license-free default, and `load_swc_cell`
is the path for users who have obtained real cells under their own terms.

## Usage

```bash
simnibs_python -m tit.microscale config.json
```

`config.json`:

```json
{
  "mode": "response",
  "project_dir": "/path/to/project",
  "subject_ids": ["001"],
  "sim_name": "my_sim",
  "model": "ball_stick",
  "targets": [[-40.0, -20.0, 60.0]],
  "carrier_freqs": [2000.0, 2010.0],
  "duration": 100.0,
  "dt": 0.005
}
```

- `mode: "response"` → spike counts + per-cell polarization maps.
- `mode: "threshold"` → bisect the field amplitude to each target's firing
  threshold.

**Activation criterion.** Under a (quasi-)uniform field the lowest-threshold
elements are **axon terminals**, not the soma (Aberra et al. 2020), so a target
counts as activated when a spike occurs at the **spike-initiation site** (any
compartment), while the somatic trace is still returned for inspection.
Verified in-container on the default ball-stick cell: somatic firing requires a
proper axon initial segment / tuned kHz channels, which is why realistic
responses use user-registered cortical cells.

- `mode: "viz"` → publication-oriented visualizations per target.
- `mode: "population"` → an **unconnected population** over a cortical cluster.

Outputs land under `derivatives/SimNIBS/sub-<id>/microscale/<sim>/`:
`*_targets.csv`, `*_response.npz`, `*_polarization.npz`, `*_threshold.npz`.

### Visualizations (`mode: "viz"`)

Renders five artifacts per target (matplotlib, headless; no pyvista/VTK), using
the Shirinpour et al. 2021 palette, diameter-scaled neurites and a scale bar:

- `*_morphology.png` — the neuron's 3D morphology, colored by region (soma/
  basal/apical/tuft/axon/AIS/nodes).
- `*_cortex.png` — the neuron embedded in a patch of the subject's cortical
  surface at the target (colored by `TI_max`), oriented along the cortical normal.
- `*_efield.png` — the TI E-field as 3D vectors around the target, with the
  neuron for scale (shows the field is ~uniform at the cell scale).
- `*_quasipotential.png` — the neuron colored by the applied quasipotential Ψ
  on a diverging colormap (Shirinpour Fig. 2F style): the field-induced dipole
  along the morphology.
- `*_hodograph.png` — the **rotating TI modulation vector**: the instantaneous
  field `E(t) = E1·sin(ω1 t) + E2·sin(ω2 t)` traces a time-colored Lissajous in
  the E1–E2 plane (the two carriers beat at slightly different frequencies, so
  the resultant *rotates* over the beat cycle — a defining feature of TI).
- `*_clip.gif` — an animated clip: per-compartment membrane potential + the
  **rotating** instantaneous E-field arrow over time (the clip uses a
  lower-frequency, amplified drive so the envelope-tracking response is visible;
  the real-amplitude kHz drive is far sub-threshold).

## Population over a cortical cluster (`mode: "population"`)

For the standard subthreshold-polarization / activation question the field-coupling
literature uses an **unconnected population** of morphologically-realistic neurons,
not a single cell and not a connected network (Aberra 2018/2020; Seo & Jun 2017;
Shirinpour 2021). The quasi-uniform approximation licenses treating each neuron
independently — connectivity changes *emergent activity*, not direct polarization.

`run_population` (and `mode: "population"`) does exactly this:

1. **Analytic central estimate** — first-order somatic ΔVm = `coupling × E_normal`
   for **every** cluster vertex (cheap, vectorized). The coupling constant defaults
   to 0.27 mV/(V/m) for L5 pyramidal somata (Radman 2009; Bikson 2004 measured 0.12).
2. **NEURON distribution** — on a representative **subsample** of vertices, places
   `n_clones × n_azimuth` cells (clones = morphological variants; azimuths =
   rotations about the cortical normal to marginalize the unconstrained tangential
   angle) and solves the cable model to characterize the spread around the central
   estimate. **No synaptic connectivity.**

Outputs: `*_population.npz` (analytic map over all vertices + the subsample
distribution) and `*_population_summary.csv`.

> **Scope note.** This population model supports **subthreshold polarization /
> "priming"** claims with their cluster distribution. It does *not* model
> demodulation or recruitment into slow waves — those need an active **connected**
> network (Esmaeilpour 2021), a separate, larger project.

The plotting functions (`plot_morphology`, `plot_cell_in_cortex`,
`plot_efield_vectors`, `animate_response`) take plain NumPy arrays and are
reusable independently of the CLI.

A GUI front-end is available as the **Microscale** extension
(`tit/gui/extensions/microscale.py`).

## Validation targets (from the literature)

The implementation reproduces the Wang et al. (2022) coupling. Their reported
single-cell activation thresholds (L5 pyramidal, total E-field) are useful
sanity checks:

| Modality | Threshold (V/m) |
|---|---|
| Low-freq (10 Hz) | 16.9 – 47.4 |
| kHz (HFS / TIS / AM-HFS) | 75 – 230 |
| Conduction block (TIS) | ≳ 1700 |

The takeaway from that work — suprathreshold TIS needs scalp-infeasible fields
and tends to *block* rather than drive — is itself a result this pipeline lets
you explore on subject-specific fields.

## References

- Aberra, Wang, Grill, Peterchev (2020). *Brain Stimulation* 13(1):175–189.
  doi:10.1016/j.brs.2019.10.002
- Wang, Aberra, Grill, Peterchev (2022). *J. Neural Eng.* 19:066047.
  doi:10.1088/1741-2552/acab30
- Mirzakhalili et al. (2020). *Cell Systems* 11:557–572.
  doi:10.1016/j.cels.2020.10.004
- Shirinpour et al. (2021). *Brain Stimulation* 14(6):1470–1482.
  doi:10.1016/j.brs.2021.09.004
- Grossman et al. (2017). *Cell* 169:1029–1041. doi:10.1016/j.cell.2017.05.024
