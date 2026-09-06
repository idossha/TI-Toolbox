# TI-Toolbox desktop — design specification (v3)

This is the visual and interaction contract for every screen in `desktop/`. Page agents implement
it; the design-system package (`src/renderer/ui/`) is the only place tokens and primitives live.
If a page needs something that is not here, it asks (report it) rather than inventing a variant.

v3 carries the "use the real estate" decisions U1–U10 from `dev/notes/v3-ui-program.md`, on top
of the density and information-architecture decisions of `dev/notes/v3-ux-redesign-plan.md` (§0
D1–D8, migration map §2, rules §3) — whose §1–§3 layout parts this document's §2 supersedes. Where
this document and the UI program disagree, **the program wins and this document is wrong** — say so.
Sections are numbered and never renumbered: lanes, specs and commits cite them by number.

## 0. What must not be lost

Everything below survived the redesign on purpose. A change that removes one of these is a
regression, not a simplification, no matter how much space it saves.

| | Why it stays |
|---|---|
| **The token set** — the cool-biased neutrals, the semantic separation, `--field` as a subject-only colour, `--on-accent`/`--on-danger`, the `--ink-3` restriction | Contrast-verified by `tests/unit/tokenContrast.test.ts`. v2 changed geometry and type, not one colour. |
| **The Jobs rail as the signature** | The one thing people remember: running work is always in view, on every screen. It gained two more heights; it did not become a page you have to visit. |
| **"Anything longer than a request is a job"** | The button shows loading only until the job is accepted, then a toast and a trace in the rail. No screen ever blocks on a computation. |
| **The Plan's content, and `POST /api/plan/{kind}`** | Resolved outputs, `exists`/`will_overwrite`, lock waits ("will queue behind #12"), cost. Telling the truth before you click Run is the second signature. v2 moved the *button* out of the panel; v3 turns the prose into a grid (§4.5). Not one field of the server contract changes. |
| **Presence chips** (raw / freesurfer / m2m / dwi / ct / leadfield) | The fastest read in the app: what a subject actually has. v3 moves them off the context bar and onto the Subjects page (U6) — they are columns of a table, not ambient chrome — but they are not simplified away. |
| **Schema-driven forms** (react-hook-form + ajv from `schema.json`, `forms/serverErrors.ts`) | Server validation maps onto fields. No hand-written duplicate of the contract. |
| **The discovery registry** (`app/registry.ts`, one `PageDef` per page directory) | A page is added by adding a directory. Nav, shortcuts and gating all derive from it. |
| **The ViewSpec server layer** (`tit/viewspec.py`, `GET /api/view/{kind}`) | The server resolves what to show; the client renders it. The viewer never assembles paths. |
| **Both themes, screenshotted** | Every screen in light and dark, now at 1280 × 800 **and** 1440 × 900, with `metrics.json` beside the pictures (§12). |
| **Copy discipline** | Sentence case, plain verbs, the same word for the same thing, no exclamation marks, no marketing voice. |

## 1. Subject, audience, job

TI-Toolbox is an instrument panel for a neuroscience lab: researchers configure long-running,
expensive computations (head models, FEM simulations, electrode optimizations, statistics), watch
them run for minutes to hours, and go to the results. The app's single job is **configure safely →
run with visibility → reach the result**. Everything on screen serves one of those three verbs.

Design stance: *calm precision*. Dense enough for scientists, breathable enough to scan. No
marketing gestures, no hero blocks, no decorative gradients. Numbers are first-class citizens.

## 2. Layouts

v3 rule (program U1): **every page uses the full width of the content area.** There is no 880 px
work-pane cap, no decorative outer margin, and no pane that exists without content. A page has at
most two panes — work, plus a *purposeful* right pane — and there are exactly three shapes.

```
Shape A — run page (U2)                          Shape B — browser (U4)                    Shape C — bleed (U5/V1)
┌──────┬─────────────────────┬────────────────┐  ┌──────┬───────┬─────────┬──────────┐  ┌──────┬──────────────────────┐
│ rail │ work pane           │ RUN PANEL      │  │ rail │ list  │ tree    │ preview  │  │ rail │ source bar        40 │
│ 216  │ (flush sections,    │ ┌────────────┐ │  │ 216  │ 200   │ flex    │ 40 %     │  │  56  ├──────────────────────┤
│      │  2-col at ≥1440)    │ │ PLAN grid  │ │  │      │       │         │          │  │      │ "what will open"     │
│      │                     │ ├────────────┤ │  │      │       │         │          │  │      │ fills the content    │
│      │                     │ │ TERMINAL   │ │  │      │       │         │          │  │      │ box, no right pane   │
│      ├─────────────────────┤ │ (fills)    │ │  └──────┴───────┴─────────┴──────────┘  └──────┴──────────────────────┘
│      │ action bar       44 │ └────────────┘ │
├──────┴─────────────────────┴────────────────┤   jobs rail 32 (⌘J → 260)
```

| shape | pages | work pane | right pane |
|---|---|---|---|
| **A `run`** | Pre-processing, Simulator, Optimizer, Analyzer | form, flush sections, sticky action bar | `RunPanel` — Plan grid over Terminal (§4.5, §4.6) |
| **B `browse`** | Results, Subjects, Jobs | internally split list → detail | preview / detail, **rendered only when it has content** |
| **C `bleed`** | Viewer | the source bar + the "what will open" summary | none — the Viewer has no right pane (§10) |

### 2.1 Exact widths

Content box = window width − nav rail. Page padding `--page-pad` is **16 px below 1440, 24 px at or
above it**; the browser shape negates it.

| | 1280 × 800 | 1440 × 900 |
|---|---|---|
| nav rail (icons below 1440; labels at ≥ 1440 — Q1, §9; program §0) | 56 | 216 |
| content box | 1224 × 704 | 1224 × 804 |
| **A** work pane / handle / run panel | 610 / 6 / **576** | 560 / 6 / **610** |
| **A** form grid columns | 1 or 2 (container ≥ 760 either size — see §4.2) | 2 (770 ≥ 760) |
| **B** list / tree / preview | 200 / 534 / 490 | 200 / 534 / 490 |
| **B** two-pane degenerate (Subjects, Jobs) | 1224 / 0 (no selection) | 1224 / 0 (no selection) |
| **C** source bar / stage | 40 / **1224 × 664** | 40 / **1224 × 764** |

The nav rail's 160 px of labels at ≥ 1440 is funded by the window's own 160 px of extra width
(1440 − 1280), so the content box is **1224 px wide at both sizes** — every page but the run shape
(A) sees identical horizontal room whether the window is 1280 or 1440 wide; only its height and
`--page-pad` change. The run panel and page padding grow at 1440 (400 px / 24 px vs. 360 px / 16 px),
which is why the work pane is *narrower* at 1440 (560) than at 1280 (610) despite the wider window.

The 760 px number is not arbitrary: it is the container width below which a label-left row
(`--field-label-w` 160 + a 240 px control + gutter) stops being honest two-up (§4.2). With the work
pane now 826 px at 1280 (Q1 raised it from the pre-Q1 666 px), a form section's container may
already clear 760 px at 1280 as well as 1440 — this is a **container** query, not a window-width
rule, so the exact column count depends on each section's own padding chain; verify against a
current `screens.spec.ts` capture rather than this table before relying on either count.

- **Right-pane sizing.** The **run panel** (A: Pre-processing, Simulator, Optimizer, Analyzer,
  Source) is a fraction of the *window*, not a fixed column: `clamp(320px, 45vw, calc(100% - 566px))`
  — 576 px at 1280, 610 px at 1440 (where the ceiling binds, not the 45 %), 900 px at 2000. The PLAN
  grid and the TERMINAL are documents like the Results preview, and the old fixed 360/400 px read as
  ~26 % of a wide window. The ceiling is the ≥ 560 px work-pane floor of §12.3
  (work = 100 % − 6 px handle − pane).
- **Right-pane range.** Resizable **36 vw to 70 vw** by drag or arrow keys — 461–896 at 1280,
  518–1008 at 1440, 720–1400 at 2000 (measured) — collapsible to a 16 px rail with `⌘⇧I`, expandable
  to the full content box, persisted per machine per page kind under `tit-pane-v3-<pageId>` (the
  version bump is what stops a width stored against an older default from pinning a user to the
  narrow pane). Both dividers read these limits: the `usePaneController` separator **and** the
  legacy `InspectorHandle` a page without a controller gets. They must not diverge — a legacy
  ceiling of 560 px, *below* the run pane's own default, is what made the pane snap narrower when
  the user dragged it wider.
- **Pages that pin a different default.** Jobs' detail column stays the fixed **360 below 1440 / 400
  at or above** (`rightPaneWidth`, a control column, not a document) and the Results preview stays
  `clamp(380px, 40%, 560px)` of the content box — both browse-shape (B) panes, both listed in the
  table above. They pass `minWidth: 320` so their own floors survive; they share the primitive, the
  70 vw ceiling and the `v3` key. Only the run shape's *default* and *floor* changed.
- **Never an empty pane.** A right pane whose model is empty is not rendered and the work pane takes
  its width — Jobs with nothing selected is one full-width table, not a table plus 360 px of
  "Select a job". This is the U1 rule in its enforceable form.

### 2.2 Breakpoints and minimums

**Minimum window 1024 × 680.**

| breakpoint | what changes | why |
|---|---|---|
| **1440** | `--page-pad` 16 → 24; run panel 360 → 400; nav rail 56 icons → 216 labelled (Q1, §9) | below 1440 a 216 px labelled rail would leave only 1064 px of content — too little for a run page's work pane beside its 3-D pane — so every page takes the icon rail below this width and gains the width back |
| **1100** | the right pane stops being a column and becomes a drawer over the work pane (`⌘⇧I` opens it) | below this a 360 px pane leaves the form under 600 px |
| **900** | `--page-pad` → 8 | last resort before the minimum |
| *container* **760** | `.form-grid` 2 → 1 column | measured on the pane, so a form in a dialog collapses on its own merits |

### 2.3 What the shell owns

- **The context bar carries global chrome, not scope** (U11, superseding U6's crumb — the maintainer's
  own words: "we still need to remove this from the top rail"). Left: `⌘K` search, wide, where the
  project crumb used to sit. Right: connection · running count. **No project crumb, no subject
  switcher, no presence chips, no "+ Add subjects"** — a project is inspected at Settings ▸ Project
  (reachable from the rail and the palette's "Open settings"); a subject is switched from the
  palette's Subjects section (`⌘P` opens the same palette — §6 rule 5) or from a page's own control;
  presence chips live on the Subjects page and batch selection is a page's own job (Pre-processing's
  Subjects section is the first to have one) — scope is chosen where the work is, not in a rail.
  `dev/notes/v3-pipelines-program.md` §6 U11 is the record of the decision.
- **The action bar owns commitment.** 44 px at the bottom of the *work pane*, on shape A only.
  Left: the plan digest (`planDigest(plan)`, §4.5), shown only while the run can start — when it is
  blocked the bar prints nothing and the disabled primary carries the reason as its tooltip (L3). Right: at most one secondary and
  exactly one primary, labelled from the plan. `⌘⏎` fires it from anywhere on the page.
  **It reserves its own height**: the work pane is not the scroller — its scroll child
  (`.page-layout-main-scroll`, `[data-page-work-scroll]`) is — so the bar is a `flex: none` sibling
  *outside* the scrollport and nothing can be painted under it at any scroll offset (L4, §4.7).
- **The right pane owns either the run or the result** — never a grab-bag inspector. On shape A it is
  the `RunPanel`; on shape B it is the preview of the selected row; on shape C it does not exist.
- **The jobs rail owns running work.** One component at three heights: rail 32 / panel 260 (`⌘J`,
  tabs Jobs / Console / Host / Report) / full page (`jobs` route). It is the app's signature and it
  stays on every screen.
- **There is no status bar.** The 24 px bottom rail and its per-page cell registry were removed
  wholesale: it printed a job/plan digest and a viewer read-out that nobody navigated by, and it
  cost every page a registration hook to fill. The one fact that had to survive is **whether the
  server is reachable**, and that now lives only in the context bar, as the connection dot next to
  the running-jobs count (`AppContextBar`, with `connection.reason` as its tooltip). The version
  string it also carried was already stated at Settings ▸ About the server.
- **No page header.** The nav rail already says which page this is. Settings and Help are the two
  exceptions (`showHeader`). *Today Subjects, Simulator and Results still print one — that is a
  v2 regression each lane removes.*
- **The command palette** (`cmdk`, `⌘K`) carries pages, subjects, runs, jobs, verbs and the theme.

## 3. Tokens (CSS variables, `src/renderer/ui/tokens.css`)

Light (default) → dark (`[data-theme="dark"]`, and `prefers-color-scheme: dark` when theme = system).

### 3.1 Colour — unchanged from v1, and deliberately so

| token | light | dark | use |
|---|---|---|---|
| `--bg` | `#F5F7FA` | `#0F1419` | **gutters only** (nav rail, jobs rail, resize dividers) |
| `--surface` | `#FFFFFF` | `#161C24` | **the app ground**, panes, tables |
| `--surface-2` | `#EEF2F6` | `#1E2630` | table headers, wells, code |
| `--line` | `#D8DEE6` | `#2A3441` | 1 px borders, dividers, section rules |
| `--line-strong` | `#B9C3CF` | `#3A4653` | focused/hovered borders |
| `--ink` | `#161D26` | `#E6EBF1` | primary text, changed values |
| `--ink-2` | `#4B5865` | `#A7B3BF` | labels, secondary text, default values |
| `--ink-3` | `#6B7784` | `#7D8A97` | placeholders and disabled **only** — never real copy |
| `--accent` | `#1F5BD7` | `#7FA6FF` | primary actions, links, running state, changed tick |
| `--accent-hover` | `#1948AE` | `#9DBBFF` | |
| `--accent-soft` | `#E6EEFC` | `#1B2A4A` | selected rows, soft chips |
| `--on-accent` / `--on-danger` | `#FFFFFF` | `#0F1419` | text **on** a solid accent/danger fill |
| `--success` / `--success-soft` | `#177A47` / `#E1F3EA` | `#5BCB8A` / `#12301F` | succeeded, present |
| `--warning` / `--warning-soft` | `#9A6412` / `#FBF0DA` | `#F0B95B` / `#3A2C10` | conflicts, skipped, waits, blocked plan |
| `--danger` / `--danger-soft` | `#B42318` / `#FAE3E0` | `#F28B7D` / `#3B1714` | failed, destructive, errors |
| `--field` / `--field-soft` | `#E25B22` / `#FCE9E0` | `#FF8A5B` / `#3A1E12` | *field* semantics only: TI_max/mTI chips (the "hot" colormap's orange — never for actions) |
| `--lost` | `#7C3AED` | `#B794F6` | job state `lost` |
| `--focus` | `#1F5BD7` | `#7FA6FF` | 2 px ring, 2 px offset |
| `--shadow-2` | `0 4px 12px -4px rgba(16,24,40,.16)` | `0 6px 20px -6px rgba(0,0,0,.7)` | popovers, drawers, dialogs, toasts |
| **`--canvas`** | `#0B0D10` | `#0B0D10` | render surfaces — **identical in both themes** (§10) |

Neutrals carry a slight cool (blue) bias — chosen, not default grey. Semantic colour is separate
from the accent and never used for decoration.

**Ground inversion.** The app ground is `--surface`; panes are delineated by 1 px `--line` rules,
not by white rectangles floating on grey. `--bg` survives only in gutters. Use the aliases
`--app-ground` and `--gutter` rather than naming `--surface`/`--bg` directly for this purpose.

**`--shadow-1` is off `.card`.** Elevation is reserved for things that are genuinely above the
page: Popover, Drawer, Dialog, the palette, Toast — all of which use `--shadow-2`.

### 3.2 Type

UI: **IBM Plex Sans** (self-hosted, 400/500/600). Data, paths, logs, values: **IBM Plex Mono**
(400/500). Fallbacks `system-ui, "Segoe UI", Helvetica, Arial, sans-serif` / `ui-monospace, Menlo,
monospace`. All numbers `font-variant-numeric: tabular-nums`.

| step | class | use |
|---|---|---|
| 11/14 | `.text-micro`, `.text-eyebrow` (.07em, 600, uppercase) | chips, eyebrows, section titles, table headers. **Chips and eyebrows only.** |
| 12/16 | `.text-caption` | field labels, help, value summaries, plan digest |
| **13/18** | `.text-body`, `.text-dense` — **the base**, set on `<body>` | every control, every table cell, everything else |
| 14/20 | `.text-prose` | running prose only: Help, About, a Callout's paragraph |
| 16/22 | `.text-emphasis`, `.text-section` (600) | card titles, page-level headings |
| 20/26 | `.text-page-title` (600) | the two pages that still have a title (Settings, Help) |

**The 12 px floor.** Anything a user is meant to read is at least 12 px, and 11 px never combines
with `--ink-3`. `tests/unit/cssRules.test.ts` scans the stylesheets for that pairing.

### 3.3 Space, shape, density

4 px grid (4, 8, 12, 16, 24, 32, 48). Radii: 4 px controls, 6 px panes, 999 px chips. Borders 1 px
`--line`.

| token | value | what it sizes |
|---|---|---|
| `--control-h` / `-sm` / `-lg` | 28 / 24 / 32 | every input, select, button (sm: in-table controls and chips; lg: a workflow's primary run action, including Source's in-card actions) |
| `--row-h` | 28 | table rows, field rows, list rows |
| `--section-header-h` | 28 | flush section headers |
| `--field-label-w` | 160 | the label column of a label-left field row |
| `--pane-pad` | 12 | pane and section body padding |
| `--context-bar-h` / `--action-bar-h` | 40 / 44 | shell strips |
| `--nav-w` / `--nav-w-icons` | 216 / 56 | the rail, labelled and icon-only |
| `--right-pane-w` / `--right-pane-w-lg` | 360 / 400 | the run panel and every other right pane (§2.1); `--right-pane-w-lg` applies at ≥ 1440 |
| `--inspector-w` | 300 | **legacy alias**, kept so a v2 page renders unchanged; no v3 page sets it |
| `--page-pad` / `--page-pad-sm` | 24 / 16 | the shell's content padding; a full-bleed page negates exactly this |

`--control-height`, `--control-height-sm/lg` and `--row-height` remain as aliases of the canonical
names so no page needs an edit to pick the new numbers up.

Control widths: numbers 96–128 px with a unit suffix inside the control; **a select or combobox
fills its column** (capped at 420 px on a full-bleed or stacked row, where "the column" is the whole
pane); text fills its column. The 200–280 px select was written for a 666 px work pane and left a
ragged right edge and ~110 px of ground at the end of every row once the pane became 826 px.
Nothing is centred except a whole-page empty state.

**One density.** There is no comfortable/compact switch: two densities means two sets of
screenshots and two sets of bugs.

### 3.4 Motion and icons

150 ms ease-out on hover/focus/expand; job traces animate width; the liveness pulse is a 1.6 s
opacity loop; a refetch is a 1.2 s indeterminate sweep. `prefers-reduced-motion` disables all of
it. No page transitions. Icons: `lucide-react`, 12–14 px inside controls, 16 px in buttons, 20 px
in the nav rail; always with a label or a tooltip, never icon-only without `aria-label`.

## 4. Layout, forms and state

### 4.1 Page layout

`PageLayout` has three variants, one right pane, and three slots.

- **`run`** — work pane + `RunPanel` right pane + sticky action bar. The work pane takes every pixel
  the right pane does not (§2.1). No max width.
- **`browse`** — work pane (internally split: list → tree) + an optional preview right pane sized as
  a percentage. No padding on the panes themselves; 1 px `--line` rules divide them.
- **`bleed`** — no padding, no max width; the page fills the shell's content box. The Viewer is the
  reason it exists.
- Slots: `rightPane` content, `actionBar`, and an opt-in header (`showHeader` + `title`/`purpose`,
  or a built `header` node) that only Settings and Help use.

The v2 names survive so no page needs an edit to keep working: `variant="standard"` maps to `run`
without a right pane, `variant="full-bleed"` maps to `bleed`, and `inspector` / `contextPanel` still
render as the right pane at `inspectorWidth ?? 300`. What is **gone in v3** is the 880 px work-pane
cap and the "Plan block on top, then page-specific blocks" inspector: the Plan is a grid inside the
`RunPanel` (§4.5), and a page has no other blocks to stack on it.

### 4.2 Forms — nine rules

1. **Label-left rows.** `Field` is a 28 px grid row: label in a `--field-label-w` gutter,
   right-aligned, 12 px `--ink-2`; control right. No third line. Cost per field: 28 px, down from
   70. `layout="stacked"` and `fullBleed` are the only escapes.
2. **Help is an (i) popover, units are a suffix.** A sentence of help opens from a 14 px trigger
   next to the label; `mm`, `mA`, `V/m` live inside the control (`NumberInput`'s `unit`). Help is
   never a printed third line, and a multi-line explanatory `Callout` inside a form is a popover.
3. **Full-bleed exceptions.** **Any `.data-table-container`**, `ElectrodePairsEditor`,
   `KeyValueTable`, `PathInput`, chip `MultiSelect`, consoles and callouts drop the label gutter and
   span the row. They request it structurally (a `:has()` rule in `components.css`), so a page
   written before the `fullBleed` prop existed still gets it. The data-table clause is what makes
   the rule true of the Analyzer's sphere table, which was written as a `Field` around a
   `.data-table-container` and therefore kept a 160 px label gutter it should never have had.
4. **Sections, not cards.** `FormSection` is a flush `<section>` whose **header is a 28 px band on
   `--surface-2`** — the same object §4.3 defines for a table header — over a 4/8 px body, with no
   border box and no shadow. Chrome per section: 40 px, down from 94. The header is **not sticky**
   (L4, §4.7): a sticky header inside the pane's own scroller paints over its own body, and five
   Optimizer controls were measured hit-testing to it. `Card` stays for Workbench cards and result
   summaries — genuinely separate objects on a page. The Subjects control (§3, `SubjectsField`)
   draws the same band, because it is the first section of every run page.
5. **A collapsed section states its values.** `summary` is right-aligned in the header
   ("ellipse · 8×8 mm · gel 4 mm"). A section with a non-default child takes an accent dot; one
   with an error takes a `--danger` dot, visible while collapsed. `⋯ ▸ Reset section` restores
   defaults.
6. **Disclosure is safe or it does not happen.** Tier 1 (what the plan cannot resolve for you:
   subject, ROI, montage/leadfield, goal, space) is always open — typically 4–7 fields. Tier 2
   (anything with a defensible default) starts collapsed. Tier 3 (table editors) is a dialog.
   **An `advanced` group holding non-default values force-opens and badges "Advanced · N changed".**
   A parameter never sits out of sight doing something to the science.
7. **Defaults are visible, changes are marked.** A field at its schema default renders its value in
   `--ink-2`; a changed one renders in `--ink` and takes a 2 px accent tick in the label gutter
   (`changed` prop, or `useChangedFields(values, defaults)`). This is what buys the right to
   collapse Tier 2 by default.
8. **Validation is inline and never hidden.** Validate on blur, then on change once a field has
   errored. The errored control takes a 1 px `--danger` border and its message replaces the help
   slot in the same row. **Run stays enabled**; pressing it with errors focuses the first one. The
   action bar shows the count, the Plan lists them with jump-to-field links, and the owning section
   carries the danger dot. Preflight problems (an existing output, a lock conflict, a missing
   leadfield) are warnings in the Plan and never block the button; only the overwrite `AlertDialog`
   blocks, and only at commit.

9. **One idiom per idea: a small exclusive choice is a `SegmentedControl`.** Two to four short,
   mutually exclusive options — a mode, a space, a scope, a target type — render as
   `SegmentedControl` with an `aria-label`, on every page, in one 28 px row. `RadioGroup` is for
   the case a segment cannot carry: five or more options, or options that each need a sentence of
   their own (`layout="cards"`). The failure it prevents, measured: "Cortical / Subcortical /
   Spherical" was a `RadioGroup` inside `pages/_shared/roi` on the Optimizer and a
   `SegmentedControl` on the Analyzer — **one idea, two controls, on two pages a user moves
   between** — and the ROI picker mixed both idioms inside itself, a segment for the ROI type 40 px
   above a radio pair for the coordinate space. Both render `role="radiogroup"` / `role="radio"`,
   so the swap is invisible to every existing spec and to a screen reader; what changes is that a
   user learns the control once. (`tests/e2e/roi-idiom.spec.ts` asserts it on both pages.)

Two-up rows: `.form-grid` is `repeat(2, minmax(0, 1fr))` with a 8/24 px gap, collapsing to one
column by container query at **760 px** — the width below which a label-left row stops being
honest.

### 4.3 Tables

Sticky 28 px header on `--surface-2`, 11 px uppercase `--ink-2`; 28 px body rows; hover
`--accent-soft` at 40 %; selected row `--accent-soft` with a 2 px accent left bar; right-aligned
tabular numbers; horizontal scroll inside the table's own container — the page never scrolls
sideways. Wide content (consoles, CSV tables, plots) gets `overflow: auto` on its own container.

### 4.4 State matrix

Every surface answers the same four questions the same way. "First load" is the only place a
skeleton appears.

| surface | first load | empty | failed load | refetch |
|---|---|---|---|---|
| **table** | `Skeleton rows={n}` sized to the real row count | `emptyMessage`, one line, inside the table body | `InlineError` above the table, retry in it | 2 px `RefetchBar`, rows stay |
| **stage card** (Workbench) | skeleton at the card's real height | chip reads `missing` + the one next action | `InlineError` in the card | bar on the card |
| **right pane block** (plan grid, preview, detail) | 2–3 skeleton rows, or `n` matrix rows sized to the selected subjects | `EmptyState variant="inline"`, ≤ 2 lines, left/top aligned, one ghost action — or the pane is not rendered at all (§2.1) | `InlineError` in the block | bar under the block header |
| **viewport** | per-dataset progress with bytes over `--canvas` | "Nothing loaded" over `--canvas`, one action | error text over `--canvas`, retry | none — the canvas keeps what it has |
| **whole page** | skeletons in the panes | centred `EmptyState` with icon, one sentence, one primary | `InlineError` in the work pane | 2 px bar under the context bar |
| **disconnected** | — | — | warning strip in the context bar, forms stay editable, the action bar's primary disables **with the reason as its tooltip** | reconnect is automatic |

**A failed data load is never a toast.** A toast disappears and takes the explanation with it. Job
failures *are* toasts (persistent, with "Open job ▸") because the failure is not about the surface
you are looking at.

**A page whose populated state is a table takes the *table* row, not the whole-page row.** Its
empty state is that same table — column headers, the message inside the body, ground rows
(`.run-table-filler`, `.data-table-filler`) down to the bottom of the pane — plus one action. The
whole-page centred `EmptyState` is for a page with no table shape to show. The failure it prevents,
measured at 1280×800: Jobs with no jobs was **99.1 % dead** — one centred sentence in a 1224 × 704
box that told a first-time user nothing about what a job even looks like here — and
`panel-subject-info` 86.6 %. As the table with its own shape they are 14.7 % and 21.1 %.

**Ground rows belong to the component that renders the rows, and a row cap is a default, not a
ceiling.** A page asks for them (`fill`, or `minRows` for a fixed floor) and the control measures
the room and draws real `<tr>`s into it. The failure it prevents, measured: `ui/DataTable` owned
its own `<tr>`s and would not draw ground rows, so `pages/jobs/jobs-page.css` and
`pages/panels/panels.css` each painted the *same* repeating gradient behind the table — one rule
written twice, in two files that do not know about each other, at a pitch that only happened to
match the rows above it — and `pages/panels/panels.css` reached into `pages/_shared` a third time
to lift `.run-subject-scroll`'s `max-height: 176px` for the Source panel, because a constant chosen
for a run page's first screen is not the answer on the page whose whole job is choosing subjects.
With the room measured instead, Pre-processing's table is 12 rows at 1440×900 and 26 at 1440×1300
where it was five at any size, and the three copies of the rule are one.

### 4.4.1 Choosing who takes part: a set, or a list of rows

`pages/_shared/subjects/SubjectsField` is the one control for a **set** of subjects, and it is the
first section of every page that takes one (§3, J1–J4).

Three panels cannot use it, and the reason is a property of their science rather than a preference:
`nifti-group-average`, `cluster-permutation` and `nilearn-visuals` submit a list of
`(subject, simulation, role)` **rows**, and the same subject may legitimately appear twice — a
paired permutation test and a diff pair are exactly that design. A set control cannot express it.

They use `pages/panels/_participants/ParticipantsField` instead, which is the same grammar over a
row list: the same 28 px `--surface-2` header band, the same title word (**Subjects**), the same
one-line summary carrying J4's semantics — and stating `4 rows · 3 subjects · …` when a subject
repeats, which is precisely what a set could not say — the same table with real column headers, the
same "Why not" column that exists only while some row has a reason, and the same blocked sentence
(`participantsBlockedReason`, naming the row the way `subjectsBlockedReason` names the subject). It
drops only what a row list has no meaning for: the filter and select-all (set operations over a
catalog) and the disclosure (the rows *are* the page's first decision). `participants.css` writes
its own class names — a class names what it styles — and
`tests/unit/participants-field.test.tsx` compares the two stylesheets declaration by declaration so
they cannot drift into two grammars.

**The rule: a fourth idiom for "who takes part" is a defect.** If a page cannot use `SubjectsField`,
it uses `ParticipantsField`; if it can use neither, that is a design decision to be recorded with
the measurement that forced it, not a new control.

### 4.4.2 What survives a navigation — the user's state and the derived state

**A page comes back exactly as the user left it, for the open project session.** Visited pages now
retain their component tree and live canvas (§13). Previously, leaving a page unmounted it and state in
`useState`, so a step onto Results and back built a brand-new page: measured on 2026-09-04 against
the running container, `tests/e2e/real/page-memory.spec.ts` failed on **all four** run pages —
Simulator's `Electrodes` closed by hand came back open, the Optimizer's "After the search" opened by
hand came back closed and its typed run name was gone, the work pane's 55 px scroll offset went to
0, the right pane fell back from Terminal to Scene, and the Analyzer's table went from 1 row to 2.
The maintainer reported it as *"the state of the tabs is not persistent: jumping between tabs resets
them"*.

The line, and it is the whole rule:

| | Owner | Rule |
|---|---|---|
| A section the user opened or closed, the Terminal/Scene tab they picked, where they scrolled, the segment or sub-tab they chose, what they typed, which subjects they ticked | **the user** | survives navigation for the life of the session; nothing recomputes it |
| The fill controller's first-open decision for a section the user has **never** touched on this page in this session (§4.7) | **derived** | recomputed on every mount and at every pane size |

Three consequences, each with the failure it prevents:

1. **A user-touched section outranks both the fill controller and a `fill` table.** The controller
   never opens or closes one, and `SubjectsField`'s ground rows give room back to it rather than
   taking room from it — the arbitration that used to be settled by whichever measured first.
   `data-fill-section` carries `data-fill-user="open"|"closed"` while the state is the user's and
   nothing while it is still the controller's, the same contract `RunPaneTabs` publishes as
   `data-chosen`. Without the attribute a test (or a person) cannot tell a section that *is* open
   from one that will *stay* open, and a spec that read one for the other failed intermittently.
2. **In memory, not `localStorage`.** A preference (theme §7, pane width §2.1) describes how the app
   should look and survives a restart. A half-configured run does not: restoring yesterday's ROI,
   subject set and run name into a fresh launch would offer a job the user never assembled, and the
   bag carries no project identity, so it would follow them to a different dataset. Closing the app
   is the reset; navigating is not. `app/pageSession.ts` is the store; `usePageSession(key, initial)`
   is a drop-in for `useState`, so session-scoping a field is one line and a transient (a dialog's
   open flag, an in-flight `running`) stays `useState` on purpose.
3. **The live renderer is part of page state.** A session bag alone cannot preserve its camera,
   surfaces and uploaded buffers. The 2026-09-04 maintainer requirement supersedes the embed
   migration's visible-only lifetime: visited pages and their canvases remain mounted, and a
   retained canvas is the claim `page-memory.spec.ts` measures — the same DOM node, a live GL
   context, and zero guide requests to redraw it. Contexts are released on project close/switch. See §13 and `docs/ARCHITECTURE.md` §2.

### 4.5 Run panel

Every run page (Pre-processing, Simulator, Optimizer, Analyzer) carries the same right pane
(program U2): a **Plan grid** on top and a **Terminal** filling the rest. Nothing else goes in it.
It is one component, `RunPanel`, and the four pages differ only by `kind`.

```
┌ RUN PANEL 360 ──────────────────────────────┐
│ PLAN                                    ⟳  │ 24  header: eyebrow + refetch
│ ┌──────┬──────┬──────┬──────┐              │
│ │ JOBS │ CPUS │  MEM │ WAITS│              │ 40  stats strip: four tiles
│ │   2  │   8  │ 16 GB│   0  │              │
│ └──────┴──────┴──────┴──────┘              │
│         dicom   charm   fs    tissue        │ 24  matrix header (stage ids)
│  ernie    new    new    new    new          │ 24  one row per subject
│  101      new   skip   over…    ·           │ 24
│  new · skip · overwrite · blocked · wait    │ 20  legend, once
│  ⚠ 101 — charm output exists and will be    │     warnings callout
│    replaced.                                │
├─────────────────────────────────────────────┤
│ TERMINAL  pre · ernie · running 4m12s  ⌕ ⇩ ⧉│ 24  header: job identity + filter/follow/reveal
│ 12:04:01 INFO  charm: meshing …             │
│ 12:04:09 WARN  low contrast in T2           │     fills the remaining height, min 180
│ 12:04:11 INFO  charm: 847k nodes            │
└─────────────────────────────────────────────┘
```

**Stats strip.** Four tiles, equal width, 40 px tall, 8 px gap: `JOBS`, `CPUS`, `MEM`, `WAITS`.
11 px uppercase `--ink-2` label over a 16 px tabular value in `--ink`. Units are suffixes inside the
value (`16 GB`). A zero is a zero, never a dash — these four always have a value once a plan
resolves. `WAITS` takes `--warning` ink when non-zero.

**Subject × stage matrix.** Rows are subjects in plan order, columns are the stages the plan
returned for this kind, header row 24 px, body rows 24 px, first column is the subject id in mono.
Each cell is exactly one chip from the fixed vocabulary — never free text, never a repeated
"Output" label:

| chip | tokens | means | derived from `PlanResult` |
|---|---|---|---|
| `new` | `--success-soft` / `--success` | nothing exists; this stage will be created | `job.exists === false` |
| `skip` | `--surface-2` / `--ink-2` | output exists and the config keeps it | `job.exists && !job.will_overwrite` |
| `overwrite` | `--warning-soft` / `--warning` | output exists and will be replaced | `job.exists && job.will_overwrite` |
| `blocked` | `--danger-soft` / `--danger` | a precondition is missing; this stage cannot run | a `warnings[]` entry naming this subject *and* this stage |
| `wait` | `--accent-soft` / `--accent` | queues behind a running job | a `lock_conflicts[]` entry whose `subject` is this row |

Precedence when more than one applies: **blocked > wait > overwrite > skip > new**. A cell with no
planned job renders a 12 px `·` in `--ink-3` — a stage that is not part of this run is visibly not
part of it, and an empty box would read as a bug. **One legend**, 20 px, under the matrix, listing
the five chips in that order; it is the only place the words appear as a key.

Hovering a cell shows its `output_dir` in a tooltip, mono, truncated from the left. Clicking a row
pins the Terminal to that subject's job (§4.6).

**Warnings callout.** `Callout kind="warning" title="Before you run this"`, one line per
`warnings[]` entry, under the legend. It is the *only* free text in the panel. Warnings never
disable the primary action; only the overwrite `AlertDialog` blocks, and only at commit (§4.2 r8).

**Empty state.** With no subject selected the panel renders, in the plan's place, a two-line inline
`EmptyState` — "Select a subject to see the plan." + a ghost `Choose subject ⌘P` — left- and
top-aligned. The stats strip is not drawn with dashes in it. The Terminal below keeps its own empty
state, so the pane is never blank.

**Loading / failed.** First load: a 40 px skeleton for the strip and `n` skeleton rows for the
matrix, `n` = the number of selected subjects, so the panel does not resize when the data lands.
Refetch: a 2 px `RefetchBar` under the header, rows stay. Failure: `InlineError` with retry, in
place of the grid; the Terminal is unaffected.

**The action-bar digest is derived, not written.** `planDigest(plan)` builds one line from the same
model:

```
`${jobs} job${s} · ${cpus} CPU · ${memoryGb} GB`
  + (overwrites ? ` · ${overwrites} overwrite` : "")
  + (waits      ? ` · ${waits} wait`           : "")
```

`jobs`, `cpus` and `memoryGb` come from the stats strip; `overwrites` counts cells resolving to
`overwrite`, `waits` counts `lock_conflicts`. When `jobs === 0` the digest is the plan's
`blockedReason` — but that string is **not printed anywhere**: the digest is suppressed and the
single signal that a run cannot start is the primary itself, `disabled`, in the
disabled treatment (§5), **with that string as its tooltip** (maintainer call, 2026-09; supersedes
the earlier "never a silent disabled button"). The digest and the strip cannot disagree because they
read one object.

### 4.6 Terminal

`JobTerminal` is the live console of the run page you are on. It exists so nobody has to open the
jobs panel to find out what their own run is doing. It is a caller of the one shared renderer —
`ui/Jobs.tsx`'s `JobConsole`, also used by the Jobs rail and the gallery — over the one shared pure
transform, `app/jobs/logLines.ts`. Jobs-detail `<pre>` excerpts are diagnostic records, not
terminals.

**Which job it follows**, in order, first match wins:

1. the pinned job, if the user clicked a plan row or a job trace (`pinnedJobId`);
2. the **newest running or queued** job whose `kind` is one of the page's kinds *and* whose subjects
   intersect the page's current subject selection;
3. the same, dropping the subject filter (a run started from this page before the selection changed).

There is deliberately no fourth rule. **A finished job is never followed automatically** (FXU2):
opening a tab showed `pre · 102 · succeeded 12s` with a full DICOM log, which reads as "a job is
happening" on a page that ran nothing. A finished log is shown only because someone asked for it —
the Jobs page, a plan cell, or this pane's pin button — and a pin the user made is page-session
state, so it survives navigation within the session.

Ties break on `created_at` descending. Starting a new run of the page's kind clears the pin. The
header states the resolved identity — `pre · ernie · running 4m12s` — so "which log am I reading"
is never a guess; the state word takes its `JobStateChip` colour.

**Behaviour.** Virtualised (`VirtualList`, 18 px rows, mono 12 px). Follow-tail on by default; it
turns itself off when the user scrolls more than 40 px off the bottom and back on when they return.
A filter box narrows by substring. **Clear is local and presentational**: a per-source sequence
watermark hides the lines currently on screen. It never deletes server events or truncates a log
file; lines with a higher sequence appear normally, and changing job/file source resets the
watermark while Follow is retained and the text filter resets. Level colours are tokens, never
literals: `debug` `--ink-3`,
`info` `--ink`, `warning` `--warning`, `error` `--danger`. **Reveal log** is a 24 px icon button in
the header (`aria-label="Reveal log file"`) wired to the existing `onRevealLogFile`.

**The Jobs page's Raw log is the same console, not a `<pre>`** (2026-09-06). The Raw log tab fills
the detail pane with the shared renderer rather than a fixed-height excerpt under a "Load more"
button, so "what did it print" has one answer with one set of behaviours — follow-tail, filter,
level colours, Reveal — wherever it is asked. The run page's Terminal and the Jobs detail pane are
two callers of one component; neither is a summary of the other.

**Height.** The Terminal fills the run panel below the plan grid and never shrinks below **180 px**:
the plan grid is capped at 45 % of the panel height and scrolls internally past that, so a
twelve-subject plan cannot squeeze the log out of existence.

**Empty state.** One quiet line, `--ink-2`, no icon and no button: *"No job running. Start one with
Run, or pick a job from the Jobs page."*, with the header reading `Terminal · No job`. The pane is
an empty console and nothing else — no tail of the last log file, no "What will run" step list:
content in the log pane of a page you merely opened is what made an idle tab look busy.

### 4.7 The run-page skeleton, and the four numbers it is held to

Plan of record `dev/notes/v3-scene-ia-plan.md` §4 (L1–L5). Pre-processing, Simulator, Optimizer and
Analyzer are **one skeleton**, and a page may add sections but never reorder it:

```
work pane                                        right pane
┌───────────────────────────────────────────┐   ┌──────────────┐
│ SUBJECTS  ernie · one job per subject  [⋯]│28 │ PLAN         │  Plan grid (§4.5)
├───────────────────────────────────────────┤   ├──────────────┤
│ TIER-1 SECTION            summary         │28 │ Terminal·Scene│ tab host (S7)
│   label-left rows, two-up at ≥ 720 px     │   │              │
├───────────────────────────────────────────┤   │              │
│ TIER-1 SECTION            summary         │   │              │
├───────────────────────────────────────────┤   │              │
│ ▸ DETAIL SECTION          summary         │   │              │  collapsed, states its values
├───────────────────────────────────────────┤   └──────────────┘
│ digest · blocked reason        [Run …] ⌘⏎ │44  action bar — OUTSIDE the scrollport
└───────────────────────────────────────────┘
```

- **L1 order.** Subjects (always first, always `data-tier="1"`, the shared `SubjectsField` §3) → the
  page's Tier-1 decisions → collapsible detail sections → the action bar. The right pane is the
  `RunPanel`: Plan on top, tabbed **Terminal · Scene** below (§4.5, §4.6, S7).
- **L2 Tier-1 is what changes the science**: the subject set, the method/mode, the target or
  montage, the net, the output name. Everything with a defensible default — electrode geometry,
  conductivity, solver knobs, the existing-output policy — is a collapsed section with a summary.
  Tier-1 is marked `data-tier="1"` in the DOM, because that is what `firstScreenControls` reads.
- **L3 the action bar is the only place a run starts**, and it always carries the digest, the
  blocked reason (naming the subject that cannot run) and the Run control. §2.3.
- **L4 nothing overlaps.** The work pane is a clipping box; its scroll child is the scroller; the
  action bar is a `flex: none` sibling outside it. `FormSection`'s header is not sticky, for the
  same reason. Asserted by hit-testing, not by comparing rectangles — `tests/e2e/layout.spec.ts`
  scans the whole scroll range in 40 px steps and calls `document.elementFromPoint` at the centre
  of every enabled control, which is the test Chromium itself applies to a click.
- **L5 the numbers**, at 1280×800 and 1440×900, in both themes, on the populated state:

  | | limit | preprocess | simulator | optimizer | analyzer |
  |---|---|---|---|---|---|
  | dead space, 1280×800 | ≤ 45 % | 36.3 % | 34.4 % | 41.6 % | 40.8 % |
  | dead space, 1440×900 | ≤ 45 % | 42.0 % | 38.3 % | 42.8 % | 43.5 % |
  | Tier-1 controls below the fold | 0 | 0 / 21 | 0 / 16 | 0 / 18 | 0 / 28 |
  | controls under the action bar | 0 | 0 | 0 | 0 | 0 |
  | horizontal page scroll | 0 px | 0 | 0 | 0 | 0 |

  Measured 2026-09-04 by `tests/e2e/layout.spec.ts` against the mock server, offscreen. That spec
  is the gate; `screens.spec.ts` remains the instrument that writes `metrics.json` and the pictures.

#### 4.7.1 The panel pages hold to the same skeleton and the same numbers

The four job-submitting panels are run pages with a smaller vocabulary, so they read the same way:
**Subjects first** (`SubjectsField`, or `ParticipantsField` where the model is a row list, §4.4.1),
then what will run, then the plan beside it, then the **action bar** — one digest, one blocked
reason, one primary (`panelDigest`, `pages/panels/_shared.ts`). Before this each of the four
reported its problems as a list of sentences above a Run button that stayed enabled and never said
what it was about to cost.

Two-column body (`.panel-page-split`), not a single 826 px column in a 1224 px pane: who takes part
on the left, growing to the pane with ground rows; how to analyse them on the right. **Measured and
rejected** — moving the Plan into a `PageLayout` right pane, as the four run pages do: it improved
the work pane (cluster-permutation 42.9 → 40.4 % dead) and made the *page* worse, 46.9 → 58.1 %,
because a 360 px column holding one short Plan card is 70 % ground, which is the empty pane U1
forbids. A plan four lines long belongs beside the form.

The same L5a limit, on the state a user lands on — nothing chosen, nothing run:

  | | limit | source | cluster-perm | nifti-avg | nilearn | subject-info | jobs |
  |---|---|---|---|---|---|---|---|
  | dead space, 1280×800 | ≤ 45 % | 41.7 % | 37.6 % | 41.5 % | 38.8 % | 18.9 % | 12.5 % |
  | dead space, 1440×900 | ≤ 45 % | 43.7 % | 35.6 % | 44.0 % | 42.3 % | 19.8 % | 15.7 % |
  | before, 1280×800 | — | 82.3 % | 74.4 % | 65.3 % | 71.1 % | 86.6 % | 99.1 % |

  Identical in both themes (measured, not assumed). Gate: `tests/e2e/panels-shape.spec.ts`.

### 4.8 Selection — one list, everywhere

Anything chosen out of a set — subjects, montages, ROI regions, electrodes, participants, jobs — is
`ui/SelectionList`. There is no second selection idiom.

- Click selects one; ⇧-click takes the range from the last click; ⌘/Ctrl-click toggles one; ⌘A takes
  everything the filter is showing; Esc clears it.
- A checkbox column is the visible form of the same toggle. A row is never *only* clickable and never
  *only* tickable.
- An always-on filter box; `All · None` are the only bulk buttons; an `N of M selected` badge is the
  only place the count is stated.
- A bulk button acts on the **visible** rows. A row the filter is hiding keeps its state.
- The value's order is the order rows were chosen, and that is the order jobs are submitted in.
- A row that cannot be used keeps its checkbox and states its reason in the row (the reason is what
  Run then prints); `bulkExclude` keeps it out of `All`, so a bulk convenience can never create a
  blocked run.
- No drag-to-reorder anywhere, and no per-item options: options apply to the whole selection.
- Where a form field has no room for a list, `SelectionPicker` puts the same list in a dialog behind
  a trigger that states the selection in words (`F7, P7, +3 more`). Single-value fields — each slot
  of an electrode pair — use `mode="single"`.
- `role="listbox"`/`option` for a list of things; `role="grid"`/`row` where the list is a real
  multi-column table (the Jobs page). Both are keyboard-navigable with a roving
  `aria-activedescendant`. Virtualised past 150 visible rows.

**No receipt.** A run page states its batch **twice and no more**: the plan grid in the run pane
(subject × stage, one cell per job) and the action bar's digest ("1 job · 2 CPU · 6 GB"). Both are
renderings of one `PlanModel`, so they cannot disagree, and the grid is a click away from the Run
button it confirms. A third rendering — the run receipt, a strip above Run repeating the count, the
first 15 rows and the existing-outputs line — was removed 2026-09-06 (maintainer: "we have enough
info overlapping on the right planning window"). What survived it is `planCounts()` in
`pages/_shared/run/planModel`, which the pages use for the number the existing-outputs dialog asks
about.

**Existing outputs** are one question with three answers, on every run page:
`pages/_shared/run/ExistingOutputsDialog` — Skip (default, its label counting the batch: "Skip 3, run
1") / Replace and rerun / Cancel.

### 4.9 Electrodes and channels in the scene pane

In the montage scene pane, an electrode's **colour is its whole state**: neutral grey when it is in
no channel, 35 % grey when it is unusable, and its channel's hue when it is placed. No ring, no
outline, no second glyph. Since 2026-09-06 that is structural rather than a message we decline to
send: the pane is our own renderer (§13), and a selected marker's footprint is byte-identical to an
idle one's, so "no ring" is a pixel assertion. Names are shown for placed electrodes only: 185 labels over a head is not a
legend, it is a fog. The channel hues are **Okabe-Ito** and are the same colours the pair editor and
the channel legend use, so "pair 2 is orange" means one thing everywhere; every hue comes from
`channelCss()`, never from a literal.

A **channel legend** sits above the pane: one chip per pair, its swatch and `E1 → E2`, and clicking a
chip makes that pair the one the next 3-D click fills. The active pair is stated by ring *and* ink,
never by hue alone. Click an idle dot to fill the next free slot of the active pair; click a selected
dot to remove it and park the cursor on the vacated slot. The form is the source of truth and the
markers re-derive from it in one pass — there is no partial update to get wrong.

### 4.10 Jobs table

*Added 2026-09-06 (`docs/ARCHITECTURE.md` §7.5), extended the same day to the Optimizer. It removes
the page-level subject set from all three run pages that submit batches, and with it §4.4.1's "a
set" answer for them.*

A run page that submits **more than one job at a time** describes the run as a table in which **one
row is one job**, and the row owns every input that differs between jobs. This is now the grammar of
all three: the Simulator's row is `Subject · Source · EEG net · Montage · Pairs · Currents`; the
Analyzer's is `Subject · Simulation · Space · Field`; the Optimizer's is
`Subject · Method · Net / leadfield · Goal` — five methods (flex, adaptive, pareto, ex, mEx) in the
Method cell, where the page previously described exactly one search.

**A row is two lines, and the split is not cosmetic.** Line 1 carries the columns a user *scans*
down to compare rows — the identifying four or five, never truncated, in a resolver-sized colgroup.
Line 2 carries what only makes sense *within* that row: the Simulator's per-channel pairs and their
own currents, the Analyzer's and the Optimizer's target sentence. Line 2 is prose, not columns, so
it can be long, and it can change length (TI's two pairs to mTI's four) without any column moving
anywhere. Anything richer than a sentence — an ROI with an atlas, a hemisphere and a label set —
opens a **dialog** from the row, so the table stays a table.

1. **The row owns its subject.** A page with a jobs table has no page-level subject control. The
   subject grammar (§4.4.1, J3) still applies, inside the cell: a subject that cannot run here is
   *listed with its reason* and cannot be picked.
2. **A cell may change with the row, never the layout.** Column widths come from a resolver whose
   total is the container by construction, so a row switching source (or polarity) changes what is
   *inside* its cells and moves nothing anywhere else in the table.
3. **Incomplete is allowed.** A half-filled row is shown and is not planned. One predicate
   (`isRunnableRow`) is the gate, and the disabled Run states the *table* being empty before it
   states anything about subjects.
4. **Duplicate, not fan-out.** Repeating a job for another subject is one click on the row —
   duplicate it and change the subject. There is no cross-product button and no "quick add every
   subject with this simulation" (removed 2026-09-06): the table never expands itself on the user's
   behalf. `+ Add row`, duplicate and remove are the whole gesture set.
5. **What is global stays global.** Properties of the *run* rather than of a job — electrode
   geometry, conductivity, output fields, the analysis ROI — remain page-level sections.
6. **A group is a switch over the rows,** not a separate mode with its own selection: the rows name
   the cohort, and rows that disagree about what a cohort job can only do once are refused with the
   reason on the button. It rides the table's own footer line — `+ Add row` on the left, the switch
   right-aligned on the same row with its label and an (i) popover, and no separate field label
   repeating the word the switch already says (maintainer, 2026-09-06).
7. **The table survives the run.** Submitting does not empty it.
8. **A row may be a different KIND of job.** Where a page's rows submit as more than one job kind —
   the Optimizer's flex and ex families — one Run is one submission *per kind*, and the page says
   so rather than implying a single atomic batch.
9. **A cell with nothing to decide says so.** A column meaningless for a row's method prints a muted
   `—` with the reason in its `title`, never a disabled control, which reads as a choice the user
   has failed to make.

**Authoring is not choosing.** The Simulator's free-hand *editor* is its own section, opened on
demand; picking a saved placement in a row is a different act from writing one, the same split the
montage catalog already had. A permanently-rendered coordinate table also made the section tall
enough to change the run shape's auto-open decision across a navigation, which §4.4.2 forbids.

## 5. Components (`src/renderer/ui/`) — the only primitives pages may use

The exact props, file paths and "must keep working" lists for every v3 addition below live in
`dev/notes/v3-ui-program/u0-design-notes.md` §3; the wireframe each one appears in lives in
`dev/notes/v3-ui-program/wireframes.md`. Lanes code against those signatures verbatim.


**Buttons.** `primary` (accent fill), `secondary` (surface + `--line`), `ghost`, `destructive`.
States: hover, active, focus-visible ring, **disabled** (not a dimmed copy of the enabled control:
flat `--surface-2`, `--line` hairline, `--ink-3` label, `cursor: not-allowed` — it is the only
signal that an action is unavailable, so it must read as a different control), **loading** (spinner
replaces the icon, label and width stay — a busy primary keeps its accent fill). Sizes sm/md/lg = 24/28/32. `IconButton` requires `aria-label`. Primary actions are
verbs: "Run simulation", "Queue 3 jobs", "Stop", "Save montage".

**Status.** `StatusDot`, `Chip` (kinds neutral/accent/success/warning/danger/field/lost, optional
dot, optional strikethrough for "missing"), `Badge`, `Progress` (determinate / indeterminate),
`LivenessBadge` ("active" pulse / "stalled 3m" — never a fake percentage), `JobStateChip`.

**Forms** (react-hook-form + ajv resolver from `schema.json`). `Field` (label-left by default;
`layout`, `fullBleed`, `changed`, `help` as a popover), `useChangedFields`/`changedFields`,
`TextInput`, `Textarea`, `NumberInput` (unit suffix, step, min/max, tabular), `Select`, `Combobox`,
`MultiSelect`, `Switch`, `Checkbox`, `RadioGroup`, **`SegmentedControl`** (one-of-N in one 28 px
row — Method, Scope, Space), `Slider`, `PathInput`, `SubjectPicker`, `CoordinateInput`,
`KeyValueTable`, `ElectrodePairsEditor`, `FormSection` (§4.2 rules 4–6).

**Chrome.** `ContextBar` + `Crumb`/`CrumbSeparator` (a breadcrumb-style trigger; the context bar
itself stopped using it at U11, but a page's own scope control — a run label, a batch table's
header — still can), `ActionBar` (digest,
warning count, one secondary, one primary, `⌘⏎` hint), `StatusBar` + `StatusCell`, `RefetchBar`,
`PageLayout` (§4.1), `ResizablePanels`.

**Containers.** `Card`/`CardHeader`/`CardBody` (Workbench cards, result summaries — not form
groups), `Tabs`, `Dialog`, `AlertDialog` (confirmations; the destructive verb is the confirm
label), `Drawer`, `Popover`, `Tooltip` (400 ms), `Toast` (sonner; success 4 s, error persistent
with "Details"), `EmptyState` (`page` | `inline`), `Skeleton` (`rows` or explicit size),
`InlineError`, `Callout`, `Kbd`, `VirtualList`, `DefinitionList`, `DataTable`,
`Sparkline`/`LineChart`.

**Jobs and runs.** `JobTrace`, `JobsTable`, `JobConsole` (virtualised, level colours, filter,
follow-tail, "Reveal log file"), `JobStateChip`, `ArtifactList` (Open / View / Reveal).
v3 adds, in `pages/_shared/run/`: **`RunPanel`** (§4.5), **`PlanGrid`** (stats strip + subject ×
stage matrix + legend + warnings), **`JobTerminal`** (§4.6, `JobConsole` with job resolution and a
header), and the pure `PlanModel` mapper `planModelFrom(result, subjects, stages)` /
`planDigest(plan)`. **`PlanSummary` is deprecated** — it stays exported and working for any page not
yet migrated, and every run page moves to `PlanGrid`; the last migration deletes it.

## 6. Interaction rules

1. Anything longer than a request is a job: the button shows loading only until the job is
   accepted, then a toast ("Queued: simulation for ernie") and a trace in the rail.
2. Destructive or irreversible actions (overwrite outputs, stop a job, terminate a process, delete
   a montage) use `AlertDialog`; the confirm button repeats the verb.
3. Errors explain what and how to fix, in the interface's voice, never apologetic, never vague.
4. Empty states invite action and link to it; inline ones do it in ≤ 2 lines.
5. **Keyboard.** Unmodified keys belong to whatever has focus — including the scene canvas, whose
   own keys are unmodified letters and arrows. **Every app shortcut carries ⌘/Ctrl.** `?` opens one
   sheet listing them. `Esc` is scoped to the innermost overlay.
   `⌘K` palette · `⌘P` subject switcher (U11: opens the same palette, at its Subjects section —
   there is no separate switcher to open any more) · `⌘J` jobs rail · `⌘⇧I` collapse/expand the right
   pane · `⌘⇧N` notes · `⌘⏎` the action bar's primary · `⌘⇧V` focus the canvas ·
   `⌘1`–`⌘9` the rail's workflow rows in order, `⌘0` Settings (§9) · `⌘,` Settings. (`⌘\` was v2's inspector toggle and is retired with the
   inspector — one gesture, one meaning.)
6. State in form as well as colour: chips have text, progress has numbers, dots have tooltips.
7. Loading follows §4.4. Never a blank page, never a re-skeleton on refetch.
8. Copy: sentence case, plain verbs, the same word for the same thing everywhere (Run/Stop/Queue,
   subject, simulation, montage, ROI, job). No exclamation marks.

## 7. Theme

**Light is the default** (program U9). A first launch with no stored preference renders light, on a
machine set to dark included; dark is a choice, not an inheritance, because every screenshot in this
document and every acceptance number was read on the light palette.

Two places change it, and only two:

- **Settings ▸ Appearance** — `system` / `light` / `dark`, a `SegmentedControl`.
- **`⌘K` ▸ "Theme: light" / "Theme: dark" / "Theme: system"** — three palette actions, so the
  toggle is one keystroke away from any screen. It is not in the context bar: a preference is not
  ambient state.

Mechanics are unchanged from v2. `tokens.css` defines the light set on bare `:root`, the dark set
under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and again
under `:root[data-theme="dark"]` so the explicit choice wins in both directions. The resolved value
is persisted in `localStorage` and written to `<html data-theme>` **before first paint**, so a dark
user never sees a light flash. Components use tokens only; no literal colours in pages. Never give a
token its only definition inside a theme block — `--canvas` is defined once on bare `:root` precisely
because it must not change with the theme.

Every page is screenshotted in **both** themes at **both** sizes, every round (§12).

## 8. Quality floor per screen

Responsive at 1024 / 1280 / 1440 / 1600 wide; keyboard-only pass; contrast ≥ 4.5:1 for text; reduced
motion respected; light and dark both checked; the screens spec (§12) captures every page in both
themes at 1280 × 800 and 1440 × 900 into the run's artifact directory (gitignored) and writes the
numbers beside them.

**Acceptance numbers.** v3 replaces v2's work-column target — the cap it measured is gone — with the
three metrics of §12. The per-page limits are in §12.3. The density numbers below survive unchanged
and are still what makes those limits reachable:

| | v1 | v2 | v3 |
|---|---|---|---|
| work column width | 674 px | ≥ 880 px | **the content box minus the right pane** (§2.1) |
| page header | 86 px | 0 px | **0 px** (Settings and Help excepted) |
| chrome per form section | 94 px | ≤ 41 px | **≤ 41 px** |
| field row / section header / table row | 70 / 44 / 36 px | 28 / 28 / 28 px | **28 / 28 / 28 px** |
| dead-space ratio, populated, 1280 × 800 | — | — | **≤ 25 %** (§12.3) |

Every run page shows all of its Tier-1 controls on the first screen at 1280 × 800 without scrolling
(`firstScreenControls(page).hidden.length === 0`). The Gallery's density ruler
(`pages/dev/DensityGallery.tsx`) measures the last row with `getBoundingClientRect` so the numbers
are read, not estimated.

### 8.1 How a screen is assessed — and why nothing appears on your monitor

**A test run never takes the screen.** `src/main/window.ts` builds the window and never shows it
when `TIT_E2E_OFFSCREEN=1`, hides the dock icon and swallows notification banners;
`tests/e2e/_helpers.ts`'s `offscreenEnv()` sets that by default on darwin, and every spec launches
through `launchElectronApp()`. `TIT_E2E_HEADED=1` puts the windows back for a human debugging
session, and is the only thing that does. The renderer still runs on the real GPU, so screenshots
and WebGL behave exactly as they do for a user.

**It is proven, not asserted.** `npm run e2e:quiet` (`scripts/e2e-quiet-check.sh`) runs the suite
while sampling the window server (`CGWindowListCopyWindowInfo`) and the frontmost application twice
a second. It fails if any Electron/Chromium window reaches layer 0 or if the focus moves.
`getBounds()` is what Electron *asked* for; the window list is what the screen actually shows, which
is the difference between a claim and a proof. Run it before saying a change is quiet.

**Judge numbers and the DOM, not pictures.** A screenshot is an artifact for a human to look at
later; it is not how an assertion is made. Assert instead on:

- `data-page` / `data-subject` on `[data-testid="shell-content"]` — the app's own statement of which
  screen is on and what it is scoped to (`expectPage` / `expectSubject` in `tests/e2e/_helpers.ts`).
  The app runs a MemoryRouter, so `toHaveURL` can never see a route change.
- measured geometry — `getBoundingClientRect` for the acceptance numbers above.
- roles, accessible names and testids for structure; computed styles for tokens.

Screenshots are still taken, in both themes, and are still the thing a reviewer opens. They are
evidence, not the test.

## 9. Navigation (`app/registry.ts` is the implementation)

**The rail is a flat, workflow-ordered list. No group headers, no subject-id label, no subject
scoping in the rail** (program U7): a subject is chosen in the context bar, and printing "101" as a
group heading told the user a page belonged to a subject when it did not.

| # | page id | label | icon (`lucide-react`) | shortcut | layout |
|---|---|---|---|---|---|
| 1 | `overview` | Overview | `LayoutGrid` | ⌘1 | browse |
| 2 | `preprocess` | Pre-processing | `SquareStack` | ⌘2 | run |
| 3 | `simulator` | Simulator | `Zap` | ⌘3 | run |
| 4 | `optimizer` | Optimizer | `Target` | ⌘4 | run |
| 5 | `analyzer` | Analyzer | `BarChart3` | ⌘5 | run |
| 6 | `pipeline` | Pipeline | `Workflow` | ⌘6 | run |
| 7 | `results` | Results | `FolderOpen` | ⌘7 | browse |
| 8 | `viewer` | Viewer | `Eye` | ⌘8 | bleed |
| 9 | `jobs` | Jobs | `ListChecks` | ⌘9 | browse |
| — | *(spacer)* | | | | |
| 0 | `settings` | Settings | `Settings` | ⌘0 (⌘, alias) | run + header |
| 10 | `help` | Help | `CircleHelp` | — (`?` sheet) | run + header |

- **Optimizer is one page.** `optimizer-flex` and `optimizer-ex` merge into `pages/optimizer`, with
  a `SegmentedControl` **Method ⟨Flex │ Ex │ mEx⟩** as the first row of the work pane and one shared
  `RoiPicker`. Two nav entries were a copy of the PyQt tab strip, not a workflow.
- **Icons + tooltips below 1440; icons + labels at ≥ 1440** (Q1, §0). A 216 px labelled rail below
  1440 would leave only 1064 px of content — too little for the run pages' 3-D panes —
  so the icon breakpoint moved to 1440 for every page rather than forcing the Viewer alone onto a
  permanent icon rail (`PageDef.railMode: "icons"` still exists for a future page that needs it,
  but no page sets it today: at 1440 the Viewer's content box is 1224 px either way).
- **The rail's first row is Overview** (⌘1): the landing page, the catch-all destination and the
  palette's first page. It is the project's coverage, its presence matrix and who can run what next
  — per subject: raw staged/converted, FastSurfer, FreeSurfer, m2m, DWI, CT, leadfields, EEG nets
  and high-level totals for simulations, optimizations and analyses, in five presence states
  (`present · absent · partial · pending · failed`). It links into a workflow or into Results; it
  never lists outputs itself, and it is not subject-scoped — a subject is chosen in the context bar
  or on a page's own batch table.
- Settings and Help are pinned to the bottom below a spacer; they are the only two pages with a
  header.
- Nav rows carry **no shortcut badges** — shortcuts live in the palette and the `?` sheet, assigned
  in the registry so nav, palette and sheet cannot disagree.
- There is no "Panels" group and no "Tools" group: every optional panel is a *mode* inside a page,
  toggled by Settings ▸ Optional tools. `panel-subject-info` is **deleted** (its facts are Overview's; `/panel-subject-info` falls through to
  `/overview` and a stale saved panel id is ignored), `panel-source`
  into Pre-processing, the three analysis panels into Analyzer, `system` into the jobs panel's Host
  tab, `panel-quick-notes` into the `⌘⇧N` drawer, and `dev` stays palette-only behind
  `VITE_INCLUDE_GALLERY`. **Not yet done** (critic round 1, finding 1; Stage-2 scope, deliberately
  not this round's fix): the four panel pages (`panel-source`,
  `panel-cluster-permutation`, `panel-nilearn-visuals`, `panel-nifti-group-average`) still ship as
  independent rail rows and routes rather than folded modes, and Settings' "Optional tools" copy
  says as much ("Enabled panels appear in the nav rail"). What *is* done for this round: they carry
  no `PageHeader` (§2.3's "no page header outside Settings and Help" rule applies to them like any
  other page — `pageHeaderHeight: 0`), and each page's one-line purpose moved into an info tooltip
  on its first section header rather than being lost. Panels remain standalone pages until folded.

## 9.1 Pipeline

**A pipeline page is a canvas of the pages you already have.** Rail row 6, ⌘6, the `run` shape.
Palette on the left (the node kinds), the React Flow canvas in the middle, the receipt over the
Terminal on the right — the same right pane every run page has, because a pipeline run is a job group
like any other.

- The **Subjects node** is the source of the graph and the only place a cohort is named
  (2026-09-06). Every other node takes its subjects over a `subjects` wire, so two steps in one
  document cannot disagree about who the study is about, and no node carries a copy to retype.
- A **subjects wire is refused on what those subjects actually have.** Each kind declares what it
  requires (`raw | m2m | leadfield | simulation`) and what it produces, and the canvas checks the
  drag against the project's own readiness — before a graph exists, using `GET /api/pipelines/kinds`
  — then again at validate and at run, from the same table, so the refusal is one sentence and not
  three. It names the subjects that fail, never a count: *"102 has no head model"*. A chain may
  satisfy what a cohort cannot: `Subjects(raw) → Pre → Simulator` is accepted because Pre produces
  `m2m`, while `Subjects(raw) → Simulator` is refused.
- A **node** is one existing job kind carrying exactly the config the matching page builds. Double-click
  opens that page's own form sections — imported, not copied.
- An **edge** is a typed binding between one node's named output and another's same-named input:
  `subjects | montages | simulation | roi | leadfield`. Ports and their wires take one hue per type.
  An illegal drag is refused *with its reason* on the canvas, never silently dropped.
- **Run submits once.** One group id, one row-group in Jobs, cancellable as one thing.
- **Save/Load** under `code/ti-toolbox/pipelines/<name>.json`; **Export notebook** writes an `.ipynb`
  that calls only the documented `tit` scripting API and carries the document in its metadata.
- No drag-to-reorder of anything but the node positions themselves; order is the graph.

### 9.1.1 The card is a row, not a poster

**A node card is at the app's density like everything else**: 208 px wide, 8 px padding, a 20 px
header row of kind icon + name + status chip, a two-line 12/16 summary that clamps, and 13/18 as the
base — the same steps §3.2 gives every other surface. It is not a place where a canvas earns its own
type scale.

The failure this rule was written from, and it is worth stating plainly because it cost a release's
worth of trust in the page: `pipeline.css` was authored against a token vocabulary that **does not
exist in this app** — `--surface-default`, `--text-muted`, `--font-size-sm`, `--border-subtle`,
`--radius-md`, `--shadow-sm`, `--accent-primary`, 36 references in all. A browser drops a declaration
whose custom property is undefined and reports nothing, so every visual property on the card, the
palette and the port handles was silently discarded, the card inherited React Flow's own default
type at roughly three times this density, and the page shipped looking broken while every behaviour
on it was fine. **A stylesheet must use tokens `ui/tokens.css` actually defines**;
`tests/unit/pipelineTokens.test.ts` fails on one that does not, and `tests/e2e/pipeline-ux.spec.ts`
reads the computed style off the live card.

### 9.1.2 What a node states about itself

- **An unbound required input is a chip on the card**, not a line in the receipt: `needs: subjects`,
  in `--danger`, one per unbound port, straight from the server's `missing_input` issues. Clicking
  it opens that node's form with that field focused; wiring the port removes it. The card never
  prints what it is missing in its summary as well — that said the same thing twice and left no room
  for what the node actually has.
- **Ports print their names on hover.** Five hues is a legend nobody memorises.
- **The selection ring is on the card**, drawn off React Flow's own `.selected`, so a click, a
  marquee and ⌘A all light the same thing.
- **A wire animates while either of its ends is running**, and stops on `prefers-reduced-motion`.

### 9.1.3 The receipt states the plan, or the blockers — never both as a list

This is the one page where the maintainer wants a run summary in the right pane, and it follows
§4.8's "first 15 + … and K more" rule: "N jobs in one group — K steps", then the labels with their
`after` chain.

**When the pipeline cannot run, the receipt is the blockers instead, grouped by node, each group with
a Fix button that selects and centres that node.** Only `level: "error"` counts. The two findings that
are not faults — a node wired to nothing (`unconnected`), a node still at its defaults
(`unconfigured`) — collapse into **one** sentence at the bottom ("3 steps run independently"). The
page tells them apart by `PipelineIssue.code`, which was added to the contract for exactly this;
matching on the message text is not allowed, because a reworded sentence would then turn a note into
a blocker with nothing failing.

The failure it prevents, from the maintainer's own screenshot: three unwired nodes produced three
"… is not connected to anything; it will run on its own" warnings and three "has no configuration
yet" warnings, in the same flat list as the real errors, so a pane of six alarms described a graph
with nothing wrong with it.

### 9.1.4 The empty canvas is one line and a way in

One sentence — "Add a step or import a pipeline" — and a **Start from a sample** button that builds
the `pre → flex → sim → analyzer` graph, wired, on a subject the project has. The sample is the
graph the D6 gate submits, so what a first-time user lands on is a pipeline that is *known* to
validate and run, not four unconfigured cards. The empty state is drawn **over** a live canvas, never
instead of one: React Flow has to be mounted or a palette drag has nowhere to land.

## 9.2 Settings — the Viewer card

*Rewritten 2026-09-06 with the embed's retirement (§10). The card it replaces described an engine
this app shipped: a bundle version, a protocol range, a release index, install and rollback.*

The card answers one question — **where is Tetravox on this machine** — and it answers it by looking
at the local filesystem through `window.tit.viewer.probe`, never over the network. Found: the
resolved path and the bundle's version, stated plainly. Not found: that fact first, then
**Download Tetravox**. A path override exists for an install outside the conventional places (an
AppImage, a second copy), and it is the only setting here, because there is nothing else to decide:
the app updates itself and its releases are not this project's to pin.

## 10. Viewer

**The Viewer page is a source, a file list, and Open** (V1 · VM · VM2,
`dev/notes/v3-native-panes-external-viewer/{VX,VM,VM2}.md`).

V1 made it a data selector: *"the viewer tab only acts as the data selection and it actually opens
up everything in [an external window] like we have in 2.5.0."* VM read the empty space that left as
room for a composition panel — per-layer cards with opacity, colormap and threshold, a layout, a
camera, a background, "Also open" extras — and the maintainer's verdict on the screenshots was
**"too much"**. VM2 is the correction, and it is a better page than either:

> **The list of files that will open is the whole scene, and it is editable.**

Remove a row and that dataset is not in the scene. Add one — from everything the subject and the
simulation offer, or any path in the project — and it is, at the end. Drag (or ↑/↓) to reorder and
that is the layer order. Reset lets the source decide again. Open writes exactly those files, in
that order.

```
┌──────┬────────────────────────────────────────────────────────────┐
│ rail │   Open in Tetravox                                         │  centred, max 880
│  56  │   Pick a source, edit the list of files it resolves to…    │
│      │  ┌ SOURCE  The type decides which of the fields it needs ┐ │
│      │  │ Type ⟨Simulation⟩      Subject ⟨ernie⟩                │ │
│      │  │ Simulation ⟨Thalamus⟩  Field ⟨…⟩                      │ │
│      │  │ Space ⟨Subject│MNI⟩                                   │ │
│      │  └───────────────────────────────────────────────────────┘ │
│      │  ┌ WHAT WILL OPEN  2 files, in this order      [+ Add…]  ┐ │
│      │  │ ⠿ T1.nii.gz           volume  12.5 MB  ↑ ↓ ×         │ │
│      │  │ ⠿ ernie_TI_max.nii.gz volume  16.6 MB  ↑ ↓ ×         │ │
│      │  └───────────────────────────────────────────────────────┘ │
│      │  [Save as preset…] [Recent]            [Open in Tetravox]  │
└──────┴────────────────────────────────────────────────────────────┘
```

- **The page does not say how a file should look, and that is deliberate.** Opacity, colormap,
  threshold, layout, camera, convention: all of it is a judgement about the *data* — a percentile
  window on a TI field, a LUT and `nearest` on a label volume, a mesh added hidden because the file
  is 64 MB — and it lives in `tit/viewspec.py` with the rest of the scene's defaults. A file the
  view type produced keeps exactly that view type's settings; a file the person added is described
  by `_layer_for_path` from its name. Tetravox has an inspector, its own window and the reader's
  full attention; this page has a list. (The server's `overrides` plumbing from VM still exists and
  is still tested — nothing on this page sends it.)
- **The list is the same endpoint that opens it.** It resolves through `POST /api/view/open` with
  `dry_run`, and Open is the same call without it. A list built by different code from the thing it
  opens is a list that can be wrong, and the one moment this page must not be wrong is the moment
  before another application's window covers someone's work. Editing a row therefore re-resolves:
  the server is the one that knows a path is jailed out, missing or a duplicate, and the row
  disappearing is a truer answer than a row the client kept and the scene did not.
- **Sizes are on every row, and in the picker.** One of these files is routinely 64 MB. "How much
  is about to open" is the fact a person wants *before* the window, not after thirty seconds of
  loading.
- **Changing the source resets the list.** A different source resolves to different files; keeping
  the edited rows would silently open the previous subject's data under a new heading.
- **Reordering works without a mouse.** Drag is the natural gesture and ↑/↓ buttons are the one
  that everybody has.
- **A preset is kept; a recent is a footprint.** Presets are JSON under
  `<project>/code/ti-toolbox/viewer/presets/` — the project is the unit people copy, archive and
  share, and a preset in browser storage would be lost exactly when the work it describes was
  passed on. Recents are the last eight *opened*, in this machine's browser storage. Restoring
  either fills the page and opens nothing.
- **A second Open reuses the window that is already open.** Tetravox holds a single-instance lock
  and routes a second launch's file into the running window (verified in its repo at 0.3.11), so
  this page never has to track whether the app is running.
- **Three states, each naming what happened.**
  - **Nothing selected** — "Choose a source above and the files it resolves to appear here"; Open's
    disabled title says what is missing.
  - **Tetravox not installed** — a callout leads with that fact and offers **Download Tetravox**;
    Open is disabled rather than failing on click. Everything else still works, because building a
    list does not need the app.
  - **Browser mode** — no main process to start an application, so the button reads **Download
    scene** and the sentence afterwards says File ▸ Open Scene…. A complete answer, not a degraded
    one: the file is the interface.
- **Settings ▸ Viewer is the other half.** The resolved path and version, a path override, and the
  same download link. It reaches no network.
- **The page is allowed to be mostly empty.** Two cards and a footer; padding them out to fill
  1440 px would be filling space, not designing it. This remains the one page whose dead-space
  budget (§9) does not apply.
- **Keyboard.** `⌘⇧V` is gone with the canvas it focused. Nothing here owns unmodified keys.

## 11. Status bar — removed

There is no bottom rail. The 24 px status bar, its `--status-bar-h` token, `AppStatusBar`, the
`useStatusCells` cell registry and every page's registration were deleted; §2.3 records where the
one fact worth keeping went (the connection dot in the context bar). The section number is kept
empty so §12 and §13 still mean what the lane notes say they mean.

## 12. The dev loop

The method is the deliverable (program U10): **build → offscreen screenshots → DOM metrics →
self-critique against the checklist → fix**, at least twice per lane, with the numbers per round
recorded in `dev/notes/v3-ui-program/<lane>-notes.md`. "Looks fine" is not a gate. An agent cannot
judge a picture; it can judge a number.

### 12.1 The instrument — `desktop/tests/e2e/_metrics.ts`

Three helpers, shared by every lane and by the critic panel.

**`deadSpaceRatio(page, selector?)`** — the U1 metric. Samples the element's rect on a **16 px grid**
starting 8 px inside its top-left, calls `document.elementFromPoint(x, y)` at each point, and counts
the point as **content** when the topmost element is:

- a `CANVAS`, `IFRAME`, `IMG`, `SVG`, `VIDEO`, `INPUT`, `SELECT`, `TEXTAREA`, `BUTTON` or `A`; or
- a leaf (`childElementCount === 0`) whose `textContent.trim()` is non-empty; or
- an element with a non-transparent `background-color` **whose own rect covers less than 25 % of the
  sampled rect** — that is what makes a chip, a table header or a stats tile count while a pane's own
  background does not.

Everything else is dead. Returns `{ ratio, samples, dead, rect }`. The 25 % clause is the whole
point of the metric: without it a page could paint one giant surface and score zero.

**`paneWidths(page)`** — `{ nav, content, work, right, gap }`, each the rounded
`getBoundingClientRect().width` of `[data-testid="nav-rail"]`, `[data-testid="shell-content"]`,
`[data-testid="page-work"]` and `[data-testid="page-right-pane"]`; a pane that is not rendered
reports `0`, which is how "never an empty pane" is asserted rather than described.

**`firstScreenControls(page)`** — `{ total, visible, hidden }` over
`[data-tier="1"] :is(input, select, textarea, button, [role="combobox"], [role="radiogroup"], [role="switch"])`
inside the work pane; a control is `visible` when its rect bottom is at or above the work pane's
visible bottom **with the pane's scrollTop at 0**. `hidden` carries the accessible names, so a
failure says *which* control fell off the first screen.

### 12.2 The artifacts — `desktop/tests/e2e/screens.spec.ts`

One spec captures every page in both themes at both sizes and writes the numbers next to the
pictures:

```
tests/e2e/artifacts/<run id>/
  <page>-<theme>-<w>x<h>.png        e.g. preprocess-light-1280x800.png
  metrics.json
```

```json
{
  "runId": "u0-32124",
  "capturedAt": "2026-09-03T14:04:11Z",
  "pages": [
    {
      "page": "preprocess", "theme": "light", "width": 1280, "height": 800,
      "deadSpaceRatio": 0.21, "samples": 2814, "dead": 591,
      "panes": { "nav": 216, "content": 1064, "work": 666, "right": 360, "gap": 6 },
      "firstScreenControls": { "total": 9, "visible": 9, "hidden": [] },
      "screenshot": "preprocess-light-1280x800.png"
    }
  ]
}
```

The pictures are evidence for a human; `metrics.json` is what the lanes and the critic assert on.
The run never takes the screen — `scripts/e2e-quiet-check.sh` proves it by sampling the window
server, and its exit 2 means "could not tell you", never a pass (§8.1).

### 12.3 Acceptance numbers per page

Measured on the mock fixture in its **populated** state, light theme, at 1280 × 800; the same
numbers are captured at 1440 × 900 and in dark, where they may only improve.

| page | dead space | panes at 1280 | first-screen Tier 1 |
|---|---|---|---|
| `subjects` | ≤ 44 % populated · ≤ 45 % with no row selected | nav 216 · work ≥ 704 · right 360 or **0** | n/a |
| `preprocess` | ≤ 22 % | work ≥ 560 · right 576 | `hidden` empty |
| `simulator` | ≤ 22 % | work ≥ 560 · right 576 | `hidden` empty |
| `optimizer` | ≤ 22 % | work ≥ 560 · right 576 | `hidden` empty |
| `analyzer` | ≤ 25 % | work ≥ 560 · right 576 | `hidden` empty |
| `results` | ≤ 20 % | list 200 · tree ≥ 400 · preview 426 ± 8 | n/a |
| `viewer` | n/a (V1: a selector page is meant to be mostly empty — §10) | nav **56** · work ≥ 1200 | n/a |
| `jobs` | ≤ 25 % with history · ≤ 30 % empty | work ≥ 704 · right 360 or **0** | n/a |

`subjects` was ≤ 25 % / ≤ 30 % while four cards of readiness chips covered the lower half of the
page. Those cards were removed on 2026-09-06 and the presence matrix's columns were spread out for
readability, so eight of a row's eleven columns now hold one 10 px dot each and the sampler counts
more of the page as empty: the measured floor of the page as it now is, held by
`tests/e2e/overview.spec.ts` so a regression that empties it further still fails.

For reference, the same measurement on the v2 build this program replaces (cell-occupancy pixel
proxy, `dev/notes/v3-ui-program/u0-design-notes.md` §1): subjects 88 %, preprocess 74 %,
simulator 67 %, results 86 %, jobs 92 %, viewer 16 %.

### 12.4 The self-critique checklist

Every lane runs this every round; the critic panel uses the same list and reports by item number.

1. Dead-space ratio within §12.3 on the populated state; no pane exists without content (U1).
2. Nothing on screen restates the nav label; no page header outside Settings and Help.
3. Every chip and badge is from the shared vocabulary (§4.5, §5); no ad-hoc colours.
4. Every number is tabular; units are suffixes; paths are mono and truncate from the left.
5. Both themes: text contrast ≥ 4.5:1 by the token test; no hard-coded colours.
6. No status bar: the shell has no bottom rail, and no page registers cells for one.
7. `firstScreenControls(page).hidden` is empty on every run page at 1280 × 800.
8. Keyboard: `⌘K`, `⌘P`, `⌘J`, `⌘⇧I`, `⌘⏎`, `Esc` scoped to the innermost overlay; focus visible.
9. Copy: sentence case, verbs on buttons, no exclamation marks, no "Freeview / Gmsh / X11".
10. The page still passes its e2e spec, and the spec asserts DOM state, not pixels.

## 13. Workflow continuity and focused scene previews

The [2026-09-04 maintainer requirements](../docs/requirements/2026-09-04-maintainer-polish.md)
supersede earlier plans wherever they required unmounting an inactive tab. The cross-component
contract is [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §§2–4.

Visited tabs retain their live page, form and live canvas until project close/switch. Each tab remembers
its subject and route context; a different tab cannot reset it. Inactive pages relinquish keyboard
shortcuts, commands, status cells and portals, and their content is hidden and inert. A Results link
prefills the Viewer's draft selection; nothing opens until **Open in Tetravox** is pressed (§10).
Plain navigation resumes the draft.

Preview collapse/expansion hides the alternate pane without discarding it. Source-editor drafts,
including unfinished coordinate text, and dropdown search terms remain intact when returning.

**The run-page scene panes draw a fixed guide, not the selected subject.** Simulator, Optimizer and
Analyzer render packaged reference anatomy served by `GET /api/guide/*`; the pane selects *names*
(electrodes, EEG nets, atlas regions) and never coordinates, and a subject switch costs it zero
requests and zero remounts. Click-to-place of a sphere centre is gone from these panes: a guide
coordinate is not any research subject's millimetres, so the form's typed x/y/z fields are the way
a centre is set. Subject-specific anatomy lives in the Viewer and in Results.

**Those panes are this app's own WebGL2 renderer** (`src/renderer/scene/`, restored 2026-09-06,
`docs/ARCHITECTURE.md` §7.2) — no iframe, no message protocol, no second engine to install. They
draw one 3-D viewport, the orientation cues, a pair of labelled Skin / Grey matter opacity controls
and the interaction hint. There is no application chrome to hide, because the renderer only ever
drew the pane. Opacity is shown as a percent and changing it updates the corresponding surface
without reloading geometry or resetting the camera; grey matter also carries the cortical atlas
surface, whose regions the pane names on hover and selects on click (§4.9, §4.10).

Shared dropdowns contain long values and use the available viewport height. Interactive elements
carry their accessible names. The action bar has the shared primary action on the right and grows
from its existing minimum height when a blocked-action reason needs another line.
