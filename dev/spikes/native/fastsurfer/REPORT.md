# N0.2 -- FastSurfer `--seg_only` as the recon-all replacement

Spike lane N0.2 of `dev/notes/v3-native-desktop-plan.md`. Answers skeptic-2's refutation
("FastSurfer's DKT map is picked on filename convenience, zero accuracy evidence") with
measured numbers on real data (sub-ernie), and answers r3's open runtime/torch questions.

Machine: Apple M2 Max, 12 physical cores (8 performance + 4 efficiency), 32 GB RAM, macOS 15.
Everything below ran natively (arm64), CPU only, no Docker, no GPU/MPS.

---

## 1. What was built, and how (reproducible)

`run.sh` (owned copy at `dev/spikes/native/fastsurfer/run.sh`) does this from nothing:

1. `git clone https://github.com/Deep-MI/FastSurfer.git`, `git checkout v2.5.4`
   (pinned tag; commit `cdfccea89e6c2bdbd6a2abb3f033f2e618a54538`).
2. `uv venv --python 3.11 .venv` -- **native arm64** CPython 3.11.14 (uv's own managed
   interpreter, not Homebrew's; no `python3.11` was preinstalled on this Mac). `platform.machine()`
   confirms `arm64` inside the venv (not Rosetta/x86_64).
3. `uv pip install -e .` (NOT `pip install -r requirements.txt` -- that file is
   auto-generated from a Linux CUDA container running **Python 3.12** and pins
   `tifffile==2026.5.2` which requires `Python>=3.12`, so it is literally uninstallable
   on Python 3.11: `uv pip install -r requirements.txt` fails immediately with
   *"tifffile==2026.5.2 depends on Python>=3.12 ... your requirements are unsatisfiable"*.
   `pyproject.toml`'s own looser, cross-platform dependency set (`torch==2.7.*`, no
   Python-version-specific pins) installs cleanly and resolves **torch 2.7.1** for
   macOS arm64 automatically -- no separate index or `--extra-index-url` needed; PyPI's
   only macOS wheel for torch is the CPU/MPS build.
4. `FastSurferCNN/download_checkpoints.py --vinn` -- downloads the 3 DKT-segmentation
   checkpoints. **Note**: the primary URL (`b2share.fz-juelich.de`) failed with an SSL
   certificate error from this network (`SSLCertVerificationError`); the script's
   automatic fallback to the secondary `zenodo.org/records/10390573/files` URL
   succeeded. Total download **67.2 MB** (3 x ~22.4 MB), **27 s**. Matches r3's estimate exactly.
5. `run_fastsurfer.sh --t1 <T1w> --sid sub-ernie --sd out --seg_only --no_cereb
   --no_hypothal --device cpu --threads 8 --py <venv>/bin/python3 --allow_root`, wrapped
   in `/usr/bin/time -l` for wall-clock + peak RSS.

Deviation from the brief worth flagging: `--seg_only` alone (even with `--no_cereb
--no_hypothal`) does **not** skip the Corpus Callosum (`FastSurfer-CC`) module -- that
needs its own `--no_cc` flag, which I did not pass (found this only after the run). CC
processing downloaded two more checkpoints (`FastSurferCC_localization_v1.0.0.pkl`
73.8 MB, `FastSurferCC_segmentation_v1.0.0.pkl` 7.5 MB -- 81.3 MB extra, not in r3's
budget) and then **crashed** (see SS4). It ran *after* the DKT segmentation was already
saved, so it did not affect the comparison, but a real integration must pass `--no_cc`
too if CC targeting isn't wanted, or budget the extra 81 MB/time if it is.

---

## 2. Timing and memory (measured, `/usr/bin/time -l`, 8 threads, CPU-only)

| Stage | Time |
|---|---|
| Coronal plane inference (256 batches) | 100.24 s |
| Sagittal plane inference (256 batches) | 96.14 s |
| Axial plane inference (256 batches) | 95.23 s |
| **DKT segmentation total** (conform + 3-plane inference + view agg + save) | **~300 s (~5 min)**, inferred from the three stage times above plus the surrounding conform/checkpoint-load overhead visible in the log |
| Full invocation incl. N4 bias correction, stats generation, and the failed CC module | **391.64 s real** (696.06 s user, 273.47 s sys -- confirms multi-threading across the 8 requested threads) |
| **Peak RSS** (`maximum resident set size`) | **5,194,137,600 bytes = 4.84 GiB** |

For comparison, steady-state RSS observed via `ps -o rss` at ~10 s intervals throughout
inference stayed in the 4.2-5.0 GB range, consistent with the `/usr/bin/time` peak.

**This is the first CPU-only wall-clock number anywhere in the N0 research** -- r3
explicitly flagged this as unmeasured (FastSurfer's own docs only give a GPU figure,
"under 1 minute", from the 2019 paper abstract). **Real CPU number: ~5 minutes for the
segmentation itself, on 8 of this Mac's 12 cores.** A production estimate for users
should budget 5-8 minutes per subject on a typical laptop CPU, not "under a minute" --
correcting the only speed claim anyone had put in front of the maintainer so far.

**Environment sizes**:
- venv (torch 2.7.1 + all `pyproject.toml` deps): **1.0 GB**
- checkpoints (asegdkt only, what the toolbox actually needs): **67.2 MB**
- checkpoints (asegdkt + accidental CC): 142 MB total
- FastSurfer git clone (`.git` + working tree): 94 MB (would not ship; source is vendored, not the `.git` history)
- Output directory for one subject (`--seg_only`, minus the failed CC artifacts): 26 MB

The venv's 1.0 GB is **not all incremental cost** for the target architecture: SimNIBS's
own `BrainNet`/`BrainSynth` packages already require `torch` (`torch>=2.1`, see SS5) as a
hard dependency of charm's default cortical-surface path, so torch itself is already
budgeted in `v3-native-desktop-plan.md`'s size table. FastSurfer's genuinely *new*
packages on top of a SimNIBS-carrying runtime are: `torchvision`, `torchio`,
`torch-interpol`, `monai`, `meshpy`, `lapy`, `pyrr`, `neuroreg`, `tensorboard` (+
`tensorboard-data-server`, `grpcio`, `protobuf`), `simpleitk`, `scikit-image`, `einops`,
`jaxtyping`, `plotly`, `narwhals` -- not independently sized in this pass, but visibly a
few hundred MB, not another 1 GB, once torch/numpy/scipy/nibabel/pandas/matplotlib are
already shared with SimNIBS.

---

## 3. torch 2.7.1 vs 2.6.0 compatibility

- **torch 2.7.1** (FastSurfer's own pin, `torch==2.7.*` in `pyproject.toml`): installed
  and used for the full, successful `--seg_only` run above. Confirmed native arm64
  (`platform.machine()` -> `arm64`), MPS backend available but unused (`--device cpu`
  forced throughout, per the brief).
- **torch 2.6.0** (the version SimNIBS's container currently carries, per
  `docker exec tit-v3-spike simnibs_python -m pip show torch` -> `2.6.0+cpu`, reused from
  r2/skeptic-2's own finding): installed in a **separate** venv (`torch26check/`, same
  machine) and checked for import compatibility only (not a full run -- out of the
  90-minute time box once the main run already used most of it): basic tensor ops,
  `nn.Conv2d`, and `from FastSurferCNN.models.networks import FastSurferVINN` (the
  actual model class the seg_only pipeline instantiates) **all import and run cleanly
  under torch 2.6.0** with `PYTHONPATH` pointed at the FastSurfer checkout.
- **No hard pin conflict exists for a shared runtime.** I read
  `brainnet-0.2.dist-info/METADATA` directly in the live SimNIBS container:
  `Requires-Dist: torch>=2.1` -- a **floor**, not an exact pin. FastSurfer's `torch==2.7.*`
  and SimNIBS's `torch>=2.1` are simultaneously satisfiable by a single **torch 2.7.1**
  in one shared runtime venv. The container currently shipping 2.6.0 is an artifact of
  when it was built, not a hard requirement.
- **What this does NOT prove**: that `charm`/`atlas2subject`/TopoFit surface
  reconstruction actually still work correctly if the shared runtime's torch is bumped
  from 2.6.0 to 2.7.1 -- that needs an actual charm run against torch 2.7.1, which is
  N0.1's territory (native SimNIBS runtime), not this lane's. **Follow-up for N1**: when
  N0.1's native runtime and this lane's FastSurfer integration are combined into one
  venv, re-run a real charm/`subject_atlas` pass to confirm no regression from the torch
  version bump.

---

## 4. What failed, and why

**FastSurfer-CC (Corpus Callosum) module crashed** after the DKT segmentation had
already completed and been saved:
```
OSError: Failed loading the image '.../mri/callosum.CC.orig.mgz' with error:
No such file or no access: '.../mri/callosum.CC.orig.mgz'
File "CorpusCallosum/paint_cc_into_pred.py", line 461, in <module>
```
`fastsurfer_cc.py` (localization + segmentation, using the two extra checkpoints) ran,
but its output apparently wasn't written to (or found at) the path
`paint_cc_into_pred.py` expected next. **Root cause not diagnosed in this pass** (out of
time box; this module is out of scope for the toolbox's actual need -- DKT parcellation,
not corpus-callosum shape analysis). **Practical takeaway for N1**: pass `--no_cc`
explicitly alongside `--no_cereb --no_hypothal` when wiring `run_fastsurfer_seg` as a
`tit.pre` stage, both to avoid this crash and to avoid the unwanted 81 MB checkpoint
download -- the toolbox has no use for corpus-callosum sub-segmentation. This crash did
**not** corrupt or truncate the primary deliverable (`aparc.DKTatlas+aseg.deep.mgz` was
written and closed before the CC module started); all Dice/volume numbers in SS6-7 are
computed from that file post-crash and are unaffected.

**Checkpoint download's primary URL (`b2share.fz-juelich.de`) failed** with a TLS
certificate error on this network; the script's built-in fallback to `zenodo.org`
succeeded silently. Worth noting for an offline/restricted-network installer: don't
assume the primary host is reachable, and vendor/mirror the checkpoints (as
`v3-native-desktop-plan.md` already plans to do for SimNIBS's own wheels) rather than
relying on either external host at first-run time.

---

## 5. Label-ID compatibility (verified, not assumed)

Before trusting any Dice number, I confirmed the three sources actually use the *same*
numeric label IDs for the same anatomy -- this was the one thing r3's "drop-in" claim
never checked, per skeptic-2:
- `FastSurferCNN/config/FreeSurferColorLUT.txt` (bundled in the FastSurfer repo) and
  `/Users/idohaber/01_production/simnibs/simnibs/resources/labeling_FreeSurferColorLUT.txt`
  (charm's LUT) both assign `10=Left-Thalamus`, `17=Left-Hippocampus`,
  `1024=ctx-lh-precentral`, `1035=ctx-lh-insula`, etc. -- **identical IDs**, confirmed by
  `diff` against both files for every subcortical + cortical label used below.
- The real recon-all `aparc.DKTatlas+aseg_labels.txt` on sub-ernie (`mri_segstats`
  output) independently confirms the same numbering for the actual data used in this
  comparison.

So Dice/volume/centroid numbers below are label-ID-matched, not name-matched or
manually remapped.

---

## 6. FastSurfer vs. real FreeSurfer recon-all (same subject, same modality)

**Grid check, done first, not assumed**: FastSurfer's own internal conform step and real
FreeSurfer's conform produced **byte-identical affines and shapes** -- both
`(256, 256, 256)`, affine `[[-1,0,0,132.263],[0,0,1,-101.812],[0,-1,0,112.358]]` -- so
**no resampling was needed** for this comparison (they land on the same
FreeSurfer-conform grid, LIA, 1 mm iso, by construction). This is itself a finding: two
independently-implemented conform routines (FreeSurfer's classic one, FastSurfer's own)
agree on center-of-mass and orientation for this real T1w, at least for this subject.

**Mean Dice, FastSurfer `aparc.DKTatlas+aseg.deep.mgz` vs. real
`aparc.DKTatlas+aseg.mgz`**:
- **Subcortical (14 structures -- bilateral thalamus/caudate/putamen/pallidum/
  hippocampus/amygdala/accumbens): mean Dice = 0.922**, range 0.826 (R-Accumbens) - 0.956 (L-Thalamus).
- **Cortical (20 DKT regions -- bilateral precentral/postcentral/superiorfrontal/
  insula/inferiorparietal/superiortemporal/precuneus/lateraloccipital/superiorparietal/
  parsopercularis): mean Dice = 0.914**, range 0.860 (L-parsopercularis) - 0.942 (R-insula).

Volumes agree closely: most structures within +/-5% of real FreeSurfer's volume; the
worst outlier is Right-Accumbens at **+17.5%** (680 mm3 -> 799 mm3, a small structure
where a handful of voxels swings the percentage). Centroid distances (world-space,
computed independently in each source's own affine, no resampling involved) are **almost
all under 1.1 mm**; the one cortical exception is `ctx-lh-superiortemporal` at 3.07 mm.

Full per-structure table: `compare_output.md` SS2a/2b (copied into the repo alongside
this report).

**What this means for TI-Toolbox specifically**: Dice ~0.91-0.92 and centroid shifts
mostly <1.5 mm is a **methodologically sound agreement** between two independently
trained segmentation pipelines that were never co-designed (exactly skeptic-2's
concern) -- but it is *not* voxel-identical, and TI ROI spheres are 5-15 mm radius (per
the brief). A 3 mm centroid shift on a 5 mm-radius ROI moves its center by more than half
the radius; that is a real, user-visible difference for the smallest ROIs the toolbox
supports, even though it's well within the range any two segmentation methods would
disagree by. This should be **disclosed in the UI/docs**, not treated as invisible.

---

## 7. Subcortical comparison against charm's `labeling.nii.gz` (different grid)

`labeling.nii.gz` is `(256, 256, 208)` with a different affine than the FreeSurfer-conform
grid -- resampling *is* required here, unlike SS6.

**Validation of the from-scratch resampler** (the exact risk skeptic-2 flagged for
`mri_convert --reslice_like`, refuting r2's "Small-Medium effort" framing as
underselling the *risk*, not just the work): the pipeline already has a real,
production-made `mri_convert --reslice_like`-resampled copy of real FreeSurfer's
`aparc.DKTatlas+aseg.mgz` on this exact grid, sitting in the dataset
(`aparc_DKTatlas+aseg_resampled_256x256x208_45dfa12d.nii.gz` -- clearly the analyzer's own
cache artifact). I resampled the same source file onto the same target grid using only
`nibabel`+`numpy` (affine-matrix nearest-neighbour, no scipy/nilearn) and compared voxel-for-voxel:

> **100.00% of voxels agree** between our from-scratch nearest-neighbour resampler and
> the toolbox's existing `mri_convert --reslice_like` output, for the exact source/target
> grid pair the toolbox uses today.

This is a real, if narrow (one image, one source->target grid pair, label data not
intensity data), validation that a pure-Python nearest-neighbour affine resample can
reproduce `mri_convert --reslice_like`'s actual behavior for this use case -- directly
answering skeptic-2's open question #3 ("no test of a from-scratch reslice_like
replacement against real output"). It does not test the tkreg/scanner-RAS edge cases
skeptic-2 worried about in general (this pair of images share the same handedness/RAS
convention already), so it should not be read as "the replacement is proven for every
grid pair," only "for the one pair actually exercised by this pipeline on this subject."

**Subcortical Dice, both tools vs. charm** (14 structures, all resampled onto charm's
grid): FastSurfer-vs-charm and real-FreeSurfer-vs-charm Dice are **close to each other**
for every structure (mean difference ~0.02, max difference 0.065 at Right-Accumbens) --
i.e. **swapping FastSurfer in for real FreeSurfer does not measurably change how well
subcortical ROI labels agree with the SimNIBS simulation's own segmentation.** Both
tools disagree with charm's whole-head SAMSEG variant by a similar amount (mean Dice
~0.85 across structures, notably lower for pallidum: 0.73-0.79 for both). This is
useful, previously-missing evidence for skeptic-2's open question #2 (does charm's
SAMSEG fork match standalone accuracy) -- it doesn't answer that question directly (no
ground truth here, just three plausible tools examined pairwise), but it does show
FastSurfer isn't introducing a *new* accuracy gap beyond what real recon-all already had
relative to charm.

Centroid distances vs. charm: mostly 0.4-2 mm for both tools, with **pallidum the
consistent outlier** (Left ~3.0-3.2 mm, Right ~3.7-4.4 mm, both tools) -- the smallest,
most centrally-located subcortical structure the toolbox targets, and exactly where a
5 mm-radius ROI sphere would be most sensitive to which segmentation source placed it.

Full table: `compare_output.md` SS3.

---

## 8. Answering the brief's core question

**"Which differences matter for TI focality (ROI sizes 5-15 mm)?"**

- **Cortical/subcortical Dice ~0.91-0.92 (FastSurfer vs. real FreeSurfer)** is a good
  result for two independently-trained networks and is very unlikely to change which
  *gyrus* or *structure* a targeting workflow lands on.
- **Centroid shifts are the number that matters more than Dice for small ROIs**, and
  they are small (<1.5 mm) for every structure **except pallidum** (~3-4 mm, consistent
  across both real-FreeSurfer-vs-charm and FastSurfer-vs-charm) and one cortical outlier
  (`superiortemporal`, 3.07 mm vs. real FreeSurfer). For a 5 mm-radius ROI sphere, a 3-4
  mm centroid shift is a genuinely material difference in which tissue gets stimulated;
  for the toolbox's more typical 10-15 mm ROIs it is comfortably inside the sphere.
- **Practical recommendation**: FastSurfer `--seg_only` is a defensible default for
  voxel-space DKT cortical parcellation (matches r3's ranked recommendation #2, now with
  evidence). For **pallidum targeting specifically**, and for any workflow using ROI
  spheres at the small end of the toolbox's 5-15 mm range, the UI/docs should flag that
  segmentation-source choice (real FreeSurfer vs. FastSurfer vs. charm's own
  `labeling.nii.gz`) can shift the effective target by several mm -- this was not
  previously quantified anywhere in the N0 research and is new, load-bearing evidence
  for that specific caveat.

---

## 9. Integration sketch: `tit.pre` FastSurfer stage (sketch only, not implemented)

Read `tit/pre/recon_all.py`, `tit/pre/charm.py`, `tit/atlas/constants.py`,
`tit/atlas/voxel.py`, `tit/pre/preflight.py`, `tit/jobs/plans.py` to model this on the
existing shape (per r3's own sketch, refined with what this lane measured):

- **New module** `tit/pre/fastsurfer.py`:
  `run_fastsurfer_seg(project_dir, subject_id, *, logger, runner=None) -> None`, same
  signature shape as `run_charm`/`run_recon_all` (`tit/pre/charm.py:48`,
  `tit/pre/recon_all.py:102`). Resolve T1 via the same `_find_anat_files(subject_id)`
  helper both existing modules already use (`tit/pre/utils.py`).
- **Command**, based on what actually worked in this spike:
  `run_fastsurfer.sh --sd <derivatives/fastsurfer/sub-<id>> --sid sub-<id> --t1 <T1.nii.gz>
  --seg_only --no_cereb --no_hypothal --no_cc --device cpu --threads <physical_cores>
  --py <bundled runtime python>` -- **`--no_cc` is a correction to r3's sketch**: without
  it, the run downloads 81 MB of unused checkpoints and crashed in this environment (SS4).
- **Output landing spot**: write
  `derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep.mgz` (BIDS-derivatives-shaped,
  distinct from `derivatives/freesurfer/` so old and new projects never collide), plus copy
  or symlink into `m2m_<id>/segmentation/aparc.DKTatlas+aseg.mgz` -- the exact filename
  `tit/atlas/constants.py:12`'s `VOXEL_ATLASES` dict already expects. Confirmed in this
  spike: FastSurfer's own bundled `FreeSurferColorLUT.txt` uses identical numeric IDs to
  both charm's LUT and real FreeSurfer's (SS5), so no ID remapping is needed -- the existing
  `VoxelAtlasManager`/`list_regions()`/`roi_spec.py._load_freesurfer_lut()` code paths
  work unmodified once the file is discoverable.
- **`VoxelAtlasManager` wiring** (`tit/atlas/voxel.py:34-56`, `list_atlases()`): either
  (a) point a *new* constructor argument (e.g. `fastsurfer_mri_dir`) at
  `derivatives/fastsurfer/sub-<id>/mri/`, parallel to the existing `freesurfer_mri_dir`,
  or (b) copy the file straight into `seg_dir` (`m2m_<id>/segmentation/`) at job-completion
  time so it's discovered by the existing `seg_dir` search path with zero code change
  beyond writing the file there -- (b) is less code and matches r3's original framing
  ("no FreeSurfer directory needs to exist at all").
- **`mri_segstats` replacement is now on the critical path** the moment `recon-all`
  itself is gone (r2 row 4): `VoxelAtlasManager.list_regions()`
  (`tit/atlas/voxel.py:107-146`) still shells out to `mri_segstats --ctab-default` for
  **every** voxel atlas, including FastSurfer's and charm's own -- this is a real
  FreeSurfer-binary dependency that must be replaced (small effort per r2: `np.unique` +
  the LUT parser `tit/opt/roi_spec.py:494`'s `_load_freesurfer_lut()` already has) before
  a FreeSurfer-free build can ship, independent of whether FastSurfer is adopted.
- **Preflight/config wiring**: add `STEP_FASTSURFER_SEG` alongside `STEP_RECON_ALL`
  (`tit/pre/preflight.py:20-28`), reusing the same `_has_bids_t1` gate
  (`tit/pre/preflight.py:66-72`); add `run_fastsurfer_seg: bool` to `PreprocessConfig`
  (`tit/pre/config.py`, alongside `run_recon` at line 239).
- **Job plan**: a `g2c` `PlannedJob` in `plan_preprocessing`
  (`tit/jobs/plans.py:115-142`, modeled on `g2a`/`g2b`), `after_labels=[g1.label] if g1
  else []` -- no dependency on charm (`g2a`) since FastSurfer only needs the raw T1, so it
  can run in parallel with charm exactly like today's `recon-all` (`g2b`) already does.
  During a transition period, `g2b` (real recon-all) and `g2c` (FastSurfer) can coexist
  as independent opt-in flags, letting labs with existing recon-all derivatives keep
  using them (per skeptic-2's migration-path concern #4) while new projects default to
  `g2c`.
- **Not addressed by this stage** (per r3 SS0, confirmed unchanged by this spike):
  thalamic-nuclei and hippocampal-subfield sub-segmentation -- FastSurfer's `--seg_only`
  has no equivalent of `segmentThalamicNuclei.sh`/`segmentHA_T1.sh`; whole-structure
  thalamus/hippocampus/amygdala remain available from charm's own `labeling.nii.gz` with
  no FastSurfer involvement at all.

---

## 10. What this proves and what it does not

**Proven, with numbers:**
- FastSurfer `--seg_only` (`aparc.DKTatlas+aseg.deep.mgz`) runs natively on macOS arm64,
  CPU only, from a from-scratch `uv`-built Python 3.11 venv, no FreeSurfer, no Docker.
- Real CPU timing: ~5 minutes for the DKT segmentation itself (391.64 s including
  N4/stats/the failed CC module), peak RSS 4.84 GiB, on 8 of 12 cores.
- torch 2.7.1 (FastSurfer's pin) and the SimNIBS container's current torch 2.6.0 are
  **not in conflict** for a shared runtime -- SimNIBS's own constraint is `torch>=2.1`.
- Label IDs are genuinely identical (not just similarly-named) across FastSurfer, real
  FreeSurfer, and charm's `labeling.nii.gz` for every structure tested.
- Mean Dice vs. real recon-all: 0.922 (14 subcortical structures), 0.914 (20 cortical
  DKT regions), on one real subject (sub-ernie).
- A from-scratch `nibabel`+`numpy` nearest-neighbour resampler reproduces the pipeline's
  existing `mri_convert --reslice_like` output at 100% voxel agreement, for the one
  source/target grid pair actually exercised by this pipeline.
- Checkpoint size: 67.2 MB for the DKT module (matches r3's estimate exactly).

**Not proven / explicitly out of scope for this spike:**
- **n=1.** Every accuracy number here is for sub-ernie only -- no claim about
  cross-subject robustness, pathology, scanner variability, or non-T1w contrasts.
- Windows and Linux native runs were not attempted (this Mac only, per the brief).
- torch 2.6.0 compatibility was checked at **import level only**, not a full run.
- The FastSurfer-CC crash's root cause is undiagnosed (out of scope: the toolbox doesn't
  need corpus-callosum sub-segmentation; `--no_cc` sidesteps it).
- `mri_convert --reslice_like` validation covers one grid pair with matched RAS
  handedness; skeptic-2's broader tkreg/scanner-RAS concern for *other* grid pairs
  (e.g. a genuinely oblique or different-handedness source) is not tested here.
- Thalamic-nuclei / hippocampal-subfield gap is unchanged and unaddressed by this lane
  (confirmed still absent from FastSurfer's `--seg_only` output set).
- No comparison against SynthSeg or other alternatives was re-run (r3 already
  deprioritized SynthSeg for the TensorFlow-dependency reason; not revisited here).

---

## 11. Follow-ups for Stage N1

1. Re-run this same comparison on 2-3 more `datasets/000`-style subjects if more BIDS
   subjects with real recon-all output become available, to move past n=1.
2. Diagnose the FastSurfer-CC crash (SS4) if corpus-callosum targeting is ever wanted; not
   currently a toolbox requirement.
3. When N0.1's native SimNIBS runtime and this lane's FastSurfer environment are merged
   into one venv, re-run a real `charm`/`atlas2subject` pass against torch 2.7.1 (not
   2.6.0) to confirm no regression -- flagged in SS3, not yet tested by any N0 lane.
4. Implement the `mri_segstats`/`mri_convert --reslice_like` replacements in
   `tit/atlas/voxel.py`/`tit/analyzer/analyzer.py` (r2 rows 4-5) -- these are needed the
   moment FreeSurfer binaries are removed, independent of the FastSurfer decision, and
   this lane's 100%-agreement resampler result is a starting point, not a finished
   validated replacement (SS10).
5. Decide, with the pallidum/superiortemporal centroid-shift numbers in SS6-8 in hand,
   whether the UI should surface which segmentation source (real FreeSurfer, FastSurfer,
   or charm `labeling.nii.gz`) backs a given ROI pick, given they measurably disagree by
   several mm for small ROIs.
6. Time-budget the full pipeline (`--seg_only --no_cereb --no_hypothal --no_cc`, the
   corrected invocation) for the wall-clock number a first-run UX estimate should quote --
   this spike's ~5 minute segmentation-only number, not "under a minute".

---

## Files

- `dev/spikes/native/fastsurfer/run.sh` -- reproducible build+run script (rebuilds from nothing).
- `dev/spikes/native/fastsurfer/compare.py` -- nibabel+numpy-only comparison script.
- `dev/spikes/native/fastsurfer/compare_output.md` -- full per-structure Dice/volume/centroid tables (this run's actual output).
- `dev/spikes/native/fastsurfer/REPORT.md` -- this file.

Scratch (not in repo, per the brief):
`/private/tmp/claude-501/-Users-idohaber-01-production-TI-toolbox/2f1d440f-51f9-4340-bb8a-c347107a12b1/scratchpad/native/fastsurfer/`
-- `FastSurfer/` (clone + venv + checkpoints), `out/` (segmentation output),
`torch26check/` (torch 2.6.0 compat venv), `compare_output.md`, `run_fastsurfer.log`,
`run_fastsurfer.time.log`.
