# TI-Toolbox v3 — Proposal D: the viewer-centric workbench

**Lens:** the embedded Tetravox viewer is the application. Simulate / Optimise / Analyse are
task panels over one persistent scene, in the tradition of 3D Slicer, Freeview and Blender.
Freeview and Gmsh survive only as "open externally" escape hatches.

**Status:** design proposal. Nothing in the repository was modified. Every claim below cites
`file:line`. Paths are absolute where they leave the worktree
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui` (abbreviated `WT/`)
and `/Users/idohaber/00_development/tetravox` (abbreviated `TVX/`).

---

## Part 0 — The diagnosis, with receipts

The maintainer's brief says the v3 UI reads as a copy-paste of the PyQt approach. That is
literally true, and it is checkable.

### 0.1 The nav is the PyQt tab bar

The legacy PyQt window adds exactly six tabs, in this order:

```
WT/tit/gui/main.py:196   self.tab_widget.addTab(self.pre_process_tab,     "Pre-processing")
WT/tit/gui/main.py:197   self.tab_widget.addTab(self.optimizer_tab,       "Optimizer")
WT/tit/gui/main.py:198   self.tab_widget.addTab(self.simulator_tab,       "Simulator")
WT/tit/gui/main.py:199   self.tab_widget.addTab(self.analyzer_tab,        "Analyzer")
WT/tit/gui/main.py:200   self.tab_widget.addTab(self.nifti_viewer_tab,    "NIfTI Viewer")
WT/tit/gui/main.py:201   self.tab_widget.addTab(self.system_monitor_tab,  "System Monitor")
```

and then appends every enabled extension as a further tab
(`WT/tit/gui/main.py:318`, `self.tab_widget.addTab(extension_widget, name)`), the extensions being
the eight files in `WT/tit/gui/extensions/` (`cbp.py`, `electrode_placement.py`,
`nifti_group_average.py`, `nilearn_viz.py`, `quick_notes.py`, `source.py`,
`subject_info_viewer.py`, `visual_exporter.py`).

The v3 nav is the same list with the Optimizer split in two and the extensions renamed "Panels"
(`WT/desktop/DESIGN.md:172-191`, the binding navigation table; `WT/desktop/src/renderer/app/NavRail.tsx:7-14`
for the group labels). Counting from the PageDefs in `WT/desktop/src/renderer/pages/*/index.tsx`:
Subjects (`subjects/index.tsx:115-123`), Pre-processing (`preprocess/index.tsx:738-746`),
Simulator (`simulator/index.tsx:253-262`), Optimizer·Flex-search (`optimizer-flex/index.tsx:363-371`),
Optimizer·Ex/mEx-search (`optimizer-ex/index.tsx:139-147`), Analyzer (`analyzer/index.tsx:6-15`),
Viewer (`viewer/index.tsx:780-788`), Results (`results/index.tsx:575-583`),
Jobs (`jobs/index.tsx:199-207`), System (`system/index.tsx:235-242`),
Settings (`settings/index.tsx:304-312`), Help (`help/index.tsx:27-34`), plus six panel pages
(`WT/desktop/src/renderer/pages/panels/_shared.ts:24-31` enumerates the `PanelId` union) and a dev
Gallery (`dev/index.tsx:6-10`). **Nineteen destinations in a 220 px sidebar** —
`WT/desktop/src/renderer/app/shell.css:14` — visible in every screenshot, e.g.
`WT/desktop/tests/e2e/artifacts/final-mock/simulator-light.png`, where the rail runs from
"Subjects" to "Gallery" without a scroll and consumes the full window height.

### 0.2 The shape "one tab = one full-page form" survives, and it is wasteful

`WT/desktop/src/renderer/ui/components.css:1377-1382` caps the content column at `max-width: 960px`;
`:1383-1391` pins a 320 px sticky context panel beside it. On a 1280 px window that is
220 (nav) + 960 (content) + 320 (panel) = 1500 px of demand for 1280 px of supply, so in practice
the content column never reaches 960 and the right column is the only thing that grows. Where a page
has no panel content the right half of the window is empty: see
`final-mock/subjects-light.png` (a three-row table, then ~560 px of nothing),
`final-mock/jobs-light.png` (two rows, then ~450 px of nothing) and
`final-mock/panel-subject-info-light.png` (three rows, then ~500 px of nothing).

### 0.3 The screens overlap each other

* **Subjects** (`subjects/index.tsx`) and the **Subject info** panel
  (`pages/panels/subject-info/`) render the *same table*. Compare
  `final-mock/subjects-light.png` (columns: Subject, Data chips, Simulations) with
  `final-mock/panel-subject-info-light.png` (Subject, Data chips, Leadfields, Simulations). The
  panel is the superset. Two nav items, one table.
* **Results** (`results/index.tsx:557-565`: tabs Simulations / Flex runs / Ex-search·mEx-search runs
  / Analyses / Group) and **Optimizer·Ex**'s third tab
  (`optimizer-ex/index.tsx:129`, `{ id: "results", label: "Results", … }`) both browse ex-search
  output.
* **Viewer** and **Results** both ask "which subject / which simulation / which field", with
  independent pickers (`viewer/index.tsx:272`, `results/index.tsx:514`).

### 0.4 The Plan panel is not applied consistently

`WT/desktop/DESIGN.md:25-29` calls the right-hand Plan panel the app's second signature. It is a
`contextPanel` prop on `PageLayout` (`WT/desktop/src/renderer/ui/Layout.tsx:199-204`) on Simulator
(`simulator/index.tsx:123`), Pre-processing, Flex, Ex and Analyzer — but the Nilearn panel renders a
`Plan` *card inline at the bottom of the content column* instead
(`final-mock/panel-nilearn-visuals-light.png`, the card headed "Plan" below "Add at least one
subject-simulation pair"; `pages/panels/PlanSummary.tsx` is the shared inline variant). Two
different homes for the same idea.

Worse, on Analyzer and Flex the panel is mostly empty while the form is being filled — see
`final-mock/analyzer-cortical-light.png` ("Complete the subject, simulation, and target above to
see the plan.") and `final-mock/optimizer-flex-spherical-light.png` (three grey skeleton bars).
A 320 px column, permanently reserved, that is blank for most of the interaction.

### 0.5 The Viewer is a command builder, not a viewer

`WT/desktop/src/renderer/pages/viewer/index.tsx:1-6` says so in its own docstring: "Viewer screen —
the Freeview launcher … plus a Gmsh mesh launcher." The page's product is the string shown in
`final-mock/viewer-light.png`:
`freeview -v /mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz:colormap=grayscale:…`.
It is gated on an X server (`WT/tit/server/routes/viewers.py:56-61`, `_require_x11` → HTTP 409
"No X11 display available"; probe at `WT/tit/server/routes/capabilities.py:44`), which the
screenshot shows failing with a permanent amber callout. Users configure layers — colormap,
opacity, threshold, electrode overlay — in a form and then see the result *in a different
application*.

### 0.6 The subject is nominally global and actually not

`WT/desktop/src/renderer/app/subjectContext.ts:1-15` defines a zustand store for "the subject a page
most recently worked with". Seven pages read or write it (analyzer, subjects, viewer, results,
optimizer-flex, optimizer-ex, simulator), each while *also* rendering its own picker; and
**Pre-processing and all six Panels never touch it at all** — `preprocess/index.tsx` renders its own
`SubjectPicker` (visible in `final-mock/preprocess-light.png`), and no `panels/*` file imports the
store. So the top bar's `sub-ernie` chip (`WT/desktop/src/renderer/app/TopBar.tsx:35,52`) is a
read-out of a value half the app ignores.

### 0.7 cmdk is installed and unused

`WT/desktop/package.json` lists `"cmdk": "1.1.1"`, and the only import is inside the Combobox
primitive (`WT/desktop/src/renderer/ui/Combobox.tsx:2`). There is no command palette; navigation is
`⌘1…⌘9` plus mouse (`WT/desktop/src/renderer/app/keyboard.ts:37-52`). Nineteen destinations, nine
digits.

**Conclusion.** The information architecture is the *implementation's* architecture (one PyQt tab →
one FastAPI runner → one React page), not the researcher's. The fix is not to restyle the pages. It
is to stop having pages.

---

## Part 1 — Conventions borrowed, and why

Four products, one convention each, taken deliberately.

### 1.1 3D Slicer — "the view grid never unmounts; modules are panels over one scene"

Slicer has ~150 modules and one persistent 2×2 view layout. Choosing a module swaps a single left
panel; it never navigates away from the data. **Borrowed:** the Tetravox canvas mounts once at app
start and is never unmounted by task switching; Simulate / Optimise / Analyse are panels beside it.
**Why:** every one of our tasks is *about* a volume or a mesh — an ROI is a place in a brain, a
montage is four points on a scalp, a result is a field over tissue. A form that describes those
things in numbers while the picture lives in another screen (§0.5) is the illogic the brief names.
**Rejected from Slicer:** its module panel is a stack of collapsible sections all expanded at once,
with no notion of "done". We use a step model instead (§4.1).

### 1.2 VS Code — "Activity Bar + one Side Bar + one Panel + Status Bar", and ⌘K as the real nav

VS Code has hundreds of commands and a 48 px icon rail with five items, because the palette is the
navigation surface and the bottom Panel multiplexes Problems / Output / Terminal / Ports into one
region instead of four screens. **Borrowed:** exactly that skeleton — a 56 px activity bar with six
items, one swappable task panel, one bottom Dock with tabs, one status bar; plus ⌘K as a first-class
citizen. **Why:** it is the only convention that lets nineteen destinations (§0.1) collapse without
losing any of them — the ones that leave the rail become palette entries, dock tabs and dialog tabs.
`cmdk` is already a dependency (§0.7).

### 1.3 Blender — the Properties editor's icon-tab column, and "the viewport is the app"

Blender's Properties editor puts ~12 categories in a one-icon-wide vertical strip; picking one
replaces the whole properties stack. Its N-panel and T-panel slide over the viewport rather than
shrinking it, and both are toggled by one key. **Borrowed:** (a) the task panel is *replaced*, never
appended to, by the activity choice; (b) at narrow widths the side columns become overlay sheets
over the canvas rather than squeezing it (§3.3); (c) `⌘B` / `⌘⌥B` toggle them, Blender-style.
**Why:** it protects a canvas floor (§3.3) on a 13" laptop, which a three-fixed-column layout cannot.

### 1.4 Linear — density, and no page-title blocks

Linear runs a 13 px base, ~28 px rows, one accent colour, and — critically — **no `<h1>` that
repeats the sidebar label**. Context lives in a slim breadcrumb bar with the primary action on it.
**Borrowed:** the density tokens in §6 and the deletion of `PageHeader` (§5.7). **Why:** today every
screen spends 66 px of vertical space restating its own nav item plus a sentence
(`WT/desktop/src/renderer/ui/Layout.tsx`'s `PageHeader`; see the "Simulator / Configure and run TI /
mTI simulations…" block in `final-mock/simulator-light.png`). Across a viewer-centric layout that is
a whole slice pane's worth of chrome, spent on text the user reads once.

### 1.5 (Secondary) Xcode / Instruments — one run bar owns "what am I running, on what"

**Borrowed:** the scheme/destination pattern becomes our Run bar's `project ▸ subject` pair (§3.2),
which is the *only* subject picker in the app — fixing §0.6.

**Explicitly not borrowed:** Postman's request/response split (our long jobs are not
request/response), and Figma's floating panels — Tetravox forbids floating overlays over the canvas
because pane overlays are `pointer-events: none` by contract
(`TVX/docs/ARCHITECTURE.md:3305-3312`, §13.3's argument against a floating palette). Our overlay
sheets therefore dock to an edge and are opaque.

---

## Part 2 — The information architecture

### 2.1 Nav structure — exact items, groups, order

The activity bar has **six** items in one group plus two bottom-anchored utilities. There are no nav
groups with labels; six items need no taxonomy.

| # | Activity | Icon (lucide) | Shortcut | Task panel contains |
|---|---|---|---|---|
| 1 | **Project** | `folder-tree` | ⌘1 | Subjects list · subject detail · Prepare (pre-processing) · Assets (leadfields, EEG forward) |
| 2 | **Simulate** | `zap` | ⌘2 | Montage source (Montage / Flex result / Free-hand) · currents · parameters |
| 3 | **Optimise** | `crosshair` | ⌘3 | Method (Flex / Ex / mEx) · ROI · electrodes · hyper-parameters |
| 4 | **Analyse** | `flask-conical` | ⌘4 | Scope (Single / Group) · space · field · ROI · group method |
| 5 | **Results** | `layout-list` | ⌘5 | Runs tree (simulations, flex, ex/mex, analyses, group, figures, reports) |
| 6 | **Jobs** | `list-checks` | ⌘6 | Queue, filters; focuses the Dock's Jobs tab |
| — | Settings | `settings` | ⌘, | modal dialog, bottom-anchored |
| — | Help | `circle-help` | `?` | modal sheet, bottom-anchored |

The activity bar is **icon-only at every width**, 56 px, with a tooltip carrying the title and the
shortcut, and a 2 px accent left bar on the active item. The current `PageDef.purpose` string
becomes that tooltip's second line and the palette entry's description — the text is kept, the
66 px header block is not (§5.7).

There is **no "Panels" group**. Nothing in this app is an optional top-level destination toggled in
Settings; the Feature-panels checkbox list (`settings/index.tsx:18-24`,
`final-mock/settings-light.png`) is deleted from the UI. The server's `settings.panels` field stays
in the contract (`WT/contracts/openapi.v1.yaml:1370`, `/api/settings`) and is ignored by the
renderer, so `WT/desktop/src/renderer/app/registry.ts:62-70`'s `useEnabledPages` panel-filtering
machinery goes away with it.

There is **no "Viewer" nav item**, because the viewer is always on screen.

### 2.2 Where everything moved — the complete migration table

Nothing is lost. Every existing page, tab and section maps to exactly one new home.

| Existing (file) | New home | Notes |
|---|---|---|
| `pages/subjects` — table (`subjects/index.tsx:115-123`) | **Project ▸ Subjects** (task panel) | Merged with Subject info (below) |
| `pages/subjects` — right "Simulations" card | **Inspector ▸ Subject** | Becomes the subject detail card; also drives the scene |
| `pages/panels/subject-info` (`panels/_shared.ts:29`) | **deleted, merged into Project ▸ Subjects** | Its extra columns (Leadfields, DWI, CT) and *Export selected* move onto the one Subjects table. `final-mock/panel-subject-info-light.png` **is** the target table |
| `pages/preprocess` — Subjects card | **Project ▸ Prepare**, multi-select from the same Subjects table | The page's own `SubjectPicker` is deleted (§0.6) |
| `pages/preprocess` — Processing steps | **Project ▸ Prepare ▸ Steps** | Checkbox list unchanged |
| `pages/preprocess` — DWI processing (Docker) | **Project ▸ Prepare ▸ Steps ▸ Advanced ▸ DWI** | Disclosure; gated on `capabilities.docker_socket` (`WT/tit/server/routes/capabilities.py:41`) |
| `pages/simulator` — Subjects card | **Run bar subject picker** (multi-select popover) | One picker for the app |
| `pages/simulator` — Montage / Flex-search / Free-hand tabs (`simulator/index.tsx:150-152`) | **Simulate ▸ step 1 "Montage"**, a 3-way segmented control | Free-hand becomes viewer-driven (§7.2) |
| `pages/simulator` — Selected jobs table | **Simulate ▸ step 2 "Runs"** | Table of subject × montage × currents |
| `pages/simulator` — Global parameters + `ConductivityDialog` | **Simulate ▸ step 3 "Parameters"** + its dialog | Unchanged dialog |
| `pages/simulator/PlanPanel.tsx` | **Simulate ▸ action bar plan strip** (§4.2) | Same data, no reserved column |
| `pages/optimizer-flex` (all) | **Optimise ▸ method = Flex** | |
| `pages/optimizer-flex/FocalityOptions.tsx` (non-ROI) | **Optimise ▸ step "Target" ▸ Avoid** | Second ROI set, second colour in the scene |
| `pages/optimizer-flex/HyperParams.tsx` | **Optimise ▸ step "Search" ▸ Advanced** | |
| `pages/optimizer-ex/ExForm.tsx`, `MExForm.tsx` (`optimizer-ex/index.tsx:104,117`) | **Optimise ▸ method = Ex / mEx** | The Ex/mEx tab pair becomes two entries in the same method selector as Flex |
| `pages/optimizer-ex/LeadfieldPanel.tsx` | **Project ▸ Assets ▸ Leadfields** | A leadfield is a per-subject derivative, not an optimiser setting; Optimise shows a presence chip and a "Generate…" link into Project |
| `pages/optimizer-ex/ElectrodeBuckets.tsx` | **Optimise ▸ step "Electrodes"**, with viewer picking (§7.2) | |
| `pages/optimizer-ex` — Results tab (`optimizer-ex/index.tsx:129`) | **Results ▸ Ex/mEx runs** | Duplicate removed (§0.3) |
| `pages/_shared/roi/RoiPicker.tsx` + `pages/optimizer-ex/roi/RoiPicker.tsx` | **one** ROI step component, viewer-bound (§7.1) | Two implementations collapse to one |
| `pages/analyzer` (Single/Group, mesh/voxel, cortical/subcortical/spherical) | **Analyse ▸ scope + space + target** | |
| `pages/analyzer/ResultsPanel.tsx` | **Results ▸ Analyses** | |
| `pages/viewer` — Source / Field & overlays / Layers cards | **dissolved.** Layers → **Inspector ▸ Layers**; source selection → **Results tree** | Choosing a result *is* loading it |
| `pages/viewer` — Freeview command card, `Open in Freeview`, `Open in Gmsh` | **Results ▸ row overflow menu ▸ "Open externally ▸ Freeview / Gmsh"** + Settings ▸ External tools | Kept, demoted; still `POST /api/viewers/{freeview,gmsh}` (`WT/contracts/openapi.v1.yaml:1233,1256`) |
| `pages/viewer` — Create electrode overlay (`tools` job, `WT/tit/server/routes/viewers.py:10-38`) | **Results ▸ simulation ▸ Export ▸ "Electrode positions (NIfTI)"** | No longer needed for *viewing* (§7.2); kept for exporting to other tools |
| `pages/results` — Simulations / Flex runs / Ex runs / Analyses / Group tabs (`results/index.tsx:557-565`) | **Results ▸ one tree**, five top-level nodes | Tabs → tree; selection loads into the scene |
| `pages/results` — report iframe | **Dock ▸ Report tab** (sandboxed iframe, `GET /api/files/report/{id}`) | Full width beneath the canvas |
| `pages/jobs` — All jobs / Groups tabs, filters, `JobDetailDrawer`, console | **Dock ▸ Jobs** and **Dock ▸ Console**; Activity 6 focuses them | The drawer becomes the Console tab's header |
| `pages/system` — CPU/Memory/Disk cards, Running jobs, Processes, DooD | **Dock ▸ System** | Live telemetry belongs with the terminal-shaped things |
| `pages/settings` — Project / Appearance / Telemetry | **Settings dialog** (⌘,) tabs Project · Appearance · Telemetry | |
| `pages/settings` — Feature panels list | **deleted** (§2.1) | |
| `pages/settings` — image tag override | **Settings ▸ Project ▸ Advanced** | |
| `pages/help` — Docs / About / Cite / Acknowledgments / Contact (`help/index.tsx:15-19`) | **Help sheet** (`?`), same five tabs | |
| `pages/panels/source` — "Build forward solution" | **Project ▸ Assets ▸ EEG forward** | It is a per-subject derivative, like a leadfield |
| `pages/panels/source` — "Map fields to fsaverage" | **Analyse ▸ space = fsaverage** | It is a projection of simulation fields, and it feeds surface group stats |
| `pages/panels/cluster-permutation` | **Analyse ▸ scope = Group ▸ method = Cluster permutation** | |
| `pages/panels/nifti-group-average` | **Analyse ▸ scope = Group ▸ method = NIfTI average** | |
| `pages/panels/nilearn-visuals` | **Results ▸ Figures ▸ New figure (Nilearn)** | It renders existing results; it is an export |
| `pages/panels/quick-notes` | **Dock ▸ Notes** | Always available, project-scoped, `GET/PUT /api/catalog/notes` |
| `pages/panels/PlanSummary.tsx` | **deleted** — one plan component (§4.2) | |
| `pages/dev` Gallery (`dev/index.tsx:6-10`) | **⌘K ▸ "Developer: Design gallery"**, dev builds only | No rail entry |
| `app/TopBar.tsx` — project, subject, connection, version, jobs indicator | split: project+subject → **Run bar**; connection, version, running count → **Status bar** | |
| `app/jobs-rail/JobsRail.tsx` (36/280 px, `shell.css:194,217`) | **Dock** (32/320 px, §3.6) | Same traces, more tabs |
| `ui/Layout.tsx` `PageHeader` | **deleted** (§5.7) | |
| `ui/Layout.tsx` `PageLayout` contextPanel | **deleted**; replaced by the action-bar plan strip (§4.2) | |

### 2.3 The workflow, as the IA now reads it

```
Project ──▶ Simulate ──▶ Results          (montage you already have)
   │           ▲
   │           │
   └──▶ Optimise ┘                         (search a montage, then simulate it)
   │
   └──▶ Analyse ──▶ Results                (statistics over a simulation)
```

`Optimise` hands a result to `Simulate` ("Simulate this montage" on a flex/ex result row);
`Simulate` hands a result to `Analyse` ("Analyse this simulation"); `Analyse` hands a result to
`Results`. Those three handoffs are buttons on result rows, and each pre-fills the next activity's
panel and switches to it. That is the pipeline the current nav tries to express by *ordering nav
items* — an ordering nothing enforces and nothing follows.

---

## Part 3 — The shell

### 3.1 Layout at 1600 × 1000 (the design width)

```
┌──────────────────────────────────────────────────────────────────────────────────────── 1600 ──┐
│ RUN BAR                                                                                  44 px │
│ ▣ Dataset 000 ▾ │ sub-ernie ▾ │ Simulate ▸ Montage        ⌘K  ● connected   3 running   ⌘J    │
├────┬──────────────────────┬───────────────────────────────────────────┬────────────────────────┤
│ A  │ TASK PANEL   360 px  │ CANVAS                            fluid   │ INSPECTOR       320 px │
│ C  │                      │                                           │                        │
│ T  │ ① Montage         ✓  │ ┌─────────────────┬─────────────────┐     │ ▸ Layers               │
│ I  │   GSN-HydroCel-185   │ │                 │                 │     │   ● TI_max      hot ▓  │
│ V  │   F3_F4  ·  edit     │ │       3D        │     Axial       │     │   ● final_tissues  ▓   │
│ I  │                      │ │                 │                 │     │   ● T1        gray ▓   │
│ T  │ ② Runs            2  │ ├─────────────────┼─────────────────┤     │   ● electrodes   pts   │
│ Y  │   ernie · F3_F4      │ │                 │                 │     │ ▸ Coordinates          │
│    │   101   · F3_F4      │ │    Coronal      │    Sagittal     │     │   -42.0 18.0  6.0 RAS▾ │
│ 56 │                      │ │                 │                 │     │ ▸ Cursor / Mouse       │
│    │ ③ Parameters      ▾  │ └─────────────────┴─────────────────┘     │   TI_max  0.412 V/m    │
│ ▣  │   ▸ Advanced      2  │            ~840 × ~620                    │   final_tissues  GM    │
│ ⚡ │                      │                                           │ ▸ Regions              │
│ ⊕  │                      │                                           │ ▸ Measurements         │
│ ⚗  │                      │                                           │                        │
│ ☰  │                      │                                           │                        │
│ ✓  ├──────────────────────┴───────────────────────────────────────────┴────────────────────────┤
│    │ ACTION BAR (sticky, in the task panel only)                                         56 px │
│ ⚙  │ ▸ 2 jobs · 8 CPU · 16 GB · outputs new              [ Run simulation ⌘↵ ]                 │
│ ?  ├───────────────────────────────────────────────────────────────────────────────────────────┤
│    │ DOCK  Jobs · Console · Results · Report · Notes · System            32 collapsed / 320 px │
│    │ ● running  sim ernie ▬▬▬▬▬▬▭▭▭ 2m14s   ● queued sim 101   ● ok analyzer ernie 9s      ⌃  │
├────┴───────────────────────────────────────────────────────────────────────────────────────────┤
│ STATUS BAR  Dataset 000 · /mnt/000 │ RAS −42.0 18.0 6.0 │ 60 fps · 4.1 ms · WebGL2 (M3 Pro)  24│
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Widths, exactly: activity bar **56**, task panel **360** (resizable 300–520, remembered per
activity), inspector **320** (resizable 280–420), canvas takes the rest with a **640 px floor**
(§3.3). Run bar **44**, action bar **56** (inside the task panel column, not full width), dock
**32** collapsed / **320** expanded / full-height maximised (⌘⇧J), status bar **24**. All borders
1 px `--line`.

Minimum window **1120 × 720** (today: 1024 × 680, `WT/desktop/src/renderer/app/shell.css:6-7`). The
height rises because the vertical chrome is now 44 + 32 + 24 = 100 px and a 2 × 2 grid needs ≥ 280 px
panes; 720 − 100 = 620 clears it.

### 3.2 Run bar (44 px)

Left → right: the project chip (`GET /api/project`), a **`/`**, the subject picker, a **`▸`**, and
the active task's breadcrumb (`Simulate ▸ Montage`). Right: the ⌘K affordance (a 28 px pill reading
`⌘K`), connection dot + label, running-jobs pill (⌘J), and the overflow `⋯` (Sign out).

The **subject picker is the app's only one** (fixing §0.6). It is a Combobox that accepts multi-select
for the activities that take many subjects (Prepare, Simulate, group Analyse) and shows
`ernie +2` when more than one is chosen. Changing it does two things atomically: re-runs the active
panel's catalog queries, and swaps the scene's base layers (T1, tissues, head mesh) for the new
subject while keeping layout, cursor, colormaps and thresholds. `subjectContext.ts` grows from a
"most recently used" hint into the single source of truth and gains a second field, `simulationName`,
for the same reason.

### 3.3 The collapse ladder (responsive, deterministic)

The canvas floor is **640 px**. Columns collapse in a fixed order until it is met, and each collapse
is reversible by hand (⌘B task panel, ⌘⌥B inspector) with the manual choice remembered per width
bucket.

| Available width | Task panel | Inspector | Canvas |
|---|---|---|---|
| ≥ 1600 | 360 docked | 320 docked | ≥ 864 |
| 1400–1599 | 360 docked | 320 docked | 664–863 |
| 1240–1399 | 360 docked | **40 px icon strip**, opens as a 320 px overlay sheet over the canvas' right edge | 744–903 |
| 1120–1239 | **40 px icon strip**, opens as a 360 px overlay sheet over the canvas' left edge | 40 px strip | 984–1103 |
| < 1120 | window minimum; not supported | | |

Overlay sheets are **opaque and edge-docked**, never floating over the middle of the canvas —
Tetravox's pane overlays are `pointer-events: none` by contract
(`TVX/docs/ARCHITECTURE.md:3305-3312`), so a translucent palette over the panes would fight the
WebGL grid for pointer capture. A sheet dims nothing; it takes canvas width for as long as it is
open and the engine re-fits on close.

**Focus mode** (`⌘⇧F`, or double-click a pane's header strip): both side columns go to strips, the
dock collapses to 32, and the canvas takes 1024–1520 px. This is the "read the result" posture.

### 3.4 The activity bar (56 px)

Six icons at 18 px, 44 px tall targets, a 2 px `--accent` left bar on the active one, a 20 px gap,
then Settings and Help pinned to the bottom. Each has an `aria-label` and a tooltip carrying the
title, its purpose sentence and the shortcut. No labels, at any width — the six are learned in a
day, and the palette covers the rest.

A **badge** appears on Jobs when anything is running (count) or has failed since last visit (a
`--danger` dot), and on Project when a subject in the project lacks an m2m folder while any other
activity is selected — the one "you cannot proceed" signal worth surfacing globally.

### 3.5 The Inspector (320 px) — Tetravox's right column, adopted verbatim

Tetravox already specifies this column, and re-inventing it would be a bug factory. Adopt its order
and its contents (`TVX/docs/ARCHITECTURE.md:2655-2660` for the region order, and the sections at
`:2697` coordinate bar, `:2708` measurements, `:2687` info panel, `:2723` region panel, `:2719`
histogram widget):

1. **Layers** — ordered list, eye, opacity, per-kind property editor, 1 px accent border on the
   active layer, per-dataset load card with phase + percent + elapsed + Cancel. This is where the
   current Viewer page's Layers card goes (`viewer/index.tsx`'s `EditableLayer` model), and it is
   *strictly better* than that card because the change is visible immediately instead of being
   re-serialised into a Freeview argument string.
2. **Coordinates** — the coordinate bar: editable `x y z`, space selector from
   `Engine.coordinateSpaces()` (`TVX/docs/ARCHITECTURE.md:895`), copy/paste of triples. This
   **replaces** the Subject/MNI radio pairs scattered through the forms
   (`viewer/index.tsx` `SPACE_OPTIONS`, `pages/_shared/roi/types.ts`'s `RoiSpace`,
   `final-mock/optimizer-flex-spherical-light.png`'s "Space ◉ Subject ○ MNI"): one selector, and the
   number in the form is the number in the bar because both go through `Engine.toSpace` /
   `fromSpace` (`TVX/docs/ARCHITECTURE.md:896-897`).
3. **Cursor / Mouse** — the info panel's two blocks, per-layer voxel index, value, label name,
   element id, tag name, field values.
4. **Regions** — search-as-you-type over the `LabelTable`, per-row eye + swatch + count,
   `Alt+click` to solo, double-click to jump to a centroid (`labelCentroids`,
   `TVX/docs/ARCHITECTURE.md:914`). This is the **atlas region picker** (§7.1).
5. **Measurements** — one row per measurement, jump-to, delete.

The TI-Toolbox additions to this column are exactly two, and both are *sections*, not a new column:
a **Subject** card at the top when Project is the active activity, and a **Field** card (colorbar,
histogram window, threshold, percentile presets) which is just Tetravox's histogram widget
(`:2719`) applied to the TI field layer.

### 3.6 The Dock (32 / 320 / full)

Six tabs, left-aligned, 28 px tall: **Jobs · Console · Results · Report · Notes · System**. Collapsed
(32 px) it shows the current Jobs traces exactly as the Jobs rail does today
(`WT/desktop/src/renderer/app/jobs-rail/JobsRail.tsx`) — that signature element survives intact,
it just gained neighbours. `⌘J` toggles; `⌘⇧J` maximises; clicking a tab expands.

* **Jobs** — today's jobs table plus its filters (`jobs/index.tsx:145,181` All jobs / Groups).
* **Console** — the selected job's virtualised log with level colours, filter, follow-tail,
  "Reveal log file". Opening a failed job's toast "Details" lands here.
* **Results** — a wide table for whatever the Results tree has selected: an ex-search CSV
  (`GET /api/catalog/ex-runs/{run}/results`), an analysis summary
  (`GET /api/catalog/analyses/{name}/summary`), a flex manifest. Tables belong under the canvas at
  full width, not in a 360 px panel.
* **Report** — the sandboxed report iframe (`GET /api/files/report/{id}`).
* **Notes** — Quick notes, project-scoped.
* **System** — CPU / memory / disk sparklines, processes with terminate, DooD siblings.

### 3.7 The Status bar (24 px)

Left: project name and container path. Centre: the cursor's world RAS, in the selected space, always
(`TVX/docs/ARCHITECTURE.md:2697-2707` — "every value carries its space"). Right: fps, median frame
ms, `Capabilities.renderer`, connection dot, `tit` and API versions. Every cell has a tooltip; the
renderer cell is the one that explains a missing-GPU failure (§8.4).

---

## Part 4 — How forms live beside a canvas

This is the crux of the lens. A 360 px column cannot hold the Analyzer's current form
(`final-mock/analyzer-cortical-light.png` uses ~660 px of width and scrolls past 1000 px of height).
Three rules make it fit, and they are the compaction the brief asks for.

### 4.1 Steps, not sections: a one-at-a-time accordion with summaries

Every task panel is a **numbered step list**. A step is in one of three states:

* **done** — one line, 28 px: `① Montage ✓  GSN-HydroCel-185 · F3_F4` with a hover `edit` link;
* **active** — expanded, its fields visible; exactly one step is active at a time;
* **pending** — one line, dimmed, un-clickable until its prerequisites resolve, with the reason on
  hover (`② Runs — pick a montage first`).

Advancing is implicit (fill the last required field) or explicit (`⌘↓` / clicking the next step).
Steps never renumber; a step that does not apply is hidden, not disabled.

**Why an accordion and not Slicer's all-expanded stack:** at 360 px, only one form can be legible at
once, and the step summaries are a better recap than a scrollbar position. **Why steps and not a
wizard:** a wizard forbids going back and forbids running before the end; here every step is
reachable, and the action bar is always live.

The six step lists:

| Activity | Steps |
|---|---|
| Project | ① Subjects ② Prepare ③ Assets |
| Simulate | ① Montage ② Runs ③ Parameters |
| Optimise | ① Method ② Target ③ Electrodes ④ Search |
| Analyse | ① Scope ② Source ③ Target ④ Options |
| Results | (no steps — a tree) |
| Jobs | (no steps — filters + list) |

### 4.2 Sticky action bar with an expanding plan strip — **the Plan panel is deleted**

**Decision: sticky action bar. The 320 px Plan column does not survive.**

The action bar is 56 px, sticky at the bottom of the *task panel column only* (it does not span the
canvas). It contains, on one line:

```
▸ 2 jobs · 8 CPU · 16 GB · outputs new           [ Run simulation  ⌘↵ ]
```

The left half is the plan **summary**, rendered from the same `POST /api/plan/{kind}` response the
Plan panel uses today (`WT/contracts/openapi.v1.yaml:916`). Clicking the `▸` — or hovering for
400 ms — expands a **plan sheet** upward over the task panel, max 280 px, scrollable, containing
exactly what `simulator/PlanPanel.tsx` renders now: per-subject output paths, `new` / `overwrite`
chips, lock conflicts ("will queue behind #12, charm sub-101"), warnings, and the resolved montage
list. Esc or a second click closes it.

Three states of the summary line, and they are the whole validation model:

* **ready** — `2 jobs · 8 CPU · 16 GB · outputs new`, button enabled, `--ink-2` text.
* **conflicts** — `2 jobs · 1 output exists`, in `--warning`; the button reads
  `Run simulation…` and opens an `AlertDialog` whose confirm is `Overwrite and run`.
* **incomplete** — `3 fields to complete`, in `--danger`; the button **stays enabled** (DESIGN.md's
  existing rule, `WT/desktop/DESIGN.md:126-127`), and pressing it opens the plan sheet with the
  errors listed, focuses the first one, and flashes its step in the list.

**Why the sticky bar wins.** (a) The Plan column is empty for most of an interaction (§0.4) and a
viewer-centric layout has no 320 px to reserve for text that is blank half the time. (b) The plan is
read *once*, immediately before running — a pull, not a push. (c) Putting the verb at the bottom of
the panel that produced it is the convention every configuration surface in Xcode, Linear and VS
Code settings uses, and it survives the responsive ladder (§3.3) unchanged, whereas a third column
does not. The signature the design doc wanted — "the app tells the truth before you click Run"
(`WT/desktop/DESIGN.md:25-29`) — is *preserved verbatim*; only its geometry changes.

### 4.3 Field compaction rules (binding)

1. **One column.** Never a 2-column field grid in a 360 px panel. Exception: two numeric fields that
   are read as a pair (min/max cutoff, lo/hi percentile) share a row, 50/50, with one shared label.
2. **Labels above**, 12 px `--ink-2`, 4 px gap, sentence case, no colon, no uppercase eyebrows on
   fields (eyebrows are reserved for step headers).
3. **Units are suffixes inside the control**, never a separate element or a label suffix — the
   existing `NumberInput unit=` prop is already right (`simulator/index.tsx:55`, `unit="mA"`).
4. **No help text under a field by default.** The `?` on the *step header* opens a popover carrying
   every field's help for that step. The only things allowed under a control are (a) an inline
   validation error and (b) a *consequence* number the user needs to make the decision — e.g.
   ex-search's `119,140 combinations / run` (`final-mock/optimizer-ex-light.png`'s Plan card) moves
   *under the search-space radio* where the decision is made. Today every field carries a sentence:
   `final-mock/optimizer-ex-light.png` shows four identical "Electrodes for channel N positive pole
   (anodes)" lines under four chip inputs — 96 px of vertical space restating the label.
5. **Defaults are invisible.** A field whose value equals the schema default and which the user has
   never touched lives under the step's **Advanced** disclosure. The disclosure's label carries a
   count of non-default values: `▸ Advanced · 2 changed`. This is what turns the Flex "Basic
   parameters" + "Advanced" + "Hyper-parameters" + "Electrode parameters" + "Focality options" stack
   (`optimizer-flex/index.tsx` imports at `:1-20`) into one step with a three-field face.
6. **Chips over lists.** Multi-selects render as removable chips inline (already the case —
   `final-mock/optimizer-ex-light.png`'s `E1 ×`), and overflow to `+7` with a popover.
7. **Presence, not prose.** A missing prerequisite is a chip on the step (`m2m` present,
   ~~`freesurfer`~~ missing — the strikethrough chip already exists in
   `final-mock/subjects-light.png`) with a one-click route to the activity that creates it, not a
   paragraph.
8. **Inline validation on blur and on submit**; the first error is focused; server field errors map
   through `forms/serverErrors.ts` unchanged.

Applied to the Analyzer, whose current form is the worst offender: step ① Scope = two radios;
step ② Source = subject (from the run bar) + simulation; step ③ Target = a 3-way segmented control
plus **the viewer** (§7.1); step ④ Options = space, tissue, field, with everything else under
Advanced. Four steps, ~9 visible controls, versus today's ~14 controls and 6 help paragraphs in one
scroll.

### 4.4 What the canvas does while a form is open

The canvas is **not decorative during configuration** — that is the whole thesis. Each step arms the
scene:

| Activity ▸ step | Scene state |
|---|---|
| Project ▸ Subjects | T1 + `final_tissues` label overlay for the highlighted subject; hovering a row previews it |
| Project ▸ Prepare | T1 only; steps that will produce a volume show a ghost layer row |
| Simulate ▸ Montage | head mesh + EEG net points; the selected montage's 4 electrodes highlighted, others dimmed |
| Simulate ▸ Runs | as above, one montage per selected row, cycled with `[`/`]` |
| Optimise ▸ Target | ROI spheres / atlas regions rendered live (§7.1); Avoid set in a second colour |
| Optimise ▸ Electrodes | net points, bucket membership as four colours |
| Analyse ▸ Target | the field layer + the ROI mask as a label layer, so the user sees what will be measured |
| Results ▸ any row | the run's layers, thresholds from its own analysis |

---

## Part 5 — Per-screen wireframes

Common frame, abbreviated in the drawings below:

```
ACT = activity bar 56 · TASK = task panel 360 · CANVAS = fluid · INSP = inspector 320
Run bar 44 on top · Action bar 56 at the foot of TASK · Dock 32/320 · Status 24
```

### 5.1 Project (⌘1) — subjects, prepare, assets

```
┌ RUN ▣ Dataset 000 ▾ │ sub-ernie ▾ │ Project ▸ Subjects        ⌘K ● connected 0 running ⌘J ─┐
├──┬──────────────────────────┬────────────────────────────────┬──────────────────────────────┤
│▣ │ ① SUBJECTS          3    │ ┌──────────────┬─────────────┐ │ SUBJECT  ernie               │
│⚡│  ⌕ filter          + Add │ │              │             │ │ ───────────────────────────  │
│⊕ │ ┌──────────────────────┐ │ │      3D      │    Axial    │ │ Head model  m2m_ernie        │
│⚗ │ │☑ ernie   raw fs m2m  │ │ │   scalp +    │  T1 + tissue│ │ Nodes       847,000          │
│☰ │ │  ▸ 3 sims · 1 lf     │ │ │   tissues    │   overlay   │ │ Space       subject           │
│✓ │ │☑ 101     raw ─  m2m  │ │ ├──────────────┼─────────────┤ │ ───────────────────────────  │
│  │ │  ▸ 1 sim             │ │ │   Coronal    │  Sagittal   │ │ DATA                          │
│  │ │☐ MNI152  ─   ─  m2m  │ │ │              │             │ │ raw ✓ · freesurfer ✓ · m2m ✓  │
│  │ └──────────────────────┘ │ └──────────────┴─────────────┘ │ dwi ✓ · ct ✗                  │
│  │                          │                                │ ───────────────────────────  │
│  │ ② PREPARE           ▾    │                                │ ASSETS                        │
│  │  ☑ DICOM → NIfTI         │                                │ Leadfield GSN-185   2.0 GB ✓  │
│  │  ☑ SimNIBS charm         │                                │ Leadfield EGI_temp    — ⊕     │
│  │  ☑ FreeSurfer recon-all  │                                │ EEG forward         — ⊕       │
│  │  ☐ Subcortical seg.      │                                │ ───────────────────────────  │
│  │  ☑ Tissue analyzer       │                                │ LAYERS                        │
│  │  ▸ Advanced · DWI        │                                │ ● final_tissues   label ▓     │
│  │                          │                                │ ● T1              gray  ▓     │
│  │ ③ ASSETS            ▾    │                                │                               │
│  ├──────────────────────────┤                                │                               │
│  │ ▸ 2 jobs · 8 CPU · new   │                                │                               │
│⚙ │        [ Queue 2 jobs ⌘↵]│                                │                               │
│? ├──────────────────────────┴────────────────────────────────┴──────────────────────────────┤
│  │ Jobs · Console · Results · Report · Notes · System                        No jobs running │
├──┴────────────────────────────────────────────────────────────────────────────────────────────┤
│ Dataset 000 · /mnt/000     RAS  −42.0  18.0  6.0        60 fps · 3.8 ms · WebGL2 (Apple M3)   │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Notes. The Subjects list is the merged table (§2.2): the presence chips of
`final-mock/subjects-light.png` plus the Leadfields column and *Export selected* of
`final-mock/panel-subject-info-light.png`. Checkboxes drive Prepare; the *highlighted* row (arrow
keys, single click) drives the scene and the inspector. `+ Add` opens the DICOM/NIfTI import dialog.
Assets is where `LeadfieldPanel.tsx` and the Source panel's "Build forward solution" now live, each
a row with a presence chip and a `⊕` that queues its job.

### 5.2 Simulate (⌘2)

```
┌ RUN ▣ Dataset 000 ▾ │ ernie +1 ▾ │ Simulate ▸ Montage           ⌘K ● connected 0 running ─┐
├──┬──────────────────────────┬───────────────────────────────────┬───────────────────────────┤
│▣ │ ① MONTAGE                │ ┌───────────────┬───────────────┐ │ LAYERS                    │
│⚡│  ┌────────────────────┐  │ │               │               │ │ ● electrodes    pts  ▓    │
│⊕ │  │Montage│Flex│Free-h │  │ │      3D       │     Axial     │ │ ● ernie.msh    mesh  ▓    │
│⚗ │  └────────────────────┘  │ │   scalp with  │  T1 + tissues │ │ ● T1           gray  ▓    │
│☰ │  Net  GSN-HydroCel-185 ▾ │ │  E24 ● ● E124 │               │ │ ──────────────────────────│
│✓ │  ⌕ montage       + New   │ │  E37 ○ ○ E87  │               │ │ MONTAGE  F3_F4            │
│  │ ┌──────────────────────┐ │ ├───────────────┼───────────────┤ │ E24 → E124   1.0 mA       │
│  │ │◉ F3_F4      E24→E124 │ │ │    Coronal    │   Sagittal    │ │ E37 → E87    1.0 mA       │
│  │ │○ Thalamus_t E37→E87  │ │ │               │               │ │ ──────────────────────────│
│  │ │○ L_Insula_t E37→E18  │ │ └───────────────┴───────────────┘ │ COORDINATES               │
│  │ └──────────────────────┘ │  ⓘ click an electrode to reassign │  −42.0  18.0  6.0  RAS ▾  │
│  │  ⓘ hover a row to preview│    the focused pair slot          │ ──────────────────────────│
│  │                          │                                   │ CURSOR                    │
│  │ ② RUNS              2 ▾  │                                   │  T1            412        │
│  │ ┌──────────────────────┐ │                                   │  final_tissues GM         │
│  │ │ernie F3_F4  1.0 1.0  │ │                                   │                           │
│  │ │101   F3_F4  1.0 1.0  │ │                                   │                           │
│  │ └──────────────────────┘ │                                   │                           │
│  │                          │                                   │                           │
│  │ ③ PARAMETERS         ▾   │                                   │                           │
│  │  Conductivity  Isotropic▾│                                   │                           │
│  │  Electrode  ◉Ellipse ○Rect│                                  │                           │
│  │  ▸ Advanced · 1 changed  │                                   │                           │
│  ├──────────────────────────┤                                   │                           │
│  │ ▸ 2 jobs · 8 CPU · 16 GB │                                   │                           │
│⚙ │      [ Run 2 simulations⌘↵]                                  │                           │
│? ├──────────────────────────┴───────────────────────────────────┴───────────────────────────┤
│  │ Jobs · Console · Results · Report · Notes · System                       No jobs running  │
└──┴─────────────────────────────────────────────────────────────────────────────────────────  ┘
```

The three montage sources become a segmented control (was: tabs at `simulator/index.tsx:150-152`).
"Global parameters" loses its name — in a step list the step *is* the grouping — and its six controls
reduce to two plus an Advanced disclosure. The electrode picking behaviour is §7.2.

### 5.3 Optimise (⌘3)

```
├──┬──────────────────────────┬───────────────────────────────────┬───────────────────────────┤
│▣ │ ① METHOD                 │ ┌───────────────┬───────────────┐ │ LAYERS                    │
│⚡│  ┌────────────────────┐  │ │               │               │ │ ● roi           pts  ▓    │
│⊕ │  │ Flex │ Ex │ mEx   │  │ │      3D       │     Axial     │ │ ● avoid         pts  ▓    │
│⚗ │  └────────────────────┘  │ │  ● ROI sphere │  ⊕ ROI disc   │ │ ● DK40          label▓    │
│☰ │  Goal  mean ▾            │ │  ○ avoid      │               │ │ ● T1            gray ▓    │
│✓ │  Post  max_TI ▾          │ ├───────────────┼───────────────┤ │ ──────────────────────────│
│  │  ▸ Advanced · 1 changed  │ │    Coronal    │   Sagittal    │ │ REGIONS      ⌕ superior…  │
│  │                          │ │               │               │ │ ☑ superiorfrontal  lh 8k  │
│  │ ② TARGET             ▾   │ └───────────────┴───────────────┘ │ ☐ rostralmiddle…   lh 5k  │
│  │  ┌──────────────────────┐│  ⓘ ⇧-click a pane to place a      │ ☐ parsopercularis  lh 2k  │
│  │  │Sphere│Cortex│Subcort ││    sphere · drag to move it       │ ──────────────────────────│
│  │  └──────────────────────┘│                                   │ COORDINATES               │
│  │   x      y      z    r   │                                   │  10.0 −20.0 15.0  MNI ▾   │
│  │  ┌────┬─────┬─────┬────┐ │                                   │  world RAS  8.4 −22.1 …   │
│  │  │ 10 │ −20 │  15 │  8 │ │                                   │ ──────────────────────────│
│  │  └────┴─────┴─────┴────┘ │                                   │ CURSOR                    │
│  │  [ ⊕ Pick in viewer ]    │                                   │  DK40  superiorfrontal    │
│  │  ▸ Avoid region (focality)│                                  │                           │
│  │                          │                                   │                           │
│  │ ③ ELECTRODES         ▾   │                                   │                           │
│  │ ④ SEARCH             ▾   │                                   │                           │
│  ├──────────────────────────┤                                   │                           │
│  │ ▸ 1 job · 8 CPU · 12 GB  │                                   │                           │
│  │   119,140 combinations   │                                   │                           │
│⚙ │      [ Run flex-search ⌘↵]                                   │                           │
```

Flex / Ex / mEx are one method selector (they differ in steps ③ and ④, not in kind), which removes
the ⌘4/⌘5 split that forced a user to know *which algorithm* before knowing *what they wanted*. The
leadfield requirement for Ex/mEx appears as a presence chip in step ① with a link to Project ▸ Assets
(§2.2) rather than as a full card of its own.

### 5.4 Analyse (⌘4)

```
├──┬──────────────────────────┬───────────────────────────────────┬───────────────────────────┤
│▣ │ ① SCOPE                  │ ┌───────────────┬───────────────┐ │ LAYERS                    │
│⚡│  ┌───────────────┐       │ │               │               │ │ ● TI_max     hot  ▓ 0.98  │
│⊕ │  │ Single │ Group│       │ │      3D       │     Axial     │ │ ● roi_mask   label▓       │
│⚗ │  └───────────────┘       │ │  field on GM  │ T1 + TI_max   │ │ ● T1         gray ▓       │
│☰ │                          │ │  + ROI outline│ + ROI outline │ │ ──────────────────────────│
│✓ │ ② SOURCE             ✓   │ ├───────────────┼───────────────┤ │ FIELD  TI_max             │
│  │  ernie · Thalamus        │ │    Coronal    │   Sagittal    │ │  ▁▂▅█▆▃▁ log              │
│  │                          │ │               │               │ │  window 0.21 ── 0.98 V/m  │
│  │ ③ TARGET             ▾   │ └───────────────┴───────────────┘ │  p50–p99.9  2–98%  ±p99   │
│  │  ┌──────────────────────┐│                                   │ ──────────────────────────│
│  │  │Sphere│Cortex│Subcort ││                                   │ REGIONS  ⌕ thalamus       │
│  │  └──────────────────────┘│                                   │ ☑ Left-Thalamus     4.1k  │
│  │  Atlas  DK40           ▾ │                                   │ ☐ Right-Thalamus    4.0k  │
│  │  Regions  [superiorfr ×] │                                   │ ──────────────────────────│
│  │           [+ 2 more]     │                                   │ CURSOR                    │
│  │                          │                                   │  TI_max        0.412 V/m  │
│  │ ④ OPTIONS            ▾   │                                   │  roi_mask      in ROI     │
│  │  Space ◉Mesh ○Voxel      │                                   │                           │
│  │  Field  Auto (TI_max)  ▾ │                                   │                           │
│  │  ▸ Advanced              │                                   │                           │
│  ├──────────────────────────┤                                   │                           │
│  │ ▸ 1 job · 2 CPU · new    │                                   │                           │
│⚙ │      [ Run analysis ⌘↵ ] │                                   │                           │
```

Group scope replaces step ② with a subject×simulation pair table and step ④ with a method selector
(`NIfTI average` / `Cluster permutation` / `Group comparison`) — i.e. the three panels of §2.2 land
here as *options in one step*, not three nav items. `Space` gains a third value, `fsaverage`, which
is the Source panel's "Map fields to fsaverage".

### 5.5 Viewer / focus mode (⌘⇧F) — the reading posture

```
┌ RUN ▣ Dataset 000 ▾ │ ernie ▾ │ Results ▸ Thalamus ▸ TI_max      ⌘K ● connected  0 running ─┐
├──┬─────────────────────────────────────────────────────────────────────────────────────┬────┤
│▣ │ ┌───────────────────────────────────┬───────────────────────────────────┐           │ ▤  │
│⚡│ │  L                             R  │  A                             P  │           │ ▤  │
│⊕ │ │                                   │                                   │           │ ▤  │
│⚗ │ │              3D                   │             Axial                 │           │ ▤  │
│☰ │ │      head + field isosurface      │       T1 + TI_max (heat)          │           │ ▤  │
│✓ │ │            ⟨cube⟩                 │  Thalamus  z = 8   RAS 0 −20 8    │           │ ▤  │
│  │ │                              NEU  │  ├──10 mm──┤                 NEU  │           │ ▤  │
│  │ ├───────────────────────────────────┼───────────────────────────────────┤           │ ▤  │
│  │ │  S                             I  │  S                             I  │           │ ▤  │
│  │ │            Coronal                │            Sagittal               │  ▮ 0.98   │ ▤  │
│  │ │                                   │                                   │  ▮        │ ▤  │
│  │ │                                   │                                   │  ▮ 0.60   │ ▤  │
│  │ │                              NEU  │                              NEU  │  ▮ 0.21   │ ▤  │
│  │ └───────────────────────────────────┴───────────────────────────────────┘  TI_max   │ ▤  │
│⚙ │                                                                            V/m      │ ▤  │
│? ├─────────────────────────────────────────────────────────────────────────────────────┴────┤
│  │ Jobs · Console · Results · Report · Notes · System                          No jobs      │
├──┴───────────────────────────────────────────────────────────────────────────────────────────┤
│ Dataset 000 · /mnt/000     RAS  0.0  −20.0  8.0  ·  MNI −1.2 −18.9 9.4    60 fps · WebGL2   │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

Both side columns are 40 px strips (`▤` = the inspector's section icons: layers, coordinates,
cursor, regions, measurements — Blender's convention, §1.3); clicking one opens that section as a
320 px overlay sheet. The pane chrome — orientation letters on all four edges, the `NEU`/`RAD`
badge, the scale bar, the corner slice/RAS info, the orientation cube, the colour bar — is
Tetravox's, mandatory and non-optional (`TVX/docs/ARCHITECTURE.md:2671-2685`), and we neither
re-draw nor suppress any of it.

### 5.6 Jobs (⌘6) — dock expanded

```
├──┬──────────────────────────┬───────────────────────────────────────────────────────────────┤
│▣ │ FILTERS                  │                                                               │
│⚡│  State   All          ▾  │                    canvas keeps the current scene             │
│⊕ │  Kind    All          ▾  │                                                               │
│⚗ │  Subject All          ▾  │                                                               │
│☰ │ ─────────────────────────┤                                                               │
│✓ │ GROUPS               2   │                                                               │
│  │  ▸ pre · 3 subjects      │                                                               │
│  │  ▸ sim · 2 subjects      │                                                               │
│  ├──────────────────────────┴───────────────────────────────────────────────────────────────┤
│  │ ● Jobs   Console   Results   Report   Notes   System                    ⌃ collapse  ⌘⇧J  │
│  ├──────────────────────────────────────────────────────────────────────────────────────────┤
│  │ State      Kind      Subject  Stage             Elapsed   CPU    RSS     Waiting on      │
│  │ ● running  sim       ernie    solving 3/4  ▬▬▬▭ 2m14s     780%   3.1 GB  —          ⏹ ⋯ │
│  │ ● queued   sim       101      —                 —         —      —       #41 sim ernie ⋯│
│  │ ● ok       analyzer  ernie    done · 100 %      9s        —      —       —            ⋯ │
│  │ ● failed   flex      101      exit 1            4m02s     —      —       —      Details │
│⚙ │                                                                                         │
│? ├──────────────────────────────────────────────────────────────────────────────────────────┤
│  │ Dataset 000 · /mnt/000    RAS 0.0 −20.0 8.0        3 running · 1 failed · WebGL2         │
```

Selecting a row and pressing `⌘⏎`, or clicking `Details`, switches the dock to **Console** with that
job's log, tailing. The `JobDetailDrawer` (`jobs/index.tsx`) becomes the Console tab's header strip:
spec, artifacts (Open / View / Reveal), and Cancel / Rerun / Force.

### 5.7 What is gone from every screen

* The `PageHeader` block — 24 px title + 14 px purpose + 24 px margin ≈ 66 px, on every screen
  (`WT/desktop/src/renderer/ui/Layout.tsx`; visible at the top of every screenshot). Replaced by the
  run bar's breadcrumb (`Simulate ▸ Montage`), which is 0 additional pixels because the run bar
  already exists.
* The 320 px context panel (§4.2).
* The 960 px content cap (`WT/desktop/src/renderer/ui/components.css:1379`) — content is now sized by
  its column, and wide content lives in the dock.
* The nav rail's group labels and per-item ⌘-chips (`NavRail.tsx:7-14,43-45`) — tooltips carry both.

---

## Part 6 — Density and theme tokens

### 6.1 Type scale (replaces `WT/desktop/DESIGN.md:62-65`)

| token | px/lh | use |
|---|---|---|
| `--text-micro` | 11/14 | status bar, pane corner info, chip counts |
| `--text-sm` | 12/16 | field labels, help, secondary table cells |
| **`--text-base`** | **13/18** | **body: controls, table cells, buttons, activity tooltips** |
| `--text-md` | 14/20 | step headers, inspector section headers, dialog body |
| `--text-lg` | 16/22 | dialog titles, empty-state headline |

There is no 20 px and no 24 px size. Page titles do not exist (§5.7). Weights: 400 body, 500
labels/buttons/step headers, 600 dialog titles. Uppercase eyebrows (12 px, .06em, `--ink-2`) are
reserved for **step headers and inspector section headers only**. Fonts unchanged: IBM Plex Sans /
IBM Plex Mono, `font-variant-numeric: tabular-nums` on every number.

### 6.2 Density (replaces `WT/desktop/DESIGN.md:66-69`)

| element | today | proposed |
|---|---|---|
| table row | 36 | **28** |
| input / select / button (md) | 32 | **28** |
| button sm / lg | 28 / 40 | **24 / 32** |
| icon in a control | 16 | **14** |
| icon in a rail | 20 | **16** (18 in the activity bar) |
| step summary row | — | **28** |
| tree row | — | **26** |
| section gap in the task panel | 16 | **8** |
| field gap | 8 | **6** |
| card padding | 16 | **12** (10 in the inspector) |

Spacing scale: 2 · 4 · 6 · 8 · 12 · 16 · 24 (drops 32 and 48). Radii: 3 controls, 5 cards/panels,
999 chips. **Rationale:** Slicer, Blender and VS Code all run 11–13 px chrome with 22–28 px rows
because the chrome must not compete with the canvas; Linear runs 13/28 for the same reason on a
list-heavy product. Moving from 14/36 to 13/28 recovers ~22 % of vertical space in every list and
form, which is exactly the budget the canvas needs.

### 6.3 Colour

Keep every token in `WT/desktop/DESIGN.md:34-57` — the palette is good, disciplined, and the
`--field` orange for TI/mTI semantics is a genuinely nice decision. Three changes:

1. **Add `--canvas: #08090B`, identical in both themes.** Tetravox's panes stay dark in every theme
   by contract (`TVX/docs/ARCHITECTURE.md:2736-2740`: "a light viewport changes what a greyscale T1
   and a heat overlay look like"). The token exists so the chrome knows the canvas will not follow it.
2. **Add `--chrome`** (`#12161C` dark / `#FFFFFF` light) for the four rails, distinct from
   `--surface`, so the rails read as frame and the panels read as content.
3. **Default theme becomes dark.** A light chrome wrapped around a permanently dark canvas is the
   worst of both; and every reference viewer (Slicer, Freeview, Blender, ITK-SNAP) ships dark.
   `system` / `light` / `dark` all stay, in Settings ▸ Appearance, applied before first paint exactly
   as today (`WT/desktop/DESIGN.md:159-164`). Light must remain fully supported and screenshotted.

The engine's own chrome is themed through `Engine.setTheme` in the same tick as the DOM flip
(`TVX/docs/ARCHITECTURE.md:2740-2744`); the app must call it and must not restyle panes in CSS.

### 6.4 Motion

Unchanged from `WT/desktop/DESIGN.md:70-73` (150 ms ease-out, 1.6 s liveness pulse,
`prefers-reduced-motion` kills all of it), with one addition: **the canvas never animates on layout
change** — a pane resize is instant, because an animated WebGL resize is a stutter, not a transition.

---

## Part 7 — The viewer as an input device

This is what "viewer-centric" buys that no amount of restyling can.

### 7.1 ROI definition, interactive

Today an ROI is typed: `x / y / z / radius` number inputs plus a Subject/MNI radio pair
(`WT/desktop/src/renderer/pages/_shared/roi/types.ts:36-45`, `SphereRow`; the radio pair visible in
`final-mock/optimizer-flex-spherical-light.png`), or an atlas + region combobox picked from a list of
names with no picture (`final-mock/analyzer-cortical-light.png`: "Select an atlas…" then "Select an
atlas first").

**Spherical.** The ROI is a Tetravox `PointsLayer`
(`TVX/docs/ARCHITECTURE.md:441-449`: `points: { position, color, radiusMm }[]`, `shape: 'sphere'`).
`⊕ Pick in viewer` calls
`Engine.setPointTool({ layerId, mode: 'place', template: { radiusMm, color, group: 'roi' } })`
(`TVX/docs/ARCHITECTURE.md:907`, `:821-836` for the spec type). Every unmodified left click in any
pane appends a centre and fires a `PointToolEvent { kind:'placed', world }`; the step's table gains a
row. Dragging a placed sphere in the pane it lives in moves it (`mode:'select'`'s on-slice drag,
`TVX/docs/ARCHITECTURE.md:2548-2552`); the row's numbers follow. Radius is edited in the row and
written back as `radiusMm`, so the disc in every pane is the actual search radius — the single most
valuable thing a TI researcher can see before spending four hours on a flex-search.

Multiple spheres remain a **union**, exactly as `roiToConfig` already encodes
(`pages/_shared/roi/types.ts:88-101`, arrays of x/y/z/radius). The Avoid (non-ROI, focality) set is a
second `PointsLayer` with `--danger` colouring and its own tool arming; the two are never armed at
once, which the engine guarantees (arming one disarms measure mode and vice versa,
`TVX/docs/ARCHITECTURE.md:907-908`).

**Space.** `use_mni` (`types.ts:90`) stops being a radio pair and becomes the inspector's coordinate
space selector. The form stores world RAS; `Engine.toSpace`/`fromSpace`
(`TVX/docs/ARCHITECTURE.md:896-897`) convert for display and for the wire. A space that cannot be
resolved is listed, disabled, with the reason on it — Tetravox's own rule
(`TVX/docs/ARCHITECTURE.md:2703-2706`) — which is a far better answer than today's silent MNI radio
on a subject with no registration.

**Cortical / subcortical.** The atlas is loaded as a **label layer**; the inspector's Regions panel
(§3.5, `TVX/docs/ARCHITECTURE.md:2723-2730`) is the picker: search-as-you-type over the `LabelTable`,
eye + swatch + count per row, `Alt+click` to solo, double-click to jump the cursor to that region's
centroid via `labelCentroids` (`:914`). **The Regions panel's checkbox state and the form's
`RoiRegion[]` are one value** — tick a region in the panel and it appears as a chip in the step;
click a region in a pane and it is added. `RoiRegion.id` is already the FreeSurfer `.annot` label
index / atlas voxel value (`pages/_shared/roi/types.ts:26-30`), which is exactly what a `LabelTable`
is keyed by (`TVX/docs/ARCHITECTURE.md:224-227`), so the two models join with no translation layer.

The consequence: `pages/_shared/roi/RoiPicker.tsx` and `pages/optimizer-ex/roi/RoiPicker.tsx` — two
implementations of the same widget — collapse into one *step* whose face is a 3-way segmented
control and a table, because the picking has moved to the canvas.

### 7.2 Montage and electrode placement, interactive

Today: an EEG net dropdown, a montage table of `E24→E124` strings
(`final-mock/simulator-light.png`), and — to see where those electrodes actually are — a background
`tools` job that bakes a NIfTI of electrode positions
(`WT/tit/server/routes/viewers.py:10-38`; the "Create electrode overlay" card in
`final-mock/viewer-light.png` carries a five-line explanation of the round trip and a
`TI · not created` chip).

Instead:

* The subject's head mesh (`m2m_<id>/<id>.msh`) is a mesh layer; the net's positions
  (`m2m_<id>/eeg_positions/`, already the path the overlay tool takes,
  `viewer/index.tsx:92`) load as a **`PointsLayer` with `showLabels`**
  (`TVX/docs/ARCHITECTURE.md:449`). 185 labelled dots on a scalp — this is `GSN-HydroCel-185`, drawn.
* Selecting a montage row highlights its four electrodes (per-point `color`) and dims the rest via
  the layer's `offPlaneOpacity` / point colours; hovering a row previews it. Polarity is two colours,
  so anode/cathode is legible without reading `E1+ / E1−` labels.
* **Editing a montage**: one of the four pair slots is focused (`Tab` cycles); clicking any electrode
  in any pane assigns it to the focused slot and advances. This is exactly the ex-search bucket model
  (`pages/optimizer-ex/ElectrodeBuckets.tsx`; the four chip inputs of
  `final-mock/optimizer-ex-light.png`) made spatial, and it is the same interaction for
  ex-search's E1+/E1−/E2+/E2− buckets.
* **Free-hand** (`simulator/FreehandTab.tsx`, `PUT /api/catalog/freehand/{name}`): arm the point tool
  in `place` mode against a `freehand` points layer; a click in the 3D pane picks the scalp surface
  (`TVX/docs/ARCHITECTURE.md:2516-2518` — a 3D click uses `pick`, and a click on nothing places
  nothing rather than inventing a point on the near plane), giving four scalp points and a montage.
  That is a feature the PyQt GUI never had and the current v3 form cannot have.
* The electrode-overlay NIfTI job survives as an **export** (§2.2), for people taking figures into
  Freeview or FSLeyes.

### 7.3 Results inspected in place

Selecting a run in the Results tree loads its layers rather than describing them:

| Result kind | Scene |
|---|---|
| simulation | T1 (gray) + `TI_max` (heat, window from the run's own stats) + `final_tissues` (label, hidden) + the montage's electrodes |
| mesh simulation | `<sim>.msh` with the field as the mesh's scalar, tissue tags in the Regions panel |
| flex run | the optimised electrodes as points + the ROI sphere that was searched + the resulting field |
| ex/mex run | the best montage's electrodes; the CSV in the dock's Results tab, and selecting a CSV row swaps the electrodes |
| analysis | the field + the ROI mask as a label layer + the summary table in the dock |
| group | the MNI average volume + the cluster mask |

`GET /api/view/{kind}` (`WT/contracts/openapi.v1.yaml:1184`) already returns exactly the layer list
this needs — `{ path, kind: volume|label, colormap, opacity, visible, cal_min, cal_max, lut }` — built
by `WT/tit/viewspec.py`. **That endpoint is kept and repurposed**: its `layers[]` map onto
`Engine.addDataset({kind:'path'})` + `Engine.addLayer(...)` one for one, and only its
`freeview_args[]` field becomes vestigial (used solely by the "Open externally" escape hatch). No
server change is needed to put the first version of this on screen.

**Comparison** is two field layers in one scene with a blend slider, or a `3d+1` layout with a
different active layer per pane — `SliceView.layerVisibility` is per view
(`TVX/docs/ARCHITECTURE.md:564`), so an A/B is a layout, not a feature.

### 7.4 Figures

Tetravox's `Engine.screenshot(opts)` writes a PNG with DPI in the pHYs chunk
(`TVX/docs/ARCHITECTURE.md:927`, `:2780-2790`). The **camera** button in the run bar's overflow
produces a publication figure of the current scene — including colour bars, orientation labels and
the scale bar, each toggleable in the dialog — and writes it to
`derivatives/ti-toolbox/figures/`. The Nilearn panel keeps its own job for the glass-brain /
surface-plot styles Tetravox does not draw (§2.2, Results ▸ Figures).

---

## Part 8 — States

### 8.1 Empty

| Where | State |
|---|---|
| Canvas, no project | Centred `EmptyState` **inside the canvas**: "Open a BIDS project to begin." + `Open project…` + `Create project…` + recents list |
| Canvas, project but no subject | "Pick a subject to load its head model." + subject list + `⌘K to search` |
| Canvas, subject with no m2m | "sub-101 has no head model yet." + `Prepare sub-101` (routes to Project ▸ Prepare with it selected) |
| Subjects list empty | "No subjects in Dataset 000." + `Add subject…` (DICOM/NIfTI import) |
| Results tree empty | "Nothing has been run for ernie yet." + three buttons: `Simulate`, `Optimise`, `Prepare` |
| Regions panel, no label layer | "Load an atlas to browse regions." + `Add atlas…` |
| Dock ▸ Jobs empty | "No jobs yet." — one line, 28 px, no illustration |

Empty states are the only centred thing in the app (a rule DESIGN.md already has,
`WT/desktop/DESIGN.md:69`), one sentence, at most three actions, no illustration larger than a 24 px
icon.

### 8.2 Loading

* **Datasets**: Tetravox's per-dataset **load card** in the Layers list — phase + percent + elapsed +
  Cancel (`TVX/docs/ARCHITECTURE.md:2655-2658`). Do not build a second one. A 847k-node
  `ernie.msh` takes real time and the phase (`fetch → inflate → parse → topology`) is the honest
  progress.
* **Catalog queries**: skeleton rows in the list being filled, never a spinner over a whole panel,
  never a blank panel.
* **Plan**: the summary line shows `computing plan…` with a 2 px indeterminate underline; the button
  stays enabled and queues the plan request on click.
* **Canvas first paint**: the panes render their chrome (orientation letters, badges) over
  `--canvas` immediately; only the imagery streams in.

### 8.3 Errors

* **Field**: inline, under the control, `--danger`, 12 px; the control gets a `--danger` border.
  Server errors map to fields via `forms/serverErrors.ts`.
* **Preflight** (existing outputs, lock waits): in the plan sheet, per subject, with the affected
  subject named — as today.
* **Job failure**: the dock row turns `--danger`; a persistent toast "flex-search failed for 101"
  with `Details` opening Dock ▸ Console at the failing job, scrolled to the last 40 lines.
* **Dataset load failure**: the layer row shows a `--danger` chip and the reason; the engine emits
  `error { code, message, datasetId }` (`TVX/docs/ARCHITECTURE.md:857`) and never retries into the
  same wasm instance (`:1035` — a panic poisons the module).
* **Disconnected**: status-bar dot to `--warning`, a 2 px amber strip under the run bar, run buttons
  disabled with a tooltip; forms stay editable and nothing is discarded.
* **Voice**: what happened, what to do, no apology, no exclamation mark — DESIGN.md's rule
  (`WT/desktop/DESIGN.md:146-148`) is right and stands.

### 8.4 The one state that decides whether this design ships: **no WebGL2**

Chromium M137 removed the automatic SwiftShader fallback, so a blocklisted driver yields
`getContext('webgl2') === null` (`TVX/docs/ARCHITECTURE.md:25`). On such a machine the canvas is
dead and the app must still be usable.

The canvas region renders a first-class failure state — "This machine has no WebGL2 (`<renderer>`).
The viewer is unavailable; results can still be opened in Freeview or Gmsh." — with two buttons wired
to the *kept* `POST /api/viewers/{freeview,gmsh}` endpoints, and the status bar's renderer cell in
`--warning`. The task panels, the dock, the jobs model and every form keep working; only the picking
interactions (§7.1, §7.2) fall back to their numeric inputs, which is why those inputs are never
removed — `⊕ Pick in viewer` is always an *additional* affordance beside a live `x / y / z` row, never
a replacement for it.

This is also the honest answer to "why keep Freeview at all": not nostalgia, a fallback with a
concrete trigger.

---

## Part 9 — Keyboard and the command palette

### 9.1 The rule that prevents collisions

Tetravox binds many **unmodified** keys on the canvas: `r` reset, `m` measure, `x` cycle layout,
`+`/`-` zoom, arrows nudge the cursor, PgUp/PgDn step slices, `space`+drag pans, `?` the keyboard
sheet (`TVX/docs/ARCHITECTURE.md:2495-2530`).

**Rule: unmodified keys belong to whatever has focus. Every app-level shortcut carries ⌘/Ctrl.**
The one shared key is `?`, which opens one keyboard sheet listing both halves. `Esc` is scoped:
it closes the top-most overlay if there is one, else cancels the canvas's pending gesture, else
blurs the focused control.

### 9.2 The map

| Keys | Action |
|---|---|
| `⌘K` | Command palette |
| `⌘P` | Quick open — subjects, simulations, analyses, runs, by fuzzy name |
| `⌘1…⌘6` | Project · Simulate · Optimise · Analyse · Results · Jobs |
| `⌘,` / `?` | Settings dialog / Help sheet |
| `⌘B` / `⌘⌥B` | Toggle task panel / inspector |
| `⌘J` / `⌘⇧J` | Toggle dock / maximise dock |
| `⌘⇧F` | Focus mode (both columns to strips) |
| `⌘↵` | Run the active task (the action bar's primary verb) |
| `⌘↓` / `⌘↑` | Next / previous step in the task panel |
| `⌘⇧V` | Focus the canvas (blur every form control) |
| `⌘\` | Cycle canvas layout — the app's alias for Tetravox's `x` |
| `[` / `]` | Previous / next item in the active list (montage, run, region) — list-scoped, not global |
| `Esc` | Scoped close/cancel/blur, as above |

`⌘7`, `⌘8`, `⌘9` are deliberately unbound: six activities, six digits, and a free range for later
without renumbering. The current map (`WT/desktop/DESIGN.md:174-191`) binds nine digits to nine
pages and still cannot reach ten of the nineteen destinations.

### 9.3 The palette (⌘K) — where the removed nav items went

`cmdk` is already a dependency (§0.7). The palette has typed groups, each with an icon:

* **Go** — the six activities, plus every dock tab, plus `Settings ▸ <tab>`, `Help ▸ <tab>`. This is
  where **System**, **Notes**, **Report** and the Settings/Help tabs are reachable by name — nothing
  that left the rail became unreachable.
* **Subjects** — `ernie`, `101`, `MNI152`; picking one sets the run bar's subject and loads the scene.
* **Open** — every simulation, flex run, ex/mex run, analysis and report, as
  `ernie / Thalamus / TI_max`; picking one loads it into the scene and selects it in Results.
* **Run** — `Run simulation`, `Queue pre-processing for 3 subjects`, `Run flex-search`, each
  disabled with its reason when the active panel is incomplete.
* **View** — `Layout 2×2 / 1+3 / 3d+1 / 3D only`, `Radiological on/off`, `Reset view`, `Screenshot…`,
  `Toggle colour bars`, `Toggle scale bar`, each a direct `Engine` call.
* **Developer** (dev builds only) — `Design gallery`, `Copy ViewSpec JSON`, `Dump scene`.

Every entry carries its shortcut on the right and the `PageDef.purpose` sentence as its description —
which is where those twelve sentences go once the page headers die (§5.7).

---

## Part 10 — Build sequence

Ordered so that each step is shippable and none blocks on the one after it.

1. **Shell swap, no behaviour change.** Activity bar + run bar + task panel + dock + status bar,
   with the *existing* pages rendered into the task panel column unchanged and a placeholder canvas.
   Kill `PageHeader` and the 960 px cap. Density tokens (§6.2). Ship: the app looks right, nothing
   is lost.
2. **Palette + one subject.** ⌘K, ⌘P, the run bar's single subject picker; delete the seven per-page
   pickers; make `subjectContext` authoritative. Ship: navigation stops depending on the rail.
3. **Canvas, read-only.** Mount `@tetravox/engine` (`create(canvas)`,
   `TVX/docs/ARCHITECTURE.md:937`); wire `GET /api/view/{kind}` → `addDataset` + `addLayer`; adopt
   the inspector (layers, coordinates, cursor, regions, measurements). Results selection loads the
   scene. Ship: **the Viewer page can be deleted** and Freeview demoted.
4. **Steps + action bar.** Convert the five task panels to the step model and the plan strip; delete
   the context panel and `PlanSummary.tsx`. Ship: the forms are compact.
5. **The viewer as an input device.** Point tool for spherical ROI; Regions panel bound to the
   cortical/subcortical selection; electrode picking; free-hand placement. Ship: the thesis.
6. **Absorb the panels.** Source → Project ▸ Assets and Analyse ▸ fsaverage; group methods into
   Analyse ▸ Group; Nilearn into Results ▸ Figures; Notes and System into the dock; delete the
   Panels group and the Settings toggle list.

The one thing that must be decided before step 1 is packaging: Tetravox is an Electron app with its
own privileged `tetravox://` scheme, a per-dataset worker model and a strict path allow-list
(`TVX/docs/ARCHITECTURE.md:1014-1016,1037-1050`, rules 3 and 9). Embedding it means the TI-Toolbox main
process registers that scheme and owns the allow-list, admitting paths that the *server* named (a
`ViewSpec` layer path) as the "user gesture" equivalent — the server already jails those paths
(`WT/tit/server/routes/viewers.py:64-76`, `_jail_viewspec_layers`), so the two allow-lists compose.
Files reach the renderer over `tetravox://file/`, never over `/api/files/artifact`, because the
worker must stream them and IPC copies ArrayBuffers (`TVX/docs/ARCHITECTURE.md:1014-1016`, rule 3).
That is an engineering task, not a design one, but it is the gate.

---

## Part 11 — What is good today and must not be lost

1. **The token set** (`WT/desktop/DESIGN.md:34-57`). Cool-biased neutrals, one accent, semantic
   colour kept separate from the accent, and `--field` orange reserved for TI/mTI semantics and
   never for actions. Keep all of it; add two tokens (§6.3).
2. **The Jobs rail as a signature** (`WT/desktop/DESIGN.md:17-23`;
   `WT/desktop/src/renderer/app/jobs-rail/JobsRail.tsx`). Running work always in view, as animated
   traces rather than a modal progress dialog, is the right answer for a tool whose jobs take hours.
   It becomes the Dock and keeps its collapsed behaviour exactly.
3. **"Anything longer than a request is a job"** (`WT/desktop/DESIGN.md:142-144`) and the whole jobs
   model behind it — queue, group, progress, liveness, waiting-on, console, cancel, rerun, force
   (`WT/contracts/openapi.v1.yaml:960-1183`). This is the strongest part of v3 and it is untouched.
4. **The Plan idea** — telling the truth before Run: resolved outputs, `new`/`overwrite`, lock
   conflicts, cost, and a button labelled from the plan ("Queue 2 jobs"). Only its geometry changes
   (§4.2); the content and the endpoint stay.
5. **Presence chips** (`raw` / `freesurfer` / `m2m` / `dwi` / `ct`, struck through when missing —
   `final-mock/subjects-light.png`). A compact, honest, colour-blind-safe state read-out. Keep, and
   use them on steps as prerequisites (§4.3 rule 7).
6. **Schema-driven forms** — react-hook-form + ajv against the server's own `schema.json`
   (`WT/desktop/src/renderer/forms/ajvResolver.ts`, `GET /api/schema/{name}`), so the client cannot
   drift from the dataclasses. Keep entirely; the step model changes layout, not validation.
7. **Discovery-based registration** (`WT/desktop/src/renderer/app/registry.ts:31-35`: a directory
   with an `index.tsx` *is* a screen). Keep the mechanism, retarget it: an entry now declares an
   activity or a step, not a nav item.
8. **The `ViewSpec` server layer** (`WT/tit/viewspec.py`, `GET /api/view/{kind}`). Its layer list —
   path, kind, colormap, opacity, cal_min/max, lut — maps one-for-one onto Tetravox layers. This was
   built for Freeview and it turns out to be exactly the right server contract for an embedded
   viewer.
9. **Light and dark both real, both screenshotted**, tokens-only in pages, theme applied before
   first paint (`WT/desktop/DESIGN.md:159-164`, and the `*-dark.png` half of every artifact). Keep,
   with dark as the default (§6.3).
10. **The copy discipline** (`WT/desktop/DESIGN.md:156-158`): sentence case, plain verbs, the same
    word for the same thing, no exclamation marks. It shows in the screenshots and it should not be
    touched.

---

## Appendix A — Screens reviewed

Every PNG in `WT/desktop/tests/e2e/artifacts/final-mock/` was viewed. Light/dark pairs exist for:
analyzer (configured, cortical), gallery, help, jobs, optimizer-ex, optimizer-flex (spherical,
cortical, subcortical, non-roi), panel-cluster-permutation, panel-nifti-group-average,
panel-nilearn-visuals, panel-quick-notes, panel-source, panel-subject-info, preprocess, results,
settings, simulator, subjects, system, viewer; plus `unauthenticated.png`.

## Appendix B — Sources read

* `WT/desktop/DESIGN.md` (all 191 lines)
* `WT/desktop/src/renderer/app/`: `Shell.tsx`, `NavRail.tsx`, `TopBar.tsx`, `registry.ts`,
  `keyboard.ts`, `shell.css`, `subjectContext.ts`, `jobs-rail/JobsRail.tsx`
* `WT/desktop/src/renderer/ui/`: `Layout.tsx`, `components.css`, `Combobox.tsx`
* `WT/desktop/src/renderer/pages/`: every `*/index.tsx` PageDef; full reads of `simulator/index.tsx`,
  `viewer/index.tsx`, `_shared/roi/{types.ts,RoiPicker.tsx}`, `panels/_shared.ts`
* `WT/desktop/package.json`
* `WT/dev/notes/v3-build-plan.md` §3 (contract inventory)
* `WT/contracts/openapi.v1.yaml` (path list)
* `WT/tit/server/routes/{viewers.py,capabilities.py}`; `WT/tit/gui/main.py`; `WT/tit/gui/extensions/`
* `TVX/docs/ARCHITECTURE.md` §1, §2, §3, §4.4, §4.5, §4.7, §5, §7.5, §8, §13, §13.1–13.3
