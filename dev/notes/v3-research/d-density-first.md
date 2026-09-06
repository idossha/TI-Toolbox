# TI-Toolbox v3 desktop — density & compaction-first redesign

Lens: **DENSITY & COMPACTION-FIRST.** Every form fits one screen at 1280×800. No card sprawl. One
consistent two-pane run layout. Figma/Blender inspector density with Radix accessibility.

Scope of evidence: every screenshot in `desktop/tests/e2e/artifacts/final-mock/`, `desktop/DESIGN.md`,
the shell (`app/Shell.tsx`, `app/NavRail.tsx`, `app/TopBar.tsx`, `app/shell.css`), `ui/Layout.tsx`,
`ui/tokens.css`, `ui/components.css`, the nine page sources, `tit/gui/main.py`'s tab list,
`tit/server/routes/viewers.py`, `tit/viewspec.py`, `dev/notes/v3-build-plan.md` §3, and Tetravox's
`docs/ARCHITECTURE.md` §4.7 / §5 / §6.5 / §8 / §13.

Every claim below cites `file:line`. All paths are absolute from
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/` unless noted;
Tetravox paths are absolute from `/Users/idohaber/00_development/tetravox/`.

---

## 0. Verdict

The maintainer is right, and the reason is measurable, not aesthetic. The v3 shell reproduces the
PyQt tab bar as a **220 px labelled nav rail with six group headings and up to nineteen items**
(`desktop/src/renderer/app/shell.css:14`, `desktop/src/renderer/app/NavRail.tsx:7-14`,
`desktop/DESIGN.md:180-194`), and it reproduces the PyQt tab *body* as a stack of bordered,
shadowed, 16 px-padded Cards in a column that — at the app's own reference width of 1280 — is only
**674 px wide** while a 320 px Plan panel sits beside it half-empty.

Three numbers carry the whole argument:

| | measured today | after this proposal |
|---|---|---|
| Work-column width at 1280 | **674 px** (`simulator-light.png`: card spans x 245→919; derived from `shell.css:14` 220 + `shell.css:178` 24×2 + `components.css:1385` 320 + `components.css:1373` 16) | **891 px** (+32 %) |
| Vertical space below the chrome at 800 | **582 px** (800 − 48 top bar `shell.css:116` − 36 rail `shell.css:194` − 48 padding `shell.css:178` − 86 page header `base.css:97` + `components.css:1429`) | **684 px** (+18 %) |
| Non-content chrome per form section | **94 px** (`components.css:841` header 12+12+20, `components.css:849` body 16+16, 2 px border, `simulator/index.tsx:125` 16 px gap) | **41 px** (−56 %) |

Compounded on the Simulator that is **306 px of pure chrome removed from one screen**, which is why
today the "Global parameters" section is cut off mid-radio-button at the fold
(`simulator-light.png`, "Ellipse" clipped at y≈838) and why Flex-search needs three scroll-heights
to reach its ROI table (`optimizer-flex-nonroi-spherical-light.png` shows the scrollbar thumb at
roughly one third travel with the Run button parked 500 px above the field being edited).

The IA problem is separate and worse. The nav is a flat translation of `tit/gui/main.py:196-201`'s
six tabs plus the extension mechanism (`tit/gui/extensions.py:158`), so:

- "Optimizer · Flex-search" and "Optimizer · Ex/mEx-search" are **two destinations for one verb**
  (`optimizer-flex/index.tsx:363-372`, `optimizer-ex/index.tsx`), and they duplicate an ROI picker
  (`pages/_shared/roi/RoiPicker.tsx` vs `pages/optimizer-ex/roi/RoiPicker.tsx`, 327 and 271 lines
  of near-identical code).
- "Subject info" is a strict **superset** of "Subjects" — same table, plus Leadfields, dwi, ct and
  Export (`panel-subject-info-light.png` vs `subjects-light.png`; `panels/subject-info/index.tsx:157`
  vs `subjects/index.tsx:114-124`) — yet it lives in a different nav group, behind a Settings toggle.
- The four statistics/figure panels (`panels/nifti-group-average`, `panels/cluster-permutation`,
  `panels/nilearn-visuals`, plus Results' own "Group" tab at `results/index.tsx:483-511`) are
  **four separate top-level entries for one step of the domain workflow**, and two of them break
  the app's own Plan-panel contract by rendering Plan as an inline card at the bottom of the form
  (`panels/nifti-group-average/index.tsx:184`, `panels/cluster-permutation/index.tsx:360`) — visible
  in `panel-nifti-group-average-light.png`, where "Plan" is below the fold and the right rail is
  empty.
- The Viewer is a **form for building someone else's command line** (`viewer/index.tsx:515-596`
  renders the literal `freeview …` argv in a `<pre>`), which is exactly the thing Tetravox exists
  to delete.

Everything below is one recommendation per item. No alternatives, no hedging.

---

## 1. Conventions borrowed, and why each one

I am borrowing four specific conventions from four products, and naming the exact mechanism.

**1. Blender's Properties editor → kill the Card, keep the section.**
Blender stacks a dozen property *panels* in one scrolling column with no box around any of them:
a 20-ish px header row with a disclosure triangle, a 1 px rule, and the content flush to the pane
edge. There is no border, no shadow, no gap between panels. That is the single highest-yield change
available here, because `components.css:830-857` spends 94 px per section on box chrome and
`ui/Layout.tsx:151-166` applies it to *every* form group. Borrowed: sections become flush
`<section>`s inside one bordered pane, separated by 1 px `--line`. Also borrowed: **a collapsed
panel still shows its state in its own header** — Blender puts the modifier's name and its key
values on the collapsed strip, which is what makes aggressive collapsing safe rather than lossy.

**2. Figma's right-hand properties panel → label-left rows and the 28 px control.**
Figma runs label-left / control-right at ~28 px rows, packs X/Y/W/H two-up, uses segmented controls
where TI-Toolbox uses radio groups, and hides help behind a `?` rather than printing a third line.
`components.css:267-293` does the opposite: `.field` is a *column* (label 18 + gap 4 + control 32 +
help 16 = 70 px per field). Borrowed: the label-left grid row at `min-height: 28px`, the help
popover, and the "changed vs default" value tint. At ten fields that is 700 px → 360 px.

**3. VS Code → the icon activity bar, `⌘K`, and the bottom Panel.**
VS Code carries a 48 px icon-only activity bar with no labels and no group headings, promotes
everything else into the command palette, and keeps a resizable bottom panel on `⌘J`. TI-Toolbox
already has the bottom panel on `⌘J` (`app/keyboard.ts:37-41`, `shell.css:188-232`) — that part is
correct and stays. What is missing is the other half of the bargain: the rail can only shed its
220 px if a palette exists to replace label-scanning, and today `cmdk` is a dependency
(`desktop/package.json:48`) used **only** by `ui/Combobox.tsx:2` — there is no palette. Borrowed:
permanent 56 px icon rail + `⌘K` palette. No new dependency required.

**4. 3D Slicer / Freeview / ITK-SNAP → the viewer owns the window.**
No imaging viewer puts a 24 px page title, a purpose sentence and a 24 px page margin above the
render panes. Borrowed, for the View screen only: no page header, no shell padding, full-bleed
canvas, and — quoting Tetravox's own rule — **the panes stay dark in both themes**
(`docs/ARCHITECTURE.md:2723-2731`, "imaging convention: a light viewport changes what a greyscale
T1 and a heat overlay look like").

(Linear is the tie-breaker on one smaller decision — no page title where the nav already says the
page name — but it is not a primary reference here; the shell is a workstation, not an issue tracker.)

---

## 2. The shell — exact geometry

```
1280 × 800, all numbers are CSS px, all edges 1 px --line

┌────┬───────────────────────────────────────────────────────────────────────────────┐
│ 56 │  Context bar                                                             40   │
│ px ├──────────────────────────────────────────────┬────────────────────────────────┤
│    │                                              │                                │
│ ic │  Work pane                                   │  Inspector                     │
│ on │  flex: 1  (891 px at 1280)                   │  300 px  (resize 260–420)      │
│ ra │  padding 16  ·  own scroller                 │  own scroller                  │
│ il │                                              │                                │
│    ├──────────────────────────────────────────────┴────────────────────────────────┤
│    │  Action bar (run screens only)                                           44   │
│    ├───────────────────────────────────────────────────────────────────────────────┤
│    │  Jobs rail  collapsed 32 / expanded 260 (drag or ⌘J)                     32   │
└────┴───────────────────────────────────────────────────────────────────────────────┘
```

| region | size | replaces |
|---|---|---|
| Nav rail | **56 px, always icon-only** | 220 px labelled rail (`shell.css:14`) and its `max-width:1199px` collapse branch (`shell.css:56-79`) — one state, so the wordmark/monogram swap and the bug documented at `shell.css:33-38` both disappear |
| Context bar | **40 px** | 48 px top bar (`shell.css:116`) **and** the 86 px page header (`ui/Layout.tsx:169-190`, `base.css:97-101`, `components.css:1416-1431`) |
| Work pane | flex, **16 px padding** | `max-width: 960px` that never applies (`components.css:1380`) + 24 px padding (`shell.css:178`) |
| Inspector | **300 px, resizable, persistent** | 320 px non-resizable Plan panel that only some pages fill (`components.css:1383-1391`) |
| Action bar | **44 px, sticky, spans work + inspector** | the Run button buried at the top of the Plan card (`simulator/PlanPanel.tsx:130`, `optimizer-flex/PlanPanel.tsx:39`) |
| Jobs rail | **32 / 260, drag-resizable** | 36 / 280 fixed (`shell.css:194`, `shell.css:217`) |

**Context bar contents** (left→right): breadcrumb `example ▸ sub-ernie ▸ Simulate` (project from
`TopBar.tsx:33`, subject from `app/subjectContext.ts`, page from the registry), then a flexible gap,
then `⌘K` search affordance, connection dot (`TopBar.tsx:51-54`), `N running` chip
(`TopBar.tsx:58-60`), `?`, `⚙`. The breadcrumb's subject segment is a **click-to-change combobox** —
that is the app's single subject switcher and it replaces the "Subjects" card that opens six of the
nine pages today (`simulator/index.tsx:126-141`, `optimizer-flex/index.tsx:225-249`,
`preprocess/index.tsx:481`, `panels/source/index.tsx`, `analyzer/AnalyzerPage.tsx:353`,
`results/index.tsx:531-546`).

**Breakpoints.** One, not three. Below 1120 px the inspector becomes an overlay drawer on the right
(`⌘\` toggles it) instead of stacking under the form — the current stacking rule
(`components.css:1371-1414`) is what forces `.page-layout-main` to stop being a scroller and caused
the clipping bug documented in that comment. Minimum window **1120 × 720**, raised from 1024 × 680
(`shell.css:5-6`, `DESIGN.md:94`): a two-pane workstation with a viewer in it has no honest 1024
layout, and pretending otherwise is what produced three conflicting media queries.

---

## 3. Information architecture

### 3.1 The rail — 9 icons, no group labels

```
▣   Project          ⌘1     workspace: subjects, presence, project health
▤   Prepare          ⌘2     DICOM/NIfTI → charm → recon-all → DWI → EEG forward
⚡  Simulate         ⌘3     TI / mTI from montage · flex result · free-hand
◎   Optimize         ⌘4     flex-search │ ex-search │ mEx-search
▦   Analyze          ⌘5     subject │ group │ figures
👁  View             ⌘6     Tetravox
─────────────────────────
▥   Results          ⌘7     every run, every artifact, every report
▤   Jobs             ⌘8     (rail toggles with ⌘J)
⚙   Settings         ⌘,     project · appearance · system · optional tools
```

Nine items, one divider, **zero group headings**. Compare today: 12 base items in 5 labelled groups
plus up to 6 panels in a sixth plus Gallery (`DESIGN.md:180-194`, `NavRail.tsx:7-14`) — up to 19
rows and 6 headings in a 220 px column, which is what `subjects-light.png` shows filling two thirds
of the window height with navigation for a page whose entire content is a three-row table.

Each icon carries a Radix tooltip with title + shortcut (already the pattern at `NavRail.tsx:50-52`;
`aria-label` already present at `NavRail.tsx:39`). Active item: 2 px `--accent` left bar + `--accent`
icon, no `--accent-soft` fill (a filled 40 px pill in a 56 px rail reads as a button, not a location).

### 3.2 Why these six primaries

They are the researcher's verbs, in order, one per stage of the workflow the brief describes:
create/open project → add subject → pre-process → simulate **or** optimize → analyze → view.
Everything that is not a verb is a *destination for looking at output* (Results) or *machine state*
(Jobs, Settings). Nothing in the rail names a Python module or a PyQt tab.

**Optimize is one screen with a mode segment**, not two nav items. Flex-search and Ex-search differ
in exactly three places — the search method, whether a leadfield is required, and the electrode
input shape — and share subject selection, ROI definition, output naming, plan, and run. Merging
deletes one nav item, one duplicated ROI picker (`optimizer-ex/roi/RoiPicker.tsx`, 271 lines), one
duplicated PlanPanel (`optimizer-ex/PlanPanel.tsx`, 133 lines vs `optimizer-flex/PlanPanel.tsx`, 91),
and the "Optimizer · " prefix that forces both nav labels to wrap onto two lines
(`optimizer-flex-spherical-light.png`, the rail item occupies 2 lines and 44 px).

**Analyze absorbs the three statistics panels.** `panels/nifti-group-average`,
`panels/cluster-permutation` and `panels/nilearn-visuals` are group-level analysis; they belong
behind Analyze's mode segment, not in the nav. This also fixes their broken Plan placement
(`panels/nifti-group-average/index.tsx:184`, `panels/cluster-permutation/index.tsx:360`).

**View is Tetravox.** See §7.

---

## 4. Density tokens — the delta

Keep `ui/tokens.css`'s palette wholesale: it is contrast-verified with a real test
(`tokens.css:38-45` cites `tests/unit/tokenContrast.test.ts`), the `--ink-3` restriction at
`tokens.css:27-34` is correct, and `--field` as a subject-only colour (`tokens.css:59-61`) is a good
idea. Change only geometry and type.

| token | today | new | where it bites |
|---|---|---|---|
| `--control-height` | 32 (`tokens.css:96`) | **28** | every input, select, button |
| `--control-height-sm` | 28 (`tokens.css:97`) | **24** | table-row controls, chips |
| `--control-height-lg` | 40 (`tokens.css:98`) | **32** | the action bar's primary only |
| `--row-height` | 36 (`tokens.css:95`) | **28** | tables: 8 more rows per screen |
| `--radius-control` | 4 (`tokens.css:85`) | **3** | |
| `--radius-card` | 6 (`tokens.css:86`) | **4**, renamed `--radius-pane` | |
| **new** `--field-label-w` | — | **148** | the label column |
| **new** `--section-header-h` | — | **28** | flush section headers |
| **new** `--pane-pad` | — | **12** | replaces `.card-body`'s 16 (`components.css:849`) |
| **new** `--viewport` | — | `#0B0E12` in *both* themes | Tetravox panes (§7) |

Type scale (`base.css:76-106`), one step down across the board:

| class | today | new |
|---|---|---|
| `.text-caption` | 12/16 | **11/14** |
| `.text-dense` | 13/18 | **12/16** |
| `.text-body` (base) | 14/20 | **13/18** |
| `.text-emphasis` | 16/22 | **14/20** |
| `.text-section` | 20/26 | **13/18 600** (section headers are not headlines) |
| `.text-page-title` | 24/30 | **deleted** — no page has a title any more |
| `.text-eyebrow` | 12 / .06em | **11 / .07em** |

13 px base is what Figma, Linear and VS Code all ship; `DESIGN.md:64-66`'s 14 px base is a web
default, not a workstation one. Shadows: `--shadow-1` (`tokens.css:67`) is removed from `.card`
(`components.css:834`) and survives only on Popover/Drawer/Dialog. Panes are separated by 1 px
`--line`, not by elevation.

Ground inversion: the app ground becomes `--surface` and panes are delineated by rules;
`--bg` survives only as the gutter behind the resizable dividers and the jobs rail. Today
`shell.css:8` paints `--bg` and every card floats a white rectangle on it — nine floating
rectangles on the Settings screen alone (`settings-light.png`).

---

## 5. Form compaction — seven rules

### R1 · Label-left rows, 28 px, no third line

```css
.field {                       /* replaces components.css:267-272 */
  display: grid;
  grid-template-columns: var(--field-label-w) minmax(0, 1fr);
  align-items: center;
  column-gap: var(--space-3);
  min-height: 28px;
}
```
Label is 12 px `--ink-2`, right-aligned to the gutter. Help text (`components.css:286-289`, a third
line on nearly every field) becomes an `(i)` 12 px trigger after the label opening a Popover, **or**
a unit suffix inside the control where it is a unit (`mm`, `mA`, `V/m` — `NumberInput` already
supports this, `DESIGN.md:127`). Cost per field: **70 px → 28 px**.

Full-bleed exception (`grid-column: 1 / -1`): coordinate/sphere tables, `ElectrodePairsEditor`,
`KeyValueTable`, `PathInput`, chip `MultiSelect`, consoles, callouts. The viewer page already
hand-rolls this escape hatch with an inline style and a comment explaining why
(`viewer/index.tsx:713-715`) — make it a supported prop instead.

### R2 · Sections, not Cards

`FormSection` (`ui/Layout.tsx:137-167`) stops rendering `<Card>`. New shape:

```
▾ ELECTRODES                              ellipse · 8×8 mm · gel 4 mm   •   ⋯
──────────────────────────────────────────────────────────────────────────────
  Shape          ⟨ Ellipse │ Rectangle ⟩
  Dimensions     8   × 8    mm
  Gel thickness  4          mm
──────────────────────────────────────────────────────────────────────────────
▸ CONDUCTIVITY                            isotropic · SimNIBS defaults
```

Header: 28 px, 11 px uppercase eyebrow, chevron, right-aligned **value summary** in `--ink-2`, a
`•` when any child is non-default, a `⋯` menu (Reset section · Copy as JSON). Body padding
`var(--pane-pad)` = 12. Separator: 1 px `--line`. Cost per section: **94 px → 41 px**.

### R3 · Progressive disclosure, three tiers, with a hard rule

- **Tier 1, always open**: fields the plan cannot resolve for you — subject, ROI/target,
  montage or leadfield, optimization goal, analysis space. Typically 4–7 fields.
- **Tier 2, collapsed by default**: everything with a defensible default — electrode geometry,
  conductivity, hyper-parameters, output fields, run settings, "automatic simulations".
- **Tier 3, dialog**: table editors. Already correct — `ConductivityDialog`
  (`simulator/ConductivityDialog.tsx:68`), `MontageManager`'s editor
  (`simulator/MontageManager.tsx:219`), `QsiPrepDialog`/`QsiReconDialog`
  (`preprocess/QsiPrepDialog.tsx:44`, `preprocess/QsiReconDialog.tsx:105`). Keep all four.

**The rule that makes this safe: a collapsed section must render its current values in its own
header.** Never collapse state out of sight. This is what `ui/Layout.tsx:155-163`'s existing
"Advanced" disclosure gets wrong — it shows the word "Advanced" and nothing else, so the user cannot
tell whether anything inside is set (`optimizer-flex-spherical-light.png`, the "› Advanced" row at
y≈583 tells you nothing about the three anisotropy fields behind it).

### R4 · Defaults are visible, changes are marked

A field still at its schema default renders its value in `--ink-2`; a changed field renders in
`--ink` and gets a 2 px `--accent` tick in the label gutter; its section header gets the `•`.
`⋯ ▸ Reset section` clears back to defaults. Borrowed from Blender's overridden-property tint and
Xcode's inspector. This is what buys the right to collapse Tier 2 by default.

### R5 · Inline validation that a collapsed section cannot hide

Keep `DESIGN.md:125-128` exactly: validate on blur and on submit, focus the first error, **Run stays
enabled** and the Plan carries the errors (`optimizer-flex/PlanPanel.tsx:43`). Add two things:
the errored control gets a 1 px `--danger` border and its error string replaces the help slot in the
same row (11 px, `--danger`, no new line unless it wraps); and **the section header inherits a
`--danger` dot**, so an error inside a collapsed Tier-2 section is always visible. The Plan's error
list entries are click-targets that expand the owning section and focus the field.

### R6 · Sticky action bar **and** Plan panel — the split is by role. Decided.

**Decision: keep the Plan panel, move the Run button out of it into a 44 px sticky action bar.**

Reason: the Plan is genuinely load-bearing — resolved outputs, `exists`/`will_overwrite`, lock waits
"will queue behind #12", cost — and it is the app's second signature (`DESIGN.md:25-29`); the server
contract is built for it (`dev/notes/v3-build-plan.md:125-127`, `POST /api/plan/{kind}`). But the
*button* is in the wrong place. Today it sits at the top of a right-hand card, ~500 px above the
control the user is actually editing when they finish a long form — visible in
`optimizer-flex-nonroi-spherical-light.png` (Run at y≈290; the last editable field, the sphere
radius, at y≈689) and worse in `preprocess-light.png` (Queue 2 jobs at y≈658, with three more
sections below the fold). Two of the six run screens have already broken away from the pattern and
put Plan inline at the bottom instead (`panels/nifti-group-average/index.tsx:184`,
`panels/cluster-permutation/index.tsx:360`) — that is the pattern failing under load, not two
authors being sloppy.

The split:

```
Inspector, top block                 Action bar (sticky, 44 px, spans both panes)
─────────────────────────            ─────────────────────────────────────────────
PLAN                      ⟳          2 jobs · 8 CPU · 16 GB · 1 overwrite
2 jobs · 8 CPU · 16 GB               ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈  [Save preset ▾] [▶ Run 2 simulations ⌘⏎]
ernie → Thalamus       new
101   → Thalamus  overwrite ⚠        left: the one-line digest (mirrors the panel)
waits  none                          right: one secondary + one primary
⚠ before you run this…               primary label is generated from the plan
                                     (DESIGN.md:29 — "Run simulation" / "Queue 3 jobs")
```

The bar is always present on the six run screens, never on Project / Results / Jobs / View /
Settings. `⌘Enter` fires it from anywhere on the page. When the plan is unresolvable the digest reads
the blocking reason (`Pick a subject and an ROI`) and the primary is disabled with that as its
tooltip — never a silent disabled button.

### R7 · Two-up rows, container-queried

Work pane is 891 px at 1280; a row is 148 + 240 = 388 px; two rows + 24 px gutter = 800 px. So:

```css
.form-rows { display: grid; grid-template-columns: repeat(2, minmax(340px, 1fr)); gap: 8px 24px; }
@container (max-width: 760px) { .form-rows { grid-template-columns: 1fr; } }
```

`.card-body` already establishes the container (`components.css:850-857`) — that machinery survives,
retargeted at the section body. Note the current threshold is 560 px (`components.css:880`), which
at a 674 px column means the two-column grid *never* collapses and never has room; raising the
column to 891 px is what makes two-up honest.

### R8 · Presets replace re-typing

Every run screen gets `Save preset ▾` in the action bar, writing the form state (not the subject)
under `/api/catalog/…`-style storage. Rationale: the density win is only half the story — the other
half of "why is this form so long" is that a lab runs the same 24-field flex-search on forty
subjects. A preset chip in the context bar (`Preset: deep-thalamic ▾`) collapses forty repeats to
one selection. This is the one *addition* in the proposal; everything else removes.

---

## 6. The six core screens

Frames below are 1280 × 800 to scale (≈116 chars ≈ 1280 px, ≈1 line ≈ 21 px).

### 6.1 Project (⌘1) — replaces Subjects + Subject info

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ Project                              ⌘K              ● connected   ⚡0 running   ?   ⚙     │
├────┼─────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│ ▤  │ 3 subjects   [ Filter…            ]  ⟨All│Ready│Incomplete⟩  + Add│ sub-ernie                        │
│ ⚡ │ ─────────────────────────────────────────────────────────────── │ ────────────────────────────────── │
│ ◎  │ Subject   raw fs m2m dwi ct   Leadfields        Sims  Opt  Anly │ Head model   m2m · charm 4.6       │
│ ▦  │ ernie      ●  ●  ●   ●  ○    GSN-HydroCel-185     3    2    5  │ Surfaces     recon-all 7.4.1       │
│ 👁 │ 101        ●  ○  ●   ○  ●    —                    1    0    0  │ Leadfield    GSN-185 · 2.0 GB      │
│ ── │ MNI152     ○  ○  ●   ○  ○    —                    0    0    0  │ ────────────────────────────────── │
│ ▥  │                                                                 │ RECENT                             │
│ ▤  │                                                                 │ ✓ sim  Thalamus        2 h  open ▸ │
│ ⚙  │                                                                 │ ✓ flex L_Insula        1 d  open ▸ │
│    │                                                                 │ ✗ ex   E2E_Target      2 d  log  ▸ │
│    │                                                                 │ ────────────────────────────────── │
│    │                                                                 │ [Simulate] [Optimize] [Analyze]    │
│    │                                                                 │ [View in Tetravox]                 │
│    ├─────────────────────────────────────────────────────────────────┴────────────────────────────────────┤
│    │ No jobs running                                                                             ⌃  ⌘J    │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Removed / merged:**
- "Subject info" as a nav item and a page — its table *is* this table
  (`panels/subject-info/index.tsx:157-198` columns Subject / Data / Leadfields / Simulations, plus
  Refresh and Export selected). Its Export moves to the `⋯` on this toolbar. **−1 nav item, −198 lines.**
- The page header (title 24 px + purpose, `subjects/index.tsx:89`) — **−86 px**.
- The `Simulations` Card in the inspector (`subjects/index.tsx:22-54`) and its 180 px centered
  `EmptyState` (`subjects/index.tsx:26-31`) — replaced by a 3-line "Recent" list and four verbs.
  Centering a 3-line empty block in a 300 px inspector wasted 200 px; **this overrules
  `DESIGN.md:69` ("Nothing is centered except empty states") — empty states are left- and
  top-aligned, max two lines.**
- The chip trio raw/freesurfer/m2m (`subjects/index.tsx:68-80`, three 20 px pills per row) becomes
  five 8 px `StatusDot`s under fixed column heads. Row height 36 → 28.

**Result at 800:** 20 subject rows visible where 3 fitted before.

### 6.2 Simulate (⌘3)

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ [ernie, 101 ▾] ▸ Simulate     Preset ⟨ — ▾ ⟩    ⌘K      ● connected  ⚡3 running   ?   ⚙  │
├────┼─────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│ ▤  │ Source  ⟨ Montage │ Flex result │ Free-hand ⟩       Net GSN-185 ▾│ PLAN                          ⟳   │
│ ⚡ │ ─────────────────────────────────────────────────────────────── │ jobs 2   cpus 8   mem 16 GB        │
│ ◎  │ ☑ F3_F4             E24→E124      1.0  1.0 mA       ✎  🗑      │ ernie → Thalamus            new    │
│ ▦  │ ☐ Thalamus_target   E37→E87       —                 ✎  🗑      │ 101   → Thalamus      overwrite ⚠  │
│ 👁 │ ☑ L_Insula_target   E37→E18       1.0  1.0 mA       ✎  🗑      │ waits  none                        │
│ ── │ ☐ E2E_Test_Montage  E1→E2, E3→E4  —                 ✎  🗑      │ ⚠ Overwrites an existing           │
│ ▥  │                                       Uni-polar ▾  + New montage│   simulation for 101.              │
│ ▤  │ ─────────────────────────────────────────────────────────────── │ ────────────────────────────────── │
│ ⚙  │ ▾ RUN NAME                                                      │ RECENT                             │
│    │   Name        Thalamus                                          │ ✓ ernie/Thalamus     2 h   open ▸  │
│    │ ▸ ELECTRODES            ellipse · 8×8 mm · gel 4 mm         •   │ ✓ 101/L_Insula       1 d   open ▸  │
│    │ ▸ CONDUCTIVITY          isotropic · SimNIBS defaults            │                                    │
│    │ ▸ OUTPUT FIELDS         TI_max                                  │                                    │
│    ├─────────────────────────────────────────────────────────────────┴────────────────────────────────────┤
│    │ 2 jobs · 8 CPU · 16 GB · 1 overwrite       [Save preset ▾]        [ ▶ Run 2 simulations      ⌘⏎ ]    │
│    ├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│    │ ● sim ernie ▓▓▓▓▓▓░░░ 62% 4m12s   ● pre 101 ▓░░ 8%   ✓ analyzer ernie 9s                   ⌃  ⌘J   │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Removed / merged (from `simulator/index.tsx` + `simulator-light.png`):**
- **"Subjects" Card** (`:126-141`) → the breadcrumb's subject combobox. **−120 px.**
- **"Selected jobs" Card** (`:158-192`) → merged into the montage table. It was a second table
  listing the rows you had just ticked in the first table, with the currents editor as its only
  unique content (`:179-181`); the currents columns move inline. **−1 table, −180 px.**
- **"Global parameters" Card** (`:194-244`) → split into three Tier-2 sections (Electrodes,
  Conductivity, Output fields), all collapsed, each showing its values in the header. Its `(i)`
  Popover for output-field help (`:198-202`) survives on the Output fields header. **−260 px.**
- **The Tabs container Card** (`:143-156`) → the tab strip becomes a segmented control in the
  toolbar row; `Tabs`'s 16 px content padding (`components.css:910`) goes. **−94 px.**
- Page header (`:122`). **−86 px.**
- Plan Card chrome (`simulator/PlanPanel.tsx:130`) → flush inspector block; Run button → action bar.

**Net: 4 Cards + 1 Plan Card → 1 table + 3 collapsed section headers.** ~740 px of chrome and
duplicated content removed; the montage table shows **8 rows** instead of 4 with everything else
still on screen.

### 6.3 Optimize (⌘4) — flex + ex + mEx, one screen

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ [ernie ▾] ▸ Optimize    Preset ⟨ deep-thalamic ▾ ⟩   ⌘K     ● connected  ⚡1 running  ? ⚙ │
├────┼─────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│ ▤  │ Method ⟨ Flex-search │ Ex-search │ mEx-search ⟩   Run name  NewRun│ PLAN                         ⟳   │
│ ⚡ │ ─────────────────────────────────────────────────────────────── │ jobs 1   cpus 8   mem 12 GB        │
│ ◎  │ ▾ TARGET                                                        │ ernie → ex-search/NewRun    new    │
│ ▦  │   Region     ⟨Cortical│Subcortical│Spherical⟩  Space ⟨Subj│MNI⟩ │ electrodes        185              │
│ 👁 │   Atlas      DK40 ▾              (i)    Volumetric  ☐          │ current splits      7              │
│ ── │   Regions    [L · bankssts ×] [+ add]                          │ combinations  119,140              │
│ ▥  │   ───────────────────────────────────────── or a sphere ─────  │ waits  none                        │
│ ▤  │   x  10.0   y  -20.0   z  15.0   r  8.0  mm            🗑  +    │ ────────────────────────────────── │
│ ⚙  │ ▾ OBJECTIVE                                                     │ LEADFIELD                          │
│    │   Goal       focality — threshold-free ▾  (i)                   │ ● GSN-HydroCel-185      2.0 GB     │
│    │   Post-proc  max_TI ▾            Non-ROI   everything else ▾    │ ○ EGI_template     not generated   │
│    │   Weight     0.0    (i)          Aniso     isotropic ▾          │ [ Generate leadfield ]             │
│    │ ▸ ELECTRODES     4 × ellipse 8×8 · gel 4 · min dist 20 mm   •   │ ────────────────────────────────── │
│    │ ▸ SOLVER         DE · pop 13 · maxiter 500 · tol 0.1            │ RECENT RUNS                        │
│    │ ▸ AFTER THE RUN  final sim ☑ · mapped sim ☐                     │ ✓ E2E_Target  score 0.91  open ▸   │
│    ├─────────────────────────────────────────────────────────────────┴────────────────────────────────────┤
│    │ 1 job · 8 CPU · 12 GB · 119,140 combinations       [Save preset ▾]      [ ▶ Run ex-search      ⌘⏎ ] │
│    ├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│    │ ● ex ernie ▓░░░ 0s                                                                          ⌃  ⌘J   │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Method-dependent content is **only** what actually differs: Flex shows SOLVER (DE hyper-params,
`optimizer-flex/HyperParams.tsx:26`); Ex/mEx show the leadfield block in the inspector
(`optimizer-ex/LeadfieldPanel.tsx`) and swap TARGET's electrode-selection rows for E1±/E2± chip
fields (`optimizer-ex/ExForm.tsx:192-219`); mEx adds an `mTI CONFIGURATION` Tier-2 section
(`optimizer-ex/MExForm.tsx:230`). Everything else is shared and stops being written twice.

**Removed / merged:**
- **One nav item** (`optimizer-ex/index.tsx` PageDef, order 40, ⌘5) and its two-line rail label.
- **Two ROI pickers → one** (`pages/_shared/roi/RoiPicker.tsx` 327 lines kept;
  `pages/optimizer-ex/roi/RoiPicker.tsx` 271 lines deleted).
- **Two Plan panels → one** (`optimizer-ex/PlanPanel.tsx` 133 lines deleted).
- **"Subjects" Card** (`optimizer-flex/index.tsx:225-249`) and **"Subject and leadfield" Card**
  (`optimizer-ex/index.tsx:60`) → breadcrumb + inspector leadfield block. **−240 px.**
- **"ROI definition" + "Focality options" Cards** (`optimizer-flex/index.tsx:299-312`) merged into
  one TARGET section + one OBJECTIVE section; the non-ROI picker no longer duplicates the whole
  Cortical/Subcortical/Spherical + Space + sphere-table stack visible in
  `optimizer-flex-nonroi-spherical-light.png` — it collapses to a single `Non-ROI ▾` select whose
  "Specific region" value reveals a *second row set inside OBJECTIVE*, not a second card. **−320 px.**
- **"Automatic simulations (optional)"** (`optimizer-flex/index.tsx:317-343`) → `AFTER THE RUN`,
  collapsed, header shows both checkbox states. **−150 px.**
- **The nested "Results" tab** (`optimizer-ex/ResultsPanel.tsx`, `optimizer-ex/index.tsx` tab 3) →
  Results screen. A run screen does not host a results browser.
- Page header, both Card headers, both Tab strips.

**Net:** two screens totalling 9 Cards + 2 Plans + 3 nested tabs → one screen with 2 open sections
and 3 collapsed ones. Fits 800 with the sphere table visible, which today requires two scrolls.

### 6.4 Analyze (⌘5) — subject + group + figures

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ [ernie ▾] ▸ Analyze     Preset ⟨ — ▾ ⟩       ⌘K          ● connected  ⚡0 running   ?  ⚙  │
├────┼─────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│ ▤  │ Scope ⟨ Subject │ Group │ Figures ⟩       Analysis name  ROI_1   │ PLAN                          ⟳   │
│ ⚡ │ ─────────────────────────────────────────────────────────────── │ jobs 1   cpus 2   mem 4 GB         │
│ ◎  │ ▾ INPUT                                                         │ ernie/Thalamus → analyses/ROI_1    │
│ ▦  │   Simulation  Thalamus ▾           Field   auto (TI_max) ▾ (i)  │ waits  none                        │
│ 👁 │   Space       ⟨ Mesh │ Voxel ⟩     Tissue  GM ▾  (voxel only)   │ ────────────────────────────────── │
│ ── │ ▾ TARGET                                                        │ LAST RESULT · ROI_1                │
│ ▥  │   Type        ⟨Cortical│Subcortical│Spherical⟩  Coords ⟨Sub│MNI⟩│ TI_max  mean 0.412  max 0.981      │
│ ▤  │   x  -12.4   y  -18.2   z  7.9   r  5.0  mm            🗑   +   │ TI_norm mean 0.301  max 0.774      │
│ ⚙  │   (i) One row = the classic single-sphere analysis.             │ [ Open in View ]  [ Report ▸ ]     │
│    │ ▸ OUTPUTS       csv · json · mesh · report                      │ ────────────────────────────────── │
│    │                                                                 │ RECENT                             │
│    │                                                                 │ ✓ ROI_1     2 h ago      open ▸    │
│    ├─────────────────────────────────────────────────────────────────┴────────────────────────────────────┤
│    │ 1 job · 2 CPU · 4 GB                              [Save preset ▾]      [ ▶ Run analysis       ⌘⏎ ]  │
│    ├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│    │ No jobs running                                                                             ⌃  ⌘J   │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

`Scope: Group` swaps INPUT for a **subject × simulation × group table** (one 28 px row per subject,
`+ Add subject`) and TARGET for a `Method ⟨ Average / difference │ Cluster permutation ⟩` segment —
absorbing `panels/nifti-group-average/index.tsx` (Subjects rows `:133-155` + Analysis configuration
`:156-183`) and `panels/cluster-permutation/index.tsx` (Subjects `:222`, Analysis `:262`, Advanced
`:307`) wholesale. `Scope: Figures` is `panels/nilearn-visuals/index.tsx` (Subject-simulation pairs,
Output, Visualization parameters).

**Removed / merged:**
- **3 nav items** (Cluster permutation, NIfTI group averaging, Nilearn visuals) and their 3 page
  headers. **−3 rail rows, −258 px of headers.**
- Their **3 inline Plan Cards** (`panels/nifti-group-average/index.tsx:184`,
  `panels/cluster-permutation/index.tsx:360`, `panels/nilearn-visuals` PlanSummary) → the one
  inspector Plan block. This is the single largest consistency fix in the proposal: today three
  screens put the Plan below the fold and leave the right rail empty
  (`panel-nifti-group-average-light.png`, `panel-nilearn-visuals-light.png`).
- **"Subject and simulation" Card** (`analyzer/AnalyzerPage.tsx:353`) → INPUT rows + breadcrumb; the
  `Mode: Single/Group` radio (`:355-360`) is promoted to the Scope segment where it belongs.
- **`ResultsPanel`** (`analyzer/ResultsPanel.tsx:115-128`, an entire results browser appended below
  the form) → the inspector's LAST RESULT block + a link to Results. **−219 lines, −300 px.**
- The three "Add at least one …" info Callouts that occupy 60 px each
  (`panel-nifti-group-average-light.png` y≈730, `panel-nilearn-visuals-light.png` y≈730) → the
  action bar's blocking-reason digest. **−180 px across the three.**
- The "Not yet implemented" subcortical warning (`analyzer/AnalyzerPage.tsx:493`) stays but becomes
  a `⚠` chip on the TARGET header + the reason in the action-bar digest, not a 4-line block.

### 6.5 View (⌘6) — Tetravox, full-bleed

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ [ernie ▾] ▸ View        ⌘K                             ● connected  ⚡2 running   ?    ⚙  │
├────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▤  │ [ernie ▾] [Thalamus ▾] [TI_max ▾] ⟨Subj│MNI⟩  + Add layer ▾   │ 2×2 ▾ ⊹ RAD ▭ ⌗ 📷 │  ⋯ open ext ▾ │ 40
│ ⚡ ├──────────────┬─────────────────────────────────────────────────┬─────────────────────────────────────┤
│ ◎  │ LAYERS       │  ┌───────────────┬───────────────┐             │ x  -42.0  y  18.0  z  6.0   RAS ▾  │
│ ▦  │ 👁 TI_max    │  │ A             │ A             │             │ ─────────────────────────────────── │
│ 👁 │    hot 0.2–1 │  │      axial    │    coronal    │             │ CURSOR                              │
│ ── │    ▓▓▓▓ 0.7  │  │  L         R  │  L         R  │             │ T1        vox 128 91 74   val 412   │
│ ▥  │ 👁 T1        │  │             P │             P │             │ TI_max    vox 128 91 74   val 0.71  │
│ ▤  │    grey      │  ├───────────────┼───────────────┤             │ ernie.msh elm 118342  tag 2 GM      │
│ ⚙  │ 👁 ernie.msh │  │ S             │      3D       │             │ ─────────────────────────────────── │
│    │    tissues ▸ │  │   sagittal    │    ⟨cube⟩     │             │ MOUSE                               │
│    │ 👁 electrodes│  │ A         P   │               │             │ TI_max    val 0.68                  │
│    │              │  │             I │  ▬▬ 20 mm     │             │ ─────────────────────────────────── │
│    │ + dataset    │  └───────────────┴───────────────┘             │ REGIONS   [search…]                 │
│    │              │                                                 │ 👁 ▪ L-Thalamus     4,182           │
│    ├──────────────┴─────────────────────────────────────────────────┴─────────────────────────────────────┤
│    │ ● sim e2e-system ▓▓▓▓░ 5s   ● report 101 ▓░ 2s                                              ⌃  ⌘J  │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Regions follow Tetravox's own UX contract (`docs/ARCHITECTURE.md:2657-2664`): layers left, view grid
centre, coordinate bar → measurements → info → regions right. The shell contributes only the 56 px
rail, the 40 px context bar, the 40 px source bar and the 32 px jobs rail — **152 px of chrome
around a 648 px canvas**, versus today's Viewer which is 100 % form and 0 % pixels.

**Removed / merged (from `viewer/index.tsx`, 791 lines):**
- **"Source" FormSection** (`:635-676`, Mode / Subject / Simulation / Path / Space) → the 40 px
  source bar. Mode's five kinds (`KIND_OPTIONS`) collapse: subject/simulation/analysis are implied
  by which of the three comboboxes you fill; `custom` and `group` become `+ Add layer ▾ ▸ From
  path…` / `▸ Group result…`. **−1 section, −5 fields, −220 px.**
- **"Field & overlays" FormSection** (`:678-701`) → `[TI_max ▾]` in the bar; atlas overlay and voxel
  analysis overlay become `+ Add layer ▾ ▸ Atlas` / `▸ Analysis overlay`. **−180 px.**
- **"Electrode overlay" FormSection** (`:703-749`) including its 3-line info Callout (`:590-594`)
  → `+ Add layer ▾ ▸ Electrodes`, which queues the existing `tit.tools.electrode_overlay` tools job
  (`tit/server/routes/viewers.py:11-38`) and auto-inserts the layer when it succeeds. Its
  JobStateChip/Stop/Refresh-status trio (`:729-745`) is redundant with the jobs rail. **−260 px.**
- **"Layers" FormSection** (`:751-782`) → Tetravox's own layer panel, which already has per-kind
  property editors, a histogram widget with `min–max / 2–98 % / p50–p99.9 / symmetric ±p99` presets,
  a colour-bar toggle and a region table (`docs/ARCHITECTURE.md:2735-2755`). **−1 section, −186 px
  of hand-rolled `LayerRow`.**
- **"Freeview command" Card** (`:515-596`) — the `<pre>` printing `freeview -v /mnt/example/…`, Copy
  command, Refresh, Open in Freeview, plus an embedded `JobConsole`. **Deleted entirely.** The argv
  is a server implementation detail (`tit/viewspec.py:472` `to_freeview_args`); a researcher should
  never read one. Freeview survives only as `⋯ ▸ Open externally ▸ Freeview`.
- **"Gmsh" Card** (`:597-632`) → `⋯ ▸ Open externally ▸ Gmsh`.
- **"X server required" Callout** (`:510-513`) → the `⋯` menu's items are disabled with that
  sentence as their tooltip when `capabilities.x11_display` is false. A permanent 100 px warning for
  a feature that is now a fallback is exactly backwards.

**Net: 4 FormSections + 3 right-hand Cards + 1 callout → 1 source bar + Tetravox.**

### 6.6 Jobs (⌘8 / ⌘J)

```
┌────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣  │ example ▸ Jobs                                 ⌘K                ● connected  ⚡2 running   ?    ⚙  │
├────┼─────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│ ▤  │ ⟨All│Running│Failed│Done⟩  kind ▾  subject ▾  [filter…]  ⟨Flat│Grouped⟩│ #1042  sim  ernie   ● running│
│ ⚡ │ ────────────────────────────────────────────────────────────────│ ────────────────────────────────── │
│ ◎  │ State      Kind      Subject  Stage        Elapsed  CPU   RSS   │ stage  head modelling   62 %       │
│ ▦  │ ● running  sim       ernie    ● active       4m12s  78.9 1.8GB │ waiting on  —                      │
│ 👁 │ ● queued   pre       101      —                  0s   —    —   │ ────────────────────────────────── │
│ ── │ ✓ succeed  analyzer  ernie    done · 100 %       9s   —    —   │ CONSOLE          [filter…]  ⟨follow⟩│
│ ▥  │ ✗ failed   pre       104      charm exit 1      38s   —    —   │ [stage] head modelling started      │
│ ▤  │ ● running  ex        ernie    ● active         9m 0s 76.3 3.2GB│ charm --forceqform sub-101          │
│ ⚙  │                                                                 │ low contrast in T1 near vertex     │
│    │                                                                 │ charm exited 1: see log for details │
│    │                                                                 │ ────────────────────────────────── │
│    │                                                                 │ ARTIFACTS                          │
│    │                                                                 │ 📄 report.html      view  open  ▸  │
│    │                                                                 │ [Stop] [Rerun] [Reveal log]        │
│    ├─────────────────────────────────────────────────────────────────┴────────────────────────────────────┤
│    │ ● sim ernie ▓▓▓▓▓░ 62%   ● ex ernie ▓▓░ 21%                                                 ⌃  ⌘J  │
└────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Removed / merged (`jobs/index.tsx`, `jobs/JobDetailDrawer.tsx`):**
- **The filters Card** (`:148-165`) — three stacked `Field`s in a bordered box, 96 px tall for three
  selects — becomes a 32 px toolbar row: a state segment + two comboboxes + a text filter. **−96 px.**
- **The "All jobs / Groups" Tabs** (`:141-190`) → a `⟨Flat│Grouped⟩` segment in the same toolbar;
  `GroupsView` (`jobs/GroupsView.tsx`, 154 lines) becomes a grouping mode of the one table, not a
  second table. **−1 tab strip, −16 px content padding, −1 component.**
- **`JobDetailDrawer`** (374 lines) → the inspector. A drawer that overlays the table you selected
  the row from is the wrong container for something you read *while* the row updates. Its three
  AlertDialogs (Stop `:284`, Force `:295`, Delete `:306`) stay as dialogs.
- Page header + the dev-only "Submit test job" button (`:128-137`) → palette command, dev builds only.
- Row height 36 → 28: **16 rows visible instead of 9.**

**The rail and the page are the same component at two heights.** Collapsed 32 px = traces; expanded
260 px (⌘J) = this table without the inspector; the page (⌘8) = this table with it. One `JobsTable`,
one `JobConsole`, three heights — versus today's `JobsRail` + `JobsTable` + `JobDetailDrawer` +
`GroupsView`.

---

## 7. Tetravox integration — the concrete plan

**Route.** `/view` renders a `<TetravoxHost>` that mounts a canvas and calls
`create(canvas, opts)` from `packages/engine/src/api.ts` (`docs/ARCHITECTURE.md:759`,
`:934` for `create`). No page header, no `PageLayout`, no shell padding. The shell's inspector is
*reused* for Tetravox's right column (coordinate bar, info, measurements, regions —
`docs/ARCHITECTURE.md:2657-2662`), so the app has exactly one inspector everywhere.

**Getting bytes in — decided.** The engine's `DatasetSource` is
`{kind:'path'|'file'|'bytes'}` (`docs/ARCHITECTURE.md:772-776`), mapping onto the worker's
`LoadSource` (`docs/ARCHITECTURE.md:1879-1975` / §6.5.1), and the worker fetches
`tetravox://file/<abs path>` itself — **bytes never cross IPC and never touch the UI thread**
(`docs/ARCHITECTURE.md:1013-1016`, rule 3).

TI-Toolbox's files are *inside the container*, but the project is bind-mounted, and the server
already reports both halves: Settings shows `Container path /mnt/example` and
`Host path /Users/example/projects/example` (`settings-light.png`; `GET /api/project`,
`dev/notes/v3-build-plan.md:142`). So:

1. `GET /api/view/{kind}` returns a ViewSpec whose layer paths are already jailed and resolved
   (`tit/viewspec.py:299` `build_view`, `:514` `jail_roots`, `:524` `resolve_jailed`;
   `tit/server/routes/viewers.py:64-85` re-jails client-supplied specs).
2. The host rewrites each `layer.path` container→host with the project prefix pair, calls Electron
   main's `allowPath` equivalent, and hands Tetravox `{kind:'path', path: hostPath, sidecars:{lut}}`.
   The LUT sidecar role is already in the ViewSpec (`layer.lut`, build-plan §3 Viewers line) and
   Tetravox keys sidecars **by role, not position** (`docs/ARCHITECTURE.md:1919-1921`) — they line up.
3. **Fallback for a non-bind-mounted / remote project**: `{kind:'url'}` against
   `GET /api/files/artifact?path=` (`dev/notes/v3-build-plan.md:140`), extended with Range support.
   Slower, still correct.

Three follow-ons the shell must respect and that I am naming so nothing is discovered late:
- Tetravox's privileged `tetravox://` scheme and its read allow-list (`docs/ARCHITECTURE.md:1035-1043`,
  rule 9) means the TI-Toolbox main process must mint admissions for the ViewSpec's paths **and their
  sidecars together**, from a user gesture (opening the View screen with a chosen simulation counts).
- `Engine.setTheme` is called in the same tick as the shell's `data-theme` flip
  (`docs/ARCHITECTURE.md:2731-2733`), and **the panes stay `--viewport` dark in both themes**.
- The mesh is 847 k nodes (`ernie.msh`); `removeDataset(id)` ⇒ `worker.terminate()` is the only way
  memory comes back (`docs/ARCHITECTURE.md:1005-1010`, rule 1), so the host must drop datasets when
  the subject changes, not keep a cache.

**Freeview and Gmsh** stay exactly as they are on the server (`tit/server/routes/viewers.py:181-224`)
and lose their UI to a single `⋯ ▸ Open externally ▸ {Freeview, Gmsh}` menu, disabled with a reason
when `capabilities.x11_display` is false (`viewer/index.tsx:509`).

**Later, not now:** Tetravox's extension mechanism (`docs/ARCHITECTURE.md:3176-3200`) is the right
home for a TI-specific panel (electrode placement, ROI sphere picking against the anatomy) — it is
a manifest plus an `index.js` with its own panel, keys and files, and the ESLint wall
(`docs/ARCHITECTURE.md:3229-3235`) keeps it from reaching into the shell. That is how the
"Open T1 in Freeview" button on the ROI pickers (`optimizer-flex/index.tsx:307`,
`analyzer/SphereRows.tsx`) eventually becomes "pick this sphere on the anatomy". Do not build it in
the same pass as the redesign.

---

## 8. Panels — where every one goes

The "Panels" nav group (`NavRail.tsx:12`, `DESIGN.md:192`) and the `panel-` PageDef prefix
(`app/registry.ts:63-66`) are **deleted**. The Settings toggle survives, renamed.

| panel today | new home | mechanism |
|---|---|---|
| Source (`panels/source/index.tsx`) | **Prepare ▸ Source** mode | It needs m2m + freesurfer and writes `derivatives/SimNIBS/sub-*/forward/` — it is pre-processing. Its two side-by-side run cards (`panel-source-light.png`: "Build forward solution" and "Map fields to fsaverage", each with its own Run button and its own "Select a subject." error) become **two sections and one action bar** whose primary switches on which section is open. **−1 nav item, −2 Run buttons, −2 duplicated error callouts.** |
| Nilearn visuals (`panels/nilearn-visuals`) | **Analyze ▸ Figures** | mode segment |
| NIfTI group averaging (`panels/nifti-group-average`) | **Analyze ▸ Group ▸ Average / difference** | sub-mode |
| Cluster permutation (`panels/cluster-permutation`) | **Analyze ▸ Group ▸ Cluster permutation** | sub-mode |
| Subject info (`panels/subject-info`) | **Project** | merged; it is a superset (§6.1) |
| Quick notes (`panels/quick-notes`) | **Notes drawer, `⌘⇧N`** | A 60 vh textarea on its own route (`panels/quick-notes/index.tsx:126`) is a destination for something that is a companion. Right-side drawer over any screen, autosaving to the same `/api/catalog/notes` (build-plan §3), with `Insert timestamp` / `Copy` / `Clear` in its header. **−1 nav item, −1 page header.** |

`Settings ▸ Feature panels` (`settings/index.tsx:209`, "Toggling one requires a reload to take
effect") becomes **`Settings ▸ Optional tools`**, and a toggle now shows/hides a *mode* inside
Prepare or Analyze. The whole `useEnabledPages` live-nav machinery (`app/registry.ts:38-78`, 40 lines
of commentary about React Query cache sharing) becomes a plain boolean read where the mode segment
renders — the elaborate mechanism exists only because panels were nav items.

---

## 9. Empty, loading, error, offline

**Empty.** Left-aligned, top-aligned, ≤ 2 lines, ≤ 1 action, no icon, no box. `EmptyState`'s current
centered icon + sentence + button block (`subjects/index.tsx:26-31`,
`simulator/index.tsx:132-137`, `viewer/index.tsx:757`) costs 180 px inside a 300 px inspector. New:
`No simulations for ernie yet.  Run one ▸` on one 18 px line. **This deliberately overrules
`DESIGN.md:69`.**

**Loading.** Skeletons only on *first* load, sized to real rows (`n × 28 px`), never a slab —
`subjects/index.tsx:92` uses `Skeleton height={240}` for a table whose real content is 3 × 28 px, so
the page visibly jumps. Refetch/refresh is a 2 px indeterminate bar under the context bar, nothing
else; that removes the layout shift between `analyzer-configured-light.png` and
`analyzer-cortical-light.png` where the whole ROI block re-skeletons on a mode change.

**Error.** One 32 px `Callout` line + a `Details ▸` disclosure holding the server message. Never a
persistent multi-line explanatory Callout in a form — `viewer/index.tsx:590-594` (3 lines about
electrode overlays), `analyzer/AnalyzerPage.tsx:493-499` (4 lines about subcortical) and
`optimizer-flex/index.tsx:283` help text are all `(i)` popovers. Field-level errors follow R5.
Toast policy unchanged (`DESIGN.md:139`): success 4 s, error persistent with Details.

**Offline / reconnecting.** The context bar's connection dot turns `--warning` and the bar grows a
24 px strip reading `Reconnecting to the server…` — no modal, no page replacement, forms stay
editable and the action bar's primary disables with that reason. Unauthenticated keeps the
full-window takeover (`Shell.tsx:14-29`) — that one is correct.

**Job failure.** A failed job pushes a `--danger` trace into the rail and a persistent toast with
`Open job ▸`; the page you are on never changes.

---

## 10. Keyboard and the command palette

`⌘K` opens a cmdk palette (`desktop/package.json:48` — the dependency is already there, used only by
`ui/Combobox.tsx:2`). Sources, in rank order:

1. **Go to** — the 9 destinations plus modes (`Optimize ▸ Ex-search`, `Analyze ▸ Group`).
2. **Subjects** — `sub-ernie` sets the breadcrumb's subject context globally.
3. **Runs** — every simulation / flex run / ex run / analysis from the catalog, action = open in
   Results or View.
4. **Jobs** — `#1042 sim ernie`, action = open in the inspector.
5. **Verbs** — Run (`⌘⏎`), Stop last job, Toggle theme, Open externally ▸ Freeview, New montage,
   Save preset, Reveal project folder, Open Gallery (dev only).

Full map:

| key | action |
|---|---|
| `⌘K` | command palette |
| `⌘1`–`⌘7` | Project · Prepare · Simulate · Optimize · Analyze · View · Results |
| `⌘8` | Jobs page · `⌘J` jobs rail (kept from `keyboard.ts:37-41`) |
| `⌘,` | Settings · `?` shortcuts sheet |
| `⌘⏎` | run the action bar's primary |
| `⌘\` | toggle inspector · `⌘⇧N` notes drawer |
| `[` / `]` | previous / next subject in the breadcrumb |
| `⌥1`–`⌥9` | toggle section *n* open/closed on a run screen |
| `Esc` | close dialog/drawer/palette (Radix, unchanged) |

`keyboard.ts:35` already guards typing targets and requires a modifier — that guard is what makes
this safe next to Tetravox, whose keys are **unmodified single letters and arrows**
(`docs/ARCHITECTURE.md` §7.5: `r` reset, `?` sheet, arrows nudge). Rule: while the Tetravox canvas
has focus the shell handles `⌘`-prefixed keys only and lets everything else through.

---

## 11. Theme

Keep the palette (`DESIGN.md:52-71`, `ui/tokens.css`) — it is deliberate, cool-biased, semantically
separated, and verified. Four changes:

1. **Ground inversion.** App ground = `--surface`; `--bg` survives only in the gutter behind
   dividers and the jobs rail. Panes are 1 px `--line` rules, not floating boxes.
2. **`--shadow-1` off `.card`** (`components.css:834`). Elevation is for things that are *actually*
   above the page: Popover, Drawer, Dialog, palette, toast — all of which already use `--shadow-2`.
3. **New `--viewport: #0B0E12`, identical in both themes**, for the Tetravox panes and any future
   render surface. Non-negotiable, and it is Tetravox's own rule
   (`docs/ARCHITECTURE.md:2723-2731`).
4. **Theme mechanics unchanged.** `tokens.css:11-116` / `:118-155` / `:157-192` already do the
   three-block light / `prefers-color-scheme` / `[data-theme]` dance correctly, including the
   `color-scheme` narrowing documented at `tokens.css:12-16`. Do not touch it.

`Settings ▸ Appearance` keeps system/light/dark (`settings/index.tsx:178-186`) and gains the density
note; there is **one** density, tuned compact — no comfortable/compact switch, because two densities
means two sets of screenshots and two sets of bugs.

---

## 12. Migration ledger — nothing is lost

Every page and every named section in the current app, and where it goes.

| today (file:line) | new home |
|---|---|
| `pages/subjects` — table (`subjects/index.tsx:97-109`) | **Project** — main table |
| `pages/subjects` — Simulations panel (`:22-54`) | **Project** — inspector "Recent" |
| `pages/panels/subject-info` — Subjects table + Refresh + Export (`panels/subject-info/index.tsx:157-198`) | **Project** — merged into the same table; Export → toolbar `⋯` |
| `pages/preprocess` — Subjects (`:481`) | **Prepare** — breadcrumb multi-select |
| `pages/preprocess` — Processing steps (`:541`) | **Prepare** — `STEPS` section, open |
| `pages/preprocess` — DWI processing (Docker) (`:603`) + QSIPrep/QSIRecon dialogs | **Prepare** — `DWI` section, collapsed; dialogs unchanged |
| `pages/preprocess` — Existing outputs (`:674`) | **Prepare** — inspector Plan's per-stage detail (already duplicated there, `preprocess-light.png`) |
| `pages/preprocess` — Run settings (`:691`) | **Prepare** — `RUN SETTINGS` section, collapsed |
| `pages/panels/source` — Build forward solution | **Prepare ▸ Source** — section 1 |
| `pages/panels/source` — Map fields to fsaverage | **Prepare ▸ Source** — section 2 |
| `pages/simulator` — Subjects (`:126`) | breadcrumb |
| `pages/simulator` — Montage source tabs (`:143-156`) | **Simulate** — source segment + table |
| `pages/simulator` — Selected jobs (`:158`) | **Simulate** — merged into the montage table |
| `pages/simulator` — Global parameters (`:194`) | **Simulate** — 3 collapsed sections |
| `simulator/MontageManager.tsx:219` editor · `ConductivityDialog.tsx:68` · `FreehandTab.tsx:92` | unchanged (Tier-3 dialogs / tab content) |
| `pages/optimizer-flex` — Subjects (`:226`) | breadcrumb |
| `pages/optimizer-flex` — Basic parameters (`:252`) | **Optimize** — `OBJECTIVE` |
| `pages/optimizer-flex` — ROI definition (`:300`) | **Optimize** — `TARGET` |
| `pages/optimizer-flex` — Focality options (`FocalityOptions.tsx:49`) | **Optimize** — rows inside `OBJECTIVE` |
| `pages/optimizer-flex` — Electrode parameters (`ElectrodeParams.tsx:19`) | **Optimize** — `ELECTRODES`, collapsed |
| `pages/optimizer-flex` — Hyper parameters (`HyperParams.tsx:26`) | **Optimize** — `SOLVER`, collapsed |
| `pages/optimizer-flex` — Automatic simulations (`:318`) | **Optimize** — `AFTER THE RUN`, collapsed |
| `pages/optimizer-ex` — Subject and leadfield (`:60`) | breadcrumb + inspector `LEADFIELD` block |
| `pages/optimizer-ex` — Ex-search: Electrode / ROI / Current (`ExForm.tsx:192,221,241`) | **Optimize ▸ Ex-search** — `TARGET` + `OBJECTIVE` |
| `pages/optimizer-ex` — mEx-search: + mTI configuration (`MExForm.tsx:230`) | **Optimize ▸ mEx-search** — `mTI`, collapsed |
| `pages/optimizer-ex` — Results tab (`ResultsPanel.tsx:81-131`) | **Results ▸ Optimizations** |
| `optimizer-ex/roi/RoiPicker.tsx` (271 lines) | **deleted** — `pages/_shared/roi/RoiPicker.tsx` is the one picker |
| `optimizer-ex/PlanPanel.tsx` (133 lines) | **deleted** — one Plan block |
| `pages/analyzer` — Subject and simulation (`:353`) | **Analyze** — `INPUT` + breadcrumb; Mode radio → Scope segment |
| `pages/analyzer` — Analysis configuration (`:429`) | **Analyze** — `INPUT` + `TARGET` |
| `analyzer/SphereRows.tsx` · `_shared/roi/RoiPicker.tsx` | **Analyze ▸ TARGET**, unchanged components |
| `analyzer/ResultsPanel.tsx:115` | **Analyze** — inspector `LAST RESULT` + link to Results |
| `pages/panels/nifti-group-average` (all 3 cards) | **Analyze ▸ Group ▸ Average / difference** |
| `pages/panels/cluster-permutation` (Subjects/Analysis/Advanced) | **Analyze ▸ Group ▸ Cluster permutation** |
| `pages/panels/nilearn-visuals` (Pairs/Output/Parameters) | **Analyze ▸ Figures** |
| `pages/viewer` — Source (`:635`) / Field & overlays (`:678`) | **View** — 40 px source bar |
| `pages/viewer` — Electrode overlay (`:703`) | **View** — `+ Add layer ▾ ▸ Electrodes` (same tools job) |
| `pages/viewer` — Layers (`:751`) | **View** — Tetravox layer panel |
| `pages/viewer` — Freeview command card (`:515`) | **deleted**; `⋯ ▸ Open externally ▸ Freeview` |
| `pages/viewer` — Gmsh card (`:597`) | `⋯ ▸ Open externally ▸ Gmsh` |
| `pages/viewer` — X server callout (`:510`) | tooltip on the disabled `⋯` items |
| `pages/results` — Subject select card (`:531-546`) | breadcrumb |
| `pages/results` — tabs Simulations / Flex / Ex / Analyses (`:558-570`) | **Results** — one list with a `kind` filter segment; detail in the inspector |
| `pages/results` — Group tab (`:571`, `GroupPanel` `:483-511`) | **Results** — `kind: group`, same list |
| `results/index.tsx:465` PDF embed · `:248,303,370` Artifacts | **Results** — inspector artifact list + report viewer |
| `pages/jobs` — filters card (`:148`) | **Jobs** — 32 px toolbar |
| `pages/jobs` — All jobs / Groups tabs (`:141-190`, `GroupsView.tsx`) | **Jobs** — `⟨Flat│Grouped⟩` segment on one table |
| `jobs/JobDetailDrawer.tsx` (374 lines) | **Jobs** — inspector; its 3 AlertDialogs stay |
| `pages/system` — CPU / Memory / Disk / Running jobs / DooD / Processes (`:119-...`) | **Settings ▸ System** |
| `pages/settings` — Project / Appearance / Telemetry / Advanced / About the server (`:150,178,187,233,272`) | **Settings** — same, as flush sections |
| `pages/settings` — Feature panels (`:209`) | **Settings ▸ Optional tools** (toggles modes, not nav items) |
| `pages/help` — Docs / About / Cite / Acknowledgments / Contact (`help/index.tsx:14-20`) | **Help** — route kept, off the rail; reached by `?` and the palette |
| `pages/panels/quick-notes` (`:94`) | **Notes drawer**, `⌘⇧N` |
| `dev/Gallery.tsx` (661 lines) | dev builds, palette-only; **the design system's regression surface — keep it, extend it with the new section/row primitives** |

Nothing on that list is dropped. Fourteen page headers, eleven Cards, four Plan implementations,
three tab strips, two ROI pickers and one Freeview command line are.

---

## 13. Build order

Do it in this order; each step is independently shippable and each one is measurable against the
existing screenshot suite (`tests/e2e/artifacts/final-mock/`, `DESIGN.md:172-177`).

1. **Tokens + primitives** (`ui/tokens.css`, `base.css`, `ui/Layout.tsx`, `ui/Field.tsx`,
   `components.css`): §4's table, R1's `.field` grid, R2's `FormSection` without `Card`. Extend
   `dev/Gallery.tsx` first — it is the one place every primitive is rendered side by side, so the
   density change is verified before a page sees it. **No page file changes.** Expect the whole
   screenshot suite to shift; that is the point.
2. **Shell** (`app/Shell.tsx`, `NavRail.tsx`, `TopBar.tsx`, `shell.css`): 56 px rail, 40 px context
   bar with the subject combobox, resizable inspector, `⌘K` palette, `⌘\`. Delete the
   `max-width:1199px` branch (`shell.css:56-79`) and the 1099 stacking branch
   (`components.css:1371-1414`).
3. **Action bar** + Plan-block split (R6) as a shell slot, adopted by all six run screens at once so
   the pattern never exists in two forms.
4. **Merges, in this order**: Project ← Subject info; Optimize ← flex + ex + mEx; Analyze ← the
   three panels; Notes drawer ← quick notes. Each merge deletes a PageDef and a nav row.
5. **Jobs** — one table at three heights.
6. **View** — Tetravox host; Freeview/Gmsh demoted to `⋯` in the same commit, not later.

`DESIGN.md` §2 §3 §4 §5 §9 and `app/registry.ts`'s nav contract are rewritten in step 1–2's commit,
since `DESIGN.md:9-11` makes the spec binding on page agents; leaving it stale is how the two
inline-Plan panels happened.
