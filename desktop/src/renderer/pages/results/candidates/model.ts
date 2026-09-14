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
export function tradeoffCandidates(candidates: Candidate[], key: string | null, background: Metric): Candidate[] {
  return key ? candidates.filter((c) => c.comparison_key === key && finite(c.metrics.roi_mean) && finite(c.metrics[background])) : [];
}
/** Nondominance among the displayed candidates; never compare raw optimization objectives. */
export function frontierIds(candidates: Candidate[], background: Metric): Set<string> {
  const ordered = candidates.filter((c) => finite(c.metrics.roi_mean) && finite(c.metrics[background]))
    .toSorted((a, b) => (background === "contrast" ? -1 : 1) * (a.metrics[background]! - b.metrics[background]!) || b.metrics.roi_mean! - a.metrics.roi_mean!);
  const ids = new Set<string>();
  let best = -Infinity;
  for (let i = 0; i < ordered.length;) {
    const first = ordered[i]!;
    const target = first.metrics.roi_mean!;
    let end = i + 1;
    while (end < ordered.length && ordered[end]!.metrics[background] === first.metrics[background]) end++;
    if (target > best) {
      for (let j = i; j < end && ordered[j]!.metrics.roi_mean === target; j++) ids.add(ordered[j]!.id);
    }
    best = Math.max(best, target);
    i = end;
  }
  return new Set(candidates.filter((c) => ids.has(c.id)).map((c) => c.id));
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
