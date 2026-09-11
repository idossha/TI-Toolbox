/**
 * The node inspector — double-clicking a node card opens this over the canvas.
 *
 * Every field here is the *same component the node's own page uses*: `ObjectiveSection` and
 * `ElectrodesSection` from `pages/optimizer/FlexSections`, the shared `RoiPicker`, the same
 * `Field`/`Select`/`NumberInput` primitives. Nothing is a copy, so a change on the Optimizer page
 * shows up here with no edit.
 *
 * Kinds whose page form does not lift out of its page (`ex`, `mex`, `leadfield`, `source`,
 * `stats`) get a JSON editor, plainly labelled — an honest gap rather than a half-form that would
 * build a config the runner rejects.
 */
import { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog } from "../../ui/Overlay";
import { Switch } from "../../ui/Toggle";
import { Field } from "../../ui/Field";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { FormSection } from "../../ui/Layout";
import { Callout } from "../../ui/Feedback";
import { ObjectiveSection, ElectrodesSection, SolverSection, PostRunSection } from "../optimizer/FlexSections";
import { RoiPicker, emptyRoi, getAtlases, type Atlas, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { getAtlasRegions } from "../_shared/roi/api";
import { MontageSelection } from "./MontageSelection";
import type { FlexFormState } from "../optimizer/flexConfig";
import { ExNodeSettings } from "./ExNodeSettings";
import { PreNodeSettings } from "./PreNodeSettings";
import { SimulationSettings } from "../simulator/SimulationSettings";
import { getEegNets } from "../simulator/api";
import { AnalysisFieldSelect } from "../analyzer/AnalysisFieldSelect";
import { AnalyzerSettings } from "../analyzer/AnalyzerSettings";
import { type TissueKind } from "../_shared/roi";
import { analyzerEditorTarget, analyzerNodeTargets, type NodeEditor } from "./editors";
import { SubjectsEditor } from "./SubjectsEditor";
import {
  KIND_TITLE,
  PORT_LABEL,
  incoming,
  subjectsOf,
  type PipelineDoc,
  type PipelineNode,
  type PortType,
} from "./graph";

/** Same per-subject atlas resolution the Optimizer page does, for one subject. */
export function useAtlasLookup(subject: string | undefined, value: RoiValue | undefined): (atlas: string) => AtlasLookup | undefined {
  const kind = value?.mode === "cortical" ? "cortical" : value?.mode === "subcortical" ? "subcortical" : undefined;
  const space = value?.mode === "subcortical" ? value.atlasSpace : undefined;
  const { data } = useQuery({
    queryKey: kind === "subcortical" ? ["atlases", subject, "subcortical", space] : ["atlases", subject, "cortical"],
    queryFn: () => getAtlases(subject!, kind as "cortical" | "subcortical", space),
    enabled: kind !== undefined && !!subject,
  });
  return useMemo(() => (atlasId: string) => (data as Atlas[] | undefined)?.find((a) => a.id === atlasId), [data]);
}

export function NodeInspector({
  doc,
  node,
  editor,
  focusPort,
  onEditorChange,
  onLabelChange,
  onClose,
}: {
  doc: PipelineDoc;
  node: PipelineNode;
  editor: NodeEditor;
  /** Open with this port's field focused — how a card's "needs: subjects" chip lands here. */
  focusPort?: PortType | null;
  onEditorChange: (next: NodeEditor) => void;
  onLabelChange: (label: string) => void;
  onClose: () => void;
}) {
  const wired = incoming(doc, node.id);
  // The cohort a node runs over comes from the graph, never from the node: it is stated once, on
  // the `subjects` node, and reaches this one over the wire. `subjects[0]` is only ever used to
  // ask the catalog which atlases *a* subject has, so a form can list regions.
  const subjects = subjectsOf(doc, node.id);
  const body = useRef<HTMLDivElement>(null);
  const eegNets = useQuery({queryKey:["eeg-nets", subjects[0]],queryFn:()=>getEegNets(subjects[0]!),enabled:editor.kind === "flex" && !!subjects[0]});
  const analyzerAtlas = editor.kind === "analyzer" && (editor.roi.mode === "cortical" || editor.roi.mode === "subcortical") ? editor.roi : undefined;
  const atlasRegions = useQuery({queryKey:["pipeline-atlas-regions",subjects[0],analyzerAtlas?.atlas], queryFn:()=>getAtlasRegions(subjects[0]!,analyzerAtlas!.atlas!,"both"), enabled:!!subjects[0] && !!analyzerAtlas?.atlas});
  const analyzerRoi = analyzerAtlas ? {...analyzerAtlas,regions:analyzerAtlas.regions.map((selected)=>{
    const match=atlasRegions.data?.find((region)=>region.name===selected.name);
    return match ? {...selected,id:match.id,...(match.hemi ? {hemi:match.hemi}: {})} : selected;
  })} : editor.kind === "analyzer" ? editor.roi : undefined;


  const jsonError = useMemo(() => {
    if (editor.kind !== "json") return null;
    try {
      const parsed: unknown = JSON.parse(editor.text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "a config must be a JSON object";
      return null;
    } catch (error) {
      return String((error as Error)?.message ?? error);
    }
  }, [editor]);

  // The chip on the card names a *port*; the field that satisfies it is labelled with that port's
  // own name, which is the one thing both sides already agree on.
  useEffect(() => {
    if (!focusPort) return;
    // After the paint, and after Radix: a dialog moves focus to its own first focusable on open
    // (`onOpenAutoFocus`), which runs *after* this effect and would take the focus straight back
    // off the field the chip asked for. Two frames is enough, and a missing field is not an error
    // — a port with no form control of its own (`roi`, `leadfield`) simply opens the form.
    const frame = requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        const field = body.current?.querySelector<HTMLElement>(
          `input[data-port="${focusPort}"], textarea[data-port="${focusPort}"]`,
        );
        field?.focus();
        field?.scrollIntoView({ block: "center" });
      }),
    );
    return () => cancelAnimationFrame(frame);
  }, [focusPort]);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`${KIND_TITLE[node.kind]} — ${node.id}`}
    >
      <div className="pipeline-inspector" ref={body}>
        <FormSection title="Node">
          <>
            <Field label="Name" help="Shown on the card and in the exported notebook.">
              <input
                className="input"
                value={node.label ?? ""}
                placeholder={KIND_TITLE[node.kind]}
                onChange={(e) => onLabelChange(e.target.value)}
                aria-label="Node name"
              />
            </Field>
            {wired.length > 0 && (
              <Field label="Wired inputs" className="pipeline-span">
                <ul className="pipeline-wired">
                  {wired.map((edge) => (
                    <li key={`${edge.from}-${edge.port}`}>
                      <strong>{PORT_LABEL[edge.port]}</strong> from <code>{edge.from}</code>
                    </li>
                  ))}
                </ul>
              </Field>
            )}
          </>
        </FormSection>

        {editor.kind === "subjects" && (
          <FormSection title="Cohort">
            <div className="pipeline-span">
              <SubjectsEditor
                value={editor.subjects}
                onChange={(next) => onEditorChange({ ...editor, subjects: next })}
              />
            </div>
          </FormSection>
        )}

        {editor.kind === "pre" && <div className="pipeline-span"><PreNodeSettings editor={editor} onChange={onEditorChange}/></div>}

        {(editor.kind === "ex" || editor.kind === "mex") && <ExNodeSettings editor={editor} subjects={subjects} leadfieldBound={wired.some((edge)=>edge.port === "leadfield")} onChange={onEditorChange}/>}

        {editor.kind === "flex" && (
          <>
            <ObjectiveSection
              form={editor.form}
              onChange={(patch: Partial<FlexFormState>) => onEditorChange({ ...editor, form: { ...editor.form, ...patch } })}
              nonRoi={editor.nonRoi ?? emptyRoi("subcortical")}
              onNonRoiChange={(nonRoi) => onEditorChange({ ...editor, nonRoi })}
              subject={subjects[0]}
            />
            <ElectrodesSection
              form={editor.form}
              onChange={(patch: Partial<FlexFormState>) => onEditorChange({ ...editor, form: { ...editor.form, ...patch } })}
            />
            <SolverSection form={editor.form} onChange={(patch) => onEditorChange({...editor,form:{...editor.form,...patch}})} eegNets={eegNets.data ?? []}/>
            <PostRunSection form={editor.form} onChange={(patch) => onEditorChange({...editor,form:{...editor.form,...patch}})} eegNets={eegNets.data ?? []}/>
            <FormSection title="Target">
              <div className="pipeline-span">
                {(editor.roi.mode === "cortical" || editor.roi.mode === "subcortical") && editor.roi.atlas?.startsWith("/") && <Callout kind="info">Saved target: {editor.roi.atlas}. Selected labels: {editor.roi.regions.map((r) => r.id).join(", ")}. Choose an atlas to replace this saved target.</Callout>}
                <RoiPicker
                  value={editor.roi}
                  onChange={(roi) => onEditorChange({ ...editor, roi })}
                  modes={["spherical", "cortical", "subcortical", "mask"]}
                  subject={subjects[0]}
                />
              </div>
            </FormSection>
          </>
        )}

        {editor.kind === "sim" && (
          <FormSection title="Simulation">
            <>
              <MontageSelection editor={editor} disabled={wired.some((e) => e.port === "montages")} onChange={onEditorChange} />
              <Field label="Currents (mA)">
                <input
                  className="input"
                  value={editor.currents}
                  onChange={(e) => onEditorChange({ ...editor, currents: e.target.value })}
                  aria-label="Currents"
                />
              </Field>
              <div className="pipeline-span"><SimulationSettings value={editor.params} onChange={(params)=>onEditorChange({...editor,params:{...params,customConductivities:params.customConductivities ?? {}}})}/></div>
            </>
          </FormSection>
        )}

        {editor.kind === "analyzer" && (
          <>
            <FormSection title="Analysis">
              <>
                <Field label="Combine into one group analysis" className="pipeline-span">
                  <Switch checked={editor.mode === "group"} onCheckedChange={(group) => onEditorChange({ ...editor, mode: group ? "group" : "single" })} aria-label="Combine into one group analysis" />
                </Field>
                <Field
                  label="Simulation"
                  help={
                    wired.some((e) => e.port === "simulation")
                      ? "Wired from a Simulator node — one analysis per simulation it writes."
                      : "Simulation (montage) name to analyse."
                  }
                  className="pipeline-span"
                >
                  <input
                    className="input"
                    value={editor.simulation}
                    data-port="simulation"
                    disabled={wired.some((e) => e.port === "simulation")}
                    onChange={(e) => onEditorChange({ ...editor, simulation: e.target.value })}
                    aria-label="Simulation"
                  />
                </Field>
                <Field label="Space">
                  <SegmentedControl
                    value={editor.space}
                    onValueChange={(v) => onEditorChange({ ...editor, space: v as typeof editor.space, field: v === "voxel" && editor.field === "TI_normal" ? "__auto__" : editor.field })}
                    options={[
                      { value: "mesh", label: "Mesh" },
                      { value: "voxel", label: "Voxel" },
                    ]}
                    aria-label="Analysis space"
                  />
                </Field>
                <Field label="Field"><AnalysisFieldSelect value={editor.field} space={editor.space} onChange={(field)=>onEditorChange({...editor,field})}/></Field>
              </>
            </FormSection>
            <div className="pipeline-span">
              <AnalyzerSettings row={{id:node.id,subjectId:subjects[0] ?? "",simulation:editor.simulation,space:editor.space,field:editor.field,tissue:editor.tissueType as TissueKind,roi:analyzerRoi ?? editor.roi,combine:editor.combine ?? true}}
                onChange={(patch)=>onEditorChange({...analyzerEditorTarget(editor,patch.roi ?? editor.roi,patch.combine ?? editor.combine ?? true),...(patch.tissue ? {tissueType:patch.tissue}: {})})}/>
              {analyzerNodeTargets(editor).length > 1 && <Callout kind="info">Creates {analyzerNodeTargets(editor).length} analysis steps when this editor closes, one per target.</Callout>}
            </div>
          </>
        )}

        {editor.kind === "json" && (
          <FormSection title="Config">
            <div className="pipeline-span">
              <Callout kind="info">
                {`${KIND_TITLE[editor.nodeKind]} has no lifted form yet — edit its config as JSON. The server validates it against the same dataclass the runner reads, so a mistake comes back as a reason, not a failed job.`}
              </Callout>
              <textarea
                className={`input pipeline-json${jsonError ? " is-invalid" : ""}`}
                rows={14}
                spellCheck={false}
                value={editor.text}
                data-port="subjects"
                data-testid="pipeline-json"
                onChange={(e) => onEditorChange({ ...editor, text: e.target.value })}
                aria-label="Node config JSON"
                aria-invalid={jsonError ? true : undefined}
              />
              {/* Unparseable JSON used to become `{}` in the document, without a word: the node
                  quietly lost its config the moment a brace was mistyped. It now keeps the last
                  config that parsed, and the reason is on screen while the text is broken. */}
              {jsonError && (
                <Callout kind="danger" title="Not valid JSON — the step keeps its last good config">
                  {jsonError}
                </Callout>
              )}
            </div>
          </FormSection>
        )}
      </div>
    </Dialog>
  );
}
