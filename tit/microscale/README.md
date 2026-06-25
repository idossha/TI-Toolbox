# `tit.microscale` — cortical polarization map

Optional, research-grade module that maps a completed TI/mTI simulation's
electric field to the **subthreshold polarization of cortical neurons** —
the per-vertex somatic ΔVm the field induces across a region, accounting for both
field **intensity and orientation**, not just magnitude.

> **Status:** experimental, single-neuron scale. Whole-brain neural-mass / TVB
> coupling is intentionally out of scope (it discards the orientation
> information this module preserves), and so are network-level effects
> (entrainment, recruitment, TI selectivity — Esmaeilpour et al. 2021).

## What it computes (and why this and not spike counts)

The headline product is a **cortical polarization map**: for every vertex of the
TI central surface, the first-order somatic membrane polarization

```
ΔVm = coupling · E_normal        coupling ≈ 0.27 mV/(V/m)  (L5 PC, Radman 2009)
```

This is the *robust, literature-grounded* quantity for realistic TI. Scalp-
deliverable human TI envelope fields at depth are ~0.1–0.6 V/m (Rampersad et al.
2019) — two-to-three orders of magnitude **below** the ~17–230 V/m needed to make
an L5 pyramidal cell fire (Wang et al. 2022). So the honest readout is *how
strongly, and in what sign, the montage polarizes neurons* — not predicted
spikes. Absolute spike-count / firing-threshold modeling is deliberately **not**
the headline: the built-in cells use NEURON's vanilla Hodgkin-Huxley channels,
which Wang et al. 2022 call "ill suited" to kHz stimulation, so those numbers are
only a qualitative demonstrator (kept as fenced library functions —
`simulate_response` / `find_threshold` — not a CLI mode).

## Physics

Under the **quasi-static approximation** (valid for tES/TI to ≥10 kHz; tissue
resistive, the FEM field independent of neuron dynamics; Bossetti et al. 2008;
Wang et al. 2024), coupling is (Aberra et al. 2018/2020; Wang et al. 2022):

1. **sample** the E-field vector at the soma (locally near-uniform at cell scale);
2. **integrate** it over the morphology to a quasipotential `Ve(c) = −E·l_c`
   (`l_c` = compartment displacement from the soma);
3. for the central estimate, take the **first-order somatic polarization**
   `ΔVm = coupling · E_normal`, linear in the field (Radman et al. 2009).

A **NEURON subsample** then refines this: it places `n_clones × n_azimuth` L5
cells at a representative subset of vertices and solves the cable model, to
characterize how morphology and orientation spread the polarization around the
analytic estimate. **It does not move the central estimate**, and there is no
synaptic connectivity (the accepted standard for direct polarization; Aberra et
al. 2018/2020; Seo & Jun 2017; Shirinpour et al. 2021).

### Units (read this before trusting a result)

- SimNIBS meshes are in **mm**; NEURON morphology is in **µm**. The sampler owns
  the conversion (`mm_to_um`/`um_to_mm`). A 1000× slip silently misplaces the cell.
- SimNIBS `E` is in **V/m**, and `1 V/m == 1 mV/mm`, so dotting the field with a
  displacement in mm gives the potential directly in **mV** — NEURON's
  `e_extracellular` unit.

### The coupling constant (caveats)

`0.27 mV/(V/m)` is the **single representative** L5 pyramidal soma of Radman et
al. 2009 at **near-optimal orientation** — not a population mean (their 51 cells
span ≈ −0.29…+0.49). Bikson et al. 2004 measured `0.12` for hippocampal CA1.
Treat it as a central value in a ~0.1–0.5 range. Using `E_normal` assumes the
somatodendritic axis ≈ the cortical surface normal (good at gyral crowns; an
approximation on walls/sulci), and tangential components (~15 %; Weise et al.
2023) are neglected.

## Usage

```bash
simnibs_python -m tit.microscale config.json
```

`config.json`:

```json
{
  "mode": "polarization",
  "project_dir": "/path/to/project",
  "subject_ids": ["001"],
  "sim_name": "my_sim",
  "model": "l5_pyramidal",
  "cluster_normal_field": "TI_normal",
  "cluster_threshold": null,
  "n_subsample": 50,
  "n_clones": 5,
  "n_azimuth": 6,
  "polarization_coupling": 0.27
}
```

`cluster_threshold: null` maps the whole surface; set e.g. `0.15` (V/m on
`TI_normal`) to focus the cluster. `n_subsample: 0` is analytic-only (no NEURON).

A GUI front-end is the **Microscale** extension
(`tit/gui/extensions/microscale.py`).

### Outputs

Under `derivatives/SimNIBS/sub-<id>/microscale/<sim>/`:

| File | Contents |
|---|---|
| `…_polarization.msh` | ΔVm as a node field on the TI central surface (loads in gmsh / SimNIBS) |
| `…_polarization.gii` | ΔVm as a GIFTI overlay (loads in FreeView / Connectome Workbench) |
| `…_summary.csv` | region table: ΔVm mean/median/percentiles/peak, peak \|E_normal\|, and the subthreshold margin vs the firing threshold |
| `…_polarization.npz` | full arrays: analytic map (all vertices), cluster indices, NEURON-subsample ΔVm + amplification |
| `…_polarization.png` | the default figure: cortical patch colored by ΔVm + the ΔVm histogram |
| `…_population.png` | standalone meso-scale figure: **one L5 cell per vertex** of the analyzed ROI (the thresholded cluster, or a focus window when the whole surface is analyzed), capped at `max_cells`; `render_population=True` |
| `…_polarization.gif` | time-domain animation at the focus: the cell colored by the applied quasipotential Ψ, the rotating TI field vector, and the carrier/beat trace (`render_video=True`) |

The `.msh`/`.gii` overlays and the `.png`/`.gif` figures are best-effort (skip
gracefully if the surface/dep is absent). Disable the extra figures with
`render_population=False` / `render_video=False`. An optional *populated gyrus*
over a named region is available via `render_population_region` with a
`RegionSpec` (atlas label / MNI sphere / binary mask).

### TI envelope vs the two HF fields

The static **map** uses the simulator's `TI_normal` — the normal component of the
TI *envelope* (modulation depth), the standard subthreshold quantity. The
time-domain **video** must instead use the two **HF pair fields** (`TDCS_1`/
`TDCS_2`, each a carrier): the rotation of the resultant and the beat *only exist*
in the superposition of the two carriers — the envelope is a derived static
amplitude with no time axis. So both are used, each for what it is correct for.

## Plugging in realistic cells

The built-in `l5_pyramidal` is procedural and license-free. Realistic Blue Brain
/ Aberra cortical reconstructions are CC-BY-NC-SA (non-commercial) and are **not
shipped**; load any SWC reconstruction, or register a validated multi-channel
cell for trustworthy thresholds:

```python
from tit.microscale.models import load_swc_cell, register_model
cell = load_swc_cell("my_neuron.swc")
register_model(spec, lambda: load_swc_cell("my_neuron.swc"))
```

## What to expect

- ΔVm of **fractions of a mV** at scalp-realistic fields — the correct, physical
  regime. **Do not expect predicted firing**; if you see it, you are using
  unrealistically high fields or the fenced demonstrator.
- The map shows **where** the field couples most strongly (gyral crowns,
  orientation-dependent) — useful for *relative targeting / focality*, not for
  predicting evoked spikes.
- Suprathreshold TI is a **blocking** regime (>1700 V/m) undeliverable through
  the scalp (Wang et al. 2022).

## References

- Bossetti, Birdno & Grill (2008). *J. Neural Eng.* 5:44–53. doi:10.1088/1741-2560/5/1/005
- Radman, Ramos, Brumberg & Bikson (2009). *Brain Stimul.* 2:215–228. doi:10.1016/j.brs.2009.03.007
- Bikson et al. (2004). *J. Physiol.* 557:175–190. doi:10.1113/jphysiol.2003.055772
- Aberra, Peterchev & Grill (2018). *J. Neural Eng.* 15:066023. doi:10.1088/1741-2552/aadbb1
- Aberra, Wang, Grill & Peterchev (2020). *Brain Stimul.* 13:175–189. doi:10.1016/j.brs.2019.10.002
- Wang, Aberra, Grill & Peterchev (2022). *J. Neural Eng.* 19:066047. doi:10.1088/1741-2552/acab30
- Mirzakhalili et al. (2020). *Cell Systems* 11:557–572. doi:10.1016/j.cels.2020.10.004
- Shirinpour et al. (2021). *Brain Stimul.* 14:1470–1482. doi:10.1016/j.brs.2021.09.004
- Seo & Jun (2017). *Front. Hum. Neurosci.* 11:515. doi:10.3389/fnhum.2017.00515
- Esmaeilpour et al. (2021). *Brain Stimul.* 14:55–65. doi:10.1016/j.brs.2020.11.007
- Rampersad et al. (2019). *NeuroImage* 202:116124. doi:10.1016/j.neuroimage.2019.116124
- Grossman et al. (2017). *Cell* 169:1029–1041. doi:10.1016/j.cell.2017.05.024
