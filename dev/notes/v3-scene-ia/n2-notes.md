# Lane N2 — "the state of the tabs is not persistent: jumping between tabs resets them"

Maintainer's report, verbatim. "Tabs" means the pages in the left rail. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04. Nothing
committed; every run offscreen through `desktop/scripts/e2e-quiet-check.sh`.

## 1. The model, written before the fix

| | Owner | Rule |
|---|---|---|
| A section the user opened or closed, the Terminal/Scene tab they picked, where they scrolled, the segment or sub-tab they chose, what they typed, which subjects they ticked | **the user** | survives navigation for the life of the session; nothing recomputes it |
| `RunWork`'s fill controller deciding a first-open for a section the user has **never** touched on this page in this session | **derived** | recomputed on every mount and at every pane size |

Three rules follow, each with the failure it prevents. They are now also in `desktop/DESIGN.md`
**§4.4.2** (new subsection, nothing renumbered), which is where they survive this lane.

1. **A user-touched section outranks the fill controller and a `fill` table.** Resolves CL2's open
   issue 2 (`cl2-notes.md` §8.2: "arbitration by ordering, not by rule"). The controller never
   opens or closes a section the user has touched — now across mounts, not just within one — and
   `SubjectsField`'s ground rows re-measure against the column so a section the user opens takes
   room *from the ground rows* instead of overflowing the page and making the controller close
   something to pay for it.
2. **In memory, not `localStorage`.** A preference (theme, pane width) describes how the app should
   look and must survive a restart. A half-configured run must not: restoring yesterday's ROI,
   subject set and run name into a fresh launch offers a job the user never assembled, and the bag
   carries no project identity, so it would follow them to a different dataset. Closing the app is
   the reset; navigating is not.
3. **It is a requirement on the pane, not on the renderer** — see §7, the statement that has to
   survive the Tetravox embed migration.

## 2. The reproduction, and its number BEFORE

`desktop/tests/e2e/page-memory.spec.ts` (mock) and `desktop/tests/e2e/real/page-memory.spec.ts`
(the running container) visit each run page, do what a user does — close an open section, open a
different closed one, pick the Terminal tab, type a run name, scroll the work pane to the bottom —
then go to Jobs and come back, and compare a **fingerprint captured as data**: every collapsible
section's `aria-expanded`, whose decision that is (`data-fill-user`), the run pane's `data-tab`,
the scroll offset, every segmented control's chosen label, every text input's value, and the number
of real (non-ground) table rows. No screenshot: a picture cannot say that `Conductivity` was closed
and is now open.

Measured with the session memory switched off (a two-line kill switch in `pageSession.ts`, so the
*final* spec runs against the pre-fix behaviour, not an earlier draft of it):

```
default project (mock server), 1280x800                          4 failed
real project    (container 8765, sub-ernie), 1280x800            4 failed
```

The real run, which is the environment the report came from:

| page | left as | came back as |
|---|---|---|
| preprocess | `Existing outputs` **open** (user) | **closed** |
| simulator | `Electrodes` closed, `Conductivity` open, `Output fields` open; tab **Terminal** | Electrodes closed, Conductivity **closed**, Output fields **closed**; tab **Scene** |
| optimizer | `Electrodes` closed, `After the search` open; tab Terminal; scroll **55 px**; run name **`n2-probe`** | Electrodes **open**, After the search **closed**; tab **Scene**; scroll **0**; run name **empty** |
| analyzer | `Output` closed; tab Terminal; **1** table row | `Output` **open**; tab **Scene**; **2** table rows |

The last cell is the maintainer's "its row count changed 1 to 2", reproduced.

## 3. The cause

Three separate ones, all the same shape — state that belongs to the user kept in something that
dies with the component:

1. **The page unmounts on every navigation.** `app/App.tsx` renders exactly one route element, and
   every run page keeps *all* of its state in `useState` — subject selection, method, ROI, sphere
   table, montage draft, run name, output fields. So the answer to "do typed form values survive?"
   (the maintainer could not prove they do not) is: **they did not.** Nothing survived. The reason
   only the sections looked like a *reset* rather than a fresh page is that the sections come back
   in a *different* arrangement, which is visible, while a form coming back at its defaults reads
   as "I have not configured this yet".
2. **`RunWork`'s fill controller re-derives the section layout on every mount.** Its record of what
   the user had decided was a `useRef(new Set())` and its own opened set a `useState` — both gone
   with the component — so the next mount measured whatever that mount happened to look like and
   landed somewhere else. That is the "reset" in the report.
3. **`RunPaneTabs` promised more than it delivered.** Its own doc comment said a chosen tab is
   pinned "for the rest of the session on that page"; the choice was a `useState`, so it lasted
   until the user left the page.

And a fourth, found while fixing: **`<RunWork fill={false}>` (the Optimizer) handed `FormSection` a
`null` context**, which switched off the *section memory* along with the *measuring*. Two different
things behind one flag: with it off, a section the user closed was never recorded at all and
`defaultOpen` decided again on the next mount — which is why the Optimizer lost both directions.

## 4. The fix

New: `desktop/src/renderer/app/pageSession.ts` — a zustand store (the `app/theme/store.ts` pattern)
holding one flat bag keyed `"<pageId> <key>"`, plus `usePageSession(key, initial)`, a **drop-in for
`useState`**, and `usePageSessionRef(key)` for state that changes too often to re-render on (the
scroll offset fires per frame). The page id comes from a context `Shell` provides — it already
computes `activePageId` for `data-page` — so nothing is threaded through `RunPanel`. The hook is a
local `useState` seeded from the bag and mirrored back in an effect, deliberately not a zustand
selector: a slot has exactly one owner, and seeding a missing slot from a selector needs a
render-phase write into an external store, which is the one thing React 18 may tear on.

- **`pages/_shared/run/RunWork.tsx`** — `userOpen` (the user's decisions) and the controller's own
  opened set both move into the bag; the candidate filter reads `!(id in userOpen)`. `fill={false}`
  now turns off the measuring only: the context is always provided, and `openFor` returns
  `undefined` when the controller has no remit.
- **`ui/Layout.tsx`** — `FormSectionFill` gains `userOpenFor(id)` and `onUserToggle(id, open)`;
  precedence becomes *the user (this mount or an earlier one) → the density pin → the controller →
  `defaultOpen`*. The section publishes `data-fill-user="open"|"closed"` while the state is the
  user's, absent while it is the controller's.
- **`pages/_shared/run/scrollMemory.ts`** (new) + a `RunWork` effect — the work pane's offset,
  re-applied on every content resize because the page mounts short (the first assignment is clamped
  to 0), abandoned at 2 s or on the first `wheel`/`touchstart`/`keydown`, and never recorded while a
  restore is in flight (the clamped intermediates are the browser's, not the user's).
- **`pages/_shared/run/RunPaneTabs.tsx`** — the chosen tab moves into the bag, which is what its
  own doc comment always claimed.
- **`pages/_shared/subjects/SubjectsField.tsx`** — the `fill` table's `ResizeObserver` also observes
  the column (`.run-work`). The scrollport is a fixed box, so a section opening beside the table
  resized neither observed box and the table kept ground rows measured against a shorter column.
  Safe against the oscillation CL2 warned about: `others = columnH − box.clientHeight` is invariant
  to the box's own height, so a re-measure reproduces the same row count and `setFitted`'s identity
  check stops there.
- **The four pages** — every field the *user* decides is now `usePageSession`; every transient stays
  `useState`, on purpose: `conductivityDialogOpen`, `confirmOverwrite`, `confirmOpen`,
  `qsiPrepOpen`, `qsiReconOpen`, `confirmReplaceOpen`, `running`, `validationErrors`,
  `lastShellSubject` (the shell-subject sync sentinel). Pre-processing's steps live in React Hook
  Form, which has its own store and dies the same way, so the bag seeds `defaultValues` once and a
  `form.watch` subscription writes changes back — imperative, because `form.watch()` returns a new
  object every render and mirroring it through React state would re-render on its own output.

## 5. The number AFTER

```
host      python3 -m pytest -q                      3587 passed, 32 skipped, 21 deselected (49 s)
desktop   npm run typecheck                         clean
desktop   npm run lint                              0 errors, 3 warnings (all pre-existing; the one
                                                    in preprocess/index.tsx only moved line — proved
                                                    by linting the file with the new effect removed)
desktop   npx vitest run                            956 passed, 78 files  (+10 new, this lane's
                                                    tests/unit/page-session.test.tsx)
desktop   npm run build (plain)                     0 test-hook / gallery strings in out/
e2e       page-memory.spec.ts (mock, default)       4 passed   [was 4 failed]
e2e       real/page-memory.spec.ts (container)      4 passed   [was 4 failed]
e2e       full default project                      142 passed, 1 skipped, 0 failed (8.7 m)
                                                    e2e-quiet-check: PASS, no window on screen
```

Layout gate re-measured on this tree (`layout.spec.ts`, L5a limit 45 %), all four run pages, both
sizes, both themes — **nothing moved out of budget and no budget was loosened**:

| page | 1280×800 | 1440×900 |
|---|---|---|
| preprocess | 28.1 % | 31.7 % |
| simulator | 34.5 % | 38.4 % |
| optimizer | 39.8 % | 41.3 % |
| analyzer | 40.9 % | **43.5 %** (worst) |

`tier1` 21/21, 16/16, 18/18, 28/28 on the first screen; `obstructed=0` everywhere; light and dark
identical to the digit. `table-room.spec.ts`: `panel-source` 44.8 %, preprocess 31.7 %, 12 rows at
1440×900 and 26 at 1440×1300 — unchanged from CL2's numbers.

## 6. Two defects found in the specs, and why they are not "loosening"

Both are check-then-act races against the fill controller, both pre-existing, both proved
independent of this lane by re-running them with the session memory switched off **and** with
`RunWork`'s user-decision store reverted to the old ref (still failed).

- `segmented-idiom.spec.ts`'s `openSection` counted `.form-section-body`, then clicked. The
  controller opens sections over rAF passes after mount, so a body absent at the count can be
  present when the click lands — and the click then *closes* the section. Measured deterministically
  on the Simulator at 1280×900: read closed → clicked → ended closed.
- The same shape reading a section as "open" gave no promise it would *stay* open: on
  Pre-processing the controller had closed "Existing outputs" again by the next assertion.

Fixed with one shared helper, `setSectionOpen(page, title, open)` in `tests/e2e/_helpers.ts`, used
by `segmented-idiom.spec.ts` and `simulator.spec.ts`: it re-reads `aria-expanded` immediately before
each click, and insists the state is the **user's** (`data-fill-user`) — clicking twice when the
state is already right, because that is how a user makes a state stick, and the rule it leans on is
the product's, not the test's.

## 7. The requirement that has to survive the Tetravox embed migration

Written into `desktop/DESIGN.md` §4.4.2, consequence 3, and repeated here because lane M of
`dev/notes/v3-embed-convergence-plan.md` will delete `desktop/src/renderer/scene/**` and drive an
embed `<iframe>` from `ScenePane`:

> The Terminal/Scene choice, the section open/closed state and the work-pane scroll offset are
> **page-session state, not renderer state**. A migration that replaces the renderer must keep them
> read from and written to the page's session bag (`app/pageSession.ts`), never to component state
> that dies with the pane. Lane M's own requirement — *mount only the visible pane and tear it down
> on unmount*, for the wasm heap — is exactly the case that makes this necessary: a torn-down pane
> must not take the user's tab choice with it. `tests/e2e/page-memory.spec.ts` and its `real` twin
> name no renderer; a migration that keeps them green has kept this rule.

One additional decision that migration will have to take explicitly rather than by accident: the
embed's own camera is the user's too. Either it is restored from the bag on remount, or the plan
records that the camera is derived and re-framed on every mount, with the measurement that made
that acceptable.

## 8. Open issues

1. **The controller opens a section under the user's cursor.** A section the user aims at while it
   is closed can be opened by the fill controller a frame or two after mount, so the click *closes*
   it — and since this lane that decision now sticks for the session. It is the same race §6
   measured in a spec; a user hits it as "I clicked to open it and it closed". Not fixed here
   because the fix is the fill rule's, not the memory's: the controller should stop deciding once
   the page has been on screen long enough for a click to be deliberate, or should not move a
   section under a pointer that is over it.
2. **Only the four run pages remember.** The bag is generic and the hook is a drop-in, but Settings,
   Results, Jobs, the Viewer and the panel pages still reset on navigation. Settings is another
   workflow's file this lane must not touch; the rest were out of scope. Scroll memory in particular
   lives in `RunWork`, so a page without it (every panel page) has none — `PageLayout` is where it
   would belong if this becomes general.
3. **`data-fill-user` is a new DOM contract.** It is deliberately test-visible, like
   `data-chosen`. Anything that renders `FormSection` outside `RunWork` gets it from the component's
   own state, which is correct but means the attribute says "the user decided in this mount" there,
   not "for the session".
4. **The session bag has no eviction and no project identity.** It grows with the pages visited
   (kilobytes at most) and is dropped when the renderer reloads. If the app ever changes project
   without reloading the renderer, the bag must be cleared — `clearPageSession()` exists for that
   and nothing calls it yet.
5. **Pre-existing, unchanged, re-observed here**: the mock server still shares state across spec
   files (five lanes have now flagged it); `panel-source` sits at 44.8 % of L5a's 45 %; and a
   `tests/e2e/fixtures/fake-docker.js --serve-fake-server` process is left running by the
   launcher/native-launch specs after a suite run (three were alive after this lane's runs; not
   killed, since another lane may be mid-run).

## 9. How to re-run this lane

```bash
cd .../worktrees/v3-electron-gui/desktop
npm run typecheck && npm run lint && npx vitest run && npm run build
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh npx playwright test --project=default page-memory
TOK=$(docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep TIT_SERVER_TOKEN | cut -d= -f2)
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/page-memory.spec.ts
# the whole default project needs the flagged build (gallery + scene hooks), then a plain rebuild:
VITE_INCLUDE_GALLERY=1 VITE_SCENE_HOOKS=1 npx electron-vite build
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh npx playwright test --project=default
npm run build      # out/ must be left PLAIN — the container serves it
```

To re-measure the "before" numbers without reverting anything, make `hasSession()` return `false`
and `readSession()` return `undefined` in `app/pageSession.ts`, rebuild, run, and restore.
