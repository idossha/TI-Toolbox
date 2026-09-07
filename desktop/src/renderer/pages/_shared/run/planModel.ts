/**
 * `PlanModel` — the one object the run panel, the plan grid and the action-bar digest all read
 * (DESIGN.md v3 §4.5, u0-design-notes §3.1). Pure: no React, no fetch, so it is unit-testable
 * against `tests/fixtures/` without a browser.
 *
 * The rule this file exists to enforce: **the digest and the stats strip cannot disagree**,
 * because both are derived from one `planModelFrom()` result rather than each page formatting
 * `PlanResult` its own way (v2 had four different spellings of "8 CPUs · 16 GB").
 */
import type { components } from "../../../api/schema";

export type PlanKind = "pre" | "sim" | "flex" | "ex" | "mex" | "analyzer";
export type PlanChip = "new" | "skip" | "overwrite" | "blocked" | "wait";

/** `PlanJob` widened with the `stage`/`label` fields `tit/jobs/plans.py` already carries but the
 *  wire model does not yet declare (same widening `pages/preprocess/api.ts` does). */
export type PlanJob = components["schemas"]["PlanJob"] & { stage?: string; label?: string };
export type LockConflict = components["schemas"]["LockConflict"];
export type PlanSystem = components["schemas"]["PlanSystem"];

/** One entry of the `resolved.stages` array the real server's `_plan_pre` appends to in the same
 *  loop as `jobs` (plan.py ≈ 590–606). Not in `openapi.yaml` yet, so it is widened here and
 *  every read of it is guarded by a length check (see `stageIdOf`). */
export interface PlanResolvedStage {
  tags?: string[];
  label?: string;
}
export type PlanResult = Omit<components["schemas"]["PlanResult"], "jobs" | "resolved"> & {
  jobs: PlanJob[];
  resolved?: (components["schemas"]["PlanResolved"] & { stages?: PlanResolvedStage[] }) | null;
};

export interface PlanStats {
  jobs: number;
  /** `PlanResult.cost.cpus` — PER JOB. `_plan_cost` returns one representative job's cost, "not
   *  summed across a multi-job plan" (plan.py docstring), so the tiles must not multiply. */
  cpus: number;
  /** `PlanResult.cost.mem_gb` — PER JOB, same reason. */
  memoryGb: number;
  /** `PlanResult.cost.eta_minutes` — the WHOLE plan's wall clock, unlike the two above, because
   *  that is the number a user reads before pressing Run (`tit/jobs/eta.py`). `null` when the
   *  server has no model for the kind, or could not read what the model needs. */
  etaMinutes: number | null;
  /** `PlanResult.cost.system` — the machine the estimate was computed for, so the UI can say
   *  "on this machine" instead of quoting a universal duration. */
  system: PlanSystem | null;
  waits: number;
}
export interface PlanStage {
  id: string;
  label: string;
}
/** One planned job inside a cell. A cell holds more than one whenever a column is a *category*
 *  rather than a single stage — the Simulator's `Montage · Flex · Free-hand` summary columns, where
 *  every montage of a subject folds into one cell. */
export interface PlanCellJob {
  /** Index into `PlanResult.jobs`, for pinning the terminal. */
  jobIndex: number;
  chip: PlanChip;
  /** The job's own stage id (the montage / run name) — what the popover lists. */
  label: string;
  outputDir: string;
}
export interface PlanCell {
  stageId: string;
  /** `null` = this stage is not part of this subject's run → the grid renders a `·` / `—`. */
  chip: PlanChip | null;
  outputDir: string;
  /** Index into `PlanResult.jobs`, for pinning the terminal. `null` for an empty cell. */
  jobIndex: number | null;
  /** Every job that folded into this cell, in plan order. Empty for an empty cell; exactly one
   *  entry for the one-job-per-cell pages (Pre-processing, Optimizer, Analyzer). */
  jobs: PlanCellJob[];
}
export interface SubjectPlan {
  subject: string;
  cells: PlanCell[];
}

export interface PlanModel {
  kind: PlanKind;
  stats: PlanStats;
  stages: PlanStage[];
  subjects: SubjectPlan[];
  /** `PlanResult.warnings`, verbatim — the only free text in the panel. */
  warnings: string[];
  /** Non-null when nothing can be planned. The digest and the disabled primary's tooltip use it
   *  verbatim ("Select at least one montage."). Never a silent disabled button. */
  blockedReason: string | null;
}

/** Chip precedence, most severe first (DESIGN.md §4.5). */
const CHIP_ORDER: PlanChip[] = ["blocked", "wait", "overwrite", "skip", "new"];

/**
 * The pre-processing stage tags `tit.jobs.plans.plan_preprocessing` emits (G1…G6), mapped to the
 * short column headings the wireframe asks for. An unknown tag keeps its own text, so a new
 * server stage shows up as itself rather than disappearing.
 */
const PRE_STAGE_LABELS: Record<string, string> = {
  G1: "dicom",
  G2a: "charm",
  G2b: "fastsurfer",
  G3: "tissue",
  G4: "qsiprep",
  G5: "qsirecon",
  G6: "dti",
  report: "report",
};

function basename(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/**
 * A directory named after the subject is a per-subject *instance* of one stage, not a stage of
 * its own: `m2m_ernie` and `m2m_101` are the same column. Without this, a `kind="pre"` plan whose
 * server does not send `resolved.stages` (the mock, and any older backend) produces one
 * single-cell column per subject — a diagonal, not a matrix.
 */
export function normalizeStageId(raw: string, subject: string): string {
  if (!subject) return raw;
  const stripped = raw.replace(new RegExp(`[_-]?${escapeRegExp(subject)}[_-]?`, "gi"), "_");
  const cleaned = stripped.replace(/^[_-]+|[_-]+$/g, "").replace(/[_-]{2,}/g, "_");
  return cleaned === "" ? raw : cleaned;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Stage id for `jobs[i]`, in the precedence u0-design-notes §3.1 fixes:
 * 1. `resolved.stages[i].tags[0]` (kind `pre` only, and only when the two arrays are the same
 *    length — they are aligned by construction server-side, and a mismatch means this is not
 *    that server, so it falls through rather than mislabelling);
 * 2. `resolved.stages[i].label`;
 * 3. the job's own `stage`/`label`, then the normalised basename of `output_dir`.
 */
export function stageIdOf(kind: PlanKind, result: PlanResult, i: number): string {
  const job = result.jobs[i];
  const stages = result.resolved?.stages;
  const aligned = Array.isArray(stages) && stages.length === result.jobs.length;
  if (aligned) {
    const stage = stages[i];
    if (kind === "pre" && stage?.tags?.[0]) return stage.tags[0];
    if (stage?.label) return stage.label;
  }
  if (job?.stage) return job.stage;
  if (job?.label) return job.label;
  return job ? normalizeStageId(basename(job.output_dir), job.subject) : `stage-${i}`;
}

export function stageLabelOf(kind: PlanKind, id: string): string {
  if (kind === "pre") return PRE_STAGE_LABELS[id] ?? id;
  return id;
}

/** `true` when `warning` names both `subject` and `stageId` on word boundaries. */
function warningNames(warning: string, subject: string, stageId: string): boolean {
  const has = (needle: string): boolean =>
    needle !== "" && new RegExp(`(^|[^A-Za-z0-9_])${escapeRegExp(needle)}([^A-Za-z0-9_]|$)`, "i").test(warning);
  return has(subject) && has(stageId);
}

/**
 * The chip for one planned job. `blocked` has no server field — `PlanResult` carries only
 * `warnings: string[]` — so it is derived by matching a warning that names both this subject and
 * this stage (orchestrator decision on u0 Q2: string matching for 3.0; a structured
 * `PlanResult.blocked` is the follow-up).
 */
export function chipFor(job: PlanJob, conflicts: LockConflict[], warnings: string[], stageId: string): PlanChip {
  if (warnings.some((w) => warningNames(w, job.subject, stageId))) return "blocked";
  if (conflicts.some((c) => c.subject === job.subject)) return "wait";
  if (job.exists && job.will_overwrite) return "overwrite";
  if (job.exists) return "skip";
  return "new";
}

export function planModelFrom(
  kind: PlanKind,
  result: PlanResult,
  subjectIds: string[],
  opts?: {
    blockedReason?: string | null;
    /**
     * The page's own column list, in **run order** — every stage of this page's kind, whether or
     * not the plan returned a job for it (FXU1: "columns = every stage of the page's kind in run
     * order"). Without it the matrix only has columns for the stages that happened to be planned,
     * which is a one-cell strip on a fresh configuration. Stages the plan returns that are not in
     * this list are appended, so a server that grows a stage is never silently truncated.
     */
    stages?: PlanStage[];
    /**
     * Fold a job onto a column of the caller's own choosing, given the id `stageIdOf` derived.
     * The Simulator uses it to map every montage/flex/free-hand job onto one of three fixed
     * summary columns; every other page omits it and keeps one column per stage.
     */
    stageFor?: (job: PlanJob, index: number, defaultStageId: string) => string;
  },
): PlanModel {
  const warnings = result.warnings ?? [];
  const conflicts = result.lock_conflicts ?? [];

  // Declared columns first, then anything the plan returned that they did not name.
  const declared = opts?.stages ?? [];
  const labelById = new Map(declared.map((s) => [s.id, s.label]));
  const stageIds: string[] = declared.map((s) => s.id);
  const cellsBySubject = new Map<string, Map<string, PlanCell>>();

  result.jobs.forEach((job, i) => {
    const defaultStageId = stageIdOf(kind, result, i);
    const stageId = opts?.stageFor?.(job, i, defaultStageId) ?? defaultStageId;
    if (!stageIds.includes(stageId)) stageIds.push(stageId);
    let row = cellsBySubject.get(job.subject);
    if (!row) {
      row = new Map();
      cellsBySubject.set(job.subject, row);
    }
    const chip = chipFor(job, conflicts, warnings, defaultStageId);
    const entry: PlanCellJob = { jobIndex: i, chip, label: defaultStageId, outputDir: job.output_dir };
    const existing = row.get(stageId);
    // Two or more jobs in one cell (a re-planned stage, or a Simulator summary column): every job
    // is kept, and the cell's own chip is the most severe of them — the same precedence a single
    // cell uses, so a matrix can never under-report.
    if (!existing) {
      row.set(stageId, { stageId, chip, outputDir: job.output_dir, jobIndex: i, jobs: [entry] });
      return;
    }
    existing.jobs.push(entry);
    if (CHIP_ORDER.indexOf(chip) < CHIP_ORDER.indexOf(existing.chip ?? "new")) {
      existing.chip = chip;
      existing.outputDir = job.output_dir;
      existing.jobIndex = i;
    }
  });

  // Every selected subject gets a row, in the page's display order; a subject the plan returned
  // that was not in the selection is appended, so a plan is never silently truncated.
  const ordered = [...subjectIds, ...[...cellsBySubject.keys()].filter((s) => !subjectIds.includes(s))];

  const subjects: SubjectPlan[] = ordered.map((subject) => {
    const row = cellsBySubject.get(subject);
    return {
      subject,
      cells: stageIds.map(
        (stageId) => row?.get(stageId) ?? { stageId, chip: null, outputDir: "", jobIndex: null, jobs: [] },
      ),
    };
  });

  return {
    kind,
    stats: {
      jobs: result.jobs.length,
      cpus: result.cost?.cpus ?? 0,
      memoryGb: result.cost?.mem_gb ?? 0,
      etaMinutes: result.cost?.eta_minutes ?? null,
      system: result.cost?.system ?? null,
      waits: conflicts.length,
    },
    stages: stageIds.map((id) => ({ id, label: labelById.get(id) ?? stageLabelOf(kind, id) })),
    subjects,
    warnings,
    blockedReason: opts?.blockedReason ?? null,
  };
}

/** How many planned *jobs* in the model resolve to a given chip — the digest's overwrite count.
 *  Counted over `cell.jobs`, not over cells, so a summary column that folds several jobs into one
 *  cell reports all of them. */
export function countChip(plan: PlanModel, chip: PlanChip): number {
  return plan.subjects.reduce((n, s) => n + s.cells.reduce((m, c) => m + c.jobs.filter((j) => j.chip === chip).length, 0), 0);
}

/** How many jobs of each chip a cell holds, in vocabulary order — what a summary cell prints
 *  ("2 new · 1 skip"). */
export function cellChipCounts(cell: PlanCell): { chip: PlanChip; count: number }[] {
  return [...CHIP_ORDER]
    .reverse()
    .map((chip) => ({ chip, count: cell.jobs.filter((j) => j.chip === chip).length }))
    .filter((e) => e.count > 0);
}

/**
 * The action bar's one-line digest (DESIGN.md §4.5). Derived, never written: the strip and the
 * digest read the same object, so they cannot disagree.
 */
export function planDigest(plan: PlanModel): string {
  if (plan.blockedReason) return plan.blockedReason;
  const { jobs, cpus, memoryGb, waits } = plan.stats;
  const overwrites = countChip(plan, "overwrite");
  let out = `${jobs} job${jobs === 1 ? "" : "s"} · ${cpus} CPU · ${memoryGb} GB`;
  if (overwrites) out += ` · ${overwrites} overwrite`;
  if (waits) out += ` · ${waits} wait`;
  return out;
}

/**
 * Fold the per-row plan responses a page issues one-per-job (Simulator plans one
 * `POST /api/plan/sim` per (subject, montage) row) into the single `PlanResult` the model reads.
 *
 * `cost` is deliberately **not** summed: `_plan_cost` returns one representative job's CPUs and
 * memory, "not summed across a multi-job plan" (plan.py docstring), so the merged cost is the
 * largest single job's — the number the tiles' "per job" tooltip claims. Warnings and lock
 * conflicts are de-duplicated, because N identical rows would otherwise print one warning N times.
 */
export function mergePlanResults(results: PlanResult[]): PlanResult {
  const jobs: PlanJob[] = [];
  const conflicts = new Map<string, LockConflict>();
  const warnings: string[] = [];
  let cpus = 0;
  let memGb = 0;
  //  ... and `eta_minutes` IS summed, for the opposite reason: it is already the whole of each
  //  response's plan, and a page that plans one row per job runs those rows one after another.
  let eta: number | null = null;
  let system: PlanResult["cost"]["system"] = null;
  for (const r of results) {
    jobs.push(...r.jobs);
    for (const c of r.lock_conflicts ?? []) conflicts.set(`${c.key}:${c.held_by}:${c.subject}`, c);
    for (const w of r.warnings ?? []) if (!warnings.includes(w)) warnings.push(w);
    cpus = Math.max(cpus, r.cost?.cpus ?? 0);
    memGb = Math.max(memGb, r.cost?.mem_gb ?? 0);
    if (typeof r.cost?.eta_minutes === "number") eta = (eta ?? 0) + r.cost.eta_minutes;
    system = system ?? r.cost?.system ?? null;
  }
  return {
    jobs,
    lock_conflicts: [...conflicts.values()],
    cost: { cpus, mem_gb: memGb, eta_minutes: eta, system },
    warnings,
    resolved: null,
  };
}

/** The counts every run page needs to decide whether the existing-outputs dialog has anything to
 *  ask about. Derived from the same `PlanModel` the grid and the digest draw, so the three cannot
 *  disagree. (This is what is left of the run receipt, removed 2026-09-06: the plan grid in the
 *  run pane and the action-bar digest are the confirmation now, so only the *numbers* survived.) */
export interface PlanCounts {
  /** Planned jobs — the number the button and the digest also print. */
  jobs: number;
  /** Jobs whose output directory already exists (`skip` + `overwrite`). */
  existing: number;
  /** Of those, the ones that would be replaced rather than skipped. */
  overwrites: number;
  blocked: number;
  waits: number;
}

/**
 * Count the planned jobs, in the page's own display order. A `null` chip means "this stage is not
 * part of this subject's run" and is not counted, because a job that will not run is not a job.
 */
export function planCounts(plan: PlanModel | null): PlanCounts {
  let jobs = 0;
  let existing = 0;
  let overwrites = 0;
  let blocked = 0;
  for (const subject of plan?.subjects ?? []) {
    for (const cell of subject.cells) {
      // Over the cell's jobs, not the cell: a Simulator summary column holds one cell per subject
      // and many jobs inside it, and every one of them is a job that will run.
      for (const cellJob of cell.jobs) {
        jobs += 1;
        if (cellJob.chip === "skip") existing += 1;
        if (cellJob.chip === "overwrite") {
          existing += 1;
          overwrites += 1;
        }
        if (cellJob.chip === "blocked") blocked += 1;
      }
    }
  }
  return { jobs, existing, overwrites, blocked, waits: plan?.stats.waits ?? 0 };
}
