# Skeptic 2 — Review of R1–R6 (Native Electron / FreeSurfer-free / Docker questions)

**Lens**: neuroimaging methods scientist. Does the proposed FreeSurfer replacement actually
give TI-Toolbox's ROI/atlas/TI_normal code what it needs — label sets, surfaces, fsaverage
mapping, accuracy — and what silently changes for users? Secondary: sanity-check the
cross-cutting packaging/Docker claims that gate the whole "compile it all into one Electron
app" plan.

All findings below are **my own independent checks** (fresh `curl`/PyPI queries, fresh
`docker exec`, a fresh venv+port for `tit.server`, files read myself) — not a re-statement of
what R1–R6 already showed. Time-boxed to ~45 min.

---

## Refuted / overstated claims

### 1. "FastSurfer's `aparc.DKTatlas+aseg.deep.mgz` is a near-exact match — a drop-in with a rename"
**Lane**: r3-parcellation-alternatives, §1 and Ranked Recommendation #2.

**Why refuted**: The claim conflates a *filename* match with a *methodological* match, and
asserts "drop-in" without any accuracy or spatial-consistency check. I fetched FastSurfer's
own docs (`deep-mi.org/FastSurfer/dev/overview/intro.html`) and README
(`github.com/Deep-MI/FastSurfer/blob/stable/README.md`) directly: neither publishes a
Dice/accuracy comparison against FreeSurfer's own `aparc.DKTatlas+aseg.mgz`, and neither
confirms the label IDs are identical to `FreeSurferColorLUT` numbering on the pages I could
reach (the README instead flags a DKT-atlas-merged-labels caveat for a *different* downstream
tool, TRACULA). More importantly, and unaddressed by R3: FastSurferCNN's `--seg_only` output
is a **purely volumetric, per-voxel CNN classification**, structurally independent of any
cortical surface. TI-Toolbox's own cortical ROI system is already charm-native today (R2 row
6, confirmed by me below) — a **surface**-based `.annot` on the TopoFit-reconstructed mesh.
Grafting FastSurfer's **volumetric** DKT map on top means the toolbox now has *two*
independently-trained boundary-drawing pipelines (TopoFit-surface vs. FastSurferCNN-volume)
that were never co-designed to agree voxel-for-voxel at the GM/WM boundary. No lane, including
mine, tested whether a voxel FastSurfer labels "precentral" spatially overlaps the same-named
ROI on the charm surface mesh for the same subject. That is exactly the kind of silent
discrepancy a neuroimaging user would only discover after already trusting the tool.

**Evidence**: WebFetch of both FastSurfer pages (quoted results above); `tit/atlas/mesh.py`
read in full (confirms today's cortical ROI path is surface/`.annot`-only, no voxel component
at all — so this would be a genuinely new second pathway, not a swap).

### 2. R6's open question "confirm whether torch can simply be dropped" — resolved, and the answer is no
**Lane**: r6-native-deps-audit, §4 (`torch` row).

**Why refuted**: R6 grepped `tit/` and `resources/`, found zero `import torch`, and flagged
this as something the maintainer should "confirm... or is a hard SimNIBS-core dependency," time-boxed out. I ran the check R6 didn't have time for:
```
$ docker exec tit-v3-spike simnibs_python -m pip show torch
Version: 2.6.0+cpu
Required-by: BrainNet, BrainSynth, pytorch-ignite
```
`BrainNet`/`BrainSynth` are exactly SimNIBS's TopoFit-based cortical-surface-reconstruction
packages — the very FreeSurfer-free surfacing pipeline `charm_main.py` uses by default
(`simnibs/segmentation/charm_main.py:354-361`, read myself: `if fs_dir is None: ...
brain_surface.cortical_surface_estimation(...)`). So torch (715 MB, R1/R4's own measurement)
is **not** negotiable weight — it is a hard, structural cost of the exact "no FreeSurfer"
cortical-surface capability the maintainer wants to keep. R1 and R4's size-budget tables
already (correctly) carry it as required; R6 read in isolation understates that.

**Evidence**: `docker exec tit-v3-spike simnibs_python -m pip show torch` (above, my own run,
not reused from R1); `simnibs/segmentation/charm_main.py:354-361` read directly.

### 3. R2's "replace `mri_convert --reslice_like` with nibabel/scipy — Small–Medium effort"
**Lane**: r2-freesurfer-audit, §7 effort table (row 4).

**Why refuted/overstated**: I confirmed the call is real, unconditional, and already fires on
charm's own FreeSurfer-free `labeling.nii.gz` atlas today (read `tit/atlas/voxel.py:108-149`
and `tit/atlas/constants.py` myself: `list_regions()` always shells to `mri_segstats
--ctab-default`, no numpy-only fallback exists). R2 is aware of this (its own §7 flags
"Yes, if FreeSurfer container is fully removed"), but "Small–Medium" undersells *why* it's
risky, not just effortful: `mri_convert --reslice_like`'s actual behavior depends on
FreeSurfer's own `tkreg`/surface-RAS vs. scanner-RAS conventions and its "conformed" 256³ LIA
resampling order — a classic, easy-to-get-subtly-wrong reimplementation target in neuroimaging
tooling (silent voxel-grid misalignment, not a crash, so it fails quietly). Neither R2 nor any
other lane proposes validating a from-scratch replacement against real `mri_convert` output on
the `ernie` dataset before cutting the FreeSurfer binary loose — that validation step belongs
in the plan, not an afterthought.

**Evidence**: `tit/atlas/voxel.py:108-149`, `tit/atlas/constants.py:1-40` read directly by me.

---

## Upheld claims (my own independent check agreed — several strengthened beyond what the report itself verified)

1. **charm's default path (no `--fs-dir`) is FreeSurfer-free by construction, using TopoFit** —
   r3. I read `simnibs/segmentation/charm_main.py:354-369` myself: `if fs_dir is None:
   ...cortical_surface_estimation(...)`. **Strengthened**: none of the six reports checked
   whether TopoFit's reconstructions are actually *accurate*, only that the code path exists.
   I searched independently and found TopoFit's own validation (Hoopes et al.) reports it more
   accurate than the prior SOTA deep-learning baseline and *comparable to or better than*
   FreeSurfer on longitudinal consistency — this is genuine supporting evidence no lane
   surfaced, not just an unverified code path.

2. **charm's `labeling.nii.gz` uses genuinely FreeSurfer-identical numeric label IDs, not just
   "compatible-looking" ones** — r2/r3. I read the full 57-line
   `simnibs/resources/labeling_FreeSurferColorLUT.txt` myself and confirmed exact matches to
   FreeSurfer's own aseg IDs (10=Left-Thalamus-Proper, 17=Left-Hippocampus, 18=Left-Amygdala,
   etc.). **Strengthened, with one caveat neither R2 nor R3 raised**: I found independent,
   peer-reviewed evidence (a large N=1,629 test–retest study, PMC9052126) that FreeSurfer's
   *own* SAMSEG is at least as reliable as ASEG for exactly these eight subcortical structures
   — real support for "this isn't a downgrade." Caveat: that study validates FreeSurfer's
   *standalone* SAMSEG tool; SimNIBS's charm uses its own whole-head-adapted SAMSEG variant
   (also segmenting scalp/skull/eyes for the FEM mesh) — nobody, including me, has confirmed
   this adapted fork preserves the same brain-structure accuracy as the tool the reliability
   study actually tested.

3. **fsaverage projection is charm-native with no resolution downgrade for users** — r2. I
   confirmed live in-container: `simnibs/resources/templates/fsaverage_surf/lh.central.gii`
   has exactly **163,842 vertices** — the literal standard FreeSurfer fsaverage (ico7) vertex
   count. Group-level fsaverage-space results built on charm's bundled template stay directly
   comparable to the wider literature and other FreeSurfer-based tools; this is not a
   lower-fidelity SimNIBS-only mesh, which R2 asserted but did not measure.

4. **`simnibs`, `cortech`, `brainsynth`, `FastSurfer` are absent from PyPI (404)** — r1/r3. I
   re-ran the exact PyPI-JSON queries myself (`curl -s -o /dev/null -w "%{http_code}"`), fresh,
   same 404s.

5. **`bpy` and `torch` both lack a macOS x86_64 wheel at the pinned/current versions** — r4. I
   independently re-fetched the PyPI release-file lists for `bpy==5.0.1` and `torch==2.6.0`:
   confirmed `bpy` ships only `macosx_11_0_arm64`/`manylinux_2_28_x86_64`/`win_amd64`/
   `win_arm64` (no Intel-Mac wheel); `torch==2.6.0` macOS wheels are `macosx_11_0_arm64` only
   across every CPython tag. Matches R4 exactly.

6. **v3 desktop has fully dropped `dockerode`; it survives only in the legacy `package/` tree**
   — r5/r6. I grepped fresh: zero `dockerode` hits in `desktop/package.json` or
   `desktop/package-lock.json`; exactly one hit, `"dockerode": "^4.0.9"`, in the legacy
   `package/package.json`.

7. **`tit.server`/`tit.jobs` already run natively today with a minimal dependency set** — r6.
   I reproduced this independently rather than trusting R6's own already-running process: used
   R6's leftover venv but a **fresh port (8811)** and a fresh `curl`: `python -m tit.server
   --project /tmp/skeptic2-proj --port 8811` → `GET /api/health` → `{"status":"ok",...}` on the
   first try.

8. **TI-Toolbox's own code never touches ADMlib (the one GPLv2-non-commercial-only component
   bundled inside SimNIBS)** — r1. I re-ran the grep myself:
   `grep -rln "ADM\b|TMSLIST|tms_optimization" tit/` → 0 files.

---

## Overall assessment

Realistic as an *engineering* program, and the three-way goal (native Electron+SimNIBS+
Tetravox, FreeSurfer-free parcellation, native Docker integration) decomposes cleanly along
exactly the seams the six reports found — the v3 codebase has already made several of the
needed architectural choices (dockerode dropped, `tit.server` container-agnostic, charm
already FreeSurfer-free by default for surfaces and whole-structure subcortical ROIs). From my
neuroimaging-methods seat, the single biggest risk the six reports collectively understate is
not "can we ship SimNIBS/Tetravox as an .app" (yes) or "can we drop dockerode" (already done)
— it's that **the FreeSurfer-elimination story is scientifically solved for two of three
required capabilities (cortical surface ROI, whole-structure subcortical volume ROI) but
*unvalidated*, not solved, for the third (voxel-space DKT parcellation and gyral-detail
subcortical work)**: the proposed fix (FastSurfer `--seg_only`) is picked on filename
convenience, with zero accuracy or cross-pipeline-consistency evidence gathered by any of the
six reports or by me. That is a data-science task (run FastSurfer + charm + real FreeSurfer
side-by-side on `sub-ernie`, diff the labels) that takes an afternoon, not a research program —
but it has to happen before "drop-in" appears in a scope document, because it is exactly the
kind of silent-accuracy-change a methods reviewer (or a paper's Methods section) would ask
about later.

---

## Missing — questions a go/no-go decision needs that nobody in R1–R6 (or my own pass) answered

1. **No accuracy or spatial-consistency check between FastSurfer's volumetric DKT labels and
   TI-Toolbox's already-charm-native surface `.annot` atlases (or against real FreeSurfer
   `aparc.DKTatlas+aseg.mgz`) on an actual dataset.** This is the load-bearing gap behind
   Refuted #1 above and should be the first thing done before committing to FastSurfer as the
   `recon-all` replacement.
2. **No validation that SimNIBS charm's whole-head-adapted SAMSEG fork matches the accuracy of
   FreeSurfer's own standalone SAMSEG** — the reliability literature I found (PMC9052126)
   tested the latter, not the former.
3. **No test of a from-scratch `mri_convert --reslice_like` replacement against real FreeSurfer
   output on `sub-ernie`**, to catch tkreg/scanner-RAS or conform-order-of-operations bugs
   before the FreeSurfer binary is actually removed (Refuted #3).
4. **No stated migration/backward-compatibility path for labs whose existing BIDS derivatives
   already contain real `recon-all` output** (thalamic-nuclei, hippocampal-subfield files) if
   the shipped app drops FreeSurfer entirely — do old projects keep working, degrade
   gracefully, or break?
5. **No estimate of how many current TI-Toolbox users actually use thalamic-nuclei /
   hippocampal-subfield targeting** (the one capability every lane agrees has no FreeSurfer-free
   equivalent) — is losing it by default acceptable, or does HippUnfold (raised by R3 as
   REPORTED-only, unverified) need to become a real, tested dependency before ship?
6. **R6's flagged-but-unchecked `mumps` Python-binding platform coverage** (same class of risk
   as `petsc4py`'s win-64/macOS-x86_64 gaps, R4 §4.2) is still open — needed before trusting the
   Windows/macOS-arm64 legs of the native build.
7. **No timed CPU-only run of FastSurfer `--seg_only`** exists anywhere in this research pass
   (R3 explicitly flags this as unmeasured) — "fast native app" is part of the pitch and nobody
   has a number.
8. **`tit/stats/surface.py`'s `nilearn.datasets.fetch_surf_fsaverage()` call** (I found this
   independently, reading `tit/stats/surface.py:130` — not mentioned by any of the six reports)
   downloads FreeSurfer's own fsaverage5/6/7 from nilearn's servers at runtime, separately from
   SimNIBS's bundled `fsaverage_surf`/`fsaverage10k_surf`/`fsaverage40k_surf` templates used
   elsewhere. Nobody checked whether this needs vendoring/caching for a genuinely
   self-contained, possibly-offline desktop executable, or whether it silently requires
   internet access the first time a user runs surface group-stats.
9. **No dry run of the macOS multi-GB Python-tree signing/notarization pipeline** R4 flags as
   "genuinely new, unproven work for this codebase" — a go/no-go on the macOS leg specifically
   should not proceed on an estimate alone.
10. **No data on what fraction of the current user base is on Intel Macs** — R4's (evidence-
    backed) recommendation to drop macOS x86_64 from the native-bundle path is a product
    decision nobody has the usage data to make yet.

---

## Commands/checks run this session (for reproducibility)

```
sed -n '330,380p' simnibs/segmentation/charm_main.py                 # TopoFit default path
cat simnibs/resources/labeling_FreeSurferColorLUT.txt                # 57-line LUT, read in full
sed -n '1,150p' tit/atlas/voxel.py; sed -n '1,60p' tit/atlas/constants.py
sed -n '1,60p' tit/atlas/mesh.py
grep -rn "labeling.nii.gz|labeling_LUT" tit/ --include='*.py'
docker exec tit-v3-spike simnibs_python -c "... fsaverage_surf lh.central.gii vertex count"  # 163842
docker exec tit-v3-spike simnibs_python -m pip show torch             # Required-by: BrainNet, BrainSynth
curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/{simnibs,cortech,brainsynth}/json  # 404 x3
curl -s https://pypi.org/pypi/FastSurfer/json                          # {"message":"Not Found"}
curl -s https://pypi.org/pypi/bpy/json    | python3 -c "... 5.0.1 wheel filenames"
curl -s https://pypi.org/pypi/torch/json  | python3 -c "... 2.6.0 macOS wheel filenames"
grep -rn "dockerode" desktop/package.json desktop/package-lock.json    # 0 hits
grep -n '"dockerode"' package/package.json                             # 1 hit, legacy tree
grep -rn "ADM\b|TMSLIST|tms_optimization" tit/ --include="*.py"        # 0 hits
# fresh venv (reused R6's interpreter, fresh port/process):
python -m tit.server --project /tmp/skeptic2-proj --host 127.0.0.1 --port 8811
curl -s http://127.0.0.1:8811/api/health                               # {"status":"ok",...}
WebFetch: deep-mi.org/FastSurfer/dev/overview/intro.html, github.com/Deep-MI/FastSurfer/blob/stable/README.md
WebSearch: TopoFit accuracy vs FreeSurfer; SAMSEG vs ASEG subcortical reliability
```
