# Interface design

This is the current visual and interaction reference for the desktop and browser interface.
[ARCHITECTURE.md](ARCHITECTURE.md) owns runtime boundaries and lifetime guarantees;
[CONTRIBUTING.md](CONTRIBUTING.md) owns verification commands. Measurements belong in
[BENCHMARKS.md](BENCHMARKS.md), and design history belongs in [DECISIONS.md](DECISIONS.md).
Section numbers remain stable for source and test citations. This reference describes current
behavior; historical programs are not a second specification to reconcile.

## 0. What must not be lost

The interface lets researchers configure safely, monitor expensive computations and reach their
results. Preserve the shared token system, visible jobs rail, server-derived plans, subject readiness,
schema-driven forms, registry-driven navigation and server-resolved viewing paths. Both themes and
keyboard operation are part of the product. Simplification must retain these capabilities.

## 1. Subject, audience, job

TI-Toolbox is a scientific work surface. Use compact, readable controls and stable layouts; give
numbers, units, filenames and scientific scope priority over decoration. Copy uses sentence case,
plain verbs and consistent terms: Run, Stop, Queue, subject, simulation, montage, ROI and job.

## 2. Layouts

Pages use the available content width. A right pane exists for a run, selected result or selected job,
not as an empty decorative column. [`PageLayout`](../../desktop/src/renderer/ui/Layout.tsx) supplies
three shapes:

| Shape | Work area | Secondary area |
|---|---|---|
| Run | Inputs and a bottom action bar | Plan above live Terminal, with Scene where supported |
| Browse | Table, catalog or results tree | Selected item detail or preview |
| Bleed | Canvas or dedicated viewing surface | No additional inspector |

### 2.1 Exact widths

Sizing rules live in [`tokens.css`](../../desktop/src/renderer/ui/tokens.css),
[`pane.css`](../../desktop/src/renderer/ui/pane.css) and
[`paneState.ts`](../../desktop/src/renderer/ui/paneState.ts). Do not reproduce a table of measured
window arithmetic here; pane widths depend on the viewport, active page and stored user preference.

Run panes use a responsive fraction of the window with a work-area floor. Jobs and Results have
purpose-specific initial widths. Resize by drag or keyboard, double-click to reset, collapse to a
rail, or expand over the work area. These operations preserve the hidden pane's state. User widths
persist by page kind; all handles obey the same limits. An unselected Jobs detail pane is absent.

### 2.2 Breakpoints and minimums

The desktop minimum is 1024 × 680. Navigation uses icons below 1440 px and labels above it. Narrow
right panes become drawers; form columns respond to their own container width rather than the outer
window. The form-grid transition is 760 px. Wide tables scroll inside themselves, never across the
whole page. Source: [`shell.css`](../../desktop/src/renderer/app/shell.css) and shared layout styles.

### 2.3 What the shell owns

- The context bar carries command search, connection status and running-job count. Scientific scope
  belongs in page controls; project details belong in Settings.
- The action bar is outside the work scroller. Its primary action remains on the right, with at most
  one secondary action. A blocked primary exposes its reason; a runnable action uses the shared plan
  digest. Controls must never scroll beneath the bar.
- The jobs rail is available throughout the app. Its expanded panel contains Jobs and Host; job
  detail provides the Raw log and artifacts. The Jobs split is resizable and remembered.
- System, Settings and Help are the header-bearing utility pages. Other pages use their navigation
  context instead of repeating a large title.
- There is no separate bottom status bar. Connection status has one home in the context bar.

Sources: [`app/`](../../desktop/src/renderer/app/),
[`jobs-rail/`](../../desktop/src/renderer/app/jobs-rail/), [`Chrome.tsx`](../../desktop/src/renderer/ui/Chrome.tsx).

## 3. Tokens

[`tokens.css`](../../desktop/src/renderer/ui/tokens.css) is the authoritative value roster.
Pages use defined semantic tokens rather than copied colors, dimensions or another library's names.

### 3.1 Colour

The app ground is `--surface`; `--bg` belongs to gutters. Panes use thin rules rather than floating
shadowed cards. Elevation belongs to overlays. Accent denotes actions and selection; success,
warning, danger and lost denote state; `--field` denotes scientific field semantics. Color is always
paired with text, a label or an accessible explanation.

`--ink-3` is for placeholders and disabled states, not normal copy. Solid action fills use their
on-color token. `--canvas` remains dark in both themes so theme changes do not alter the visual
context of anatomical images and field overlays.

### 3.2 Type

Use self-hosted IBM Plex Sans for interface prose and IBM Plex Mono for data, paths, values and logs.
Numbers are tabular. The base is 13/18; labels/help use 12/16. Small uppercase section/chip text may
use 11/14, but normal readable copy has a 12 px floor and must not combine tiny type with muted ink.
The shared type tokens own the remaining scale.

### 3.3 Space, shape, density

Use the 4 px spacing grid and one density. Standard controls, table rows and section headers are
28 px; compact controls are 24 px and workflow primary actions are 32 px. Labels align in the shared
field gutter, number controls carry their unit suffix, and selects/text inputs use their column.
Long values cannot push neighboring controls out of the pane.

### 3.4 Motion and icons

Use shared motion tokens and respect reduced motion. Do not animate page navigation. Lucide icons
have a visible label or accessible name; a tooltip alone is not a replacement for naming an icon
button. Loading preserves button label and width.

## 4. Layout, forms and state

### 4.1 Page layout

Use the shared run/browse/bleed structure rather than page-specific pane systems. Forms and wide
content have their own scrollports; the action bar reserves its height. A preview expansion hides
and inerts alternate content instead of unmounting it.

### 4.2 Forms — nine rules

1. Align labels left in shared field rows; use stacked layout only where the content requires it.
2. Put explanatory help in the field popover and units inside their controls.
3. Tables, coordinate editors, paths, consoles and other wide content span the field row.
4. Use flush `FormSection` groups; their headers are not sticky over editable content.
5. Collapsed sections summarize their values and retain changed/error indicators.
6. Essential scientific choices remain exposed. Advanced non-default settings cannot disappear
   without an indication that they affect the run.
7. Distinguish schema defaults from changed values through the shared changed-field treatment.
8. Keep validation near its field and expose blocked-action reasons. Readiness errors, unresolved
   required inputs and a disconnected server can disable Run; output replacement is decided at commit.
9. Use `SegmentedControl` for a short exclusive choice; use a larger choice control only when its
   labels or descriptions need it. One idea has the same interaction on every page.

Schema validation and server-error mapping remain in [`forms/`](../../desktop/src/renderer/forms/).
Component props and exceptions are the exported types in [`ui/`](../../desktop/src/renderer/ui/).

### 4.3 Tables

Tables use the shared header/row density, semantic hover and selected treatments, and right-aligned
numeric columns. A table retains headers and its own inline empty state when it has no rows.
Filler rows belong to the table component, not page-specific background gradients. Overflow stays
inside the table.

### 4.4 State matrix

| State | Required behavior |
|---|---|
| Initial load | Skeleton or dataset progress sized for the expected content |
| Empty | Inline explanation and relevant next action; retain the table or console shape |
| Load failure | Persistent local error and retry; do not rely on a disappearing toast |
| Refetch | Retain content and indicate refresh without replacing it with a skeleton |
| Disconnected | Preserve editable drafts, show connection state and explain unavailable submission |

Job submission may report success or failure by toast, while the persistent job record remains
available in the rail. A viewport failure retains successfully loaded data where possible.

### 4.4.1 Choosing who takes part: a set, or a list of rows

[`SubjectsField`](../../desktop/src/renderer/pages/_shared/subjects/) selects a set from the project.
[`ParticipantsField`](../../desktop/src/renderer/pages/panels/_participants/) represents repeated
subject/simulation/role rows needed by paired and grouped analyses. Both use the same section,
readiness and reason vocabulary. Participant counts distinguish rows from unique subjects.
CSV/TSV imports validate the whole table before replacing rows; they never partially apply a file.

### 4.4.2 What survives a navigation — the user's state and the derived state

Within a project session, navigation preserves drafts, selections, scrolling, disclosures, pane tabs,
loaded geometry and camera. User-touched disclosure state outranks automatic fill decisions.
Untouched sections may respond to available room. Closing/switching projects disposes this state;
machine preferences such as theme and pane width have their separate persistence.

The retention mechanism and inactive-page constraints are [ARCHITECTURE.md](ARCHITECTURE.md) §2.

### 4.5 Run panel

[`RunPanel`](../../desktop/src/renderer/pages/_shared/run/RunPanel.tsx) places the plan above a live
Terminal and optional Scene tab. The plan is bounded so the terminal retains useful room; computational
extensions use the same arrangement with a concise plan summary when a grid is unnecessary.

The grid and action digest read one [`PlanModel`](../../desktop/src/renderer/pages/_shared/run/planModel.ts).
It shows job count, representative per-job CPU/memory cost, waits, subject/stage cells, output paths
and server warnings. Costs are not multiplied into an invented batch budget. Chip precedence is
`blocked > wait > overwrite > skip > new`; an absent job is distinct from an existing skipped output.
Clicking a plan entry can select its terminal source. See Appendix A for the warning-matching limit.

### 4.6 Terminal

The shared console supplies filtering, follow-tail, level colors, copying and log reveal. Clear is a
local sequence watermark; it never deletes server events or files. Changing sources resets local
line/filter state without discarding the user's follow preference.

Job selection respects an explicit pin, matching active work and jobs started by this page session.
The last completed job started here remains available; unrelated old jobs are not adopted when a
page opens. New submission takes over the page's terminal. The header names the actual job and state.
Sources: [`terminalSources.ts`](../../desktop/src/renderer/pages/_shared/run/terminalSources.ts),
[`JobTerminal.tsx`](../../desktop/src/renderer/pages/_shared/run/JobTerminal.tsx),
[`JobConsole`](../../desktop/src/renderer/ui/Jobs.tsx).

### 4.7 The run-page skeleton, and the four numbers it is held to

Work begins with the subject set or explicit job rows, followed by essential choices and details.
The plan/terminal pane is beside it and the primary action is outside its scroller. Keep essential
controls reachable on the first screen, prevent overlap, avoid horizontal page scrolling and use
space for the task rather than empty chrome. Acceptance assertions live in the layout tests (§12).

#### 4.7.1 The panel pages hold to the same skeleton and the same numbers

Source, Cluster permutation, NIfTI group averaging, Nilearn visuals and visual export keep inputs in
the work area and live output in the right pane. An idle terminal is intentional room for future logs.
Export uses the shared Scene/Terminal controls. Per-page implementations remain under
[`pages/panels/`](../../desktop/src/renderer/pages/panels/).

### 4.8 Selection — one list, everywhere

Use [`SelectionList`](../../desktop/src/renderer/ui/SelectionList.tsx) or its picker wrapper for sets.
Plain click selects one, Shift-click extends a range, modifier-click toggles, modifier-A selects the
filtered set and Escape clears. All/None act only on visible rows; hidden selections remain intact.
Selection order determines submission order. Unusable rows explain why and are excluded from bulk
selection. Single-value fields use the same grammar in single mode.

Existing outputs use [`ExistingOutputsDialog`](../../desktop/src/renderer/pages/_shared/run/ExistingOutputsDialog.tsx):
Skip, Replace and rerun, or Cancel. Replace is disabled until the saved project setting
`allow_unsafe_overrides` is true. Loading or failed settings checks confer no permission. Every
replacement still requires a fresh choice; earlier confirmation and saved defaults do not bypass it.
Where skipping runs only new jobs, the label states the counts. Pipeline Skip and job Rerun Skip
queue nothing and must not promise partial execution. Incomplete pipeline previews cannot enable
Replace. Server enforcement is described in [ARCHITECTURE.md](ARCHITECTURE.md) §10.

### 4.9 Electrodes and channels in the scene pane

Electrode color expresses neutral, unavailable or channel membership. Placed markers use the same
channel palette as the form and legend, without a second selection ring. Labels belong to placed
markers rather than every point on the head. The active channel is identified in the legend, and
marker edits update the form's single source of truth. Coordinate placement requires subject-specific
geometry; a packaged guide selects names, not subject coordinates (§13).

### 4.10 Jobs table

Simulator, Analyzer and Optimizer use one row per job. Each row owns its subject and varying inputs;
identifying fields align in columns while pairs, currents or target descriptions may use a second
line. Rich settings open from the row. Inapplicable cells show a reasoned dash rather than an unusable
choice. Incomplete rows stay visible but are not planned.

Add, duplicate and remove express the batch explicitly; no implicit subject cross-product is added.
Cohort mode uses the same rows and rejects incompatible shared values. Mixed optimizer methods may
produce separate group submissions, which must not be presented as one atomic operation. Submission
keeps the rows. Simulator field mapping is a per-job choice; Source owns forward solutions.

## 5. Components — the only primitives pages may use

[`ui/`](../../desktop/src/renderer/ui/) owns buttons, fields, tables, selection, overlays, feedback,
layout and consoles. Exported TypeScript props are the component reference; duplicating those APIs
in Markdown creates stale instructions. Page families may share domain components in
[`pages/_shared/`](../../desktop/src/renderer/pages/_shared/).

Disabled buttons have a distinct treatment and a reason where needed. Loading retains label/width.
Destructive confirmations name their action. Dialogs, popovers, drawers and tooltips must fit the
viewport and remain keyboard accessible. A page-specific visual variant requires a design decision.

## 6. Interaction rules

Computations become jobs as soon as accepted; the interface never waits for their completion.
Destructive actions require explicit confirmation. Errors state what failed and a usable next step.
Empty states preserve context and offer a relevant action. Copy is concise and consistent.

App shortcuts use Cmd/Ctrl modifiers; unmodified keys belong to the focused control or canvas.
Escape closes the innermost overlay first. The active page alone owns its run shortcut. Navigation,
palette and help derive shortcut assignments from the registry instead of maintaining separate lists.

## 7. Theme

Light is the initial preference. Settings and the command palette provide light, dark and system
choices, persisted and applied before paint. Components resolve semantic tokens in both themes;
canvas ground remains unchanged. Scientific figures retain their authored background rather than
being inverted for dark mode. Source: [theme store](../../desktop/src/renderer/app/theme/store.ts).

## 8. Quality floor per screen

The interface supports the desktop minimum, keyboard-only use, visible focus, readable contrast and
reduced motion. Both themes are checked. Geometry, DOM state and rendering assertions determine
correctness; screenshots supplement review rather than replace assertions.

### 8.1 How a screen is assessed — and why nothing appears on your monitor

Automated GUI tests launch hidden through the shared Electron fixture. A test must not take focus,
show a window or emit native notifications. The native quiet monitor checks process-attributed window
and focus evidence; unavailable or unresolved attribution remains unverified. Procedures and known
limitations belong in [CONTRIBUTING.md](CONTRIBUTING.md) and [BENCHMARKS.md](BENCHMARKS.md).

## 9. Navigation

[`registry.ts`](../../desktop/src/renderer/app/registry.ts) owns page discovery, ordering, gating and
shortcuts. Workflow rows run from Overview through Jobs; System, Settings and Help are pinned utility
entries. Settings keeps Cmd/Ctrl-comma. Optional extensions retain their registered pages rather than
being described as hypothetical folded modes.

The Viewer has Menu and Tetravox subitems inside one retained page. The icon rail omits their labels;
the command palette still exposes both destinations. A subitem does not gain a separate page instance
or workflow digit. Scope selection stays in the page or palette, not in a subject-labeled nav group.

### 9.1 Pipeline

The canvas presents existing job kinds with a palette, typed edges and a plan/terminal pane. Subjects
are supplied through the cohort node. A node keeps its own settings; a binding does not inherit the
producer's whole form. Invalid wires state the missing capability or incompatible port. Run submits
one job group; Save/Load preserve the graph; notebook export uses the public scripting API.

#### 9.1.1 The card is a row, not a poster

Node cards use the app's density and defined tokens, with compact identity, status and summary.
They do not introduce a canvas-specific typography or color vocabulary.

#### 9.1.2 What a node states about itself

Missing inputs appear on the affected node and lead to its editor. Ports show names as well as color;
selection follows the canvas selection model. Flow animation respects reduced motion.

#### 9.1.3 The receipt states the plan, or the blockers — never both as a list

A valid receipt states jobs and dependencies. An invalid one groups blockers by node and offers Fix.
Nonblocking notes remain concise. Classification uses structured issue codes rather than message text.

#### 9.1.4 The empty canvas is one line and a way in

Keep the canvas mounted beneath an empty-state prompt and sample/import actions so palette placement
still works. A sample is editable project input and remains subject to current server validation.

### 9.2 Settings — the Viewer card

The card reports the active bundle, source, compatibility and verified digest. It exposes server-owned
update policy, explicit checks, installation and rollback. Opening Settings does not itself fetch a
remote release index. Project unsafe-override permission is distinct from machine appearance and
execution preferences; changes take effect after saving the project settings.

### 9.3 Notebooks

A notebook list sits beside the document, with cells in one scroller. The toolbar offers execution,
interrupt/restart, output clearing and saving. The kernel pill communicates state and recovery.
Code uses CodeMirror; prose has an editor and rendered view. Completion/signature help comes from
an existing kernel. Editor preferences apply immediately and remain separate from notebook content.
Selected cells use an accent rule; stderr is warning-colored and error outputs are danger-colored.
The architecture and lifecycle contract is [ARCHITECTURE.md](ARCHITECTURE.md) §7.6.

## 10. Viewer

The Viewer is a composition Menu and a dedicated Tetravox view, with one retained iframe behind both.
It does not require installing a second host application. Sources:
[`viewer page`](../../desktop/src/renderer/pages/viewer/index.tsx),
[`Tree.tsx`](../../desktop/src/renderer/pages/viewer/Tree.tsx),
[`TetravoxFrame.tsx`](../../desktop/src/renderer/viewer/TetravoxFrame.tsx).

### 10.1 The Menu

A subject/space tree lists available anatomy, simulations and analyses. Meshes, surfaces, volumes and
attachments retain their distinct server-classified kinds. The tree and editable What will open list
share one selection. Rows show filenames and size; attachments belong to their surface. Subject
changes remove incompatible selections, and the server rejects mixed-subject compositions.

Open is explicit. Selection-only links, presets and recents prepare the Menu. Explicit Open in viewer actions
from results or job artifacts carry load intent and open the selected data. The
server resolves selected files and display defaults; detailed camera/layer controls belong to
Tetravox. Composition saves preserve choices; scene saves preserve the embed's actual serialized view.
A sparse Menu is acceptable when it accurately states the selection.

### 10.2 Tetravox

The embed fills the viewing area with a slim scene/reload strip. It owns layer and camera controls;
TI does not add a second inspector. Layer names match file basenames. Loading reports dataset bytes,
keeps successful layers and distinguishes missing bundle, handshake timeout, unavailable rendering
and dataset failure. These states must remain distinguishable without a log or vanished toast.

### 10.3 Retention, and the one request

Changing subpages preserves the frame and camera. Open resolves the composition once and supplies the
embed and export addressings from that same result. Reload remounts the frame and re-reads changed
files at stable paths. The route owns which subpage is visible; the draft does not silently replace
the displayed scene. The canvas owns unmodified keys while focused.

## 11. Status bar — removed

Connection status belongs in the context bar (§2.3). This number is retained for existing citations.

## 12. The dev loop

Use [CONTRIBUTING.md](CONTRIBUTING.md) for commands and [BENCHMARKS.md](BENCHMARKS.md) for outcomes.
A design edit changes this current reference; it does not append another implementation program.

### 12.1 The instrument

[`_metrics.ts`](../../desktop/tests/e2e/_metrics.ts) measures occupied space, pane dimensions and
first-screen controls. Measurements occur after data loads; a skeleton or large painted background
must not stand in for useful content.

### 12.2 The artifacts

[`screens.spec.ts`](../../desktop/tests/e2e/screens.spec.ts) captures pages in both themes and target
sizes, with metrics beside screenshots. Artifacts are review evidence, not a second specification.

### 12.3 Acceptance numbers per page

Executable thresholds belong to the relevant page/layout tests; captured values belong to
[BENCHMARKS.md](BENCHMARKS.md). Shared invariants are zero horizontal page scroll, zero controls
occluded by the action bar, reachable essential controls and no contentless detail pane. Refer to
[`layout.spec.ts`](../../desktop/tests/e2e/layout.spec.ts) and the page's own suite when changing
geometry rather than copying a historical width or density result.

### 12.4 The self-critique checklist

Check available space, non-overlap, shared tokens, readable units/paths, both themes, keyboard focus,
correct scientific scope, retained state and meaningful errors. Verify existing behavior as well as
the changed interaction. Report actual assertions, skips and limitations.

## 13. Workflow continuity and focused scene previews

Retention follows §4.4.2 and [ARCHITECTURE.md](ARCHITECTURE.md) §§2–3. Hidden pages relinquish commands
and portals; pane collapse preserves drafts and rendering resources. Guide selections name regions
or electrodes, never subject coordinates. Simulator scalp placement uses subject-specific geometry.
One skin-opacity control leaves grey matter opaque, and payload updates preserve the camera unless
the user explicitly reframes. Long dropdowns and interactive canvases remain keyboard accessible.

## Appendix A — contracts shared with tests

### A.1 How a plan cell's chip is derived, and the one place it is a guess

[`planModel.ts`](../../desktop/src/renderer/pages/_shared/run/planModel.ts) owns stage resolution,
counts and chip precedence. Representative cost is per job. The wire plan has prose warnings rather
than a structured per-cell blocked field, so blocked chips depend on warning matching; a changed
warning can alter that preview without changing server admission. This limitation is not permission
to parse other structured errors by message text.

### A.2 The DOM contract the metrics and every spec read

Preserve work/right-pane test IDs, `data-tier="1"`, user-touched disclosure markers and chosen pane
tab markers. Shell `data-page`/`data-subject` identify the active context because browser URL alone
does not describe MemoryRouter navigation. Tests should distinguish user choices from automatic
layout and hidden retained content from the active page.
