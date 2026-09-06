/**
 * Flex-search's method-specific sections: objective, electrode parameters, solver, post-run.
 * Merged from `optimizer-flex/{ElectrodeParams,HyperParams,FocalityOptions}.tsx` — the parity
 * sources are `tit/gui/flex_search_tab.py` and `tit/gui/components/{electrode_config,
 * solver_params}.py`; `pages/optimizer/PARITY.md` maps every control to where it now lives.
 */
import { FormSection } from "../../ui/Layout";
import { Field, TextInput } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Checkbox } from "../../ui/Toggle";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { RoiPicker, type RoiValue } from "../_shared/roi";
import type { EegNet } from "./api";
import {
  parsePctList,
  sweepCombinationCount,
  type ElectrodeShape,
  type FlexFormState,
  type FocalityMode,
  type NonRoiMethod,
} from "./flexConfig";
import { flexCost } from "./cost";

/** The option text is the goal's name; what each one optimizes is the field's `help`. A select
 *  whose longest option is a sentence sets its own min-content width and pushes past its grid
 *  column (the label/control overlap measured in round 1). */
export const GOAL_OPTIONS = [
  { value: "mean", label: "Mean" },
  { value: "max", label: "Max" },
  { value: "focality", label: "Focality" },
  { value: "focality_tf", label: "Focality, threshold-free" },
];

const GOAL_HELP =
  "Mean: maximize the average field in the ROI. Max: maximize its peak. Focality: maximize the " +
  "ROI field while minimizing it elsewhere. Threshold-free focality: the same contrast with no " +
  "thresholds to tune — it stays optimizable at deep targets where the threshold form goes flat.";

export const POSTPROC_OPTIONS = [
  { value: "max_TI", label: "max_TI" },
  { value: "dir_TI_normal", label: "dir_TI_normal" },
  { value: "dir_TI_tangential", label: "dir_TI_tangential" },
];

const POSTPROC_HELP = "max_TI: the maximum TI field. dir_TI_normal / dir_TI_tangential: its component normal or tangential to the surface.";

// `FlexConfig.anisotropy_type` per contracts/schema.json documents "scalar"/"vn" only; the Qt tab
// also offered "dir"/"mc" (PARITY.md), left out pending confirmation `run_flex_search` takes them.
const ANISOTROPY_OPTIONS = [
  { value: "scalar", label: "Isotropic (scalar)" },
  { value: "vn", label: "Volume-normalized (vn)" },
];

const NON_ROI_METHOD_OPTIONS = [
  { value: "everything_else", label: "Everything else (default)" },
  { value: "specific", label: "Specific region" },
];

const FOCALITY_MODE_OPTIONS = [
  { value: "manual", label: "Manual thresholds" },
  { value: "adaptive", label: "Adaptive (single run)" },
  { value: "pareto", label: "Pareto sweep" },
];

const SHAPE_OPTIONS = [
  { value: "ellipse", label: "Ellipse" },
  { value: "rect", label: "Rectangle" },
];

export type FlexPatch = (patch: Partial<FlexFormState>) => void;

/** Tier 1: the goal, its post-processing, and — when the goal is focal — the focality machinery. */
export function ObjectiveSection({
  form,
  onChange,
  nonRoi,
  onNonRoiChange,
  subject,
}: {
  form: FlexFormState;
  onChange: FlexPatch;
  nonRoi: RoiValue;
  onNonRoiChange: (v: RoiValue) => void;
  subject: string | undefined;
}) {
  const isThreshold = form.goal === "focality";
  const isTf = form.goal === "focality_tf";
  const isFocality = isThreshold || isTf;
  const combinations = sweepCombinationCount(form);

  return (
    <FormSection title="Objective">
      <>
        <Field label="Goal" help={GOAL_HELP}>
          <Select value={form.goal} onValueChange={(v) => onChange({ goal: v as FlexFormState["goal"] })} options={GOAL_OPTIONS} />
        </Field>
        <Field label="Post-processing" help={POSTPROC_HELP}>
          <Select value={form.postproc} onValueChange={(v) => onChange({ postproc: v as FlexFormState["postproc"] })} options={POSTPROC_OPTIONS} />
        </Field>
        {isFocality && (
          <Field label="Non-ROI">
            <Select value={form.nonRoiMethod} onValueChange={(v) => onChange({ nonRoiMethod: v as NonRoiMethod })} options={NON_ROI_METHOD_OPTIONS} />
          </Field>
        )}
        {isTf && (
          <Field label="Intensity weight" help="0 = most focal (balanced), 1 = favours on-target intensity.">
            <NumberInput value={form.intensityWeight} onValueChange={(v) => onChange({ intensityWeight: v ?? 0 })} min={0} max={1} step={0.05} />
          </Field>
        )}
        {isThreshold && (
          <Field label="Threshold mode" className="optimizer-span">
            <SegmentedControl value={form.focalityMode} onValueChange={(v) => onChange({ focalityMode: v as FocalityMode })} options={FOCALITY_MODE_OPTIONS} aria-label="Threshold mode" />
          </Field>
        )}
        {isThreshold && form.focalityMode === "manual" && (
          <Field label="E-field thresholds" help="One value: non-ROI max = ROI min. Two: non-ROI max, ROI min. In V/m.">
            <TextInput value={form.manualThresholds} onChange={(e) => onChange({ manualThresholds: e.target.value })} placeholder="e.g. 0.2 or 0.2,0.5" />
          </Field>
        )}
        {isThreshold && form.focalityMode === "adaptive" && (
          <>
            <Field label="Non-ROI share" help="Percent of the achievable intensity found by a first mean-optimization run.">
              <NumberInput value={form.adaptiveNonRoiPct} onValueChange={(v) => onChange({ adaptiveNonRoiPct: v ?? 20 })} min={1} max={99} unit="%" />
            </Field>
            <Field label="ROI share">
              <NumberInput value={form.adaptiveRoiPct} onValueChange={(v) => onChange({ adaptiveRoiPct: v ?? 80 })} min={1} max={99} unit="%" />
            </Field>
          </>
        )}
        {isThreshold && form.focalityMode === "pareto" && (
          <>
            <Field label="ROI thresholds" help="Comma-separated percentages, e.g. 80 or 80,70.">
              <TextInput value={form.paretoRoiPcts} onChange={(e) => onChange({ paretoRoiPcts: e.target.value })} />
            </Field>
            <Field label="Non-ROI thresholds" help="Comma-separated percentages, e.g. 20,30,40.">
              <TextInput value={form.paretoNonRoiPcts} onChange={(e) => onChange({ paretoNonRoiPcts: e.target.value })} />
            </Field>
          </>
        )}
      </>
      {isThreshold && form.focalityMode === "pareto" && parsePctList(form.paretoRoiPcts).length > 0 && parsePctList(form.paretoNonRoiPcts).length > 0 && (
        <p className="optimizer-cost optimizer-span" data-testid="optimizer-sweep-cost">
          {combinations} threshold {combinations === 1 ? "combination" : "combinations"} · {flexCost(form).line}
        </p>
      )}
      {isFocality && form.nonRoiMethod === "specific" && (
        <Field label="Non-ROI region" className="optimizer-span" layout="stacked">
          <RoiPicker value={nonRoi} onChange={onNonRoiChange} modes={["cortical", "subcortical", "spherical"]} subject={subject} />
        </Field>
      )}
    </FormSection>
  );
}

/**
 * Electrode geometry and the current-ratio search. Kept apart from the solver box: electrode
 * parameters belong in an electrode section (memory: feedback_gui_param_placement.md).
 */
export function ElectrodesSection({ form, onChange }: { form: FlexFormState; onChange: FlexPatch }) {
  return (
    <FormSection
      title="Electrodes"
      collapsible
      summary={`${form.electrodeShape} · ${form.dimensionWidth}×${form.dimensionHeight} mm · gel ${form.gelThickness} mm · min dist ${form.minElectrodeDistance} mm`}
    >
      <>
        <Field label="Current" required>
          <NumberInput value={form.currentMA} onValueChange={(v) => onChange({ currentMA: v ?? 1 })} unit="mA" min={0.1} step={0.1} />
        </Field>
        <Field label="Shape">
          <SegmentedControl value={form.electrodeShape} onValueChange={(v) => onChange({ electrodeShape: v as ElectrodeShape })} options={SHAPE_OPTIONS} aria-label="Electrode shape" />
        </Field>
        <Field label="Dimensions (x, y)" required className="optimizer-span">
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <NumberInput value={form.dimensionWidth} onValueChange={(v) => onChange({ dimensionWidth: v ?? 8 })} unit="mm" min={0.1} step={0.5} aria-label="Electrode width" />
            <NumberInput value={form.dimensionHeight} onValueChange={(v) => onChange({ dimensionHeight: v ?? 8 })} unit="mm" min={0.1} step={0.5} aria-label="Electrode height" />
          </div>
        </Field>
        <Field label="Gel thickness" required>
          <NumberInput value={form.gelThickness} onValueChange={(v) => onChange({ gelThickness: v ?? 4 })} unit="mm" min={0.1} step={0.5} />
        </Field>
        <Field label="Min distance">
          <NumberInput value={form.minElectrodeDistance} onValueChange={(v) => onChange({ minElectrodeDistance: v ?? 5 })} unit="mm" min={0} step={1} />
        </Field>
        <Field label="Current ratio" help="Search the two-channel current split alongside electrode placement." className="optimizer-span">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <Checkbox checked={form.optimizeCurrentRatio} onCheckedChange={(v) => onChange({ optimizeCurrentRatio: v })} label="Optimize" />
            <NumberInput
              value={form.ratioLevels}
              onValueChange={(v) => onChange({ ratioLevels: v ?? 21 })}
              min={2}
              max={51}
              step={1}
              disabled={!form.optimizeCurrentRatio}
              aria-label="Ratio levels"
            />
          </div>
        </Field>
        <Field label="Ratio total current" help="Blank = 2 × electrode current (the 1:1 split stays in range).">
          <NumberInput value={form.ratioTotalMA} onValueChange={(v) => onChange({ ratioTotalMA: v })} unit="mA" min={0.1} step={0.1} disabled={!form.optimizeCurrentRatio} />
        </Field>
      </>
    </FormSection>
  );
}

/** Differential-evolution settings + the conductivity model. The cost line lives beside them. */
export function SolverSection({ form, onChange, eegNets }: { form: FlexFormState; onChange: FlexPatch; eegNets: EegNet[] }) {
  const cost = flexCost(form);
  return (
    <FormSection
      title="Solver"
      collapsible
      summary={`DE · pop ${form.populationSize} · ${form.maxIterations} iter · tol ${form.tolerance}`}
      advanced={
        <>
          <Field label="Anisotropy type">
            <Select value={form.anisotropyType} onValueChange={(v) => onChange({ anisotropyType: v as FlexFormState["anisotropyType"] })} options={ANISOTROPY_OPTIONS} />
          </Field>
          <Field label="Anisotropy max ratio">
            <NumberInput value={form.anisoMaxratio} onValueChange={(v) => onChange({ anisoMaxratio: v ?? 10 })} min={1} step={0.5} />
          </Field>
          <Field label="Anisotropy max conductivity" help="S/m">
            <NumberInput value={form.anisoMaxcond} onValueChange={(v) => onChange({ anisoMaxcond: v ?? 2 })} min={0.1} step={0.1} />
          </Field>
          <Field label="Skin region margin" help="Signed valid-skin-region margin. Positive expands the region; negative constricts it.">
            <NumberInput value={form.skinRegionMarginMm} onValueChange={(v) => onChange({ skinRegionMarginMm: v ?? 0 })} unit="mm" step={5} min={-20} max={40} />
          </Field>
          <Field label="Landmark exclusion">
            <Checkbox checked={form.avoidLandmarkRegions} onCheckedChange={(v) => onChange({ avoidLandmarkRegions: v })} label="Avoid eye/ear landmarks" />
          </Field>
          <Field label="Skin visualization" help="Overlay valid and invalid electrodes from a net on the valid-skin-region visualization.">
            <Checkbox
              checked={form.visualizeSkinElectrodes}
              onCheckedChange={(v) => onChange({ visualizeSkinElectrodes: v, skinVisualizationNet: v ? form.skinVisualizationNet : undefined })}
              label="Plot EEG net electrodes"
            />
          </Field>
          {form.visualizeSkinElectrodes && (
            <Field label="Visualization EEG net" required>
              <Select
                value={form.skinVisualizationNet}
                onValueChange={(v) => onChange({ skinVisualizationNet: v })}
                options={eegNets.map((n) => ({ value: n.name, label: n.name }))}
                placeholder="Select a net…"
              />
            </Field>
          )}
        </>
      }
    >
      <>
        <Field label="Optimization runs" help="Higher values increase the chance of finding the global optimum but take longer.">
          <NumberInput value={form.nMultistart} onValueChange={(v) => onChange({ nMultistart: v ?? 1 })} min={1} max={20} step={1} />
        </Field>
        <Field label="Max iterations">
          <NumberInput value={form.maxIterations} onValueChange={(v) => onChange({ maxIterations: v ?? 500 })} min={50} max={2000} step={10} />
        </Field>
        <Field label="Population size">
          <NumberInput value={form.populationSize} onValueChange={(v) => onChange({ populationSize: v ?? 13 })} min={4} max={100} step={1} />
        </Field>
        <Field label="Tolerance" help="Convergence tolerance for the differential evolution optimizer.">
          <NumberInput value={form.tolerance} onValueChange={(v) => onChange({ tolerance: v ?? 0.1 })} min={0.0001} max={1} step={0.01} />
        </Field>
        <Field label="Mutation (min, max)" className="optimizer-span">
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
            <NumberInput value={form.mutationMin} onValueChange={(v) => onChange({ mutationMin: v ?? 0.01 })} min={0} max={2} step={0.01} aria-label="Mutation min" />
            <span className="field-help">to</span>
            <NumberInput value={form.mutationMax} onValueChange={(v) => onChange({ mutationMax: v ?? 0.5 })} min={0} max={2} step={0.01} aria-label="Mutation max" />
          </div>
        </Field>
        <Field label="Recombination" help="Recombination probability for differential evolution.">
          <NumberInput value={form.recombination} onValueChange={(v) => onChange({ recombination: v ?? 0.7 })} min={0} max={1} step={0.05} />
        </Field>
        <Field label="CPUs" help="Leave blank to auto-detect.">
          <NumberInput value={form.cpus} onValueChange={(v) => onChange({ cpus: v })} min={1} step={1} />
        </Field>
      </>
      <p className="optimizer-cost optimizer-span" data-testid="optimizer-cost-flex">
        {cost.line}
      </p>
    </FormSection>
  );
}

/** Simulations the search runs for you once it has a winner. */
export function PostRunSection({ form, onChange, eegNets }: { form: FlexFormState; onChange: FlexPatch; eegNets: EegNet[] }) {
  const on = [form.runFinalElectrodeSimulation && "final montage", form.enableMapping && "mapped electrodes"].filter(Boolean);
  return (
    <FormSection title="After the search" collapsible defaultOpen={false} summary={on.length ? on.join(" · ") : "off"}>
      <>
        <Field label="Simulate" className="optimizer-span">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            <Checkbox
              checked={form.runFinalElectrodeSimulation}
              onCheckedChange={(v) => onChange({ runFinalElectrodeSimulation: v })}
              label="Run final electrode simulation"
            />
            <Checkbox
              checked={form.enableMapping}
              onCheckedChange={(v) => onChange({ enableMapping: v, eegNet: v ? form.eegNet : undefined })}
              label="Run simulation with mapped electrodes"
            />
          </div>
        </Field>
        {form.enableMapping && (
          <Field label="EEG net template" required>
            <Select
              value={form.eegNet}
              onValueChange={(v) => onChange({ eegNet: v })}
              options={eegNets.map((n) => ({ value: n.name, label: n.name }))}
              placeholder="Select a net…"
            />
          </Field>
        )}
      </>
    </FormSection>
  );
}
