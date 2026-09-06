# TI-Toolbox v3 desktop — WORKFLOW-FIRST redesign

**Lens:** the app is organised around *the subject and the pipeline stage the researcher is in*.
A subject workbench with stage status and next actions, like a modern project tool (Linear/Notion)
crossed with a lab instrument panel. Optimise for "what do I do next" and for never losing track of
a subject's state.

Every claim about the current build cites `file:line`. Paths are relative to
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/` unless absolute.
Tetravox citations are relative to `/Users/idohaber/00_development/tetravox/`.

---

## 0. Diagnosis — why the current UI reads as a PyQt transcription

The maintainer's instinct is right, and it is visible in code, not just in feel. Nine specific
symptoms:

**0.1 The nav is the PyQt tab bar, rotated 90°, plus its extension list.**
`tit/gui/main.py:196-201` registers six tabs (Pre-processing, Optimizer, Simulator, Analyzer, NIfTI
Viewer, System Monitor). `DESIGN.md:174-190` binds thirteen nav items in six groups, and
`desktop/src/renderer/pages/settings/index.tsx:17-23` adds six more as a top-level `PANELS` group.
`desktop/src/renderer/app/NavRail.tsx:7-14` names those groups Workspace / Pipeline / Explore /
System / Panels / Dev. So *Nilearn visuals* and *Quick notes* are siblings of *Simulator* in the
primary navigation. `subjects-light.png` shows 16 rail entries; `panel-source-light.png` shows 19
once every panel is enabled. The rail is a settings list, not a navigation.

**0.2 The subject is a passive label, and every screen re-invents picking one.**
`desktop/src/renderer/app/TopBar.tsx:48` renders `sub-ernie` as read-only text. There is no way to
change subject from the chrome. Consequently six screens each build their own picker:
`simulator/index.tsx:126-141`, `optimizer-flex/index.tsx:226-250`, `analyzer/AnalyzerPage.tsx:368`,
`viewer/index.tsx:640`, `results/index.tsx:532`, `preprocess/index.tsx:481`, plus
`panels/source/index.tsx`. Three different widgets are used for the same concept — a `DataTable`
(`subjects/index.tsx:99-107`), a `SubjectPicker` (`ui/SubjectPicker.tsx`), and a plain `Select`. The
single most frequent act in the workflow ("work on ernie now") is the one act the shell does not
support.

**0.3 One decision is split across two nav items; the split is not the user's.**
`DESIGN.md:179-180` gives *Optimizer · Flex-search* and *Optimizer · Ex/mEx-search* separate rail
rows and separate shortcuts. The legacy GUI had a single **Optimizer** tab
(`tit/gui/main.py:197`). The researcher decides "optimize placement for this ROI"; *how* it searches
(differential evolution vs exhaustive over a leadfield) is a method parameter, not a destination.
The two-row split also produces the two longest labels in the rail, which is why they wrap onto two
lines at 220 px (`subjects-light.png`, rail rows 4 and 5).

**0.4 The Plan lives in three different places.**
`DESIGN.md:24-28` makes the Plan panel the second signature element. But
`optimizer-flex/index.tsx:212` and `simulator/index.tsx:123` pass it as `PageLayout.contextPanel`;
`analyzer/AnalyzerPage.tsx:295-342` wraps `PlanSummary` in its own ad-hoc `Card`; and
`panel-nifti-group-average-light.png` shows a "Plan" card at the *bottom of the content column*.
Three placements, one component. And in its idle state it is a 320 px column of nothing —
`analyzer-cortical-light.png` gives a third of the window to the sentence "Complete the subject,
simulation, and target above to see the plan."

**0.5 Four nested boxes for one form field.**
`components.css:1380` caps the content column at 960 px and `:1385` gives the panel 320 px. Inside
that column each section is a `Card` (`ui/Layout.tsx:85-100`) on `--bg`, inside the page, inside the
shell. `simulator-light.png` shows the result: four white cards floating on grey, each with its own
1 px border and header rule, and the "Global parameters" grid at ~640 px usable width with two
columns of controls and a large dead zone on the right. The page needs three scroll-screens for
what is one instrument panel.

**0.6 Progressive disclosure exists and is used once.**
`ui/Layout.tsx:137-167` implements `FormSection` with an `advanced` disclosure. Only
`optimizer-flex/index.tsx:252-273` uses it. `simulator`, `analyzer`, `preprocess` and `viewer`
render every parameter flat. `preprocess/index.tsx:481-691` is five sections, all open, all the
time.

**0.7 The Viewer is a command-line builder wearing a form.**
`viewer/index.tsx:506` states the purpose as "Launch Freeview or Gmsh". `viewer-light.png` shows the
right column rendering a literal `freeview -v /mnt/example/...:colormap=heat:opacity=0.7` string
(`viewer/index.tsx:514-595`) beside a Gmsh launcher (`:596-631`), both greyed out because
`tit/server/routes/viewers.py:56` requires an X server. The user's mental model is "look at my
result"; the screen's model is "assemble argv".

**0.8 Jobs exist twice and neither is readable.**
The rail is 36 px (`shell.css:193-199`) and packs each job into a chip. In `simulator-light.png`
eight running jobs render as six truncated chips ending mid-word ("repor…"). The full Jobs page
(`jobs/index.tsx:140-186`) then re-renders the same data with a three-select filter card above it,
so the filters occupy 120 px to filter two rows (`jobs-light.png`).

**0.9 Chrome eats the top of every screen and says nothing.**
`ui/Layout.tsx:169-190` renders a 24 px title plus a purpose sentence on every page. The title
duplicates the nav label the user just clicked (`Subjects` → "Subjects"), and the purpose sentence
is read once, ever. That is ~72 px of permanent vertical loss on a window whose minimum height is
680 px (`shell.css:6`).

**One thing the current build gets right and must be protected:** the token system
(`DESIGN.md:34-64`, `ui/tokens.css`) is genuinely good — cool-biased neutrals, semantic colour kept
separate from accent, `--field` reserved for field semantics, tabular numerals everywhere. This
proposal changes **no colour value**. It changes structure and density.

---

## 1. Conventions borrowed, and why

| Product | Convention borrowed | Why it applies here |
|---|---|---|
| **Linear** | A short, stable sidebar (≤10 rows) plus a **command palette as the real navigator**; the active *object* is a switcher in the chrome, not a label. | The rail cannot hold 19 rows and stay scannable. `cmdk` is already a dependency and is currently used only inside `ui/Combobox.tsx:2`. Making ⌘K the reachability mechanism is what lets the rail shrink without losing anything. Subjects become palette entries, which fixes 0.2 in one move. |
| **VS Code** | The **bottom Panel**: always present, tabbed, drag-resizable, one keystroke (⌘J), holding the things you *monitor* rather than *navigate to* (terminal, problems, output). | The jobs rail is already trying to be this (`DESIGN.md:17-23`) but is a fixed 36/280 px with no tabs (`shell.css:193,217`). Giving it tabs absorbs *Jobs*, *System* and *Quick notes* — three nav rows deleted — and makes the 36 px chip soup readable. |
| **Blender — Properties editor** | Parameter categories as collapsible groups in a single narrow column, with **advanced groups collapsed by default and no card chrome between them**; the header of a group carries the state. | This is the exact shape of a TI run configuration: 20–40 parameters in 5–7 semantic groups where 6 matter and 34 have correct defaults. Flush sections with a rule (not cards on a ground) removes the nesting in 0.5. |
| **3D Slicer / Freeview** | Module parameters left at ~320 px, **viewport takes all remaining space and gets no page header**; the viewport is the document. | The Viewer must become a workspace, not a form. It also happens to be Tetravox's own contract: `docs/ARCHITECTURE.md:2655-2658` specifies left = layer panel, centre = view grid, right = coordinate bar / measurements / info panel. Adopting Slicer's convention here means embedding Tetravox costs *no* layout negotiation. |
| **Postman** | The commit control (**Send**) is pinned and never scrolls; the request/response split is the page. | Decides 0.4: the Plan becomes a pinned action bar, not a column. The commit control is where the eye already goes at the end of a form — bottom-right — and it is visible from the first field, so "how much will this cost" is answerable before scrolling. |

---

## 2. Information architecture

### 2.1 Nav rail — exact items, groups, order

```
┌─ 216 px ─────────────────┐
│ ▣ TI-Toolbox             │   brand, 32 px row
│                          │
│ ⌕  Search…        ⌘K     │   palette trigger, 28 px, --surface-2 well
│                          │
│ ▦  Overview       ⌘1     │   LayoutGrid
│                          │
│ SUBJECT ───────────────  │   group label, 12/.06em, --ink-2
│ ⟨ ernie          ▾ ⌘P ⟩  │   SUBJECT SWITCHER — 32 px, a real button
│ ◈  Workbench      ⌘2     │   CircuitBoard
│ ⬒  Prepare        ⌘3     │   Boxes
│ ⚡  Simulate       ⌘4     │   Zap
│ ⌖  Optimize       ⌘5     │   Crosshair
│ ⚗  Analyze        ⌘6     │   FlaskConical
│ ⊞  Results        ⌘7     │   FolderTree
│ ◉  Viewer         ⌘8     │   Eye
│                          │
│ PROJECT ───────────────  │
│ ⚇  Group study    ⌘9     │   UsersRound
│                          │
│ ───────── (spacer) ───── │
│ ▤  Jobs           ⌘J     │   pinned to bottom; toggles the Panel
│ ⚙  Settings       ⌘,     │
│ ?  Help                  │
└──────────────────────────┘
```

Ten navigable rows plus a switcher plus three pinned utilities. Down from 13 + 6 panels + Gallery.

**Rules that make this stick:**

1. **The `SUBJECT` group is scoped by the switcher directly above it.** Everything in it is
   "…for ernie". This is the entire justification for deleting six in-page subject pickers (0.2).
2. **`shortcut` badges leave the rail.** `NavRail.tsx:42-46` renders a `Kbd` on every row; that is
   19 pieces of chrome for information needed twice. Shortcuts move to the palette and the `?`
   sheet, where they are actually learned. The rail keeps `aria-keyshortcuts`.
3. **`navGroup` values change to `root | subject | project | utility`.** `registry.ts:77-88` already
   groups by first appearance in `order`, so this is a `PageDef` field edit, not an architecture
   change. `registry.ts:29`'s `import.meta.glob` discovery is preserved exactly.
4. **`useEnabledPages` (`registry.ts:62-69`) survives but stops driving the nav.** Panels are no
   longer pages, so `isPanelPageEnabled` (`registry.ts:46-48`) and the whole
   `panels/_shared.ts:22-40` localStorage mirror are deleted. The `settings.panels` server field is
   repurposed to gate *capabilities* (§7.3), which have no nav presence.

### 2.2 Batch is additive, not a picker

`Prepare` and `Simulate` are genuinely multi-subject (`preprocess/index.tsx:481`,
`simulator/index.tsx:139`). They keep that, but not with a full picker. The subject bar gains a
`+ 2 more ▾` chip; opening it lists the project's subjects with presence chips and checkboxes. Zero
clicks for the 95% single-subject case; one click for the batch case. `ui/SubjectPicker.tsx` is
reused verbatim inside that popover — nothing is rewritten.

---

## 3. Shell layout — pixel widths

```
┌──────────────┬──────────────────────────────────────────────────────────────────────┐
│ Nav rail     │ Top bar                                                        44 px │
│ 216 px       │  ▣ Dataset 000 ▾   │   ⌕ Search or run a command   ⌘K   │  ● live   │
│              │                    │                                    │  ▤ 3      │
│ (56 px icon  ├──────────────────────────────────────────────────────────────────────┤
│  rail below  │ Subject bar (subject-scoped screens only)                      36 px │
│  1280 px)    │  ⟨ernie ▾⟩ +2 more │ ●Prepare › ●Target › ◐Simulate › ○Analyze │ 3 ▸│
│              ├──────────────────────────────────────────────────────────────────────┤
│              │                                                                      │
│              │ Page body — NO page header.                                          │
│              │ One pane, or config (≤ 880 px) + result/preview (flex).              │
│              │ Scrolls here and nowhere else.                                       │
│              │                                                                      │
│              ├──────────────────────────────────────────────────────────────────────┤
│              │ Action bar (run screens only)                                  56 px │
│              │  1 job · 8 CPU · 12 GB · writes ernie/Thalamus  [Plan ▾] [▷ Run]     │
│              ├──────────────────────────────────────────────────────────────────────┤
│              │ Panel — collapsed 28 px / expanded 240–520 px drag, default 280  ⌘J  │
│              │  [Jobs 3] [Console] [Host] [Notes]                                   │
└──────────────┴──────────────────────────────────────────────────────────────────────┘
```

Deltas from today, each with its reason:

| Element | Today | Proposed | Why |
|---|---|---|---|
| Nav rail | 220 px (`shell.css:14`) | **216 px**, icon rail **56 px** below **1280 px** | 216/56 are on the 8-grid; the collapse breakpoint moves from 1199 (`shell.css:56`) to 1280 because the subject bar needs room and 1280 is the screenshot width. |
| Top bar | 48 px (`shell.css:116`) | **44 px** | Four px back; the row holds a project *switcher* (not a label — `TopBar.tsx:44-47`), the ⌘K field, and status. The `tit 3.0.0-mock · api v0` version string (`TopBar.tsx:55-57`) moves into Settings → About; it is diagnostic, not ambient. |
| Page header | ~72 px, every page (`ui/Layout.tsx:169-190`) | **deleted** | Replaced by the subject bar, which carries state instead of restating the nav label. `PageHeader` survives only on Settings and Help, at 20/600 with no purpose line. |
| Content pane | 960 px cap (`components.css:1380`) | **config pane ≤ 880 px; tables, viewer and results panes uncapped** | Prose needs a measure; a 12-column job table does not. |
| Context panel | 320 px sticky (`components.css:1385`) | **deleted as a layout slot** | See §5. |
| Action bar | — | **56 px, pinned** | New. |
| Jobs rail | 36 / 280 px (`shell.css:193,217`) | **28 px collapsed / 240–520 px drag, persisted; four tabs** | `ui/Layout.tsx:210-270` already ships `ResizablePanels`; the drag handle logic is reused. |

**Breakpoints.** 1024 (min, `shell.css:7`): rail 56 px, config single column, panel collapsed.
1280: rail 216 px, config 2 columns. 1600: config 3 columns where a section declares it; Workbench
stage cards go 4-across; Viewer right panel appears. Nothing stacks the config under a panel any
more, because there is no panel — the 1099 px reflow hack in `components.css:1392-1405` disappears.

---

## 4. The six core screens + the Workbench

### 4.1 Overview (replaces `pages/subjects` + `panels/subject-info`)

Project-level. The only screen with no subject scope.

```
 ┌ Overview ─────────────────────────────────────────────────────────────────────────┐
 │ Dataset 000 · /mnt/000 · 3 subjects                     [+ Add subject]  [Export ⤓]│
 │                                                                                    │
 │ ┌ COVERAGE ────────────────────────────────────────────────────────────────────┐   │
 │ │  raw 3/3 ███  recon 1/3 █░░  m2m 3/3 ███  dwi 1/3 █░░  sims 4  analyses 2    │   │
 │ └──────────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                    │
 │ Subject     Data                        Leadfield   Sims  Analyses  Last activity  │
 │ ────────────────────────────────────────────────────────────────────────────────   │
 │ ernie    ●raw ●recon ●m2m ●dwi ○ct     GSN-185        3      2      12 min ago  ›  │
 │ 101      ●raw ○recon ●m2m ○dwi ●ct     —              1      0      2 days ago  ›  │
 │ MNI152   ○raw ○recon ●m2m ○dwi ○ct     —              0      0      —           ›  │
 │                                                                                    │
 │ ┌ NEEDS ATTENTION ─────────────────────────────────────────────────────────────┐   │
 │ │ ⚠ 101 — no FreeSurfer recon-all. Blocks cortical ROIs.      [Run recon-all]  │   │
 │ │ ⚠ ernie — flex run "NewRun" has no simulation.              [Simulate it]    │   │
 │ └──────────────────────────────────────────────────────────────────────────────┘   │
 └────────────────────────────────────────────────────────────────────────────────────┘
```

- Row click **switches the global subject and lands on that subject's Workbench**. Today it only
  sets a store value (`subjects/index.tsx:103-107`) and the user must then find a nav row.
- The `dwi` / `ct` / `Leadfield` columns come from `panels/subject-info` — `tit/catalog.py:1070-1086`
  (`subject_info_matrix`) and `tit/catalog.py:181-213` (`subject_detail`) already return all of it,
  and `/api/catalog/subject-info` (`contracts/openapi.v1.yaml:836`) stays as the CSV export behind
  `[Export ⤓]`. The panel is deleted; nothing is lost.
- The right-hand "Simulations" context card (`subjects/index.tsx:90`, `subjects-light.png`) is
  deleted — its content is the Workbench's Simulate stage card, where it belongs.
- **NEEDS ATTENTION is the workflow-first payload at project scope.** Derived client-side from
  `/api/catalog/subjects/{id}` (`openapi.v1.yaml:307`) + `/api/catalog/flex-runs` (`:595`) +
  `/api/catalog/analyses` (`:669`). No new endpoint.

### 4.2 Workbench — the signature screen (new)

The answer to "what do I do next for ernie". Reached by ⌘2 and by clicking any Overview row.

```
 ⟨ernie ▾⟩  ●Prepare › ●Target › ◐Simulate › ○Analyze              3 jobs for ernie ▸
 ┌──────────────────────────────────────────────────┬─────────────────────────────────┐
 │ ┌ ① PREPARE                       complete  ●┐   │ ACTIVITY                        │
 │ │ raw ✓  recon-all ✓  m2m ✓  dwi ✓  ct —    │   │ ◐ sim  Thalamus       running   │
 │ │ charm 2026-08-14 · 847k nodes             │   │   ██████░░░ 62% · 4m12s  [Stop] │
 │ │                        [Open Prepare ›]   │   │ ● flex NewRun       succeeded   │
 │ └───────────────────────────────────────────┘   │   12 min ago         [Results ›]│
 │ ┌ ② TARGET                       2 results ●┐   │ ● pre  charm        succeeded   │
 │ │ ROIs 3 · Leadfield GSN-185 ✓ (2.0 GB)     │   │   2 h ago                       │
 │ │ flex 1 · ex 1 · montages 4                │   │                                 │
 │ │        [Optimize ›]  [Manage montages]    │   ├─────────────────────────────────┤
 │ └───────────────────────────────────────────┘   │ NEXT                            │
 │ ┌ ③ SIMULATE                    3 sims    ◐┐   │ ▸ Analyze "Thalamus" — it has   │
 │ │ Thalamus  TI mTI    L_Insula  TI          │   │   fields but no ROI statistics. │
 │ │ docs_example  mTI                         │   │   [Analyze Thalamus]            │
 │ │              [Simulate ›]  [View ◉]       │   │                                 │
 │ └───────────────────────────────────────────┘   │ ▸ ernie has no CT. Optional —   │
 │ ┌ ④ ANALYZE                     2 analyses ○┐   │   only needed for iEEG.         │
 │ │ Thalamus/Sphere_10  L_Insula/DK40         │   │                                 │
 │ │ reports 1                                 │   ├─────────────────────────────────┤
 │ │      [Analyze ›]  [Open report]           │   │ NOTES                    [edit] │
 │ └───────────────────────────────────────────┘   │ ernie: check gel thickness      │
 └──────────────────────────────────────────────────┴─────────────────────────────────┘
```

**Stage model — four stages, derived entirely from existing catalog calls.**

| Stage | Fields | Source |
|---|---|---|
| ① Prepare | `has_raw`, `has_freesurfer`, `has_m2m`, `has_dwi`, `has_ct` | `tit/catalog.py:203-213` |
| ② Target | `eeg_nets`, `has_leadfields`, ROIs, flex runs, ex runs, montages | `catalog.py:208-210`, `:575`, `:696`, `:759`, `:351` |
| ③ Simulate | simulations with `has_ti` / `has_mti` | `catalog.py:71-99` |
| ④ Analyze | analyses per simulation, reports | `catalog.py:831`, `:893` |

State chips: `●` complete (`--success`), `◐` running (`--accent`, pulsing), `◑` partial
(`--warning`), `○` not started (`--ink-3`). Every stage card **always renders**, including empty
ones — a missing stage that is invisible is the failure mode this lens exists to prevent.

Card is 168 px tall, 2-across below 1600 px, 4-across above. Stage cards are one of only three
places `Card` chrome survives (§6.2).

### 4.3 Simulate (replaces `pages/simulator`)

```
 ⟨ernie ▾⟩ +2 more  ●Prepare › ●Target › ◐Simulate › ○Analyze        3 jobs for ernie ▸
 ┌ config ≤880 ────────────────────────────────────┬─── queue (flex) ──────────────────┐
 │ SOURCE                                          │ 2 SIMULATIONS QUEUED               │
 │ ( Montage )( Flex result )( Free-hand )         │                                    │
 │                                                 │ ernie · E2E_Test_Montage           │
 │ Net  [GSN-HydroCel-185 ▾]  [Uni-polar ▾]  [+New]│   E1→E2, E3→E4                     │
 │ ┌───────────────────────────────────────────┐   │   [1.0]mA  [1.0]mA          [✕]    │
 │ │ ☐ F3_F4          E24→E124            ✎ 🗑 │   │                                    │
 │ │ ☐ Thalamus_target E37→E87            ✎ 🗑 │   │ 101 · F3_F4                        │
 │ │ ☑ E2E_Test_Montage E1→E2, E3→E4      ✎ 🗑 │   │   E24→E124                         │
 │ └───────────────────────────────────────────┘   │   [2.0]mA  [2.0]mA          [✕]    │
 │                                                 │                                    │
 │ ── ELECTRODES ─────────────────────────────     │ Applies to all: 8×8 mm ellipse,    │
 │ Shape (Ellipse)(Rect)   Size [8]×[8] mm         │ gel 4 mm, isotropic, TI_max        │
 │ Gel   [4] mm                                    │                                    │
 │                                                 │                                    │
 │ ── OUTPUT ─────────────────────────────────     │                                    │
 │ Fields  ☑TI_max ☐TI_normal ☐hf_peak ☐hf_SAR ⓘ  │                                    │
 │                                                 │                                    │
 │ ▸ Conductivity  ·  isotropic, SimNIBS defaults  │                                    │
 │ ▸ Advanced                                      │                                    │
 └─────────────────────────────────────────────────┴────────────────────────────────────┘
 │ 2 jobs · 8 CPU · 16 GB · writes ernie/E2E_Test_Montage, 101/F3_F4  [Plan ▾] [▷ Run] │
```

Changes from `simulator-light.png`:

- **Montage source tabs → a segmented control** (`simulator/index.tsx:146-154`). Same three sources,
  6 px of chrome instead of a card header plus a tab strip plus a card body.
- **"Selected jobs" table → a right-hand queue pane** (`simulator/index.tsx:159-192`). It is the
  *result* of the left pane's picking, so it belongs beside it, not stacked 400 px below it. The
  per-pair current editors (`simulator/index.tsx:40-62`) move with it unchanged.
- **"Global parameters" card → three flush sections** (`simulator/index.tsx:194-244`), with
  Conductivity demoted to a collapsed disclosure that states its current value in the header
  ("isotropic, SimNIBS defaults"). `ConductivityDialog` (`simulator/ConductivityDialog.tsx`) opens
  from inside it, unchanged.
- The "Applies to all" line in the queue pane is a derived read-back of the left pane's parameters —
  this is the rule from §6.4: a parameter you set once and apply N times must be visible where the
  N things are listed.

### 4.4 Optimize (merges `pages/optimizer-flex` + `pages/optimizer-ex`)

One screen. Method is a segmented control, not a destination.

```
 ⟨ernie ▾⟩  ●Prepare › ●Target › ◐Simulate › ○Analyze                3 jobs for ernie ▸
 ┌ config ≤880 ────────────────────────────────────┬─── preview ───────────────────────┐
 │ METHOD ( Flex )( Exhaustive )( mTI exhaustive ) │ ┌ TARGET ─────────────────────┐   │
 │                                                 │ │  [ Tetravox mini-view ]     │   │
 │ ── TARGET ─────────────────────────────────     │ │  T1 + ROI sphere, 3 planes  │   │
 │ Region ( Cortical )( Subcortical )( Sphere )    │ │  10, −20, 15 · r 8 mm       │   │
 │ Space  ( Subject )( MNI )                       │ └─────────────────────────────┘   │
 │   x [ 10]  y [−20]  z [ 15]  r [  8] mm   [🗑]  │                                    │
 │   [+ Add sphere]                        [◉ Pick]│ ┌ SEARCH COST ────────────────┐   │
 │                                                 │ │ Population 13 × 500 gen      │   │
 │ ── GOAL ───────────────────────────────────     │ │ ≈ 6 500 FEM solves           │   │
 │ [ mean — maximize field in target ROI      ▾ ]  │ │ ≈ 40–90 min on 8 CPU         │   │
 │ Post-proc [ max_TI ▾ ]                          │ └─────────────────────────────┘   │
 │                                                 │                                    │
 │ ── ELECTRODES ─────────────────────────────     │ ┌ RECENT RUNS ────────────────┐   │
 │ Pairs [2]  Radius [10] mm  Min distance [25] mm │ │ ● NewRun     mean 0.412  ›  │   │
 │                                                 │ │ ● Sphere_L   mean 0.388  ›  │   │
 │ ▸ Search settings · DE, pop 13, 500 gen         │ │             [Simulate this] │   │
 │ ▸ Focality              (shown only for goal=focality)                            │ │
 │ ▸ Anisotropy · isotropic                        │ └─────────────────────────────┘   │
 │ ▸ Post-run simulations · off                    │                                    │
 └─────────────────────────────────────────────────┴────────────────────────────────────┘
 │ 1 job · 8 CPU · 12 GB · writes ernie/flex-search/NewRun         [Plan ▾] [▷ Run]    │
```

For **Exhaustive** / **mTI exhaustive** the same skeleton holds; the differences appear as:

- a **precondition strip** directly under the segmented control, replacing the "Subject and
  leadfield" card (`optimizer-ex/index.tsx:60`, `optimizer-ex/LeadfieldPanel.tsx`):
  `Leadfield · GSN-HydroCel-185 ✓ 2.0 GB` or, when absent,
  `⚠ No leadfield for GSN-HydroCel-185 — required. [Generate (≈40 min)]`. A hard prerequisite is a
  gate, not a form field.
- ELECTRODES becomes the four bucket comboboxes (`optimizer-ex/ElectrodeBuckets.tsx`), unchanged.
- SEARCH COST shows `185 electrodes · 7 splits · 119 140 combinations` — the numbers
  `optimizer-ex/PlanPanel.tsx` computes today, promoted out of the plan column into a permanent
  preview so the cost is visible *while* you widen a bucket, not only after.

The `Results` tab currently inside optimizer-ex (`optimizer-ex/ResultsPanel.tsx`) becomes the
RECENT RUNS card, and its `[Simulate this]` action deep-links to Simulate with the Flex-result
source pre-selected. That handoff currently requires the user to independently discover
`simulator/FlexTab.tsx`.

Seven stacked cards (`optimizer-flex/index.tsx:226,252,300,312,314,315,318`) become one segmented
control, three open sections and four disclosures.

### 4.5 Analyze (replaces `pages/analyzer`)

```
 ⟨ernie ▾⟩  ●Prepare › ●Target › ●Simulate › ◐Analyze                3 jobs for ernie ▸
 ┌ config ≤880 ────────────────────────────────────┬─── results ───────────────────────┐
 │ SIMULATION [ Thalamus ▾ ]     Scope (One)(Group)│ Thalamus / Sphere_10               │
 │            TI_max TI_normal · mesh + voxel      │ ─────────────────────────────────  │
 │                                                 │ Field     Max     Mean    Focality │
 │ ── SPACE ──────────────────────────────────     │ TI_max    0.981   0.412   0.31     │
 │ ( Mesh )( Voxel )      Tissue [ Gray matter ▾ ] │ TI_normal 0.774   0.301   0.28     │
 │ Field  [ Auto (TI_max / mTI_max) ▾ ]            │                                    │
 │                                                 │ [ histogram, uPlot ]               │
 │ ── TARGET ─────────────────────────────────     │                                    │
 │ ( Cortical )( Subcortical )( Spherical )        │ ROI 1 240 nodes · 2.1 cm³          │
 │ Atlas   [ DK40 ▾ ]                              │                                    │
 │ Regions [ superiorfrontal ✕ ] [ precentral ✕ ]  │ [Open report] [View in Viewer ◉]   │
 │         Multiple regions union into one target. │ [Export to fsaverage]              │
 │                                                 │                                    │
 │ ▸ Output · CSV + PDF report, named Sphere_10    │ PREVIOUS                           │
 │ ▸ Advanced                                      │ ● Thalamus/DK40_L    12 min ago ›  │
 └─────────────────────────────────────────────────┴────────────────────────────────────┘
 │ 1 job · 4 CPU · 8 GB · writes ernie/Thalamus/Analyses/Sphere_10  [Plan ▾] [▷ Run]   │
```

- `Mode: Single / Group` (`analyzer/AnalyzerPage.tsx:356-366`) is relabelled **Scope: One / Group**
  and moved to the top row beside the simulation; `Group` swaps the top row for a subject-multiselect
  and everything below is unchanged.
- The subject `Select` (`analyzer/AnalyzerPage.tsx:368-404`) is **deleted** — the subject bar owns it.
- `analyzer/ResultsPanel.tsx` moves from below the form into the right pane, where it is visible
  next to the configuration that produced it.
- **`[Export to fsaverage]` lands here**, taking the "Map fields to fsaverage" half of the Source
  panel (`panels/source/index.tsx`, right column of `panel-source-light.png`). That half is a
  *post-simulation* operation and its current home next to "Build forward solution" is a workflow
  error: `panel-source-light.png` shows the two side by side as if they were one stage.

### 4.6 Viewer — Tetravox embedded (replaces `pages/viewer`)

```
 ⟨ernie ▾⟩  ●Prepare › ●Target › ●Simulate › ●Analyze                3 jobs for ernie ▸
 ┌ 280 ─────────────┬──────────────── viewport (flex, --viewport) ────────┬─ 300 ─────┐
 │ LOAD FROM ernie  │  ┌──────────────┬──────────────┐                    │ COORDS    │
 │ ○ T1             │  │              │              │                    │ [World ▾] │
 │ ○ Tissues + LUT  │  │   Axial      │   Coronal    │   L ── R           │ x  10.0   │
 │ ○ Head mesh      │  │              │              │                    │ y −20.0   │
 │ ▸ Simulation     │  │              │              │                    │ z  15.0   │
 │   Thalamus       │  ├──────────────┼──────────────┤   RAD              │ MNI(aff)  │
 │   ☑ TI_max       │  │              │              │                    │  12 −18 9 │
 │   ☐ TI_normal    │  │  Sagittal    │     3D       │   ▣ 20 mm          │           │
 │ ▸ Analysis mask  │  │              │              │                    │ MEASURE   │
 │ ▸ Electrodes     │  └──────────────┴──────────────┘                    │ M1 24.1mm │
 │                  │                                                     │           │
 │ LAYERS           │                                                     │ INFO      │
 │ ═ TI_max    👁 ▤ │   ← Tetravox owns everything inside this frame:     │ Cursor    │
 │   heat  p95–99.9 │     panes, chrome, orientation letters, scale bar,   │ TI_max    │
 │   ▬▬▬▬▬●▬ 0.70   │     cube, colour bars, picking, measure mode.        │  0.412    │
 │ ═ T1        👁 ▤ │                                                     │ tissue    │
 │   grayscale      │                                                     │  GM       │
 │ ─────────────────│                                                     │ Mouse     │
 │ [Save scene]     │                                                     │  …        │
 │ [Open externally▾]│                                                    │           │
 └──────────────────┴─────────────────────────────────────────────────────┴───────────┘
```

**Embedding decision: a `WebContentsView` layered over the viewport rect, loading
`tetravox://app/index.html`. Not an iframe.**

Reason, and it is not preference: Tetravox's contract requires (a) `tetravox` registered via
`registerSchemesAsPrivileged` with `standard, secure, supportFetchAPI, stream, corsEnabled`
(`docs/ARCHITECTURE.md:971-974`), (b) `win.loadURL('tetravox://app/index.html')` and **never**
`loadFile` (`:981`), (c) one module Worker *per dataset* fetching `tetravox://file/…` under that
origin (`:993-998`), and (d) a document CSP carrying `connect-src 'self' tetravox:` because
`tetravox://file` is a different host from `tetravox://app` (`:1063`). An `<iframe>` inside the
TI-Toolbox renderer puts those workers under the TI-Toolbox origin and breaks all four. A
`WebContentsView` gives Tetravox its own origin, CSP and worker pool with **zero changes to
Tetravox's source**, which is what makes this maintainable across `tetravox` releases.

**Path bridge.** The server is in the container and returns container paths (`/mnt/000/…`);
`tetravox://file/` reads host absolute paths from a gesture-minted allow-list
(`docs/ARCHITECTURE.md:1055-1062`). Decision: **translate container → host in the Electron main
process and call `allowPath()` on the host path**, because the app already knows both halves of the
mapping — Settings displays "Container path `/mnt/example`" and "Host path
`/Users/example/projects/example`" (`settings-light.png`, `pages/settings/index.tsx:150`). Only when
the server is remote and no host path exists does it fall back to `LoadSource {kind:'url'}` against
`/api/files/artifact` (`openapi.v1.yaml:1299`) with the session token. Never `kind:'bytes'` — that
would put an 847k-node mesh on the renderer thread that `ARCHITECTURE.md:993` explicitly forbids
from seeing raw file bytes.

**What survives from the current Viewer, and what dies:**

- `GET /api/view/{kind}` (`openapi.v1.yaml:1184`) and `tit/viewspec.py` **survive and get more
  important** — the resolved `ViewSpec` becomes the *LOAD FROM* catalog (which T1, which fields,
  which atlas + LUT, which analysis mask), mapped onto `Engine.addDataset` + `Engine.addLayer`
  (`docs/ARCHITECTURE.md:874-877`). All six audit fixes documented at `tit/viewspec.py:11-52` (the
  HF glob, the missing `labeling_LUT.txt`, the `_LUT.txt` sidecar rule, the MNI path fallback, the
  dropped absolute thresholds, the MNI-space atlas) are retained, because they are about *finding
  the right files*, which is still the server's job.
- **`to_freeview_args` and the "Freeview command" card die as UI** (`viewer/index.tsx:514-595`,
  visible as a raw argv block in `viewer-light.png`). The argv builder stays in `tit/viewspec.py`
  and is reachable only through `[Open externally ▾] → Freeview` / `→ Gmsh` / `→ Copy command`.
  `tit/server/routes/viewers.py:181,203` and its `_require_x11` guard (`:56`) are unchanged; the
  X-server warning callout moves inside that menu instead of occupying the top of the page.
- **`FormSection "Layers"` (`viewer/index.tsx:751`) dies.** Per-layer colormap, opacity, threshold
  and percentile are Tetravox's own left panel and histogram widget
  (`docs/ARCHITECTURE.md:2655-2657`, `:2769-2771`). Re-implementing them in React would violate
  Tetravox's own rule — "Everything the UI can do must be reachable from the `Engine` API alone. No
  logic in React" (`:2654`) — and would give two answers to "what is the window".
- **The electrode-overlay job (`viewer/index.tsx:86-94`) survives** as a `▸ Electrodes` entry in
  LOAD FROM: absent → "Create electrode overlay" (a background job), present → a loadable layer.
- **`[Save scene]`** writes `*.tetravox.json` (`ARCHITECTURE.md:663`) into the run directory, so a
  figure setup is reproducible and shareable — a capability the Freeview launcher never had.
- Theme: the viewport uses a new `--viewport` token, dark in *both* themes, because
  `ARCHITECTURE.md:2740-2742` requires it ("a light viewport changes what a greyscale T1 and a heat
  overlay look like"). `Engine.setTheme` (`:915`) is called in the same tick as our `data-theme`
  flip so the chrome matches.

### 4.7 Jobs — the Panel, not a page

`Jobs` in the rail toggles the Panel and focuses its Jobs tab. There is no Jobs *route*.

```
 collapsed (28 px, always visible):
 ├─────────────────────────────────────────────────────────────────────────────────┤
 │ ▤ 3 running   ◐ sim ernie ██████░░ 62%   ◐ pre 101 ▂▃▄  ◐ report 101 ▂▃▄    ⌃  │
 ├─────────────────────────────────────────────────────────────────────────────────┤

 expanded (⌘J, 240–520 drag, default 280):
 ├─────────────────────────────────────────────────────────────────────────────────┤
 │ [Jobs 3] [Console] [Host] [Notes]           ernie ▾  running ▾   ⌕        ⌄  ✕  │
 ├──────────────────────────────────┬──────────────────────────────────────────────┤
 │ ◐ sim      ernie  Thalamus       │ 14:22:01 INFO  Meshing head model…           │
 │   ██████░░ 62% · 4m12s · 78% CPU │ 14:22:44 INFO  FEM solve 1/2                 │
 │ ⏸ report   101    waiting #4     │ 14:24:10 WARN  PETSc iteration limit         │
 │ ● flex     ernie  NewRun    12m  │ 14:24:12 INFO  FEM solve 2/2                 │
 │ ✕ analyzer 101    failed     2h  │                                              │
 │                                  │ [☑ follow] [level ▾] [Reveal log] [Stop]     │
 └──────────────────────────────────┴──────────────────────────────────────────────┘
```

- **Master–detail replaces tabs-over-a-filter-card.** `jobs/index.tsx:149-163` puts three full
  `Field`+`Select` controls in a `Card` above the table; in `jobs-light.png` that is 120 px of
  chrome filtering two rows. They become two inline dropdowns and a search box in the tab strip.
- `jobs/JobDetailDrawer.tsx` (374 lines: console, log, artifacts, cancel, rerun, force) becomes the
  detail pane. It is no longer a `Drawer` over the page — you can watch a log *while editing the
  next run*, which is the actual behaviour during a multi-hour charm.
- `jobs/GroupsView.tsx` (the subject→stage tree, `jobs/index.tsx:180-184`) becomes a `⌄` grouping
  toggle on the list, not a peer tab.
- **`Host` tab absorbs `pages/system` entirely** (`system/index.tsx`): CPU/Memory/Disk sparklines,
  Processes table, DooD siblings note. It is monitoring, which is what a Panel is for, and it
  frees a rail row. Its "Running jobs" card (`system-light.png`) is deleted as a duplicate of the
  Jobs tab.
- **`Notes` tab absorbs `panels/quick-notes`** (`catalog.py:1049-1068`,
  `openapi.v1.yaml:805`). A running notepad is never a destination; it must be one keystroke from
  wherever you are.
- The collapsed rail shows at most 4 traces plus `+n more`; today it renders every job and truncates
  mid-word at eight (`simulator-light.png` bottom edge).

---

## 5. Forms: compaction rules

### 5.1 The decision — sticky action bar, and the Plan becomes a popover

**The 320 px Plan column is deleted. `PageLayout.contextPanel` (`ui/Layout.tsx:197-207`,
`components.css:1383-1391`) is removed as a layout slot.** The Plan's *content* is preserved
entirely, in two places:

1. **Always visible, in the action bar** — the one-line cost summary:
   `2 jobs · 8 CPU · 16 GB · writes ernie/E2E_Test_Montage, 101/F3_F4`. This is the 80% of the Plan
   people read, and it is now readable from the first field instead of after a scroll.
2. **One click away, in a `[Plan ▾]` popover** — the full `PlanSummary` (`ui/PlanSummary.tsx`):
   per-job resolved output directories, `exists` / `will_overwrite` markers, lock conflicts ("will
   queue behind #12, charm sub-101"), warnings, and the overwrite checkbox. Opens *above* the bar,
   440 px wide, and auto-opens once when a conflict or wait first appears.

Why this and not the panel:

- The panel costs 320 px + 16 px gap on every run screen, permanently, for content that is empty
  until the form is complete — `analyzer-cortical-light.png` gives a third of the window to
  "Complete the subject, simulation, and target above to see the plan."
- It is already inconsistently placed (§0.4): `contextPanel` in flex/simulator/preprocess, an ad-hoc
  `Card` in analyzer (`analyzer/AnalyzerPage.tsx:295-342`), and *inside the content column* in the
  group panels (`panel-nifti-group-average-light.png`). One placement, enforced by the shell, ends
  that.
- The Run button currently sits inside the panel and scrolls with it. In `optimizer-ex-light.png`
  the button is at y≈488 while the form continues past y≈840 — you commit from a control that is
  nowhere near what you last edited.
- `DESIGN.md:24-28` names the Plan panel as a signature. What made it a signature is *telling the
  truth before you click Run* — that survives verbatim. The 320 px column was the packaging, not the
  idea.

The action bar also carries the error count (`⚠ 2 problems`, clicking jumps to the first) and, once
submitted, briefly becomes a confirmation strip before returning to idle.

### 5.2 Progressive disclosure — five rules

1. **Seven-control rule.** A screen shows at most seven primary controls before its first
   disclosure. Everything else starts collapsed.
2. **A disclosure header states its current value.** `▸ Conductivity · isotropic, SimNIBS defaults`,
   `▸ Search settings · DE, pop 13, 500 gen`, `▸ Anisotropy · isotropic`. A collapsed group is never
   opaque.
3. **Non-default values force the group open and badge it.** `▾ Advanced · 2 changed`, with the
   changed fields marked. This is the rule that makes hiding parameters *safe for science*: you can
   never have a parameter silently doing something out of view. It is the one addition
   `ui/Layout.tsx:137-167` needs — it currently starts closed unconditionally (`:149`).
4. **Mutually-exclusive branches swap, never coexist.** `viewer/index.tsx:514-631` renders the
   Freeview card and the Gmsh card simultaneously though you use exactly one; ROI type in
   `analyzer/AnalyzerPage.tsx:479` already does this correctly and is the model.
5. **Anything derivable is derived.** Output directory names, job counts, combination counts and
   memory estimates are read-back, never inputs.

Applied: `optimizer-flex` goes from 7 open cards to 3 open sections + 4 disclosures;
`preprocess` from 5 open `FormSection`s (`preprocess/index.tsx:481,541,603,674,691`) to 2 open + 3
disclosures; `simulator` from 4 cards to a segmented control + 3 sections + 2 disclosures; `viewer`
from 5 sections to zero (it is a workspace).

### 5.3 Defaults

- Every field ships a default that is correct for a first run. A field with no sensible default is
  `required` and marked; there are at most **two** per screen.
- **Last-used per subject**, persisted in `localStorage` keyed `tit:v3:<screen>:<subject>`. Re-runs
  are the common case and re-typing 30 parameters is the current cost.
- A `[Reset to defaults]` ghost button in each disclosure header, active only when that group differs.

### 5.4 Inline validation

- Validate **on blur**, then **on every change after the field's first error** (never on first
  keystroke).
- The Run button **stays enabled** — `DESIGN.md:126-127` is right and is kept. Pressing it with
  errors focuses the first one and does not submit.
- Errors surface in three coordinated places: the field (red border + message), the action bar
  (`⚠ 2 problems`), and the Plan popover (a list with jump-to-field links). Server validation from
  `POST /api/validate/{kind}` (`openapi.v1.yaml:888`) maps onto fields through
  `forms/serverErrors.ts`, already built.
- Preflight problems that are **not** field errors — an existing output, a lock conflict, a missing
  leadfield — are warnings in the Plan popover and never block the button. Only the overwrite
  `AlertDialog` (`optimizer-flex/index.tsx:347-358`) blocks, and only at commit.

---

## 6. Visual system

### 6.1 Density tokens (add to `ui/tokens.css`)

```css
/* density — “compact” is the default; Settings offers “comfortable” */
--control-h:        28px;   /* was 32 (tokens.css:92) */
--control-h-sm:     24px;
--control-h-lg:     32px;   /* primary + action-bar buttons only */
--row-h:            28px;   /* was 36 (tokens.css:91) */
--row-h-comfortable:36px;

--pane-pad:         12px;
--section-gap:      16px;
--field-gap:         8px;
--label-gap:         4px;

--nav-w:           216px;
--nav-w-collapsed:  56px;
--topbar-h:         44px;
--subjectbar-h:     36px;
--actionbar-h:      56px;
--panel-h-collapsed:28px;
--panel-h-default: 280px;
--config-max:      880px;

--viewport:     #0B0E12;    /* SAME in light and dark — Tetravox contract, ARCHITECTURE.md:2740 */
```

`[data-density="comfortable"]` on `<html>` swaps `--control-h: 32px` and `--row-h: 36px`; nothing
else changes, because every component reads the tokens.

### 6.2 Type: promote "dense" to the default

`DESIGN.md:62-63` already defines a `13/18 dense` step and makes `14/20` the base. Invert that for
chrome: **13/18 is the default for labels, controls, table cells and nav; 14/20 survives for prose**
(help text, empty-state copy, callouts, report bodies). This is the VS Code / Linear settings
density and is right for a screen holding 40 parameters. Page titles drop 24/30 → **20/26** where a
title survives at all. Everything else in `DESIGN.md:59-64` is unchanged, fonts included.

### 6.3 Kill card-in-card

A `Card` (`ui/Layout.tsx:85-100`) survives in exactly three places:

1. **Workbench stage cards** — genuinely discrete objects, each with its own state and actions.
2. **Result summaries** — a run, an analysis, a report; something you could open on its own.
3. **The Plan popover.**

Everywhere else a form section is **flush**: a 12 px uppercase eyebrow (`--ink-2`, `.06em`), a 1 px
`--line` rule, then the grid. No border, no fill, no nested surface. The config pane sits directly
on `--surface`; `--bg` becomes the ground *between* top-level regions only. This alone removes three
levels of nesting from `simulator-light.png`.

### 6.4 Grids and tables

- Form grid: `repeat(auto-fit, minmax(240px, 1fr))`, max 3 columns, inside `--config-max` (880 px).
  A field may declare `span: 2` (region multiselects, paths).
- Tables: `--row-h` 28 px, sticky header on `--surface-2`, right-aligned tabular numerals,
  `overflow-x` on the container only. Zebra striping stays off; the 1 px row rule is enough at 28 px.
- A parameter set applied to N queued items is echoed as one read-back line beside the list (§4.3),
  never repeated per row.

### 6.5 Empty, loading, error, disconnected — decided per surface

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Table | 5 skeleton rows at real `--row-h`, real header | One line + one primary action, **left-aligned at 24 px inset** inside the table body | Inline `Callout kind="danger"` in the body, server message verbatim in mono, `[Retry]` |
| Stage card (Workbench) | Skeleton chips, card frame real | Card renders anyway: name, `○` chip, the action button. **Never absent.** | `⚠` chip on the card + reason in the card body |
| Right/result pane | Skeleton block | One sentence naming what would appear and the action producing it | Inline `Callout` |
| Viewport | Tetravox's own per-dataset load card, phase + % + elapsed + Cancel (`ARCHITECTURE.md:2655-2658`) | "Nothing loaded — pick a layer on the left." | Tetravox `error` event → `Callout` over the left panel |
| Whole page | Never blank; the shell renders instantly | Centered `EmptyState` (the **only** centering allowed) | `PageErrorBoundary` (already exists) |
| Disconnected | — | — | Subject bar turns into a full-width `--warning` strip; the action bar disables with "Server disconnected"; the Panel keeps the last known job list, greyed |

Toasts (`sonner`) are for **job submission and completion only**. A failed data load is never a
toast — it is an inline error in the surface that failed. Today `viewer/index.tsx` uses
`notify.error("Could not launch Freeview.")` for a load-path failure with no inline trace.

### 6.6 Motion and theme

Unchanged from `DESIGN.md:71-72` and `DESIGN.md:159-164`: 150 ms ease-out, 1.6 s liveness pulse,
`prefers-reduced-motion` kills all of it, tokens defined on `:root` / `@media (prefers-color-scheme:
dark)` guarded by `:root:not([data-theme="light"])` / `:root[data-theme="dark"]`. Two additions:
`--viewport` is theme-invariant (§6.1), and `Engine.setTheme` (`ARCHITECTURE.md:915`) is called in
the same tick as the `data-theme` stamp so Tetravox's own chrome follows.

---

## 7. Keyboard, command palette, migration

### 7.1 Command palette — ⌘K

`cmdk` is a dependency (`package.json`) used only by `ui/Combobox.tsx:2`. It becomes the app's
navigator. Four result groups, in this order:

1. **Subjects** — every subject id, with presence chips. Selecting one **switches the global
   subject** and stays on the current screen. This is the single highest-frequency action and it
   currently has no UI at all.
2. **Go to** — the ten nav destinations, plus the ones with no rail row: `Host monitor`,
   `Notes`, `Gallery` (dev builds only, gated by `VITE_INCLUDE_GALLERY` as today).
3. **Run** — `Run simulation`, `Run flex-search for ernie`, `Generate leadfield`,
   `Open Thalamus in Viewer`, `Open externally in Freeview`, contextual to the current screen.
4. **Jobs** — running jobs by name: `Stop sim ernie`, `Open log for #4`, `Rerun analyzer 101`.

Fuzzy across all four; recents first when the query is empty.

### 7.2 Shortcut map

| Key | Action |
|---|---|
| `⌘K` | Command palette |
| `⌘P` | Subject switcher (a scoped palette — subject switching is frequent enough for its own key) |
| `⌘1`…`⌘9` | The rail, in rail order (`keyboard.ts:43-49` unchanged in mechanism) |
| `⌘J` | Toggle Panel · `⌘⇧J` focus its Console tab |
| `⌘↵` | Run, from anywhere in a run screen |
| `⌘,` | Settings |
| `?` | Shortcut sheet |
| `Esc` | Close dialog / popover / palette; cancels an in-flight Tetravox measurement |
| `⌥←` `⌥→` | Previous / next stage for the current subject |

In the Viewer, unmodified keys forward to Tetravox's own grammar (`ARCHITECTURE.md:2464`, §7.5);
`⌘`-modified keys stay with the shell. `isTypingTarget` (`keyboard.ts:5-8`) already guards text
entry and is extended to guard the focused `WebContentsView`.

### 7.3 Migration map — every page and section

| Today | New home | Note |
|---|---|---|
| `pages/subjects` table (`subjects/index.tsx:99-107`) | **Overview** table | Row click now switches subject *and* navigates to Workbench |
| `pages/subjects` Simulations context card (`:13-56, :90`) | **Workbench** stage ③ | |
| `pages/preprocess` Subjects (`preprocess/index.tsx:481`) | Subject bar + `+n more` | |
| `pages/preprocess` Processing steps (`:541-600`) | **Prepare** — open section | 5 checkboxes unchanged |
| `pages/preprocess` DWI (Docker) (`:603-672`), `QsiPrepDialog`, `QsiReconDialog` | **Prepare** — `▸ DWI (optional)` | Dialogs unchanged |
| `pages/preprocess` Existing outputs (`:674`) | **Plan popover** | It is preflight, not configuration |
| `pages/preprocess` Run settings (`:691`) | **Prepare** — `▸ Advanced` | |
| `pages/simulator` Subjects (`simulator/index.tsx:126-141`) | Subject bar + `+n more` | |
| `pages/simulator` Montage source tabs (`:143-156`) incl. `MontageManager`, `FlexTab`, `FreehandTab` | **Simulate** — segmented SOURCE | Components unchanged |
| `pages/simulator` Selected jobs (`:159-192`) | **Simulate** — right queue pane | |
| `pages/simulator` Global parameters (`:194-244`), `ConductivityDialog` | **Simulate** — ELECTRODES + OUTPUT + `▸ Conductivity` | |
| `pages/optimizer-flex` Subjects (`optimizer-flex/index.tsx:226`) | Subject bar | |
| `pages/optimizer-flex` Basic parameters (`:252`) | **Optimize** — GOAL + `▸ Anisotropy` | |
| `pages/optimizer-flex` ROI definition (`:300`), `_shared/roi/RoiPicker` | **Optimize** — TARGET | Shared with Analyze |
| `pages/optimizer-flex` Focality options (`:312`) | **Optimize** — `▸ Focality`, shown only when goal is focality | |
| `pages/optimizer-flex` `ElectrodeParams` (`:314`) | **Optimize** — ELECTRODES | |
| `pages/optimizer-flex` `HyperParams` (`:315`) | **Optimize** — `▸ Search settings` | |
| `pages/optimizer-flex` Automatic simulations (`:318`) | **Optimize** — `▸ Post-run simulations` | |
| `pages/optimizer-ex` Subject and leadfield (`optimizer-ex/index.tsx:60`), `LeadfieldPanel` | **Optimize** — precondition strip under the Exhaustive segment | |
| `pages/optimizer-ex` `ExForm` / `MExForm` / `ElectrodeBuckets` | **Optimize** — Exhaustive / mTI exhaustive segments | |
| `pages/optimizer-ex` `ResultsPanel` | **Optimize** — RECENT RUNS, with `[Simulate this]` | |
| `pages/analyzer` Mode single/group (`analyzer/AnalyzerPage.tsx:356`) | **Analyze** — Scope segmented, top row | |
| `pages/analyzer` Subject select (`:368`) | **deleted** — subject bar | |
| `pages/analyzer` Analysis configuration (`:429-500`), `SphereRows` | **Analyze** — SPACE + TARGET | |
| `pages/analyzer` `ResultsPanel` | **Analyze** — right results pane | |
| `pages/viewer` Source / Field & overlays (`viewer/index.tsx:635,678`) | **Viewer** — LOAD FROM list | Fed by `/api/view/{kind}` |
| `pages/viewer` Layers (`:751`) | **Tetravox layer panel** | React re-implementation deleted |
| `pages/viewer` Electrode overlay (`:519-…`) | **Viewer** — `▸ Electrodes` in LOAD FROM | Job unchanged |
| `pages/viewer` Freeview command (`:514-595`) + Gmsh (`:596-631`) | **Viewer** — `[Open externally ▾]` menu | `viewers.py:181,203` unchanged; X11 callout moves inside the menu |
| `pages/results` Subject select (`results/index.tsx:532`) | **deleted** — subject bar | |
| `pages/results` Simulations / Flex / Ex-mEx / Analyses tabs (`:557-564`) | **Results** — one list with a Kind filter, master–detail | Same four sources, one layout |
| `pages/results` Group tab (`:565`, `:491-503`) | **Group study** | |
| `pages/jobs` All jobs + filters (`jobs/index.tsx:149-176`) | **Panel → Jobs** | Filters inline in the tab strip |
| `pages/jobs` Groups (`:180-184`), `GroupsView` | **Panel → Jobs**, `⌄` grouping toggle | |
| `pages/jobs` `JobDetailDrawer` | **Panel → Jobs**, right detail pane | No longer a modal drawer |
| `pages/system` (all of `system/index.tsx`) | **Panel → Host** | Its "Running jobs" card deleted as a duplicate |
| `pages/settings` Project (`settings/index.tsx:150`) | **Settings → Project** | Host/container paths feed the Tetravox path bridge |
| `pages/settings` Appearance (`:178`) | **Settings → Appearance** | `+ Density: compact / comfortable` |
| `pages/settings` Telemetry (`:187`) | unchanged | |
| `pages/settings` Feature panels (`:209`, `PANEL_INFO :17-23`) | **deleted** | Panels are no longer nav items; replaced by **Modules** (EEG forward, DWI/QSIPrep, Tetravox path bridge) with dependency notes. Kills the "toggling one requires a reload" behaviour and `panels/_shared.ts:22-40`'s localStorage mirror. |
| `pages/settings` Advanced (`:233`) / About the server (`:272`) | **Settings → Advanced / About** | Absorbs the version string from `TopBar.tsx:55-57` and `help/AboutTab.tsx` |
| `pages/help` 5 tabs (`help/index.tsx:14-20`) | **Help** — one scrolling page, 4 sections | `AboutTab` merges into Settings → About |
| `panels/source` — Build forward | **Prepare** — `▸ EEG forward (optional)` | |
| `panels/source` — Map fields to fsaverage | **Analyze** — `[Export to fsaverage]` on a result | Corrects a workflow-stage error |
| `panels/nifti-group-average` | **Group study** — Average mode | |
| `panels/cluster-permutation` | **Group study** — Permutation mode | |
| `panels/nilearn-visuals` | **Group study** — Visuals mode, and `[Figure ▾]` on Results | |
| `panels/quick-notes` | **Panel → Notes** | `catalog.py:1049-1068` unchanged |
| `panels/subject-info` | **Overview** table columns + `[Export ⤓]` | `catalog.py:1070-1086` unchanged |
| `pages/dev` Gallery | **⌘K only**, dev builds | Rail row deleted |
| `ui/Layout.tsx` `PageHeader` | Settings + Help only | |
| `ui/Layout.tsx` `PageLayout.contextPanel` | **removed** | Replaced by the action bar + per-screen right panes |
| `ui/Layout.tsx` `ResizablePanels` | **Panel** drag handle, **Jobs** master–detail | Now load-bearing |
| `ui/PlanSummary.tsx` | **Plan popover** | Component unchanged |
| `ui/SubjectPicker.tsx` | Subject bar `+n more` popover, Group study | Six page-level uses collapse to two |
| `app/subjectContext.ts` | **Promoted**: the switcher writes it, seven screens read it, ⌘P and ⌘K set it | Today only `TopBar.tsx:48` reads it, as a label |

**Nothing in the migration table is dropped.** Every section has a destination; four are deleted only
because they are exact duplicates (`system` Running jobs, `subjects` Simulations card, `help` About,
`settings` Feature panels).

### 7.4 Server changes required

**None are required to ship the IA.** Every surface above is backed by an endpoint that exists:
`/api/catalog/subjects` and `/{id}` (`openapi.v1.yaml:183,307`), `subject-info` (`:836`),
`leadfields` (`:574`), `flex-runs` (`:595`), `ex-runs` (`:616`), `analyses` (`:669`), `reports`
(`:722`), `group` (`:792`), `notes` (`:805`), `plan/{kind}` (`:916`), `jobs` + `ws/jobs`
(`:960,:1172`), `view/{kind}` (`:1184`), `viewers/*` (`:1233,:1256`), `files/artifact` (`:1299`),
`system` + `ws/system` (`:240,:298`).

Two optional additions, both convenience-only:

1. `GET /api/catalog/subjects/{id}/stages` — the four-stage rollup the Workbench composes today from
   five calls. Purely a round-trip optimisation.
2. `GET /api/project/paths` — the container↔host prefix pair for the Tetravox bridge. The desktop
   app already holds both (`main/userConfig.ts`, `settings-light.png`), so this only matters for
   browser mode, where the bridge falls back to `kind:'url'` anyway.

---

## 8. What this buys, measured against the screenshots

- Nav rows: **19 → 10** + a switcher (`panel-source-light.png` vs §2.1).
- Subject pickers: **7 → 1** (`simulator:126`, `optimizer-flex:226`, `analyzer:368`, `viewer:640`,
  `results:532`, `preprocess:481`, `panels/source` → the subject bar).
- Vertical chrome above the first control: **~120 px → 80 px** (48 top + 72 header → 44 top + 36
  subject bar), and the 36 px that remain now carry the subject's pipeline state.
- Horizontal working width at 1280: **~700 px → ~1000 px** for a config pane (960 cap + 320 panel +
  gaps → 880 cap with the right pane earning its width).
- `optimizer-flex` first screen: **2 controls visible** today (`optimizer-flex-spherical-light.png`
  shows Subjects + goal before the fold) → **9**, with the run cost visible from the start.
- Two of the three screens a new user must understand before running anything (Viewer's argv
  builder, the Panels group) stop existing.
