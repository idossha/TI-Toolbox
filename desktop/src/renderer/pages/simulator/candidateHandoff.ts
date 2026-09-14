import { DEFAULT_JOB_SETTINGS, newRowId, type JobSettings, type SelectedRow } from "./types";

interface CandidateHandoff { id: string; requestId?: string; subject: string; kind: string; run: string; config: Record<string, unknown> }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const numbers = (value: unknown): value is number[] => Array.isArray(value) && value.every((v) => typeof v === "number" && Number.isFinite(v));
const xyz = (value: unknown): value is [number, number, number] => numbers(value) && value.length === 3;
/** Validate the handoff before adding it to the existing editable jobs table. Never auto-submit. */
export function candidateRow(value: unknown): SelectedRow {
  if (!object(value) || typeof value.id !== "string" || typeof value.subject !== "string" || typeof value.run !== "string" || !object(value.config)) throw new Error("Invalid candidate handoff.");
  const handoff = value as unknown as CandidateHandoff;
  const config = handoff.config;
  if (config.subject_id !== handoff.subject || !Array.isArray(config.montages) || config.montages.length !== 1 || !object(config.montages[0])) throw new Error("Candidate must contain one montage for this subject.");
  const montage = config.montages[0];
  const pairs = montage.electrode_pairs;
  if (!Array.isArray(pairs) || pairs.length < 2 || !numbers(config.intensities) || config.intensities.length !== pairs.length) throw new Error("Candidate geometry or currents are incomplete.");
  const named = pairs.every((pair) => Array.isArray(pair) && pair.length === 2 && pair.every((v) => typeof v === "string"));
  const placed = pairs.every((pair) => Array.isArray(pair) && pair.length === 2 && pair.every(xyz));
  if (!named && !placed) throw new Error("Candidate electrode pairs are invalid.");
  const settings: JobSettings = {
    ...DEFAULT_JOB_SETTINGS,
    conductivity: typeof config.conductivity === "string" ? config.conductivity : DEFAULT_JOB_SETTINGS.conductivity,
    anisoMaxratio: typeof config.aniso_maxratio === "number" ? config.aniso_maxratio : DEFAULT_JOB_SETTINGS.anisoMaxratio,
    anisoMaxcond: typeof config.aniso_maxcond === "number" ? config.aniso_maxcond : DEFAULT_JOB_SETTINGS.anisoMaxcond,
    electrodeShape: config.electrode_shape === "rect" ? "rect" : "ellipse",
    dimensions: numbers(config.electrode_dimensions) && config.electrode_dimensions.length === 2 ? config.electrode_dimensions as [number, number] : DEFAULT_JOB_SETTINGS.dimensions,
    gelThickness: typeof config.gel_thickness === "number" ? config.gel_thickness : DEFAULT_JOB_SETTINGS.gelThickness,
    outputFields: Array.isArray(config.output_fields) && config.output_fields.every((v) => typeof v === "string") ? config.output_fields : DEFAULT_JOB_SETTINGS.outputFields,
    mapToMni: config.map_to_mni === true,
    mapToFsavg: config.map_to_fsavg === true,
    customConductivities: object(config.tissue_conductivities) ? config.tissue_conductivities as Record<string, number> : {},
  };
  const currents = config.intensities.join(",");
  return {
    id: newRowId(), subjectId: handoff.subject, source: named ? "montage" : "flex",
    name: typeof montage.name === "string" ? montage.name : `candidate_${handoff.id}`,
    kind: pairs.length > 2 ? "multi_polar" : "uni_polar",
    eegNet: named && typeof montage.eeg_net === "string" ? montage.eeg_net : undefined,
    pairs: named ? pairs as [string, string][] : undefined,
    xyzPairs: placed ? pairs as [[number, number, number], [number, number, number]][] : undefined,
    currents, settings,
    candidate: { id: handoff.id, requestId: handoff.requestId, run: handoff.run, config: structuredClone(config), originalCurrents: currents, originalSettings: structuredClone(settings) },
  };
}
export function candidateMetricsChanged(row: SelectedRow): boolean {
  return !!row.candidate && (!!row.candidate.originalConfig || row.currents !== row.candidate.originalCurrents || JSON.stringify(row.settings) !== JSON.stringify(row.candidate.originalSettings));
}
/** Changing a source or subject retires its exact poses; current/settings edits retain orientation. */
export function patchCandidateRow(row: SelectedRow, patch: Partial<SelectedRow>): SelectedRow {
  const replacesGeometry = (["subjectId", "source", "name", "eegNet", "pairs", "xyzPairs"] as const).some((key) => key in patch && JSON.stringify(patch[key]) !== JSON.stringify(row[key]));
  return { ...row, ...patch, ...(replacesGeometry ? { candidate: undefined, mappingPending: undefined } : {}) };
}

/** Original subject coordinates remain available while a candidate is snapped to a cap. */
export function candidateOriginalPairs(row: SelectedRow): SelectedRow["xyzPairs"] {
  const config = row.candidate?.originalConfig ?? row.candidate?.config;
  const montage = Array.isArray(config?.montages) ? config.montages[0] : undefined;
  const pairs = object(montage) ? montage.electrode_pairs : undefined;
  return Array.isArray(pairs) && pairs.every((pair) => Array.isArray(pair) && pair.length === 2 && pair.every(xyz))
    ? pairs as NonNullable<SelectedRow["xyzPairs"]> : undefined;
}

/** Snapping changes geometry, not the selected candidate or the user's edited currents/settings. */
export function snapCandidateRow(row: SelectedRow, net: string, pairs: [string, string][]): SelectedRow {
  if (!row.candidate || !candidateOriginalPairs(row)) throw new Error("Candidate has no optimized coordinates.");
  const originalConfig = row.candidate.originalConfig ?? row.candidate.config;
  const config = structuredClone(originalConfig);
  const montage = (config.montages as Record<string, unknown>[])[0]!;
  montage.mode = "flex_mapped";
  montage.electrode_pairs = pairs;
  montage.eeg_net = net;
  delete montage.electrode_poses;
  return { ...row, mappingPending: undefined, eegNet: net, pairs, xyzPairs: undefined, candidate: { ...row.candidate, config, originalConfig } };
}

export function restoreCandidateRow(row: SelectedRow): SelectedRow {
  if (!row.candidate) return row;
  const xyzPairs = candidateOriginalPairs(row);
  if (!xyzPairs) return row;
  return { ...row, mappingPending: undefined, eegNet: undefined, pairs: undefined, xyzPairs, candidate: { ...row.candidate, config: row.candidate.originalConfig ?? row.candidate.config, originalConfig: undefined } };
}
