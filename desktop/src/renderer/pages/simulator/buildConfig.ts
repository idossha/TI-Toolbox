import { CARRIER_FIELDS, carrierOnlyAllowed, rowCurrents, sendsXyz, settingsFor, type JobSettings, type SelectedRow } from "./types";
import type { CustomConductivities } from "./ConductivityDialog";

/**
 * The page's **defaults**. A row that never disagreed with them is built from them; a row the user
 * customised carries its own `settings` and is built from those (`settingsFor`).
 */
export type GlobalParams = JobSettings & { customConductivities: CustomConductivities };

/**
 * Builds the JSON body for one (subject, montage) job — one `SimulationConfig` with exactly one
 * `Montage`, mirroring `tit.sim.utils.build_simulation_config_for_job`. Every key here is a real
 * `SimulationConfig` field: `contracts/generated/config.schema.json`'s `SimulationConfig` sets
 * `additionalProperties: false`, so an extra convenience key here (such as the plan-only `name`
 * this function once added) would fail schema validation even though the real server's default
 * lenient `deserialize_config(strict=False)` would have silently dropped it.
 */
export function buildSimulationConfig(row: SelectedRow, defaults: GlobalParams): Record<string, unknown> {
  const params = settingsFor(row, defaults) as GlobalParams;
  // Carrier-only is a 2-pair control; an mTI row (e.g. seeded from a carrier-only row) runs as
  // ordinary mTI, whose carriers are distinct frequencies by construction.
  const carrierOnly = !!params.carrierOnly && carrierOnlyAllowed(row);
  const carrierFields = params.outputFields.filter((f) => CARRIER_FIELDS.includes(f));
  const outputFields = carrierOnly ? (carrierFields.length ? carrierFields : [...CARRIER_FIELDS]) : params.outputFields;
  // A flex row is `flex_mapped` when it carries an EEG net (its electrodes are that cap's labels)
  // and `flex_free` when it does not (the optimiser's own XYZ coordinates) — the same distinction
  // `Montage.Mode` makes, and the reason a run with no mapping file is still simulable.
  const mode =
    row.source === "montage" ? "net" : row.source === "flex" ? (row.eegNet ? "flex_mapped" : "flex_free") : "freehand";
  const electrodePairs = sendsXyz(row)
    ? (row.xyzPairs ?? []).map(([a, b]) => [a, b])
    : (row.pairs ?? []).map(([a, b]) => [a, b]);

  const originalMontage = row.candidate?.config.montages as Record<string, unknown>[] | undefined;
  const montage: Record<string, unknown> = {
    ...originalMontage?.[0],
    // `_type` is required by contracts/generated/config.schema.json's `Montage` def — `Montage` is itself a member
    // of the top-level `PipelineConfig` union, so `dev/build_schema.py` marks it with the same
    // `_type` discriminator (config_io.py's CONFIG_CLASS_REGISTRY) even when nested, and
    // `deserialize_config` checks it whenever present.
    _type: "Montage",
    name: row.name,
    mode: row.candidate ? originalMontage?.[0]?.mode ?? mode : mode,
    electrode_pairs: electrodePairs,
    eeg_net: row.eegNet ?? null,
  };

  const config: Record<string, unknown> = {
    ...row.candidate?.config,
    subject_id: row.subjectId,
    montages: [montage],
    conductivity: params.conductivity,
    aniso_maxratio: params.anisoMaxratio ?? 10,
    aniso_maxcond: params.anisoMaxcond ?? 2,
    // Exactly what the row's channel inputs show (`rowCurrents`): one value per channel, a blank
    // cell 1.0 mA. The old parser read "" as [0, 0] and passed a short or long list through, so
    // a row showing 1.0 / 1.0 ran at 0 mA and a 4-pair row showing four inputs sent two.
    intensities: rowCurrents(row),
    electrode_shape: params.electrodeShape,
    electrode_dimensions: params.dimensions,
    gel_thickness: params.gelThickness,
    output_fields: outputFields,
    map_to_mni: params.mapToMni ?? false,
    map_to_fsavg: params.mapToFsavg ?? false,
    // Only sent when on: absent is the previous behaviour, for a server that predates the field.
    ...(carrierOnly ? { carrier_only: true } : {}),
  };
  if (row.candidate) delete config.tissue_conductivities;
  if (Object.keys(params.customConductivities).length > 0) {
    config.tissue_conductivities = params.customConductivities;
  }
  return config;
}
