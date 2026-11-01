/** Candidate metrics are optimization estimates, comparable only within their recorded domain. */
export type CandidateKind = "flex" | "ex" | "mex";
export type Metric = "roi_mean" | "roi_p99_9" | "background_mean" | "background_p95" | "contrast";
export interface Candidate {
  id: string;
  objective: number | null;
  objective_label: string;
  objective_direction: "minimize" | "maximize";
  metrics: Partial<Record<Metric, number | null>>;
  metric_labels: Partial<Record<Metric, string>>;
  comparison_key: string | null;
  /** Ex/mEx: the row of `final_output.csv` as written, keyed by column in the file's order. */
  csv?: Record<string, string>;
  positions?: [number, number, number][];
  pairs?: [string, string][];
  eeg_net?: string;
  currents_mA?: (number | null)[];
  replay_note?: string;
  optimizer_termination?: {
    global: { success: boolean; message: string; iterations?: number; evaluations?: number };
    local?: { success: boolean; message: string; iterations?: number; evaluations?: number };
    accepted_stage: "global" | "local";
  };
}
export interface CandidatePage { candidates: Candidate[]; total: number; legacy: boolean }
export interface CandidateDetail { candidate: Candidate; simulation_config: Record<string, unknown> }
export interface CandidateRun { subject: string; kind: CandidateKind; run: string }
export const METRIC_LABELS: Record<Metric, string> = {
  roi_mean: "ROI mean (V/m)", roi_p99_9: "ROI p99.9 (V/m)",
  background_mean: "Non-ROI mean (V/m)", background_p95: "Non-ROI p95 (V/m)", contrast: "ROI / non-ROI ratio (see definition)",
};
export const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
/** The plot's horizontal axis for ex/mEx: the CSV's ROI mean (flex plots its recorded `roi_mean`). */
export const EX_X_COLUMN = "TImean_ROI";
/** A plot coordinate: an ex/mEx CSV cell as a number (empty is missing), or a flex metric. */
export function axisValue(candidate: Candidate, axis: string): number | null | undefined {
  if (!candidate.csv) return candidate.metrics[axis as Metric];
  const cell = candidate.csv[axis]?.trim();
  return cell ? Number(cell) : null;
}
const roiMean = (candidate: Candidate) => axisValue(candidate, candidate.csv ? EX_X_COLUMN : "roi_mean");
/** Ex/mEx vertical axes: the CSV's metric columns some row has a number for (not its montage, currents or x axis). */
export function csvMetricColumns(candidates: Candidate[]): string[] {
  return Object.keys(candidates[0]?.csv ?? {}).filter((column) => column !== EX_X_COLUMN && !column.startsWith("Current_") && candidates.some((c) => finite(axisValue(c, column))));
}
/** Which way an axis is better: 1 higher, -1 lower; 0 (e.g. HFpeak_Focality) records no preference, so no frontier. */
const AXIS_DIRECTION = new Map<string, 1 | -1>([["contrast", 1], ["background_mean", -1], ["background_p95", -1], ["TImax_ROI", 1], ["TImean_GM", -1], ["Focality", 1], ["Composite_Index", 1], ["TI_Selectivity", 1]]);
export const axisDirection = (axis: string): -1 | 0 | 1 => AXIS_DIRECTION.get(axis) ?? 0;
export function tradeoffCandidates(candidates: Candidate[], key: string | null, axis: string): Candidate[] {
  return key ? candidates.filter((c) => c.comparison_key === key && finite(roiMean(c)) && finite(axisValue(c, axis))) : [];
}
/** Nondominance among the displayed candidates; never compare raw optimization objectives. */
export function frontierIds(candidates: Candidate[], axis: string): Set<string> {
  const direction = axisDirection(axis);
  if (!direction) return new Set();
  const y = (c: Candidate) => axisValue(c, axis)!;
  const ordered = candidates.filter((c) => finite(roiMean(c)) && finite(axisValue(c, axis)))
    .toSorted((a, b) => -direction * (y(a) - y(b)) || roiMean(b)! - roiMean(a)!);
  const ids = new Set<string>();
  let best = -Infinity;
  for (let i = 0; i < ordered.length;) {
    const first = ordered[i]!;
    const target = roiMean(first)!;
    let end = i + 1;
    while (end < ordered.length && y(ordered[end]!) === y(first)) end++;
    if (target > best) {
      for (let j = i; j < end && roiMean(ordered[j]!) === target; j++) ids.add(ordered[j]!.id);
    }
    best = Math.max(best, target);
    i = end;
  }
  return new Set(candidates.filter((c) => ids.has(c.id)).map((c) => c.id));
}

/** Round-number ticks inside [min, max]: steps of 1, 2 or 5 x 10^k, about `count` of them. */
export function niceTicks(min: number, max: number, count = 5): { value: number; label: string }[] {
  if (!(max > min)) return Number.isFinite(min) ? [{ value: min, label: String(min) }] : [];
  const raw = (max - min) / count, power = 10 ** Math.floor(Math.log10(raw)), ratio = raw / power;
  const step = power * (ratio >= Math.sqrt(50) ? 10 : ratio >= Math.sqrt(10) ? 5 : ratio >= Math.SQRT2 ? 2 : 1);
  const decimals = Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
  const first = Math.ceil(min / step - 1e-9), last = Math.floor(max / step + 1e-9);
  return Array.from({ length: Math.max(0, last - first + 1) }, (_, k) => ({ value: (first + k) * step, label: ((first + k) * step).toFixed(decimals) }));
}

/** Translate archived display prose without changing its percentile or measurement domain. */
export function metricDefinition(text: string): string {
  return text.replace(/\bbackground\b/gi, "non-ROI").replace(/\btarget\b/gi, "ROI");
}

/** Blue-to-orange intensity scale: colour encodes ROI mean only, not a combined performance score. */
export function intensityColor(value: number, min: number, max: number): string {
  const t = max > min ? Math.max(0, Math.min(1, (value - min) / (max - min))) : 0.5;
  const low = [35, 133, 194], high = [213, 94, 0];
  return `rgb(${low.map((channel, index) => Math.round(channel + (high[index]! - channel) * t)).join(", ")})`;
}
