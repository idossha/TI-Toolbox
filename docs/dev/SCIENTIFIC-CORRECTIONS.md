# Scientific corrections from v2.x to v3.0.0

An external audit of the shared scientific core on **2026-09-07** found six defects in the
statistics engine and the field analyzer. All six were reproduced independently in this
repository, fixed on `feature/v3-electron-gui`, and pinned by tests. This page is the
record a user needs to decide whether their existing results are affected and what to do
about it.

Scope: `tit/stats/**` and `tit/analyzer/**`. Simulation and optimization (`tit/sim`,
`tit/opt`, `tit/calc`, `tit/fields`) were also audited; what was checked and found correct
is listed under [Verified unchanged](#verified-unchanged), and the one genuinely open
modelling question is under [Open decisions](#open-decisions).

**How to read the version ranges.** The `tit` Python package first appears at **v2.2.3**
(as `tit/stats/stats_utils.py`) and was restructured into `tit/stats/engine.py` +
`tit/analyzer/analyzer.py` at **v2.3.0**. Ranges below were verified by reading the tagged
sources, not inferred.

| | What was wrong | Affected | Effect on results |
|---|---|---|---|
| [SCI-01](#sci-01) | Two-sided/left-tailed cluster test merged opposite-sign clusters and built its null with `max()` of signed masses | 2.2.3 – 2.5.0 | Cluster p-values wrong in both directions; **re-run** |
| [SCI-02](#sci-02) | Group stacking accepted equal-shape images with different affines | 2.3.0 – 2.5.0 | Silent cross-subject misalignment; **re-run** if grids differed |
| [SCI-03](#sci-03) | Voxel focality volumes divided by 100 instead of 1000 | 2.3.0 – 2.5.0 | `focality_*_area` from voxel analyses **10× too large**; rescalable |
| [SCI-04](#sci-04) | Sampled permutation p-value was `b/m`, so `p = 0` was reachable | 2.2.3 – 2.5.0 | Smallest p understated; **rescalable** |
| [SCI-05](#sci-05) | Voxel geometry read header zooms instead of the affine | 2.3.0 – 2.5.0 | Wrong only for sheared affines; **re-run** those |
| [SCI-06](#sci-06) | Zero standard error collapsed to `t = 0, p = 1` | 2.2.3 – 2.5.0 | Perfectly separated voxels reported as null; **re-run** |

---

## SCI-01

**What was wrong.** In two-sided and left-tailed cluster inference the significance mask
was labelled with a bare `scipy.ndimage.label`, so a positive and a negative
supra-threshold blob that touch became one cluster whose signed mass is their *difference*,
and the permutation null was built with `max()` over signed cluster masses, which under a
left or two-sided tail selects the cluster **closest to zero** rather than the most
extreme one.

**Affected.** 2.2.3 – 2.5.0 (`tit/stats/stats_utils.py` at 2.2.3–2.2.4; `tit/stats/engine.py`
from 2.3.0; the fsaverage surface twin `tit/stats/surface.py` from 2.4.0). Verified present
on `main` at v2.5.0. One-sided **`alternative="greater"`** analyses are *not* affected: the
oriented statistic there is the signed mass itself, and an exhaustive check over all 20
relabellings of a 3-vs-3 design found 0/20 permutations differing.

**What changes and by how much.** Everything downstream of the cluster null: the null
distribution, `cluster_stat_threshold`, per-cluster p-values, `significant_clusters.csv`,
and the significance mask. On the same exhaustive 3-vs-3 / 8-voxel design used in the test,
2/20 permutations differed under `alternative="less"` and 3/20 under `"two-sided"`; the
largest single discrepancy was a null value of **−64.06 where the correct oriented value is
+64.06** — i.e. the v2.x null was not merely small, it had the wrong sign, so nearly any
observed cluster cleared it. Two-sided results were anti-conservative (too many
"significant" clusters); genuine symmetric adjacent effects could also be erased entirely
(a fused cluster of mass ≈ 0).

**How to detect affected results.** Any `derivatives/.../stats/` output produced with
`alternative` of `two-sided` (the default) or `less`. In the analysis log, `Threshold
(p<0.050): <negative number> mass units` is a certain tell — an oriented cluster threshold
can never be negative. A cluster with `stat_value` near 0 and a large `size` is the fused
opposite-sign case.

**What to do.** Re-run. There is no rescaling; the null distribution itself was wrong.

**Fix.** `682cbfcf` — *fix(stats): correct two-sided cluster inference and permutation p-values*.
`engine.label_signed` labels positive and negative voxels as separate components;
`engine.tail_statistic` maps a cluster to a statistic that is monotone in extremeness
(mass for `tail=+1`, −mass for `tail=−1`, |mass| for `tail=0`), so observed and permuted
values live on the same scale and the comparison is always right-tailed.
`surface._label_graph_signed` / `surface._max_cluster_stat` do the same on the fsaverage
graph. `correct_groups` now also sign-restricts one-sided cluster forming, which it
previously did only in the correlation path.

**Tests.** `tests/numerical/test_sci01_cluster_sign.py` — 14 tests, including a from-scratch
reference implementation (chain connectivity, MNE `permutation_cluster_1samp_test`
semantics) driven over *every* relabelling of a tiny design through the production
`_run_single_permutation`, for `mass`/`size` × `two-sided`/`less`/`greater`; plus a test
that the volume and surface backends agree on a chain graph, and two tests that pin the
v2.x behaviour numerically so the defect is documented, not just described.

---

## SCI-02

**What was wrong.** `load_group_data_ti_toolbox` kept the **first** subject's affine and
never compared the others. Any set of images sharing an array shape was stacked and
analysed voxel-by-voxel, even when subjects were translated, rotated, differently scaled or
left/right flipped relative to each other.

**Affected.** 2.3.0 – 2.5.0 (`tit/stats/nifti.py`, added at 2.3.0). Verified present on `main`.

**What changes.** Nothing, for the normal case: subjects normalised to the same MNI template
by the toolbox share a grid exactly, and their results are bit-identical. For a mismatched
group the loader now **raises** instead of producing a silently meaningless map.

**How to detect affected results.** For each subject in a past group analysis, compare
`nibabel.load(f).affine`. If any pair differs by more than 1e-3 mm in origin or 1e-4 in the
direction block, that analysis compared different anatomy across subjects. A sign flip in
`det(affine[:3,:3])` between subjects (a handedness difference) is the worst case and is
now called out by name in the error.

**What to do.** Re-run affected analyses after resampling the subjects onto one reference
grid. Results from a group whose affines already matched need nothing.

**Fix.** `35a833ec` — *fix(stats): require a common voxel grid when stacking a subject group*.
`tit/stats/nifti.py::_check_same_grid` compares shape, direction block and origin against
the first subject and raises a `ValueError` naming the subject id, its file and the
reference file. The same commit replaces the `list` + `np.stack` + `astype` accumulation
with a preallocated output array (the audit's low-priority memory item): peak memory drops
from roughly 3× the final array to 1× plus one volume.

**Tests.** `tests/numerical/test_sci02_grid_consistency.py` — translation, rotation,
voxel-size and handedness variants each rejected with the subject named; float-noise
jitter accepted; end-to-end rejection through the public loader; and a positive case that
pins ordering and the template affine.

---

## SCI-03

**What was wrong.** `Analyzer._compute_focality_metrics` divided the summed weights by
`100.0` with the comment `mm^2 -> cm^2`. That is right for the **mesh** path, which weights
by node area in mm². The **voxel** path passes weights in mm³, where the factor to cm³ is
**1000**.

**Affected.** 2.3.0 – 2.5.0. This is a regression introduced with the unified `Analyzer`:
the v2.2.x `tit/analyzer/voxel_analyzer.py` it replaced divided by 1000 correctly
(`# Convert from mm³ to cm³ for consistency with ex-search`). Verified present on `main`.

**What changes and by how much.** `focality_50_area`, `focality_75_area`,
`focality_90_area`, `focality_95_area` in **voxel-space** analyses only — CSV, JSON and
report values are now exactly **one tenth** of the v2.3.0–v2.5.0 numbers. Mesh-space
values are unchanged. `total_area_or_volume` was always mm²/mm³ and is unchanged. The
field **names** are deliberately kept (`..._area` for a volume) so that scripts and the
group aggregator keep working; the documented unit for the voxel case is cm³.

**How to detect affected results.** Any `analysis_results.csv` / `*.json` under a
voxel-space analysis directory written by 2.3.0–2.5.0. A quick sanity check: a
`focality_50_area` of, say, 120 for a grey-matter ROI is 120 cm³ — implausibly close to the
volume of a whole hemisphere; the true value is 12 cm³.

**What to do.** **Rescale**, no re-run needed: divide every `focality_*_area` from a
voxel-space analysis by 10. (Re-running gives the identical answer.)

**Fix.** `5b3bc6cb` — *fix(analyzer): voxel focality volumes in cm^3, geometry from the affine*.
`_compute_focality_metrics` gained an explicit `weight_to_cm` parameter that must track the
unit of `weights`; the voxel path passes `1000.0`, the mesh path keeps the default `100.0`.

**Tests.** `tests/numerical/test_sci03_sci05_analyzer_geometry.py` — all four cutoffs for
area and volume, the anisotropic-voxel case, and an explicit assertion that the two
divisors differ by the factor 10 that was the error.

---

## SCI-04

**What was wrong.** `pval_from_histogram` returned `b / m` — the fraction of the `m`
sampled permutations at least as extreme as the observation. With a *sampled* (Monte-Carlo)
null that is not a valid p-value: it can return **0**, and it is anti-conservative exactly
in the tail where cluster inference operates.

**Affected.** 2.2.3 – 2.5.0. Verified present on `main`.

**What changes and by how much.** Every permutation p-value moves up by a bounded amount:
`p_new = (b + 1) / (m + 1)` instead of `b / m`. At the default 1000 permutations the floor
becomes `1/1001 ≈ 9.99e-4` instead of 0, and a p of `b/1000` becomes `(b+1)/1001` — a shift
of at most 0.001 in absolute terms. No cluster crosses `alpha = 0.05` because of this
change unless it sat within 0.001 of the threshold. Reported `p = 0.0000` values in old
outputs should be read as `p < 1/(m+1)`.

**What to do.** **Rescale** if you only need the numbers: `p_new = (p_old * m + 1)/(m + 1)`
with `m` the permutation count recorded in the analysis log. Re-run if a borderline cluster
matters.

**Fix.** `682cbfcf` (same commit as SCI-01).
`pval_from_histogram` gained `sampled=True` (the default, the estimator of Phipson & Smyth
2010); `sampled=False` restores the exact `b/m`, which is correct **only** when the null is
the exhaustive enumeration of the permutation group, and is now documented as such.

**Tests.** `tests/numerical/test_sci04_sci06_pvalues_degenerate.py` pins the floor
`1/(m+1)` for several `m`, checks the counts by hand for each tail, checks the
`sampled=False` opt-out, and asserts the new estimator is never below the naive one.
`tests/test_stats_engine.py::TestPvalFromHistogram` was updated from the `b/m` values it
previously pinned.

---

## SCI-05

**What was wrong.** Voxel geometry came from `img.header.get_zooms()` — the **column norms**
of the affine. Voxel volume was `prod(zooms)` and spherical-ROI distance was
`sqrt(Σ (zoom_k · Δv_k)²)`. Both silently assume the voxel axes are orthogonal in world
space, which is false for any sheared affine.

**Affected.** 2.3.0 – 2.5.0. Verified present on `main`. **Not** affected in practice for
images on an orthogonal grid (all MNI-normalised outputs the toolbox writes, and every
subject image the standard pipeline produces): for an orthogonal affine `prod(zooms) ==
|det A|` and the two distance formulas coincide exactly, so results are bit-identical.

**What changes and by how much.** Only for sheared affines — a hand-written affine, or a
volume imported from an external tool with an oblique acquisition matrix. On the test's
representative shear, `prod(zooms)` overestimates the voxel volume by **11.3 %**, which
propagates directly into `total_area_or_volume` and every `focality_*_area`, and the
spherical ROI was the wrong ellipsoid.

**How to detect affected results.** For the field image used,
`A = nibabel.load(f).affine[:3,:3]`; if `abs(prod(header.get_zooms()[:3]) - abs(det(A)))`
is more than float noise, the affine is sheared and that analysis is affected.

**What to do.** Re-run any analysis on a sheared image.

**Fix.** `5b3bc6cb` (same commit as SCI-03).
`voxel_volume_mm3(affine)` returns `|det(A)|`; `_world_distance_grid(affine, centre, shape)`
returns `‖A(v − c)‖`. `_analyze_voxel_roi` now takes the affine and derives the volume
itself, so there is no second, disagreeing source of geometry.

**Tests.** `tests/numerical/test_sci03_sci05_analyzer_geometry.py` — the distance grid is
compared against world points transformed independently with
`nibabel.affines.apply_affine` on an asymmetric sheared affine, with an explicit assertion
that the v2.x zoom formula *disagrees* there; the determinant path is checked against the
zoom product, on an orthogonal affine, and for a negative determinant (LAS storage).

---

## SCI-06

**What was wrong.** `ttest_ind` and `ttest_rel` set `t = 0` (hence `p = 1`) for every voxel
with zero standard error. That conflates two opposite situations: a truly undefined `0/0`
(identical constant groups) and a **nonzero** contrast over zero within-group variance —
perfect separation, the strongest evidence the data can carry, which `scipy` reports as
`t = ±inf, p → 0`.

**Affected.** 2.2.3 – 2.5.0. Verified present on `main`.

**What changes.** Voxels with zero within-group variance. Previously all of them were
reported as "no effect"; now `0/0` gives `nan` and `±x/0` gives `±inf` with the
tail-consistent p, matching `scipy.stats.ttest_ind` / `ttest_rel` exactly (checked against
scipy in the test for all three `alternative` values). Because a `nan` or `inf` cluster mass
would corrupt the permutation machinery, `ttest_voxelwise` now *excludes* degenerate voxels
from `valid_mask` and logs how many, and the permutation workers neutralise any degenerate
voxel a relabelling happens to create (slightly conservative, and preferable to an infinite
null).

**How to detect affected results.** Look for voxels constant across every subject in a
group (common in masked or thresholded inputs, and in small samples). Such voxels silently
carried `p = 1` before; they are now excluded, with a `WARNING` in the analysis log naming
the count.

**What to do.** Re-run. The change can only add evidence at voxels that previously carried
none, and can change `valid_mask` and therefore cluster geometry.

**Fix.** `682cbfcf` (same commit as SCI-01).
`engine._safe_t` divides under `np.errstate` so the IEEE result (`±inf` / `nan`) reaches the
`t.sf` calls unchanged; `_neutralise_degenerate` and the `ttest_voxelwise` mask handle the
downstream.

**Tests.** `tests/numerical/test_sci04_sci06_pvalues_degenerate.py` — `0/0`, `+/0` and `−/0`
for `two-sided` / `greater` / `less`, paired and unpaired, each compared against `scipy`;
plus a test that the v2.x `t = 0, p = 1` answer is no longer produced, and one that
`ttest_voxelwise` drops degenerate voxels from `valid_mask`.

---

## Lower-priority items

Two of the audit's lower-priority items were cheap enough to fix here.

- **`channels` must partition `fields`** (`tit/calc.py::_resolve_channels`). A field index
  that no channel referenced was silently dropped, so the envelope described a different
  montage from the one passed — and from the one `hf_peak`/`hf_sar` described, since those
  always sum every field. It now raises, naming the unused indices; a carrier that does not
  beat is spelled as its own channel with an empty `group_b`, which was already supported.
  Fix `4abf5181`; test `tests/test_calc_mti.py::TestChannelsMustPartitionFields`.
- **`hf_peak` exactness is now queryable** (`tit/fields.py::hf_peak_is_exact`). Above
  `EXACT_SIGN_ENUM_MAX_FIELDS` (8) carriers the direction sweep returns a *lower bound* on
  the true worst-case peak, so it is slightly non-conservative as a safety metric. That was
  documented in the docstring but not exposed; callers that record or display `hf_peak` can
  now carry the flag. Fix `4abf5181`; test `tests/test_fields.py`.

Two were left, deliberately:

- **Envelope cancellation at extreme P/Q** (`tit/calc.py::_envelope_from_PQ`). At `Q → P`
  the difference `sqrt(2(P+Q)) − sqrt(2(P−Q))` loses precision, and the rationalised form
  `2Q·sqrt(2)/(sqrt(P+Q) + sqrt(P−Q))` is better conditioned. The current form already
  clamps negative round-off inside both roots, and the regime where it matters
  (`|P − Q| / P` below ~1e-12) is far below the accuracy of the FEM fields it consumes.
  Worth doing, but it is a numerical-quality change in the simulation core rather than a
  correctness defect, and it belongs with the SCI-07 decision below.
- **Preallocation elsewhere.** Only the group-stacking loop was changed; the other
  accumulations are small.

---

## Open decisions

### SCI-07 — what a shared carrier means for the exposure metrics

**No behaviour was changed.** This is a modelling question for the maintainer.

`montage.channels` lets several FEM fields be grouped onto one carrier (the shared-carrier
design of Lee et al. 2022, several electrode pairs driven at the same frequency). The
envelope path (`tit/calc.py::_resolve_channels`, used by `tit/sim/mTI.py`) **sums
same-carrier fields first** and then forms the beat, which is exact: fields at the same
frequency and phase superpose coherently, so pre-summing and pairing once is algebraically
identical to what a single pair carrying that sum would produce.

The carrier-exposure metrics in `tit/fields.py` (`hf_peak`, `hf_sar`) do the opposite:
they treat **every raw field as its own incoherent carrier**, `hf_sar = Σᵢ |Eᵢ|²` and
`hf_peak = max_s |Σᵢ sᵢEᵢ|`, and ignore `channels` entirely. The two conventions disagree
by a factor that grows with the grouping. For **two aligned unit fields** put into one
channel (`channels=[([0], [1])]` vs. the same two fields treated as two carriers):

| | raw fields (v2.x and v3.0 behaviour) | grouped onto one carrier |
|---|---|---|
| `hf_sar = Σ\|E\|²` | `1 + 1 = 2` | `\|E₁+E₂\|² = 2² = 4` |
| RMS (`= hf_sar / 2`) | `1` | `2` |
| `hf_peak` | `max_s \|s₁E₁+s₂E₂\| = 2` | `2` (unchanged) |

**Model A — fields are independent carriers (today's behaviour).** Each FEM field is driven
at its own frequency; power adds incoherently. `hf_sar = Σ|Eᵢ|²` is then correct and
`channels` is purely an envelope-side bookkeeping device. Implication: a montage that groups
fields reports the *same* SAR whether or not the grouping is declared, and the reported SAR
is a **lower bound** if the fields really do share a frequency, because coherent addition of
same-frequency fields gives `|ΣEᵢ|² ≥ Σ|Eᵢ|²` whenever they are not mutually orthogonal.

**Model B — `channels` is the physical truth.** Fields inside a group *are* the same
carrier, so they must be summed before any exposure metric is computed:
`hf_sar = Σ_channels |Σ_{i∈ch} Eᵢ|²`, and `hf_peak` enumerated over channel sums rather than
raw fields. Implication: `hf_sar` and RMS rise (by up to the number of grouped fields, when
they are aligned); `hf_peak` is unchanged, because its sign enumeration already reaches the
coherent sum. This makes the safety metric consistent with the envelope, and conservative.

**Recommendation: Model B**, gated on the montage actually declaring `channels`. The
envelope path already asserts that grouped fields are coherent; letting the safety metric
assume the opposite for the same montage is the inconsistency. Model B is also the
conservative direction — it can only raise reported exposure — which is the right default
for a safety metric. Concretely: give `hf_peak` / `hf_sar` an optional `channels` argument,
have `tit/sim/mTI.py` pass `self.montage.channels`, and leave the `channels=None` path
bit-identical so that every montage without an explicit grouping is unaffected. The
docstrings in `tit/calc.py::get_mTI_vectors` and `tit/fields.py` would then need the
sentence "`hf_peak`/`hf_sar` are unaffected by `channels`" removed rather than kept as a
caveat.

Deciding this also settles whether the `_envelope_from_PQ` rationalisation above is worth
doing in the same pass.

---

## Verified unchanged

The audit examined these and found no defect; they are recorded so the same ground is not
re-covered.

- **`alternative="greater"` cluster inference.** The oriented statistic under a right tail
  *is* the signed mass, so SCI-01 does not reach it. Confirmed empirically: 0 of 20
  exhaustive relabellings of the test design changed value.
- **The mesh (surface-node-area) focality path.** Its weights are mm² and its `/100` divisor
  is correct; mesh `focality_*_area` values from 2.3.0–2.5.0 stand.
- **`total_area_or_volume`.** Documented and computed as mm² (mesh) / mm³ (voxel) throughout;
  unaffected by SCI-03.
- **`pval_from_histogram` tail logic.** The `<=` / `>=` / `|·|` comparisons per tail were
  correct; only the `b/m` denominator (SCI-04) and the orientation of the *null* it is
  handed (SCI-01) were wrong.
- **The vectorised t-test algebra.** Pooled variance, the paired mean/difference
  reconstruction used by the sign-flip permutation, and the `t.sf` tail selection all match
  `scipy` on non-degenerate input.
- **The correlation kernel** (`engine.correlation`), including the weighted and Spearman
  (pre-ranked) paths.
- **`cluster_analysis`** MNI centre-of-mass mapping via `nibabel.affines.apply_affine`.
- **The `tit.calc` envelope API** — `get_TI_vectors`, `get_TI_avg`, `get_TI_dir` and the
  K ≥ 2 modulation-depth search. The `channels` pre-summing is exact (see SCI-07); only its
  interaction with the *exposure* metrics is open.
- **`hf_peak` for N ≤ 8 carriers.** Exact sign enumeration over all `2^(N-1)` combinations.
