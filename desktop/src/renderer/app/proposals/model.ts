/**
 * What an agent's proposal says, in the user's terms — pure functions the card renders
 * (`ProposalCard.tsx`) and the unit tests read (`tests/unit/proposal-card.test.tsx`). The record
 * itself is `tit.server.proposals` (ARCHITECTURE §6); nothing here decides what runs.
 */
import type { JobStatus } from "../jobs/types";
import type { Proposal } from "../jobs/types";

export type { Proposal };
export type ProposalStep = Proposal["steps"][number];
export type StepState = ProposalStep["state"];
type Config = Record<string, unknown>;

const KIND_LABEL: Record<string, string> = {
  pre: "Pre-process",
  sim: "Simulate",
  sim_from_flex: "Simulate the flex-search result",
  flex: "Flex-search",
  flex_adaptive: "Flex-search (adaptive focality)",
  flex_pareto: "Flex-search (Pareto sweep)",
  ex: "Ex-search",
  mex: "mEx-search",
  leadfield: "Leadfield",
  analyzer: "Analyze",
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

const GOAL_LABEL: Record<string, string> = {
  mean: "Mean field in the target",
  max: "Peak field in the target",
  focality: "Focality (thresholds)",
  focality_tf: "Focality",
};

const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const base = (p: unknown): string => (typeof p === "string" ? (p.split("/").pop() ?? p) : "");

/** A FlexConfig ROI object as one line: what it is, which atlas or where. */
export function roiLabel(roi: unknown): string {
  if (!roi || typeof roi !== "object") return "—";
  const r = roi as Config;
  const labels = list(r.label).join(", ");
  if (r._type === "SphericalROI") {
    const at = [list(r.x)[0], list(r.y)[0], list(r.z)[0]].join(", ");
    return `Sphere r ${list(r.radius)[0] ?? "?"} mm at (${at})${r.use_mni ? " MNI" : ""}`;
  }
  if (r._type === "AtlasROI") return `Cortex labels ${labels} · ${base(list(r.atlas_path)[0])}`;
  if (r._type === "SubcorticalROI") return `Subcortical labels ${labels} · ${base(list(r.atlas_path)[0])}`;
  return String(r._type ?? "ROI");
}

function mA(values: unknown): string {
  const xs = list(values).map(num).filter((x): x is number => x !== undefined);
  return xs.length ? `${xs.join(" / ")} mA` : "";
}

/**
 * The key settings of a step as `[label, value]` rows. Only fields the step's config sets are
 * shown; *steps* resolves a `sim_from_flex` step's source to the flex step it names.
 */
export function stepFacts(step: ProposalStep, steps: readonly ProposalStep[]): [string, string][] {
  const c = step.config as Config;
  const rows: [string, string][] = [];
  const add = (label: string, value: unknown) => {
    if (value !== undefined && value !== null && value !== "") rows.push([label, String(value)]);
  };
  if (step.kind.startsWith("flex")) {
    add("Goal", GOAL_LABEL[String(c.goal)] ?? c.goal);
    add("Target", roiLabel(c.roi));
    add("Current", num(c.current_mA) !== undefined ? `${c.current_mA} mA per channel` : undefined);
    const e = (c.electrode ?? {}) as Config;
    add("Electrodes", e.shape ? `${e.shape} ${list(e.dimensions).join(" × ")} mm` : undefined);
    add("Run name", base(c.output_folder));
    if ((num(c.n_multistart) ?? 1) > 1) add("Restarts", c.n_multistart);
    if (c.enable_mapping) add("Map to net", c.eeg_net);
  } else if (step.kind === "sim") {
    for (const m of list(c.montages) as Config[]) {
      const pairs = (list(m.electrode_pairs) as unknown[][]).map((p) => p.map((x) => (Array.isArray(x) ? "xyz" : x)).join("–")).join(", ");
      add("Montage", `${m.name} · ${pairs}${m.eeg_net ? ` · ${m.eeg_net}` : ""}`);
    }
    add("Currents", mA(c.intensities));
    add("Conductivity", c.conductivity);
  } else if (step.kind === "sim_from_flex") {
    const source = steps.find((s) => s.id === c.flex_step);
    add("Electrodes from", source ? `step ${source.id} (${base((source.config as Config).output_folder)})` : c.flex_run);
    add("Placement", c.eeg_net ?? "the run's mapped net, else its optimised positions");
    add("Currents", mA(c.intensities) || "the run's own");
    add("Conductivity", c.conductivity);
    for (const [sid, r] of Object.entries((step.resolved ?? {}) as Record<string, Config>)) {
      add(`Resolved (${sid})`, `${r.placement} · ${mA(r.intensities)}`);
    }
  } else if (step.kind === "pre") {
    const stages = [
      c.convert_dicom && "DICOM import",
      c.run_fastsurfer && "FastSurfer",
      c.create_m2m && "head model (charm)",
      c.run_freesurfer && "FreeSurfer",
      c.run_qsiprep && "QSIPrep",
      c.run_qsirecon && "QSIRecon",
    ].filter(Boolean);
    add("Stages", stages.join(", "));
  } else if (step.kind === "ex" || step.kind === "mex") {
    add("Run name", c.run_name);
    add("Leadfield", base(c.leadfield_hdf));
  }
  return rows;
}

/** Live step state: the job store when it knows every job of the step, else the server's. */
export function liveStepState(step: ProposalStep, jobs: Record<string, JobStatus>): StepState {
  const known = step.job_ids.map((id) => jobs[id]).filter((j): j is JobStatus => j !== undefined);
  if (step.job_ids.length === 0 || known.length !== step.job_ids.length) return step.state;
  const states = known.map((j) => j.state);
  if (states.every((s) => s === "succeeded")) return "succeeded";
  if (states.some((s) => s === "failed" || s === "cancelled" || s === "lost" || s === "skipped")) return "failed";
  return states.includes("running") ? "running" : "queued";
}

export const STEP_STATE_KIND: Record<StepState, "neutral" | "accent" | "success" | "warning" | "danger"> = {
  proposed: "neutral",
  waiting: "neutral",
  queued: "neutral",
  running: "accent",
  succeeded: "success",
  failed: "danger",
  skipped: "warning",
  error: "danger",
};

/** Every output a step would replace, with the step that replaces it and whether it may. */
export function overwrites(p: Proposal): { step: string; path: string; allowed: boolean }[] {
  return p.steps.flatMap((s) => (s.plan?.will_overwrite ?? []).map((path) => ({ step: s.id, path, allowed: s.overwrite })));
}

/** Errors and missing inputs that would make the server refuse the approval. */
export function blockers(p: Proposal): string[] {
  return p.steps.flatMap((s) => [
    ...(s.plan?.errors ?? []).map((e) => `Step ${s.id}: ${e}`),
    ...(s.plan?.missing_inputs ?? []).map((m) => `Step ${s.id}: missing ${m.what}`),
  ]);
}

export function totalEta(p: Proposal): number | null {
  const etas = p.steps.map((s) => s.plan?.eta_minutes).filter((x): x is number => typeof x === "number");
  return etas.length ? etas.reduce((a, b) => a + b, 0) : null;
}

/** Who proposed it, as the card's byline says it. */
export function proposer(p: Proposal): string {
  return p.client || (p.created_by === "agent" ? "your AI agent" : p.created_by);
}

/** Proposals the Jobs page shows: everything undecided, in flight or failed (until dismissed), and the last day's rest. */
export function visibleProposals(all: readonly Proposal[], now = Date.now()): Proposal[] {
  return all.filter(
    (p) =>
      p.status === "pending" ||
      p.status === "running" ||
      p.status === "failed" ||
      now - Date.parse(p.updated_at ?? p.created_at) < 86_400_000,
  );
}

/** Done or rejected: these leave the card strip for the finished list. A failed plan stays a full card (with Retry) until dismissed. */
export function isFinished(p: Proposal): boolean {
  return p.status === "succeeded" || p.status === "rejected";
}

export function pendingCount(all: readonly Proposal[] | undefined): number {
  return (all ?? []).filter((p) => p.status === "pending").length;
}
