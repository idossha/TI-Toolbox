---
name: ti-domain
description: Temporal interference neurostimulation domain knowledge. Use when working on simulation, optimization, analysis, or preprocessing code in TI-Toolbox.
user-invocable: false
---

# Temporal Interference Neurostimulation — Domain Reference

This document is the primary domain reference for AI agents working on TI-Toolbox who have no neuroscience background. Every section is relevant to understanding the codebase, the physics it implements, and the clinical context it serves.

> Numerical behavior changes need independent real-library regression tests. If published
> outputs change, document affected workflows and any user action in the relevant release page.
> For 2.x migration, read [the targeted fixes](../../../docs/releases/v3.0.0.md#scientific-corrections);
> MCP clients can discover the release link through `read_changelog`.

---

## 1. Temporal Interference (TI) Fundamentals

### The Core Idea

Temporal interference is a non-invasive brain stimulation technique that can reach deep brain structures without overstimulating the superficial cortex — something conventional methods like tDCS (transcranial direct current stimulation) and tACS (transcranial alternating current stimulation) struggle with.

### How It Works

1. **Two pairs of electrodes** are placed on the scalp. Each pair delivers a sinusoidal (AC) current at a slightly different high frequency. For example, Pair 1 operates at 2000 Hz and Pair 2 at 2010 Hz.

2. **High-frequency currents pass through superficial tissue without stimulating neurons.** Neurons have a biophysical low-pass filtering property — they cannot follow electrical oscillations above roughly 1 kHz. The 2000 Hz and 2010 Hz signals individually do nothing to neural tissue.

3. **At the deep target, the two electric fields superpose.** Where both fields overlap in space, they create an amplitude-modulated (AM) waveform. The envelope of this AM signal oscillates at the **difference frequency** (2010 - 2000 = 10 Hz). This 10 Hz modulation falls within the range that neurons *can* follow, so it drives neural activity at the target.

4. **Superficial regions see only the high-frequency carriers** (each pair's field dominates near its own electrodes), so they are not stimulated. Only where both fields have comparable magnitude — typically at depth — does meaningful interference occur.

### Foundational Reference

Grossman, N., Bono, D., Bhatt, N. et al. (2017). "Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields." *Cell*, 169(6), 1029–1041. This paper demonstrated TI stimulation in living mice, showing selective deep-brain activation without superficial cortex engagement.

### Key Field Quantities

Understanding these field quantities is critical because they are the primary outputs of every simulation in the codebase:

- **TI_max field**: The maximum envelope amplitude at each spatial point, computed across ALL possible neural fiber orientations. This is the orientation-independent maximum stimulation intensity. It answers: "What is the strongest possible TI effect at this location, regardless of which direction neurons are pointing?"

- **TI_normal field**: The envelope component projected along a specific direction vector — typically the cortical surface normal. It answers: "How strongly would TI stimulate neurons oriented perpendicular to the cortical surface at this point?" This is more physiologically relevant for cortical targets because pyramidal neurons are approximately normal to the cortical sheet. It is always ≤ `TI_max`.

  **`TI_normal` is mesh-only, by design** — it only exists on the cortical surface, so a voxel-space analysis of it is an error, not a bug. It is written for both TI and mTI runs; for mTI, `tit/sim/mTI.py::_calculate_mti_normal` reads the per-channel central-surface overlays, takes the node normals, and evaluates `get_TI_dir(e_fields, normals)`, writing `<montage>_mTI_normal.msh`. An mTI simulation run *before* that support existed has no normal mesh: requesting `TI_normal` raises `FileNotFoundError` and the `normal_*` statistics are `None` — the fix is to re-run the simulation.

- **fsaverage projection**: `tit/source/fsaverage.py` projects finished simulations onto the fsaverage surface *post hoc* (spacings 5/6/7 = 10242/40962/163842 nodes per hemisphere), covering `TI_max`, `TI_normal`, `hf_peak` and `hf_sar`, and writing `sub-<id>_sim-<sim>_space-fsaverage<spacing>_fields.npz`. This is what makes surface-space group statistics possible. Unlike SimNIBS's native `map_to_fsavg` (simulation time, `TI_max` only) it can be run after the fact. Confirm mTI coverage against the module before promising it — the source and `docs/wiki/simulator.md` disagree today.

- **Modulation depth**: A dimensionless ratio between 0 and 1 that indicates how effectively the two fields interfere at a given point:

  ```
  M(x) = 2 · min(|E1(x)|, |E2(x)|) / (|E1(x)| + |E2(x)|)
  ```

  - M = 1 when |E1| = |E2| (perfect interference, maximum modulation)
  - M → 0 when one field dominates (no meaningful modulation)
  - The modulation depth determines stimulation effectiveness independent of total field magnitude

### Important: The Envelope Is Not Simply |E1 - E2|

A common misconception is that the TI effect is just the difference of the two field magnitudes. The actual calculation involves **vector fields** and must consider orientation. At each spatial point, E1 and E2 are 3D vectors. The envelope magnitude depends on the relative orientation of these vectors and the neural fiber direction being considered. The full TI_max calculation searches over orientations using two quadratic forms built from the fields; the implementation is in `tit/calc.py`.

### Simplified Scalar TI Envelope

For intuition (the scalar case where fields are co-aligned):

```
E_TI(x) = |E1(x) + E2(x)| - |E1(x) - E2(x)|
```

This equals `2 · min(|E1|, |E2|)` when the fields point in the same direction. The full vector calculation generalizes this to arbitrary 3D field orientations.

### Key Advantage Over Conventional Stimulation

| Method | Depth Capability | Mechanism |
|--------|-----------------|-----------|
| tDCS | Superficial only | Static current flow |
| tACS | Superficial only | Low-frequency AC, strongest near electrodes |
| TI | Deep targets | High-freq carriers pass through; interference envelope at depth |
| mTI | Deep + more focal | Multiple interference patterns, more steering control |

---

## 2. Multi-polar Temporal Interference (mTI)

### Extension to N Electrode Pairs

Standard TI uses 2 electrode pairs. Multi-polar TI (mTI) extends this to N pairs — in the current TI-Toolbox implementation, typically **4 pairs**.

### How mTI Works

1. Each pair operates at a distinct carrier frequency. For example:
   - Pair 1: 2000 Hz
   - Pair 2: 2010 Hz
   - Pair 3: 2020 Hz
   - Pair 4: 2030 Hz

2. Multiple interference patterns form simultaneously. With 4 pairs, there are C(4,2) = 6 pairwise interference terms, each producing a different beat frequency (10, 20, 30 Hz, etc.).

3. **Phase optimization** is a key additional degree of freedom. By adjusting the relative starting phases between pairs, the spatiotemporal field pattern can be controlled more precisely. This is not available in standard 2-pair TI.

4. The result is **more focal stimulation** and **better steering** to deep targets compared to standard TI.

### mTI Field Calculation

The mTI field computation is more complex than standard TI:
- Must consider all pairwise interference terms between the N pairs
- Phase relationships between pairs affect the spatiotemporal envelope
- The optimization search space is larger (more electrodes, more intensities, plus phases)

### Key References

Check attributions against `read_wiki_page("simulator")` before repeating them —
several were corrected after a full-text audit, and Botzanowski 2025 in particular
contains **no equations** to cite.

### Codebase Detection

mTI vs standard TI is auto-detected from the montage's pair count. The rule is
stated once, in `tit.constants.is_valid_pair_count`, and enforced in
`Montage.simulation_mode` and `tit.calc._validate_field_list`:

> an **even** number of electrode pairs, **at least two** — 2 = TI, 4 or more = mTI.

So 2, 4, 6, 8, 12, 16 … are legal and 1, 3, 5 are not: an odd count leaves a
channel with nothing to beat against, and a single pair is tACS, not TI.

- **2 electrode pairs** → standard TI pathway (`tit/sim/TI.py`)
- **4+ (even) electrode pairs** → mTI pathway (`tit/sim/mTI.py`)

Note the capitalisation of both filenames — the container's filesystem is
case-sensitive.

### The envelope API — and what was removed

`tit.calc` exposes exactly **three** public functions, each taking a *list* of `2K`
field arrays paired **positionally** (each two consecutive fields share one carrier):

```python
get_TI_vectors(fields, psi=None)           # (N,3) modulation-amplitude vectors
get_TI_avg(fields, psi=None)               # (N,)  direction-averaged envelope
get_TI_dir(fields, directions, psi=None)   # (N,)  envelope along given directions
```

`psi` is a per-carrier envelope phase offset, shape `(K,)`, radians; `None` means
phase-aligned. `K = 1` uses an exact closed form; `K >= 2` runs the modulation-depth
direction search.

**Removed in v2.5.0 — never emit or describe these:** `get_nTI_vectors` (the old
recursive `TI(TI(E1,E2), TI(E3,E4))` algorithm, which is simply wrong for `N >= 4`),
`get_mTI_vectors` / `get_mTI_dir` (renamed), `get_magnitude_am`, the positional
`get_TI_vectors(E1, E2)` form, and the `channels=` carrier-regrouping parameter.
There is no `montage.channels` and no separate "carrier wiring" control:
**wiring is positional — one field is one carrier**, which is also how
`tit.fields.hf_peak(*fields)` and `hf_sar(*fields)` read their input.

---

## 3. Electrode Montage Design

### What Is a Montage?

A montage is the assignment of electrodes to pairs, specifying the anode (current source) and cathode (current sink) for each pair. In the codebase, a montage is represented as:

```python
# Standard TI (2 pairs):
[[anode1, cathode1], [anode2, cathode2]]

# mTI (4 pairs):
[[anode1, cathode1], [anode2, cathode2], [anode3, cathode3], [anode4, cathode4]]
```

### Electrode Naming Systems

Electrodes are referenced by standardized naming conventions:

- **10-20 System**: The international standard with 21 electrode positions (e.g., Fp1, Fp2, F3, F4, C3, C4, Cz, Pz, O1, O2). Positions are defined as percentages of skull measurements (nasion-inion, pre-auricular distances).

- **10-10 System**: Extension to ~64 positions, filling in between 10-20 locations.

- **10-5 System**: Further extension to ~345 positions, extremely dense coverage.

- **GSN HydroCel (EGI Geodesic Sensor Nets)**: Commercial electrode nets with numbered electrodes:
  - GSN-HydroCel-32 (32 channels)
  - GSN-HydroCel-65 (65 channels)
  - GSN-HydroCel-128 (128 channels)
  - GSN-HydroCel-185 (185 channels)
  - GSN-HydroCel-257 (257 channels)
  - In the codebase, these are referenced by their CSV filenames (e.g., `"GSN-HydroCel-185.csv"`). The CSV files contain 3D electrode coordinates and the parser **skips the first (header) line**.

### Electrode Properties

Each electrode has physical properties that affect the simulation:
- **Shape**: ellipse or rectangular
- **Dimensions**: width and height in millimeters
- **Thickness**: electrode material thickness (mm)
- **Sponge thickness**: conductive sponge/gel pad thickness (mm) — this is the interface between electrode and scalp

### Current Intensity

- Each electrode pair delivers current at a specified intensity, typically **1–2 mA** (milliamperes)
- Current flows from anode → through tissue → to cathode for each pair
- The sum of all injected currents must satisfy Kirchhoff's current law (what goes in must come out)

### Unipolar Montages

In unipolar montages, each pair has one "active" electrode near the target and one "reference" electrode placed far from the region of interest. This is a common configuration in the TI-Toolbox montage system.

### Montage JSON Format

Montages are stored in JSON configuration files:
```json
{
  "nets": {
    "GSN-HydroCel-185.csv": {
      "uni_polar_montages": {
        "my_montage": [[10, 50], [20, 60]]
      }
    }
  }
}
```

---

## 4. Finite Element Method (FEM) Simulation

### Why FEM?

The human head is not a uniform conductor. It contains multiple tissue types with very different electrical conductivities, complex geometry (folded cortex, irregular skull), and anisotropic properties (white matter fibers). Analytical solutions are impossible for realistic head geometry. FEM discretizes the continuous head volume into millions of small elements and numerically solves the governing equation.

### The Governing Equation

```
∇ · (σ ∇φ) = 0
```

Where:
- **σ** is the conductivity tensor (S/m — Siemens per meter) — can be a scalar (isotropic) or 3x3 matrix (anisotropic)
- **φ** is the electric potential (Volts)
- **∇φ** is the gradient of potential
- **σ∇φ** is the current density (Amperes/m²) — Ohm's law in differential form
- The equation states: the divergence of current density is zero (charge conservation, no sources/sinks inside the volume)

Boundary conditions are set by the electrode currents on the scalp surface.

The electric field is derived from the potential:
```
E = -∇φ
```

### SimNIBS

SimNIBS (Simulation of Non-invasive Brain Stimulation) is the open-source tool TI-Toolbox uses for FEM computation. It:
- Takes a tetrahedral head mesh as input
- Sets up and solves the FEM system
- Returns the electric field vector (Ex, Ey, Ez) at each mesh element centroid
- Provides Python APIs that TI-Toolbox calls directly

### Head Mesh

The head mesh is a volumetric tetrahedral mesh generated from structural MRI. A typical mesh contains **3–5 million tetrahedral elements**. Each element belongs to a tissue compartment.

### Tissue Compartments and Conductivities

The head model segments tissue into distinct compartments, each with a characteristic electrical conductivity:

| Tissue | Typical Conductivity (S/m) | Notes |
|--------|---------------------------|-------|
| Scalp | 0.465 | Skin + subcutaneous tissue |
| Skull (compact bone) | 0.007 | Very low — skull is the main barrier |
| Skull (spongy bone) | 0.025 | Diploe layer, somewhat more conductive |
| CSF (cerebrospinal fluid) | 1.654 | Highly conductive — acts as current pathway |
| Gray matter | 0.275 | Neuronal cell bodies, dendrites |
| White matter | 0.126 | Myelinated axon fibers |
| Eyes | ~1.5 | Vitreous humor, similar to CSF |
| Ventricles | ~1.654 | CSF-filled cavities deep in brain |

Key insight: the **skull** is the dominant barrier (conductivity ~50x lower than scalp or brain). The **CSF** is the most conductive tissue and acts as a preferential current pathway, which is why current tends to shunt through CSF rather than penetrating cortex.

### Anisotropic Conductivity

White matter conductivity is **anisotropic** — it varies with direction relative to axon fiber bundles:
- **Along fibers**: higher conductivity (current flows easily along myelinated axons)
- **Perpendicular to fibers**: lower conductivity

Anisotropic conductivity tensors are derived from diffusion tensor imaging (DTI) data. When DTI is available, the conductivity σ becomes a 3x3 symmetric positive-definite matrix at each mesh element, rather than a scalar.

### Leadfield Matrix

The leadfield matrix is a precomputed data structure that enables rapid optimization:

```
Leadfield dimensions: [n_elements × 3 × n_electrodes]
```

- For each electrode (with unit current, 1 mA), the electric field at every mesh element is computed once via FEM
- Any montage's field can then be computed by linear combination: E_montage = Σ(I_k × L_k) where I_k is the current at electrode k and L_k is the k-th leadfield column
- This avoids re-running the expensive FEM solve for every candidate montage during optimization
- Computing the leadfield itself requires n_electrodes FEM solves, but after that, evaluating millions of montages is fast (matrix multiplication)

---

## 5. Optimization Approaches

### Why Optimize?

With hundreds of possible electrode positions and continuous current intensities, the space of possible montages is enormous. The goal is to find the montage that best delivers stimulation to a specified target (ROI) while minimizing stimulation elsewhere.

### Flex Search (Differential Evolution)

Differential evolution (DE) is a **stochastic global optimization** algorithm. In the TI-Toolbox, "flex search" is the primary optimization method.

**How DE works:**
1. Initialize a **population** of random candidate montages (typical population size: ~13)
2. For each generation:
   - For each candidate, create a **mutant** by combining other candidates (mutation)
   - Mix the mutant with the original candidate (crossover/recombination)
   - Evaluate the **objective function** for the trial candidate
   - Keep the better of the original and trial (selection)
3. Repeat for up to **max_iterations** (~500) or until convergence (tolerance met)

**Search variables:**
- Electrode positions (selected from allowed electrode set)
- Current intensities per pair
- Phases (for mTI only)

**Objective function options:**
- Maximize mean field in ROI
- Maximize peak field in ROI
- Maximize focality (ROI field vs. off-target field)

**Multi-start strategy:** Run N independent DE optimizations with different random seeds, then take the best result. This mitigates the risk of getting trapped in local optima.

**Speed:** Uses the leadfield matrix, so each objective function evaluation is a fast matrix operation — no FEM solve needed.

**Key parameters:**
- `population_size`: number of candidate solutions per generation (~13)
- `max_iterations`: maximum generations (~500)
- `tolerance`: convergence threshold
- `mutation_rate`: DE mutation scaling factor (typically 0.5–1.0)
- `recombination_rate`: crossover probability (typically 0.7–0.9)

### Exhaustive Search

Brute-force enumeration of all possible montage combinations from a defined electrode pool.

**How it works:**
1. Define a pool of candidate electrodes
2. Enumerate all valid combinations of electrode assignments to pairs
3. For each combination, compute the field using the leadfield matrix
4. Return the combination with the best objective value

**Computational cost:** O(n^k) where n = number of electrodes in pool, k = number of electrode positions to assign. This grows very quickly, so exhaustive search is only feasible for small electrode pools.

**Electrode selection strategies:**
- **Bucket**: electrodes are grouped into buckets; one electrode is selected from each bucket
- **Pool**: all electrodes come from a single shared pool

**Guarantee:** finds the global optimum within the search space (unlike DE, which is stochastic).

### ROI (Region of Interest) Types

The optimization target is defined as an ROI:

- **Spherical ROI**: defined by a center point (x, y, z coordinates in mm, either in MNI standard space or subject-native space) and a radius (mm). All mesh elements whose centroids fall within the sphere are included. Simple and commonly used.

- **Cortical ROI**: defined by an atlas region name (e.g., "superiorfrontal" from the DK40 atlas). Includes all mesh elements labeled with that region in the atlas parcellation. More anatomically precise than spherical.

- **Subcortical ROI**: similar to cortical, but targeting deep brain structures (e.g., hippocampus, thalamus, putamen). These are the primary targets where TI's depth advantage matters.

### Optimization Goals

The objective function can be configured as:

| Goal | Formula | When to Use |
|------|---------|-------------|
| `"mean"` | Maximize mean(E_ROI) | General-purpose, robust target coverage |
| `"max"` | Maximize max(E_ROI) | When peak intensity matters (e.g., threshold effects) |
| `"focality"` | Maximize mean(E_ROI) / mean(E_nonROI) | When minimizing off-target stimulation is critical |

---

## 6. Brain Imaging and Preprocessing Pipeline

### Overview

Before any simulation can run, the subject's brain anatomy must be imaged, reconstructed, and meshed. This preprocessing pipeline transforms raw scanner data into a simulation-ready head model.

### Step 1: DICOM to NIfTI Conversion

- **DICOM** (Digital Imaging and Communications in Medicine): the raw output format from MRI scanners. Each slice is a separate file with extensive metadata.
- **NIfTI** (Neuroimaging Informatics Technology Initiative, .nii or .nii.gz): the standard neuroimaging format. A single file containing the entire 3D volume plus an affine matrix defining its position in physical space.
- **dcm2niix**: the standard conversion tool. Handles vendor-specific DICOM quirks and produces properly oriented NIfTI files.

### Step 2: FreeSurfer Cortical Reconstruction

FreeSurfer's `recon-all` performs automated cortical surface reconstruction from T1-weighted MRI:

1. **Skull stripping**: removes non-brain tissue
2. **Tissue segmentation**: classifies voxels as white matter, gray matter, CSF
3. **Surface reconstruction**: generates two surfaces per hemisphere:
   - **White surface**: boundary between white matter and gray matter
   - **Pial surface**: boundary between gray matter and CSF
4. **Cortical parcellation**: labels each vertex with an atlas region
5. **Cortical thickness**: computed as the distance between white and pial surfaces

Runtime: 6–12 hours per subject. Output goes to `derivatives/freesurfer/sub-{id}/`.

### Step 3: CHARM Head Meshing (SimNIBS)

CHARM (Complete Head Anatomy Reconstruction Model) creates the tetrahedral head mesh needed for FEM:

1. **Input**: T1-weighted MRI (required) + T2-weighted MRI (optional but improves skull segmentation)
2. **Tissue segmentation**: classifies each voxel into tissue compartments (scalp, skull layers, CSF, GM, WM, eyes, ventricles)
3. **Surface generation**: creates boundary surfaces between tissue types
4. **Volume meshing**: fills the surfaces with tetrahedral elements using Gmsh
5. **Output**: the `m2m_{subject}` directory containing the head mesh and related files

The mesh output goes to `derivatives/SimNIBS/sub-{id}/m2m_{id}/`.

### Step 4: Diffusion Imaging (Optional but Valuable)

Diffusion-weighted imaging (DWI/DTI) measures water molecule diffusion in brain tissue:

- **Why it matters**: water diffuses preferentially along white matter fibers. By measuring diffusion directionality, we can infer fiber orientation and derive anisotropic conductivity tensors.
- **Diffusion tensor**: a 3x3 symmetric matrix at each voxel describing the diffusion ellipsoid. Its eigenvectors indicate fiber directions; its eigenvalues indicate diffusion magnitude along each direction.
- **Conductivity mapping**: the diffusion tensor is mathematically transformed into a conductivity tensor. The relationship assumes that electrical conductivity and water diffusion share the same anisotropy directions (both follow fiber geometry).
- **QSIPrep**: preprocessing pipeline for diffusion MRI (motion correction, distortion correction, denoising)
- **QSIRecon**: reconstruction pipeline (tensor fitting, fiber orientation distribution estimation, tractography)

### Atlas Parcellation Systems

Atlases divide the cortical surface or brain volume into labeled regions. They are essential for defining cortical ROIs:

| Atlas | Regions per Hemisphere | Total Regions | Resolution | Common Use |
|-------|----------------------|---------------|------------|------------|
| DK40 (Desikan-Killiany) | 34 | 68 | Coarse | Default in most analyses, well-validated |
| Destrieux (a2009s) | 74 | 148 | Medium | When finer parcellation needed |
| HCP-MMP1 (Glasser) | 180 | 360 | Fine | High-resolution analyses |

Example DK40 regions: `superiorfrontal`, `middletemporal`, `precentral`, `postcentral`, `inferiorparietal`, `lateraloccipital`, `insula`, `caudalmiddlefrontal`, `rostralmiddlefrontal`, `medialorbitofrontal`.

Subcortical structures (not atlas-dependent): hippocampus, amygdala, thalamus, caudate, putamen, pallidum, nucleus accumbens.

---

## 7. Analysis Methods

### Field Statistics per ROI

For each ROI, the following statistics are computed over all mesh elements within the region:

- **Mean**: average field intensity — most robust summary measure
- **Max**: peak field intensity — relevant for threshold-based neural effects
- **Median**: middle value — less sensitive to outliers than mean
- **Standard deviation**: spread of field values within the ROI
- **Percentiles**: 5th, 25th, 75th, 95th — characterize the full distribution
  - 95th percentile is often more stable than max for comparing across subjects

### Focality Metrics

Focality quantifies how well-targeted the stimulation is:

```
Focality = mean(E_ROI) / mean(E_nonROI)
```

Alternative formulation:
```
Focality = max(E_ROI) / percentile(E_nonROI, 95)
```

Higher focality means the stimulation is more concentrated at the target and weaker elsewhere. A focality of 1.0 means the target receives no more stimulation than the rest of the brain.

Flex-search also offers `focality_tf`, a threshold-free variant
`mean_ROI^(1+w) / p95_nonROI`, which avoids picking an arbitrary cut-off.

#### Units — the one thing to get right

The analyzer's `focality_50_area`, `focality_75_area`, `focality_90_area` and
`focality_95_area` measure **how much tissue exceeds a fraction of the peak**, and
their unit depends on the space:

| Space | Element weight | Reported unit | Conversion |
|-------|----------------|---------------|------------|
| mesh  | node area, mm² | **cm²** | ÷ 100 |
| voxel | voxel volume, mm³ | **cm³** | ÷ 1000 |

The `_area` suffix is deliberately kept for the voxel case too, so existing scripts
and the group aggregator keep working — **read the name as "extent", and take the
unit from the space**. Voxel-space values produced by v2.3.0–v2.5.0 divided by 100
instead of 1000 and are therefore **ten times too large**; divide them by 10, no
re-run needed. Mesh values were always correct. `total_area_or_volume` is raw
mm²/mm³ and never moved.

#### Geometry comes from the affine, not the zooms

Voxel volume is `|det(A)|` of the affine's 3×3 block, and the distance from a
spherical ROI's centre is `‖A(v − c)‖`. The older code used
`header.get_zooms()` — the affine's *column norms* — which silently assumes the
voxel axes are orthogonal in world space. On an orthogonal grid the two agree
exactly; on a sheared one the zooms overestimated voxel volume by ~11%, which
propagated into `total_area_or_volume` and every `focality_*_area`, and made the
"spherical" ROI the wrong ellipsoid. Detection: compare
`prod(header.get_zooms()[:3])` with `abs(det(affine[:3,:3]))` — a difference above
float noise means the data is sheared and the result must be re-run.

Group stacking is guarded the same way: every subject's image must share a grid
(shape, direction block, origin) with the first, or the load raises `ValueError`
naming the subject. Affines differing by more than 1e-3 mm in origin or 1e-4 in the
direction block mean the analysis compared different anatomy; a sign flip in
`det(affine[:3,:3])` (a left–right handedness flip) is the worst case.

### Surface Mapping

Volumetric (3D) field data can be projected onto cortical surfaces for visualization:
- The field value at each cortical surface vertex is determined by the nearest volumetric mesh element
- This enables visualization of stimulation patterns on inflated or flattened cortical surfaces
- Critical for understanding which gyri and sulci receive stimulation

### NIfTI Resampling and MNI Space

- **Subject space**: coordinates aligned to the individual's MRI — each subject has a unique coordinate system
- **MNI space**: a standardized coordinate system based on the Montreal Neurological Institute template brain — enables cross-subject comparison
- **Resampling**: transforming field maps from subject space to MNI space using nonlinear registration (warping)
- This is necessary for group-level analyses where data from multiple subjects must be in the same coordinate frame

### Group Analysis

Comparing stimulation patterns across multiple subjects:

- **Between-group comparison**: e.g., patients vs. healthy controls — do the groups differ in field distribution for the same montage?
- **Correlation analysis**: relate field intensity at each location to a behavioral or clinical variable
- **Why it matters**: individual anatomy varies significantly (skull thickness, cortical folding, CSF distribution), so the same montage produces different field patterns in different subjects

### Cluster Permutation Testing

A non-parametric statistical method for spatial data that controls for the multiple comparisons problem:

1. **Compute test statistic** at each spatial point (e.g., t-test between groups)
2. **Threshold**: identify points exceeding a significance threshold (e.g., p < 0.05 uncorrected)
3. **Form clusters**: group spatially contiguous significant points into clusters
4. **Cluster statistic**: sum the test statistics within each cluster
5. **Permutation distribution**: randomly shuffle group labels N times (e.g., 1000), repeat steps 1–4 each time, record the largest cluster statistic
6. **Significance**: compare observed cluster statistics to the permutation distribution. Clusters larger than 95% of permutation clusters are significant at p < 0.05 (corrected)

**Key parameters:**
- `n_permutations`: number of random shuffles (~1000; more = more precise p-values)
- `alpha`: significance level (typically 0.05)
- `cluster_threshold`: initial voxel-level threshold for cluster formation

**Advantages**: no assumption of normal distribution, controls family-wise error rate across the entire brain, data-driven cluster formation.

#### The p-value is `(b + 1) / (m + 1)`

With a *sampled* Monte-Carlo null, the naive `b / m` (the fraction of `m`
permutations at least as extreme) can return exactly 0 and is anti-conservative in
the tail. The correct estimator (Phipson & Smyth 2010) adds the observed statistic
to its own null:

```
p = (b + 1) / (m + 1)
```

At the default 1000 permutations the floor is `1/1001 ≈ 9.99e-4`, never 0, and the
shift is at most 0.001 absolute. An old report showing `p = 0.0000` should be read
as `p < 1/(m+1)`; to convert, `p_new = (p_old * m + 1) / (m + 1)`. The exact `b / m`
is correct **only** when the null is an exhaustive enumeration of the permutation
group, not a sample.

#### Clusters carry a sign, and the comparison is always right-tailed

A supra-threshold map contains both positive and negative blobs. Labelling it with
a plain connected-components pass fuses touching positive and negative blobs into
one cluster whose signed mass is their *difference*, and taking `max()` over signed
masses under a left- or two-sided tail selects the cluster **closest to zero**
rather than the most extreme. Two rules fix it:

1. **Label positive and negative voxels as separate components** — a cluster never
   mixes signs.
2. **Map each cluster to a statistic monotone in extremeness** before comparing:
   `mass` for a right tail, `−mass` for a left tail, `|mass|` for two-sided. The
   observed and permuted values are then on the same scale and the comparison is
   always right-tailed.

One-sided cluster *forming* is sign-restricted to match. A right-tailed
(`alternative="greater"`) analysis was never affected, because there the oriented
statistic already is the signed mass. **Detection tell:** a log line reading
`Threshold (p<0.050): <a negative number> mass units` — an oriented threshold can
never be negative. Affected analyses must be **re-run**; there is no rescaling.

Degenerate voxels (zero standard error) are also handled explicitly now: `0/0`
(undefined) and `±x/0` (perfect separation) are no longer both flattened to
`t = 0, p = 1`; degenerate voxels are excluded from the valid mask and counted in a
warning. This can change the valid mask and therefore cluster geometry, so it too
is a re-run, not a rescale.

---

## 8. Key Equations Reference

These equations appear in the codebase (primarily in `tit/calc.py`) and understanding them is essential for working on simulation and analysis code.

### TI Envelope (Simplified Scalar)

When E1 and E2 are co-aligned scalars:
```
E_TI(x) = |E1(x) + E2(x)| - |E1(x) - E2(x)| = 2 · min(|E1(x)|, |E2(x)|)
```

### TI_max (Full Vector, Orientation-Independent)

For 3D vector fields E1(x) and E2(x), find the orientation unit vector **n** that maximizes the envelope:
```
TI_max(x) = max_n [ |n · (E1 + E2)| - |n · (E1 - E2)| ]
```

For `K = 1` carrier pair this has an exact closed form. For `K >= 2` (mTI) the
implementation reduces the problem, per direction, to two quadratic forms `P` and
`Q` built from the fields, and searches directions over a Fibonacci sphere with a
local refinement pass.

**Numerical conditioning.** The envelope is *not* evaluated as
`sqrt(2(P+Q)) - sqrt(2(P-Q))`. At `Q << P` — which is every off-target voxel, and
therefore the denominator of every focality ratio — that subtraction of two nearly
equal square roots loses all leading digits and returns exactly 0 once
`Q/P < ~1e-16`. The algebraically identical rationalised form is used instead:

```
MD = 2*sqrt(2) * Q / ( sqrt(P + Q) + sqrt(P - Q) )
```

a quotient of *additions*, accurate to ~1e-14 relative down to `Q/P = 1e-20`
(`P = Q = 0` yields 0). If you touch this expression, the conditioning is the point.
The implementation is in `tit/calc.py`.

### Modulation Depth

```
M(x) = 2 · min(|E1(x)|, |E2(x)|) / (|E1(x)| + |E2(x)|)
```

Ranges from 0 (no modulation, one field dominates) to 1 (perfect modulation, equal field strengths).

### Focality

```
F = mean(E_ROI) / mean(E_nonROI)
```

Note the analyzer's `focality_*_area` outputs are a different thing — an *extent*
of tissue above a fraction of peak, in cm2 (mesh) or cm3 (voxel). See section 7.

### FEM Governing Equation

```
∇ · (σ ∇φ) = 0        (Laplace equation with inhomogeneous conductivity)
E = -∇φ                (Electric field from potential)
J = σ E                (Current density from Ohm's law)
```

### Leadfield-Based Field Computation

```
E(x) = Σ_k  I_k · L(x, k)
```

Where I_k is the current at electrode k and L(x, k) is the precomputed leadfield at point x for electrode k. This is the basis of fast optimization.

---

## 9. Safety Considerations

These safety parameters are embedded in the codebase's validation and constraint systems:

### Current Limits
- **Total injected current per pair**: typically capped at **2 mA** (milliamperes)
- **Current density at electrode-skin interface**: must stay below **2 mA/cm²** to prevent skin irritation or burns
- Larger electrodes spread the same current over more area, reducing current density

### Thermal Effects
- Resistive heating occurs at electrode contacts and in tissue (P = I²R)
- Most significant at the electrode-skin interface where impedance is highest
- Electrode gel/sponge must maintain good electrical contact to prevent hot spots

### Exposure metrics: `hf_peak` and `hf_sar`

These are the toolbox's two carrier-exposure outputs, and their definitions are
precise. Follow Cassarà et al. 2025 (Parts I and II), which the implementation is
written to.

**The engine is quasi-static.** An FEM field `E` is a **phasor amplitude** vector
in V/m — a **peak**, not an RMS — and there is no time axis anywhere in the
toolbox. Every exposure quantity is therefore a **worst case over the unknown
relative phases** of the carriers: equal to the time-domain definition when that
worst phase is actually attained (which it is, for incommensurate carriers), and an
upper bound otherwise. This is the same convention that gives the modulation depth.

**How carriers combine** (Cassarà Part II, p. 8, verbatim): *"coherent field
superposition was used for identical frequencies, and incoherent superposition
(i.e., SAR addition) was used when the frequencies differed."* So fields at the
same frequency sum **as vectors** first, and distinct carriers then combine
**incoherently** — in power for `hf_sar`, and by worst-case sign enumeration for
`hf_peak`. Under the toolbox's shipped **positional wiring** one field *is* one
carrier, so with `E_c` the field of carrier `c`:

```
hf_peak = max over signs s_c in {+1,-1} of  | sum_c  s_c * E_c |      (V/m)
hf_sar  = sum_c |E_c|^2                                              ((V/m)^2)
```

- `hf_sar` carries **no** time-averaging factor. The factor of ½ appears exactly
  once, in the calibration: `SAR = (σ / 2ρ) · hf_sar` in W/kg, and the RMS carrier
  field is `sqrt(hf_sar / 2)`.
- `hf_peak` is **exact** by enumerating all `2^(N-1)` sign combinations up to
  `EXACT_SIGN_ENUM_MAX_FIELDS = 8` carriers; above that a direction sweep returns a
  **lower bound**, which is slightly non-conservative. `hf_peak_is_exact(n)` says
  which regime you are in.
- Cassarà's Table 3 (p. 15) limits are **peak** values, not RMS: brain 16 mA /
  30 V/m below 2.5 kHz, scaling as `f / 2.5 kHz` above; skin 7 mA / 200 V/m. The
  temperature-derived route gives 14 mA for the FDA's 0.1 °C brain limit and
  100 mA for 2 °C in skin.
- `TI_max`, `TI_avg`, `TI_normal` and everything downstream in the analyzer and
  statistics were never affected by the carrier-grouping question.

**Deliberately not computed** (do not claim the toolbox reports them): current
density `J = σE` (needs the 2 mm ICNIRP averaging kernel and per-tissue σ),
temperature rise (Pennes bioheat), charge per phase and the Shannon limit, exposure
duration / CEM43, and the activating function.

### General SAR context
- SAR = σ|E|² / ρ (W/kg), where ρ is tissue density; regulatory limits are
  typically 2 W/kg averaged over 10 g of tissue.

### Impedance Monitoring
- Electrode-skin impedance should be monitored before and during stimulation
- High impedance indicates poor contact, risking burns and unreliable current delivery
- Typical target: < 5 kΩ per electrode

### Contraindications
- **Metallic implants** (cochlear implants, surgical clips, DBS electrodes) — can concentrate current and cause heating
- **Epilepsy history** — stimulation could trigger seizures
- **Pregnancy** — insufficient safety data
- **Skin lesions** under electrode sites

---

## 10. BIDS Data Organization

TI-Toolbox follows the BIDS (Brain Imaging Data Structure) standard, which enforces a consistent directory hierarchy:

```
project_root/
├── sourcedata/                          # Raw DICOM files from scanner
│   └── sub-{id}/                        # Per-subject raw data
│
├── sub-{id}/                            # Subject-level BIDS directory
│   └── anat/                            # Anatomical images
│       ├── sub-{id}_T1w.nii.gz          # T1-weighted MRI (required)
│       └── sub-{id}_T2w.nii.gz          # T2-weighted MRI (optional)
│
├── derivatives/                         # All derived/computed data
│   ├── SimNIBS/sub-{id}/                # SimNIBS outputs
│   │   ├── m2m_{id}/                    # Head mesh (CHARM output)
│   │   │   ├── {id}.msh                 # Tetrahedral mesh file
│   │   │   ├── T1fs_conform.nii.gz      # Conformed T1 image
│   │   │   └── ...                      # Tissue maps, transforms
│   │   └── Simulations/                 # TI simulation outputs
│   │       └── {montage_name}/          # Per-montage results
│   │           ├── TI_vectors.msh       # Raw field vectors
│   │           ├── TI_max.msh           # Max envelope field
│   │           └── ...                  # NIfTI transforms, surfaces
│   │
│   ├── freesurfer/sub-{id}/             # FreeSurfer recon-all output
│   │   ├── surf/                        # Cortical surfaces (lh.pial, rh.pial, etc.)
│   │   ├── label/                       # Atlas parcellations
│   │   ├── mri/                         # Processed MRI volumes
│   │   └── stats/                       # Morphometric statistics
│   │
│   └── ti-toolbox/                      # TI-Toolbox-specific outputs
│       ├── reports/                     # Generated HTML reports
│       ├── analysis/                    # Analysis CSV files, figures
│       └── optimization/               # Optimization results
│
└── code/ti-toolbox/                     # Everything the toolbox itself owns
    ├── config/                          # montage_list.json, EEG nets, settings
    ├── jobs/{id}/                       # v3 job store: spec.json, status.json,
    │                                    #   events.jsonl, stdout.log
    ├── notebooks/                       # .ipynb documents (examples/ only subdir)
    ├── pipelines/{name}.json            # pipeline DAGs (+ runs/ for resolved ports)
    └── viewer/{kind}.tetravox.json      # viewer scenes
```

The head model also carries `m2m_{id}/eeg_positions/`, `m2m_{id}/segmentation/`,
`m2m_{id}/surfaces/` and `m2m_{id}/stim_configs/` (free-hand electrode placements
in subject-RAS millimetres). The job store lives inside the project so a notebook
and a restarted server see the same jobs; `.bidsignore` carries the line
`code/ti-toolbox/jobs/`. Never hand-build any of these paths — go through
`tit.paths.get_path_manager`.

### Subject ID Convention

Subject IDs follow BIDS convention: `sub-{id}` where `{id}` is typically a zero-padded number (e.g., `sub-001`). The `sub-` prefix is part of the directory name but is stripped in some internal code contexts — the PathManager handles this consistently.

---

## 11. Glossary of Domain Terms

| Term | Definition |
|------|-----------|
| **Anode** | Electrode where current enters the tissue (positive terminal) |
| **Cathode** | Electrode where current exits the tissue (negative terminal) |
| **Conductivity (σ)** | Material property describing how easily electric current flows (S/m) |
| **CSF** | Cerebrospinal fluid — highly conductive fluid surrounding the brain |
| **DTI** | Diffusion Tensor Imaging — MRI technique measuring water diffusion directionality |
| **EEG** | Electroencephalography — brain electrical activity recording (shares electrode position standards) |
| **FEM** | Finite Element Method — numerical technique for solving PDEs on complex geometry |
| **GM** | Gray matter — brain tissue containing neuronal cell bodies |
| **Leadfield** | Precomputed field-per-electrode matrix enabling fast montage evaluation |
| **MNI space** | Montreal Neurological Institute standard coordinate system for brain imaging |
| **Montage** | Configuration of electrode positions and pair assignments |
| **mTI** | Multi-polar temporal interference (4+ electrode pairs) |
| **NIfTI** | Neuroimaging file format (.nii/.nii.gz) |
| **Parcellation** | Division of cortical surface into labeled anatomical regions |
| **ROI** | Region of interest — the stimulation target |
| **SAR** | Specific Absorption Rate — power absorbed per unit mass of tissue |
| **SimNIBS** | Simulation of Non-invasive Brain Stimulation — FEM solver |
| **TI** | Temporal interference — brain stimulation via interfering high-frequency fields |
| **WM** | White matter — brain tissue containing myelinated axon fibers |

---

## 12. Key References

### Temporal Interference — Foundational
- Grossman, N., Bono, D., Dedic, N., Kodandaramaiah, S.B., Rudenko, A., Suk, H.J., Cassara, A.M., Neufeld, E., Kuster, N., Tsai, L.H., Bhatt, D.K., Bhatt, N., Pascual-Leone, A., & Bhatt, D.K. (2017). **Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields.** *Cell*, 169(6), 1029–1041. — The foundational paper demonstrating TI in mice, showing selective hippocampal stimulation without cortical engagement.
- Rampersad, S., Roig-Solvas, B., Yarossi, M., Kulkarni, P.P., Santarnecchi, E., Dorval, A.D., & Brooks, D.H. (2019). **Prospects for transcranial temporal interference stimulation in humans: A computational study.** *NeuroImage*, 202, 116124. — First computational modeling of TI in realistic human head models; showed practical feasibility and identified challenges.
- Huang, Y. & Bhatt, D.K. (2020). **An analytical model for temporal interference stimulation.** *Physics in Medicine & Biology*, 65(12), 125001. — Mathematical framework for understanding TI field distributions analytically.

### Multi-polar TI (mTI) & Multi-channel
- Lee, S., Lee, C., Park, J., & Im, C.H. (2020). **Individually customized transcranial temporal interference stimulation for focused modulation of deep brain structures: a simulation study with different head models.** *Scientific Reports*, 10, 11730. — Extended TI to individually optimized configurations; showed subject-specific anatomy matters.
- Botzanowski, B., Donahue, M.J., Giannopoulos, G., Gomez, L.J., & Bhatt, D.K. (2022). **Multi-channel temporal interference stimulation for focal deep brain modulation.** — Demonstrated advantages of 4+ electrode pair configurations for improved focality.
- Cao, J. & Bhatt, D.K. (2020). **Stimulus waveform design for multi-channel transcranial temporal interference stimulation.** — Phase optimization for mTI; showed how relative phase between pairs controls field steering.
- von Conta, J., Kasten, F.H., Curio, G., Villringer, A., & Herrmann, C.S. (2022). **Interindividual variability of electric fields during transcranial temporal interference stimulation (tTIS).** *Scientific Reports*, 12, 1598. — Documented how anatomical variation affects TI fields across individuals.

### FEM & Head Modeling
- Thielscher, A., Antunes, A., & Saturnino, G.B. (2015). **Field modeling for transcranial magnetic stimulation: A useful tool to understand the physiological effects of TMS?** *IEEE EMBS*, 222–225. — SimNIBS original paper; describes the FEM approach for brain stimulation modeling.
- Saturnino, G.B., Madsen, K.H., & Thielscher, A. (2019). **Electric field simulations for transcranial brain stimulation using FEM: an efficient implementation and error analysis.** *Journal of Neural Engineering*, 16(6), 066032. — SimNIBS v3 implementation details; efficient FEM solver and accuracy analysis.
- Puonti, O., Van Leemput, K., Saturnino, G.B., Siebner, H.R., Madsen, K.H., & Thielscher, A. (2020). **Accurate and robust whole-head segmentation from magnetic resonance images for individualized head modeling.** *NeuroImage*, 219, 117044. — CHARM segmentation pipeline; how head meshes are generated from MRI.
- Nielsen, J.D., Madsen, K.H., Puonti, O., Siebner, H.R., Bauer, C., Madsen, C.G., Saturnino, G.B., & Thielscher, A. (2018). **Automatic skull segmentation from MR images for realistic volume conductor models of the head.** *NeuroImage*, 174, 587–598. — Skull segmentation (critical because skull is the dominant barrier to current flow).
- Windhoff, M., Opitz, A., & Thielscher, A. (2013). **Electric field calculations in brain stimulation based on finite elements: An optimized processing pipeline for the generation and usage of accurate individual head models.** *Human Brain Mapping*, 34(4), 923–935. — Pipeline for generating FEM head models from MRI.

### Conductivity & Tissue Properties
- McCann, H., Pisano, G., & Beltrachini, L. (2019). **Variation in reported human head tissue electrical conductivity values.** *Brain Topography*, 32, 825–858. — Comprehensive review of reported conductivity values for all head tissues; reference for the values in `tit/constants.py`.
- Opitz, A., Paulus, W., Will, S., Antunes, A., & Thielscher, A. (2015). **Determinants of the electric field during transcranial direct current stimulation.** *NeuroImage*, 109, 140–150. — How tissue conductivity (especially skull and CSF) shapes current flow; why anisotropy matters.
- Basser, P.J., Mattiello, J., & LeBihan, D. (1994). **MR diffusion tensor spectroscopy and imaging.** *Biophysical Journal*, 66(1), 259–267. — Foundational DTI paper; basis for deriving anisotropic conductivity tensors from diffusion imaging.

### Diffusion Imaging & QSI
- Cieslak, M., Cook, P.A., He, X., Yeh, F.C., Dhollander, T., Adebimpe, A., ... & Satterthwaite, T.D. (2021). **QSIPrep: An integrative platform for preprocessing and reconstructing diffusion MRI data.** *Nature Methods*, 18, 775–778. — QSIPrep pipeline for diffusion MRI preprocessing.
- Yeh, F.C., Wedeen, V.J., & Tseng, W.Y.I. (2010). **Generalized q-sampling imaging.** *IEEE Transactions on Medical Imaging*, 29(9), 1626–1635. — Generalized approach to diffusion MRI reconstruction beyond simple DTI.

### FreeSurfer & Cortical Reconstruction
- Fischl, B. (2012). **FreeSurfer.** *NeuroImage*, 62(2), 774–781. — Comprehensive overview of the FreeSurfer pipeline; cortical surface reconstruction, parcellation, thickness estimation.
- Dale, A.M., Fischl, B., & Sereno, M.I. (1999). **Cortical surface-based analysis I: Segmentation and surface reconstruction.** *NeuroImage*, 9(2), 179–194. — Original cortical surface reconstruction algorithm.
- Desikan, R.S., Ségonne, F., Fischl, B., Quinn, B.T., Dickerson, B.C., Blacker, D., ... & Killiany, R.J. (2006). **An automated labeling system for subdividing the human cerebral cortex on MRI scans into gyral based regions of interest.** *NeuroImage*, 31(3), 968–980. — The DK40 (Desikan-Killiany) atlas; 34 regions per hemisphere.
- Destrieux, C., Fischl, B., Dale, A., & Halgren, E. (2010). **Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature.** *NeuroImage*, 53(1), 1–15. — The Destrieux (a2009s) atlas; 74 regions per hemisphere.
- Glasser, M.F., Coalson, T.S., Robinson, E.C., Hacker, C.D., Harwell, J., Yacoub, E., ... & Van Essen, D.C. (2016). **A multi-modal parcellation of human cerebral cortex.** *Nature*, 536, 171–178. — The HCP-MMP1 atlas; 180 regions per hemisphere.

### Electrode Positioning
- Jasper, H.H. (1958). **The ten-twenty electrode system of the International Federation.** *Electroencephalography and Clinical Neurophysiology*, 10, 371–375. — Original 10-20 system paper; the foundation for all EEG electrode positioning.
- Oostenveld, R. & Praamstra, P. (2001). **The five percent electrode system for high-resolution EEG and ERP measurements.** *Clinical Neurophysiology*, 112(4), 713–719. — The 10-5 extension to 345 electrode positions.
- Luu, P. & Ferree, T. (2005). **Determination of the HydroCel Geodesic Sensor Nets' average electrode positions and their 10–10 international equivalents.** Technical Report, Electrical Geodesics Inc. — GSN HydroCel net electrode position specifications used in TI-Toolbox.

### Optimization for Brain Stimulation
- Dmochowski, J.P., Datta, A., Bikson, M., Su, Y., & Parra, L.C. (2011). **Optimized multi-electrode stimulation increases focality and intensity at target.** *Journal of Neural Engineering*, 8(4), 046011. — Foundational paper on optimizing electrode montages for targeted stimulation.
- Saturnino, G.B., Siebner, H.R., Thielscher, A., & Madsen, K.H. (2019). **Accessibility of cortical regions to focal TES: Dependence on spatial position, safety, and practical constraints.** *NeuroImage*, 203, 116183. — Systematic analysis of what cortical targets are reachable with optimized montages.
- Storn, R. & Price, K. (1997). **Differential Evolution – A Simple and Efficient Heuristic for global Optimization over Continuous Spaces.** *Journal of Global Optimization*, 11(4), 341–359. — The differential evolution algorithm used in flex search.

### Statistical Methods
- Maris, E. & Oostenveld, R. (2007). **Nonparametric statistical testing of EEG- and MEG-data.** *Journal of Neuroscience Methods*, 164(1), 177–190. — Cluster permutation testing method implemented in `tit/stats/`; non-parametric approach for spatial neuroimaging data.
- Nichols, T.E. & Holmes, A.P. (2002). **Nonparametric permutation tests for functional neuroimaging: a primer with examples.** *Human Brain Mapping*, 15(1), 1–25. — General introduction to permutation testing in neuroimaging.

### Safety & Dosimetry
- Bikson, M., Grossman, P., Thomas, C., Zannou, A.L., Jiang, J., Adnan, T., ... & Woods, A.J. (2016). **Safety of transcranial direct current stimulation: Evidence based update 2016.** *Brain Stimulation*, 9(5), 641–661. — Comprehensive safety review for transcranial electrical stimulation; current density limits, thermal effects, contraindications.
- Antal, A., Alekseichuk, I., Bikson, M., Brockmöller, J., Brunoni, A.R., Chen, R., ... & Paulus, W. (2017). **Low intensity transcranial electric stimulation: Safety, ethical, legal regulatory and application guidelines.** *Clinical Neurophysiology*, 128(9), 1774–1809. — Regulatory guidelines for transcranial stimulation safety.
- Esmaeilpour, Z., Kronberg, G., Reato, D., Parra, L.C., & Bhatt, D.K. (2020). **Temporal interference stimulation targets deep brain regions by modulating neural oscillations.** *Brain Stimulation*, 14(1), 55–65. — Safety and efficacy analysis specific to TI; SAR considerations for kHz-range stimulation.

### BIDS Standard
- Gorgolewski, K.J., Auer, T., Calhoun, V.D., Craddock, R.C., Das, S., Duff, E.P., ... & Poldrack, R.A. (2016). **The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments.** *Scientific Data*, 3, 160044. — The BIDS specification; directory structure and naming conventions used by TI-Toolbox.

### Review Articles & Broader Context
- Deng, Z.D., Lisanby, S.H., & Bhatt, D.K. (2013). **Electric field depth-focality tradeoff in transcranial current stimulation: simulation comparison of 50 electrode montages.** *Brain Stimulation*, 6(1), 1–13. — Demonstrated the fundamental depth-focality tradeoff that TI aims to overcome.
- Voroslakos, M., Takeuchi, Y., Brinyiczki, K., Zombori, T., Oliva, A., Fernandez-Ruiz, A., ... & Bhatt, D.K. (2018). **Direct effects of transcranial electric stimulation on brain circuits in rats and humans.** *Nature Communications*, 9, 483. — In vivo evidence of how transcranial stimulation affects neural circuits.
- Alekseichuk, I., Mantell, K., Shirinpour, S., & Bhatt, D.K. (2019). **Comparative modeling of transcranial direct current stimulation (tDCS) and temporal interference stimulation (TIS).** *Brain Stimulation*, 12(2), 536. — Direct comparison of tDCS vs TI field distributions in the same head models.
