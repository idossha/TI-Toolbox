/**
 * One row = one (subject, montage) pair the user has selected to run — this is also exactly one
 * planned/submitted job, matching `tit.sim.utils.build_simulation_config_for_job` (one
 * `SimulationConfig` per subject/montage) and the plan panel's "one planned job per (subject,
 * montage)" (v3-build-plan.md P2 lane).
 */
export type MontageSource = "montage" | "flex" | "freehand";

export interface SelectedRow {
  /** Stable client-side id (subject + source + item key) used for React keys and dedup. */
  id: string;
  subjectId: string;
  source: MontageSource;
  /** Montage-catalog kind, only meaningful when source === "montage". */
  kind?: "uni_polar" | "multi_polar";
  /** EEG net filename, meaningful for source === "montage" and "flex" (mapped mode). */
  eegNet?: string;
  /** Montage name / flex-run name / freehand config name — becomes the SimulationConfig's montage name. */
  name: string;
  /** Electrode pairs as label strings ([]  for flex/freehand, resolved separately). */
  pairs?: [string, string][];
  /** Resolved XYZ pairs for flex (free) or freehand sources. */
  xyzPairs?: [[number, number, number], [number, number, number]][];
  /** Per-row default currents (mA), comma-separated — seeded from the global default, editable. */
  currents: string;
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

/**
 * Default `1.0` per required current: 2 values for a 2-pair (TI) montage, one per pair for a
 * 4+-pair (mTI) montage — matches `_validate_simulation_inputs`'s `required_currents`.
 */
export function defaultCurrents(numPairs: number): string {
  const n = numPairs <= 2 ? 2 : numPairs;
  return Array(n).fill("1.0").join(",");
}

export const CONDUCTIVITY_OPTIONS = [
  { value: "scalar", label: "Isotropic" },
  { value: "vn", label: "Anisotropic (volume-normalized)" },
  { value: "dir", label: "Anisotropic (direct)" },
  { value: "mc", label: "Anisotropic (mean conductivity)" },
];
