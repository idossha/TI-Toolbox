/**
 * The Optimizer's **Jobs table** row model (2026-09-06, lane OJ).
 *
 * Maintainer, on a screenshot of the page still showing a global Subjects list and "No subjects
 * selected": *"create something similar logically to the Simulator and Analyzer: choose a subject,
 * then an optimisation approach (Flex, Ex, mEx…) and configure each job exactly how they want, so
 * users create a list of jobs and run them."*
 *
 * What the page was: one page-level subject SET × one method × one target × one form. Three
 * subjects was three copies of the same search, and "flex on ernie's insula and ex on 101's
 * thalamus" could not be expressed at all — the cross-product was the only sentence the page
 * could say. 2.5.0 had the same defect in a different shape (two tabs, each with its own Global
 * Parameters box), so nothing is being taken away from it: the box was *per tab*, which is
 * per method, which is now per row.
 *
 * So **one row is one search job**, and the row owns everything that differs between jobs: the
 * subject, the method, the net (Flex) or the leadfield (Ex/mEx), the goal, the target, the avoid
 * ROI, and the whole method-specific form. Nothing is left global — the page has no global
 * TARGET / ELECTRODES / COST sections, because none of those were ever properties of the *run*.
 *
 * This module is the pure half: the model, its defaults, its readable summaries and its
 * column-width resolver. Everything that needs the network (atlas paths, leadfield paths) is
 * resolved by `index.tsx` at plan/submit time, per row, from that row's own subject.
 */
import { emptyRoi, isRoiComplete, type RoiRegion, type RoiValue } from "../_shared/roi";
import type { PlanKind } from "../_shared/run";
import { defaultFlexFormState, jobKindFor, type FlexFormState, type OptGoal } from "./flexConfig";
import { defaultExFormState, defaultMExFormState, type ExFormState, type MExFormState } from "./exConfig";
import { exCost, mexCost } from "./cost";

/**
 * The **two** things a row can be. A method is the kind of *search* — free electrode positions, or
 * an exhaustive sweep over a precomputed leadfield — and nothing more.
 *
 * Coordinator, 2026-09-06, on a Method select listing five entries: the five job kinds this page
 * submits are not five methods. `flex_adaptive` / `flex_pareto` are what a flex search *becomes*
 * when its focality thresholds are derived or swept, and `mex` is what an exhaustive search
 * *becomes* when it is given four pairs instead of two. Both are **derived** from options the user
 * already sets in the row's editor (`rowJobKind`), exactly as the Simulator infers TI from mTI from
 * how many electrode pairs a montage has. A select that also let the kind be *chosen* would be a
 * second control able to disagree with the first.
 */
export type OptMethod = "flex" | "ex";

/** What actually goes on the wire, and to `POST /api/plan/{kind}`. Never chosen directly. */
export type OptJobKind = "flex" | "flex_adaptive" | "flex_pareto" | "ex" | "mex";

export const OPT_METHODS: { value: OptMethod; label: string; title: string }[] = [
  { value: "flex", label: "Flex", title: "Differential-evolution search over free electrode positions" },
  { value: "ex", label: "Ex", title: "Exhaustive search over a precomputed leadfield — two pairs (TI) or four (mTI)" },
];

export const OPT_METHOD_LABEL: Record<OptMethod, string> = { flex: "Flex", ex: "Ex" };

/** The Flex family shares one form, one ROI vocabulary and one plan shape. */
export function isFlexMethod(method: OptMethod): boolean {
  return method === "flex";
}

/**
 * The job kind a row submits as, **derived** from what the row's editor holds:
 *
 *  * Flex — `jobKindFor(form)`: the focality mode. `focality` + manual thresholds is plain `flex`;
 *    `adaptive` and `pareto` are their own orchestration kinds. Unchanged from 2.5.0.
 *  * Ex — the electrode count. Four electrodes (two pairs) is a two-channel TI search (`ex`);
 *    eight (four pairs) is the multipolar mTI search (`mex`). The same inference the Simulator
 *    makes from a montage's pairs.
 */
export function rowJobKind(row: OptimizerRow): OptJobKind {
  if (row.method === "flex") return jobKindFor(row.flex);
  return row.exPairs === 4 ? "mex" : "ex";
}

/** `PlanKind` for `POST /api/plan/{kind}` and the run panel's step list. */
export function rowPlanKind(row: OptimizerRow): PlanKind {
  return row.method === "flex" ? "flex" : (rowJobKind(row) as "ex" | "mex");
}

/** The plan grid's column for a row: the three families the panel counts per subject. */
export function rowStage(row: OptimizerRow): "flex" | "ex" | "mex" {
  return row.method === "flex" ? "flex" : (rowJobKind(row) as "ex" | "mex");
}

/**
 * One row = one search job.
 *
 * All three method forms are carried at once, not a discriminated union, and deliberately: a user
 * who tries Ex and goes back to Flex has not thrown away the buckets they filled in, and the row
 * editor for a method is then always looking at that method's own last answer. The cost is three
 * small objects per row; the alternative is a row that silently forgets.
 */
export interface OptimizerRow {
  id: string;
  subjectId: string;
  method: OptMethod;
  /**
   * Ex only: how many electrode PAIRS the exhaustive search enumerates — 2 (four electrodes, TI)
   * or 4 (eight electrodes, mTI). This is the whole of the `ex` / `mex` decision, in two-pair
   * steps, and it lives here rather than being read back out of the bucket contents so a row that
   * is half filled in still knows which search it is.
   */
  exPairs: 2 | 4;
  /** Flex: the EEG net optimised positions are mapped onto (optional). Ex/mEx: the leadfield's
   *  net — the *bare* name, which is this page's one net identity (`nets.ts`). */
  net: string | null;
  /** The row's target — the shared `RoiValue`, in the modes its method understands. */
  roi: RoiValue;
  /** Flex focality's "avoid" region, used only when `flex.nonRoiMethod === "specific"`. */
  nonRoi: RoiValue;
  flex: FlexFormState;
  ex: ExFormState;
  mex: MExFormState;
  /** `ExConfig.run_name` / the flex output folder suffix. Blank = the runner's timestamp. */
  runName: string;
}

let rowSeq = 0;

export function newOptimizerRowId(): string {
  rowSeq += 1;
  return `opt-${rowSeq}`;
}

/** The ROI modes a method can express — Flex targets anatomy, Ex/mEx target saved CSVs or a
 *  volumetric atlas (there is no cortical ex-search target: the leadfield is volumetric). */
export function roiModesFor(method: OptMethod): ("cortical" | "subcortical" | "spherical" | "saved" | "mask")[] {
  return isFlexMethod(method) ? ["cortical", "subcortical", "spherical", "mask"] : ["saved", "subcortical", "mask"];
}

/** A blank row, seeded from the row before it (the "+ Add job" gesture 2.5.0's cards had). */
export function emptyOptimizerRow(seed?: Partial<OptimizerRow>): OptimizerRow {
  const method = seed?.method ?? "flex";
  return {
    id: newOptimizerRowId(),
    subjectId: seed?.subjectId ?? "",
    method,
    exPairs: seed?.exPairs ?? 2,
    net: seed?.net ?? null,
    roi: seed?.roi ?? emptyRoi(isFlexMethod(method) ? "cortical" : "saved"),
    nonRoi: seed?.nonRoi ?? emptyRoi("cortical"),
    flex: seed?.flex ?? defaultFlexFormState(),
    ex: seed?.ex ?? defaultExFormState(),
    mex: seed?.mex ?? defaultMExFormState(),
    runName: seed?.runName ?? "",
  };
}

/**
 * Switching a row's method. The target follows the method's own vocabulary — a saved CSV is not a
 * cortical parcellation, and carrying one across would leave a row that looks configured and
 * cannot be planned. Within the Flex family the target survives (all three take the same ROI).
 */
export function withMethod(row: OptimizerRow, method: OptMethod): OptimizerRow {
  if (method === row.method) return row;
  // A saved CSV is not a cortical parcellation: carrying a target across families would leave a
  // row that looks configured and can never be planned.
  return { ...row, method, roi: emptyRoi(method === "flex" ? "cortical" : "saved") };
}

/** The goal a row optimises. Ex/mEx rank montages by ROI field and have no goal of their own. */
export function rowGoal(row: OptimizerRow): OptGoal | null {
  return row.method === "flex" ? row.flex.goal : null;
}

/**
 * The **variant** a row's derived kind reads as, for line 2 — `adaptive`, `Pareto`, or the
 * electrode count that decides TI from mTI. Empty for a plain flex search, which has no variant to
 * state.
 */
export function rowVariantLabel(row: OptimizerRow): string {
  if (row.method === "flex") {
    const kind = rowJobKind(row);
    return kind === "flex_adaptive" ? "adaptive" : kind === "flex_pareto" ? "Pareto" : "";
  }
  return `${row.exPairs * 2} electrodes (${row.exPairs === 4 ? "mTI" : "TI"})`;
}

export const GOAL_LABEL: Record<OptGoal, string> = {
  mean: "mean",
  max: "max",
  focality: "focality",
  focality_tf: "focality_tf",
};

/**
 * A row is a **job** once it names a subject, a target its method can resolve, and — for Ex/mEx —
 * a leadfield. Deliberately pure: `hasLeadfield` is the caller's per-subject fact, because a
 * leadfield lives under one subject's derivatives and the table has one per row.
 */
export function isRunnableOptimizerRow(row: OptimizerRow, hasLeadfield: (row: OptimizerRow) => boolean): boolean {
  if (!row.subjectId) return false;
  if (!isRoiComplete(row.roi)) return false;
  if (row.method === "ex" && !hasLeadfield(row)) return false;
  return true;
}

/** `lh.insula` — the hemisphere is part of a cortical region's identity. */
function regionLabel(r: RoiRegion): string {
  return r.hemi ? `${r.hemi}.${r.name}` : r.name;
}

function count(value: number): string {
  return value.toLocaleString("en-US");
}

function num(v: number | undefined): string {
  return v === undefined ? "?" : String(v);
}

/** Up to two names, then a count — the target line has room for two, never for nine. */
function joinNames(names: string[]): string {
  if (names.length <= 2) return names.join(" + ");
  return `${names.slice(0, 2).join(" + ")} + ${names.length - 2} more`;
}

/**
 * A target as a **short chip**, not a sentence: `lh.insula · DK40`, `Sphere r10 @ 10,10,10 MNI`,
 * `Thalamus_target`.
 *
 * Coordinator, 2026-09-06, on a row reading `TARGET ◎ Choose a target… · Ex · 4 electrodes (TI) ·
 * buckets: 4 · 2 mA total · 0 electrodes · 7 splits · 0 combin…`: line 2 is an *efficient summary
 * of the optimisation*, so it states what matters and nothing line 1 already says. The target comes
 * first and never truncates (the row's CSS gives it its width and lets the rest ellipse), because a
 * search whose target the reader cannot see is not summarised at all.
 *
 * Region first, atlas after: the region is what the user chose, the atlas is where it came from.
 */
export function optimizerTargetLabel(roi: RoiValue): string {
  if (!isRoiComplete(roi)) return "Choose a target…";
  if (roi.mode === "mask") return `${roi.path.split("/").pop()} · ${roi.space === "mni" ? "MNI" : "Subject"} mask`;
  if (roi.mode === "saved") return `${joinNames(roi.selected)}${roi.space === "mni" ? " MNI" : ""}`;
  if (roi.mode === "spherical") {
    const space = roi.space === "mni" ? " MNI" : "";
    // More than one sphere is a union; naming them all would be the sentence this replaced.
    if (roi.spheres.length > 1) return `Sphere ×${roi.spheres.length}${space}`;
    const [first] = roi.spheres;
    return `Sphere r${num(first?.radius)} @ ${num(first?.x)},${num(first?.y)},${num(first?.z)}${space}`;
  }
  return `${joinNames(roi.regions.map(regionLabel))} · ${roi.atlas}`;
}

/**
 * The **essentials** of the search, for the rest of line 2 — never what line 1 already says.
 *
 *  * Flex: `goal mean · 2 pairs · 1 mA · ratio 1:1`. The derived variant qualifies the goal, since
 *    that is the only place it is stated.
 *  * Ex: `4 electrodes (TI) · 2 mA · 7 splits · 5,040 combinations`. mEx fixes one current per pair
 *    and sweeps no amplitudes, so it has no splits to report.
 *
 * The electrode count is the montage's — `pairs × 2`, fixed — not the distinct pool, which read
 * `0 electrodes` on a row whose buckets were not filled in yet and said nothing about the search.
 * The combination count still comes from `cost.ts`, so this line and the action-bar digest cannot
 * disagree about how expensive a search is (the whole point of that module).
 */
export function optimizerMethodSummary(row: OptimizerRow): string {
  if (row.method === "flex") {
    const form = row.flex;
    const variant = rowVariantLabel(row);
    return [
      `goal ${form.goal}${variant ? ` (${variant})` : ""}`,
      "2 pairs",
      `${form.currentMA} mA`,
      `ratio ${form.optimizeCurrentRatio ? `sweep ${form.ratioLevels}` : "1:1"}`,
    ].join(" · ");
  }
  if (row.exPairs === 2) {
    const cost = exCost(row.ex);
    return `${rowVariantLabel(row)} · ${row.ex.totalCurrent} mA · ${cost.splits} splits · ${count(cost.combinations)} combinations`;
  }
  return `${rowVariantLabel(row)} · ${row.mex.currentMa} mA · ${count(mexCost(row.mex).combinations)} combinations`;
}

/**
 * The Jobs section's summary line: how many rows are jobs, over how many subjects, and how many
 * are still half-filled — 2.5.0's "This will run N search(es)" confirmation, stated continuously
 * rather than only at the moment of pressing Run.
 */
export function optimizerJobsSummary(rows: OptimizerRow[], runnable: OptimizerRow[]): string {
  if (rows.length === 0) return "no jobs yet";
  const subjects = new Set(runnable.map((r) => r.subjectId)).size;
  const incomplete = rows.length - runnable.length;
  const head =
    runnable.length === 0
      ? "no complete job"
      : `${runnable.length} search${runnable.length === 1 ? "" : "es"} · ${subjects} subject${subjects === 1 ? "" : "s"}`;
  return incomplete > 0 ? `${head} · ${incomplete} incomplete` : head;
}

/* ------------------------------------------------------------------------------------------------
 * Column widths — the same grammar as the Simulator's jobs table (`simulator/MontageManager.tsx`).
 *
 * The table must never scroll sideways, so the widths cannot be a pixel colgroup the user drags
 * past the container: the actions column is fixed and the four content columns share what is left,
 * resolved to exact pixels that sum to the container by construction.
 *
 * Written here rather than imported from the Simulator because the Simulator's resolver is keyed to
 * ITS four columns (`subject · source · net · montage`) and lives in a file another lane owns. The
 * shape is identical and the two are the obvious candidate for one `useTableColumns` hook; see
 * OJ.md's open items.
 * --------------------------------------------------------------------------------------------- */

export type OptColumnKey = "subject" | "method" | "net" | "goal";
export type StoredOptColumns = Partial<Record<OptColumnKey, number>>;

export interface OptColumnWidths {
  subject: number;
  method: number;
  net: number;
  goal: number;
  actions: number;
}

/** Three 28px icon buttons (duplicate · edit · remove), the Simulator's own actions cell. */
export const OPT_ACTIONS_W = 96;

export const OPT_COLUMN_MIN: Record<OptColumnKey, number> = {
  subject: 64,
  method: 104,
  net: 132,
  goal: 96,
};

/** Measured at 1280 with the default pane (a 608px table): a subject id, "Flex adaptive", a real
 *  net name (`EEG10-10_UI_Jurak_2007`) and "focality_tf", none truncated. */
const OPT_COLUMN_DEFAULT_FRACTION = { subject: 0.17, method: 0.24, net: 0.36, goal: 0.23 } as const;

export const OPT_COLUMNS_STORAGE_KEY = "tit-opt-jobs-columns-v1";

const OPT_KEYS = ["subject", "method", "net", "goal"] as const;

/** Exact pixel widths for a table `container` px wide; the total is always `container`. */
export function resolveOptColumnWidths(container: number, stored: StoredOptColumns): OptColumnWidths {
  const avail = Math.max(0, Math.round(container) - OPT_ACTIONS_W);
  const w = { subject: 0, method: 0, net: 0, goal: 0 };
  for (const k of OPT_KEYS) {
    w[k] = Math.max(OPT_COLUMN_MIN[k], Math.round(stored[k] ?? avail * OPT_COLUMN_DEFAULT_FRACTION[k]));
  }
  const total = () => OPT_KEYS.reduce((sum, k) => sum + w[k], 0);
  if (total() !== avail) {
    w.net = Math.max(OPT_COLUMN_MIN.net, avail - w.subject - w.method - w.goal);
  }
  if (total() > avail) {
    let need = total() - avail;
    // The column the user just dragged gives last.
    for (const k of ["net", "goal", "subject", "method"] as const) {
      const give = Math.min(w[k] - OPT_COLUMN_MIN[k], need);
      w[k] -= give;
      need -= give;
      if (need <= 0) break;
    }
  }
  if (total() > avail && total() > 0) {
    const scale = avail / total();
    for (const k of OPT_KEYS) w[k] = Math.max(1, Math.floor(w[k] * scale));
  }
  w.net = Math.max(1, w.net + (avail - total()));
  return { ...w, actions: OPT_ACTIONS_W };
}

/** Reads the persisted widths; never throws (storage can be disabled or corrupt). */
export function readStoredOptColumns(storage: Pick<Storage, "getItem"> | undefined): StoredOptColumns {
  if (!storage) return {};
  try {
    const raw = storage.getItem(OPT_COLUMNS_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const rec = parsed as Record<string, unknown>;
    const out: StoredOptColumns = {};
    for (const k of OPT_KEYS) {
      const v = rec[k];
      if (typeof v === "number" && Number.isFinite(v)) out[k] = Math.max(OPT_COLUMN_MIN[k], Math.round(v));
    }
    return out;
  } catch {
    return {};
  }
}

export function writeStoredOptColumns(storage: Pick<Storage, "setItem"> | undefined, cols: StoredOptColumns): void {
  if (!storage) return;
  try {
    storage.setItem(OPT_COLUMNS_STORAGE_KEY, JSON.stringify(cols));
  } catch {
    /* storage disabled or full — the table still resizes, it just forgets. */
  }
}
