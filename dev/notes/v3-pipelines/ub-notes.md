# Lane UB — U11: no project/subject crumb in the context bar (2026-09-03)

Contract: `dev/notes/v3-pipelines-program.md` §6, decision U11. Maintainer's screenshot comment,
verbatim: *"we still need to remove this from the top rail."* Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed, staged or
stashed. `desktop/` is uncommitted scaffolding shared by every lane in this worktree — the wide
`M`/`D`/`??` spread `git status` shows at the repo root belongs to other concurrent lanes (D0, S1,
S2, F0, a Python lane), not to this one; this lane's own touch list is the file list below.

## What changed

- `desktop/src/renderer/app/AppContextBar.tsx` — removed the project `Crumb`, `CrumbSeparator` and
  the `<SubjectSwitcher>` mount, and the `getProject` query that fed the crumb's label. The bar's
  left slot (`ContextBar`'s `children`) now holds the `⌘K` trigger, restyled as a wide search field
  (`palette-trigger-wide`, `data-testid="palette-trigger"`) with the label flexing so the `⌘K`
  `Kbd` hint sits pinned at the field's right edge. The right slot (`end`) is unchanged in content
  and order: connection dot + label (`connection-state`), running count (`jobs-count`), and
  "Sign out" when `connection.status === "unauthenticated"` — verbatim from before, same testids,
  same condition. Props `onOpenProject`, `subjectSwitcherOpen`, `onSubjectSwitcherOpenChange` are
  gone from the component's signature.
- `desktop/src/renderer/app/SubjectSwitcher.tsx` — **deleted.** The palette does not import or
  reuse this component (its own `buildCommands` in `commands.ts` already lists every subject as a
  searchable `Command.Item`, independently — that code is untouched), so per the lane brief's own
  rule ("if the palette's subject command reuses it, keep the component ... ; drop only the bar
  mount") the right action was delete, not fold. The evidence this was already the intended
  direction, found before touching anything: `tests/e2e/_helpers.ts`'s `selectSubject` already
  drove subject selection through the palette exclusively (a doc comment there already called it
  "the only subject control that exists outside a page's own batch table"), and
  `pages/preprocess/index.tsx` already carries its **own** page-local Subjects batch table, seeded
  from the shell's single-subject spine but not from the switcher's `batch` state — i.e. the
  page-owned-batch-table future this deletion assumes is not hypothetical, one run page already
  built it.
- `desktop/src/renderer/app/Shell.tsx` — dropped the `switcherOpen` state and the `onOpenProject`/
  `subjectSwitcherOpen`/`onSubjectSwitcherOpenChange` props passed to `AppContextBar`; dropped the
  now-unused `useNavigate` import (`navigate` had no other caller). `⌘P` (`useGlobalShortcuts`'s
  `openSubjectSwitcher` handler — that field name is `app/keyboard.ts`'s, untouched, since renaming
  it was not something the removal broke) now opens the same palette `⌘K` does
  (`() => setPaletteOpen(true)`), rather than a switcher that no longer exists. This was the
  smallest-footprint fix: it touches only this lane's own file, leaves `keyboard.ts` and
  `KeyboardSheet.tsx` (both outside this lane's ownership) untouched and their existing "Switch
  subject" labelling still true in effect, and gives ⌘P a real destination instead of a dead one.
- `desktop/src/renderer/app/shell.css` — added `.palette-trigger-wide` (width 340px, `max-width:
  min(420px, 40%)`) and `.palette-trigger-label` (`flex: 1`, ellipsis) for the widened field;
  removed `.subject-batch`, `.subject-batch-toggle`, `.subject-batch-popover` — their only
  consumer was the deleted component.
- `desktop/tests/unit/shell-contextBar.test.tsx` — rewritten: the crumb/switcher tests are gone,
  replaced with "carries no project crumb and no subject switcher" (testid absence + bar text
  excludes the project name and "No subject") and "opens the palette from a wide search field
  carrying the ⌘K hint" (click → `onOpenPalette` called, `data-testid="palette-trigger"` present,
  carries the `palette-trigger-wide` class). The jobs-count and "no theme/version" tests are
  unchanged (still true, still asserted the same way).
- `desktop/tests/e2e/smoke.spec.ts` — two spots referenced the removed testids:
  - the opening chrome test's "project crumb / subject switcher beside it" assertions became
    "no project crumb, no subject switcher" (`toHaveCount(0)` on both testids) plus three new
    measured checks: the context bar's own `getBoundingClientRect().height` rounds to 40,
    `.context-bar` does not contain the project name ("example"), and the search field
    (`palette-trigger`) is visible, contains the `⌘K`/`Ctrl+K` hint, and measures wider than 200px.
  - the palette test's "switching subject ... re-scopes the context bar" assertion
    (`subject-switcher` containing "ernie") became "`.context-bar` does not contain 'ernie'" —
    the re-scoping itself is still proven, by `expectSubject`, which was already the next line.
- `desktop/tests/e2e/subjects.spec.ts`, `desktop/tests/e2e/screens.spec.ts`,
  `desktop/tests/e2e/_helpers.ts` — read in full; **no reference to the crumb or the switcher in
  any of the three.** `_helpers.ts`'s `selectSubject`/`gotoPage`/`expectSubject`/`openPalette` were
  already crumb-free (see above); `subjects.spec.ts` never touched context-bar chrome;
  `screens.spec.ts` already scoped its run through the palette (its own comment: "the way a person
  does it"). No edits made to any of the three — they were re-run to confirm, not changed.
- `desktop/DESIGN.md` — §2.3 "What the shell owns", the context-bar bullet: rewritten from "owns
  scope ... project name · subject switcher" to "carries global chrome, not scope" — search left
  (wide, where the crumb sat), connection + running count right, explicitly "no project crumb, no
  subject switcher, no presence chips, no + Add subjects", with where each of those four now lives
  (Settings ▸ Project / palette "Open settings"; the palette's Subjects section or a page's own
  control; the Subjects page; a page's own batch table, Pre-processing named as the first).
  §6 rule 5's keyboard line: the `⌘P` clause now says it opens the same palette, at its Subjects
  section, rather than "subject switcher" bare. §5 Components' `Crumb`/`CrumbSeparator` entry:
  the parenthetical "(the switcher trigger)" — now false — became "(...the context bar itself
  stopped using it at U11, but a page's own scope control ... still can)"; `Crumb` stays exported
  and used (`pages/dev/DensityGallery.tsx`'s demo), so nothing about the primitive itself changed.
- `dev/notes/v3-ui-program.md` — one new paragraph directly after the decisions table (same spot
  Q1's own amendment lives), pointing U6's project-crumb/subject-switcher clause at
  `dev/notes/v3-pipelines-program.md` §6 U11 as the record of the change, and restating what stays
  (store, `data-subject`, palette rows, a page's own control).

## What did NOT change (checked, left alone)

- `desktop/src/renderer/app/CommandPalette.tsx`, `desktop/src/renderer/app/commands.ts` — no edit.
  The palette's per-subject `Command.Item` rows and the "Open settings" action already satisfy
  both halves of the brief ("the palette's Change-subject command ... stay" and "reachable ...
  from ... the palette").
- `desktop/src/renderer/app/subjectContext.ts` — no edit. The store, `selection`, `batch`,
  `setBatch` are untouched; `batch`/`setBatch` simply have no UI writer left in the shell chrome
  (a page can adopt them, as Pre-processing already did with its own local state instead).
- `desktop/src/renderer/pages/settings/index.tsx` — read only, not owned by this lane. Confirmed
  it already renders a "Project" card from the same `getProject` query (`Name` / `Container path`
  / `Host path`), so "Whatever the project crumb opened ... must stay reachable from Settings"
  needed no page change — it already is.
- `desktop/src/renderer/app/keyboard.ts`, `desktop/src/renderer/app/KeyboardSheet.tsx` — not in
  this lane's ownership list; the `⌘P` fix landed entirely in `Shell.tsx` (see above) so neither
  needed touching, and neither test file nor any spec exercises `⌘P` directly.
- `pages/**`, `ui/Layout.tsx`, the jobs rail — untouched, per the brief.

## Numbers

| what | value |
|---|---|
| context bar height (`.context-bar` `getBoundingClientRect().height`, measured) | 40px, unchanged |
| search field width (`palette-trigger`, measured) | > 200px asserted; CSS sets 340px (`min(420px, 40%)` cap) |
| project/subject text in the bar | none — `.context-bar` asserted to exclude the project name ("example") both idle and after a palette-driven subject switch ("ernie") |
| `npm run typecheck` | clean |
| `npm run lint` (this lane's files only: `AppContextBar.tsx`, `Shell.tsx`) | clean; 13 pre-existing errors remain in UA-owned files (`pages/jobs/index.tsx`, `ui/Layout.tsx`, `ui/paneState.ts`) — not this lane's |
| `npx vitest run` | 648 passed / 57 files, 0 failed |
| `npm run build` | succeeds |
| `smoke.spec.ts` under quiet check | 9/9 passed |
| `subjects.spec.ts` under quiet check | 6/6 passed; dead-space numbers unchanged from their documented baseline (readiness 17.5%, table 25.5%, detail 43.5%, work 64.7%; populated 47.7%/59.2%, unselected 51.3%/66.2% — all within the spec's own bounds) |
| `screens.spec.ts` under quiet check | 5/5 passed, 48 captures |
| full suite (`npx playwright test`, default project) under quiet check | 91 passed / 1 skipped (`viewer-real.spec.ts` — needs a real server, correctly skips without one; unrelated to this lane) / 0 failed, 92 total, 5.9m |
| quiet-check window-list check | FAILS on every run in this session, same window every time: `owner=Electron title=TI-Toolbox bounds=1919,1052,1900x1030` — traced to a pre-existing, still-running `electron-vite dev` process (pid 59270+, started 6:34pm, `npm run dev` under lane D0) already on screen before this lane's first test ran; `frontmost` before/after every run in this session stayed `Tetravox` (unchanged) — focus was never stolen. This is cross-lane environmental noise from a concurrently-running dev session sharing this worktree, not a window this lane's own Playwright runs opened; not fixed here (killing another lane's live dev process is out of scope and would destroy their work). Flagged as an open issue below. |

## Open issues

- **Quiet-check false positive from a concurrent lane's dev window** (see table above). Evidence:
  same exact `bounds=1919,1052,1900x1030` on both the touched-specs run and the full-suite run, a
  live `electron-vite dev` process tree confirmed via `ps aux` (started before this lane's first
  test), and `frontmost` unchanged across every run. Suggested owner: whoever coordinates the
  worktree lanes at the end — either accept as known noise for a shared-worktree quiet check, or
  have D0 stop its dev window (or move it `TIT_E2E_HEADED`-style off screen) before a clean
  quiet-check pass is needed for real.
- **Batch subject selection has no UI path outside a page that has built its own** (Pre-processing
  has one; Simulator, Optimizer and Analyzer read `useSubject().selection`/`.batch` but nothing
  in the shell can set `.batch` any more now that the switcher's popover is gone). Not a
  regression this round introduced blind — `_helpers.ts`'s own pre-existing comment and
  Pre-processing's own pre-existing local batch table both point at "a page's own batch table" as
  the intended replacement — but three of four run pages do not have one yet. `selection` still
  degrades correctly to `[id]` (single-subject), so nothing is broken, only multi-subject batch
  runs from Simulator/Optimizer/Analyzer are unreachable from the UI until those pages grow their
  own batch control. Suggested owner: whichever future lane touches those three pages' Tier-1
  fields (out of this lane's scope — `pages/**` is UA's / a future lane's).
