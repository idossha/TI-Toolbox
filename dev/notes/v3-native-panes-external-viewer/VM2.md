# Lane VM2 — the file list is the scene

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06.
Follows **VX** (the viewer became an external app and this page a data selector) and **VM** (that
page became a composition panel). Read those first; this note is the correction to VM.

Maintainer, on VM's three screenshots: **"too much."** Then, precisely:

> Remove the LAYERS section (all per-layer cards), the LAYOUT & CAMERA section, and the ALSO OPEN
> checkboxes entirely … Keep only **Source** and one **"What will open"** list — and make that list
> *editable* … The list is the whole scene: Open in Tetravox writes exactly these files.

Every Playwright run was offscreen; **no window reached the screen and Tetravox was never
launched**. Nothing was stashed, reverted or checked out. The shared container was used over HTTP
and left as found.

---

## 1. Why this is the better page, not just the smaller one

VM's mistake was reading "the viewer opens in its own window, so this page has room" as *this page
should therefore hold more*. It has room because there is **less for it to do**. The composition
panel put two things on screen that belong in different places:

- **How a file should look** — opacity, colormap, threshold, layout, camera, convention. This is a
  judgement about the *data*: a percentile window on a TI field so the picture is not of its
  outliers, a LUT and `nearest` on a label volume so the labels are labels, a mesh added hidden
  because the file is 64 MB. `tit/viewspec.py` already makes all of those, correctly, and Tetravox
  has an inspector, its own window and the reader's full attention for changing them. A second
  place to set them is a second place for them to be wrong.
- **Which files are in the scene** — which the old page could not express *at all*. The view type
  decided, and a person who wanted the T1 plus this simulation's field plus last week's atlas had
  no way to say so.

So VM2 removes the first and makes the second direct. What is left is the two questions the page
is actually for: where does the scene come from, and what is in it.

## 2. What was built

**The server keeps VM's `overrides` plumbing.** It is additive, tested and costs nothing; nothing
on the page sends it, and the next caller that wants a camera preset does not have to re-derive
it. What VM2 adds is `files`.

| File | What |
|---|---|
| `tit/viewspec.py` | `build_view(..., files=)` — **authoritative when given**: those datasets, that order, nothing the view type would otherwise have contributed. `_layers_from_files` re-jails every path, drops one that does not resolve or does not exist, de-duplicates, and keeps a path the view type already produced with **exactly that view type's layer settings** (`copy.deepcopy` of the layer dict). `_layer_for_path` describes an *added* file from its name alone. `viewer_candidates()` — the "+ Add…" catalogue. |
| `tit/server/routes/viewers.py` | `files` on `POST /api/view/open`; `GET /api/viewer/candidates`; `_scene_files` rewritten to zip layers with datasets and report **both path languages**. |
| `tit/server/schemas.py` | `ViewerSceneFile.container_path`. |
| `contracts/` | `files` on the request, `container_path` on the row, `ViewerCandidate`, the candidates path, `ViewerPreset.files`; `.json`, `schema.d.ts` and the mock fixture regenerated. |
| `tests/test_viewspec_overrides.py` | +11 tests (38 total in the file). |
| `pages/viewer/{index.tsx,lib.ts,api.ts,viewer-page.css}` | Rewritten: two cards and a footer. `files: string[] | null` is the whole new state. |
| `desktop/DESIGN.md` §10 | Rewritten again, for the page that exists. |
| mock server, `viewer.spec.ts`, `page-memory`, `smoke`, `viewer-page.test.ts` | see §3. |

### 2.1 Three decisions worth the words

**`files === null` is "the view type's own set", not a copy of it.** A copy goes stale the moment
the source changes and the page then shows yesterday's answer beside today's selector values.
`null` also gives the Reset link its exact meaning — *let the source decide again* — which is why
the link disappears when it is pressed.

**The list resolves through the endpoint that opens it, with `dry_run`.** Editing a row costs one
request and re-resolves. That is not a compromise, it is the feature: the server is the one that
knows a path is jailed out, missing or a duplicate, and a row **disappearing** is a truer answer
than a row the client kept and the scene did not.

**Both path languages on every row.** `path` is host-facing (what a person can check, what the
scene carries); `container_path` is what goes back in `files`. A row that reported only the host
path could not be handed back to a server that jails container paths — and the failure would have
been an empty list with no error anywhere.

## 3. Gate

| Command | Result |
|---|---|
| `pnpm run typecheck` | clean |
| `npx eslint src tests` | 0 errors, 3 pre-existing warnings |
| `npx vitest run` (viewer + mock-server) | 56 passed; full run clean but for the pipeline lane's own `pipeline-graph` failure |
| `pnpm run build` / `pnpm run pree2e` | clean |
| `python3 -m pytest tests/test_viewspec*.py tests/test_view_open.py -q` | **109 passed** |
| `python3 dev/route_import_guard.py` | 20 route modules clean |
| `bash scripts/e2e-quiet-check.sh npx playwright test viewer smoke page-memory --workers=1` | **39 passed, 2 failed** — both in the *optimizer* page's DOM (`#optimizer-run-name`) and a run-page scroll, another lane's in-flight work; every `viewer.spec.ts` test passed |

Offscreen: *"no new Electron/Chromium window reached the screen."*

### 3.1 The e2e assertions

Each one reads the **written scene** — the Open's response body is byte-for-byte what went to disk.

- *the page is a source card and one file list — nothing else* — VM's `viewer-section-{layers,
  layout,extras}` are asserted to have **count 0**. Gone, not collapsed.
- *removing a row removes that dataset from the scene the server writes.*
- *adding the atlas puts it in the list and in the written scene.*
- *reordering the list reorders the scene's layers* (through ↑/↓, not drag — a list you can only
  reorder with a mouse is a list some people cannot reorder, and Playwright's drag is the flakiest
  thing in this suite).
- *Reset puts the view type's own list back*, and the link goes with it.
- *editing the list costs no scene and no launch until Open* — dry runs > 0, writes 0, launches 0;
  then one Open carrying the edited list in order.
- *changing the source resets the list to that source's own files.*
- *a preset saves the edited list and restores it without opening anything.*
- *the Recent list remembers what was opened and restores it.*
- `page-memory`: a removed row survives a tab switch, like the selection always did.
- Screenshot: `desktop/tests/e2e/artifacts/viewer-menu-v2.png`, 1440, full page.

### 3.2 Real — the live container, `sub-ernie`

```
default list (dry run, nothing written):
  T1.nii.gz 13 109 495 · L_Insula_TI_subject_TI_max.nii.gz 17 450 987 ·
  grey_… 3 113 933 · white_… 2 628 530 · grey_L_Insula_TI.msh 63 926 663

GET /api/viewer/candidates?subject=ernie&simulation=L_Insula
  33 offers — Head model 5 · Surfaces 6 · Atlases 6 · Simulation volumes 10 · Simulation meshes 6

POST /api/view/open  files=[<field>, <T1>, <labeling.nii.gz>]     (reorder + drop 3 + add 1)
  datasets   ['L_Insula_TI_subject_TI_max.nii.gz', 'T1.nii.gz', 'labeling.nii.gz']
  layers     ['TI_max (volume)', 'T1', 'Atlas']
  added atlas: interpolation 'nearest', LUT sidecar present  → the same treatment a default
               atlas layer gets, from the file name alone
  rows carry both path languages : True
  schema errors 0 · missing files [] · scene 4 633 bytes on the host

absent `files` == the pre-VM2 document, byte for byte : True
```

The 64 MB mesh in that first list is the argument for putting sizes on the rows: it is exactly the
fact a person wants before another window opens, not after it has spent thirty seconds loading.

## 4. Commits, and where this lane's content actually landed

`e3f7b945` — **all of VM2's content**. It is titled
`feat(pipeline): a Subjects node is the source, and a wire is refused when its subjects are not
ready`, which is the concurrent pipeline lane's message: that lane ran a repository-wide `git add`
while this lane's files were staged and swept every one of them in (VX §3 recorded the same hazard
in the same worktree). The diff is correct and complete — `tit/viewspec.py` +246,
`pages/viewer/index.tsx` ±663, `viewer.spec.ts` ±202, `tests/test_viewspec_overrides.py` +180 and
the rest — but the attribution is wrong, and this line is the record of it.

`<this commit>` — `desktop/DESIGN.md` §10 and this note.

VM's own commits, for the trail: `b48fa120` (server overrides/extras/dry-run), `24566623` (the
composition panel), `8582e57e` (its layer-card density), `fe45107d` (VM.md).

## 5. Open items

1. **Two `page-memory` tests are red on this branch** (`#optimizer-run-name` never appears; a
   run-page scroll comes back 66 instead of 80). Both are the optimizer lane's page and neither
   touches a viewer testid. Flagged, not fixed.
2. **No host file picker exists in this app yet.** "+ Add…" offers the catalogue plus a
   container-path field — the same field `kind: custom` has always used, with the same jail check
   on the far end. When a picker is wired (`window.tit` has no `pickPath` today), `PathInput`'s
   `onBrowse` is where it goes, and this field becomes it.
3. **`_layer_for_path` infers from the file *name*.** A field volume called `mystery.nii.gz` gets
   the heat/percentile treatment, which is the right default for the overwhelming majority of what
   lives in a TI-Toolbox project — but it is an inference, and the honest fix if it ever matters is
   for the person to change it in Tetravox's inspector, which is where layer appearance now lives.
4. **`pages/viewer/PARITY.md`** still describes the embed's gaps; several of its rows are now
   *deliberately not going to be closed on this page* (layer appearance belongs to Tetravox), and
   it wants a pass from whoever owns the parity question.
5. **The `overrides` plumbing has no client.** Kept because it is additive and tested; if it still
   has no caller in six months, deleting it is a five-line change and `test_viewspec_overrides.py`
   says exactly what would be lost.
