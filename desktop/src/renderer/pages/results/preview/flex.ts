/**
 * A flex-search run's three files → the rows and the electrode table the Results preview shows
 * (program U14). Shapes read from a real run on the maintainer's machine:
 * `derivatives/SimNIBS/sub-ernie/flex-search/VAL_lhipp_flex_focality/`.
 *
 * - `flex_meta.json` — goal, post-processing, current, electrode geometry, ROI, thresholds, the
 *   number of channels and multistarts, and `result.best_value`. **The catalog already carries
 *   this file** as `FlexRun.manifest` (`tit/catalog.py::flex_runs` reads it with
 *   `tit.opt.flex.manifest.read_manifest`), so the preview parses the object it already has rather
 *   than fetching the same JSON twice.
 * - `summary.txt` — SimNIBS' own optimiser log header: the optimiser name, the evaluation counts
 *   and the wall time. Not in `FlexRun.artifacts` (the catalog only lists png/csv/json), so it is
 *   read through `GET /api/files/text`.
 * - `electrode_positions.json` — the final positions, with the channel/array index of each.
 *
 * Every parser tolerates a missing or malformed file: a run that predates one of them still shows
 * the rows the other two produce.
 */
import { formatDate, trimNumber, type SummaryRow } from "./simulation";

export interface FlexElectrode {
  /** Stimulation channel index, from `channel_array_indices`. */
  channel: number;
  /** Electrode array index within that channel. */
  array: number;
  x: number;
  y: number;
  z: number;
}

export interface FlexSummary {
  rows: SummaryRow[];
  /** The optimiser's own goal-function value; negative for a maximised focality goal. */
  bestValue?: number;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

/** "subcortical · labeling.nii.gz label 17 · GM", or the spherical centre + radius. */
export function flexRoiLabel(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const roi = value as Record<string, unknown>;
  const parts: string[] = [];
  const type = str(roi.type);
  if (type) parts.push(type);
  const atlas = str(roi.atlas_path);
  if (atlas) {
    const file = atlas.split("/").pop() ?? atlas;
    const label = num(roi.label);
    parts.push(label === undefined ? file : `${file} label ${label}`);
  }
  const x = num(roi.x);
  const y = num(roi.y);
  const z = num(roi.z);
  if (x !== undefined && y !== undefined && z !== undefined) {
    const radius = num(roi.radius);
    parts.push(`(${[x, y, z].map(trimNumber).join(", ")})${radius === undefined ? "" : ` r ${trimNumber(radius)} mm`}`);
  }
  const tissues = str(roi.tissues);
  if (tissues) parts.push(tissues);
  return parts.length ? parts.join(" · ") : undefined;
}

/** `flex_meta.json`'s object (the catalog's `FlexRun.manifest`) → summary rows. */
export function flexManifestSummary(manifest: unknown): FlexSummary {
  const rows: SummaryRow[] = [];
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) return { rows };
  const m = manifest as Record<string, unknown>;

  const goal = str(m.goal);
  const postproc = str(m.postproc);
  if (goal) rows.push({ label: "Goal", value: postproc ? `${goal} · ${postproc}` : goal });

  const roi = flexRoiLabel(m.roi);
  if (roi) rows.push({ label: "ROI", value: roi });
  const nonRoi = flexRoiLabel(m.non_roi) ?? str(m.non_roi_method)?.replace(/_/g, " ");
  if (nonRoi) rows.push({ label: "Non-ROI", value: nonRoi });

  const net = str(m.eeg_net);
  if (net) rows.push({ label: "EEG net", value: net.replace(/\.csv$/i, "") });

  const current = num(m.current_mA);
  if (current !== undefined) rows.push({ label: "Current", value: `${trimNumber(current)} mA` });

  const pairs = num(m.n_pairs);
  const multistart = num(m.n_multistart);
  if (pairs !== undefined) {
    rows.push({
      label: "Channels",
      value: multistart === undefined ? String(pairs) : `${pairs} · ${multistart} multistart`,
    });
  }

  const thresholds = str(m.thresholds);
  if (thresholds) rows.push({ label: "Thresholds", value: thresholds });

  const distance = num(m.min_electrode_distance);
  if (distance !== undefined) rows.push({ label: "Min. distance", value: `${trimNumber(distance)} mm` });

  const result = m.result && typeof m.result === "object" ? (m.result as Record<string, unknown>) : undefined;
  const bestValue = num(result?.best_value);
  if (bestValue !== undefined) rows.push({ label: "Best value", value: trimNumber(bestValue) });
  const runs = Array.isArray(result?.all_values) ? (result?.all_values as unknown[]).length : undefined;
  if (runs) rows.push({ label: "Runs", value: String(runs) });
  if (result?.success === false) rows.push({ label: "Result", value: "did not converge" });

  const created = formatDate(str(m.created));
  if (created) rows.push({ label: "Created", value: created });

  return { rows, bestValue };
}

/** `<run>/summary.txt` — the path the preview reads the optimiser log header from. */
export function flexSummaryPath(runPath: string): string {
  return `${runPath.replace(/\/+$/, "")}/summary.txt`;
}

/** `<run>/electrode_positions.json`. */
export function flexPositionsPath(runPath: string): string {
  return `${runPath.replace(/\/+$/, "")}/electrode_positions.json`;
}

const SUMMARY_FIELDS: [label: string, pattern: RegExp, suffix?: string][] = [
  ["Optimizer", /^Optimizer:\s+(.+)$/m],
  ["FEM evaluations", /^Total number of FEM evaluations:\s+(\S+)/m],
  ["Function evaluations", /^Total number of function evaluations:\s+(\S+)/m],
  ["Duration", /^Duration \(setup and optimization\):\s+(\S+)/m, "s"],
];

/**
 * The handful of numbers worth lifting out of SimNIBS' 60-line `summary.txt`. Deliberately a small
 * fixed list rather than a generic "Key: value" scrape: that file also contains the optimiser's
 * whole settings dict and two 8-element bound vectors, none of which belongs in a 490 px pane.
 */
export function parseFlexSummaryText(text: string): SummaryRow[] {
  const rows: SummaryRow[] = [];
  for (const [label, pattern, suffix] of SUMMARY_FIELDS) {
    const match = pattern.exec(text);
    if (!match?.[1]) continue;
    const raw = match[1].trim();
    const value = Number(raw);
    if (label === "Duration" && Number.isFinite(value)) {
      rows.push({ label, value: `${Math.round(value)} s` });
    } else {
      rows.push({ label, value: Number.isFinite(value) ? `${trimNumber(value)}${suffix ?? ""}` : raw });
    }
  }
  return rows;
}

/**
 * `electrode_positions.json` → one row per electrode. `channel_array_indices` is parallel to
 * `optimized_positions`; when it is missing or shorter the index is derived from the position's own
 * order, which is what SimNIBS writes them in.
 */
export function parseFlexPositions(text: string): FlexElectrode[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return [];
  }
  if (!parsed || typeof parsed !== "object") return [];
  const doc = parsed as Record<string, unknown>;
  const positions = Array.isArray(doc.optimized_positions) ? doc.optimized_positions : [];
  const indices = Array.isArray(doc.channel_array_indices) ? doc.channel_array_indices : [];
  const out: FlexElectrode[] = [];
  positions.forEach((entry, i) => {
    if (!Array.isArray(entry) || entry.length < 3) return;
    const [x, y, z] = entry.map(num);
    if (x === undefined || y === undefined || z === undefined) return;
    const pair = Array.isArray(indices[i]) ? (indices[i] as unknown[]).map(num) : [];
    out.push({ channel: pair[0] ?? i, array: pair[1] ?? 0, x, y, z });
  });
  return out;
}
