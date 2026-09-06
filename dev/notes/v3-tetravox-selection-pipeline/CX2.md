# Lane CX2 — consolidation: seams, records, and the delivery gate (2026-09-05/06)

Plan of record: `dev/notes/v3-tetravox-selection-pipeline-plan.md` (A–D). Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. **Nothing committed, staged,
stashed, checked out or reverted** — and `git stash` was not run in any form (lane PC's own note
records what one cost the shared container mid-FEM). Every Playwright run was offscreen.

## 1. Seams closed

| Seam | What it turned out to be | Files touched |
| --- | --- | --- |
| (a) the Pipeline rail row shifted every ⌘-number | `smoke.spec.ts` asserted the pre-Pipeline map in two places (`⌘6 → results`, `⌘7 → viewer`) and the Help page's Keyboard tab **hard-coded nine rows ending "⌘9 Settings"**, which the ninth rail row made wrong the day it landed. The specs now assert the derived map — ⌘1 Overview · ⌘2 Pre-processing · ⌘3 Simulator · ⌘4 Optimizer · ⌘5 Analyzer · **⌘6 Pipeline** · ⌘7 Results · ⌘8 Viewer · ⌘9 Jobs · **⌘0 Settings** — and `KeyboardTab.tsx` now builds its rows from `enabledPages` exactly as `app/KeyboardSheet.tsx` already did, so a future rail row needs no edit in either. `help.spec.ts` asserts `⌘0`; the stale `⌘9` prose in `registry.ts` and `PARITY.md` is corrected | `tests/e2e/smoke.spec.ts`, `tests/e2e/help.spec.ts`, `src/renderer/pages/help/{KeyboardTab.tsx,PARITY.md}`, `src/renderer/app/registry.ts` (one comment) |
| (b) PC's dynamic-binding write-back (its §7, "the one change this lane needed and did not own") | Landed, but **not** as PC's sketch. PC proposed the resolve step write a `bindings.json` into the *consumer's job directory*, which needs the consumer's job id — and `submit_plan` submits the resolve step *before* the consumer, so that id does not exist yet. Inverted instead: the path is a pure function of `(pipeline, node, port)`, so the **consumer carries it** and no id is needed. `tit/jobs/bindings.py` (new) owns the key and the merge; `plan.py` attaches one descriptor per dynamic port after the config round-trips (so it never reaches a config dataclass); `JobManager._runner_config_path` calls `merge_pipeline_bindings` — one line plus its comment — and admission is provably after every `after` job finished, which is the first moment the file can exist. A resolve step that found nothing leaves the field as the canvas set it | `tit/jobs/bindings.py` **(new)**, `tit/jobs/manager.py`, `tit/pipeline/plan.py`, `tit/tools/pipeline_resolve.py` (docstring), `tests/test_pipeline_bindings.py` **(new, 7 tests)**, `docs/wiki/pipelines.md` |
| (c) SG's `receipt` slot on `PageLayout` | Added as a first-class prop, rendered between `.page-layout-main-scroll` and the action bar — so the receipt is a sibling of the bar, not a last child of the scroller. All four run pages pass it instead of rendering `<Receipt>` inside `RunWork`. `.page-layout-main > .run-receipt { flex: none }`; the CSS comment that described the sticky failure now describes the fix | `src/renderer/ui/Layout.tsx`, `pages/{simulator/index.tsx,optimizer/index.tsx,preprocess/index.tsx,analyzer/AnalyzerPage.tsx}`, `pages/_shared/run/run.css` |
| (d) EL's explicit idle colours vs TX's upstream fix | EL's colours **kept**, as instructed: TX fixed `resolvePoint` in PR #35 (`ebd814b`) so an idle point with no colour of its own now takes `stateColors.idle`, but no release carries an embed asset, and the container still runs the hand-installed 0.4.0 EL measured. A `TODO(tetravox)` on `pointsFromMarkers` cites TX.md and names the condition for removal (a bundle built from 0.3.12+) | `pages/_shared/scene/embedScene.ts` (two comments) |
| (e) contract declarations | **Confirmed, nothing to do.** `contracts/openapi.v1.json` declares all six `/api/pipelines*` paths, `/api/tetravox/policy` and `/ws/tetravox`; `npx vitest run tests/mock-server` is **33/33** (its contract test asserts every declared path is exercised, so a declaration without a mock route fails it). AU's note recorded `contract.test.ts` red on PC's eight pipeline operations — that was mid-flight and is green now | — |
| (f) PC's open item 7 (no job re-adoption across `--reload`) | **Not implemented**, as instructed. Recorded in `docs/ROADMAP.md`'s new "Known follow-ups" table with its cause (the manager keeps a child pid in memory only), the escape hatch (`POST /api/jobs/{id}/force`, which lands the job in `lost`) and the fix that is already half-built (`status.json` persists the `pid`/`create_time` pair for exactly this) | `docs/ROADMAP.md` |
| (g) other cross-lane red | None left from this program. EL's note reported `scene-pane.spec.ts:81` and `guide.spec.ts:169` failing against SG's mid-flight `SubjectsField` rewrite, and `simulator.spec.ts` failing on a `subjects-select-all-button` testid that did not exist yet; all three settled before this lane ran and are green in the full suite below. AU's `settings.spec.ts` lint error and the seven `tetravox-card` unit failures were likewise mid-flight and are gone | — |

**Negative controls, so the seams are tested and not just written.** Commenting out
`merge_pipeline_bindings` in `_runner_config_path` makes exactly one of the new tests fail
(`test_the_manager_merges_the_resolved_value_into_the_runners_config`, `assert [] == ['L_Insula_mean']`)
and the other six stay green — the test tests the hook, not the fixture.

### A note on where the write-back lives

`tit/jobs/bindings.py`, not `tit/pipeline/`, because `tit.pipeline` already imports
`tit.jobs.spec` and the job manager must not import a pipeline module to run an ordinary job. The
key has one definition, in `tit.jobs`, and `tit.pipeline.plan` re-exports it because it is the module
that writes it.

## 2. Records landed

| File | Entry |
| --- | --- |
| `docs/requirements/2026-09-05-tetravox-selection-pipeline.md` | **new** dated intent document: the six asks verbatim from the plan's "Maintainer asks", decisions A–D each with its gate test, and a closing list of what the decision log now settles. It states that it follows, and does not reverse, the first 2026-09-05 requirements |
| `docs/ARCHITECTURE.md` | **new §7**, in four numbered parts. §7.1 the Tetravox update channel — two delivery paths and one rule (protocol range + named features, never a version), the three release-asset names and their formats, the manifest-asset pre-check, the cache/policy/provenance rules, `/ws/tetravox`, and AU's **compatibility matrix**. §7.2 the points-layer electrode contract (`dotRadiusPx`, `labelColorSource`, `EmbedPoint.radiusPx`; point colour beats `stateColors`; an idle point is never state-coloured; no `name` means no label; the dot pass is 2-D-only before 0.3.12). §7.3 pipelines — `pipeline.schema.json`, "a pipeline run is one job group", the closed port set, validation answering rather than throwing, the static-versus-`resolve` binding rule **including the admission write-back**, export as a pure function, and the non-goals. §7.4 the selection grammar, the receipt slot and the derived ⌘-number. §§1–6 untouched |
| `docs/DECISIONS.md` | **eight** appended entries in the file's existing Decision/Why/Alternatives-rejected shape, deduping the five lanes' overlapping proposals: *the release index is the GitHub Releases API and the pin is a protocol range*; *updates install themselves by default, and "newer" means newer than what we installed* (carrying rollback, the policy's location and the `/ws/tetravox` choice); *electrodes are dots whose colour is their whole state* (carrying Okabe-Ito and the "no ring, asserted not assumed" rule); *one selection grammar, with the receipt as the confirmation*; *a pipeline is a job group, not a workflow engine*; *React Flow is the canvas, `nbformat` is an optional extra*; *notebook export is public-API-only and carries the document in its metadata*; *Settings' ⌘-number is derived* |
| `docs/ROADMAP.md` | the new requirements linked; **six rows** appended to "What is next" (A, A6, B, C, D and this consolidation gate, each with the evidence that proves it and the lane note that records it); a **new "Known follow-ups" table** of ten items with why each is not done and where it is described — per-point `radiusPx`, hover colour, removing the explicit idle colour, notebook import, job re-adoption across a reload, a retry endpoint, the saved-pipeline form-state reader, JSON-edited node kinds, SG's two `PageLayout`/`SelectionList` follow-ups, and `tags` on `JobStatus` |
| `tracks/active/v3-electron-gui.md` | ADR **row 26**, "Tetravox currency, electrode dots, one selection grammar, pipelines (2026-09-05)", in the table's three-column form, quoting the maintainer and citing plan / requirements / §7 / the six lane notes / Tetravox PR #35 |
| `desktop/DESIGN.md` | **new §4.8 Selection** (SG's text: the grammar, the filter-interplay rule with teeth, `bulkExclude`, the two ARIA shapes, the receipt through the layout slot, the one existing-outputs dialog) and **§4.9 Electrodes and channels** (EL's text: colour is the whole state, Okabe-Ito from `channelCss()`, names for the selection only, the legend, the click rules). **New §9.1 Pipeline** (the page's shape and its five rules) and **§9.2 Settings — the viewer engine card** (AU's reworded rule 2). §9's rail table updated to nine rows + Settings on ⌘0, and §6.5's shortcut line with it. §4.7 kept its number — the new sections are additions, not a renumbering |
| `desktop/IMPLEMENTATION_PLAN.md` | Status line now records the second 2026-09-05 pass, its plan, requirements, contract section and gate, and that it adds a ninth rail row rather than reversing anything |
| `dev/notes/v3-tetravox-selection-pipeline-plan.md` | Status line: implemented and gated, with the records it landed and the one thing still outstanding (the maintainer's Tetravox release) |
| `docs/wiki/pipelines.md` | the "Today's limit" callout deleted; the dynamic path is now described as working, with an honest paragraph on what happens when a resolve step finds nothing |
| `container/blueprint/README.md` | **verified, already done by AU** — "Which Tetravox gets baked" names the three assets, the protocol range read out of `tit/tetravox/protocol.py`, the stdlib-only lookup, the deliberate agreement with `tit/tetravox/updates.py`, and the non-fatal failure path |

## 3. Gate

| Command | Where | Result |
| --- | --- | --- |
| `pnpm run typecheck` | `desktop/` | clean (both projects) |
| `pnpm run lint` | `desktop/` | **0 errors**, 3 warnings — all pre-existing `react-hooks/incompatible-library` on `ui/DataTable.tsx` and `ui/VirtualList.tsx` |
| `pnpm run test` | `desktop/` | **84 files, 949 tests passed** |
| `npx vitest run tests/mock-server` | `desktop/` | **33 passed** (seam e) |
| `npx vitest run tests/unit/shell-registry.test.ts` | `desktop/` | **20 passed** — the derived shortcut map, after seam (a) |
| `pnpm run e2e:quiet` (full suite, offscreen) | `desktop/` | **195 passed, 3 skipped, 0 failed** (9.9 min); `e2e-quiet-check: PASS`, `no new Electron/Chromium window reached the screen`. SG measured 193/3/**2** before this lane; the two reds were seam (a) |
| `pnpm run build` | `desktop/` | `✓ built in 2.49s` |
| `python3 -m pytest tests/ -q` | root | **3741 passed, 47 skipped, 21 deselected** (67 s). PC/AU last measured 3734; +7 are this lane's `tests/test_pipeline_bindings.py` |
| `python3 dev/route_import_guard.py` | root | `route_import_guard: 21 route module(s) clean` |
| `python3 dev/contracts_check.py` | root | **7 problems — the same 7 CX recorded on 2026-09-05**, all pre-existing (`Capabilities.tetravox_embed`, `Capabilities.fastsurfer`, `Subject.has_fastsurfer` served but not required). No lane in this program touches those schemas; nothing was added or removed |
| `python3 -m pip wheel . --no-deps` | root | `tit-2.4.0-py3-none-any.whl` — **20** `tit/scene/guide/*` data files (unchanged from CX) and all five `tit/pipeline/*` modules, plus `tit/jobs/bindings.py`, `tit/tools/pipeline_resolve.py` and `tit/tetravox/updates.py` |

PC's note reports `dev/contracts_check.py` flagging 52 "missing from dump components" — that is the
two-argument form (`contracts_check.py <yaml> <dump>`), and the count is identical before and after
this program because those routes take plain `dict`/`list` bodies for which FastAPI declares no
component. The repo's default invocation, which is what CI runs, is the 7 above.

### Real container

`ti-toolbox-fad740e5-tit-1` (port 8765, worktree mounted at `/ti-toolbox`, `--reload`), Dataset 000.
**Checked first that nothing was running** — `GET /api/jobs?state=running` → `[]` and
`?state=queued` → `[]` — so no FEM run was disturbed and none was started concurrently.

```
GET /api/health            200  {"status":"ok","uptime_s":489.01}
GET /api/pipelines         200  []
GET /api/pipelines/kinds   200  port_types [subjects, montages, simulation, roi, leadfield]
GET /api/tetravox/updates  200  auto_update true, from_cache true,
    index https://api.github.com/repos/idossha/tetravox/releases
    message "v0.3.11 carries no tetravox-embed-<version>.tgz asset; v0.3.10 …; v0.3.9 …"
    last_outcome {"action": "current", …} — the startup pass ran on its own
```

That message is the honest, expected answer today: 0.3.11 exists and carries no embed asset, which
is exactly what Tetravox PR #35 is for.

`--project=real` Playwright subset (offscreen, `TIT_E2E_SERVER_URL`/`TIT_E2E_TOKEN`), exactly the
five specs the brief names:

```
$ TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
    tests/e2e/real/{embed-electrodes,tetravox,pipeline,scene-preview,page-memory}.spec.ts
13 passed (15.5m)
```

The three `embed-electrodes` pixel tests reproduce EL's numbers exactly against the live 0.4.0
bundle — idle `148,155,167`, pair 1 `0,106,166`, pair 2 `215,149,0`, and a radial profile
`[1,8,12,16,32,25,31,22,21,21,10,7,3,0,0,…]` that is byte-identical before and after the toggle:
one solid disc, no ring. The `dotRadiusPx 5 -> 209px; 15 -> 209px` line is the pinned 3-D defect,
still failing to fail (as intended) on this bundle.

`real/pipeline.spec.ts:126` — *"the whole pipeline runs as one group and completes"* — ran a genuine
FEM simulation and its analyzer end to end in **14.7 min**, one `group_id`, `sim` then `analyzer`,
both `succeeded`, and the spec cleaned up after itself: `sub-ernie/Simulations/` is back to its six
pre-existing entries and no pipeline document was left in the shared project.

**Two things happened during this run that were not this program's doing, and both are recorded
rather than smoothed over.**

1. **The shared container was restarted by something outside this session**, mid-FEM, on the first
   attempt. It came back with a *new* `TIT_SERVER_TOKEN`, which is how it was noticed. The running
   `sim` went to **`lost`** and its dependant analyzer to **`skipped`** — which is precisely PC's
   open item 7 observed in the wild, from a third direction (not a `git stash`, not an import
   error, just a restart). I killed the stranded Playwright run, verified the orphaned output
   directory was gone and the project clean, took the new token, and re-ran the whole subset from
   scratch; the 13/13 above is that second run. The first run's first nine tests had also passed.
2. **`e2e-quiet-check` reported FAIL on the real subset**, naming Electron windows including one
   `1024x1112` titled *TI-Toolbox*. The same script with the same `TIT_E2E_OFFSCREEN=1` reported
   **PASS** on the full mock suite an hour earlier, and other Electron apps (the Tetravox app, SUNA)
   were running on the machine throughout — the maintainer was using it, which is also the most
   likely explanation for the container restart. I cannot prove the window was not ours, so this is
   reported as unresolved rather than dismissed. SG and AU recorded the same harness behaviour
   independently.

## 4. Open items, consolidated from all five lanes

Everything below is recorded in `docs/ROADMAP.md`'s "Known follow-ups" table unless marked otherwise.

**Blocked on the Tetravox release (§5)**

1. **No release carries an embed asset**, so the first genuinely automatic install cannot be run.
   Everything about it is proved against a loopback fake GitHub with real tarballs, digests and
   manifests — on the host and inside the container — plus the real API's honest empty answer (AU).
2. **Per-point `radiusPx` is inert.** B1's "7 px when hovered/active" cannot be a radius until
   Tetravox ships a second per-instance attribute; it stays expressed as colour (TX, EL).
3. **Hover colour.** Tetravox 0.3.12 adds a `pointHover` event and deliberately *no*
   `stateColors.hover` — the host owns colour — so B2's hover half lands when the app runs against
   0.3.12 (TX, EL).
4. **The explicit idle `color` on every point** can go once the app runs against 0.3.12; the
   `TODO(tetravox)` names the condition (EL, seam d).
5. **`real/embed-electrodes.spec.ts`'s third test is written to fail** when a 0.3.12 bundle arrives —
   it pins the 3-D dot defect. Invert it then; do not delete it (TX open item 7).
6. **Version numbers go backwards** at the first release: the container runs a hand-installed 0.4.0
   and the first release is 0.3.12. AU's provenance rule already handles it and is tested; clearing
   the user root once is the operator's alternative (TX open item 4).

**Product / code**

7. **Job re-adoption across a `--reload`** — seam (f). Not implemented, deliberately.
8. **`POST /api/jobs/{id}/retry` does not exist**, so C4's retry half is unimplemented; cancel and
   pin-terminal are (SG).
9. **A saved pipeline's node forms open at their defaults** — the document stores built configs and
   no page has a config → form-state reader (PC).
10. **`ex`/`mex`/`leadfield`/`source`/`stats` nodes are edited as JSON**, validated server-side
    against the real dataclass, so the failure mode is a sentence (PC).
11. **Node status chips zip plan order** rather than reading a tag, because `JobStatus` carries no
    `tags` on the wire (PC).
12. **`SelectionList` has no `rowAction` slot**, so the saved-ROI list keeps its own row shape; and
    the Source panel's two confirmations stay page-local until `/api/plan` has a source kind (SG).
13. **Two cursors**: SG shipped `activeSlot`/`onActiveSlotChange` on `ElectrodePairsEditor` (EL's
    ask), so this one is **closed** — recorded here because EL's note predates the fix.
14. **`SceneGesture` still contains `"sphere"`** and `sphereMarkers`/`roundCoord`/`vecFromCentre`
    still have no product caller — carried over unchanged from lane GD's list, and still a
    two-file deletion whenever someone wants it.
15. **`tit/tools/pipeline_resolve.py` is not `black`-clean** (two call sites black would wrap). Left
    alone: it is pre-existing to this lane and reformatting an untracked file in flight buys nothing.
    *Not in ROADMAP — a one-command cleanup.*
16. **The rate-limit path is tested against a fake 403** and unauthenticated access is deliberate; a
    token for a public repo's public releases is a credential this app would have to protect (AU).
17. **`e2e-quiet-check` can print FAIL on focus and on windows** when the machine is in use — seen
    by SG, AU and this lane. It is the harness's own check, not a spec failure, but it is not yet
    reliable enough to be evidence either way on a machine someone is working on. *Not in ROADMAP —
    a test-harness question for whoever owns `scripts/e2e-quiet-check.sh`.*
18. **A container restart orphans a running job and skips its dependants** — item 7 above, observed
    live during this lane's real run. It is the single most user-visible gap this program leaves.

## 5. The maintainer's release checklist

Everything in decision A is built and tested; the one thing it waits on is a Tetravox release that
carries embed assets. That release is yours to cut — the TX lane never touched `main` and never
tagged, by that repo's own rules.

**1 — Merge the Tetravox PR.**
[`idossha/tetravox` PR #35](https://github.com/idossha/tetravox/pull/35), `feat/embed-release` →
`main`. It carries the rebase onto 0.3.11 (so the embed finally has the 0.3.10/0.3.11 fixes), the
three release assets, the `ack` reply ids, the 3-D `dot` pass, the reachable `stateColors.idle`, the
`pointHover` event, and the schema additions. Its gate: `pnpm test` 1918 passed, embed e2e 49 passed
on both renderer legs, frozen-docs check ok. You may want to re-word `CHANGELOG.md`'s `[Unreleased]`
section first — the rebase had put the embed entries under the already-published `[0.3.9]` and TX
moved them.

**2 — Cut the release.** On a clean `main`:

```bash
scripts/release.sh 0.3.12
git push origin main
git push origin v0.3.12
```

The **tag push** is what builds the embed, attaches
`tetravox-embed-0.3.12.{tgz,tgz.sha256,manifest.json}` and drafts the Release; `release.yml`'s
`verify` job publishes it only when all three assets are present and the manifest inside the tarball
matches the sidecar. Nothing else is required of you.

**3 — What TI-Toolbox then does by itself.** Nothing to configure and no TI-Toolbox release:

- within 5 s of a server start, and every 24 h after, the server asks
  `https://api.github.com/repos/idossha/tetravox/releases`, finds v0.3.12, reads `protocol: 2` out of
  the manifest **asset** (about 2 KB — the tarball is not touched yet), and sees that 2 is inside
  this build's supported range;
- because `tetravox.auto_update` defaults **on**, it downloads the tarball, verifies the sha256,
  installs it atomically into the user-config root, activates it and keeps the previous two;
- the desktop shows one toast: *"Tetravox 0.3.12 installed — reload the viewer."* Panes already
  mounted keep their current bundle; a new mount gets the new one.

If the check fails — offline, rate-limited, a bad digest — it is one honest line in Settings and the
log, once per interval. Nothing blocks and nothing retries in a loop.

**4 — How to verify, in Settings → Viewer engine.**

- **Last checked** shows a fresh timestamp, and **Check now** forces a fresh look (it is the only
  control that reaches the network; rendering the card does not).
- The card should name **0.3.12** as active, protocol 2, installed from a release. If it still says
  0.4.0, that is the container's hand-installed dev bundle: the version number goes *backwards* at
  this release while the bundle goes forwards, which is why "newer" is measured against release
  provenance rather than the active bundle. Activate 0.3.12 explicitly, or clear the user root once.
- **Rollback** is one click, to the baked floor or the previous install.
- From a shell, the same facts: `GET /api/tetravox/updates` should stop saying *"carries no
  tetravox-embed-<version>.tgz asset"* and start listing v0.3.12 as compatible, and
  `GET /api/tetravox` should report it active.
- The visible payoff: in a montage scene pane the electrodes become true screen-space discs of a
  constant 5 px (7 px on the active pair) at any camera distance, instead of millimetre spheres.
  `tests/e2e/real/embed-electrodes.spec.ts`'s third test — the one that pins the defect — will start
  failing, which is the signal to invert it.

**5 — Then, in TI-Toolbox.** Cutting a fresh image is now optional and needs no Dockerfile edit:
`container/blueprint/build.sh` with no `--tetravox-tgz` resolves 0.3.12 by itself, by the same rule
the running server applies. Nothing else in this program is waiting on anything.

---

Nothing here is committed. `desktop/` and `tit/server/` remain untracked WIP.
