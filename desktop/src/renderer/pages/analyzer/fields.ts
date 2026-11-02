/**
 * Mirrors `tit.constants.FIELD_REGISTRY` (names, display labels and units ported verbatim;
 * `tests/test_field_registry.py` holds the two equal). What each field is, the wiki explains
 * (Output fields link there), so no description is copied here. No `/api/schema`
 * field-metadata endpoint exists, so this is a local constant rather than a fetch. `mTI_max` is
 * not a separate entry (as in the v2.5.0 Analyzer's field combo): it and `TI_max` are the same
 * quantity (modulation depth) under the 2-pair/4-pair mesh spelling, and `select_field_file`
 * resolves whichever a given simulation actually wrote.
 */
export interface FieldSpec {
  /** The saved name: values, IDs, configs and file names. */
  name: string;
  /** What a person reads: `X_{sub}` is drawn as a subscript (`<Subscripted>`). */
  label: string;
  kind: "functional" | "safety";
  units: string;
  /** Not exported to NIfTI — see `tit/analyzer/field_selector.py::_select_voxel`. */
  meshOnly?: boolean;
}

/** The absorbed-power-density field's saved name (and its registry entry below, kept a literal
 *  because tests read the list from source): a rename touches these two lines. */
export const HF_POWER_DENSITY = "hf_power_density";

export const FIELD_REGISTRY: FieldSpec[] = [
  {
    name: "TI_max",
    label: "TI_{max}",
    kind: "functional",
    units: "V/m",
  },
  {
    name: "TI_normal",
    label: "TI_{normal}",
    kind: "functional",
    units: "V/m",
    meshOnly: true,
  },
  {
    name: "TI_avg",
    label: "TI_{avg}",
    kind: "functional",
    units: "V/m",
  },
  {
    name: "hf_peak",
    label: "HF_{peak}",
    kind: "safety",
    units: "V/m",
  },
  {
    name: "hf_rms",
    label: "HF_{rms}",
    kind: "safety",
    units: "V/m",
  },
  {
    name: "hf_power_density",
    label: "p_{HF}",
    kind: "safety",
    units: "W/m³",
  },
];

export function fieldSpec(name: string): FieldSpec | undefined {
  return FIELD_REGISTRY.find((f) => f.name === name);
}

/** `mTI_max` is the mTI on-disk spelling of `TI_max` — treat it as that entry. */
export function fieldSpecForName(name: string): FieldSpec | undefined {
  if (name === "mTI_max") return fieldSpec("TI_max");
  return fieldSpec(name);
}

/** The mTI spelling of `TI_max` has its own label (tit.constants.FIELD_REGISTRY). */
const MTI_MAX_LABEL = "mTI_{max}";

/** The display label of a saved field name (`TI_{max}`, `HF_{rms}`); a name the registry does not
 *  list (`magnE`) is its own label. Render it with `<Subscripted>`. */
export function fieldLabel(name: string): string {
  if (name === "mTI_max") return MTI_MAX_LABEL;
  return fieldSpec(name)?.label ?? name;
}
