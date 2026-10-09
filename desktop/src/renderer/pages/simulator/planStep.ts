/**
 * A plan step on the Simulator (`app/proposals/stepForm.tsx`): the step's config as the jobs table's
 * rows, and the rows back as the step's one config. A step runs ONE config on every subject, so
 * the table holds the same rows for each subject; `sim_from_flex` is one Flex-result row per
 * subject, whose run is the flex step's (not run yet) or a finished run.
 */
import type { StepEdit } from "../../app/proposals/api";
import type { PlanStepTarget } from "../../app/proposals/stepForm";
import { buildSimulationConfig, type GlobalParams } from "./buildConfig";
import { settingsFromConfig } from "./candidateHandoff";
import { isRunnableRow, newRowId, settingsFor, type SelectedRow } from "./types";

type Config = Record<string, unknown>;
const object = (v: unknown): v is Config => !!v && typeof v === "object" && !Array.isArray(v);
const named = (pairs: unknown[]): pairs is [string, string][] =>
  pairs.every((p) => Array.isArray(p) && p.length === 2 && p.every((v) => typeof v === "string"));

function montageRow(subjectId: string, m: Config, currents: string, settings: SelectedRow["settings"]): SelectedRow {
  const pairs = Array.isArray(m.electrode_pairs) ? (m.electrode_pairs as unknown[]) : [];
  const source = m.mode === "freehand" ? "freehand" : m.mode === "flex_mapped" || m.mode === "flex_free" ? "flex" : "montage";
  const labels = named(pairs);
  return {
    id: newRowId(),
    subjectId,
    source,
    name: typeof m.name === "string" ? m.name : "",
    kind: source === "montage" ? (pairs.length > 2 ? "multi_polar" : "uni_polar") : undefined,
    eegNet: typeof m.eeg_net === "string" ? m.eeg_net : undefined,
    pairs: labels ? pairs : undefined,
    xyzPairs: labels ? undefined : (pairs as NonNullable<SelectedRow["xyzPairs"]>),
    currents,
    settings,
  };
}

/** The step as jobs-table rows: each subject × each montage, or one flex row per subject. */
export function simStepRows(step: PlanStepTarget): SelectedRow[] {
  const c = step.config;
  const settings = settingsFromConfig(c);
  const currents = Array.isArray(c.intensities) ? c.intensities.join(",") : "";
  if (step.kind === "sim_from_flex") {
    return step.subjectIds.map((subjectId) => ({
      id: newRowId(),
      subjectId,
      source: "flex" as const,
      name: (typeof c.flex_run === "string" ? c.flex_run : step.flexRun) ?? "",
      eegNet: typeof c.eeg_net === "string" ? c.eeg_net : undefined,
      currents,
      settings,
      planFlexStep: typeof c.flex_step === "string" ? c.flex_step : undefined,
    }));
  }
  const montages = (Array.isArray(c.montages) ? c.montages : []).filter(object);
  return step.subjectIds.flatMap((s) => montages.map((m) => montageRow(s, m, currents, settings)));
}

/** What a row runs, without who it runs on — the part every subject's rows must share. */
function rowContent(row: SelectedRow, params: GlobalParams): string {
  return JSON.stringify([row.source, row.kind, row.eegNet, row.name, row.pairs, row.xyzPairs, row.currents, settingsFor(row, params), row.planFlexStep]);
}

/** "Save to plan": the rows as the step's config and subjects; throws when they cannot be one step. */
export function simStepEdit(step: PlanStepTarget, rows: SelectedRow[], params: GlobalParams): StepEdit {
  const subjects = [...new Set(rows.map((r) => r.subjectId).filter(Boolean))];
  if (subjects.length === 0) throw new Error("Add a job row with a subject.");
  const per = subjects.map((s) => JSON.stringify(rows.filter((r) => r.subjectId === s).map((r) => rowContent(r, params))));
  if (per.some((x) => x !== per[0])) throw new Error("A plan step runs the same jobs on every subject: make each subject's rows match.");
  const mine = rows.filter((r) => r.subjectId === subjects[0]);
  const settings = buildSimulationConfig(mine[0]!, params);
  for (const key of ["subject_id", "montages", "intensities"]) delete settings[key];
  const config: Config = { ...step.config, ...settings };
  delete config.subject_id;
  // Sent only when set (buildSimulationConfig): unset in the form means unset in the step.
  for (const key of ["tissue_conductivities", "carrier_only"]) if (!(key in settings)) delete config[key];

  if (step.kind === "sim_from_flex") {
    const row = mine[0]!;
    if (mine.length !== 1 || row.source !== "flex" || !row.name) throw new Error("This step simulates one flex-search result: keep one Flex result row per subject.");
    for (const key of ["flex_step", "flex_run", "eeg_net", "intensities", "montages"]) delete config[key];
    if (row.planFlexStep && row.name === step.flexRun) config.flex_step = row.planFlexStep;
    else config.flex_run = row.name;
    if (row.eegNet) config.eeg_net = row.eegNet;
    if (row.currents.trim()) config.intensities = buildSimulationConfig(row, params).intensities;
    return { config, subject_ids: subjects };
  }

  if (!mine.every(isRunnableRow)) throw new Error("Complete every job row: a montage and its electrodes.");
  const built = mine.map((r) => buildSimulationConfig(r, params));
  const shared = (b: Config) => JSON.stringify({ ...b, montages: undefined });
  if (built.some((b) => shared(b) !== shared(built[0]!))) throw new Error("Every montage of a plan step runs with the same currents and settings.");
  config.montages = built.map((b) => (b.montages as Config[])[0]);
  config.intensities = built[0]!.intensities;
  return { config, subject_ids: subjects };
}
