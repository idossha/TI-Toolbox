/**
 * Every network call the Optimizer page makes. Flex, Ex and mEx differ in their config body and
 * their `kind`, not in the endpoints they talk to, which is why they are one page.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { appDefaults } from "../../forms/appDefaults";

export type EegNet = components["schemas"]["EegNet"];
export type Leadfield = components["schemas"]["Leadfield"];
export type PlanResult = components["schemas"]["PlanResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type PipelineKind = components["schemas"]["PipelineKind"];
export type ExConfigBody = components["schemas"]["ExConfig"];
export type MExConfigBody = components["schemas"]["MExConfig"];
export type LeadfieldConfigBody = components["schemas"]["LeadfieldConfig"];
/** Flex configs are built field-by-field in `flexConfig.ts` and validated against the server schema. */
export type FlexConfigWire = Record<string, unknown>;

export async function getEegNets(subject: string): Promise<EegNet[]> {
  const path = "/api/catalog/eeg-nets";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path);
}

export async function getLeadfields(subject: string): Promise<Leadfield[]> {
  const path = "/api/catalog/leadfields";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path);
}

/** `POST /api/plan/{kind}` for one resolved config. Thrown errors surface as the plan's error. */
export async function planFor(kind: string, config: unknown, subjectIds: string[], overwrite = false): Promise<PlanResult> {
  const path = "/api/plan/{kind}";
  return unwrap(
    await api.POST(path, {
      params: { path: { kind: kind as PipelineKind } },
      body: { config: config as never, subject_ids: subjectIds, overwrite },
    }),
    path,
  );
}

export async function validateFor(kind: string, config: unknown): Promise<ValidateResult> {
  const path = "/api/validate/{kind}";
  return unwrap(
    await api.POST(path, { params: { path: { kind: kind as PipelineKind } }, body: { config: config as never } }),
    path,
  );
}

/** The electrode a leadfield is computed with, `LeadfieldConfig`'s (= `SimulationConfig`'s) names. */
export type LeadfieldElectrode = NonNullable<Leadfield["electrode"]>;

/** What the Generate-leadfield step starts from: `x-app-defaults.leadfield` over `LeadfieldConfig`'s
 *  own defaults (the Simulator's electrode, 1 mm gel). */
export function defaultLeadfieldElectrode(): LeadfieldElectrode {
  const d = appDefaults("leadfield", "LeadfieldConfig");
  return {
    electrode_shape: d.electrode_shape as LeadfieldElectrode["electrode_shape"],
    electrode_dimensions: d.electrode_dimensions as number[],
    gel_thickness: d.gel_thickness as number,
    rubber_thickness: d.rubber_thickness as number,
  };
}

/** The `LeadfieldConfig` the Generate-leadfield step submits: this net, with this electrode. */
export function leadfieldJobConfig(subjectId: string, net: string, electrode: LeadfieldElectrode): LeadfieldConfigBody {
  return { subject_id: subjectId, eeg_net: net, tissues: [1, 2], interpolation: null, overwrite: false, ...electrode };
}

/** Queues leadfield generation for a net that has none, with the electrode the user confirmed. */
export async function submitLeadfieldJob(subjectId: string, net: string, electrode: LeadfieldElectrode): Promise<JobStatus> {
  const config = leadfieldJobConfig(subjectId, net, electrode);
  const path = "/api/jobs";
  return unwrap(
    await api.POST(path, { body: { kind: "leadfield", config: config as never, subject_ids: [subjectId] } }),
    path,
  );
}

/**
 * How long generating this net's leadfield would take, in minutes — `PlanCost.eta_minutes` from
 * `POST /api/plan/leadfield` (no new endpoint: the leadfield kind already plans).
 *
 * The strip needs this per NET, not per page: one FEM solve per electrode means a 19-electrode cap
 * and a 256-electrode one differ by more than an order of magnitude, which is exactly what the
 * button's old hardcoded "≈40 min" hid. `null` when the server has no estimate (an unreadable cap).
 */
export async function planLeadfieldEta(
  subjectId: string,
  net: string,
): Promise<{ minutes: number | null; system: components["schemas"]["PlanSystem"] | null }> {
  // One FEM solve per electrode whatever its size: the estimate is the default electrode's.
  const result = await planFor("leadfield", leadfieldJobConfig(subjectId, net, defaultLeadfieldElectrode()), [subjectId]);
  return { minutes: result.cost?.eta_minutes ?? null, system: result.cost?.system ?? null };
}
