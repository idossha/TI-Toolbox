# R2 — v3 desktop renderer map (IA redesign + Tetravox embed)

Reader report. Every claim cites `file:line`. All paths are absolute-relative to the worktree root
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/` (written below as
`<W>/`). Nothing was modified; only read-only commands were run.

---

## 0. Repo state (asked for explicitly)

- `git -C <W> status --short | wc -l` → **73**.
- The **entire `desktop/` tree is untracked** (`?? desktop/` in `git status --short`), as are
  `contracts/`, `tit/server/`, `tit/jobs/`, `tit/catalog.py`, `tit/viewspec.py`,
  `dev/notes/v3-build-plan.md`. 32 tracked files are modified (`tit/*/__main__.py`, `tit/logger.py`,
  `tit/config_io.py`, `tests/*`, `TODO.md`). **There is no committed baseline for the v3 GUI** — an
  IA refactor has no `git diff` safety net until the orchestrator commits.
- `desktop/out` **exists** (2.4 MB: `out/main`, `out/preload`, `out/renderer`) — a stale-or-current
  production build. It is gitignored (`<W>/desktop/.gitignore:2`), as are
  `tests/e2e/artifacts/` (`:5`), `test-results/` (`:7`) and `*.tsbuildinfo` (`:8`).

## 1. Current test / typecheck / lint results (asked for explicitly)

Run: `cd <W>/desktop && npm run typecheck && npm run lint && npx vitest run` (2026-09-02).

| command | exit | result |
|---|---|---|
| `npm run typecheck` (`tsc -p tsconfig.node.json && tsc -p tsconfig.web.json`, `package.json:16`) | **0** | clean, no output |
| `npm run lint` (`eslint .`, `package.json:17`) | **0** | **3 warnings, 0 errors** |
| `npx vitest run` | **0** | **29 test files, 202 tests, all passing, 2.31 s** |

The three lint warnings are all `react-hooks/incompatible-library` ("React Compiler skipped
memoizing this component"), not fixable defects:

- `src/renderer/pages/preprocess/index.tsx:395` — `form.watch()` from react-hook-form.
- `src/renderer/ui/DataTable.tsx:43` — `useReactTable()`.
- `src/renderer/ui/VirtualList.tsx:23` — `useVirtualizer()`.

E2E (`npm run e2e`) was **not** run (it builds and launches Electron; out of scope for a read-only
pass). Its config is `<W>/desktop/playwright.config.ts`.

---

## 2. Directory / ownership map with LOC

`desktop/src` = **29 582 LOC / 182 files**, of which `src/renderer/api/schema.d.ts` is 6 003
generated lines. Non-generated ≈ 23 579.

| path | LOC | files | owner (build plan `dev/notes/v3-build-plan.md:81-96`) | role |
|---|---|---|---|---|
| `src/main/**` | 1 643 | 13 | **P9** (`v3-build-plan.md:94`) | Electron main: lifecycle, launcher, docker, x11, IPC |
| `src/preload/index.ts` | 40 | 1 | **P9** | contextBridge `window.tit` |
| `src/shared/**` | 634 | 5 | **P9** | pure helpers shared main↔renderer (`compose.ts` 212, `paths.ts` 199, `tit-bridge.d.ts` 150, `quitGate.ts` 39, `pullProgress.ts` 34) |
| `src/renderer/app/**` | 1 296 | 15 | **F2** (`v3-build-plan.md:87`) | shell, router, registry, nav, top bar, jobs store+rail, theme, keyboard, `shell.css` (240) |
| `src/renderer/ui/**` | 3 978 | 26 | **F2** | design system; `components.css` **1 437**, `tokens.css` 192, `base.css` 147, `Layout.tsx` 271 |
| `src/renderer/forms/**` | 351 | 6 | **F2** | `/api/schema` loader, Ajv-2020 RHF resolver, `SchemaField`, server-error mapping |
| `src/renderer/api/**` | 6 104 | 2 | **F2** | `client.ts` 101 + generated `schema.d.ts` 6 003 |
| `src/renderer/ws/**` | 191 | 2 | **F2** | `/ws/system` client + hook |
| `src/renderer/dev/Gallery.tsx` | 661 | 1 | **F2** | design gallery |
| `src/renderer/pages/**` | 14 629 | 107 | **P1…P8**, one dir each (`v3-build-plan.md:93`) | screens; 13 256 code + **1 373 LOC of `PARITY.md`** (17 files) |

### `pages/` sub-map (LOC = whole directory incl. PARITY.md)

| dir | LOC | files | lane |
|---|---|---|---|
| `pages/panels/` (6 panels + `_shared.ts` + `PlanSummary.tsx`) | 2 360 | 24 | P8 |
| `pages/optimizer-ex/` | 1 815 | 12 | P4 |
| `pages/preprocess/` | 1 688 | 6 | P1 |
| `pages/simulator/` | 1 631 | 10 | P2 |
| `pages/analyzer/` | 1 479 | 8 | P5 |
| `pages/optimizer-flex/` | 1 119 | 8 | P3 |
| `pages/jobs/` | 1 015 | 7 | P7 |
| **`pages/viewer/`** | **981** | 3 | P6 |
| `pages/results/` | 707 | 3 | P6 |
| `pages/_shared/roi/` | 497 | 4 | P3 (`v3-build-plan.md:59`) |
| `pages/help/` | 480 | 9 | P8 |
| `pages/settings/` | 404 | 3 | P8 |
| `pages/system/` | 289 | 2 | P7 |
| `pages/subjects/` | 126 | 1 | (F2 seed; no lane listed) |
| `pages/dev/` | 22 | 1 | F2 |
| `pages/panel-*/` × 6 | 16 total | 6 | P8 discovery shims |

Panels breakdown: `cluster-permutation` 580, `source` 481, `nilearn-visuals` 367,
`nifti-group-average` 343, `subject-info` 239, `quick-notes` 200.

### Tests

`desktop/tests` = 712 files, of which **~660 are `.png` screenshot artifacts** under
`tests/e2e/artifacts/<run-id>/` (54 run-id directories; the curated ones are `final-mock` 46 PNGs,
`final3` 46, `real` 5). Non-PNG test code = 8 391 LOC:

- `tests/mock-server/server.mjs` **1 445** + `contract.test.ts` 392 + `server.test.ts` 150.
- `tests/fixtures/**` 24 JSON/CSV/HTML/PDF fixtures (largest: `atlas_regions.json` 724).
- `tests/e2e/*.spec.ts` 15 specs (1 966 LOC) + `_helpers.ts` 31 + `fixtures/fake-docker.js` 176.
- `tests/unit/*.test.ts(x)` 27 files (2 573 LOC).

---

## 3. Mechanics: adding / renaming / regrouping pages

### 3.1 Discovery — the registry

`<W>/desktop/src/renderer/app/registry.ts:29`:

```ts
const modules = import.meta.glob("../pages/*/index.tsx", { eager: true })
```

**One level deep only.** A page implemented under `pages/panels/<x>/` is therefore invisible; the
six panels each need a one-line re-export shim at `pages/panel-<x>/index.tsx` — see
`pages/panel-quick-notes/index.tsx:1-6` (the canonical comment) and the five copies
(`pages/panel-source/index.tsx:2`, `panel-cluster-permutation`, `panel-nifti-group-average`,
`panel-nilearn-visuals`, `panel-subject-info`). **The `PageDef.id`, not the directory name, decides
the route** (`panel-quick-notes/index.tsx:4-5`).

`PageDef` (`registry.ts:12-27`): `id`, `title`, `purpose`, `navGroup`, `order`, `icon` (LucideIcon),
`shortcut?` ("1".."9"), `Component`, `enabled`.

Sorting: `pages` is sorted **only by `order`** (`registry.ts:32-34`); `navGroups()` then groups by
`navGroup` **preserving each group's first appearance in that order-sorted list**
(`registry.ts:77-88`). So group ordering is an emergent property of the numeric `order` of each
group's lowest-order page — there is no separate group order list. Changing a group's position
means changing its pages' `order` numbers.

### 3.2 To add a page

1. Create `pages/<id>/index.tsx` default-exporting a `PageDef`. Nothing else changes: routes come
   from `App.tsx:24-34`, nav from `NavRail.tsx:33-56`, shortcut from `keyboard.ts:44`.
2. If the code lives deeper than one level, add the shim (§3.1).
3. Add a nav group label if the `navGroup` is new — **`GROUP_LABEL` in `NavRail.tsx:7-14` is a
   hand-maintained map** (`workspace/pipeline/explore/system/panels/dev`); an unknown group id falls
   back to the raw id (`NavRail.tsx:35`). This is the one file an IA regroup *must* edit.
4. Update the binding table in `DESIGN.md:172-191` ("binding for every PageDef").

### 3.3 To rename a page

- `PageDef.title` is the nav label **and** the `aria-label` on the NavLink (`NavRail.tsx:39`) **and**
  the tooltip (`NavRail.tsx:50`). 21 E2E call sites navigate by exactly that string via
  `page.getByRole("link", { name: "<title>", exact: true })` — see §7.
- `PageDef.id` is the route path (`App.tsx:26` `path={/${page.id}}`) and the redirect target
  (`App.tsx:35`). Renaming an id breaks the six `navigate("/preprocess")`-style cross-page links
  (§3.6) and `pages/panels/_shared.ts:47`'s `id.replace(/^panel-/, "")` contract.
- `PageDef.purpose` is rendered twice per page in practice: once by `NavRail`? no — only by each
  page's own `<PageHeader purpose=…>`, which every page **re-types by hand** rather than reading
  from its own `PageDef` (e.g. `viewer/index.tsx:506` vs `:782`; `results/index.tsx:529` vs `:577`).
  Renaming a purpose means editing two strings per page. (Duplication item, §6.)

### 3.4 Shortcuts

`app/keyboard.ts:30-53`. `Cmd/Ctrl+<key>` where `/^[1-9,]$/` matches, looked up against the
**static** `enabledPages` (`keyboard.ts:44`) — not the live `useEnabledPages()`. `Cmd/Ctrl+J`
toggles the jobs rail (`keyboard.ts:37-41`). Typing targets are excluded (`keyboard.ts:5-8`).
`modKey()` (`keyboard.ts:20-22`) renders "⌘1"/"Ctrl+1" in the rail via `<Kbd>` (`NavRail.tsx:44`).
Current assignments (from each `index.tsx`): 1 subjects, 2 preprocess, 3 simulator,
4 optimizer-flex, 5 optimizer-ex, 6 analyzer, 7 viewer, 8 results, 9 jobs, `,` settings. System,
Help, every panel and Gallery have none.

### 3.5 Enable/disable and the panels mechanism

- Static: `PageDef.enabled` (`registry.ts:26`). `pages/dev/index.tsx:19` uses
  `import.meta.env.DEV || import.meta.env.VITE_INCLUDE_GALLERY === "1"` so a plain build
  **tree-shakes the gallery out** (`pages/dev/index.tsx:13-18`, `README.md:34-51`).
- Live: `useEnabledPages()` (`registry.ts:62-69`) overrides `enabled` for any page whose
  `navGroup === "panels"` from `settings.panels` via the shared React Query cache
  `["settings"]` (`registry.ts:63`, written by `pages/settings/index.tsx:101`
  `queryClient.setQueryData(["settings"], saved)`).
- Synchronous fallback before the first `/api/settings` response: a `localStorage` mirror
  `tit-enabled-panels` (`pages/panels/_shared.ts:22-55`), read at module scope by each panel's
  `enabled: isPanelEnabled("<id>")`.
- `App.tsx:18` routes from the live list, `App.tsx:12` seeds `MemoryRouter.initialEntries` from the
  **static** `enabledPages[0]` (documented at `App.tsx:7-11`).
- Settings still hard-reloads the window when the panel set changes
  (`pages/settings/index.tsx:103-106`), and its copy says so (`:211`).
- **`PANEL_INFO` in `pages/settings/index.tsx:17-24` is a second hand-maintained list of panel
  id/label/description**, duplicating each panel's own `PageDef.title`/`purpose`. A new panel must
  be added in three places (panel dir, shim, `PANEL_INFO`) plus `PanelId` in `_shared.ts:24-30`.

### 3.6 Cross-page navigation already in place

`useNavigate` links: `panels/source/index.tsx:200` → `/preprocess`;
`panels/subject-info/index.tsx:176` → `/preprocess`; `system/index.tsx:163` → `/simulator`;
`simulator/FlexTab.tsx:65` → `/optimizer-flex`; `simulator/index.tsx:136` → `/preprocess`;
`simulator/PlanPanel.tsx:113` → `/results`; `subjects/index.tsx:30` → `/simulator`.
One deep link with query params: `analyzer/ResultsPanel.tsx:68`
`navigate(/results?${params})`, consumed by `results/index.tsx:521-524`
(`useSearchParams`, `tab` + `simulation`, read once as initial state).

---

## 4. The layout system

### 4.1 Shell (flex, **not** CSS grid)

`app/Shell.tsx:53-61` renders:

```
.shell  (flex row, height:100vh, min-height:680px, min-width:1024px)  shell.css:3-10
├── <NavRail/>            .nav-rail  width 220px, flex:none, overflow-y:auto   shell.css:13-23
└── .shell-main           flex:1, column, min-w/h:0                            shell.css:168-174
    ├── <TopBar/>         .top-bar   height 48px, flex:none                     shell.css:115-125
    ├── .shell-content    flex:1, overflow:auto, padding var(--space-6)         shell.css:175-180
    │      └── <Outlet/>  (the page) — or <Unauthenticated/> when 401           Shell.tsx:58
    └── <JobsRail/>       .jobs-rail flex:none, border-top                      shell.css:188-192
```

`.shell-content` is **the only scroller** at ≥1100 px — asserted by a unit test
(`tests/unit/cssRules.test.ts:45-49`).

### 4.2 Nav rail

- 220 px expanded (`shell.css:14`); **64 px, centred, labels+group labels hidden below 1200 px**
  (`shell.css:56-79`, `@media (max-width: 1199px)`).
- Brand: `.nav-brand` wrapper carries `aria-label="TI-Toolbox"`; `.nav-brand-mark` (20 px "TI"
  monogram) shows only collapsed, `.nav-brand-text` only expanded (`NavRail.tsx:27-32`,
  `shell.css:39-79`). **Base rules must precede the media block** — enforced by
  `tests/unit/cssRules.test.ts:61-76` and asserted in the DOM by
  `tests/unit/navBrandMark.test.tsx:45-55`.
- `.nav-item` 13 px/500, active state `[aria-current="page"]` → `--accent-soft`/`--accent`
  (`shell.css:87-109`); shortcut `Kbd` pushed right with `margin-left:auto` (`shell.css:110-112`).

### 4.3 Top bar

`app/TopBar.tsx:41-76`, 48 px. Left: project name from `GET /api/project` with a `Briefcase` icon
(`TopBar.tsx:44-47`) + `sub-<id>` from the zustand subject context (`TopBar.tsx:48`,
`app/subjectContext.ts:13-16` — deliberately not persisted, `:4-5`). Right: connection
`StatusDot` (`data-testid="connection-state"`, `:51`), version string
(`data-testid="server-version"`, `:55`), the `.jobs-indicator` "n running" button that toggles the
rail (`:58`), and a Sign-out button only when unauthenticated (`:61-73`).
**There is no command palette, no global search, no page-level primary action slot in the top bar** —
`cmdk` is a dependency (`package.json:48`) used only by `ui/Combobox.tsx`.

### 4.4 Page layout (the per-page grid)

`ui/Layout.tsx:197-207` `PageLayout({header, children, contextPanel})`:

```
.page-layout        column flex, gap 16, height:100%           components.css:1364-1370
├── header (PageHeader)                                        Layout.tsx:169-190
└── .page-layout-body    row flex, gap 16, flex:1, min-h:0     components.css:1371-1376
    ├── .page-layout-main   flex:1, min-w:0, MAX-WIDTH 960px, overflow:auto   components.css:1377-1382
    └── .page-layout-panel  flex:none, WIDTH 320px, position:sticky, top:0,
                            align-self:flex-start, max-height:100%, overflow:auto  components.css:1383-1391
```

Below **1100 px** (`components.css:1392-1415`) the body stacks (`flex-direction: column`),
`.page-layout` drops `height:100%`, `.page-layout-main` loses both `overflow:auto` and its 960 px
cap, `.page-layout-panel` becomes full-width and static. Guarded by
`tests/unit/cssRules.test.ts:29-49`.

`PageHeader` (`Layout.tsx:169-190` / `components.css:1417-1437`): optional breadcrumb, `h1.text-page-title`,
`p.page-header-purpose`, right-hand `actions` slot.

### 4.5 Jobs rail

`app/jobs-rail/JobsRail.tsx:136-183`. Collapsed **36 px** (`shell.css:193-199`): a horizontally
scrolling `.jobs-rail-traces` of `JobTrace`s plus an expand `IconButton`; empty copy "No jobs
running" (`JobsRail.tsx:142`, styled `shell.css:209-215`). Expanded **280 px**
(`shell.css:216-220`): header + `ResizablePanels` with `JobsTable` left (default 520 px, min 320)
and `JobConsole` right (`JobsRail.tsx:166-179`). A finished job lingers 4 s
(`JobsRail.tsx:47`). Toggled by `Cmd/Ctrl+J` (`Shell.tsx:46`, `keyboard.ts:37`) or the top-bar
indicator (`Shell.tsx:57`).

### 4.6 Responsive breakpoints (complete list)

| px | effect | cite |
|---|---|---|
| min window 1024 × 680 | `.shell` min-width/min-height; `BrowserWindow` minWidth/minHeight | `shell.css:5-6`, `main/index.ts:330-331` |
| ≤ 1199 | nav rail 220→64, labels hidden, monogram shown | `shell.css:56-79` |
| ≤ 1099 | context panel stacks under content; main stops scrolling and un-caps | `components.css:1392-1415` |
| ≤ 899 | `.shell-content` padding 24→16 | `shell.css:181-185` |
| container ≤ 560 | `.form-grid` collapses to one column (CSS container query) | `components.css:850, 880` |

`DESIGN.md:94-95` states the intent ("below 1200 nav collapses; below 1100 the panel stacks; forms
single-column below 900") — note the form collapse is implemented as a **container** query at
560 px, not a 900 px media query.

### 4.7 Design-system primitives (`ui/index.ts:6-27` — "the only primitives pages may use")

| module | exports (props, abbreviated) |
|---|---|
| `Button.tsx` (63) | `Button` (`variant` primary/secondary/ghost/destructive, `size` sm/md/lg, `loading`, `icon`, + button attrs, `:7-19`), `IconButton` (`icon` + **required** `aria-label`, `:41-51`) |
| `Status.tsx` (118) | `StatusDot{kind,pulse,title}`, `Chip{kind,dot,pulse,missing,title}`, `Badge{count,neutral}`, `Progress{value,label,indeterminate}`, `LivenessBadge{state,stalledFor}`, `JobStateChip{state,pulse}`; `SemanticKind` = neutral/accent/success/warning/danger/field/lost (`:4`), `JobState` 7-member union (`:98`) |
| `Field.tsx` (69) | `Field{label,htmlFor,required,help,error,helpSlot}` (`:4-13`), `TextInput{invalid}`, `Textarea{invalid}`, `describedBy()` |
| `NumberInput.tsx` (38) | `{value:number\|undefined, onValueChange, unit, step, min, max, invalid}` (`:4-13`) |
| `Select.tsx` (58) | `{value,onValueChange,options:SelectOption[],placeholder,disabled,invalid,id,aria-describedby}` (`:11-20`) |
| `Combobox.tsx` (158) | `Combobox{value,onValueChange,options,placeholder,searchPlaceholder,emptyMessage,loading,disabled,id}` (`:12-22`), `MultiSelect{values,onValuesChange,options,placeholder,disabled,id}` (`:79-86`) |
| `Toggle.tsx` (168) | `Switch{checked,onCheckedChange,disabled,id,aria-label}`, `Checkbox{…,label}`, `RadioGroup{value,onValueChange,options,layout,name}`, `Slider{value,onValueChange,min,max,step,unit,showNumberInput,disabled,aria-label}` |
| `PathInput.tsx` (49) | `{value,onValueChange,placeholder,disabled,invalid,id,onBrowse?}` — `onBrowse` is the Electron host picker; omitted ⇒ plain text (`:12-17`) |
| `SubjectPicker.tsx` (44) | `{subjects: SubjectPickerItem[{id,chips:{label,on}[]}], selected, onSelectedChange}` |
| `CoordinateInput.tsx` (57) | `{value:Coordinate{x,y,z,radius?}, onValueChange, space, onSpaceChange, withRadius, disabled}` |
| `KeyValueTable.tsx` (76) | `{rows:KeyValueRow[], onRowsChange, keyPlaceholder, valuePlaceholder, addLabel, disabled}` |
| `ElectrodePairsEditor.tsx` (105) | `{mode,onModeChange,electrodes,pairs,onPairsChange,freehandPairs,onFreehandPairsChange,disabled}` |
| `Layout.tsx` (271) | `Stack{gap:Space,align}`, `Cluster{gap,align,wrap,justify}`, `KeyValue{label,value,mono}`, `Card`, `CardHeader{title,actions}`, `CardBody`, `Tabs{items:TabItem[],value,onValueChange,defaultValue}`, `FormSection{title,helpSlot,advanced}`, `PageHeader{title,purpose,breadcrumb,actions}`, `PageLayout{header,children,contextPanel}`, `ResizablePanels{left,right,defaultLeftWidth=320,minLeftWidth=200,maxLeftWidth=560}` |
| `PlanSummary.tsx` (120) | `{loading,error,idleMessage,jobs,cpus,memoryGb,outputs,waits,warnings,className}` (`:28-51`) |
| `Overlay.tsx` (165) | `Dialog{open,onOpenChange,title,description,footer,trigger}`, `AlertDialog{…,confirmLabel,onConfirm,confirmVariant,cancelLabel}`, `Drawer{open,onOpenChange,title,side="right"}`, `Popover{trigger,open,onOpenChange}`, `Tooltip{label}` (400 ms) |
| `Toast.tsx` (48) | `ToastHost` (mounted once at `App.tsx:21`), `notify.{success,error,info}` |
| `Feedback.tsx` (75) | `EmptyState{icon,message,actionLabel,onAction}`, `Skeleton{width,height}`, `Callout{kind info/warning/danger,title}`, `Kbd`, `DefinitionList{entries:[string,ReactNode][]}` |
| `VirtualList.tsx` (65) | `<T>{items,rowHeight,renderRow,className,style,followTail}` (TanStack Virtual) |
| `DataTable.tsx` (112) | `<T>{data,columns:DataTableColumn<T>[],getRowId,selectable,selected,onSelectedChange,emptyMessage,onRowClick}` (TanStack Table) |
| `Chart.tsx` (133) | `LineChart{timestamps,values,label,unit,height,color}` (uPlot), `Sparkline{values,color,height,width}` |
| `Jobs.tsx` (154) | `JobTrace{job:JobSummary,onClick,finishing}`, `JobsTable{jobs,onOpen}`, `JobConsole{lines:JobLogLine[],onRevealLogFile}`, `ArtifactList{artifacts:ArtifactItem[],onOpen,onView,onReveal}` |
| `utils.ts` (29) | `cn`, `nextId`, `bytes`, `pct` |

**There is no canvas/WebGL/3D primitive, no full-bleed page container, and no split-view primitive
other than `ResizablePanels`.** `Drawer` (`Overlay.tsx:95-125`) is the only right-side overlay.

### 4.8 Tokens and theme

`ui/tokens.css` (192): light on bare `:root` (`:11-116`), dark redefined twice — under
`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` (`:118-155`) and under
`:root[data-theme="dark"]` (`:157-192`). Stacking tokens `--z-overlay 80 / --z-dialog 90 /
--z-popover 100 / --z-tooltip 110 / --z-toast 120` (`:111-115`). `initTheme()` stamps
`<html data-theme>` before first render (`main.tsx:15`, `app/theme/store.ts:47-49`); persisted in
`localStorage["tit-theme"]` (`store.ts:10`). Contrast is unit-tested
(`tests/unit/tokenContrast.test.ts`, 139 LOC).

---

## 5. Per-page inventory

Legend: **Plan?** = has a `contextPanel` Plan panel. LOC = whole page directory.

| id | title (nav label) | group / order / ⌘ | purpose | sections rendered, in order | API routes called | LOC | tests |
|---|---|---|---|---|---|---|---|
| `subjects` | Subjects | workspace / 1 / ⌘1 | Browse subjects and their simulations. | `PageLayout` → `DataTable` (`data-testid="subjects-table"`, `subjects/index.tsx:98`); contextPanel = "Simulations · <id>" Card (`:22-24`, `:90`). No Plan. | `GET /api/catalog/subjects`, `GET /api/catalog/simulations` (via `api/client.ts:78,82`) | 126 | `e2e/smoke.spec.ts` (70-76), `e2e/gallery.spec.ts:86-89` |
| `preprocess` | Pre-processing | pipeline / 10 / ⌘2 | Convert, segment, and prepare subjects for simulation. | Subjects (`:481`) · Processing steps (`:541`) · DWI processing (Docker) (`:603`) · Existing outputs (`:674`) · Run settings (`:691`); **Plan panel** (`:462-472`, internal `PlanPanel` at `:229`) | `/api/catalog/subjects/{id}`, `/api/validate/pre`, `/api/plan/pre`, `POST /api/jobs/groups` | 1 688 | `e2e/preprocess.spec.ts` (144), `unit/preprocess-defaults.test.ts` (190) |
| `simulator` | Simulator | pipeline / 20 / ⌘3 | Configure and run TI / mTI simulations. | Subjects card (`:127`) · Montage source card with 3 tabs Montage/Flex-search/Free-hand (`:144-153`) · "Selected jobs (n)" (`:160`); **Plan panel** (`:123`, `PlanPanel.tsx:130-155`) | `/api/catalog/eeg-nets`, `/montages` (+PUT/DELETE), `/freehand` (+PUT), `/flex-runs`, `/simulations`, `/subjects/{id}`, `/api/validate/sim`, `/api/plan/sim`, `POST /api/jobs` | 1 631 | `e2e/simulator.spec.ts` (158), `unit/simulator-defaults.test.ts` (140) |
| `optimizer-flex` | Optimizer · Flex-search | pipeline / 30 / ⌘4 | Search electrode placement for a target ROI with differential evolution. | Subjects (`:226`) · Electrode parameters (`ElectrodeParams.tsx:19`) · ROI definition (`:300`, uses `pages/_shared/roi`) · Focality options (`FocalityOptions.tsx:49`) · HyperParams · Automatic simulations (optional) (`:318`); **Plan panel** (`:211-224`) | `/api/catalog/eeg-nets`, `/api/validate/{kind}`, `/api/plan/{kind}`, `POST /api/jobs`, `/api/view/{kind}`, `POST /api/viewers/freeview` | 1 119 | `e2e/optimizer-flex.spec.ts` (146), `unit/optimizer-flex.test.ts` (137) |
| `optimizer-ex` | Optimizer · Ex/mEx-search | pipeline / 40 / ⌘5 | Search exhaustive electrode montages for TI or mTI stimulation. | Subject and leadfield card (`:60`) · Leadfield panel · Tabs Ex / mEx / Results (`:99-129`); each form: Electrode selection · ROI selection · Current configuration (`ExForm.tsx:192,221,241`) / mTI configuration (`MExForm.tsx:230`); **Plan panel published upward** via `setPlanPanel` state (`index.tsx:20,56`; `ExForm.tsx:183`) | `/api/catalog/{eeg-nets,leadfields,rois,rois/{name},atlases,atlases/regions,ex-runs,ex-runs/{run}/results}`, `/api/plan/{kind}`, `POST /api/jobs` | 1 815 | `e2e/optimizer-ex.spec.ts` (129), `unit/optimizer-ex-defaults.test.ts` (101) |
| `analyzer` | Analyzer | pipeline / 50 / ⌘6 | Extract field statistics from an ROI in one or more simulation results. | Subject and simulation (`AnalyzerPage.tsx:353`) · Analysis configuration (`:429`, spheres via `SphereRows.tsx`) · Results panel (`ResultsPanel.tsx:115`); **Plan panel** (`:294-300`) | `/api/catalog/{simulations,atlases,atlases/regions,analyses,analyses/{name}/summary}`, `/api/validate/{kind}`, `/api/plan/{kind}`, `POST /api/jobs`, `/api/view/{kind}`, `POST /api/viewers/{freeview,gmsh}` | 1 479 | `e2e/analyzer.spec.ts` (223), `unit/analyzer-defaults.test.ts` (209) |
| **`viewer`** | **Viewer** | **explore / 60 / ⌘7** | Launch Freeview or Gmsh on subject, simulation and analysis outputs. | **main column:** Source (`:635`) · Field & overlays (`:678`, sim/analysis only) · Electrode overlay (`:702`, sim/analysis only) · Layers (`:751`, N × `LayerRow` + "Additional NIfTI" `PathInput` + Add layer). **contextPanel (`:507-633`):** "X server required" Callout (`:510`) · **Freeview command** card (`:515`: `<pre>` argv, Copy command, Refresh, Open in Freeview, `JobConsole` for the active viewer job at `:589`) · **Gmsh** card (`:597`: mesh Combobox + Open in Gmsh + state chip). No Plan panel. | `/api/view/{kind}`, `POST /api/viewers/freeview`, `POST /api/viewers/gmsh`, `POST /api/jobs` (kind `tools`, `api.ts:100-110`), `POST /api/jobs/{id}/cancel`, `/api/catalog/{simulations,analyses,atlases,subjects/{id},electrode-overlays}`, `/api/capabilities`, `/api/catalog/subjects` | **981** (`index.tsx` **791**, `api.ts` 111, `PARITY.md` 79) | `e2e/viewer.spec.ts` (102) — **no unit test** |
| `results` | Results | explore / 70 / ⌘8 | Browse simulation, optimization and analysis outputs. | Subject card (`:530`) · Tabs Simulations / Flex runs / Ex-search-mEx-search runs / Analyses / Group (`:553-566`). Each tab = `ResizablePanels` list→detail: report `<iframe sandbox="allow-scripts">` (`:223-243`, forced `colorScheme:"light"`), Artifacts `ArtifactList`, manifest `DefinitionList`, `DataTable`, PDF `<embed>` (`:468`). No Plan panel. | `/api/catalog/{simulations,flex-runs,ex-runs,ex-runs/{run}/results,analyses,analyses/{name}/summary,reports,group}`, `/api/view/custom`, `POST /api/viewers/{freeview,gmsh}`, `/api/files/artifact`, `/api/files/report/{id}` | 707 | `e2e/results.spec.ts` (100) |
| `jobs` | Jobs | system / 80 / ⌘9 | Every job the server has run or is running, with live progress and controls. | Tabs All jobs (filter Card + `DataTable` `data-testid="jobs-table"`, `:140-179`) / Groups (`GroupsView.tsx`) + `JobDetailDrawer` (`:188`, 374 LOC, own `Tabs` at `JobDetailDrawer.tsx:208`). Dev-only "Submit test job" header action (`:131-136`). | `/api/jobs`, `/api/jobs/{id}`, `/events`, `/log`, `/cancel`, `/rerun`, `/force`, `/api/catalog/subjects`, `/api/project`, `/api/settings` | 1 015 | `e2e/jobs.spec.ts` (149), `unit/jobStateChip.test.tsx` (56) |
| `system` | System | system / 85 / — | Host CPU, memory and toolbox processes, live. | CPU card (`:119`) · Memory card (`:128`) · Running jobs (`:156`) · Processes (`:203`) | `WS /ws/system`, `GET /api/jobs?state=running`, `POST /api/system/terminate` (`:32`) | 289 | `e2e/system.spec.ts` (97), `e2e/smoke.spec.ts:78-84`, `unit/{systemStream,useSystemStream,chart-collecting}` |
| `settings` | Settings | system / 90 / ⌘, | Project, appearance, telemetry, and optional panels for this install. | Project (`:150`) · Appearance (`:178`) · Telemetry (`:187`) · **Feature panels** (`:209`, drives the nav) · Advanced (`:233`) · About the server (`:272`) | `GET/PUT /api/settings`, `/api/project`, `/api/version`, `/api/capabilities` | 404 | `e2e/settings.spec.ts` (86), `unit/settings-warm-cache.test.tsx` (103) |
| `help` | Help | system / 95 / — | Documentation, citation, acknowledgments, and contact. | Tabs Docs / About / Cite / Acknowledgments / Contact (`help/index.tsx:15-19`) | `/api/version`; `/docs` iframe (mock stub in `server.mjs`) | 480 | `e2e/help.spec.ts` (87), `e2e/smoke.spec.ts:46-47` |
| `panel-source` | Source | panels / 100 / — | Build EEG forward solutions and map simulation fields to fsaverage. | Subjects (`:195`) · Build forward solution (`:210`) · Map fields to fsaverage (`:231`); Plan via `panels/PlanSummary.tsx` (`:78`) | `/api/catalog/{subjects/{id},simulations}`, `/api/validate/source`, `/api/plan/source`, `POST /api/jobs` | 481 | `e2e/panels-forms.spec.ts` (170), `unit/source-defaults.test.ts` (55) |
| `panel-cluster-permutation` | Cluster permutation | panels / 105 / — | Compare or correlate field intensities across subjects with permutation testing. | Subjects (`:222`) · Analysis (`:262`) · Advanced (`:307`) · Plan (`:360`) | `/api/catalog/simulations`, `/api/validate/stats`, `/api/plan/stats`, `POST /api/jobs` | 580 | `e2e/panels-forms.spec.ts`, `unit/cluster-permutation-defaults.test.ts` (82) |
| `panel-nifti-group-average` | NIfTI group averaging | panels / 110 / — | Compute group averages and differences of NIfTI files. | Subjects (`:133`) · Analysis configuration (`:156`) · Plan (`:184`) | `/api/catalog/simulations`, `/api/validate/nifti_average`, `/api/plan/nifti_average`, `POST /api/jobs` | 343 | `e2e/panels-forms.spec.ts`, `unit/nifti-group-average-defaults.test.ts` (51) |
| `panel-nilearn-visuals` | Nilearn visuals | panels / 120 / — | Create Nilearn high-resolution publication visualizations. | Subjects · Output (`:169`) · Visualization parameters (`:178`) · Plan (`:213`) | `/api/catalog/simulations`, `/api/validate/nilearn`, `/api/plan/nilearn`, `POST /api/jobs` | 367 | `e2e/panels-forms.spec.ts`, `unit/nilearn-visuals-defaults.test.ts` (51) |
| `panel-quick-notes` | Quick notes | panels / 130 / — | A running notepad for this project. | one Card + textarea | `GET/PUT /api/catalog/notes` | 200 | `e2e/panels.spec.ts` (98) |
| `panel-subject-info` | Subject info | panels / 140 / — | Processing-stage presence for every subject in the project. | select + presence matrix (`:89,112,122`) | `/api/catalog/subject-info` | 239 | `e2e/panels.spec.ts` |
| `dev` | Gallery | dev / 999 / — | Every design-system primitive, every state. | Sections: Buttons (`Gallery.tsx:149`) · Status (`:188`) · Form fields (`:246`) · Containers (`:375`) · Feedback (`:488`) · Data (`:524`) · Layout (`:560`) · PlanSummary (`:594`) · Jobs (`:629`) | none | 661 + 22 | `e2e/gallery.spec.ts` (90) |

`PARITY.md` exists for 17 of these (all but `subjects` and `dev`): `find src -name PARITY.md`.

---

## 6. Cross-page duplication a compaction should factor

Ranked by payoff.

1. **Per-page `api.ts` files re-declare the same catalog wrappers.**
   `getSimulationsFor` appears **7×**: `panels/source/api.ts:28`, `panels/nilearn-visuals/api.ts:22`,
   `panels/cluster-permutation/api.ts:13`, `panels/nifti-group-average/api.ts:25`,
   `results/api.ts:20`, `viewer/api.ts:56`, `simulator/api.ts:76`.
   `getSubjectDetail` **4×** (`panels/source/api.ts:24`, `preprocess/api.ts:28`, `viewer/api.ts:68`,
   `simulator/api.ts:34`). `launchFreeview` **3×** (`viewer/api.ts:44`, `results/api.ts:62`,
   `optimizer-flex/api.ts:64`); `launchGmsh` **2×**; `cancelJob` **2×** (`viewer/api.ts:52`,
   `jobs/api.ts:73`); `artifactUrl` **3×** (`results/api.ts:72`, `jobs/api.ts:103`,
   `analyzer/api.ts:216`); `getAtlases` **3×** (`viewer/api.ts:64`, `_shared/roi/api.ts:13`,
   `analyzer/api.ts:44`); `getAnalyses` **3×**. Every one carries the same apology comment about
   file ownership (`viewer/api.ts:1-7`, `results/api.ts:1-5`) — the cause is the build plan's
   one-directory-per-lane rule, not a design decision. **A shared `api/catalog.ts` is the single
   biggest compaction available (~300 LOC removed).**

2. **Two ROI pickers.** `pages/_shared/roi/RoiPicker.tsx` (327 LOC, P3-owned, spherical/cortical/
   subcortical) and `pages/optimizer-ex/roi/RoiPicker.tsx` (271 LOC), which openly says it is a
   *"local stand-in for the shared ROI picker the v3 build plan assigns to `pages/_shared/roi/`"*
   and that the swap "should only touch this file and its two callers (`ExForm`, `MExForm`)"
   (`optimizer-ex/roi/RoiPicker.tsx:1-12`). Plus `analyzer/SphereRows.tsx` (172) is a third,
   narrower sphere editor.

3. **Two Plan-panel vocabularies.** `ui/PlanSummary.tsx` (120, the F2 primitive: Jobs · CPUs ·
   Memory · Outputs · Waits) is used by `preprocess`, `simulator`, `optimizer-flex`,
   `optimizer-ex`, `analyzer`; `pages/panels/PlanSummary.tsx` (95) is a **parallel implementation**
   for the four panel pages, explicitly kept local only because `ui/**` belongs to another lane
   (`panels/PlanSummary.tsx:1-8`). Each page then wraps one of them in its own `PlanPanel.tsx`
   (`simulator/PlanPanel.tsx` 193, `optimizer-ex/PlanPanel.tsx` 133, `optimizer-flex/PlanPanel.tsx`
   91, `preprocess/index.tsx:229`, `analyzer/AnalyzerPage.tsx:296`) — five near-identical
   Card+`PlanSummary`+Run-button shells.

4. **`useDebounced` copy-pasted verbatim 3×** — `panels/source/index.tsx:35-42`,
   `panels/nilearn-visuals/index.tsx:37-44`, `panels/cluster-permutation/index.tsx:36-43`
   (identical bodies; 350/350/400 ms). The same "stringify config → debounce → validate → plan"
   pipeline is re-typed in all four panels (`source:62-73`, `nilearn:92-104`,
   `cluster-permutation:164-176`, `nifti-group-average:94-102`).

5. **"Subjects" card + `SubjectPicker` repeated 6×** with hand-built select-all/clear rows:
   `preprocess/index.tsx:481-540`, `simulator/index.tsx:127-142`, `optimizer-flex/index.tsx:226-245`,
   `analyzer/AnalyzerPage.tsx:394`, `panels/source/index.tsx:195-200`, plus row-based variants in
   `cluster-permutation:222` / `nifti-group-average:133`. No `SubjectSection` primitive exists.

6. **`purpose` typed twice per page** — once in the `PageDef`, once in the page's own `PageHeader`
   (e.g. `viewer/index.tsx:506` vs `:782`, `results/index.tsx:529` vs `:577`, `jobs/index.tsx:129`
   vs `:201`). Three pages have already drifted: `simulator` (`PageDef` "Configure and run TI / mTI
   simulations." `:255` vs header "…from montages, flex-search results, or free-hand electrode
   placements." `:122`), `optimizer-ex` (`:141` vs `:53`), `optimizer-flex` header matches. A
   `PageLayout` that reads the active `PageDef` would delete this class of bug.

7. **Inline flex/gap styles survive despite `Stack`/`Cluster`.** `Layout.tsx:19-24` says the
   primitives replaced "50+ call sites", but `style={{ display: "flex", flexDirection: "column",
   gap: "var(--space-N)" }}` is still written by hand in `viewer/index.tsx:508,715,758`,
   `results/index.tsx:206,284,333,360,409,435,489`, `jobs/index.tsx:148`,
   `settings/index.tsx:215`, `panels/PlanSummary.tsx:29`, etc.

8. **Panel registration is a 4-place edit**: panel dir, `pages/panel-<x>/index.tsx` shim,
   `PanelId` union (`panels/_shared.ts:24-30`), `PANEL_INFO` (`settings/index.tsx:17-24`).

9. **Freeview/Gmsh launching is implemented on three pages** — `viewer` (the real UI),
   `results` (`useOpenInFreeview`/`useOpenInGmsh`, `results/index.tsx:71-85`, used from Artifacts
   rows and the Analyses tab), and `analyzer` (`analyzer/api.ts:200,210` +
   `analyzer/ResultsPanel.tsx:71,77` and its two buttons at `:196,208`). Their toasts even point at
   each other: *"Opened in Freeview — see the Viewer page for the console."*
   (`results/index.tsx:74`). **Any Tetravox migration must touch all three, not just `pages/viewer`.**

---

## 7. Constraints an IA change must respect

**A. E2E navigates by nav label text.** 21 call sites use
`page.getByRole("link", { name: "<PageDef.title>", exact: true })`. Exact strings currently
asserted: `Gallery` (`gallery.spec.ts:65`), `Subjects` (`:86`), `Analyzer` (`analyzer.spec.ts:54`),
`Jobs` (`jobs.spec.ts:38`), `Optimizer · Ex/mEx-search` (`optimizer-ex.spec.ts:32`), `Help`
(`help.spec.ts:50,84`; `smoke.spec.ts:46`), `Settings` (`help.spec.ts:82`, `panels.spec.ts:40`,
`panels-forms.spec.ts:60`, `settings.spec.ts:32`), `Source` (`panels-forms.spec.ts:75,113`),
`NIfTI group averaging` (`:120,132`), `Nilearn visuals` (`:139,151`; `settings.spec.ts:52,79`),
`Cluster permutation` (`:158,167`), `Quick notes` (`panels.spec.ts:57,72,79`; `settings.spec.ts:81`),
`Subject info` (`panels.spec.ts:86,92`; `settings.spec.ts:82`), `Pre-processing`
(`preprocess.spec.ts:42`), `Optimizer · Flex-search` (`optimizer-flex.spec.ts:32`), `Simulator`
(`simulator.spec.ts:32`), `Results` (`results.spec.ts:31`), `System` (`system.spec.ts:35`;
`smoke.spec.ts:78`), `Viewer` (`viewer.spec.ts:33`). Note the **middle dot `·`** in the two
optimizer titles — a rename that changes the separator breaks two specs.

**B. Every page heading is asserted.** `expect(page.getByRole("heading", { name: "<title>" }))`
follows almost every nav click (e.g. `viewer.spec.ts:34`, `analyzer.spec.ts:55`,
`gallery.spec.ts:66` asserts `"Design gallery"`, not `"Gallery"`). Title and `PageHeader` title must
stay in lockstep.

**C. Shortcuts are asserted.** `smoke.spec.ts:106-127`: `⌘8`→Results, `⌘9`→Jobs, `⌘1`→Subjects,
`⌘J`→`.jobs-rail-expanded` count 1/0. Reassigning any of 1/8/9 breaks this spec.

**D. Structural test-ids that must survive.** `subjects-table` (`subjects/index.tsx:98`; asserted in
**every** e2e `beforeEach` as the "app is up" signal — `smoke.spec.ts:42,70`, `viewer.spec.ts:29`,
`analyzer.spec.ts:51`, `gallery.spec.ts:33`, …). Also `connection-state` and `server-version`
(`TopBar.tsx:51,55`), `jobs-table` (`jobs/index.tsx:167`), `viewer-active-job`
(`viewer/index.tsx:577`), `ws-status`/`cpu-value`/`mem-value` (`system/index.tsx:119,128`),
`simulations-list`, `analysis-summary-table` (`results/index.tsx:458`).
**Moving Subjects out of the default landing position would break every e2e spec**, because
`App.tsx:12` lands on `enabledPages[0]` (lowest `order` = Subjects, `order: 1`) and every spec waits
on `subjects-table` right after connect.

**E. CSS structure is unit-asserted.** `tests/unit/cssRules.test.ts` asserts, as *text*, the
existence and source-order of `.page-layout`/`.page-layout-main` rules inside
`@media (max-width: 1099px)` (`:29-49`), `.nav-brand-mark`/`.nav-brand-text` inside
`@media (max-width: 1199px)` and that their base rules precede it (`:52-77`), and
`.select-trigger:disabled` (`:79-89`). Renaming `.page-layout*`, `.nav-brand*` or `.shell-content`
fails `npx vitest run`. `tests/unit/navBrandMark.test.tsx:45-55` additionally asserts the DOM shape
of `.nav-brand` (its `aria-label`, both spans, `aria-hidden` on the mark) and **mocks
`app/registry`'s `useNavGroups`** (`:14-21`) — changing that export's name or shape breaks it.

**F. Gallery gating.** `pages/dev/index.tsx:19` (`import.meta.env.DEV ||
VITE_INCLUDE_GALLERY === "1"`) + `package.json:19` `pree2e` (`cross-env VITE_INCLUDE_GALLERY=1
electron-vite build`) + `README.md:34-51` (electron-vite hardcodes `NODE_ENV=production`, so
`--mode` cannot be used). `gallery.spec.ts:70-73` asserts a real Switch toggle by accessible name
`"Combine ROIs"`, and `:46-58` injects a stylesheet overriding
`html, body, #root, .shell, .shell-main, .shell-content` heights and `.jobs-rail` position so
`fullPage` screenshots work — **that helper hard-codes the shell class names**.

**G. Panel gating in tests.** `panels-forms.spec.ts:33-45` routes `**/api/settings` to enable all
six panels and `:44` seeds `localStorage["tit-enabled-panels"]`; `settings.spec.ts:52,79-82`
asserts panel links appear/disappear from the nav. Any change to the `panel-` id prefix convention
(`registry.ts:47`, `_shared.ts:53`) breaks both.

**H. Design contract.** `DESIGN.md:172-191` §9 is labelled *"binding for every PageDef"* and carries
the group/order/shortcut table **and** the `GROUP_LABEL` mapping; `DESIGN.md:77-103` §4 fixes the
220/64 px rail, 48 px top bar, 960 px column, 320 px sticky panel, 36/280 px rail and the
1200/1100/900 breakpoints. `DESIGN.md:166-170` §8 requires "one Playwright screenshot per screen in
both themes at 1280 wide". An IA change should update §9 and §4 in the same pass.

**I. 17 `PARITY.md` files** (1 373 LOC) map each screen back to its PyQt source
(`tit/gui/<tab>.py`) and carry numbered "known gaps" that other documents reference. They are
per-directory, so **regrouping/merging pages orphans or splits them**; `viewer/PARITY.md:32-79`
and `results/PARITY.md:21-43` cross-reference each other (`viewer/PARITY.md:79`: *"Reveal is
Results-page scope"*).

**J. Mock-server + fixtures.** `tests/mock-server/server.mjs` (1 445) implements the full v1
contract and is contract-tested (`contract.test.ts` 392). Per-run isolation: `playwright.config.ts:11`
`PORT = TIT_MOCK_PORT ?? 8790 + (process.pid % 500)`; `:18` `process.env.TIT_E2E_RUN_ID ??=
String(process.pid)` — written onto `process.env`, not a local const, so the workers Playwright
forks inherit one id (`:12-17` documents the bug this fixed); `:22`
`TIT_E2E_ARTIFACTS ??= tests/e2e/artifacts/<RUN>`; `:29` `outputDir: test-results/<RUN>`; `workers: 1`
(`:27`). Every spec reads `process.env.TIT_E2E_ARTIFACTS` with a fallback to
`tests/e2e/artifacts` (e.g. `viewer.spec.ts:11`) and `mkdirSync(ARTIFACTS, {recursive:true})` in
`beforeAll`. A real server is used instead when `TIT_E2E_SERVER_URL` is exported
(`playwright.config.ts:9,30`), in which case no webServer is started.

**K. Bridge surface is asserted exactly.** `smoke.spec.ts:87-101` asserts
`Object.keys(window.tit).sort()` equals the 12-entry list. **Adding any `window.tit` method for
Tetravox fails that assertion** unless the list is updated (and `src/shared/tit-bridge.d.ts:11-46`
documents the numbering as a maintained invariant).

---

## 8. Where a Tetravox pane can physically live

### 8.1 What the shell permits today

`.shell` is a **flex row**, not a CSS grid (`shell.css:3-10`); `.shell-main` is a flex column
(`:168-174`) whose middle child `.shell-content` is `flex:1; overflow:auto; padding:24px`
(`:175-180`). A page is rendered straight into `.shell-content` via `<Outlet/>` (`Shell.tsx:58`).
There is **no full-bleed escape hatch**: every page inherits the 24 px padding and, if it uses
`PageLayout`, a 960 px content cap (`components.css:1380`).

### 8.2 Option A — a **full-bleed viewer page** (recommended primary)

A `PageDef` whose component does *not* use `PageLayout` renders directly into `.shell-content` and
already gets `height:100%` from `flex:1` — but it must defeat the padding. Two clean routes:

- Add a `.page-full` class (or a `PageLayout` `variant="full"`) that sets
  `margin: calc(var(--space-6) * -1)` / `height: 100%`, mirroring the negative-margin trick;
  **or** add `.shell-content:has(> .page-full) { padding: 0 }`.
- Canvas rectangle available, unpadded: at the **1280 × 900** e2e viewport, 1280 − 220 (rail) =
  **1060 wide** and 900 − 48 (top bar) − 36 (collapsed rail) = **816 high**. At the **1024 × 680**
  minimum (`shell.css:5-6`, `main/index.ts:330-331`) the nav rail is already collapsed to 64 px
  (≤1199 px), so 1024 − 64 = **960 wide** × 596 high. With `.shell-content`'s 24 px padding left in
  place, subtract 48 from each dimension (16 px padding below 899 px, `shell.css:181-185`).
- Cost: `cssRules.test.ts:45-49` asserts `.shell-content { overflow: auto }` textually — adding
  rules is fine, changing that declaration is not. The gallery helper's height override
  (`gallery.spec.ts:46-58`) also names `.shell-content`.

### 8.3 Option B — the **existing 320 px context panel** (cheapest, weakest)

`PageLayout contextPanel` is 320 px wide, sticky, `overflow:auto`, and **stacks below 1100 px**
(`components.css:1383-1414`). Fine for a thumbnail/orientation cube; far too narrow for a real
volume viewer, and the stacking rule would drop the canvas below the fold on a small window.

### 8.4 Option C — **split view via `ResizablePanels`** (recommended for "form left, viewer right")

`ui/Layout.tsx:210-271` already gives a draggable divider with keyboard support
(`:261-264`), `height:100%`, `min-height:0` (`components.css:1087-1095`).
**Default `maxLeftWidth` is 560 px** (`Layout.tsx:215`) — for a viewer-right layout you want the
*form* on the left, so the defaults fit as-is (`defaultLeftWidth=320`). Precedent: `results`
uses it for every list→detail tab (`results/index.tsx:179,271,347,422`) and `JobsRail` uses it at
520/320 (`JobsRail.tsx:166-168`). The right pane is `flex:1` with `overflow:auto`
(`Layout.tsx:266`) — a WebGL canvas would want `overflow:hidden` and a `ResizeObserver`; that is a
one-line CSS addition, not a rewrite.

### 8.5 Option D — **right `Drawer`** (for a peek-at-this-artifact affordance)

`ui/Overlay.tsx:95-125` (`side="right"`), z-index `--z-dialog: 90` (`tokens.css:112`). Already used
by `pages/jobs/JobDetailDrawer.tsx`. Good for "preview this NIfTI from the Results artifact list"
without leaving the page; unsuitable as the primary viewer (modal, no persistent state).

### 8.6 Hard technical constraints on any embed

- **CSP / origin.** The renderer is served by `tit.server` at `/`; every URL is origin-relative
  (`README.md:3-7`, `api/client.ts:1-5`). A Tetravox bundle must ship *inside* this bundle (an npm
  workspace / vendored `@tetravox/engine`), not be fetched from another origin.
- **Navigation guard.** `main/index.ts:345-355` allows only `app://launcher` and `serverOrigin`;
  `:356-371` `setWindowOpenHandler` allows a same-origin child window only. A `tetravox://`
  privileged scheme like the standalone app's (`tetravox docs/ARCHITECTURE.md` §5) would have to be
  registered here (`main/index.ts:34-36` already registers `app` via
  `protocol.registerSchemesAsPrivileged`) **and** added to both guards — a P9-owned change.
- **Permissions.** `main/index.ts:524` denies **every** permission request
  (`setPermissionRequestHandler(… callback(false))`). WebGL2 does not go through that API, but any
  future capability (fullscreen, pointer-lock, file-system) would be denied by default.
- **Sandbox.** `sandbox:true`, `contextIsolation:true`, `nodeIntegration:false`
  (`main/index.ts:334-340`). A Rust→WASM worker is fine (no Node APIs), but it must be loaded from
  the bundle; `new Worker(new URL(...))` under `base: "./"` (`electron.vite.config.ts:20`) needs a
  Vite worker entry — the current renderer config has **no worker configuration**
  (`electron.vite.config.ts:18-52`).
- **Code splitting.** `electron.vite.config.ts:41-48` manual chunks only `react`, `radix`,
  `tanstack`, `uplot`. A Tetravox engine + WASM blob should get its own chunk and, ideally, be
  lazy-imported so a user who never opens the viewer does not download it. The comment at
  `:33-40` explains why the function form (not the object shorthand) is required — follow it.
- **Data path.** Server-side paths are **container** paths (`/mnt/000/...`,
  `shared/paths.ts:1-13`). Tetravox must load bytes over HTTP, and the only jailed byte routes today
  are `GET /api/files/artifact?path=` and `GET /api/files/report/{id}` (`results/api.ts:72-78`);
  `viewer/api.ts` has none. `ernie.msh` is 847 k nodes — expect to need a ranged/streamed artifact
  route rather than a single `fetch`. Tetravox's worker protocol already accepts
  `LoadSource {kind:'url'|'file'|'bytes'}` (`tetravox docs/ARCHITECTURE.md` §6.5), so `kind:'url'`
  pointing at `/api/files/artifact?path=…` (cookie sent automatically on same-origin —
  `results/api.ts:70-71`) is the natural binding.
- **Theme.** Tetravox chrome must read the same tokens (`tokens.css`) or be given explicit
  light/dark props; `data-theme` is stamped on `<html>` (`theme/store.ts:22-26`), so a CSS-var-based
  engine palette works with no JS wiring.
- **The 12-key bridge assertion** (`smoke.spec.ts:88-101`) must be updated if any new
  `window.tit` method is added.

### 8.7 What the current Viewer page would become

If Tetravox replaces Freeview + Gmsh, the following disappear or move:

- **Delete from `pages/viewer/index.tsx`:** the entire `contextPanel` (`:507-633`) — the "X server
  required" Callout (`:510`), the Freeview-command `<pre>`/Copy/Refresh/Open block (`:515-595`) and
  the Gmsh card (`:596-631`); the `freeviewDisabledReason`/`gmshDisabledReason` capability gating
  (`:426-438`); `launchMutation`/`gmshMutation`/`stopMutation` (`:443-469`); the viewer-job
  `JobConsole` (`:589`).
- **Keep and re-target:** `GET /api/view/{kind}` and the whole layer model. `ViewSpec.layers` →
  `EditableLayer` (`:99-154`) with colormap/opacity/visible/cal_min/cal_max/percentile/lut is
  exactly a Tetravox scene description; `viewspec.py` (539 LOC server-side) already resolves
  percentiles and LUTs. `ViewSpec.freeview_args` becomes dead payload
  (`viewer/index.tsx:440-449` already notes the client never trusts it).
- **Keep unchanged:** Source (`:635`), Field & overlays (`:678`), Electrode overlay (`:702`, a
  `tools` job, unrelated to the viewer binary), the Layers editor (`:751`).
- **Also touch:** `results/index.tsx:71-85` (`useOpenInFreeview`/`useOpenInGmsh`, used at
  `:132,442,447`) and `analyzer/api.ts:200,210` + `analyzer/ResultsPanel.tsx:196,208` — three
  pages, not one (§6.9).
- **Server-side:** `tit/server/routes/viewers.py` (241 LOC) and `main/x11.ts` (200) +
  `main/index.ts:308-316` (the X11 revert on quit) become dead once no X11 viewer remains;
  `/api/capabilities.{freeview,gmsh,x11_display}` loses its consumers.
- **Tests to rewrite:** `tests/e2e/viewer.spec.ts` in full (both tests are Freeview-specific:
  `:54-77` asserts the "X server required" Callout and a disabled "Open in Freeview";
  `:79-102` routes `**/api/capabilities` to `x11_display:true` and asserts a viewer job runs and
  cancels). `results.spec.ts` may assert the Freeview toasts — check before changing.

---

## 9. Build / tooling facts an IA change needs

- Scripts (`package.json:12-23`): `dev` (electron-vite dev), `build`, `typecheck` (two tsconfigs),
  `lint`, `test` (vitest), `pree2e` (`VITE_INCLUDE_GALLERY=1 electron-vite build`), `e2e`
  (playwright), `mock-server`, `gen:api` (`openapi-typescript ../contracts/openapi.v1.json -o
  src/renderer/api/schema.d.ts`).
- `electron.vite.config.ts`: renderer `base: "./"` (`:20`), React + Tailwind 4 plugins (`:21`), dev
  proxy for `/api`, `/auth`, `/ws` to `TIT_DEV_SERVER_URL ?? http://127.0.0.1:8765` (`:7,22-29`),
  manual vendor chunks (`:41-48`); preload forced to CJS, nothing externalized (`:13-17`).
- `vitest.config.ts:5-6`: includes only `tests/unit/**` and `tests/mock-server/**`,
  `environment: "node"` (per-file `// @vitest-environment jsdom` opt-in, e.g.
  `navBrandMark.test.tsx:1`).
- `eslint.config.mjs:7`: ignores `out/`, `dist/`, `node_modules/`, `playwright-report/`,
  `test-results/`, `src/renderer/api/schema.d.ts`; `react-hooks` recommended rules apply to
  `src/renderer/**` (`:11-14`).
- Deps of note (`package.json:24-59`): React 18.3, react-router-dom **7.18**, @tanstack/react-query
  5.102 + react-table 8.21 + react-virtual 3.14, 15 Radix packages, ajv 8.20, cmdk 1.1,
  lucide-react 1.34, openapi-fetch 0.17, sonner 2.0, uplot 1.6, zustand 5.0, tailwind-merge 3.6.
  Dev: electron 44.0.0 (pinned), electron-vite 5, vite 7.3, vitest 4.1, playwright 1.62,
  typescript 5.9, jsdom 29, ws 8.21.
- Main-process modules: `index.ts` 559 (IPC handlers at `:426-499`, window at `:321-385`, quit gate
  at `:288-319`, `app://launcher` protocol at `:514-521`), `stack.ts` 247 (docker compose lifecycle),
  `x11.ts` 200, `dockerCli.ts` 189, `launcher.ts` 128 (inline HTML/JS launcher page with its own
  CSP, `:11`), `jobsNotifier.ts` 71 (native notification on job completion via a main-process
  `/ws/jobs` socket), `stackState.ts` 69, `health.ts` 36, `settings.ts` 37, `userConfig.ts` 30,
  `hostInfo.ts` 30, `log.ts` 27, `port.ts` 20.

---

## 10. Open questions for the IA/Tetravox planner

1. Does Tetravox ship as an npm workspace inside this repo, a git submodule, or a vendored build?
   Nothing in `desktop/package.json` references it today.
2. Is the byte transport `GET /api/files/artifact?path=` (needs range support for an 847 k-node
   `.msh`), a new `/api/files/volume` route, or a `tetravox://` privileged scheme reading the
   container mount? The latter requires P9 changes in `main/index.ts:34-36,345-371`.
3. Does the Viewer stay one page, or split into "Scene" (the layer form) and a full-bleed canvas
   with the form in a `ResizablePanels` left pane? The latter needs no new primitive.
4. Should `results`' Artifacts rows open Tetravox inline (a `Drawer`) or deep-link to `/viewer`
   with query params, the way `analyzer/ResultsPanel.tsx:68` already deep-links to `/results`?
5. Who owns the compaction of §6 items 1–3 (shared catalog client, single ROI picker, single
   PlanSummary)? They cross the build plan's per-lane directory ownership
   (`v3-build-plan.md:81-96`), which is what created them.
