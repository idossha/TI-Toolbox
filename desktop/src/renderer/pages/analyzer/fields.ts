/**
 * Mirrors `tit.constants.FIELD_REGISTRY` (labels/descriptions ported verbatim). No `/api/schema`
 * field-metadata endpoint exists yet, so this is a local constant rather than a fetch — see
 * PARITY.md. `mTI_max` is skipped, matching `tit/gui/analyzer_tab.py`'s field combo: it and
 * `TI_max` are the same quantity (modulation depth) under the 2-pair/4-pair mesh spelling, and
 * `select_field_file` resolves whichever a given simulation actually wrote.
 */
export interface FieldSpec {
  name: string;
  kind: "functional" | "safety";
  units: string;
  description: string;
  /** Not exported to NIfTI — see `tit/analyzer/field_selector.py::_select_voxel`. */
  meshOnly?: boolean;
}

export const FIELD_REGISTRY: FieldSpec[] = [
  {
    name: "TI_max",
    kind: "functional",
    units: "V/m",
    description:
      "Envelope modulation depth (peak-to-trough), maximised over direction (Grossman et al. 2017; Hirata et al. 2024).",
  },
  {
    name: "TI_normal",
    kind: "functional",
    units: "V/m",
    description: "Modulation depth along the cortical surface normal.",
    meshOnly: true,
  },
  {
    name: "TI_avg",
    kind: "functional",
    units: "V/m",
    description:
      "Envelope modulation depth (peak-to-trough), averaged over sampled directions rather than maximised.",
  },
  {
    name: "hf_peak",
    kind: "safety",
    units: "V/m",
    description:
      "Largest instantaneous magnitude of the summed carrier fields (peak-to-zero): max over sign choices of |sum_i s_i·E_i| (Cassarà et al. 2025, Eq. 3).",
  },
  {
    name: "hf_sar",
    kind: "safety",
    units: "(V/m)²",
    description:
      "Sum of carrier power, sum_i |E_i|². Proportional to SAR but not calibrated: SAR = (σ/2ρ)·hf_sar (Cassarà et al. 2025).",
  },
];

export function fieldSpec(name: string): FieldSpec | undefined {
  return FIELD_REGISTRY.find((f) => f.name === name);
}

/** `mTI_max` is the mTI on-disk spelling of `TI_max` — treat it as that entry for tooltip lookup. */
export function fieldSpecForName(name: string): FieldSpec | undefined {
  if (name === "mTI_max") return fieldSpec("TI_max");
  return fieldSpec(name);
}

export const TI_NORMAL_VOXEL_HELP =
  "TI_normal is a surface (mesh) field and is not exported to NIfTI; select mesh space to analyze it.";
