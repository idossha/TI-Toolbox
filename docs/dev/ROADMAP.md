# Roadmap

Priorities and completion criteria live here; [RELEASING.md](RELEASING.md) owns the release
procedure and [TESTING.md](TESTING.md) owns validation strategy and gaps. Remove completed
work; retain consequential rationale in [DECISIONS.md](DECISIONS.md).

v3.1.3 (2026-11-03) is the current release; its application image is `idossha/ti-toolbox:v3.1.3`
([release notes](../releases/v3.1.3.md)). The current checkout is available for manual testing
through the standard development loader. The table lists acceptance work still open for the next
release.

| Open acceptance work | Completion criterion |
|---|---|
| Manual workflow testing | Colleagues exercise representative copied projects and report output/result behavior |
| Rebuild the distribution candidate | Bake current source and renderer; verify the separately installed native TetraVox package and record immutable identities |
| Clean image and loader acceptance | Test without checkout mounts; verify Python/Bash launchers, packaged cross-project Attach/Recreate, project switching and Electron close-stop on each supported host |
| Hosted review | Run CI/security review on the actual candidate head; older results do not cover later fixes |
| Platform and publication checks | Verify intended platforms, macOS signing/notarization and registry access before public promotion |
| Native viewer lifecycle | Complete automatic setup and TI-owned updates: TetraVox 0.6.2 (2026-09-23) carries the managed update handshake; run the packaged macOS arm64/x64, Windows x64 and Linux x64 (Wayland and X11) install-update-foreground matrix in ARCHITECTURE §7.1 — Settings Update and the in-TetraVox popup on each leg (only macOS arm64 has been checked, from a branch build) |

Distribution candidates are rebuilt from the repository Dockerfile. Source-mounted testing does
not establish what a published image contains. Current verification evidence and its limits
belong in [TESTING.md](TESTING.md).

### Product follow-ups

These are scoped improvements, not blanket blockers for a release. Recheck the relevant
source before scheduling them; remove a row when it ships.

| Area | Follow-up |
|---|---|
| QSIPrep 26.1 | First end-to-end run of 26.1.1 and QSIRecon 26.0.1 on an x86 host, then `use_gpu` on an NVIDIA host, reading the DTI step and its report on the output; neither has run |
| QSIPrep gradient and readout-time guardrails ([DECISIONS.md](DECISIONS.md), "QSIPrep gradient and readout-time pitfalls") | (a) A host test that reads `tit/` source and fails on any read of a QSIPrep `.bvec` or an `-fslgrad`, beside the existing pin that `qsiprep_inputs` returns the `.b`. (b) Any future hand-off of a QSIPrep `.bvec` to FSL or MRtrix `-fslgrad` negates x first when det(affine) > 0, with a synthetic LPS+ and LAS test. (c) A blocking mirrored-table check: the track stage's 8-flip check shares the `.b` with its reference and cannot see a mirrored table; promote the DTI advisory's continuity flip test, or a `dwigradcheck`-style length test, to fail the track and DTI runs when a flipped table wins by a set margin. (d) `ensure_total_readout_time`: with any non-topup fieldmap (GRE) prefer `EffectiveEchoSpacing × (ReconMatrixPE − 1)` over `EstimatedTotalReadoutTime` and record which was used; plan GRE fieldmaps in `plan_distortion_correction` so the command and QSIPrep agree on the correction; correct the docstring (the placeholder case runs SyN); write the derived value somewhere other than the user's raw sidecar, or say so in the app. (e) On each QSIPrep version bump, re-read the `.bvec` convention (#592, #619), the `TotalReadoutTime` crash and the SyN readout path, and re-run the sub-CHN `.b` = diag(-1, -1, 1)·bvec check. Also open: whether sub-CHN's input data carry a z flip |
| Optimizer | Ex symmetric-bucket controls; consistent naming for Flex `output_folder` and Ex `run_name`; mixed-kind group submission; prove interrupted candidate recording remains parseable and complete; validate full optimization → candidate → preview → simulation → analysis provenance, including cancellation, retry and all-invalid histories |
| Analyzer | Expose Python multi-sphere ROI union in the config and UI |
| Jobs | Running-job ETA and bulk retry; current elapsed time and single-job Rerun remain available |
| Notebooks | Detect outdated seeded examples without overwriting user edits; variable explorer and interactive plots |
| Viewer | TetraVox 0.6.0 (2026-09-20) released PR #44's [generic scene API](../../dev/upstream/tetravox-live-scene/README.md); validate edited native snapshot/reopen, existing-file refusal, unchanged originals and macOS minimized/no-window activation. A TetraVox older than 0.6.0 cannot save live scenes through TI. |
| White-matter networks (`tit.tract`, ARCHITECTURE §15) | Send tract layers to TetraVox: its side shipped in 0.8.0, and TI's schema change is unapplied in [`dev/upstream/tetravox-tracts/`](../../dev/upstream/tetravox-tracts/README.md), guarded by `tractLayerProtocol`. Named bundles (RecoBundles + HCP842). Compare against the MRtrix3 iFOD2 reference with the V1 metrics and a two-seed noise floor (reference data in Dataset 000, [TESTING.md](TESTING.md)). Find the cause of the proof of concept's +5.24 % leadfield-against-FEM difference and check more montages. Two-simulation comparison; float16 dpv in assess outputs |
| Test harness | Avoid tracked smoke-payload churn while preserving UI/HTTP replay equivalence |
| CI | Put the mock e2e suite back on every `main` push: `desktop-e2e-mock` is opt-in (`run_e2e_mock`) until it is sharded, has its fonts and its five Linux-only spec failures are fixed ([TESTING.md](TESTING.md)) |
| Maintenance | Assess OpenSSF practices and extend integration coverage for selected colleague workflows |

For older implementation plans and retired TODO references, see [DECISIONS.md](DECISIONS.md).

### Network follow-up: slow-wave effects in source space

Does the stimulated white-matter network explain where slow-wave effects appear in source space, beyond the local field and
baseline? This is a secondary analysis drafted 2026-11-04, before any DWI was seen; it changes no primary result, and the study's
own repository owns its statistics and results. The full plan and participant inventory are unpublished and stay in Dataset 000
(`derivatives/ti-toolbox/tract_validation/dev_record/eeg_plan/`). Nothing below is built. Completion: the function below ships with
its tests, and the study's author has decided the items the plan lists.

**Toolbox function.** `tit.tract.cortex.project_to_cortex(subject_id, simulation, weight, radius_mm=3.0, reduce="mean", exclude_terminal_mm=0.0, fsaverage_spacing=5)`
returns subject central-surface arrays (lh, rh) and the fsaverage morph through SimNIBS `cross_subject_map`, and writes
`Simulations/<sim>/tract/cortex_<weight>_r<r>.npz` with a JSON provenance sidecar. Tests: a synthetic surface with a known deposit,
and a real subject with QSIPrep DWI (sub-CHN).

**Predictor, STREAM-4D style** (Atalay et al. 2025, doi:10.1016/j.brs.2025.06.015), from the whole-brain tractogram, for each
streamline and each end within r of cortex:
- Weights, three explicit variants: arc-mean ti_along excluding the 10 mm nearest the end, since that segment sits in the same local
  field as the cortex it lands on (primary); `ti_along_mean`; `align_index`.
- Deposit on the union of central-surface vertices within r = 3 mm. The network stage instead takes the single nearest label.
- Reduce to the mean of the weights deposited at a vertex (primary, less driven by termination density and gyral bias), or their sum
  over total streamlines.
- Cross-check: parcel means computed directly from `network.npz` labels and per-point ti_along should agree at r > 0.95.

**Primary test, fixed before DWI is processed.** Per subject, partial Spearman across the 68 DK parcels between the change in source
density and the predictor, controlling TI_max, TI_normal, HF_max and baseline (all three fields enter as covariates, none designated);
the statistic is the mean Fisher-z, against 10,000 parcel spins with one rotation shared across subjects (Váša et al. 2018,
doi:10.1093/cercor/bhx249; Alexander-Bloch et al. 2018, doi:10.1016/j.neuroimage.2018.05.070; spin nulls can still be liberal,
Markello & Misic 2021, doi:10.1016/j.neuroimage.2021.118052). Bundle level is the tool-robust scale for any between-subject dose, per
the cross-tool entry in [DECISIONS.md](DECISIONS.md).

**DWI logistics.**
- QSIPrep refuses arm64 hosts, so it needs an x86-64 Docker host with the TI-Toolbox image; pilot one subject.
- The project's T1 must be the image charm used (a copy of `m2m_<id>/T1.nii.gz`), or the ACPC to T1 transform is silently wrong.
- The DWI JSON needs `PhaseEncodingDirection` and `TotalReadoutTime` or `EffectiveEchoSpacing`. Run `validate_bids_dwi` and
  `ensure_total_readout_time(repair=False)` before the long run. With no reverse-PE fieldmap, SyN correction runs, with poorer
  endpoint precision where susceptibility distortion is largest.
- `tit.tract` writes into the head model's derivatives, so run it in a separate working project with file-level links to the
  source data, mounted read-only. Measured on ernie and CHN: track + network 8–9 min, assess about 5 min, peak RSS 6–8 GB. QSIPrep wall
  time was not measured.

**The result is uninterpretable if** predictor and local field are collinear at parcel level (VIF > 10, or R² of predictor on field
> 0.9), a carrier-only placebo shows the same association, frame QC fails, fewer than 80 % of streamlines have an end assigned to
cortex, or the conclusion flips across seed or radius.

### Native Apple GPU preprocessing

Managed installation, project-session consent and sandboxed FastSurfer execution are implemented for local Apple Silicon desktop sessions. Keep native execution opt-in while collecting cross-machine installation and segmentation-quality evidence. Linux/Windows GPU workers and browser-only native host integration are outside this increment.
