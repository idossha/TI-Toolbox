# Lane VW — R5: Viewer selection is explicit, loading is a command

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-05.
Plan of record `desktop/IMPLEMENTATION_PLAN.md` R5; lane rules `dev/notes/v3-overview-batch-viewer/LANES.md`.
**Nothing committed, staged, stashed, checked out or reverted.** Every Playwright run was offscreen
(macOS default in `tests/e2e/_helpers.ts::offscreenEnv`; no window reached the screen). The shared
container `ti-toolbox-fad740e5-tit-1` was used read-only over HTTP — never restarted or recreated —
and `/api/health` answered 200 after the `tit/` edits.

---

## 1. What the page does now

Two selections, not one.

| | what it is | who writes it |
|---|---|---|
| `draft` | what the source bar is showing | every selector; the deep link; the shell's subject switcher |
| `loaded` | what the embed is drawing | **only** a successful Load |

- The source bar gained a **Type** selector (`subject`, `simulation`, `analysis`, `group`,
  `custom file`) and renders only the selectors that type takes:
  `subject` → subject, atlas, space; `simulation` → subject, simulation, field, space;
  `analysis` → subject, simulation, analysis, ROI; `group` → field, ROI; `custom` → path.
  The list lives in one place (`controlsFor` in `pages/viewer/lib.ts`), and the request builder
  strips everything not in it — a leftover simulation from an earlier draft can never ride along on
  a `subject` view.
- **Any selector edit only dirties the draft.** No view request, no `load` message, no change on
  screen. Catalog queries (subjects, simulations, analyses, atlases) still run: they fill menus.
- **Load** validates (`validateSelection`; an incomplete draft is refused *before* the wire and is
  not an error state), snapshots the draft as `loaded`, issues exactly one `GET /api/view/{kind}`
  and posts exactly one scene to the retained iframe.
- **A failed Load keeps the previous scene.** The error is a strip above the canvas keyed to the
  *attempted* selection (`failure.key === draftKey`), so drafting back to something that did load
  clears it without refetching. The viewport keeps the last good picture — throwing away a scene
  someone is reading because the next request 500'd is the expensive mistake this reverses.
- **Deep links prefill only.** Results' own "Open in viewer" fills the controls and loads nothing.
- **Reload is unchanged in meaning and now honest in scope**: it remounts the iframe and re-sends
  the **loaded** scene, never the draft.
- The status bar's `space` cell reports the loaded selection's space, not the draft's — it labels
  coordinates that are on screen.

## 2. Contract: optional `atlas` on the frozen view API

`GET /api/view/{kind}` gains one optional query parameter, `atlas`. `tit.viewspec.build_view`
honours it in the two branches that build an atlas layer (`subject`, `group`).

- **Absent preserves current behaviour exactly** — asserted whole-spec, not by eye
  (`test_atlas_absent_keeps_the_servers_own_choice`).
- **An unknown id falls back to the server's own choice** rather than 404-ing the whole view: an
  atlas a subject no longer has is a stale bookmark, not a reason to answer with no picture.
- The Viewer's atlas menu asks the catalog for `kind=subcortical` — the catalog's word for the
  **voxel** atlases, i.e. the ones that can be a ViewSpec layer. The cortical entries are
  FreeSurfer `.annot` surface parcellations; offering them would give a choice that silently
  resolves back to the default.

Contract files touched: `contracts/openapi.v1.yaml` (the view section only), regenerated
`contracts/openapi.v1.json` via `python3 dev/build_contract.py`, regenerated
`desktop/src/renderer/api/schema.d.ts` via `pnpm run gen:api`, and a new
`contracts/SCHEMA-CHANGES.md` entry. `contracts/tetravox-viewspec-v2.schema.json` is **unchanged**:
the atlas is a request parameter, and what comes back is an ordinary layer the viewspec already
describes — nothing new travels in the scene document.

## 3. Files changed

Desktop:
- `desktop/src/renderer/pages/viewer/index.tsx` — draft/loaded state, Type + conditional selectors,
  Load, failure retention, reload re-send, deep-link prefill.
- `desktop/src/renderer/pages/viewer/lib.ts` — the pure half: `ViewerSelection`, `controlsFor`,
  `requiredControls`, `validateSelection`, `viewQuery`, `selectionKey`, `sameSelection`,
  `selectionFromDeepLink`, `hasViewerDeepLink`; `readDeepLink` extended with
  `analysis`/`atlas`/`roi`/`path`.
- `desktop/src/renderer/pages/viewer/api.ts` — `ViewQuery.atlas`; `getAtlases` asks for the voxel
  atlases.
- `desktop/src/renderer/pages/viewer/viewer-page.css` — the wider (horizontally scrolling) source
  bar, the path input, the load-error strip.
- `desktop/tests/unit/viewer-page.test.ts` — the selection model's unit coverage (25 tests).
- `desktop/tests/e2e/viewer.spec.ts` — helpers renamed by control instead of index; six new R5 gate
  tests; the space-cell test now proves the cell follows the *loaded* space.
- `desktop/tests/e2e/viewer-real.spec.ts` — same two-act flow (draft, then Load).
- `desktop/tests/mock-server/server.mjs` — `kind=subject` builds an atlas layer, and honours `atlas`.

Server/contract:
- `tit/viewspec.py` — `build_view(..., atlas=...)`, `_subject_atlas_layer(..., requested)`,
  `_default_mni_atlas_path(requested)`.
- `tit/server/routes/viewers.py` — the `atlas` query parameter.
- `tests/test_viewspec.py` — five new tests.
- `contracts/openapi.v1.yaml`, `contracts/openapi.v1.json`, `contracts/SCHEMA-CHANGES.md`,
  `desktop/src/renderer/api/schema.d.ts`.

The viewer store, `EmbedFrame`/`TetravoxFrame` and the embed protocol are **untouched** — the
protocol was already an explicit-command interface (`loadScene` posts one `load`), which is exactly
why R5 needed no protocol change.

## 4. Gate

Plan R5's gate, clause by clause, and the command that proves it.

| Gate clause | Where | Result |
|---|---|---|
| Initial navigation issues zero view requests and zero scene loads | e2e "navigating to the Viewer and editing the draft…" | PASS |
| Each draft edit issues zero view requests and zero scene loads | same test — 4 edits across 3 view types | PASS |
| One Load issues exactly one request with the visible draft values | e2e "one Load issues exactly one view request…" | PASS |
| …and exactly one scene-load message | same test (`__sceneLoads` counted inside the embed window) | PASS |
| Atlas A and Atlas B produce distinguishable requested ids | e2e "atlas A and atlas B…" + unit `viewQuery` | PASS |
| Failed Load keeps the previous scene identity | e2e "a failed Load keeps the previous scene…" | PASS |
| Deep link fills controls, zero view requests before Load | e2e "a deep link fills the controls…" | PASS |

Counting method, stated plainly because it is the whole gate:
- **View requests** — `page.on("request")` filtered to `/api/view/`, collected into an array and
  asserted by `toEqual([])` / `toHaveLength(1)`. Catalog requests are deliberately not filtered out
  of existence; they simply are not view requests.
- **Scene loads** — a listener installed *inside* the embed iframe counts `{tvx:1,type:"load"}`
  messages. The receiving window is the honest place to count a host→embed message, and the fake
  embed fixture needed no change for it.

### Commands and their actual output

```
$ python3 -m pytest tests/test_viewspec.py -q
36 passed in 0.18s

$ python3 -m pytest tests/ -q -k "viewspec or view or catalog_v1"
147 passed, 3568 deselected, 1 warning in 4.34s

$ cd desktop && npx vitest run
Test Files  79 passed (79)
     Tests  889 passed (889)          (viewer-page.test.ts: 25)

$ cd desktop && pnpm run lint
4 problems (0 errors, 4 warnings)     — none in this lane's files; ScenePane.tsx, preprocess/index.tsx,
                                        ui/DataTable.tsx, ui/VirtualList.tsx (react-compiler library warnings)

$ cd desktop && pnpm run pree2e && npx playwright test tests/e2e/viewer.spec.ts
Running 18 tests using 1 worker
  ✓  13 › navigating to the Viewer and editing the draft issues zero view requests and zero scene loads (4.7s)
  ✓  14 › one Load issues exactly one view request, carrying the values the bar is showing (4.7s)
  ✓  15 › atlas A and atlas B produce distinguishable requested ids (4.8s)
  ✓  16 › a failed Load keeps the previous scene and attaches the error to the attempted selection (5.0s)
  ✓  17 › a deep link fills the controls and still issues zero view requests before Load (4.8s)
  ✓  18 › Reload re-sends the loaded scene and never loads the draft (5.0s)
  18 passed (1.6m)
```

(One earlier iteration of this spec failed twice on `embedFrame()` racing the iframe mount; the
helper now polls for the frame. The run above is after that fix, and is the run of record.)

Route-import guard, after the `tit/` edits: `python3 dev/route_import_guard.py` →
`20 route module(s) clean`; `GET /api/health` on the shared container → `200`.

`pnpm run typecheck` is **red in this tree, in other lanes' files only** — `pages/overview/index.tsx`
(6), `pages/_shared/run/jobGroups.ts` + `pages/preprocess/api.ts` (`overwrite` missing on the job
group request), `tests/unit/subjects-readiness.test.ts` (imports a deleted module). Grepping this
lane's files out of the output leaves nothing: `npx tsc --noEmit -p tsconfig.web.json | grep viewer`
is empty. Not mine to fix (LANES.md rule 2).

### Real container (Dataset 000, sub-ernie)

`ti-toolbox-fad740e5-tit-1`, port 8765, token from `docker inspect`. Atlas ids come from the same
catalog the menu reads, and the layer that comes back is the one asked for:

```
GET /api/catalog/atlases?subject=ernie&space=subject&kind=subcortical
  → aparc.DKTatlas+aseg.mgz, aparc.a2009s+aseg.mgz, lh/rh.hippoAmygLabels-T1.v22.mgz,
    ThalamicNuclei.v13.T1.mgz, labeling.nii.gz

GET /api/view/subject?subject=ernie                              → [T1.nii.gz, segmentation/labeling.nii.gz]
GET /api/view/subject?subject=ernie&atlas=aparc.DKTatlas+aseg.mgz
                                                                 → [T1.nii.gz, freesurfer/.../aparc.DKTatlas+aseg.mgz]
GET /api/view/subject?subject=ernie&atlas=NotAnAtlas             → [T1.nii.gz, segmentation/labeling.nii.gz]   (fallback)

GET /api/view/subject?subject=ernie&space=mni                    → [T1_ernie_MNI.nii.gz, CIT168_labeling_MNI152NLin2009cAsym.nii.gz]
GET /api/view/subject?subject=ernie&space=mni&atlas=MorelMNI152_labeling_1mm.nii.gz
                                                                 → [T1_ernie_MNI.nii.gz, MorelMNI152_labeling_1mm.nii.gz]
```

A vs B are distinguishable on the real server, absent and unknown are byte-identical to the previous
behaviour, and every id the menu offers is one `build_view` accepts.

## 5. Open items

1. **Cortical (`.annot`) atlases are not offerable in the Viewer.** They are surface parcellations,
   not volumes, so the menu filters them out (§2). Overlaying one needs a surface layer in the
   ViewSpec — a separate piece of work, and a real one for anyone who wants DK40 on the 3D pane.
2. **`analysis` and `custom` views show no space control** because `build_view` builds both in
   subject space regardless. If either ever gains an MNI form, `controlsFor` is the one line to
   change.
3. **The `group` type is reachable from the Type menu for the first time.** Its ROI selector reuses
   the subject's atlas list, which is wrong for a project with no selected subject; it renders as
   "None" there rather than misleading anyone, but a group-scoped catalog call would be better.
4. **A route change was NOT needed in `app/`** — Results already navigates to `/viewer?…` and the
   page reads both the router's and the document's query string. No `app/` diff to hand over.

## 6. Proposed record entries (consolidation lane lands these)

### Contract amendment (`docs/ARCHITECTURE.md`, view API)

> `GET /api/view/{kind}` accepts an optional `atlas` query parameter naming which atlas overlay the
> scene should carry: an id from `GET /api/catalog/atlases` for the same subject and space, or a
> bundled MNI atlas's basename. Omitting it preserves the server-selected atlas exactly
> (`segmentation/labeling.nii.gz` when present, else the first listed voxel atlas; `DEFAULT_MNI_ATLAS`
> in MNI space), and an id that resolves to nothing available falls back to that same choice rather
> than failing the request. The parameter changes which layer is built; it adds nothing to the
> ViewSpec or scene document, so `contracts/tetravox-viewspec-v2.schema.json` is unchanged.

### Decision entry (`docs/DECISIONS.md`)

> **2026-09-05 — The Viewer loads on command, not on selection.**
> The Viewer keeps a `draftSelection` (what the source bar shows) separate from a `loadedSelection`
> (what the embed is drawing). Editing a selector changes only the draft; **Load** validates it,
> snapshots it, issues exactly one view request and posts exactly one scene to the retained iframe.
> A failed load keeps the previously loaded scene on screen with the error attached to the attempted
> selection; deep links prefill the draft and never auto-load; Reload remains iframe/runtime
> recovery for the loaded scene.
> *Why:* deriving the request from the controls meant every incidental change — a subject switch in
> the shell, a space toggle, a half-finished pick — tore down a scene that had cost minutes to load,
> and a transient server error replaced the picture with an error card. Explicitness costs one click
> and buys back the two things a viewer must never lose: the image you already have, and knowing
> which selection produced it.
> *Also decided:* `GET /api/view/{kind}` takes an optional `atlas`; absent is the previous behaviour
> and an unresolvable id falls back to it rather than 404-ing (see the contract amendment).

### `desktop/DESIGN.md` §10 rewording

Replace the source-bar bullet and its figure with:

> ```
> ┌──────┬────────────────────────────────────────────────────────────┐
> │ rail │ TYPE ⟨Simulation ▾⟩ SUBJECT ⟨ernie ▾⟩ SIMULATION ⟨… ▾⟩     │ 40  source bar
> │  56  │ FIELD ⟨TI_max ▾⟩            SPACE ⟨Subject│MNI⟩ [Load] [⟳] │
> │      ├────────────────────────────────────────────────────────────┤
> │      │  <iframe src="/tetravox/">   1224 × 664 at 1280 × 800      │
> └──────┴────────────────────────────────────────────────────────────┘
> ```
>
> - **The source bar owns the *draft* selection; Load owns the request.** A view Type selector plus
>   the selectors that type takes (subject, simulation, analysis, field, atlas, space, ROI, custom
>   path), then **Load**, then the reload `IconButton`. Editing a selector changes nothing on screen;
>   Load performs exactly one `GET /api/view/{kind}` and hands the embed exactly one scene. The bar
>   scrolls horizontally rather than growing a second row — the stage's height belongs to the canvas.
> - **A failed load keeps the picture.** The error is a strip above the canvas naming the selection
>   that failed; the last successfully loaded scene stays in the viewport. Reload re-sends *that*
>   scene, not the draft.

### `desktop/DESIGN.md` §9 (retained pages) rewording

Replace "An explicit Results link may select a new scene in the Viewer" with:

> A Results link prefills the Viewer's draft selection; the scene changes only when Load is pressed.
> Plain navigation resumes both the draft and the loaded scene.

### Roadmap line

> v3.0.0 — Viewer: explicit draft/Load selection with a view-type-aware source bar; optional `atlas`
> on `GET /api/view/{kind}`.
