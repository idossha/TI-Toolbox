/**
 * What the run page's Terminal follows, and what it shows when it follows nothing (DESIGN.md v3
 * §4.6, fix lane FXU2).
 *
 * The rule the maintainer's screenshot forced (a freshly opened Pre-processing tab showing
 * `pre · 102 · ● succeeded 12s` with a full DICOM log, which reads as "a job is happening"):
 *
 *   **The terminal never pins a finished job by itself.** On page open it follows a job only when
 *   one of this page's kinds is *currently running or queued* — then something really is
 *   happening and naming it is the truth. Otherwise the pane is an empty console with one quiet
 *   line, until the user runs from this page (the job it starts is running, so rule 2 picks it
 *   up) or pins a job explicitly (a plan-cell click, the Jobs page, this pane's own pin button).
 *   A pin the user made is page-session state and survives navigation within the session.
 *
 * The two sources the previous lane (FXU1) added — tailing the last log FILE of the kind, and a
 * "What will run" preview — are gone with it: both put content in the pane that a reader could
 * mistake for a run of their own. The step catalogue below stays, because the pages compute their
 * step list from it and it is the natural input for a future work-pane preview.
 *
 * Everything here is pure so the rules are unit-tested without a browser or a socket.
 */
import type { JobSummary } from "../../../ui/Jobs";
import type { JobState } from "../../../ui/Status";
import type { PlanKind, PlanModel } from "./planModel";

/** What the pane is showing: a followed job's live log, or nothing at all. */
export type TerminalSource = "live" | "empty";

/**
 * `ui/Jobs.tsx`'s `JobSummary` plus the two facts the follow rule needs and a rail trace does not:
 * every subject a job is scoped to (the selection is intersected with it) and the creation instant
 * (the tie-break). Structurally a `JobSummary`, so it still renders anywhere one does.
 */
export interface FollowableJob extends JobSummary {
  subjects: string[];
  createdAt: number;
  logPath?: string;
}

/** Queued counts as "happening": the job exists, is going to run, and is the one to watch. */
const RUNNING: JobState[] = ["running", "queued"];

/**
 * Which job the terminal follows — `null` for "nothing is running; show the empty console".
 *
 * Order, first match wins, ties on `createdAt` descending:
 *   1. the job the user pinned (whatever its state — they asked for that log by name);
 *   2. the newest running/queued job of one of `kinds` whose subjects intersect `subjects`;
 *   3. the newest running/queued job of one of `kinds`, when nothing intersects;
 *   4. the newest job **this page session started** (`startedJobIds`), whatever state it is in.
 *
 * Rule 4 is the maintainer's 2026-09-07 correction. Rules 1-3 alone unpinned a job the instant it
 * reached a terminal state, so the analyzer run you had just watched vanished — log and final
 * status line with it — the moment it succeeded. A job you started here stays in your terminal
 * through completion until you start another one from this page, pin another job, or the page
 * session ends. It is deliberately NOT a general "show the last finished job": a finished job this
 * page session did not start is still never auto-followed on open, which is the rule the earlier
 * screenshot (an idle Pre-processing tab reading `pre · 102 · succeeded 12s`) forced.
 */
export function resolveFollowedJob(
  jobs: FollowableJob[],
  kinds: PlanKind[],
  subjects: string[],
  pinnedJobId?: string | null,
  startedJobIds?: readonly string[],
): FollowableJob | null {
  const byNewest = [...jobs].sort((a, b) => b.createdAt - a.createdAt);
  if (pinnedJobId) {
    const pinned = byNewest.find((j) => j.id === pinnedJobId);
    if (pinned) return pinned;
  }
  const running = byNewest.filter((j) => kinds.includes(j.kind as PlanKind) && RUNNING.includes(j.state));
  const live = running.find((j) => j.subjects.some((s) => subjects.includes(s))) ?? running[0];
  if (live) return live;
  if (startedJobIds && startedJobIds.length > 0) {
    const started = new Set(startedJobIds);
    // Newest first, so a multi-stage run (preprocessing expands one subject into one job per
    // stage) settles on the LAST stage's log rather than the first one to finish.
    // Kind-filtered like every other rule: the started ids are this page's by construction, and
    // a stale id from another page's session bag must not put a foreign log in this pane.
    const mine = byNewest.find((j) => started.has(j.id) && kinds.includes(j.kind as PlanKind));
    if (mine) return mine;
  }
  return null;
}

/** One entry of a page's "What will run" list. */
export interface RunStep {
  /** Stable id — the same id the plan matrix uses for the column, where the two align. */
  id: string;
  /** Short imperative name, sentence case: "Convert DICOM to NIfTI". */
  label: string;
  /** One line the user can read: what the step does, not how. */
  detail: string;
  /** Rough wall-clock minutes for ONE subject on a typical workstation. */
  minutes: number;
}

/**
 * Estimated wall-clock for the whole plan.
 *
 * **The server's number wins.** `PlanCost.eta_minutes` (`tit/jobs/eta.py`) is computed from what
 * actually drives the run — electrodes in the cap, electrode pairs, evaluated combinations, the
 * stage list — scaled by the subject's mesh and by the machine this container is on (emulated or
 * native, core count), which is knowledge no table in the renderer can have. The step table below
 * is the fallback for a kind the server has no model for, or a plan that has not loaded yet: the
 * steps' per-subject minutes times the subject rows, divided by the rows that run at once.
 *
 * Either way it is an estimate and the UI labels it as one.
 */
export function estimateMinutes(steps: RunStep[], plan: PlanModel | null, parallel = 1): number {
  const server = plan?.stats.etaMinutes;
  if (typeof server === "number" && server > 0) return Math.round(server);
  const perSubject = steps.reduce((n, s) => n + s.minutes, 0);
  const rows = Math.max(1, plan?.subjects.length ?? 1);
  return Math.round((perSubject * rows) / Math.max(1, parallel));
}

/** "≈ 48 m on this machine" — the estimate with the caveat the number cannot carry alone. */
export function estimateLabel(minutes: number, system?: { emulated?: boolean } | null): string {
  const where = system ? " on this machine" : "";
  return `≈ ${durationLabel(minutes)}${where}`;
}

/** "1 h 25 m", "48 m", "< 1 m" — never a bare number of minutes. */
export function durationLabel(minutes: number): string {
  if (minutes < 1) return "< 1 m";
  if (minutes < 60) return `${Math.round(minutes)} m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m === 0 ? `${h} h` : `${h} h ${m} m`;
}

/**
 * The per-kind step catalogue. A page passes the subset its current configuration selected, in run
 * order; the descriptions are the ones a user needs to decide whether to press Run, not a manual.
 * Minutes are order-of-magnitude figures measured on the maintainer's ernie runs — an estimate the
 * UI labels as one.
 */
export const RUN_STEPS: Record<PlanKind, RunStep[]> = {
  pre: [
    { id: "G1", label: "Convert DICOM to NIfTI", detail: "dcm2niix over sourcedata/, writing BIDS anat/ and dwi/ with sidecars.", minutes: 2 },
    { id: "G2a", label: "SimNIBS charm", detail: "Head segmentation and tetrahedral mesh; writes m2m_<subject>/ and the subject atlases.", minutes: 45 },
    { id: "G2b", label: "FastSurfer segmentation", detail: "Deep-learning cortical parcellation; the slowest step, and CPU-bound without a GPU.", minutes: 90 },
    { id: "G3", label: "Tissue analyzer", detail: "Per-tissue volume and conductivity report for the finished head model.", minutes: 3 },
    { id: "G4", label: "QSIPrep", detail: "Dockerised diffusion preprocessing: denoise, distortion and motion correction.", minutes: 120 },
    { id: "G5", label: "QSIRecon", detail: "Dockerised reconstruction of the preprocessed DWI into scalar maps.", minutes: 60 },
    { id: "G6", label: "Extract DTI tensor", detail: "Writes the anisotropic conductivity tensor SimNIBS reads at simulation time.", minutes: 6 },
    // No report step: each preprocessing job writes its own HTML report as its final stage and
    // the server folds the subject report's minute into the plan's estimate, so a report is
    // never a step, a plan row or a job of its own (maintainer, 2026-09-07).
  ],
  sim: [
    { id: "mesh", label: "Load the head model", detail: "Reads m2m_<subject>/<subject>.msh and applies the conductivity model.", minutes: 1 },
    { id: "electrodes", label: "Mesh the electrodes", detail: "Cuts the pads and gel into the scalp surface at the montage positions.", minutes: 1 },
    { id: "fem", label: "Solve the FEM, one pair at a time", detail: "Two electrode pairs per TI montage; the dominant cost of the run.", minutes: 8 },
    { id: "ti", label: "Compute the TI envelope", detail: "Builds the requested output fields over every element of the mesh.", minutes: 1 },
    { id: "nifti", label: "Write meshes and NIfTI", detail: "Subject-space overlays plus the MNI transform for group work.", minutes: 2 },
  ],
  flex: [
    { id: "leadfield", label: "Load the leadfield", detail: "Reads the precomputed per-electrode fields for the selected EEG net.", minutes: 2 },
    { id: "roi", label: "Resolve the ROI", detail: "Turns the atlas regions or spheres into the node set the goal is scored on.", minutes: 1 },
    { id: "search", label: "Differential evolution", detail: "Moves the electrodes over the scalp to optimise the goal; the whole run.", minutes: 30 },
    { id: "write", label: "Write the result", detail: "Best montage, optimised field mesh, CSV of the population and the QC figures.", minutes: 2 },
  ],
  ex: [
    { id: "leadfield", label: "Load the leadfield", detail: "Reads the precomputed per-electrode fields for the selected EEG net.", minutes: 2 },
    { id: "roi", label: "Resolve the ROI", detail: "Turns the atlas regions or spheres into the node set the goal is scored on.", minutes: 1 },
    { id: "search", label: "Evaluate every electrode pair", detail: "Exhaustive sweep of the bucket combinations; scales with the bucket sizes.", minutes: 22 },
    { id: "write", label: "Write the ranked results", detail: "Ranked CSV plus a mesh for each of the top montages.", minutes: 3 },
  ],
  mex: [
    { id: "leadfield", label: "Load the leadfield", detail: "Reads the precomputed per-electrode fields for the selected EEG net.", minutes: 2 },
    { id: "roi", label: "Resolve the ROI", detail: "Turns the atlas regions or spheres into the node set the goal is scored on.", minutes: 1 },
    { id: "search", label: "Evaluate every electrode triple", detail: "Exhaustive multi-pair sweep; combinatorially larger than an ex-search.", minutes: 30 },
    { id: "write", label: "Write the ranked results", detail: "Ranked CSV plus a mesh for each of the top multi-pair montages.", minutes: 3 },
  ],
  analyzer: [
    { id: "load", label: "Load the simulation field", detail: "Reads the selected run's mesh or NIfTI and the chosen output field.", minutes: 1 },
    { id: "roi", label: "Build the ROI mask", detail: "Atlas region, subcortical label or sphere, in the space you picked.", minutes: 1 },
    { id: "stats", label: "Compute the metrics", detail: "Mean, median, p95, max in the ROI and in the surrounding tissue; focality.", minutes: 1 },
    { id: "report", label: "Write CSV and report", detail: "summary.csv, the overlay figures and the PDF report for the analysis.", minutes: 1 },
  ],
};

/** The steps of `kind` whose ids appear in `ids`, in the catalogue's run order. */
export function stepsFor(kind: PlanKind, ids?: string[]): RunStep[] {
  const all = RUN_STEPS[kind] ?? [];
  if (!ids) return all;
  const wanted = new Set(ids);
  return all.filter((s) => wanted.has(s.id));
}
