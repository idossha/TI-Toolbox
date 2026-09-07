# U0 design notes — measurements, contracts, open questions

> Historical, except §3. Kept only because `docs/dev/DESIGN.md` §5 defers to §3
> for the verbatim TypeScript contract signatures instead of restating them.
> Everything else here is superseded by `docs/dev/DESIGN.md` and by
> `docs/dev/HISTORY.md` § 2026-09-03 — UI program.

Companion to `docs/dev/DESIGN.md` v3 and `docs/dev/wireframes.md`. §3 is the part the
build lanes code against **verbatim**.

---

## 1. What I measured on the current build

Run `u0-32124` (`TIT_E2E_RUN_ID=u0-32124 bash scripts/e2e-quiet-check.sh npx playwright test
tests/e2e/{gallery,preprocess,results,viewer,jobs}.spec.ts`, exit 0, quiet), artifacts in
`desktop/tests/e2e/artifacts/u0-32124/`, screenshots 1280 × 900.

The DOM instrument (§3.8) does not exist yet, so these are a **cell-occupancy pixel proxy** of the
same quantity: the content box is divided into 16 × 16 px cells, a cell counts as content if any
pixel in it differs from the page ground by more than 6/255 in any channel, and dead = empty cells /
all cells. It reads the same phenomenon the DOM metric reads and is systematically *optimistic*
about content (a pane's own border or background tint marks a cell as content), so the real numbers
are no better than these.

| page | light | dark | what the space is |
|---|---|---|---|
| `jobs` | **91.9 %** | 92.0 % | one job row, then 690 px of empty table, plus a 360 px pane holding "Select a job to see its detail" |
| `subjects` | **88.0 %** | 88.0 % | three rows of table, then 600 px of nothing; a 300 px card whose whole content is a centred empty state |
| `results` | **86.3 %** | 66.8 % | a page header, a subject dropdown in a full-width card, a 320 px column right of the preview that holds nothing |
| `preprocess` | **74.0 %** | 73.6 % | the screenshot the program was written against: a 300 px Plan card whose content ends at y ≈ 545, and 295 px of unused column below it |
| `simulator` | **66.7 %** | 66.6 % | four stacked cards inside an 880 px cap; Plan card ends at y ≈ 400 |
| `viewer` | **15.7 %** | 15.7 % | the only page already close — the canvas is content — but 240 px of it is an inspector duplicating the embed's panels |

Three defects the pictures show that no ratio captures, and that U1–U10 name:

- **The status bar prints `RAS — Space — Renderer —` on Jobs, Subjects, Results and Pre-processing** —
  three cells about a canvas that is not mounted (U8).
- **The context bar's presence chips collide with "+ Add subjects"** in `results-light.png`
  (the chips overlap the button's label at x ≈ 440). A top rail is carrying a table's data (U6).
- **Subjects, Simulator and Results still render a page header** (title + purpose, 86 px), which
  DESIGN.md v2 §2 already forbade.

### 1.1 The sampling snippet B1 lifts into `tests/e2e/_metrics.ts`

This is the DOM metric — the one the acceptance numbers are stated against. It replaces the pixel
proxy above; do not ship the proxy.

```ts
export interface DeadSpace {
  ratio: number; samples: number; dead: number;
  rect: { x: number; y: number; width: number; height: number };
}

/**
 * Fraction of a 16 px grid over `selector` whose topmost element is not content (DESIGN.md §12.1).
 * The <25%-of-rect clause on background-colour is load-bearing: without it a page could paint one
 * giant surface and score zero.
 */
export async function deadSpaceRatio(page: Page, selector = '[data-testid="shell-content"]', step = 16): Promise<DeadSpace> {
  return page.evaluate(
    ({ selector, step }) => {
      const root = document.querySelector(selector);
      if (!root) throw new Error(`deadSpaceRatio: no element for ${selector}`);
      const r = root.getBoundingClientRect();
      const rectArea = r.width * r.height;
      const TAGS = new Set(["CANVAS", "IFRAME", "IMG", "SVG", "VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"]);

      const isContent = (el: Element | null): boolean => {
        if (!el || !root.contains(el)) return false;
        if (TAGS.has(el.tagName)) return true;
        if (el.childElementCount === 0 && (el.textContent ?? "").trim() !== "") return true;
        const cs = getComputedStyle(el);
        const bg = cs.backgroundColor;
        const transparent = bg === "transparent" || /rgba\(\s*0,\s*0,\s*0,\s*0\s*\)/.test(bg);
        if (!transparent) {
          const b = el.getBoundingClientRect();
          if (b.width * b.height < rectArea * 0.25) return true;   // a chip, a tile, a table header
        }
        if (cs.backgroundImage !== "none") return true;
        return false;
      };

      let samples = 0, dead = 0;
      for (let y = r.top + 8; y < r.bottom - 1; y += step) {
        for (let x = r.left + 8; x < r.right - 1; x += step) {
          samples++;
          if (!isContent(document.elementFromPoint(x, y))) dead++;
        }
      }
      return { ratio: samples ? dead / samples : 0, samples, dead,
               rect: { x: r.x, y: r.y, width: r.width, height: r.height } };
    },
    { selector, step },
  );
}
```

Two things B1 must not skip: the metric is taken **after** `page.waitForFunction` on the page's own
loaded marker (a skeleton is content and would flatter the number), and it is taken with the work
pane scrolled to the top, because `elementFromPoint` reads the viewport.

---

## 2. What I kept from v2 (and from the two research proposals)

**Kept whole, unchanged:** the token set and every colour in §3 (contrast-verified by
`tests/unit/tokenContrast.test.ts`); the type scale and the 12 px floor; the 4 px space grid and
every `--control-h` / `--row-h` / `--section-header-h` number; the eight form rules (§4.2) including
label-left 28 px rows, help-as-popover, sections-not-cards, the three disclosure tiers, changed-value
marking and inline validation with Run always enabled; the table rules (§4.3); the state matrix
(§4.4) with one row rewritten from "inspector block" to "right pane block"; every component in §5;
the interaction rules (§6); the offscreen doctrine and the "judge numbers, not pictures" section
(§8.1); the guardrail list (§0).

**Kept from `d-density-first.md`:** R1–R5 and R7 verbatim (they are already §4.2); R6's split —
Plan panel keeps the *content*, the action bar keeps the *button*; the collapsed-section value
summary; §6.2's removal list for Simulator (the Subjects card, the Selected-jobs table, the Global
parameters card, the tab-container card).

**Kept from `d-workflow-first.md`:** the coverage strip and the presence-dot columns on Subjects
(§4.1 there); the Optimize merge with Method as a segmented control and the Ex/mEx precondition
strip (§4.4); the SEARCH-COST numbers promoted out of the plan into a permanent tile (they become
the fifth stats tile, §4 of the wireframes); Analyzer's Scope segment and the deletion of its own
subject `Select` (§4.5).

**Deliberately not taken:** the Workbench stage-card page (a ninth nav entry the program's flat rail
has no room for); presets in the action bar (an addition, and U1–U10 are all removals); the
`WebContentsView` viewer embedding decision (`d-workflow-first.md` §4.6) — that is B5's and the
spike's call, not a layout question; "Open externally" and the Freeview/Gmsh menu (removed by D3).

---

## 3. Contracts

Every symbol below is what a lane writes and what another lane imports. They are **additive**: the
"must keep working" list under each is the v2 surface that stays exported and behaves unchanged.

### 3.1 `PlanModel` — `desktop/src/renderer/pages/_shared/run/planModel.ts` (B2)

Pure, no React, no fetch. Unit-testable against `tests/fixtures/` without a browser.

```ts
export type PlanKind = "pre" | "sim" | "flex" | "ex" | "mex" | "analyzer";
export type PlanChip = "new" | "skip" | "overwrite" | "blocked" | "wait";

export interface PlanStats {
  jobs: number;        // PlanResult.jobs.length
  cpus: number;        // PlanResult.cost.cpus     — PER JOB (see note)
  memoryGb: number;    // PlanResult.cost.mem_gb   — PER JOB
  waits: number;       // PlanResult.lock_conflicts.length
}
export interface PlanStage { id: string; label: string }
export interface PlanCell {
  stageId: string;
  chip: PlanChip | null;   // null = this stage is not part of this subject's run → renders "·"
  outputDir: string;       // PlanJob.output_dir, for the tooltip
  jobIndex: number | null; // index into PlanResult.jobs, for pinning the terminal
}
export interface SubjectPlan { subject: string; cells: PlanCell[] }

export interface PlanModel {
  kind: PlanKind;
  stats: PlanStats;
  stages: PlanStage[];
  subjects: SubjectPlan[];
  warnings: string[];            // PlanResult.warnings, verbatim
  /** Non-null when nothing can be planned. The digest and the disabled primary's tooltip use it
   *  verbatim — e.g. "Select at least one montage." Never a silent disabled button. */
  blockedReason: string | null;
}

export function planModelFrom(
  kind: PlanKind,
  result: PlanResult,                 // components["schemas"]["PlanResult"], unchanged
  subjectIds: string[],               // the page's current selection, in display order
  opts?: { blockedReason?: string | null },
): PlanModel;

export function planDigest(plan: PlanModel): string;
export function chipFor(
  job: PlanJob, conflicts: LockConflict[], warnings: string[], stageId: string,
): PlanChip;
```

**Mapping from `POST /api/plan/{kind}`** (`tit/server/routes/plan.py`, models at lines 119–145; the
server does not change):

| model field | server field |
|---|---|
| `stats.jobs` | `PlanResult.jobs.length` |
| `stats.cpus` / `stats.memoryGb` | `PlanResult.cost.cpus` / `.mem_gb` |
| `stats.waits` | `PlanResult.lock_conflicts.length` |
| `subjects[].subject` | `PlanJob.subject` (grouped, in `subjectIds` order; a subject with no job still gets a row of `·`) |
| `cells[].outputDir` | `PlanJob.output_dir` |
| `warnings` | `PlanResult.warnings` |

**Stage id, in precedence order** (`stageIdOf(result, i)`):
1. `result.resolved.stages[i].tags[0]` — `kind = "pre"` only; `_plan_pre` appends to `jobs` and to
   `resolved.stages` in the same loop (plan.py ≈ 590–606), so index `i` is aligned by construction.
   Assert the lengths match and fall through if they do not.
2. `result.resolved.stages[i].label`.
3. `basename(job.output_dir)` — `sim` (the montage), `flex` / `ex` / `mex` / `analyzer` (the run
   name). One column per distinct value, in first-seen order.

**Chip precedence: `blocked` > `wait` > `overwrite` > `skip` > `new`.**
- `wait` — some `lock_conflicts[]` entry has `subject === job.subject`.
- `overwrite` — `job.exists && job.will_overwrite`.
- `skip` — `job.exists && !job.will_overwrite`.
- `new` — `!job.exists`.
- `blocked` — a `warnings[]` entry containing both the subject id and the stage id, matched
  case-insensitively on word boundaries. There is **no server field for this** (open question Q3).

**`planDigest`:**
```
`${jobs} job${jobs === 1 ? "" : "s"} · ${cpus} CPU · ${memoryGb} GB`
  + (overwrites ? ` · ${overwrites} overwrite` : "")
  + (waits      ? ` · ${waits} wait`           : "")
```
and, when `plan.blockedReason` is non-null, the reason string alone.

**Note on cost.** `_plan_cost` returns *one representative job's* cost, "not summed across a
multi-job plan" (plan.py docstring). The tiles therefore read per-job and carry the `title`
attribute `"per job"`. Do not multiply — the sum is not what the server measured.

### 3.2 `RunPanel` — `pages/_shared/run/RunPanel.tsx` (B2)

```tsx
export interface RunPanelProps {
  kind: PlanKind;
  plan: PlanModel | null;      // null while the page has nothing to plan
  loading?: boolean;
  error?: ReactNode;
  onRefetch?: () => void;
  /** Subjects the page has selected, for the terminal's job filter and the empty state. */
  subjects: string[];
  /** Extra kinds whose jobs this page's terminal may follow (Optimizer: ["flex","ex","mex"]). */
  jobKinds?: PlanKind[];
  onRevealLogFile?: (jobId: string) => void;
  /** Clicking a plan row pins the terminal; the page owns the state so ⌘K can clear it. */
  pinnedJobId?: string | null;
  onPinJob?: (jobId: string | null) => void;
}
export function RunPanel(props: RunPanelProps): JSX.Element;
```
Renders `<PlanGrid>` over `<JobTerminal>`; sets `data-testid="run-panel"`, and the container carries
`data-testid="page-right-pane"` from `PageLayout`, not from here.

### 3.3 `PlanGrid` — `pages/_shared/run/PlanGrid.tsx` (B2)

```tsx
export interface PlanGridProps {
  plan: PlanModel | null;
  loading?: boolean;
  error?: ReactNode;
  onRefetch?: () => void;
  /** Number of skeleton rows on first load — pass the selected-subject count so the panel does
   *  not resize when the data lands. */
  skeletonRows?: number;
  emptyMessage?: string;          // default "Select a subject to see the plan."
  onEmptyAction?: () => void;     // ghost "Choose subject ⌘P"
  onSelectRow?: (subject: string, cell: PlanCell) => void;
}
export function PlanGrid(props: PlanGridProps): JSX.Element;
export const PLAN_CHIP_KIND: Record<PlanChip, ChipKind>;  // new→success, skip→neutral,
                                                          // overwrite→warning, blocked→danger,
                                                          // wait→accent
```
Testids: `plan-grid`, `plan-stat-<jobs|cpus|mem|waits>`, `plan-cell-<subject>-<stageId>` (its text
is the chip word, which is what a spec asserts), `plan-legend`, `plan-warnings`.

### 3.4 `JobTerminal` — `pages/_shared/run/JobTerminal.tsx` (B2)

```tsx
export interface JobTerminalProps {
  /** Kinds this terminal may follow, most specific first. */
  kinds: PlanKind[];
  /** Current subject selection; used by resolution rule 2 (DESIGN.md §4.6). */
  subjects: string[];
  pinnedJobId?: string | null;
  onPinJob?: (jobId: string | null) => void;
  onRevealLogFile?: (jobId: string) => void;
  emptyMessage?: string;   // default "No run yet for this page."
  emptyHint?: string;      // default `${label(kinds)} jobs appear here.`
}
export function JobTerminal(props: JobTerminalProps): JSX.Element;

/** Pure, exported for unit tests — rules 1–4 of DESIGN.md §4.6. */
export function resolveFollowedJob(
  jobs: JobSummary[], kinds: PlanKind[], subjects: string[], pinnedJobId?: string | null,
): JobSummary | null;
```
Wraps the existing `JobConsole` (`ui/Jobs.tsx`) unchanged — virtualisation, filter, follow-tail,
level classes and `onRevealLogFile` are already there; `JobTerminal` adds the 24 px identity header
and the resolution. Testids: `job-terminal`, `job-terminal-identity`, `job-terminal-empty`.

### 3.5 `useStatusCells` / `StatusCell` — `app/statusCells.ts` (B1)

```ts
export interface StatusCellSpec {
  id: string;                       // unique within the page
  label?: string;                   // omitted for self-describing values
  value: ReactNode | null | undefined;   // null/undefined/"" → the cell is NOT rendered
  priority: number;                 // ascending, left to right; 10/20/30 by convention
  title?: string;                   // tooltip
  tone?: "default" | "warning" | "danger";
  mono?: boolean;                   // tabular mono, e.g. RAS
}

/** Registers `cells` for as long as the calling component is mounted. Unregisters on unmount, so
 *  a stale cell from a page you left is impossible. Safe with an inline array literal: the store
 *  compares a stable serialisation of {id,label,priority,tone,mono} + String(value). */
export function useStatusCells(cells: StatusCellSpec[]): void;
```
`AppStatusBar` renders the registered cells sorted by `priority`, then the shell's fixed right
cluster (connection, `tit x.y · api vN`). It gains no page knowledge and **loses its
`viewerStatus` import** — the Viewer registers `ras` / `space` / `renderer` itself.

**Must keep working:** `StatusBar` and `StatusCell` in `ui/Chrome.tsx` (props `label`, `end`,
`title`, `children`) — `StatusCell` is still the renderer; only who decides *which* cells exist
changes.

### 3.6 `PageLayout` v3 — `ui/Layout.tsx` (B1)

```tsx
export type PageLayoutVariant = "run" | "browse" | "bleed" | "standard" | "full-bleed";
export type RightPaneKind = "run" | "preview" | "none";

export interface PageLayoutProps {
  children: ReactNode;
  variant?: PageLayoutVariant;               // default "run"
  rightPane?: ReactNode;                     // not rendered when undefined/null (U1)
  rightPaneKind?: RightPaneKind;             // default "run" for variant run, "preview" for browse
  rightPaneWidth?: number;                   // default 360 (<1440) / 400 (≥1440); "preview" uses
                                             //   clamp(380, 40% of content, 560)
  rightPaneCollapsible?: boolean;            // default true when rightPaneKind === "run" (⌘⇧I)
  rightPaneDefaultCollapsed?: boolean;
  onRightPaneWidthChange?: (width: number) => void;
  rightPaneMinWidth?: number;                // default 320
  rightPaneMaxWidth?: number;                // default 560
  actionBar?: ReactNode;
  showHeader?: boolean; title?: string; purpose?: string; headerActions?: ReactNode; header?: ReactNode;
  className?: string;
}
```
Required DOM contract, because the metrics read it: `data-testid="page-work"` on the work pane,
`data-testid="page-right-pane"` on the right pane (**absent from the DOM entirely** when there is no
right pane, so `paneWidths().right === 0`), and `data-tier="1"` on the always-open sections of a run
page so `firstScreenControls` can find them.

**Must keep working, unchanged:** `variant="standard"` (→ `run`, no cap) and `"full-bleed"`
(→ `bleed`); `inspector` and `contextPanel` (→ `rightPane`); `inspectorWidth` (→ `rightPaneWidth`,
default 300 when it is the prop used); `onInspectorResize`, `inspectorMinWidth`,
`inspectorMaxWidth`, `resizableInspector`; `actionBar`, `showHeader`, `title`, `purpose`,
`headerActions`, `header`, `className`. Also still exported from this module: `Stack`, `Cluster`,
`KeyValue`, `Card`, `CardHeader`, `CardBody`, `Tabs`, `FormSection`, `PageHeader`,
`ResizablePanels`.

### 3.7 Results outputs tree — `pages/results/outputsTree.ts` (B4)

```ts
export type OutputKind = "simulation" | "flex" | "ex" | "mex" | "analysis" | "report";

export type PreviewRef =
  | { type: "report";    reportId: string }                                             // getReports
  | { type: "analysis";  subject: string; simulation: string; name: string }            // getAnalysisSummary
  | { type: "exRun";     subject: string; run: string; kind: "ex" | "mex" }             // getExRunResults
  | { type: "artifacts"; artifacts: Artifact[] };                                       // flex runs, fallback

export interface OutputNode {
  id: string;                 // `${kind}:${subject}:${name}` — stable across refetches
  kind: OutputKind;
  label: string;
  badges: string[];           // "TI" | "mTI" | "flex" | "ex" | "mex" | "analysis" | "report"
  path: string;               // absolute container path, mono, truncated from the left
  created?: string;           // ISO; the 1440 CREATED column
  preview: PreviewRef;
  children?: OutputNode[];    // analyses hang under their simulation
}
export interface OutputGroup { kind: OutputKind | "group"; label: string; count: number; nodes: OutputNode[] }
export interface SubjectOutputs { subject: string; total: number; groups: OutputGroup[] }

export function outputsTreeFor(subject: string, data: {
  simulations: SimulationDetail[];   // GET /api/catalog/simulations?subject=
  flexRuns: FlexRun[];               // GET /api/catalog/flex-runs?subject=
  exRuns: ExRun[]; mexRuns: ExRun[]; // GET /api/catalog/ex-runs?subject=&kind=ex|mex
  analyses: Record<string, Analysis[]>;  // keyed by simulation name
  reports: Report[];                 // GET /api/catalog/reports?subject=
}): SubjectOutputs;

/** The left column: every subject with its output count. `GET /api/catalog/subjects` for the ids
 *  (`id`, `n_simulations`), the per-subject queries for the rest; "Group" is a pseudo-subject
 *  built from `GET /api/catalog/group`. */
export function subjectOutputCounts(...): { subject: string; total: number }[];
```

Field-by-field, from `tit/catalog.py` and `desktop/tests/fixtures/`:

| node | fields used |
|---|---|
| simulation | `name`, `has_ti` → badge `TI`, `has_mti` → badge `mTI`, `fields[]`, `path`, `report_ids[]` → the preview when one exists, else `artifacts` from `niftis[]` + `meshes[]` |
| flex run | `name`, `goal`, `created`, `path`, `artifacts[] {path, kind, label}` |
| ex / mex run | `name`, `path`, preview `{type:"exRun"}` (`getExRunResults` returns a `TableData`) |
| analysis | `name`, `space`, `field`, `roi`, `csv`/`json`/`nifti`/`pdf`; preview `{type:"analysis"}` |
| report | `id`, `kind`, `title`, `path`, `created`; preview `{type:"report"}` → `reportUrl(id)` |

**Must keep working:** everything exported from `pages/results/api.ts` — `getSimulationsFor`,
`getFlexRuns`, `getExRuns`, `getExRunResults`, `getAnalyses`, `getAnalysisSummary`, `getReports`,
`getGroupCatalog`, `artifactUrl`, `reportUrl`, and the re-exported schema types. B4 adds
`outputsTree.ts` beside them and rewrites `index.tsx`; the API module is untouched.

### 3.8 Metrics helpers — `desktop/tests/e2e/_metrics.ts` (B1)

```ts
export interface DeadSpace { ratio: number; samples: number; dead: number; rect: DOMRectLike }
export function deadSpaceRatio(page: Page, selector?: string, step?: number): Promise<DeadSpace>;

export interface PaneWidths { nav: number; content: number; work: number; right: number; gap: number }
export function paneWidths(page: Page): Promise<PaneWidths>;

export interface FirstScreen { total: number; visible: number; hidden: string[] }
export function firstScreenControls(page: Page): Promise<FirstScreen>;

export interface PageMetrics {
  page: string; theme: "light" | "dark"; width: number; height: number;
  deadSpaceRatio: number; samples: number; dead: number;
  panes: PaneWidths;
  firstScreenControls: FirstScreen;
  screenshot: string;                 // "<page>-<theme>-<w>x<h>.png"
}
/** Sets the theme and viewport, waits for the page's loaded marker, screenshots into
 *  `tests/e2e/artifacts/<runId>/`, and returns the row. */
export function captureScreen(page: Page, opts: {
  runId: string; pageId: string; theme: "light" | "dark"; width: number; height: number;
}): Promise<PageMetrics>;
/** Writes `tests/e2e/artifacts/<runId>/metrics.json` (DESIGN.md §12.2 shape). */
export function writeMetrics(runId: string, rows: PageMetrics[]): Promise<void>;
```
`screens.spec.ts` is the only caller that writes; a lane's own spec imports the three readers and
asserts its numbers from DESIGN.md §12.3.

**Must keep working:** `tests/e2e/_helpers.ts`'s `launchElectronApp`, `offscreenEnv`, `expectPage`,
`expectSubject` and the artifact-directory convention keyed on `TIT_E2E_RUN_ID` — every existing
spec depends on them and `_metrics.ts` is additive beside them.

---

## 4. Open questions for the maintainer

**Q1 — the rail width at 1280 is over-subscribed.** U7 puts labels on the rail at ≥ 1280 (216 px),
which leaves a 1064 px content box; U5 wants the Viewer embed ≥ 1200 px at 1280, which needs the
56 px icon rail. I resolved it by letting the Viewer — and only the Viewer — force
`railMode: "icons"` (§9, §10). The alternative is icons for *every* page below 1440, which would
also give the run pages a 826 px work pane and therefore two-up forms at 1280 instead of one column.
Which?

**Q2 — `blocked` has no server field.** `PlanResult` carries `warnings: string[]` and nothing
structured, so I specified deriving the `blocked` chip by matching a warning that names both the
subject and the stage. That is string matching against prose the server writes. Accept it for 3.0,
or add `PlanResult.blocked: [{subject, stage, reason}]` (a small, additive server change that the
program's "server unchanged" line would have to allow)?

**Q3 — Subjects and Results both list subjects with counts.** I made Subjects the *data and
readiness* home (presence columns, leadfields, coverage strip, the four run verbs) and Results the
*outputs* home (U4's subject list → outputs tree). Two subject lists is still two subject lists.
Should Subjects' detail pane link into Results instead of listing recent runs itself?

**Q4 — the per-job cost tiles.** `_plan_cost` returns one representative job's CPUs and memory, not
the plan's total, and today's Plan card prints "CPUs 8 / Memory 16 GB" beside "Jobs 2" with no
qualifier. I specified per-job with a `"per job"` tooltip. Should the tiles instead show
`8 × 2 = 16 CPU` (which the server has not measured), or keep the honest per-job figure?

**Q5 — ⌘9.** I mapped ⌘1–⌘8 to the eight workflow pages and ⌘9 to Settings (with ⌘, as an alias),
leaving Help on `?` only. Confirm, or reserve ⌘9 for Help so the two pinned pages are symmetrical?
