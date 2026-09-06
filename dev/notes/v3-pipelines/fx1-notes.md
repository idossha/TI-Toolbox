# Lane FX1 — Optimizer Ex/mEx electrode buckets, and the optimizer half of U16 (2026-09-03/04)

Scope: `desktop/src/renderer/pages/optimizer/**`, `tests/e2e/real/{ex,mex,flex}.spec.ts`,
`tests/e2e/optimizer.spec.ts` (mock), the two new unit specs. Container restarts: **0** (this lane
touches no `tit/server/**`, `tit/jobs/**` or `tit/catalog.py`).

The lane ran in two passes. The first (≈20:00–20:21 local) landed the code, the tests and a first
set of real runs but produced no notes; this file is written by the second pass (20:25–20:40),
which re-derived the diagnosis from the live catalog, proved the unit test fails without the fix,
re-ran every real spec from scratch under its own run id (`fx1b`/`fx1c`) and re-verified the
cleanup. Every number below is from the second pass, measured, not inherited.

## 1. The finding, from the two endpoints themselves

S2's evidence: `real/ex.spec.ts` and `real/mex.spec.ts` waited 30 s for the electrode option
`Fp1` that never appeared; every bucket `MultiSelect` was empty for the only leadfield-backed net
on the project. Re-derived against the live container:

```
GET /api/catalog/leadfields?subject=ernie
  [{"net":"EEG10-10_UI_Jurak_2007", "path":".../ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
    "exists":true, "size_bytes":3239314641}]              <- BARE name

GET /api/catalog/eeg-nets?subject=ernie
  [{"name":"EEG10-10_Cutini_2011.csv", ...},
   {"name":"EEG10-10_UI_Jurak_2007.csv", "electrodes":[...], "n":...}]   <- REAL FILENAME
```

The page's net identity came from the leadfield strip (`leadfields[].net`, bare) and its electrode
list from an **equality** join against the cap catalog (`eegNets[].name`, `.csv`-suffixed):

```ts
// pages/optimizer/index.tsx, before
const electrodes = eegNets.data?.find((n) => n.name === net)?.electrodes ?? [];
```

The join can never match on real data, so `electrodes` was always `[]`, every Ex/mEx bucket offered
zero options, and `blockedReason` stayed "Fill in every electrode bucket." — Ex/mEx were
unreachable from the UI for any real leadfield. The mock server hides it: its fixtures spell both
sides bare, which is why `tests/e2e/optimizer.spec.ts` passed throughout.

Two sources spell the same net differently because two different pieces of code produce them:
`tit/opt/leadfield.py::list_leadfields` parses the net out of `<sub>_leadfield_<net>.hdf5`, while
`tit/catalog.py::eeg_nets` returns `pm.list_eeg_caps()`, i.e. the cap files themselves. Same class
of bug S2 fixed in `pages/panels/source/config.ts` (a `.csv.csv` double suffix).

## 2. The fix — one net identity for the page

New module `desktop/src/renderer/pages/optimizer/nets.ts`: **a net is its bare name everywhere on
this page** — the value the strip selects, the key the electrode lookup uses, and the `eeg_net` a
leadfield job is submitted with (`LeadfieldGenerator` appends `.csv` itself, so a suffixed value
there would ask for `<net>.csv.csv`).

| Export | What it decides |
|---|---|
| `netKey(name)` | strips one trailing `.csv`; `"X.csv"` and `"X"` are one net |
| `leadfieldFor` / `leadfieldPathFor` | the HDF5 for a net across the spelling difference; `null` when the row exists but was never computed (`exists:false`) |
| `electrodesForNet` | the options behind every bucket and the Ex pool |
| `netOptions` | the strip's list: every net once, bare, leadfield-backed first (so "Generate (≈40 min)" stays reachable for a net without one) |
| `defaultNet` | the net a freshly opened page starts on: the first with a leadfield |
| `subjectsMissingLeadfield` | U16: *which* selected subjects cannot run, by name |

`index.tsx` and `ExSections.tsx` (the `LeadfieldStrip`) now go through it; no page code compares
net strings any more.

**Fails without the fix (measured, this pass).** Patched `electrodesForNet` back to the equality
join, ran `npx vitest run tests/unit/optimizer-nets.test.ts`: **1 failed | 8 passed**, failing on
`electrodesForNet(REAL_NETS, "EEG10-10_UI_Jurak_2007")`. Restored: **9 passed** (152 ms). The test
fixtures are the exact bodies the two endpoints above returned, plus the mock server's bare shape,
so both spellings stay covered.

## 3. U16 for this page — the subject set is the page's

Replaced the shell-derived subject with a page-owned control, following Pre-processing's pattern:
a Tier-1 `Subjects` `MultiSelect` seeded from the shell's current subject (`selection`), page-owned
after; a new shell subject is folded in, never re-scoped away. `subjects[0]` is the "primary" whose
catalog fills the shared controls (nets, atlases, saved ROIs).

Everything per-subject is resolved **per subject**, because on this project resolving it once and
reusing it would silently optimise every subject against the first subject's anatomy:

- `leadfieldPathFor(leadfieldsBySubject[s], net)` — one `["leadfields", s]` query per selected subject;
- `useAtlasLookups(subjects, roi)` — one atlas query per subject, so a subcortical target's
  `atlas_path` points into that subject's own `derivatives/freesurfer/sub-<id>/mri/`;
- `exSubmissions` / `flexSubmissions` expand to one job per (subject × target) / per subject.

The Optimizer submits **one job per subject** rather than one job carrying N `subject_ids`: an
optimizer config is per-subject by construction (`leadfield_hdf`, `roi_atlas[].atlas_path`), so a
single job with several ids could only carry one subject's matrix. The *plan* request does carry
every id (the server's `_plan_ex`/`_plan_flex` loop over `subject_ids`), which is what makes the
grid one row per chosen subject.

Two guards the plan/submit divergence needs (P4's own failure class — a plan that promises a job
Run never queues):

- `missingLeadfieldReason` — names the subjects with no leadfield for the chosen net;
- `missingTargetReason` — names the subjects for which the chosen atlas target does not resolve.
  Real case on Dataset 000: `sub-101` **has** its own `EEG10-10_UI_Jurak_2007` leadfield but not
  the FreeSurfer atlas ernie's target comes from, so the server plans a row for it that no config
  can be built for.

Measured (mock `tests/e2e/optimizer.spec.ts`, "U16: the page owns its subject set"): two subjects →
`plan-stat-jobs` = 2, one `plan-cell-ernie-*` and one `plan-cell-101-*`, run button reads "Run flex
search for 2 subjects", and the two `POST /api/jobs` bodies carry `subject_ids` `["ernie"]` /
`["101"]` with `config.roi.atlas_path[0]` pointing at `sub-ernie`'s and `sub-101`'s own DK40 file
respectively. Measured on real data (`real/ex.spec.ts`, second test): adding `101` to the page's
control adds a `plan-cell-101-*` row, and the action-bar digest plus the Run button's `title` name
`101` as the subject that blocks the run.

## 4. Real runs (shared container `ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`)

All offscreen through `scripts/e2e-quiet-check.sh` (`TIT_E2E_OFFSCREEN=1`); every run reported
`PASS — no new Electron/Chromium window reached the screen`. The maintainer's own dev-mode window
(id 127257) was on screen before each run and correctly ignored by the check.

| # | Command | Job | Wall | Outcome |
|---|---|---|---|---|
| 1 | `playwright test --project=real tests/e2e/real/ex.spec.ts` (`TIT_E2E_RUN_ID=fx1b`) | `675b0045382c4816` | job 34.9 s, suite 44.5 s | **2 passed** — succeeded, 2 artifacts, listed in Results as `ex:ernie:smoke-ui-fx1b-ex` |
| 2 | `playwright test --project=real tests/e2e/real/mex.spec.ts` (`fx1b`) | `3a13cd5070dd4b67` | job 45.6 s, suite 53.1 s | **1 passed** — succeeded, 2 artifacts, listed as `mex:ernie:smoke-ui-fx1b-mex` |
| 3 | `playwright test --project=real tests/e2e/real/flex.spec.ts` (`fx1b`) | `fb8832a6d4f440d1` | 3.0 s to running→cancelled | **1 passed** (F0's list-form ROI fix still holds through this page) |
| 4 | `playwright test --project=real tests/e2e/real/flex.spec.ts` (`fx1c`, after the spec edit) | `49a13d5262624183` | 2.8 s | **1 passed**, state `cancelled` confirmed via the API |
| 5 | direct API replay of `tests/smoke/payloads/ex.json` (`run_name` → `smoke-fx1-replay-ex`) | `40e868ba35b340c8` | 39.2 s | `validate` ok, `plan` 1 job `exists:false`, job **succeeded** — the recorded UI payload runs unchanged through the runner (P5 coupling for `ex`) |
| 6 | `playwright test --project=default tests/e2e/optimizer.spec.ts` (mock) | — | 8.9 s | **7 passed** |

Both e2e payloads landed: `tests/smoke/payloads/ex.json` (4 buckets, `BucketElectrodes`,
`roi_name: aparc.DKTatlas+aseg.mgz_1region`, `run_name: smoke-ui-fx1b-ex`) and `mex.json` (8
buckets, same target). `flex.json` was re-recorded byte-identically (1398 B, `atlas_path` still the
list form).

Search numbers from run 1's own log (7 candidate montages = one bucket combination × 7 current
splits): `TImax` 0.0505 → 0.1481 V/m, focality 0.9748 → 1.1331, 0.43 s per montage.

**Cleanup:** `find … -newermt "2026-09-03 20:25"` over `ex-search/`, `m-ex-search/` and
`flex-search/` returns nothing — the only entries left are the maintainer's pre-existing
`docs_ex_*`, `docs_mex_*`, `VAL_*` and timestamped runs. Nothing of this lane's survives.

## 5. Spec change in run 4

`tests/e2e/real/flex.spec.ts` still described flex as "known broken" and its terminal-state branch
asserted the old `TypeError: expected str, bytes or os.PathLike object, not list`. F0 fixed that
runner on 2026-09-03 and the healthy path is now "running → cancel", so the branch was inverted:
the payload's `atlas_path` list shape is now *asserted* (not just logged) before submission, the
running branch is the expected one, and the terminal branch fails with the job's own last lines in
the message — a regression witness that names the failure instead of timing out. Re-run: pass.

## 6. Gates

| Gate | Result |
|---|---|
| host `python3 -m pytest -q` | **3345 passed, 18 skipped, 21 deselected**, 36.7 s |
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors, 3 warnings — all pre-existing `react-hooks/incompatible-library`, in `pages/preprocess/index.tsx`, `ui/DataTable.tsx`, `ui/VirtualList.tsx`; none under `pages/optimizer/` |
| `npx vitest run` | **61 files, 716 tests passed**, 4.7 s |
| `npm run build` | ok (once, 2.4 s) |
| mock `tests/e2e/optimizer.spec.ts` | 7 passed |

## 7. Requests to other lanes

1. **[HX / S1 — `tests/smoke/matrix.py`] The `ex` and `mex` Level A rows now silently replay this
   lane's recorded payloads and will fail, and litter.** `payload_path_for` prefers
   `payloads/<row id>.json`; those two files did not exist when the matrix was written, so both
   rows are `source=payload` from now on — with no `payload_rename`, while `creates`,
   `expect_files` and the catalog check are all computed from `ctx.name("ex"/"mex")`. Measured
   in-process (host, no container):

   ```
   ex   source=payload  origin=ex.json   payload run_name = smoke-ui-fx1b-ex
        creates      = .../ex-search/smoke-selftest-ex
        expect_files = .../ex-search/smoke-selftest-ex/final_output.csv
        payload_rename = None
   mex  source=payload  origin=mex.json  payload run_name = smoke-ui-fx1b-mex   (same divergence)
   ```

   So the next `dev/smoke.sh` run writes `ex-search/smoke-ui-fx1b-ex`, fails `expect_files` and the
   catalog check on `smoke-<runid>-ex`, and leaves the directory behind (the manifest claimed the
   other path) — a P6 violation. Fix is the shape HX already used for stats/nilearn/sim:

   ```python
   def _rename_ex_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
       """``run_name``: names ``derivatives/SimNIBS/sub-<id>/{ex-search,m-ex-search}/<name>/`` 1:1."""
       config["run_name"] = ctx.name(row.id)
   ```
   wired as `payload_rename=_rename_ex_payload` on both rows. Worth doing before the CR pass, since
   the critic re-runs the whole matrix. (`tests/smoke/**` is not this lane's to edit.)

2. **[FX3 — runner artifacts] `ex` reports 2 of the 4 files it writes.** Job
   `40e868ba35b340c8` reported `final_output.csv` + `run_config.json`; the run directory it wrote
   held `final_output.csv`, `run_config.json`, `intensity_vs_focality_scatter.png` and
   `montage_distributions.png` (host listing before cleanup; a bigger search such as
   `docs_ex_symmetric` writes five PNGs). The visualisation PNGs never reach `artifacts`, so the
   Results preview U14 wants for ex/mex ("the run config and the top rows of `final_output.csv`
   … with its figures") has no figures to show. Same family as FX3's stats/blender/tools finding,
   but partial rather than empty.

3. **[Results page owner] A just-finished run is invisible until the renderer reloads.** Both
   ex/mex specs must `page.reload()` before the Results tree lists the new run: the catalog queries
   have a 60 s `staleTime` (`src/renderer/main.tsx`) and nothing invalidates them when a job
   finishes, and the page has no refresh control. Measured by S2 on the first ex run (catalog
   served at 01:10:18, job finished 01:11:00, no further request during a 20 s assertion); the
   reload is still load-bearing in this pass.

Confirmed, no action needed: the RUNBOOK's `--project=real` (not `--project real`) note is right —
the variadic form swallowed the spec path on this lane's first invocation
(`Project(s) "tests/e2e/real/ex.spec.ts" not found`).
