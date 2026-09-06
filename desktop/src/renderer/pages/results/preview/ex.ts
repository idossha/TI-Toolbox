/**
 * An ex/mEx-search run's `run_config.json` and the ranking of its `final_output.csv` (program U14).
 * Shapes read from a real run: `derivatives/SimNIBS/sub-ernie/ex-search/docs_ex_symmetric/`.
 *
 * `final_output.csv` itself is already served as `TableData` by
 * `GET /api/catalog/ex-runs/{run}/results` — the preview does not re-read the file, it ranks the
 * rows the catalog returned. A 343-montage × 7-current-split run is 2 400 rows; the pane shows the
 * ten the search actually found, by `Composite_Index` descending, which is the column
 * `tit.catalog._ex_best` itself calls "best".
 */
import { formatDate, trimNumber, type SummaryRow } from "./simulation";

export interface ExRunSummary {
  rows: SummaryRow[];
  /** The bucket lists, one line per channel pole, for the electrode-bucket mode. */
  buckets: { label: string; electrodes: string[] }[];
}

/** The columns the ranked table shows, in the order it shows them. */
export const EX_TABLE_COLUMNS = [
  "Montage",
  "Current_Ch1_mA",
  "Current_Ch2_mA",
  // An mEx run's CSV names the same two quantities `mTImax_ROI`/`mTImean_ROI`, and carries four
  // current columns; listing both spellings keeps one projection for both kinds, and the columns a
  // given file does not have are dropped rather than rendered empty.
  "TImax_ROI",
  "mTImax_ROI",
  "TImean_ROI",
  "mTImean_ROI",
  "Focality",
] as const;

export const EX_RANK_COLUMN = "Composite_Index";

/**
 * Display names for the ranked table's headers. Only the two current columns are renamed: the CSV
 * spells them `Current_Ch1_mA`, 14 characters of header over a 3-character number, which cost more
 * of a 490px pane than `TImean_ROI` and `Focality` had left. The field columns keep the CSV's own
 * names — those are the words the maintainer reads in the file and in the docs.
 */
export const EX_COLUMN_LABELS: Record<string, string> = {
  Current_Ch1_mA: "Ch1 mA",
  Current_Ch2_mA: "Ch2 mA",
  Current_Ch3_mA: "Ch3 mA",
  Current_Ch4_mA: "Ch4 mA",
};

/**
 * `F7_P7 <> F3_PO7_I1-1.0mA_I2-1.0mA` → `F7_P7 <> F3_PO7`.
 *
 * `tit.opt.ex` writes each montage's currents into its name *and* into `Current_Ch<n>_mA` columns
 * of the same row, so in a 490 px pane the suffix costs ~180 px to say what the two columns beside
 * it already say — measured, it pushed `TImax_ROI` and `Focality` off the pane behind a horizontal
 * scrollbar. An mEx name carries four of them and is worse.
 */
export function shortMontage(name: string): string {
  return name.replace(/_I1-.*$/, "");
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

const BUCKET_LABELS: Record<string, string> = {
  e1_plus: "Channel 1 +",
  e1_minus: "Channel 1 −",
  e2_plus: "Channel 2 +",
  e2_minus: "Channel 2 −",
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

/**
 * The top `limit` rows of a `final_output.csv` table, by `Composite_Index` descending, projected
 * onto {@link EX_TABLE_COLUMNS}. Columns the file does not have are dropped rather than rendered
 * empty (an mEx run's CSV names its channels differently), and a table with no rank column keeps
 * its own order — the file is already written best-first by `tit.opt.ex`.
 */
export function rankExRows(table: ExTable | undefined, limit = 10): ExTable {
  if (!table || table.columns.length === 0) return { columns: [], rows: [] };
  const rankIndex = table.columns.indexOf(EX_RANK_COLUMN);
  const ordered =
    rankIndex === -1
      ? table.rows.slice()
      : table.rows.slice().sort((a, b) => {
          const av = typeof a[rankIndex] === "number" ? (a[rankIndex] as number) : Number.NEGATIVE_INFINITY;
          const bv = typeof b[rankIndex] === "number" ? (b[rankIndex] as number) : Number.NEGATIVE_INFINITY;
          return bv - av;
        });
  const keep = EX_TABLE_COLUMNS.map((name) => table.columns.indexOf(name)).filter((i) => i !== -1);
  // No overlap at all (an unknown CSV layout): show what the file has rather than nothing.
  const indices = keep.length ? keep : table.columns.map((_, i) => i);
  const montage = table.columns.indexOf("Montage");
  return {
    columns: indices.map((i) => table.columns[i] ?? ""),
    rows: ordered.slice(0, limit).map((row) =>
      indices.map((i) => {
        const value = row[i] ?? null;
        return i === montage && typeof value === "string" ? shortMontage(value) : value;
      }),
    ),
  };
}
