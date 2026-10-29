import { appDefaults } from "../../forms/appDefaults";

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
  /** Transient: never submit the previous placement while cap assignment is in flight. */
  mappingPending?: boolean;
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
  /** Original candidate configuration preserves poses and provenance through normal job planning. */
  candidate?: { id: string; requestId?: string; run: string; config: Record<string, unknown>; originalConfig?: Record<string, unknown>; originalCurrents: string; originalSettings: JobSettings };
  /** A plan step's flex step (`planStep.ts`): this row simulates that step's run, which does not
   *  exist until the step has run, so it has no electrodes yet and only its placement is chosen. */
  planFlexStep?: string;

}

/** Everything about a job that is not its subject, its electrodes' *positions* or its currents. */
export interface JobSettings {
  conductivity: string;
  anisoMaxratio?: number;
  anisoMaxcond?: number;
  electrodeShape: "ellipse" | "rect";
  dimensions: [number, number];
  gelThickness: number;
  outputFields: string[];
  mapToMni?: boolean;
  mapToFsavg?: boolean;
  /** ΔF = 0 carrier-only control: both pairs at one frequency, in phase — no envelope; only the
   *  carrier fields are computed (`SimulationConfig.carrier_only`). 2-pair TI only. */
  carrierOnly?: boolean;
  customConductivities: Record<string, number>;
}

/** The page's own defaults, as they start: `x-app-defaults.sim` over `SimulationConfig`'s own. */
export function defaultJobSettings(): JobSettings {
  const d = appDefaults("sim", "SimulationConfig");
  return {
    conductivity: d.conductivity as string,
    anisoMaxratio: d.aniso_maxratio as number,
    anisoMaxcond: d.aniso_maxcond as number,
    electrodeShape: d.electrode_shape as JobSettings["electrodeShape"],
    dimensions: d.electrode_dimensions as [number, number],
    gelThickness: d.gel_thickness as number,
    outputFields: d.output_fields as string[],
    mapToMni: d.map_to_mni as boolean,
    mapToFsavg: d.map_to_fsavg as boolean,
    carrierOnly: d.carrier_only as boolean,
    customConductivities: (d.tissue_conductivities ?? {}) as Record<string, number>,
  };
}

/** What this row will actually run with: its own settings, or the page's defaults. */
export function settingsFor(row: SelectedRow, defaults: JobSettings): JobSettings {
  return row.settings ?? defaults;
}

/** Has the user given this row settings of its own? */
export function isCustomised(row: SelectedRow): boolean {
  return !!row.settings;
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
  if (row.mappingPending || !row.subjectId || !row.name) return false;
  if (sentPairCount(row) === 0) return false;
  return rowProblem(row) === null;
}

/** Does the job send XYZ coordinates (free-hand, an unmapped flex run) rather than cap labels? */
export function sendsXyz(row: SelectedRow): boolean {
  return row.source === "freehand" || (row.source === "flex" && !row.eegNet);
}

/** How many electrode pairs the job SENDS — the form `buildSimulationConfig` puts on the wire. */
function sentPairCount(row: SelectedRow): number {
  return (sendsXyz(row) ? row.xyzPairs?.length : row.pairs?.length) ?? 0;
}

/**
 * Two electrodes closer than this are one point: SimNIBS would place both pads on the same patch
 * of scalp, which shorts a channel (or a channel to itself). Real montages measure 11.5–127 mm.
 */
export const MIN_ELECTRODE_SEPARATION_MM = 1;

/**
 * Labels used by more than one electrode of a montage, sorted. An electrode cannot be its own
 * return (`["E1","E1"]`), and two channels on one electrode short each other (`E1–E2 · E1–E3`).
 * An empty slot (the editor's unpicked electrode) is not a label.
 */
export function repeatedElectrodes(pairs: readonly (readonly [string, string])[]): string[] {
  const labels = pairs.flat().filter((label) => label !== "");
  return [...new Set(labels.filter((label, i) => labels.indexOf(label) !== i))].sort();
}

/** The sentence a montage with a repeated electrode is refused with (row, editor and mapping). */
export function repeatedElectrodesSentence(repeated: string[]): string {
  return `${repeated.join(", ")} ${repeated.length === 1 ? "is" : "are"} used more than once: an electrode cannot be its own return, and two channels cannot share one.`;
}

type Xyz = readonly [number, number, number];

/**
 * 1-based electrode numbers (in pair order: pair 1 is electrodes 1 and 2) of every two electrodes
 * that are less than `MIN_ELECTRODE_SEPARATION_MM` apart — the XYZ form of a repeated electrode.
 */
export function coincidentElectrodes(pairs: readonly (readonly [Xyz, Xyz])[]): [number, number][] {
  const points = pairs.flat();
  const out: [number, number][] = [];
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const [a, b] = [points[i]!, points[j]!];
      if (Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) < MIN_ELECTRODE_SEPARATION_MM) out.push([i + 1, j + 1]);
    }
  }
  return out;
}

/**
 * How many currents the server needs for `numPairs` pairs: `SimulationConfig`'s `required` — 2 for
 * a 2-pair (TI) montage, one per pair for mTI. The pair count decides, not the catalog bucket.
 */
export function requiredCurrents(numPairs: number): number {
  return numPairs === 2 ? 2 : numPairs;
}

/** The row's currents, normalised to the count its polarity requires (extra values dropped, a
 *  short list padded with 1.0). */
export function currentValues(currents: string, count: number): number[] {
  // A blank cell is an *unset* current, not zero — `Number("")` is 0, which is why the empty wire
  // string used to normalise to `[0, 1]` rather than the documented `[1, 1]`.
  const parsed = currents.split(",").map((v) => (v.trim() === "" ? Number.NaN : Number(v.trim())));
  return Array.from({ length: count }, (_, i) => {
    const v = parsed[i];
    return v === undefined || Number.isNaN(v) ? 1.0 : v;
  });
}

/**
 * How many current inputs a row shows: a catalog montage's polarity is the bucket it lives in; a
 * flex or free-hand row has none, so it follows the pair count (`inferMontageKind`).
 */
export function rowCurrentsCount(row: SelectedRow): number {
  const pairs = rowPairCount(row);
  return currentsCount(row.kind ?? inferMontageKind(pairs), pairs);
}

/**
 * The currents the row's channel inputs SHOW — and therefore the `intensities` the job sends.
 * One function for both, so the table and the wire cannot disagree: a blank cell is 1.0 mA (never
 * `Number("") === 0`) and the list is exactly one value per channel.
 */
export function rowCurrents(row: SelectedRow): number[] {
  return currentValues(row.currents, rowCurrentsCount(row));
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * Why a row whose electrodes are known cannot run, in the words the row shows; `null` when it can
 * — or when it is still being filled in (no subject, no montage, no electrodes yet), which is not
 * a problem but an unfinished row. Each refusal is one the server makes (or a physical one it does
 * not make yet), so a row the table calls runnable is one the plan accepts.
 */
export function rowProblem(row: SelectedRow): string | null {
  const xyz = sendsXyz(row);
  const n = sentPairCount(row);
  if (n === 0) return null;
  if (!isValidPairCount(n)) {
    return `${plural(n, "channel")}: a montage needs 2 channels (TI) or an even number from 4 (mTI).`;
  }
  const shown = rowCurrentsCount(row);
  const required = requiredCurrents(n);
  if (shown !== required) {
    return `Saved as ${polarityLabel(row.kind ?? inferMontageKind(n))} with ${n} channels, which run with ${required} currents, not ${shown}: open it in the montage editor and save it again.`;
  }
  if (xyz) {
    const points = (row.xyzPairs ?? []).flat();
    const bad = points.findIndex((p) => !p.every(Number.isFinite));
    if (bad >= 0) return `Electrode ${bad + 1} has a coordinate that is not a number.`;
    const close = coincidentElectrodes(row.xyzPairs ?? []);
    if (close.length > 0) {
      const [a, b] = close[0]!;
      return `Electrodes ${a} and ${b} are less than ${MIN_ELECTRODE_SEPARATION_MM} mm apart: each electrode needs its own place on the scalp.`;
    }
  } else {
    const repeated = repeatedElectrodes(row.pairs ?? []);
    if (repeated.length > 0) return repeatedElectrodesSentence(repeated);
  }
  // An optimiser candidate keeps its signed currents (a negative channel is that channel's pads
  // swapped); everywhere else the inputs take 0 mA and up. Zero is never a current: a 0 mA
  // channel makes the TI envelope 0 everywhere.
  const currents = rowCurrents(row);
  const badCurrent = currents.findIndex((v) => !Number.isFinite(v) || (row.candidate ? v === 0 : v <= 0));
  if (badCurrent >= 0) {
    return `Channel ${badCurrent + 1} needs a current ${row.candidate ? "other than" : "above"} 0 mA.`;
  }
  return null;
}

/** How many electrode pairs a row carries, whichever form they came in. */
export function rowPairCount(row: SelectedRow): number {
  return row.pairs?.length ?? row.xyzPairs?.length ?? 0;
}

/** A carrier-only (ΔF = 0) control is a 2-pair TI job; `SimulationConfig` rejects it for mTI. */
export function carrierOnlyAllowed(row: SelectedRow): boolean {
  return row.kind !== "multi_polar" && inferMontageKind(rowPairCount(row)) === "uni_polar";
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
  { name: "TI_avg", description: "Envelope modulation depth (peak-to-trough), averaged over all directions rather than maximised." },
  { name: "hf_peak", description: "Largest instantaneous magnitude of the summed carrier fields (peak-to-zero): max over sign choices of |sum_i s_i*E_i| (Cassarà et al. 2025, Eq. 3)." },
  { name: "hf_sar", description: "Sum of carrier power, sum_i |E_i|^2. Proportional to SAR but not calibrated: SAR = (sigma/2*rho)*hf_sar (Cassarà et al. 2025)." },
  { name: "hf_power_density", description: "Time-averaged carrier power absorbed per volume, (1/2) sum_i E_i.sigma.E_i with the simulation's own conductivity; SAR = hf_power_density/rho (IEEE C95.1-2019)." },
];

/** The only fields defined without an envelope — what a carrier-only (ΔF = 0) job may compute. */
export const CARRIER_FIELDS = ["hf_peak", "hf_sar", "hf_power_density"];

/** What switching carrier-only on ticks when no carrier field is ticked: the two fields that need no conductivity. */
export const DEFAULT_CARRIER_FIELDS = ["hf_peak", "hf_sar"];

export const CARRIER_ONLY_HELP =
  "A control with no temporal interference: both channels run at the same carrier frequency (ΔF = 0) and in phase, " +
  "so there is no beat and no envelope. The carriers add as one fixed field, so hf_peak = |E1+E2|, hf_sar = |E1+E2|² and hf_power_density = ½(E1+E2)·σ·(E1+E2) " +
  "(coherent superposition, Cassarà et al. 2025) instead of the TI worst case max(|E1+E2|, |E1−E2|). " +
  "Only hf_peak, hf_sar and hf_power_density are computed; TI_max, TI_avg and TI_normal are undefined. 2-channel TI montages only.";

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

/**
 * `tit.constants.is_valid_pair_count`: 2 pairs (TI) or an even count from 4 (mTI). An odd count
 * leaves a channel with nothing to beat against, and the server refuses it.
 */
export function isValidPairCount(n: number): boolean {
  return n === 2 || (n >= 4 && n % 2 === 0);
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

