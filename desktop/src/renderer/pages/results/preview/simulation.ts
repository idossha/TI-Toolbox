/**
 * `<simulation>/documentation/config.json` → the rows the Results preview shows above the files
 * (program U14: *"the preview says what the output is, not where it is"*).
 *
 * Pure, and defensive by construction: this file is written by `tit.sim` at run time and its shape
 * has changed between toolbox versions (`simulation_display_name`, `electrode_coordinate_source`
 * and the `mapping_options` block are all newer than the first runs on disk). Every field is
 * therefore read through a guard and a missing one produces *no row* rather than an "undefined" —
 * a preview that invents a value is worse than one that is short. Shapes are read from a real run:
 * `derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/documentation/config.json`.
 */

/** One label/value row of the summary. `mono` for paths and ids. */
export interface SummaryRow {
  label: string;
  value: string;
  mono?: boolean;
}

export interface SimulationSummary {
  /** "TI" / "mTI" — the simulation's own mode string, uppercased as the chip vocabulary spells it. */
  mode?: string;
  eegNet?: string;
  /** One entry per stimulation channel, already formatted as "F7 → P7". */
  pairs: string[];
  rows: SummaryRow[];
  createdAt?: string;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** `1` → "1", `1.5` → "1.5", `8.0` → "8" — a trailing ".0" is noise on a scientist's screen. */
export function trimNumber(value: number): string {
  return Number(value.toFixed(4)).toString();
}

function numberList(value: unknown): number[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out = value.map(num).filter((n): n is number => n !== undefined);
  return out.length === value.length && out.length > 0 ? out : undefined;
}

/** `[["F7","P7"],["F8","P8"]]` → `["F7 → P7", "F8 → P8"]`; an XYZ montage has no pairs to name. */
export function electrodePairs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const pair of value) {
    if (!Array.isArray(pair)) continue;
    const names = pair.map(str).filter((s): s is string => s !== undefined);
    if (names.length >= 2) out.push(`${names[0]} → ${names[1]}`);
  }
  return out;
}

/** "ellipse · 8 × 8 mm · gel 4 mm · rubber 2 mm", from whichever of those four the file has. */
export function electrodeGeometry(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const g = value as Record<string, unknown>;
  const parts: string[] = [];
  const shape = str(g.shape);
  if (shape) parts.push(shape);
  const dims = numberList(g.dimensions);
  if (dims) parts.push(`${dims.map(trimNumber).join(" × ")} mm`);
  const gel = num(g.gel_thickness);
  if (gel !== undefined) parts.push(`gel ${trimNumber(gel)} mm`);
  const rubber = num(g.rubber_thickness);
  if (rubber !== undefined) parts.push(`rubber ${trimNumber(rubber)} mm`);
  return parts.length ? parts.join(" · ") : undefined;
}

/** The `map_to_*` flags that are ON, in the file's own vocabulary; "none" when every one is off. */
export function mappingOptions(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const labels: Record<string, string> = {
    map_to_surf: "surface",
    map_to_vol: "volume",
    map_to_mni: "MNI",
    map_to_fsavg: "fsaverage",
  };
  const record = value as Record<string, unknown>;
  const on = Object.entries(labels)
    .filter(([key]) => record[key] === true)
    .map(([, label]) => label);
  if (!Object.keys(labels).some((key) => key in record)) return undefined;
  return on.length ? on.join(", ") : "none";
}

/** ISO-ish timestamp → "6 Jul 2026, 18:48"; the raw string back when it is not a date. */
export function formatDate(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Parse the file's text. Returns `undefined` when it is not JSON at all (a truncated write, an HTML
 * error page from a proxy) so the caller can fall back to the artifact list rather than render an
 * empty summary that looks like a simulation with no settings.
 */
export function parseSimulationConfig(text: string): SimulationSummary | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
  const c = parsed as Record<string, unknown>;

  const mode = str(c.simulation_mode)?.toUpperCase();
  const eegNet = str(c.eeg_net)?.replace(/\.csv$/i, "");
  const pairs = electrodePairs(c.electrode_pairs);
  const rows: SummaryRow[] = [];

  if (mode) rows.push({ label: "Mode", value: mode });
  if (eegNet) rows.push({ label: "EEG net", value: eegNet });
  else if (c.is_xyz_montage === true) rows.push({ label: "Montage", value: "XYZ coordinates" });

  const intensities = numberList(c.intensities);
  if (intensities) rows.push({ label: "Intensity", value: `${intensities.map(trimNumber).join(" / ")} mA` });

  const conductivity = str(c.conductivity);
  if (conductivity) {
    const aniso = num(c.aniso_maxratio);
    rows.push({
      label: "Conductivity",
      value: conductivity === "scalar" || aniso === undefined ? conductivity : `${conductivity} · max ratio ${trimNumber(aniso)}`,
    });
  }

  const geometry = electrodeGeometry(c.electrode_geometry);
  if (geometry) rows.push({ label: "Electrodes", value: geometry });

  const mapping = mappingOptions(c.mapping_options);
  if (mapping) rows.push({ label: "Mapped to", value: mapping });

  const tissues = str(c.tissues_in_niftis);
  if (tissues) rows.push({ label: "Tissues", value: tissues });

  const createdAt = str(c.created_at);
  const created = formatDate(createdAt);
  if (created) rows.push({ label: "Created", value: created });

  return { mode, eegNet, pairs, rows, createdAt };
}

/** The path of a simulation's config file, from the simulation directory the catalog reports. */
export function simulationConfigPath(simulationPath: string): string {
  return `${simulationPath.replace(/\/+$/, "")}/documentation/config.json`;
}
