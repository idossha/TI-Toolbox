/**
 * One row of the Simulator's **Jobs table** = one job = one `SimulationConfig` with exactly one
 * `Montage` (`tit.sim.utils.build_simulation_config_for_job`).
 *
 * 2026-09-06 (maintainer): the page used to hold a *global* subject set and a montage list that
 * was fanned out across it, so "which subject runs which montage" was a cross-product the user had
 * to hold in their head — 2.5.0's job cards, where a card owned its subject, its source, its
 * montage and its currents, said it outright. The row owns all of that again: `subjectId` is a
 * cell, not a page-level control.
 *
 * A row is allowed to be *incomplete* while it is being filled in (`subjectId` or `name` empty);
 * `isRunnableRow` is the one gate between the table and the plan.
 */
export type MontageSource = "montage" | "flex" | "freehand";

export interface SelectedRow {
  /** Stable client-side id for React keys — `newRowId()`, never derived from the contents (two
   *  rows may legitimately be the same job for the same subject before one is re-pointed). */
  id: string;
  /** The subject this job runs on. `""` until the row's Subject cell is filled in. */
  subjectId: string;
  source: MontageSource;
  /** Montage-catalog kind, only meaningful when source === "montage". */
  kind?: "uni_polar" | "multi_polar";
  /** EEG net filename, meaningful for source === "montage" and "flex" (mapped mode). */
  eegNet?: string;
  /** Montage name / flex-run name / freehand config name — becomes the SimulationConfig's montage
   *  name. `""` until the row's Montage cell is filled in. */
  name: string;
  /** Electrode pairs as label strings ([]  for flex/freehand, resolved separately). */
  pairs?: [string, string][];
  /** Resolved XYZ pairs for flex (free) or freehand sources. */
  xyzPairs?: [[number, number, number], [number, number, number]][];
  /** Per-row currents (mA), comma-separated — seeded from the row's polarity, editable. */
  currents: string;
  /**
   * This job's own electrodes / conductivity / output fields.
   *
   * Maintainer, 2026-09-06: *"the three global sections should be the **default** of the
   * simulator; however each job should have its own settings configuration."* `undefined` means
   * the row still follows the page's defaults — read live, so changing a default updates exactly
   * the rows that never disagreed with it and leaves a customised row alone. Duplicating a row
   * copies whatever it had.
   */
  settings?: JobSettings;
}

/** Everything about a job that is not its subject, its electrodes' *positions* or its currents. */
export interface JobSettings {
  conductivity: string;
  electrodeShape: "ellipse" | "rect";
  dimensions: [number, number];
  gelThickness: number;
  outputFields: string[];
  mapToFsavg?: boolean;
  customConductivities: Record<string, number>;
}

/** The page's own defaults, as they start: SimNIBS's own, and the one field 2.5.0 wrote. */
export const DEFAULT_JOB_SETTINGS: JobSettings = {
  conductivity: "scalar",
  electrodeShape: "ellipse",
  dimensions: [8, 8],
  gelThickness: 4,
  outputFields: ["TI_max"],
  mapToFsavg: false,
  customConductivities: {},
};

/** What this row will actually run with: its own settings, or the page's defaults. */
export function settingsFor(row: SelectedRow, defaults: JobSettings): JobSettings {
  return row.settings ?? defaults;
}

/** Has the user given this row settings of its own? */
export function isCustomised(row: SelectedRow): boolean {
  return !!row.settings;
}

/**
 * The muted chip line 2 shows for a customised row: only what *differs* from the defaults, in the
 * order the sections are in. Empty when the row's own settings happen to equal the defaults.
 */
export function settingsSummary(settings: JobSettings, defaults: JobSettings): string {
  const parts: string[] = [];
  if (settings.electrodeShape !== defaults.electrodeShape || settings.dimensions[0] !== defaults.dimensions[0] || settings.dimensions[1] !== defaults.dimensions[1]) {
    parts.push(`${settings.electrodeShape === "rect" ? "rect" : "ellipse"} ${settings.dimensions[0]}×${settings.dimensions[1]}`);
  }
  if (settings.gelThickness !== defaults.gelThickness) parts.push(`gel ${settings.gelThickness}`);
  if (settings.conductivity !== defaults.conductivity) parts.push(settings.conductivity);
  const overrides = Object.keys(settings.customConductivities).length;
  if (overrides !== Object.keys(defaults.customConductivities).length) {
    parts.push(`${overrides} tissue override${overrides === 1 ? "" : "s"}`);
  }
  if (settings.outputFields.join(",") !== defaults.outputFields.join(",")) parts.push(settings.outputFields.join(", ") || "no fields");
  if (!!settings.mapToFsavg !== !!defaults.mapToFsavg) parts.push(settings.mapToFsavg ? "fsaverage" : "no fsaverage");
  return parts.join(" · ");
}

/** The Source cell's options, in table order. */
export const SOURCE_OPTIONS: { value: MontageSource; label: string }[] = [
  { value: "montage", label: "Montage" },
  { value: "flex", label: "Flex result" },
  { value: "freehand", label: "Free-hand" },
];

let rowSeq = 0;

/** A fresh row id. Monotonic within the session; never encodes the row's contents. */
export function newRowId(): string {
  rowSeq += 1;
  return `job-${rowSeq}`;
}

/** A blank job row, ready for its Subject and Montage cells. */
export function emptyRow(subjectId = "", source: MontageSource = "montage", eegNet?: string): SelectedRow {
  return { id: newRowId(), subjectId, source, eegNet, name: "", currents: "1.0,1.0" };
}

/**
 * Is this row a job? A row with no subject or no montage/run picked yet is a row the user is still
 * filling in — it is shown, it just is not planned or submitted. A flex/free-hand row also needs
 * resolved electrodes, since `POST /api/jobs` carries a fully-resolved `Montage`.
 */
export function isRunnableRow(row: SelectedRow): boolean {
  if (!row.subjectId || !row.name) return false;
  if (row.source === "montage") return (row.pairs?.length ?? 0) > 0;
  return (row.pairs?.length ?? 0) > 0 || (row.xyzPairs?.length ?? 0) > 0;
}

/** How many electrode pairs a row carries, whichever form they came in. */
export function rowPairCount(row: SelectedRow): number {
  return row.pairs?.length ?? row.xyzPairs?.length ?? 0;
}

export const TISSUE_TABLE: { number: number; name: string; defaultValue: number; reference: string }[] = [
  { number: 1, name: "White matter", defaultValue: 0.126, reference: "Wagner et al., 2004" },
  { number: 2, name: "Gray matter", defaultValue: 0.275, reference: "Wagner et al., 2004" },
  { number: 3, name: "CSF", defaultValue: 1.654, reference: "Wagner et al., 2004" },
  { number: 4, name: "Bone", defaultValue: 0.01, reference: "Wagner et al., 2004" },
  { number: 5, name: "Scalp", defaultValue: 0.465, reference: "Wagner et al., 2004" },
  { number: 6, name: "Eye balls", defaultValue: 0.5, reference: "Opitz et al., 2015" },
  { number: 7, name: "Compact bone", defaultValue: 0.008, reference: "Opitz et al., 2015" },
  { number: 8, name: "Spongy bone", defaultValue: 0.025, reference: "Opitz et al., 2015" },
  { number: 9, name: "Blood", defaultValue: 0.6, reference: "Gabriel et al., 2009" },
  { number: 10, name: "Muscle", defaultValue: 0.16, reference: "Gabriel et al., 2009" },
  { number: 100, name: "Silicone rubber", defaultValue: 29.4, reference: "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS" },
  { number: 500, name: "Saline", defaultValue: 1.0, reference: "Saturnino et al., 2015" },
];

export interface OutputFieldSpec {
  name: string;
  description: string;
}

/** Selectable output fields in registry order (tit/constants.py FIELD_REGISTRY, minus mTI_max/TI_normal). */
export const OUTPUT_FIELDS: OutputFieldSpec[] = [
  { name: "TI_max", description: "Envelope modulation depth (peak-to-trough), maximised over direction (Grossman et al. 2017; Hirata et al. 2024)." },
  { name: "TI_avg", description: "Envelope modulation depth (peak-to-trough), averaged over sampled directions rather than maximised." },
  { name: "hf_peak", description: "Largest instantaneous magnitude of the summed carrier fields (peak-to-zero): max over sign choices of |sum_i s_i*E_i| (Cassarà et al. 2025, Eq. 3)." },
  { name: "hf_sar", description: "Sum of carrier power, sum_i |E_i|^2. Proportional to SAR but not calibrated: SAR = (sigma/2*rho)*hf_sar (Cassarà et al. 2025)." },
];

export const OUTPUT_FIELDS_HELP =
  "Which volume fields to compute and write for each simulation. TI_normal (surface normal component) is always computed for 2-pair TI and is not a choice here. " +
  "Cost: TI_avg adds a direction sweep; hf_peak and hf_sar are effectively free alongside a field that is already being computed.";

/** Which montage bucket a montage lives in: `uni_polar_montages` / `multi_polar_montages`. */
export type MontageKind = "uni_polar" | "multi_polar";

/**
 * The polarity a *newly drawn* montage will be saved as, inferred from the electrode pairs the
 * user picked rather than chosen up front: 2 pairs (4 electrodes) is a standard two-channel TI
 * montage, more than 2 pairs is multi-channel mTI. Matches `Montage.simulation_mode`, which
 * derives the same thing server-side from the pair count.
 *
 * For a montage that already exists in the catalog the polarity is NOT re-derived: it is the
 * bucket the montage is stored in (`Montages.nets[net].uni_polar` / `.multi_polar`), which is the
 * montage's own property and survives an odd pair count in a hand-written montage file.
 */
export function inferMontageKind(numPairs: number): MontageKind {
  return numPairs > 2 ? "multi_polar" : "uni_polar";
}

/** Human label for a polarity — the chip shown beside a montage in the table. */
export function polarityLabel(kind: MontageKind): string {
  return kind === "uni_polar" ? "TI" : "mTI";
}

/**
 * How many current values a montage takes: a uni-polar (TI) montage always takes 2 (one per
 * channel), a multi-polar (mTI) montage one per pair — `_validate_simulation_inputs`'s
 * `required_currents`.
 */
export function currentsCount(kind: MontageKind, numPairs: number): number {
  return kind === "uni_polar" ? 2 : Math.max(2, numPairs);
}

/** `1.0` per required current, comma-joined — the wire string a row starts with. */
export function defaultCurrentsFor(kind: MontageKind, numPairs: number): string {
  return Array(currentsCount(kind, numPairs)).fill("1.0").join(",");
}

/**
 * Default `1.0` per required current for a source with no catalog polarity (flex / free-hand):
 * 2 values for a 2-pair (TI) set, one per pair beyond that.
 */
export function defaultCurrents(numPairs: number): string {
  return defaultCurrentsFor(inferMontageKind(numPairs), numPairs);
}

export const CONDUCTIVITY_OPTIONS = [
  { value: "scalar", label: "Isotropic" },
  { value: "vn", label: "Anisotropic (volume-normalized)" },
  { value: "dir", label: "Anisotropic (direct)" },
  { value: "mc", label: "Anisotropic (mean conductivity)" },
];


/**
 * What the 3-D pane is showing for the job row the user clicked.
 *
 * Two shapes in one type because the pane takes both: a *named montage* is `net` + `pairs`
 * (electrode names on that net), a *free-hand set* is `positions` (millimetres in `subject`'s own
 * head mesh). `subject` is on both, because since 2026-09-06 the pane draws the row's own subject
 * rather than the packaged guide, and a coordinate is only meaningful against the head it came
 * from.
 */
export interface MontagePreview {
  name: string;
  subject?: string;
  net?: string;
  pairs?: [string, string][];
  positions?: { label?: string; x: number; y: number; z: number }[];
}
