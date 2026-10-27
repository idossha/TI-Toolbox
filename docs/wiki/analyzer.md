---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer is the last step of the pipeline. After a montage has been optimized ([flex-search]({{ site.baseurl }}/wiki/flex-search/), [ex-search]({{ site.baseurl }}/wiki/ex-search/)) and [simulated]({{ site.baseurl }}/wiki/simulator/), it reduces the field to numbers: statistics inside a target and across the whole grey matter, in mesh or voxel space. One `Analyzer` class handles both spaces, and `run_group_analysis()` runs the same analysis across subjects.

This page also defines the toolbox's field quantities, `TI_max`, `TI_normal`, `TI_avg`, `hf_peak` and `hf_sar`. The optimizer and simulator pages link here for them.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/analyzer-page.png" alt="The Analyzer page: one row analysing subject 101's L_Insula simulation on the mesh, with a 10 mm MNI sphere as its target" style="width: 100%; max-width: 1000px;">
  <em>The Analyzer (⌘4). One row is one analysis, and each row owns its own target.</em>
</div>

---

## Field quantities {#quantities-of-interest}

A **channel** is one electrode pair driven by one current source at a kHz frequency. Two channels whose frequencies differ by a small $$\Delta f$$ **share a carrier** and beat at $$\Delta f$$. Standard TI uses two channels on one carrier (4 electrodes, for example 2.000 and 2.010 kHz). Multipolar TI (mTI) uses $$2K$$ channels on $$K$$ carriers (8 electrodes for $$K = 2$$, for example 2.000/2.010 and 4.000/4.010 kHz).

A kHz field alone does not modulate neurons. What matters is the amplitude of the slow beat where the channels' fields overlap (Grossman et al. 2017). Every statistic the Analyzer reports summarises that amplitude, or one of the safety metrics, over space.

<div class="image-container" style="max-width: 800px;">
  <video controls muted playsinline style="width: 100%; border-radius: 8px;" preload="metadata">
    <source src="{{ site.baseurl }}/assets/videos/TI_timeDomain.mp4" type="video/mp4">
  </video>
  <em>Two channels sharing a carrier, each too fast to modulate neurons, sum into a field whose amplitude beats at the difference frequency. The peak-to-trough swing of that envelope is the envelope amplitude; its largest value over directions is what <code>TI_max</code> stores at every mesh element or voxel.</em>
</div>

### Two channels: the envelope amplitude {#envelope-math-and-critical-values}

Let $$\mathbf{E}_1$$ and $$\mathbf{E}_2$$ be the two channels' field amplitudes (V/m) at one point, and $$\hat{\mathbf{n}}$$ a unit direction. Along $$\hat{\mathbf{n}}$$ the channels are sinusoids of amplitude $$a = \mathbf{E}_1 \cdot \hat{\mathbf{n}}$$ and $$b = \mathbf{E}_2 \cdot \hat{\mathbf{n}}$$. Their sum swings between $$\lvert a \rvert + \lvert b \rvert$$ and $$\bigl\lvert \lvert a \rvert - \lvert b \rvert \bigr\rvert$$ once per beat, so the envelope amplitude along $$\hat{\mathbf{n}}$$ is

$$
E_{\mathrm{AM}}(\hat{\mathbf{n}})
= \Bigl\lvert \, \lvert (\mathbf{E}_1 + \mathbf{E}_2) \cdot \hat{\mathbf{n}} \rvert - \lvert (\mathbf{E}_1 - \mathbf{E}_2) \cdot \hat{\mathbf{n}} \rvert \, \Bigr\rvert
= 2 \min\bigl( \lvert a \rvert, \lvert b \rvert \bigr)
$$

Its maximum over all directions has a closed form. Label the channels so that $$\lVert \mathbf{E}_1 \rVert \ge \lVert \mathbf{E}_2 \rVert$$, and flip the sign of $$\mathbf{E}_2$$ if needed so that the angle $$\alpha$$ between the fields is at most 90°. Then

$$
E_{\mathrm{AM}}^{\max} =
\begin{cases}
2 \lVert \mathbf{E}_2 \rVert
  & \text{if } \lVert \mathbf{E}_2 \rVert \le \lVert \mathbf{E}_1 \rVert \cos\alpha \\[8pt]
\dfrac{2 \lVert \mathbf{E}_2 \times (\mathbf{E}_1 - \mathbf{E}_2) \rVert}{\lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert}
  & \text{otherwise}
\end{cases}
$$

The condition is easiest to read along $$\mathbf{E}_2$$ itself, where the projections are $$\lVert \mathbf{E}_1 \rVert \cos\alpha$$ and $$\lVert \mathbf{E}_2 \rVert$$: when the first is the larger, that direction reaches the full $$2 \lVert \mathbf{E}_2 \rVert$$. Otherwise the maximum lies in the plane of the two fields, perpendicular to $$\mathbf{E}_1 - \mathbf{E}_2$$, and is smaller.

Both formulas are from Grossman et al. 2017 (_Cell_ 169:1029, STAR Methods), who call $$E_{\mathrm{AM}}$$ the envelope modulation amplitude. SimNIBS calls $$E_{\mathrm{AM}}^{\max}$$ "TImax", Hirata et al. 2024 call it the electric field envelope (EFE) amplitude, and this toolbox stores it as **`TI_max`** (V/m). The code and some figures call $$E_{\mathrm{AM}}$$ the modulation depth (MD). `tit.calc.envelope_max` evaluates an equivalent form that needs no relabelling or sign flip (Hirata et al. 2024, _Computers in Biology and Medicine_ 178:108697, Eq. 2); it agrees with SimNIBS's `TI_utils.get_maxTI` to rounding.

### Direction: `TI_max`, `TI_normal`, `TI_avg`, tangential

The envelope fields differ only in which directions $$\hat{\mathbf{n}}$$ they use:

| Field | Direction | Meaning | `tit.calc` function |
| --- | --- | --- | --- |
| `TI_max` (`mTI_max` for mTI) | the maximum over all $$\hat{\mathbf{n}}$$ | the strongest modulation a neuron at that point could see, whatever its orientation; the default output and the default score of every optimizer | `envelope_max(fields)` |
| `TI_normal` (mesh only) | the normal of the central (mid-thickness) grey-matter surface at each node | the modulation along the axis of pyramidal-cell apical dendrites; written by every simulation that has a beat | `envelope(fields, normals)` |
| `TI_avg` (optional) | the mean over all $$\hat{\mathbf{n}}$$ | what a randomly oriented neuron sees on average | `envelope_mean(fields)` |
| tangential TI (flex-search `dir_TI_tangential`) | the maximum over the $$\hat{\mathbf{n}}$$ in the surface plane, perpendicular to the normal | the strongest modulation along the cortical sheet | `envelope_max(fields, perpendicular_to=normals)` |

By definition none of `TI_normal`, `TI_avg` and the tangential maximum exceeds `TI_max`, and `TI_normal` collapses where the field runs tangential to the cortex. For two channels, $$\mathrm{TI\_normal} = 2 \min\bigl( \lvert \mathbf{E}_1 \cdot \hat{\mathbf{n}} \rvert, \lvert \mathbf{E}_2 \cdot \hat{\mathbf{n}} \rvert \bigr)$$: each channel's field is reduced to its normal component first, and then the beat amplitude of those two components is taken. This is not the normal component of the `TI_max` vector, because the envelope is not linear in the fields. With $$\mathbf{E}_1 = \hat{\mathbf{x}}$$, $$\mathbf{E}_2 = \hat{\mathbf{y}}$$ and the normal along $$\hat{\mathbf{x}}$$, the `TI_max` vector $$(1, 1, 0)$$ projects to 1, but `TI_normal` is 0, because the second channel has no normal component to beat with. For the same reason the tangential maximum is not $$\sqrt{\mathrm{TI\_max}^2 - \mathrm{TI\_normal}^2}$$: it is the envelope maximised over the in-plane directions, which equals `TI_max` of the two fields projected onto the surface plane.

For two channels the mean over directions has a closed form. Because $$E_{\mathrm{AM}} = 2\lvert a \rvert + 2\lvert b \rvert - \lvert a + b \rvert - \lvert a - b \rvert$$ and the mean of $$\lvert \mathbf{v} \cdot \hat{\mathbf{n}} \rvert$$ over the sphere is $$\lVert \mathbf{v} \rVert / 2$$,

$$
\mathrm{TI\_avg} = \lVert \mathbf{E}_1 \rVert + \lVert \mathbf{E}_2 \rVert - \tfrac{1}{2}\bigl( \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert + \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert \bigr)
$$

`tit.calc` has five functions: `envelope`, `envelope_max` and `envelope_mean` for the envelope, and `hf_peak` and `hf_power` for the carriers ([Safety metrics](#safety-metrics)). The envelope functions take `fields = [E_1, E_2, ..., E_2K]`, one `(N, 3)` array per channel, with each two consecutive channels sharing a carrier. `envelope_max(fields, return_direction=True)` also returns the unit direction of the maximum; `TI_max` times that direction is the TI vector the [Blender export]({{ site.baseurl }}/wiki/blender/) draws. Every simulation, ex-search and mex-search computes its envelope fields with these functions.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_fig4c_ti_normal.png" alt="Schematic of two cortical surface points with the TI_max arrow and the surface normal: TI_normal is large where TI_max runs along the normal and small where TI_max runs tangential" style="width: 100%; max-width: 700px;">
  <em><code>TI_normal</code> is the envelope amplitude along the local surface normal \(\hat{\mathbf{n}}\). Where the strongest modulation runs along \(\hat{\mathbf{n}}\) (left) the two values are close; where it runs tangential to the cortex (right) <code>TI_normal</code> is small although <code>TI_max</code> is unchanged. The dashed drop lines are schematic: <code>TI_normal</code> is the envelope evaluated along \(\hat{\mathbf{n}}\), not the projection of the <code>TI_max</code> vector onto \(\hat{\mathbf{n}}\). Figure 4C from <a href="https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext">Haber et al. 2026</a>.</em>
</div>

### More carriers: multipolar TI (mTI) {#more-carriers-mti}

With $$K$$ carriers, carrier $$k$$'s two channels are $$\mathbf{E}_{2k-1}$$ and $$\mathbf{E}_{2k}$$, the order `tit.calc` expects. Along $$\hat{\mathbf{n}}$$, write $$a_k = \mathbf{E}_{2k-1} \cdot \hat{\mathbf{n}}$$ and $$b_k = \mathbf{E}_{2k} \cdot \hat{\mathbf{n}}$$. Squaring the summed signal and low-pass filtering it removes every kHz term and leaves the power envelope

$$
p(t) = P + Q \cos(2\pi \Delta f \, t),
\qquad
P = \frac{1}{2} \sum_{k=1}^{K} \left( a_k^2 + b_k^2 \right),
\qquad
Q = \sum_{k=1}^{K} a_k b_k
$$

$$P$$ is the mean carrier power along $$\hat{\mathbf{n}}$$ and $$Q$$ the amplitude of the summed beats. The amplitude envelope $$A(t) = \sqrt{2 p(t)}$$ swings between $$\sqrt{2(P - \lvert Q \rvert)}$$ and $$\sqrt{2(P + \lvert Q \rvert)}$$. With $$\mathbf{S}$$ and $$\mathbf{D}$$ the $$K \times 3$$ matrices whose rows are $$\mathbf{E}_{2k-1} + \mathbf{E}_{2k}$$ and $$\mathbf{E}_{2k-1} - \mathbf{E}_{2k}$$, $$2(P + Q) = \lVert \mathbf{S} \hat{\mathbf{n}} \rVert^2$$ and $$2(P - Q) = \lVert \mathbf{D} \hat{\mathbf{n}} \rVert^2$$, so

$$
E_{\mathrm{AM}}(\hat{\mathbf{n}})
= \Bigl\lvert \, \lVert \mathbf{S} \hat{\mathbf{n}} \rVert - \lVert \mathbf{D} \hat{\mathbf{n}} \rVert \, \Bigr\rvert
= \frac{4 \, \bigl\lvert \sum_{k} a_k b_k \bigr\rvert}{\lVert \mathbf{S} \hat{\mathbf{n}} \rVert + \lVert \mathbf{D} \hat{\mathbf{n}} \rVert}
$$

The right-hand form subtracts no near-equal numbers and is the one the code evaluates. At $$K = 1$$ it is the two-channel envelope above, $$\bigl\lvert \lvert (\mathbf{E}_1 + \mathbf{E}_2) \cdot \hat{\mathbf{n}} \rvert - \lvert (\mathbf{E}_1 - \mathbf{E}_2) \cdot \hat{\mathbf{n}} \rvert \bigr\rvert = 2\min(\lvert a \rvert, \lvert b \rvert)$$. Botzanowski et al. 2025 (_Bioelectronic Medicine_ 11:7, doi:10.1186/s42234-025-00169-6, pp. 4–5) describe this square, low-pass, square-root envelope for mTI in prose; the formula makes it explicit. It assumes that every carrier beats at the same $$\Delta f$$, that the carrier bands are far enough apart for the low-pass to remove their cross terms, and that the beats are phase-aligned. A carrier with no beating partner enters as a pair with a zero field, `[E1, E2, Eu, np.zeros_like(Eu)]`: with $$u = \mathbf{E}_u \cdot \hat{\mathbf{n}}$$ it adds $$\tfrac{1}{2} u^2$$ to $$P$$ and nothing to $$Q$$, so it lowers the envelope; `hf_peak` and `hf_power` take it as one more channel field.

`TI_max` for mTI is the maximum of $$E_{\mathrm{AM}}(\hat{\mathbf{n}})$$ over directions, as for two channels; mTI meshes name it `mTI_max`. `TI_normal` is the same expression at the surface normal, and `TI_avg` its mean over the sphere.

### How each quantity is computed {#method-and-accuracy}

| Quantity | `tit.calc` | Two channels ($$K = 1$$) | More carriers ($$K \ge 2$$) |
| --- | --- | --- | --- |
| `TI_normal` | `envelope` | exact (the expression above) | exact |
| `TI_max` / `mTI_max` | `envelope_max` | exact closed form | the maximiser is an eigenvector of $$\cos\theta\,\mathbf{C}_+ - \sin\theta\,\mathbf{C}_-$$ with $$\mathbf{C}_+ = \tfrac{1}{2}\mathbf{S}^\top\mathbf{S}$$ and $$\mathbf{C}_- = \tfrac{1}{2}\mathbf{D}^\top\mathbf{D}$$: a root-find along its three eigen-branches, then a local Newton polish. On $$10^4$$ random elements per $$K = 2, 3, 4$$ and $$4 \times 10^5$$ real grey-matter elements, none came out more than $$10^{-6}$$ (relative) below a dense reference search |
| tangential maximum | `envelope_max(..., perpendicular_to=)` | exact (closed form on the in-plane fields) | exact (roots of a degree-6 polynomial) |
| `TI_avg` | `envelope_mean` | exact closed form | 4096-direction sphere quadrature (2048 on a hemisphere, since $$E_{\mathrm{AM}}(\hat{\mathbf{n}}) = E_{\mathrm{AM}}(-\hat{\mathbf{n}})$$), about $$7 \times 10^{-4}$$ relative error at worst |
| `hf_peak` | `hf_peak` | exact, $$\max(\lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert)$$ | exact for any number of channels (zonotope vertices) |
| `hf_sar`, `hf_power_density` | `hf_power` | exact | exact |

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/mti_envelope_time.png" alt="mTI time domain: per-carrier envelopes and the joint envelope at one point" style="width: 100%; max-width: 900px;">
  <em>One point of an mTI field (4 channels, 2 carriers), with every channel field along one axis for clarity. Carrier 1's channels carry 0.5 + 0.5 V/m, carrier 2's 0.3 + 0.7 V/m. On its own, each carrier's envelope amplitude is 1.00 and 0.60 V/m (top, middle). Together (bottom), the carriers add in power and the joint envelope amplitude is 1.01 V/m (<code>envelope_max</code>). The larger numbers are other quantities: the dotted sum of per-carrier envelopes (2.00 V/m) is not a physical envelope, a TI-of-TI recombination would give 1.20 V/m, and <code>hf_peak</code> = 2.00 V/m is the instantaneous peak of the summed field. The dashed running RMS is the power view of the same field; its mean square is <code>hf_power</code> = <code>hf_sar</code>/2 = 0.54 (V/m)² (see <a href="#safety-metrics">Safety metrics</a>).</em>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/mti/mti_envelope_3d.png" alt="mTI directional envelope surface in 3D vector space" style="width: 100%; max-width: 900px;">
  <em>The same idea in vector space. (A) The four channel fields at one point. (B) The envelope amplitude along each direction, drawn as the radius \(r(\hat{\mathbf{n}}) = E_{\mathrm{AM}}(\hat{\mathbf{n}})\) (MD in the figure). <code>mTI_max</code> is the radius of the farthest point, 0.89 V/m along \(\hat{\mathbf{n}}^{*}\) here, which <code>envelope_max</code> finds. <code>TI_avg</code> is the mean radius over all directions.</em>
</div>

Two shortcuts give different and wrong numbers, and the toolbox offers neither: adding the per-carrier envelopes (carriers add in power, not amplitude), and feeding per-carrier envelopes back into the two-channel formula as if they were fields (TI-of-TI). How the toolbox tells a TI montage from an mTI montage is described on the [Simulator page]({{ site.baseurl }}/wiki/simulator/#how-the-toolbox-detects-mti).

### Safety metrics

`hf_peak`, `hf_sar` and `hf_power_density` describe the kHz exposure itself rather than the envelope. They follow Cassarà et al. 2025 (_Bioelectromagnetics_, Part I 46(2):e22542, doi:10.1002/bem.22542; Part II 46(1):e22536, doi:10.1002/bem.22536) and are computed by `tit.calc.hf_peak` and `tit.calc.hf_power` from all $$N$$ channel fields $$\mathbf{E}_1, \dots, \mathbf{E}_N$$. The two channels of a carrier differ by $$\Delta f$$, so no two channels share a frequency, and every channel field enters on its own.

**Peak and RMS.** All E-fields, `TI_max` and `hf_peak` are zero-to-peak amplitudes for zero-to-peak channel currents; `hf_power` is the time-averaged mean square $$E_{\mathrm{rms}}^2$$. Compare $$\sqrt{\mathrm{hf\_power}}$$ with RMS standards tables, or `hf_peak` with $$\sqrt{2}$$ times the limit. At 1–10 kHz ICNIRP 2010 and IEEE C95.1-2019 limit the RMS in-situ electric field ("All values are rms", ICNIRP 2010 Table 2), not SAR: their SAR limits start at 100 kHz.

**`hf_peak`** (V/m) is the largest instantaneous magnitude the summed field can reach:

$$
\mathrm{hf\_peak} = \max_{s_j \in \{+1, -1\}} \left\lVert \sum_{j=1}^{N} s_j \mathbf{E}_j \right\rVert
$$

Each channel's field oscillates between $$+\mathbf{E}_j$$ and $$-\mathbf{E}_j$$, and the magnitude of the sum is largest when every channel is at a crest or a trough, so the maximum over sign choices is the maximum over all phase combinations. For two channels it is $$\max(\lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert, \lVert \mathbf{E}_1 - \mathbf{E}_2 \rVert)$$, Cassarà Part I, Eq. 3 (p. 11). The field reaches this peak when every phase combination occurs over time. With harmonically related carriers, such as channels at 2.000, 2.010, 4.000 and 4.010 kHz, some combinations never occur, and `hf_peak` is then a conservative upper bound. The maximum is exact for any number of channels: it lies at a vertex of the zonotope spanned by the $$\pm\mathbf{E}_j$$, and the candidate sign patterns are those around the directions $$\mathbf{E}_i \times \mathbf{E}_j$$.

**`hf_power`** ((V/m)²) is the time-averaged mean-square carrier field. Fields at different frequencies add in power, not amplitude (Cassarà Part I, p. 11; Part II, p. 8), so

$$
\mathrm{hf\_power} = \frac{1}{2} \sum_{j=1}^{N} \lVert \mathbf{E}_j \rVert^2 = \bigl\langle \lVert \mathbf{E}(t) \rVert^2 \bigr\rangle = E_{\mathrm{rms}}^2
$$

The on-disk field **`hf_sar`** stores $$\sum_j \lVert \mathbf{E}_j \rVert^2 = 2\,\mathrm{hf\_power}$$. It is a heating proxy, not calibrated SAR.

**`hf_power_density`** (W/m³) is the time-averaged carrier power absorbed per volume, with the conductivity $$\boldsymbol{\sigma}$$ the simulation solved with:

$$
\mathrm{hf\_power\_density} = \frac{1}{2} \sum_{j=1}^{N} \mathbf{E}_j^{\top} \boldsymbol{\sigma} \, \mathbf{E}_j
$$

For isotropic (`scalar`) conductivity this is $$\sigma \cdot \mathrm{hf\_power}$$, with each tissue's value including any overrides; for the anisotropic models (`vn`, `dir`, `mc`) each element's full DTI conductivity tensor is used. Divided by the tissue density it is SAR, $$\mathrm{SAR} = \mathrm{hf\_power\_density} / \rho$$ (IEEE C95.1-2019, p. 35; Cassarà Part II, Eq. 1); the toolbox does not apply $$\rho$$. It is written on the volume mesh and its NIfTIs only, not projected to fsaverage: that projection interpolates the fields onto the cortical surface, not the conductivity.

`TI_avg`, `hf_peak`, `hf_sar` and `hf_power_density` are optional outputs. `SimulationConfig.output_fields` defaults to `["TI_max"]`, so a simulation writes them only when they are selected (see [Output Fields on the Simulator page]({{ site.baseurl }}/wiki/simulator/#output-fields)). The Analyzer treats each like any other field, in its own units.

#### Carrier-only controls (ΔF = 0) {#carrier-only-controls}

A carrier-only control drives both channels of a two-channel montage at the **same** frequency (for example 15,000 / 15,000 Hz), phase-locked and in phase, so there is no beat and no envelope. The channels then add into one field $$\mathbf{E}_1 + \mathbf{E}_2$$ oscillating at the carrier frequency. Following Cassarà Part II (p. 8: "coherent field superposition was used for identical frequencies"), the fields are summed as vectors first:

$$
\mathrm{hf\_peak} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert,
\qquad
\mathrm{hf\_sar} = \lVert \mathbf{E}_1 + \mathbf{E}_2 \rVert^2,
\qquad
\mathrm{hf\_power\_density} = \tfrac{1}{2} (\mathbf{E}_1 + \mathbf{E}_2)^{\top} \boldsymbol{\sigma} \, (\mathbf{E}_1 + \mathbf{E}_2)
$$

`hf_peak` keeps its TI value where the two fields are within 90° of each other and is smaller elsewhere. `hf_sar` gains the cross term $$2\,\mathbf{E}_1 \cdot \mathbf{E}_2$$, so it ranges from twice its TI value (equal, aligned fields) to zero (equal, opposed fields). For example, $$\lVert \mathbf{E}_1 \rVert = 1$$ and $$\lVert \mathbf{E}_2 \rVert = 0.8$$ V/m at 120° give `hf_peak` = 1.56 V/m in a TI run and 0.92 V/m in a carrier-only run. "In phase" follows the simulation's sign convention: each channel's first electrode is driven positive at the same instant.

`TI_max`, `TI_avg` and `TI_normal` are undefined without a beat and are **not computed**; a carrier-only run writes only `hf_peak`, `hf_sar` and/or `hf_power_density`. To set one up, in the app or from Python, see [Carrier-only control on the Simulator page]({{ site.baseurl }}/wiki/simulator/#carrier-only-control).

---

## Targets {#defining-the-roi}

An analysis needs a target. Open a row's **Job settings** and choose one of four target types: **Cortical**, **Subcortical**, **Spherical** or **NIfTI mask**. Each row owns its own target.

### Sphere

- Each row of the **X / Y / Z / Radius** table is one sphere; **Add sphere** adds another, the bin icon removes one
- Coordinates are in **Subject** or **MNI** space; MNI centres are transformed into each subject's anatomy automatically
- Several spheres in one row run as **separate analyses**, one per sphere, never as a union; the row's target line ends in "(separate jobs)". In a group run, each sphere is its own group job
- A union of spheres is Python-only: `analyzer.analyze_spheres([(x, y, z, r), ...])` measures them as one ROI (overlapping spheres are not double-counted). Its output folder is named `spheres<N>_...`, and long unions are shortened to the first sphere plus a hash

### Cortical region

- Analyze one or more atlas regions as a single combined ROI — passing more than one region name unions their masks into one target, and the result's region name is the selected names joined with `+`
- **Combine regions into one ROI** (under the target, on by default): untick it to run one analysis per selected region instead of a union. In a group run, each region is then its own group job
- In mesh space, a bare region name (e.g. `cuneus`) expands to both hemispheres (`lh.cuneus` + `rh.cuneus`)
- **Cortical** lists the subject's surface atlases: `DK40`, `a2009s`, `HCP_MMP1`. In **Voxel** space the same names read volume parcellations: `DK40` reads the DKT volume (FastSurfer's `aparc.DKTatlas+aseg.deep.mgz`, or FreeSurfer's `aparc.DKTatlas+aseg.mgz`), `a2009s` reads `aparc.a2009s+aseg.mgz`, which only a FreeSurfer `recon-all` run writes, and `HCP_MMP1` has no volume version, so a voxel analysis of it stops with an error — analyze it in **Mesh** space. See [FreeSurfer reconstruction and subregions]({{ site.baseurl }}/wiki/fastsurfer/#freesurfer-reconstruction-and-subregions) for which run writes which file
- No surface atlas exists in MNI space; the shipped MNI atlases, the cortical ones included, are label volumes and are used through **Subcortical**

### Subcortical region

- Choose a volume atlas and one or more of its regions. **Combine regions into one ROI** works as for cortical regions, in single and group runs
- **Subject** space offers the subject's own label volumes: charm's `segmentation/labeling.nii.gz` (whole thalamus, hippocampus, amygdala, …), the FastSurfer and FreeSurfer volumes, including FreeSurfer's hippocampal-amygdala and thalamic-nuclei subfields, and any label volume placed in `m2m_<id>/masks/` (listed as `masks/<file>`)
- **MNI** space offers the atlases shipped with TI-Toolbox (CIT168, MASSP 2021, Harvard-Oxford cortical and subcortical, Cerebellum, Glasser HCP-MMP1.0, Schaefer 2018). The selected regions are transformed into each subject's anatomy with the subject's own registration, exactly as an MNI mask is
- Measure deep structures in **Voxel** space. A deep structure has no cortical surface, so in **Mesh** space the job stops with "… does not overlap the gray-matter surface; analyze it in voxel space instead"
- A region named exactly as an atlas label gets that label, before any longer label containing the name ("subiculum" is not "parasubiculum")
- Results go to `Analyses/<Mesh|Voxel>/subcortical_<region>_<atlas>/`. Python: `analyzer.analyze_subcortical(atlas, region, coordinate_space="subject")`

### Custom NIfTI mask targets

Choose **NIfTI mask** in a job's Target editor and import a `.nii` or `.nii.gz` file. All positive voxels belong to the target. Declare **Subject** or **MNI** explicitly: subject masks retain their coordinates, while MNI masks use the subject's nonlinear m2m registration and nearest-neighbor sampling. Group analysis requires an MNI mask, registered separately for each subject.

Mesh analysis samples the mask at gray-matter surface nodes and reports surface-area statistics. Voxel analysis samples it onto the subject field grid and intersects it with the tissue selected in the job settings, retaining volume statistics. An empty overlap fails with a clear error. The script equivalent is `analyzer.analyze_mask(mask_path, coordinate_space="mni")`; job JSON uses `analysis_type="mask"`, `mask_path`, and `coordinate_space`.

### Tissue

- **Job settings ▸ Space options ▸ Tissue** (Gray matter / White matter / GM + WM) applies to **voxel space only** — it is disabled and fixed to gray matter whenever the row's Space is Mesh. The target itself has no tissue or volumetric-evaluation control in the Analyzer
- In voxel mode, the tissue choice selects which field file is loaded by filename prefix (`grey_` for GM, `white_` for WM, no prefix for GM + WM) and builds the corresponding tissue mask

### Target preview

The Scene pane follows the active job. Cortical atlas regions remain clickable. Masks, subcortical regions and spheres show a read-only target extent on subject anatomy; edit the target in its form. This previews the geometry, before the analysis applies its tissue and mesh settings. Incomplete targets or unavailable registration show an explanatory message.

---

## Mesh and voxel space

Each row analyses its field in one of two spaces:

- **Mesh** (`space="mesh"`) reads the field on the subject's central grey-matter surface, which the simulation writes with SimNIBS `msh2cortex`. Each node is weighted by its surface area, so sizes come out in mm² and cm². `TI_normal` exists only here, and the tissue is fixed to grey matter.
- **Voxel** (`space="voxel"`) reads the simulation's NIfTI on the subject grid and keeps the voxels of the selected tissue. Each voxel is weighted by its volume, so sizes come out in mm³ and cm³. Measure deep structures here.

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_max.png" alt="TI_max on the left insula, drawn over a translucent cortex">
    <em><code>TI_max</code> in a cortical target (left insula), mesh space.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_normal.png" alt="TI_normal on the left insula, drawn over a translucent cortex">
    <em><code>TI_normal</code> in the same target.</em>
  </div>
</div>

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_max.png" alt="TI_max in a 10 mm spherical target on the cortical surface">
    <em><code>TI_max</code> in a 10 mm sphere at (−31.3, 24.0, −37.0), mesh space.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_normal.png" alt="TI_normal in the same 10 mm spherical target">
    <em><code>TI_normal</code> in the same sphere.</em>
  </div>
</div>

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_voxel_montage_1.png" alt="TI_max in the right hippocampus on sagittal and axial T1 slices">
    <em><code>TI_max</code> in a right-hippocampus target, voxel space, 1 mA per channel.</em>
  </div>
</div>

---

## Statistics

An analysis reduces the field to the statistics below. "Positive" elements are the nodes or voxels where the field is above zero; only they enter the statistics.

| Statistic | `AnalysisResult` field | Definition |
| --- | --- | --- |
| **Target intensity** | `roi_mean`, `roi_max`, `roi_min` | Mean, maximum and minimum of the field over the target's positive nodes (mesh) or voxels (voxel). The mean is weighted by node area or voxel volume. Compare it against dose thresholds and between montages. |
| **Reference intensity** | `gm_mean`, `gm_max` | The same over the whole grey-matter surface (mesh) or the whole selected tissue (voxel). The reference includes the target. It is fixed; only the optimizers accept a user-defined non-ROI. |
| **Focality ratio** | `roi_focality` | `roi_mean / gm_mean`. 1 means the target is no stronger than the average of the reference; higher is more selective. Ex-search reports the same ratio as `Focality`, but averages over the leadfield's volume elements, so its values differ. |
| **Normal component** | `normal_mean`, `normal_max`, `normal_focality` | `roi_mean`, `roi_max` and `roi_focality` recomputed on `TI_normal` (mesh only). |
| **Peak** | `percentile_95`, `percentile_99`, `percentile_99_9` | Area- or volume-weighted percentiles of the field over the grey matter (mesh) or the selected tissue (voxel): the smallest value at or below which that fraction of the area or volume lies. `percentile_99_9` is a robust peak that ignores single outlier elements. |
| **Hot-spot size** | `focality_50_area` … `focality_95_area` | Grey-matter area in $$\mathrm{cm}^2$$ (mesh), or selected-tissue volume in $$\mathrm{cm}^3$$ (voxel), where the field is at least 50, 75, 90 or 95 % of `percentile_99_9`. A small `focality_50_area` means a compact hot spot. |

The 99.9th-percentile peak and the area above a fraction of it are the conventions of SimNIBS's field summary (`get_percentiles`, `get_focality`). The peak and hot-spot statistics describe the whole grey matter (or tissue) and do not depend on the target. There is no separate whole-head analysis: these statistics and the histogram come with every analysis. Every statistic is in the units of the analysed field, so selecting `hf_sar` gives means in (V/m)², not field strengths.

---

## Outputs

### What an analysis writes

One folder per analysis, under `Analyses/<Mesh|Voxel>/<name>/`, holding the data, the field-distribution histogram and **exactly one scene**:

| File | What it is |
|---|---|
| `results.csv` | every statistic in the [AnalysisResult](#analysisresult-fields), one row each |
| `analysis.json` | the target and settings the run used |
| `roi_overlay.msh` + `.msh.opt` (mesh) | the central surface with `<field>_ROI` node data: the field at the ROI's nodes, exactly `0` everywhere else (and `TI_normal_ROI` when the run had a normal field) |
| `roi_overlay.nii.gz` (voxel) | the field, zero outside the ROI, on the field's own grid |
| `histogram.png` | the field distribution over the whole grey matter (mesh) or the whole selected tissue (voxel) — area-weighted (mesh) or volume-weighted (voxel) — with every bar coloured by the fraction of it inside the ROI (blue → red, colour bar), the ROI mean and the focality cutoffs (50/75/90/95 % of the GM 99.9th percentile) marked, and a whole-head / ROI stats box |
| `scene.tetravox.json` | a Tetravox scene of the overlay: in voxel space the field over your `T1.nii.gz`; in mesh space the whole cortex translucent with the ROI's field coloured on top, cursor on the ROI, colour bar on |
| `scene.png` | a picture of that scene, when Tetravox is installed on the machine running the app |

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_lh.insula_whole_head_roi_histogram.png" alt="Analyzer field-distribution histogram" style="width: 100%; max-width: 850px;">
  <em>Example field-distribution histogram with the target statistics and the grey-matter focality cutoffs. This example is from v2, which counted nodes; v3 weights each bar by area or volume.</em>
</div>

The scene is a few kilobytes and points at the overlay and the T1 — nothing is copied.

### AnalysisResult fields

Every analysis call returns an `AnalysisResult` dataclass. It holds the [statistics](#statistics) above under the same names, plus:

- `field_name`, `region_name`, `space` ("mesh"/"voxel"), `analysis_type` ("spherical"/"cortical"/"subcortical"/"mask")
- `n_elements`: the target's positive nodes (mesh) or voxels (voxel)
- `total_area_or_volume`: their area in $$\mathrm{mm}^2$$ (mesh) or volume in $$\mathrm{mm}^3$$ (voxel)
- The `normal_*` fields are `None` in voxel space, and for runs that predate `TI_normal` support for their mode -- see [mTI analyses](#mti-analyses)

### Viewing the results

Open a finished analysis from [Results]({{ site.baseurl }}/wiki/results/), from the job's **Artifacts** tab (**Open in Tetravox**), or by double-clicking `scene.tetravox.json`. Mesh and NIfTI outputs both open in TetraVox, the separate desktop viewer the app installs and launches (see [Viewer]({{ site.baseurl }}/wiki/visualizers/)), and every target type writes the same overlay and scene. Version 2.x opened mesh results in Gmsh and NIfTI results in Freeview; v3 ships neither (see [the v3.0.0 release notes]({{ site.baseurl }}/releases/v3.0.0/)).

---

## mTI analyses

The Analyzer handles multipolar (mTI) simulations with the same `Analyzer` class, the same `analyze_sphere` / `analyze_cortex` / `analyze_spheres` calls, and the same target types; there is no mTI mode to select. The only signal it uses is whether `{simulation}/mTI/mesh/` exists on disk.

### What it reads

| Space | mTI source                                               | Standard TI source                      |
| ----- | -------------------------------------------------------- | --------------------------------------- |
| Mesh  | `mTI/mesh/surfaces/{sim}_mTI_central.msh` (field values) | `TI/mesh/surfaces/{sim}_TI_central.msh` |
| Voxel | `mTI/niftis/` (`grey_` / `white_` prefix per tissue)     | `TI/niftis/`                            |

An mTI run also writes each carrier's own two-channel envelope (`TI_AB`, `TI_CD`, ...) into `TI/mesh/`. The Analyzer does not read them, and they are not the mTI result.

### Fields

`TI_max` and `mTI_max` are aliases for the [joint envelope amplitude](#more-carriers-mti). Whichever spelling is requested, the Analyzer resolves it to the name the detected simulation type wrote, so the Field selector lists it once. `TI_avg`, `hf_peak`, `hf_sar` and `hf_power_density` can be selected when the run wrote them.

`TI_normal` is computed for mTI too: the simulator evaluates the $$K$$-carrier envelope along the cortical surface normal (`envelope`) and writes `{simulation}_mTI_normal.msh` under `mTI/mesh/`. The Analyzer reads it when `TI_normal` is requested, and fills the `normal_*` statistics as for standard TI. mTI simulations run before this support have no normal mesh: requesting `TI_normal` raises `FileNotFoundError`, and the `normal_*` statistics are `None`. Re-run the simulation to get them.

---

## Group Analysis

`run_group_analysis()` runs one analysis — one simulation, space, field and target — over several subjects and returns a `GroupResult`. In the app it is the Analyzer's **Combine into one group analysis** switch: each row contributes its subject, and the run is refused, with the difference named, unless every row has the same simulation, space, field and target.

- **One simulation for every subject.** It is a simulation folder name each subject has (the same montage simulated in each). Rows with different simulations are refused; to compare montages within one subject, run ordinary single analyses, one row per montage.
- MNI coordinates, MNI masks and MNI atlases are transformed into each subject's own anatomy automatically; a group mask must be in MNI space.
- Several spheres, or several regions with **Combine regions into one ROI** unticked, give one group job per sphere or region.

Each run writes its own folder; each subject's own results also go to its `Analyses/` folder, as for a single analysis:

```
derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>_<YYYYMMDD>_<HHMMSS>/
├── group_summary.csv               # one row per subject plus an AVERAGE row
├── group_comparison.pdf            # 2×2 bars per subject: ROI mean, max, focality, normal mean
└── group_analysis_<timestamp>.log
```

Group runs are listed under **Results ▸ Group ▸ Group analyses**. Group analyses from earlier
versions shared one folder, `derivatives/ti-toolbox/logs/group_analysis/`, where each run replaced
the last; those files stay where they are.
