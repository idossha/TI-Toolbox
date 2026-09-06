/**
 * What the run page's Terminal shows when no job of its kind is live (DESIGN.md v3 §4.6, fix lane
 * FXU1). The rule the orchestrator's visual verdict added: **the terminal is never an empty box.**
 *
 * Three sources, first available wins:
 *   1. `live`    — the followed job's event stream (`JobTerminal`'s existing rules 1–4);
 *   2. `file`    — the LAST log file of this page's kind for the current subject, tailed from the
 *                  server (`GET /api/catalog/logs` → `GET /api/files/text?path=&tail=200`);
 *   3. `preview` — a "What will run" panel: the ordered steps of the current configuration with a
 *                  one-line description each and an estimated duration.
 *
 * Everything here is pure so the rules are unit-tested without a browser or a socket.
 */
import type { JobLogLine } from "../../../ui/Jobs";
import type { PlanKind, PlanModel } from "./planModel";

export type TerminalSource = "live" | "file" | "preview";

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

/** A log file the server lists for a subject (`GET /api/catalog/logs`). */
export interface LogFileEntry {
  path: string;
  name: string;
  kind: string;
  /** ISO-8601. */
  modified: string;
  size?: number;
}

const LEVEL_RE = /\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b/;

/**
 * A tailed log file → the same `JobLogLine[]` the live console renders, so one component draws
 * both and the level colours stay the token set (§4.6). A line with no level word is `info`:
 * inventing `debug` for it would grey out a traceback's continuation lines.
 */
export function parseLogText(text: string): JobLogLine[] {
  return text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line, i, all) => line.trim() !== "" || i < all.length - 1)
    .map((text, i) => {
      const m = LEVEL_RE.exec(text);
      const word = m?.[1]?.toUpperCase();
      const level: JobLogLine["level"] =
        word === "DEBUG"
          ? "debug"
          : word === "WARNING" || word === "WARN"
            ? "warning"
            : word === "ERROR" || word === "CRITICAL" || word === "FATAL"
              ? "error"
              : "info";
      return { seq: i, level, text };
    });
}

/**
 * The newest log file of one of `kinds`. The server sorts newest-first, but a mock, a proxy or a
 * future paginated route may not, so the pick is made here rather than assumed.
 */
export function pickLogFile(files: LogFileEntry[], kinds: PlanKind[]): LogFileEntry | null {
  const of = files.filter((f) => kinds.includes(f.kind as PlanKind));
  if (of.length === 0) return null;
  return of.reduce((best, f) => (Date.parse(f.modified) > Date.parse(best.modified) ? f : best));
}

/** `/a/b/c.log` → `c.log`. */
export function logBasename(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/**
 * Estimated wall-clock for the whole plan.
 *
 * `PlanResult.cost` carries only `cpus` and `mem_gb` — there is no server-side ETA field yet (a
 * `PlanCost.eta_minutes` is the follow-up this lane reports) — so the estimate is the steps' own
 * per-subject minutes times the number of subject rows the plan has, divided by how many of those
 * rows can run at once. It is labelled "estimate" in the UI for exactly that reason.
 */
export function estimateMinutes(steps: RunStep[], plan: PlanModel | null, parallel = 1): number {
  const perSubject = steps.reduce((n, s) => n + s.minutes, 0);
  const rows = Math.max(1, plan?.subjects.length ?? 1);
  return Math.round((perSubject * rows) / Math.max(1, parallel));
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
    { id: "report", label: "Subject report", detail: "Collects the QC figures of every step above into one HTML report.", minutes: 1 },
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
