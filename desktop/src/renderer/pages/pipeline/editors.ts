/**
 * Node editor state, and the one function that turns it into the node's config.
 *
 * **The config a node carries is the config its page already builds.** Nothing here re-derives a
 * `FlexConfig` or a `SimulationConfig` by hand: `buildFlexConfig`, `buildSimulationConfig` and the
 * Analyzer's `buildConfig` are imported from their own pages and called with the same inputs those
 * pages give them. A node is therefore exactly one job of that page, not a second implementation of
 * it that can drift.
 *
 * The editor *state* (form state, ROI value) lives on the page keyed by node id, while the
 * document stores only the built config — which is what the server validates, runs and exports.
 * The consequence, and today's known limitation: loading a saved pipeline restores every node's
 * config (so it validates, runs and exports correctly) but opens its form at that kind's defaults,
 * because no v3 page has a config -> form-state reader. See the lane note's open items.
 */
import { defaultFlexFormState, buildFlexConfig, type FlexFormState } from "../optimizer/flexConfig";
import { buildSimulationConfig, type GlobalParams } from "../simulator/buildConfig";
import { buildConfig as buildAnalyzerConfig, type AnalysisType, type Space } from "../analyzer/buildConfig";
import { emptyRoi, roiToConfig, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { EMPTY_SPHERE, type Sphere } from "../analyzer/SphereRows";
import type { SelectedRow } from "../simulator/types";
import type { NodeKind } from "./graph";

/** Every stage flag a `pre` node can turn on, in the order the page shows them. */
export const PRE_STAGES: { key: string; label: string }[] = [
  { key: "convert_dicom", label: "Convert DICOM" },
  { key: "run_fastsurfer", label: "FastSurfer segmentation" },
  { key: "create_m2m", label: "SimNIBS head model (charm)" },
  { key: "run_tissue_analysis", label: "Tissue analysis" },
  { key: "run_qsiprep", label: "QSIPrep" },
  { key: "run_qsirecon", label: "QSIRecon" },
  { key: "extract_dti", label: "Extract DTI tensors" },
];

export interface PreEditor {
  kind: "pre";
  subjects: string;
  stages: Record<string, boolean>;
}

export interface FlexEditor {
  kind: "flex";
  subjects: string;
  form: FlexFormState;
  roi: RoiValue;
}

export interface SimEditor {
  kind: "sim";
  subjects: string;
  montages: string;
  eegNet: string;
  currents: string;
  params: GlobalParams;
}

export interface AnalyzerEditor {
  kind: "analyzer";
  subjects: string;
  simulation: string;
  space: Space;
  analysisType: AnalysisType;
  field: string;
  tissueType: string;
  coordinateSpace: "subject" | "mni";
  sphere: Sphere;
  roi: RoiValue;
}

/**
 * Kinds whose page form does not lift out of its page (the ex/mEx builders take a resolved
 * leadfield path, a target and a run name that only that page computes; `leadfield`, `source` and
 * `stats` have no v3 form at all). Their config is edited as JSON here, labelled as such rather
 * than faked with a half-form that would build a config their runner rejects.
 */
export interface JsonEditor {
  kind: "json";
  nodeKind: NodeKind;
  text: string;
}

export type NodeEditor = PreEditor | FlexEditor | SimEditor | AnalyzerEditor | JsonEditor;

const SIM_PARAMS: GlobalParams = {
  conductivity: "scalar",
  electrodeShape: "ellipse",
  dimensions: [8, 8],
  gelThickness: 4,
  outputFields: ["TI_max"],
  customConductivities: {},
};

export function defaultEditor(kind: NodeKind): NodeEditor {
  switch (kind) {
    case "pre":
      return { kind: "pre", subjects: "", stages: { create_m2m: true } };
    case "flex":
      return { kind: "flex", subjects: "", form: defaultFlexFormState(), roi: emptyRoi("subcortical") };
    case "sim":
      return { kind: "sim", subjects: "", montages: "", eegNet: "", currents: "1.0, 1.0", params: { ...SIM_PARAMS } };
    case "analyzer":
      return {
        kind: "analyzer",
        subjects: "",
        simulation: "",
        space: "mesh",
        analysisType: "spherical",
        field: "__auto__",
        tissueType: "GM",
        coordinateSpace: "subject",
        sphere: { ...EMPTY_SPHERE },
        roi: emptyRoi("cortical"),
      };
    default:
      return { kind: "json", nodeKind: kind, text: "{}" };
  }
}

export function parseSubjects(text: string): string[] {
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function simRow(subjectId: string, name: string, editor: SimEditor): SelectedRow {
  return {
    id: `${subjectId}:${name}`,
    subjectId,
    source: "montage",
    name,
    pairs: [],
    eegNet: editor.eegNet || undefined,
    currents: editor.currents,
  };
}

/**
 * The node's config, built by the same function its page uses.
 *
 * The `subject_id` it embeds is a *representative* subject: a pipeline node fans out to one job
 * per subject on the server (`tit.pipeline.plan`), which forces each generated config's
 * `subject_id` to its own subject, so the id here never decides which anatomy a job reads.
 */
export function configFor(
  editor: NodeEditor,
  atlasLookup: (atlas: string) => AtlasLookup | undefined,
): Record<string, unknown> {
  const subjects = "subjects" in editor ? parseSubjects(editor.subjects) : [];
  const representative = subjects[0] ?? "";

  switch (editor.kind) {
    case "pre": {
      const flags: Record<string, unknown> = {};
      for (const stage of PRE_STAGES) flags[stage.key] = editor.stages[stage.key] === true;
      return { ...flags, subject_ids: subjects };
    }
    case "flex": {
      const roi = roiToConfig(editor.roi, atlasLookup);
      const config = buildFlexConfig(representative, editor.form, roi ?? ({} as never), undefined) as unknown as Record<string, unknown>;
      return { ...config, subject_ids: subjects };
    }
    case "sim": {
      const names = editor.montages.split(",").map((s) => s.trim()).filter(Boolean);
      // One `SimulationConfig` carrying every montage the node runs: the server's plan fans this
      // out per subject, and each montage becomes one simulation name a downstream Analyzer binds.
      const montages = names.map((name) => {
        const row = simRow(representative, name, editor);
        return (buildSimulationConfig(row, editor.params).montages as unknown[])[0];
      });
      const base = buildSimulationConfig(simRow(representative, names[0] ?? "", editor), editor.params);
      return { ...base, montages, subject_ids: subjects };
    }
    case "analyzer": {
      const config = buildAnalyzerConfig({
        mode: "single",
        subjectId: representative,
        subjectIds: subjects,
        simulation: editor.simulation,
        space: editor.space,
        tissueType: editor.tissueType,
        field: editor.field,
        analysisType: editor.analysisType,
        coordinateSpace: editor.coordinateSpace,
        sphere: editor.sphere,
        roiValue: editor.roi,
      }) as unknown as Record<string, unknown>;
      return { ...config, subject_ids: subjects };
    }
    case "json": {
      try {
        const parsed = JSON.parse(editor.text);
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
      } catch {
        return {};
      }
    }
  }
}
