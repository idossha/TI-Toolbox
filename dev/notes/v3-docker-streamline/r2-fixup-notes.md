# Lane R2 — fix-up after Phase B (2026-09-03)

Lane brief: the 8 numbered items in this session's task message, closing W5's "needs_from_other_lanes"
(`w5-viewer-notes.md`) and the remaining Freeview/Gmsh/X11 audit from `r-reconcile-notes.md`/
`w6-docs-ci-notes.md`. Read first: `dev/notes/v3-docker-streamline-plan.md` §0/§1, the three Phase-B
notes named in the brief.

## Items closed

1. **BLOCKING — fake-embed CSP fix.** Split `desktop/tests/e2e/fixtures/fake-embed/index.html`'s
   inline `<script>` into `desktop/tests/e2e/fixtures/fake-embed/fake-embed.js`, referenced by
   `<script src="./fake-embed.js"></script>` — no behaviour change. Added the missing `serialize` →
   `scene {id, spec}` handler: `state.lastScene` now keeps the raw `EmbedViewSpec` from the most
   recent `load` (not the reduced `state.layers`/`state.datasets` view) and `handleSerialize` echoes
   it back verbatim (`{datasets: [], layers: []}` before any `load`). Both mock (`server.mjs`) and
   real (`tit/server/static.py`) already resolve `.js` to `text/javascript` via `mimetypes.guess_type`
   (verified on host py3.14 and the container's py3.11) — no MIME table change needed anywhere.
   `viewer.spec.ts` + `results.spec.ts`: **8/8 passed** under the quiet check (both individually and
   as part of the full suite below).
2. **`app/jobs-rail/api.ts:47`** — deleted the `"viewer"` entry from `JOB_KINDS`. `rg -n '"viewer"'
   desktop/src/renderer/app` now finds nothing.
3. **Preprocess page: FastSurfer migration.** `pages/preprocess/index.tsx`:
   - `defaultConfig()` — `run_recon`/`parallel_recon`/`parallel_cores`/`run_subcortical_segmentations`
     replaced by `run_fastsurfer: true` (Qt-parity default) and `fastsurfer_threads: null` (the page
     has no host-CPU-count reading anywhere in `desktop/src`, so it defaults to blank and lets the
     server apply `tit.pre.fastsurfer.DEFAULT_THREADS`, per the schema docstring).
   - `computeParallelRecon()` deleted outright (no field it computed exists any more);
     `toSubmitConfig()` lost its now-unused `parallelSubjects` parameter.
   - `plannedSteps()` — `"FreeSurfer recon-all"` → `"FastSurfer segmentation"`, subcortical step
     removed; order now matches `run_pipeline`'s real execution order (`tit/pre/structural.py`:
     DICOM → charm/atlas → fastsurfer → tissue → qsiprep → qsirecon → extract_dti).
   - `describePreStageDir()` gained a `fastsurfer` branch ("FastSurfer segmentation") ahead of the
     existing `freesurfer` one (now labelled "FreeSurfer recon-all (legacy)" — still matches for any
     stray legacy-named output dir, per D2's "existing derivatives keep working").
   - UI: the "Run FreeSurfer recon-all" checkbox + nested "Run subcortical segmentations" checkbox
     replaced by one "Run FastSurfer segmentation" switch (with help text) and a nested "FastSurfer
     threads" `NumberInput` (`Field`, disabled when the switch is off, no default value — same
     no-host-CPU-count reasoning as `defaultConfig()`).
   - `pages/preprocess/PARITY.md` updated: the run_recon/subcortical rows replaced, the "Run
     recon-all in parallel" row reworded to say the fields were **removed**, not just unexposed, and
     the Plan-panel stage-list line reworded (no subcortical step).
   - `tests/e2e/preprocess.spec.ts` needed no assertion changes — it never referenced the removed
     field names or button labels, only `convert_dicom`/`create_m2m`/`run_tissue_analysis`. Confirmed
     green in the full e2e run below (#31).
4. **Unit tests against the regenerated schema.**
   - `tests/unit/preprocess-defaults.test.ts` — dropped the `computeParallelRecon` import/test;
     `toSubmitConfig()` calls dropped their 4th argument; `plannedSteps()`'s expected list and its
     `stageLabelFor()` fixture path updated to `fastsurfer`.
   - `tests/unit/forms-ajvResolver.test.ts` — needed **no change**: it imports `defaultConfig` from
     the page itself, so item 3's fix already covers it (confirmed by the vitest run below: 0
     failures across the whole suite, this file's `PreprocessConfig` case included).
   - `tests/unit/shell-subject.test.tsx` — added `has_fastsurfer` to both `Subject`-shaped fixtures
     (`presenceChips` cases at lines 79/85 before edits); the `getSubjects` mock at line 36 is
     untyped (`vi.fn(async () => [...])` inside `vi.mock`, no real-module type check) so `tsc` never
     flagged it and it was left as-is.
   - `npx tsc --noEmit -p tsconfig.web.json` and `-p tsconfig.node.json`: **0 errors**, both configs
     (was 12 errors / 4 files per W5's report; the other 8 W3b/S2 already fixed before this lane
     started, per this session's own first typecheck run).
5. **`RoiPicker.tsx` rename.** `onOpenFreeview` → `onOpenViewer` everywhere in
   `pages/_shared/roi/RoiPicker.tsx` (`RoiPickerProps`, `SphericalPanel`'s own prop type and JSDoc);
   button label "Open T1 in Freeview" → "Open T1 in viewer". `pages/optimizer-flex/index.tsx`'s
   caller updated to the new prop name, and its stale explanatory comment (about the rename not yet
   having happened) deleted — the wiring itself (`openViewer` when `roi.mode === "spherical"`) was
   already correct, only the prop name/label were stale. No unit test named `RoiPicker` exists
   (`rg` came back empty), but `tests/e2e/optimizer-flex.spec.ts:132` asserted the old button text —
   updated to "Open T1 in viewer" (see the full e2e run, #25).
6. **Comment/doc hygiene.**
   - `app/viewerStatus.ts` header rewritten: no more "imports `@tetravox/engine`, ~530 KB JS / 850
     KB wasm" claim (false since W5's lane — the store is a few KB of postMessage plumbing). Kept
     the lazy `import.meta.glob` mechanism exactly as W5's own notes asked ("do not change it as a
     side effect") — only the comment changed, framed around the chunking property it still gives
     rather than a load-cost justification that no longer holds.
   - `DESIGN.md` §10 — the stale "two external routes ('Open in Freeview', 'Open in Gmsh')" /
     "Open externally ▾" prescription replaced with an accurate three-state description read
     straight out of `pages/viewer/index.tsx` and `viewer/TetravoxFrame.tsx`: `no-webgl2` (named
     renderer, Chromium M137 software-fallback removal, no buttons), `no-embed` (the frame's own
     8s-handshake-timeout state — names `/tetravox/` and the reported version), and the page-level
     "not bundled" state (`capabilities.tetravox_embed.available === false`, shown instead of
     mounting a frame at all). The old bullet conflated what are now three distinct, differently-
     triggered states; each is called out separately with the exact component/status that owns it.

7. **`HEAD /tetravox/` 405 fix.** Confirmed the failure mode first (`starlette.routing.Route`
   auto-adds `HEAD` when `GET` is present, but FastAPI's `APIRoute`/`_populate_api_route_state`
   does **not** — reproduced with a bare `TestClient`: `GET /tetravox/` 404 (no embed dir),
   `HEAD /tetravox/` 405 before the fix). Added `@router.head(...)` decorators alongside the three
   existing `@router.get(...)` ones in `tit/server/static.py` (`tetravox_index`, `tetravox_asset`),
   pointing at the same handler functions — no new code needed since `starlette.responses.FileResponse`
   already special-cases `scope["method"] == "HEAD"` (verified: `HEAD /tetravox/` on a real embed
   dir now returns 200, the correct `content-length`, and an empty body; `GET` on the same path
   returns the same headers plus the body). New test
   `tests/test_server_skeleton.py::test_tetravox_head_matches_get_headers_with_no_body` — HEAD vs
   GET status/CSP/content-length parity, empty HEAD body, across `/tetravox`, `/tetravox/`,
   `/tetravox/manifest.json` and an asset path. `black`-formatted.

8. **Freeview/Gmsh/X11 audit** — `rg -n "Freeview|Gmsh|freeview|gmsh|X11|xhost|DISPLAY" desktop/src
   tit --glob '!*.md'` (full output kept in this session's transcript; not reproduced here since
   most of it is legitimate and listed below). Fixed:
   - `desktop/src/renderer/dev/Gallery.tsx:184` — a component-gallery demo `IconButton`'s
     `aria-label="Open in Freeview"` (flagged in `w5-viewer-notes.md` §5 too) → `"Open in viewer"`.
     Purely a kitchen-sink label, no behavior.
   - `tit/constants.py` — `ENV_DISPLAY = "DISPLAY"` was dead (grepped the whole tree: zero
     references anywhere outside its own definition) and is exactly the kind of X11 remnant D3
     removed everywhere else; deleted, and the section comment above it ("Display and system
     variables" → "System variables") updated since only `ENV_HOST_IP` remains there. Left
     `ENV_HOST_IP` alone — unrelated to X11/the grep, out of scope.

   **Left, and why** (grouped by reason — the full per-line breakdown is in the grep output itself):
   - **The whole PyQt5 `tit/gui/**` X11-forwarded CLI path** (`analyzer_tab.py`'s "View in
     Freeview"/"Launch Gmsh" buttons and their `subprocess.Popen(["freeview"/"gmsh", ...])` calls,
     `ex_search_tab.py`/`flex_search_tab.py`/`components/roi_picker.py`'s `enable_freeview_button`
     wiring and their own Freeview launches, `help_tab.py`'s "Ensure X11 / XQuartz is installed"
     troubleshooting line, `system_monitor_tab.py`'s `"gmsh"` process-watch keyword,
     `tit/gui/__init__.py`/`tit/__init__.py`'s "runs inside Docker with X11" package docstrings).
     `docs/installation/bash-cli.md` (W6, `w6-docs-ci-notes.md`) explicitly documents this as "the
     classic two-image + X11-forwarded PyQt5 CLI path, unaffected by this program" — a genuinely
     separate deployment that still ships Freeview/Gmsh/X11 by design, not a remnant of the new v3
     image. `tit/gui/nifti_viewer_tab.py`'s own Freeview-launch removal (r-reconcile item 7,
     already landed) is the one place inside `tit/gui/` this program *did* touch — that tab's whole
     purpose was launching an external viewer, unlike these four files where it is one auxiliary
     button inside a larger Qt tab. Rewriting four Qt widgets' subprocess-launch UI is a large,
     separate, out-of-scope change for a legacy path the program's own docs say it is not touching;
     flagged here rather than silently left. `tit/server/routes/system.py:66`'s `"gmsh"` process
     keyword is consistent with this — the system monitor still needs to watch for a process this
     still-live Qt path can spawn.
   - **SimNIBS/mesh-format-internal Gmsh references** (per the brief's own carve-out): `tit/sim/{base,
     config,utils}.py`'s `open_in_gmsh` (a SimNIBS API field, hardcoded `False`, "Never auto-launch
     GUI"), `tit/opt/flex/builder.py`'s same field, `tit/tools/{gmsh_opt,nifti_to_mesh}.py` and
     `tit/blender/{utils,region_exporter}.py` (`.msh`/`.opt` file generation — SimNIBS's native mesh
     format, not a "launch Gmsh" feature), `tit/analyzer/visualizer.py` (writes a `.msh.opt` file),
     `tit/tools/electrode_overlay.py` (documents how Freeview reads an overlay's alpha channel — a
     NIfTI format convention, true regardless of D3), `tit/reporting/reportlets/references.py`
     (the Geuzaine/Remacle Gmsh citation for HTML reports) and
     `desktop/src/renderer/pages/help/AcknowledgmentsTab.tsx`'s matching citation (flagged as "should
     stay" in `w5-viewer-notes.md` §5 already).
   - **Accurate historical/explanatory comments already documenting D3's outcome, not contradicting
     it**: every hit inside `desktop/src/renderer/pages/{viewer,results,analyzer,optimizer-flex}/**`
     and `desktop/src/{main/stack.ts,shared/compose.ts}` ("X11 is gone (decision D3)", "Freeview and
     Gmsh are gone (D3)", etc.) — these are the *correct* record of the removal, not a remnant of it.
   - **The deprecated `freeview_args` field and `tit/server/routes/viewers.py`'s `POST /api/view/args`
     info route** — `tit/server/schemas.py`'s field comment and the route's own module docstring both
     already say, accurately, "no route launches Freeview any more (there is no X11 in this
     runtime)" / "kept for one release". Confirmed `desktop/src/renderer` has no caller of
     `/api/view/args` any more (only the generated `schema.d.ts` comment mentions it). This is real,
     unreferenced dead code — but it is *documented* dead code that does not contradict D3 (it
     documents D3), not "user-facing" (an unused backend route, no UI string), and removing it would
     touch test files (`tests/test_viewspec*.py`) outside this lane's clean 8-item scope under a
     60-minute time box. Flagged here for a lane that owns `tit/server/routes/**`/`tests/test_viewspec*`
     to actually delete once the "one release" grace period is up, rather than removed as a
     drive-by here.

## Fixes required to close the GATE that weren't named in the 8 items

The brief's GATE requires the **full** `npm run e2e` suite green, and two pre-existing failures
(unrelated to the fake-embed fix, both regressions from lanes concurrent with or preceding this
one — the RoiPicker/ResultsPanel rename in `r-reconcile-notes.md` item 9, and the `viewer-dev`
deletion in `w5-viewer-notes.md` item 6) blocked it:

- **`tests/e2e/analyzer.spec.ts:183`** asserted `getByRole("button", { name: "Open in Freeview"
  })` visible and `"Open in Gmsh"` absent. `ResultsPanel.tsx` (r-reconcile item 9) already replaced
  both buttons with one "Open in viewer" gated on `msh || nifti` — the test was simply never
  updated for that rename. Fixed to assert the one real button; the stale "no Gmsh button" negative
  assertion (meaningless now that there is no Gmsh button to accidentally have) was dropped.
- **`tests/e2e/gallery.spec.ts:92`** navigated to a page id `"viewer-dev"` labelled "Viewer engine"
  — W5 deleted `pages/viewer-dev/**` entirely (un-vendoring the bundled engine) but this spec
  (outside W5's own owned test files, which were `viewer{,-real}.spec.ts`/`results.spec.ts`) was
  never retargeted, so the palette timed out looking for a page that no longer exists. Retargeted
  the same geometry/scroll/status-bar assertions at the real "Viewer" page (`pages/viewer`, which
  now carries `layout: "full-bleed"`), swapping `.viewerdev`/`viewer-dev-status` for
  `.viewer-page`/`viewer-source-bar`, and `status-renderer` (which the fake embed's `ready` message
  never populates — it carries no `caps.renderer`) for `status-space` (which resolves to
  `"subject"` the instant the store attaches, per `viewerStatus.ts`'s `IDLE` fallback, independent
  of what the embed under test reports).
- **A real CSS bug the retargeted geometry test then caught**: `.page-layout-full-bleed`
  (`ui/components.css`) canceled `.shell-content`'s padding with `margin: calc(var(--page-pad) *
  -1)` on all four sides, but left `.page-layout`'s own `height: 100%` untouched. `height: 100%`
  resolves against the parent's *content-box* height (i.e., already excluding both top and bottom
  padding) — a negative margin repositions a box, it does not grow a fixed (non-`auto`) height to
  fill the space its top edge moved into. Width has no equivalent problem: an unset `width` is
  `auto`, and an auto-width block *does* expand to absorb negative margins on both sides, which is
  why the page's left/right edges already landed exactly on `.shell-content`'s edges. Measured with
  a temporary `getComputedStyle`/`getBoundingClientRect` dump inside the test (removed after):
  `.shell-content` content height 756px (804px border-box − 2×24px padding), `.page-layout`'s own
  computed height already exactly 756px — so the page's bottom edge sat a full `2 × --page-pad`
  (48px) above `.shell-content`'s own bottom edge, a real, visible gap of exposed shell background
  under the Viewer page, contradicting DESIGN.md's own "no imaging tool puts a 24px margin around
  its render panes" sentence two lines above the bullet this lane rewrote in item 6. Fixed with one
  added declaration on `.page-layout-full-bleed`: `height: calc(100% + var(--page-pad) * 2)`
  (comment in the file explains the box-model asymmetry and why the width side never needed it).
  Confirmed this only takes effect ≥1100px width — the existing `@media (max-width: 1099px)` block
  re-declares `.page-layout { height: auto }` (unscoped, later in the source, same specificity) for
  the stacked layout, so nothing below that breakpoint is touched. Re-verified: `npm run typecheck`
  / `lint` / `vitest run` / `build` all still clean after the CSS change; full e2e re-run green
  (below).
- (Encountered mid-investigation, not a real bug) `viewer.spec.ts:129`'s cursor assertion looked
  flaky on one intermediate run — traced to running `npx playwright test` directly against a stale
  `out/renderer` build (no `pree2e` hook outside `npm run e2e`) rather than any real regression;
  green on every run once the build was current.

## Gates — commands and results

```
$ python3 -m pytest -q                                              # host, py3.14
3150 passed, 18 skipped in 34.32s                                    # +1 vs. lane R's 3149
                                                                       # baseline: the new HEAD test

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q \
    tests/test_server_skeleton.py tests/test_viewspec.py tests/test_files_routes.py
113 passed in 2.97s / 3.13s (re-run)                                  # 0 failed

$ python3 -m black --check tit/server/static.py tests/test_server_skeleton.py tit/constants.py
(after `black tests/test_server_skeleton.py` — one file needed reformatting, applied)
All done — 3 files would be left unchanged

$ cd desktop && npm run typecheck
tsc --noEmit -p tsconfig.node.json && tsc --noEmit -p tsconfig.web.json    # 0 errors, both configs

$ npm run lint
✖ 3 problems (0 errors, 3 warnings)     # same 3 pre-existing react-compiler warnings as R's/W5's
                                        # baseline (ui/DataTable.tsx, ui/VirtualList.tsx,
                                        # pages/preprocess/index.tsx's form.watch()); 0 errors

$ npx vitest run
Test Files  45 passed (45)
     Tests  468 passed (468)             # 0 failed (was 2 failed / 43 passed per R's/W5's baseline)

$ npm run build
✓ built in 1.88s (exit 0)

$ TIT_E2E_RUN_ID=r2-final-<n> bash scripts/e2e-quiet-check.sh npm run e2e
Running 52 tests using 1 worker
  1 skipped   (viewer-real.spec.ts -- correctly skipped, no TIT_TETRAVOX_EMBED_DIR set)
  51 passed (4.0m)
e2e-quiet-check: command exited 0
e2e-quiet-check: no Electron/Chromium window reached the screen.
e2e-quiet-check: PASS
```

**Full e2e verdict: 51 passed, 1 skipped, 0 failed. Quiet-check: PASS** (no Electron/Chromium
window reached the screen on any run this session).

## Files touched this session

- `desktop/tests/e2e/fixtures/fake-embed/{index.html,fake-embed.js}` (new)
- `desktop/src/renderer/app/jobs-rail/api.ts`
- `desktop/src/renderer/pages/preprocess/{index.tsx,PARITY.md}`
- `desktop/tests/unit/{preprocess-defaults.test.ts,shell-subject.test.tsx}`
  (`forms-ajvResolver.test.ts` needed no edit — verified, not modified)
- `desktop/src/renderer/pages/_shared/roi/RoiPicker.tsx`
- `desktop/src/renderer/pages/optimizer-flex/index.tsx`
- `desktop/tests/e2e/optimizer-flex.spec.ts`
- `desktop/src/renderer/app/viewerStatus.ts`
- `desktop/DESIGN.md`
- `tit/server/static.py`
- `tests/test_server_skeleton.py`
- `desktop/src/renderer/dev/Gallery.tsx`
- `tit/constants.py`
- `desktop/eslint.config.mjs` (new override so the fake-embed fixture's browser globals lint clean)
- `desktop/tests/e2e/gallery.spec.ts` (gate fix, not one of the 8 items — see above)
- `desktop/tests/e2e/analyzer.spec.ts` (gate fix, not one of the 8 items — see above)
- `desktop/src/renderer/ui/components.css` (gate fix — real CSS bug the retargeted gallery test
  caught, see above)

## needs_from_other_lanes

- **`tit/server/routes/viewers.py`'s `POST /api/view/args`** (and the `freeview_args` field it and
  `GET /api/view/{kind}` both still populate) is real, unreferenced dead code — no caller in
  `desktop/src/renderer` any more. Left in place deliberately (see the audit section above); a lane
  that owns `tit/server/routes/**` should delete it once the "kept for one release" grace period
  documented in `tit/server/schemas.py` has passed, updating `tests/test_viewspec*.py` alongside.
- **The whole PyQt5 `tit/gui/**` X11-forwarded CLI path's Freeview/Gmsh launchers** (`analyzer_tab.py`,
  `ex_search_tab.py`, `flex_search_tab.py`, `components/roi_picker.py`) still spawn `freeview`/`gmsh`
  subprocesses. Deliberately out of scope here (see the audit section) — flagged in case a future
  decision retires that legacy path too, at which point these become real removals rather than a
  documented, working, separate deployment.
