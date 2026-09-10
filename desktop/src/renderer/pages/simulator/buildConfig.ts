import { settingsFor, type JobSettings, type SelectedRow } from "./types";
import type { CustomConductivities } from "./ConductivityDialog";
import type { MontageSources } from "./api";

/**
 * The page's **defaults**. A row that never disagreed with them is built from them; a row the user
 * customised carries its own `settings` and is built from those (`settingsFor`).
 */
export type GlobalParams = JobSettings & { customConductivities: CustomConductivities };

function parseIntensities(s: string): number[] {
  const values = s
    .split(",")
    .map((v) => Number(v.trim()))
    .filter((v) => !Number.isNaN(v));
  if (values.length === 1) {
    const only = values[0] ?? 1.0;
    return [only, only];
  }
  return values;
}

/**
 * Builds the JSON body for one (subject, montage) job — one `SimulationConfig` with exactly one
 * `Montage`, mirroring `tit.sim.utils.build_simulation_config_for_job`. Every key here is a real
 * `SimulationConfig` field: `contracts/generated/config.schema.json`'s `SimulationConfig` now sets
 * `additionalProperties: false` (ra_11 finding 3's contract tightening), so an extra convenience
 * key here would fail schema validation even though the real server's default lenient
 * `deserialize_config(strict=False)` would have silently dropped it — see PARITY.md's updated
 * note on the plan-only `name` field this function used to add.
 */
export function buildSimulationConfig(row: SelectedRow, defaults: GlobalParams): Record<string, unknown> {
  const params = settingsFor(row, defaults) as GlobalParams;
  // A flex row is `flex_mapped` when it carries an EEG net (its electrodes are that cap's labels)
  // and `flex_free` when it does not (the optimiser's own XYZ coordinates) — the same distinction
  // `Montage.Mode` makes, and the reason a run with no mapping file is still simulable.
  const mode =
    row.source === "montage" ? "net" : row.source === "flex" ? (row.eegNet ? "flex_mapped" : "flex_free") : "freehand";
  const electrodePairs =
    row.source === "freehand" || (row.source === "flex" && !row.eegNet)
      ? (row.xyzPairs ?? []).map(([a, b]) => [a, b])
      : (row.pairs ?? []).map(([a, b]) => [a, b]);

  const montage: Record<string, unknown> = {
    // `_type` is required by contracts/generated/config.schema.json's `Montage` def — `Montage` is itself a member
    // of the top-level `PipelineConfig` union, so `dev/build_schema.py` marks it with the same
    // `_type` discriminator (config_io.py's CONFIG_CLASS_REGISTRY) even when nested, and
    // `deserialize_config` checks it whenever present.
    _type: "Montage",
    name: row.name,
    mode,
    electrode_pairs: electrodePairs,
    eeg_net: row.eegNet ?? null,
  };

  const config: Record<string, unknown> = {
    subject_id: row.subjectId,
    montages: [montage],
    conductivity: params.conductivity,
    aniso_maxratio: params.anisoMaxratio ?? 10,
    aniso_maxcond: params.anisoMaxcond ?? 2,
    intensities: parseIntensities(row.currents),
    electrode_shape: params.electrodeShape,
    electrode_dimensions: params.dimensions,
    gel_thickness: params.gelThickness,
    output_fields: params.outputFields,
    map_to_fsavg: params.mapToFsavg ?? false,
  };
  if (Object.keys(params.customConductivities).length > 0) {
    config.tissue_conductivities = params.customConductivities;
  }
  return config;
}

/**
 * `PlanRequest.montage_sources` for one row — **never sent for a row this page has already
 * resolved**, which since the flex fix is every row.
 *
 * The reason is not tidiness: `tit/server/routes/plan.py` resolves `montage_sources` into montages
 * *in addition to* `config.montages`, so a flex or free-hand row that sent both was planned twice —
 * two `PlanJob`s for one job, under two different output directories. Job submission has to embed a
 * fully-resolved `Montage` anyway (`POST /api/jobs`'s `JobSpec` has no `montage_sources` field), so
 * the resolved config is the single source of truth and this returns nothing. Kept as the one
 * documented place the decision lives, rather than deleted, because the field is still part of the
 * frozen `PlanRequest` contract.
 */
export function buildMontageSources(): MontageSources | undefined {
  return undefined;
}
