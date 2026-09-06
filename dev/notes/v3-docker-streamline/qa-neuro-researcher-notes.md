# QA — neuroscience-researcher lens (2026-09-03)

Reviewer: QA subagent. Scope: `dev/notes/v3-docker-streamline-plan.md` D1-D6 + §1 contracts, the
Phase A-C lane notes in `dev/notes/v3-docker-streamline/`, `desktop/DESIGN.md` §8.1/§10, and the
two real-embed screenshots (`desktop/tests/e2e/artifacts/phase-c/viewer-real-embed{,-dark}.png`).
Verified against the maintainer's live stack (`ti-toolbox-fad740e5-tit-1`, `idossha/ti-toolbox:dev`,
127.0.0.1:8765, project `000`) via `curl` with the bearer token (no jobs started, no restarts). Did
not drive the offscreen Electron app directly (time-boxed); relied on the provided screenshots for
the rendered-UI evidence and the live API for behavioural ground truth. No FastSurfer/charm run,
no simulation started.

## What is good (verified, not just read)

- `POST /api/plan/pre` for ernie with `run_fastsurfer: true` correctly resolves `output_dir` to
  `/mnt/000/derivatives/fastsurfer/sub-ernie` (not `derivatives/freesurfer`), `exists: false`,
  cost `{cpus: 2, mem_gb: 6}`, DAG stage `ernie:G2b` tagged `["G2b","fastsurfer"]` — matches
  w3b-preprocessing-notes.md exactly.
- The legacy alias works functionally: the same POST with `{"run_recon": true}` in place of
  `run_fastsurfer` produces an **identical** plan (same output_dir, same G2b stage) — confirms
  `tit.pre.config.migrate_legacy_keys` is wired into `POST /api/plan/pre` per r-reconcile item 2.
- `GET /api/capabilities` on the live container: `fastsurfer: true`,
  `tetravox_embed: {available: true, version: "0.3.4", protocol: 1}` — both real, not placeholders.
- `GET /api/catalog/subjects` matches ground truth exactly: ernie `has_fastsurfer: false,
  has_freesurfer: true`; 101 and are-you-sure-neither-exists cases behave sanely (see finding 1
  for where this data then goes missing in the UI).
- ROI atlas discovery (`GET /api/catalog/atlases`) does the right thing for both of the lens's
  target cases:
  - ernie (legacy FreeSurfer only): lists charm's cortical annots (DK40/HCP_MMP1/a2009s) +
    charm's `labeling.nii.gz` **and** the five legacy FreeSurfer voxel atlases
    (`aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, both hippoAmygLabels, ThalamicNuclei) —
    D2's "existing derivatives keep working" is real, not just a docstring claim.
  - subject `101` (neither FastSurfer nor legacy FreeSurfer): falls back cleanly to just charm's
    `labeling.nii.gz`, no crash, no empty-with-no-explanation state.
- Region-name resolution is correct for cortical (`DK40` lh: `bankssts`, `caudalanteriorcingulate`,
  …) and for hippocampal/amygdala subfields (`lh.hippoAmygLabels-T1.v22.mgz`:
  `Accessory-Basal-nucleus`, `Anterior-amygdaloid-area-AAA`, …) — real anatomical names, not IDs.
- `run_fastsurfer.sh --help` in the real container confirms every flag `tit/pre/fastsurfer.py`
  passes (`--seg_only --no_cereb --no_hypothal --no_cc --device --threads --py`) is a real,
  documented FastSurfer CLI flag — the invocation in the plan doc, the lane notes and
  `docs/wiki/pre-processing.md` all match the actual binary.
- `docs/wiki/pre-processing.md` is accurate and thorough: exact invocation, output layout, the
  Dice/timing table, the parallel-with-charm DAG, the `run_recon`→`run_fastsurfer` alias, and an
  explicit "What changed from FreeSurfer" section naming thalamic nuclei / hippocampal subfields
  as gone with no replacement, pointing at charm's `labeling.nii.gz` for whole-structure ROIs
  instead. Every claim checked against code or the live container matched.
- The two real-embed screenshots show a working, correctly-scened Tetravox render for ernie's
  "Thalamus" simulation, `TI_max` field, subject space: T1 + electrode overlay + grey-matter mask
  visible by default, mesh + white-matter mask correctly hidden by default (large-file lazy load
  per `_grey_mesh_layer`'s docstring), dark canvas in both themes, full-bleed layout, 40px source
  bar, Layers/Cursor/Layout/Export inspector — matches DESIGN.md §10 point for point.

## Findings

### 1. HIGH — `has_fastsurfer` exists end-to-end in the API but is invisible in every desktop UI surface

`desktop/src/renderer/api/schema.d.ts:2515` has `has_fastsurfer: boolean` (required, confirmed live
via `GET /api/catalog/subjects`), and `tit/catalog.py` puts a `fastsurfer` column ahead of
`freesurfer` in `subject_info_matrix`. But:

```
$ grep -rn "has_fastsurfer" desktop/src/renderer/
desktop/src/renderer/api/schema.d.ts:2515:            has_fastsurfer: boolean;
```

No page reads it. Every place presence chips are built (`pages/preprocess/index.tsx:179`,
`pages/subjects/index.tsx`, `app/SubjectSwitcher.tsx`, `pages/simulator/index.tsx`,
`pages/optimizer-flex/index.tsx`, `pages/panels/source/index.tsx`) still lists
`{ label: "freesurfer", on: s.has_freesurfer }` with no matching `fastsurfer` chip. Confirmed
visually in both provided screenshots: the context bar reads `raw · freesurfer · m2m · dwi · ct`
— no `fastsurfer` chip, even though this is exactly the kind of at-a-glance state DESIGN.md's own
"what must not be lost" table calls out by name: *"Presence chips … The fastest read in the app:
what a subject actually has."*

This is the one workflow this whole program is about — a researcher deciding "does this subject
need FastSurfer, or does it already have it?" — and the app's signature UI pattern for exactly that
question doesn't carry the new field at all. `pages/preprocess/index.tsx` is the worst-affected
page: its own subject picker (the page whose entire job is running FastSurfer) shows `freesurfer`
but not `fastsurfer`, so a user cannot tell from that picker who still needs the step.

**Fix**: add a `fastsurfer` chip (ahead of `freesurfer`, per the catalog's own column order)
everywhere `has_freesurfer` is read today; the field is already on the wire.

### 2. HIGH — Thalamic-nuclei ROI regions resolve to meaningless `"Label 8103"` instead of real nucleus names, even though the real names exist on disk

`GET /api/catalog/atlases/regions?subject=ernie&atlas=ThalamicNuclei.v13.T1.mgz` (live, verified):

```json
{"id": 8103, "name": "Label 8103", "hemi": null}
{"id": 8104, "name": "Label 8104", "hemi": null}
```

vs. the hippocampal/amygdala subfield atlas on the same subject, which resolves correctly:

```
$ curl .../atlases/regions?subject=ernie&atlas=lh.hippoAmygLabels-T1.v22.mgz
{"id": 7008, "name": "Accessory-Basal-nucleus", ...}
{"id": 7010, "name": "Anterior-amygdaloid-area-AAA", ...}
```

The real names for the thalamic-nuclei labels are sitting right next to the segmentation on disk —
`derivatives/freesurfer/sub-ernie/mri/ThalamicNuclei.v13.T1.volumes.txt` (produced by the original
`recon-all` run, still present, `docker exec ... cat` verified):

```
Left-LGN 345.060357
Left-PuM 1482.091016
Left-VPL 1110.453902
Left-CM 345.286175
```

but nothing in the atlas layer reads that file. `tit/atlas/segstats.py::resolve_lut_for_atlas`
falls back to the bundled `resources/atlas/FreeSurferColorLUT.txt` when no `{stem}_LUT.txt`
sidecar exists next to the atlas — and that bundled table has **zero** entries in the 8100s range
(`grep -n "^8103" resources/atlas/FreeSurferColorLUT.txt` → no hits) while it does cover the 7000s
range the hippocampus/amygdala atlas uses. The regenerated sidecar
(`ThalamicNuclei.v13.T1_labels.txt`, written by `tit.atlas.segstats` the first time this atlas is
listed) permanently bakes in the wrong names once created.

This directly undermines D2's own claim ("existing recon-all derivatives on disk keep working") for
the one legacy atlas a researcher would most plausibly still want by name — a specific thalamic
nucleus for a targeted montage, exactly this lens's stated scenario. Today the ROI picker's
"Region(s)" multi-select for this atlas is a list of 48 numbers with no way to tell `Left-CM` from
`Left-PuM` without cross-referencing `ThalamicNuclei.v13.T1.volumes.txt` by hand outside the app.

**Fix**: `resolve_lut_for_atlas` (or a purpose-built reader next to it) should also recognise
FreeSurfer's own `*.volumes.txt` sidecar (name-plus-volume, no explicit numeric id — needs pairing
by row order against the segmentation's own sorted unique label ids, which is exactly what
`ThalamicNuclei.v13.T1.mgz`'s label ordering already is) as a LUT source for this one atlas family,
the same way `labeling_LUT.txt` gets special-cased for charm's `labeling.nii.gz`. Whether this
predates this program's work or was introduced by `tit.atlas.segstats` was not established within
the time box — worth a quick `git log -p` / `main` comparison before assigning it.

### 3. MEDIUM — `docs/wiki/analyzer.md` contradicts `docs/wiki/pre-processing.md` on what's available for a new subject

`docs/wiki/analyzer.md:42`:

> Voxel atlases: `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `lh.hippoAmygLabels-T1.v22.mgz`,
> `rh.hippoAmygLabels-T1.v22.mgz`, `ThalamicNuclei.v13.T1.mgz`, plus the subject's own
> `segmentation/labeling.nii.gz`

listed with no caveat, using the pre-v3 filenames (no `.deep` FastSurfer variant mentioned at all)
and no note that four of those five are legacy-FreeSurfer-only and will not exist for any subject
processed with FastSurfer alone. `docs/wiki/pre-processing.md` (touched by this program, W6) gets
this exactly right in its own "What changed from FreeSurfer" section — same wiki, sibling page,
opposite information. A researcher who reads the Analyzer page (the page they'd actually consult
when picking an ROI) has no reason to expect the gap the Pre-processing page already documents.
`w6-docs-ci-notes.md`'s own "Not touched" section names `docs/wiki/analyzer.md` as explicitly out of
this lane's scope ("diverges heavily from main for reasons unrelated to this program") — correct
call for a docs-only lane, but the resulting cross-page contradiction is real and user-facing.

**Fix**: one paragraph in `analyzer.md` pointing at `pre-processing.md`'s "What changed from
FreeSurfer" section, or at minimum an inline note that the hippocampal-subfield/thalamic-nuclei rows
are legacy-derivative-only.

### 4. MEDIUM — Viewer layer names are raw pipeline filenames with no glossary anywhere

Screenshot layer list (`viewer-real-embed.png`, ernie / Thalamus / TI_max): `T1`,
`electrode_overlay_subject`, `Thalamus_TI_subject_TI_max`, `grey_Thalamus_TI_subject_TI…`
(truncated), `white_Thalamus_TI_subject_T…` (truncated), `grey_Thalamus_TI` (jet). These are
`os.path.basename(path)` minus extension (`tit/viewspec.py::to_tetravox_viewspec`,
`name = _scene_stem(name)`) — SimNIBS's own internal naming grammar
(`<montage>_TI_subject_TI_max` = whole-head NIfTI, `grey_`/`white_` prefix = surface-masked variant,
bare `grey_<sim>_TI` = the per-element mesh version of the same field), not a curated display name.
At the inspector's ~280px width and 1280px total (DESIGN.md's own measured screenshot width), two
of the six rows truncate to where a mesh layer (`grey_Thalamus_TI`, jet) and a NIfTI layer
(`grey_Thalamus_TI_subject_TI_max`, turbo) — same physical quantity, different colormap, no
explanation why — are visually near-identical until you hover for the native `title` tooltip
(`pages/viewer/index.tsx:255`, confirmed present in code). `docs/wiki/visualizers.md` (rewritten by
W6 as the "Viewer" page) has zero mentions of `grey_`/`white_`/`TI_max`/layer-naming at all
(`rg` came back empty) — nothing anywhere explains the grammar to a first-time user of this build.

This isn't a crash or a wrong number, so it is scored medium, not high — but it is exactly the kind
of thing DESIGN.md §8.1 asks a reviewer to judge ("numbers and the DOM, not pictures"): the DOM fact
here is that six technically-precise, un-glossed filenames are the entire explanation a working
scientist gets for what they're looking at.

**Fix**: either a short glossary block in the Viewer inspector (or linked from it) explaining the
`grey_`/`white_`/bare-mesh naming grammar and why mesh vs. NIfTI colormaps differ, or curate a
display name at the point layers are built in `to_tetravox_viewspec` instead of using the bare
filename stem.

### 5. LOW — the legacy `run_recon` alias silently migrates with no signal in the API response

`tit/pre/config.py::migrate_legacy_keys` only `logging.warning`s server-side (verified in source,
not surfaced in the response). Live-tested: `POST /api/plan/pre` with `{"run_recon": true}` in the
config returns the identical, correctly-migrated plan (finding-worthy in the "what's good" list
above) but `"warnings": []` — an old script or notebook sending the deprecated key gets no
indication anywhere in the HTTP response that its config was silently translated (or, for the other
three dropped keys, silently ignored). Low severity because the functional behaviour is correct and
this only affects a caller still using the pre-v3 JSON shape.

**Fix**: have `tit/server/routes/plan.py`'s call to `migrate_legacy_keys` collect its warnings into
the response's own `warnings: list[str]` field instead of (or in addition to) the server log.

### 6. LOW, flagged for confirmation only — live image size is 3x the documented figure

`docker images idossha/ti-toolbox:dev` on this machine reports **21.3 GB**, against the ~6.7 GB
figure both `docs/installation/installation.md:108` and `w2-image-notes.md`'s own measurement
state for the same image name/tag. `docker history` on the running image shows it was built ~15
minutes before this check, with `TIT_REPO_DIR=ti-toolbox` baked in (a full repo copy, consistent
with a dev-loop/bind-mount-friendly build rather than the lean recipe the docs describe) — I could
not confirm within the time box whether this specific `:dev` build corresponds to the same
`Dockerfile.ti-toolbox.layered` recipe W2 measured at 6.66 GB, or is a different, heavier dev
variant. Not asserting a docs bug; flagging the raw discrepancy (documented claim vs. this
machine's actual `docker images` output, both concrete numbers) for whoever owns image builds to
reconcile.

## Not verified (time-boxed out)

- Did not drive the offscreen Electron app directly against this container (the `stack-verify`/
  `viewer-verify` scratchpad scripts were available but not exercised) — relied on the two provided
  screenshots for rendered-UI evidence.
- Did not test the MNI toggle's actual behavior (switching subject-space → MNI-space datasets) live;
  only confirmed the button exists in the screenshot and that `_subject_atlas_layer`/
  `_default_mni_atlas_path` have separate code paths for `space == "mni"`.
- Did not attempt a real FastSurfer run (out of scope per the task's CPU/time constraints) — all
  FastSurfer-stage claims are verified via the plan-preview API, `--help` output, and source
  reading, not an actual segmentation.
- Did not check `docs/wiki/ex-search.md`/`simulator.md`/`mti.md` for the same kind of drift found in
  `analyzer.md` — out of this lens's core scope (preprocessing/analyze/view) and W6 already flagged
  these pages as unaudited in its own notes.
