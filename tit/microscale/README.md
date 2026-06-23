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

## Neuron model & licensing

The default model is an **authored ball-and-stick cortical neuron** built
procedurally with NEURON's built-in `hh` (active) and `extracellular`
mechanisms — no vendored assets, no `.mod` compilation, no third-party license.

The realistic Blue Brain / Aberra cortical morphologies used in the literature
are licensed **CC-BY-NC-SA** (non-commercial, share-alike) and are therefore
**not shipped**. A user who has obtained them under their own terms can register
a custom cell:

```python
from tit.microscale.models import register_model, NeuronModelSpec
register_model(my_spec, my_builder)   # my_builder() -> tit.microscale.Cell
```

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

Outputs land under `derivatives/SimNIBS/sub-<id>/microscale/<sim>/`:
`*_targets.csv`, `*_response.npz`, `*_polarization.npz`.

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
