/**
 * An ex/mEx-search run's `run_config.json` (program U14), and the table shape the Results pane
 * renders. Shapes read from a real run: `derivatives/SimNIBS/sub-ernie/ex-search/docs_ex_symmetric/`.
 */
import { formatDate, trimNumber, type SummaryRow } from "./simulation";

export interface ExRunSummary {
  rows: SummaryRow[];
  /** The bucket lists, one line per channel pole, for the electrode-bucket mode. */
  buckets: { label: string; electrodes: string[] }[];
}

export interface ExTable {
  columns: string[];
  rows: (string | number | null)[][];
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(str).filter((s): s is string => s !== undefined) : [];
}

/** `.../ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5` → `EEG10-10_UI_Jurak_2007`. */
export function netFromLeadfield(hdf: string | undefined): string | undefined {
  if (!hdf) return undefined;
  const stem = (hdf.split("/").pop() ?? hdf).replace(/\.hdf5?$/i, "");
  if (stem.includes("_leadfield_")) return stem.split("_leadfield_")[1];
  if (stem.endsWith("_leadfield")) return stem.slice(0, -"_leadfield".length);
  return stem;
}

/** `<run>/run_config.json`. */
export function exRunConfigPath(runPath: string): string {
  return `${runPath.replace(/\/+$/, "")}/run_config.json`;
}

/** `run_config.json`'s `electrodes` keys (`tit/opt/ex/results.py::save_run_config`): four bucket
 * poles for Ex, eight for mEx, or one `electrodes` list for a pool run. */
const BUCKET_LABELS: Record<string, string> = {
  e1_plus: "Channel 1 +",
  e1_minus: "Channel 1 −",
  e2_plus: "Channel 2 +",
  e2_minus: "Channel 2 −",
  e3_plus: "Channel 3 +",
  e3_minus: "Channel 3 −",
  e4_plus: "Channel 4 +",
  e4_minus: "Channel 4 −",
  electrodes: "Pool",
};

export function parseExRunConfig(text: string): ExRunSummary | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
  const c = parsed as Record<string, unknown>;
  const rows: SummaryRow[] = [];

  const roi = str(c.roi_name);
  if (roi) {
    const radius = num(c.roi_radius);
    rows.push({ label: "ROI", value: radius === undefined ? roi : `${roi} · r ${trimNumber(radius)} mm` });
  }

  const net = netFromLeadfield(str(c.leadfield_hdf));
  if (net) rows.push({ label: "EEG net", value: net });

  const mode = str(c.electrode_mode);
  if (mode) {
    const symmetric = c.symmetric_bucket === true;
    const pairing = str(c.symmetry_pairing)?.replace(/_/g, " ");
    rows.push({
      label: "Electrodes",
      value: symmetric ? `${mode} · symmetric${pairing ? ` (${pairing})` : ""}` : mode,
    });
  }

  const combos = num(c.n_combinations);
  if (combos !== undefined) rows.push({ label: "Montages", value: combos.toLocaleString() });

  const total = num(c.total_current_mA);
  const step = num(c.current_step_mA);
  if (total !== undefined) {
    rows.push({
      label: "Current",
      value: step === undefined ? `${trimNumber(total)} mA` : `${trimNumber(total)} mA · step ${trimNumber(step)} mA`,
    });
  }
  const limit = num(c.channel_limit_mA);
  if (limit !== undefined) rows.push({ label: "Channel limit", value: `${trimNumber(limit)} mA` });

  const created = formatDate(str(c.created) ?? str(c.created_at));
  if (created) rows.push({ label: "Created", value: created });

  const buckets = Object.entries(BUCKET_LABELS)
    .map(([key, label]) => ({
      label,
      electrodes: stringList((c.electrodes as Record<string, unknown> | undefined)?.[key]),
    }))
    .filter((b) => b.electrodes.length > 0);

  return { rows, buckets };
}
