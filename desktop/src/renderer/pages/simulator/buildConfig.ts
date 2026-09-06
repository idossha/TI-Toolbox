import type { SelectedRow } from "./types";
import type { CustomConductivities } from "./ConductivityDialog";
import type { MontageSources } from "./api";

export interface GlobalParams {
  conductivity: string;
  electrodeShape: "ellipse" | "rect";
  dimensions: [number, number];
  gelThickness: number;
  outputFields: string[];
  customConductivities: CustomConductivities;
}

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
 * `SimulationConfig` field: `contracts/schema.json`'s `SimulationConfig` now sets
 * `additionalProperties: false` (ra_11 finding 3's contract tightening), so an extra convenience
 * key here would fail schema validation even though the real server's default lenient
 * `deserialize_config(strict=False)` would have silently dropped it — see PARITY.md's updated
 * note on the plan-only `name` field this function used to add.
 */
export function buildSimulationConfig(row: SelectedRow, params: GlobalParams): Record<string, unknown> {
  const mode = row.source === "montage" ? "net" : row.source === "flex" ? "flex_mapped" : "freehand";
  const electrodePairs =
    row.source === "freehand"
      ? (row.xyzPairs ?? []).map(([a, b]) => [a, b])
      : (row.pairs ?? []).map(([a, b]) => [a, b]);

  const montage: Record<string, unknown> = {
    // `_type` is required by contracts/schema.json's `Montage` def — `Montage` is itself a member
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
    intensities: parseIntensities(row.currents),
    electrode_shape: params.electrodeShape,
    electrode_dimensions: params.dimensions,
    gel_thickness: params.gelThickness,
    output_fields: params.outputFields,
  };
  if (Object.keys(params.customConductivities).length > 0) {
    config.tissue_conductivities = params.customConductivities;
  }
  return config;
}

/**
 * `PlanRequest.montage_sources` for one row, for the plan preview only — job submission always
 * embeds a fully-resolved `Montage` (see `buildSimulationConfig` above) since `POST /api/jobs`
 * has no `montage_sources` field. Field names (`subject`/`run`, `subject`/`name`) match
 * `MontageSources` in `contracts/openapi.v1.yaml`, not the `subject_id`/`run_name` pair the
 * current backend route reads from inside `config` (see `planSim`'s doc comment for the gap).
 */
export function buildMontageSources(row: SelectedRow): MontageSources | undefined {
  if (row.source === "flex") {
    return { flex: [{ subject: row.subjectId, run: row.name, electrode_type: "mapped", eeg_net: row.eegNet }] };
  }
  if (row.source === "freehand") {
    return { freehand: [{ subject: row.subjectId, name: row.name }] };
  }
  return undefined;
}
