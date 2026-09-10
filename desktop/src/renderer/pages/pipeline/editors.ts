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

/** The cohort. The one node that *owns* a subject list; every other node is handed one. */
export interface SubjectsEditor {
  kind: "subjects";
  subjects: string[];
}

export interface PreEditor {
  kind: "pre";
  stages: Record<string, boolean>;
}

export interface FlexEditor {
  kind: "flex";
  form: FlexFormState;
  roi: RoiValue;
}

export interface SimEditor {
  kind: "sim";
  montages: string;
  eegNet: string;
  currents: string;
  params: GlobalParams;
}

export interface AnalyzerEditor {
  kind: "analyzer";
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

export type NodeEditor = SubjectsEditor | PreEditor | FlexEditor | SimEditor | AnalyzerEditor | JsonEditor;

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
    case "subjects":
      return { kind: "subjects", subjects: [] };
    case "pre":
      return { kind: "pre", stages: { create_m2m: true } };
    case "flex":
      return { kind: "flex", form: defaultFlexFormState(), roi: emptyRoi("subcortical") };
    case "sim":
      return { kind: "sim", montages: "", eegNet: "", currents: "1.0, 1.0", params: { ...SIM_PARAMS } };
    case "analyzer":
      return {
        kind: "analyzer",
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

/**
 * The best editor state a *saved* node's config can be read back into.
 *
 * The document stores each node's **built** config, which is what validates, runs and exports; the
 * form state that produced it is page session state and is not saved. No v3 page has a full
 * `config -> form state` reader (PC.md open item 2), so this is deliberately partial: it recovers
 * the fields a user is most likely to want to see and change again — the cohort, the montage
 * names, the simulation, the pre stages, the analyzer's space and target — and leaves the rest at
 * that kind's defaults.
 *
 * The important part is what it does **not** do. It never invents a config: opening a loaded node
 * and closing it again without touching anything leaves the document's config alone, and only an
 * actual edit rebuilds it. And for the JSON-edited kinds it seeds the textarea with the node's own
 * config rather than `{}`, which is the difference between "edit this step" and "silently replace
 * this step with an empty object".
 */
export function editorFromNode(node: { kind: NodeKind; config?: Record<string, unknown> }): NodeEditor {
  const config = node.config ?? {};
  const base = defaultEditor(node.kind);

  switch (base.kind) {
    case "subjects": {
      const list = config.subject_ids;
      return {
        ...base,
        subjects: Array.isArray(list) ? list.map((s) => String(s).trim()).filter(Boolean) : [],
      };
    }
    case "pre": {
      const stages: Record<string, boolean> = {};
      for (const stage of PRE_STAGES) if (config[stage.key] === true) stages[stage.key] = true;
      return { ...base, stages: Object.keys(stages).length ? stages : base.stages };
    }
    case "flex":
      return base;
    case "sim": {
      const montages = Array.isArray(config.montages)
        ? config.montages.map((m) => String((m as { name?: unknown })?.name ?? "")).filter(Boolean).join(", ")
        : "";
      return {
        ...base,
        montages,
        eegNet: String(config.eeg_net ?? "") || base.eegNet,
        params: { ...base.params, conductivity: String(config.conductivity ?? base.params.conductivity) },
      };
    }
    case "analyzer":
      return {
        ...base,
        simulation: String(config.simulation ?? ""),
        space: config.space === "voxel" ? "voxel" : base.space,
        analysisType: ["spherical", "cortical", "subcortical"].includes(String(config.analysis_type))
          ? (String(config.analysis_type) as typeof base.analysisType)
          : base.analysisType,
      };
    case "json":
      return { ...base, text: JSON.stringify(config, null, 2) };
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
 * **A node's config is its own.** Nothing here is copied from the node upstream of it: an edge
 * carries one named port and nothing else. The cohort is the exception that proves it — it is not
 * copied into the config at all, it stays on the `subjects` node and reaches this one over the
 * wire, so a document has exactly one place that says who takes part.
 */
export function configFor(
  editor: NodeEditor,
  atlasLookup: (atlas: string) => AtlasLookup | undefined,
  previous?: Record<string, unknown>,
  /**
   * The subjects that reach this node over the graph's `subjects` wire. Only a *representative*
   * is used, and only where a page's builder insists on one: the server fans a node out to one
   * job per subject and forces each generated config's `subject_id` to its own subject
   * (`tit.pipeline.plan`), so the id embedded here never decides which anatomy a job reads.
   */
  cohort: string[] = [],
): Record<string, unknown> {
  const representative = cohort[0] ?? "";

  switch (editor.kind) {
    case "subjects":
      // The one node that owns a subject list. Nothing else about it is configurable.
      return { subject_ids: [...editor.subjects] };
    case "pre": {
      const flags: Record<string, unknown> = {};
      for (const stage of PRE_STAGES) flags[stage.key] = editor.stages[stage.key] === true;
      return flags;
    }
    case "flex": {
      const roi = roiToConfig(editor.roi, atlasLookup);
      const config = buildFlexConfig(representative, editor.form, roi ?? ({} as never), undefined) as unknown as Record<string, unknown>;
      return config;
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
      return { ...base, montages };
    }
    case "analyzer": {
      const config = buildAnalyzerConfig({
        mode: "single",
        subjectId: representative,
        subjectIds: cohort,
        simulation: editor.simulation,
        space: editor.space,
        tissueType: editor.tissueType,
        field: editor.field,
        analysisType: editor.analysisType,
        coordinateSpace: editor.coordinateSpace,
        sphere: editor.sphere,
        roiValue: editor.roi,
      }) as unknown as Record<string, unknown>;
      // The cohort is the graph's, not this node's: `subject_ids` is deliberately not written
      // back into the config, so the document has exactly one place that says who takes part.
      delete config.subject_ids;
      return config;
    }
    case "json": {
      // `previous` is the config the node already carries. Mid-edit the textarea is *always*
      // briefly unparseable, and returning `{}` for it — which this used to do — wiped the node's
      // real config on the first mistyped brace and never said so. Keeping the last config that
      // parsed means a half-typed edit costs nothing, and the inspector shows the parse error
      // while it lasts.
      try {
        const parsed: unknown = JSON.parse(editor.text);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
      } catch {
        /* fall through to the last good config */
      }
      return previous ?? {};
    }
  }
}
