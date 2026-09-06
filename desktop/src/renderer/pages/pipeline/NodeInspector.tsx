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
import { Field } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Toggle";
import { NumberInput } from "../../ui/NumberInput";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { FormSection } from "../../ui/Layout";
import { Callout } from "../../ui/Feedback";
import { ObjectiveSection, ElectrodesSection } from "../optimizer/FlexSections";
import { RoiPicker, getAtlases, type Atlas, type AtlasLookup, type RoiValue } from "../_shared/roi";
import type { FlexFormState } from "../optimizer/flexConfig";
import { PRE_STAGES, type NodeEditor } from "./editors";
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
      description="Edited with the same form sections the node's own page uses."
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

        {editor.kind === "pre" && (
          <FormSection title="Stages">
            <>
              {PRE_STAGES.map((stage) => (
                <Field key={stage.key} label={stage.label}>
                  <Switch
                    checked={editor.stages[stage.key] === true}
                    onCheckedChange={(checked: boolean) =>
                      onEditorChange({ ...editor, stages: { ...editor.stages, [stage.key]: checked } })
                    }
                    aria-label={stage.label}
                  />
                </Field>
              ))}
            </>
          </FormSection>
        )}

        {editor.kind === "flex" && (
          <>
            <ObjectiveSection
              form={editor.form}
              onChange={(patch: Partial<FlexFormState>) => onEditorChange({ ...editor, form: { ...editor.form, ...patch } })}
              nonRoi={editor.roi}
              onNonRoiChange={() => undefined}
              subject={subjects[0]}
            />
            <ElectrodesSection
              form={editor.form}
              onChange={(patch: Partial<FlexFormState>) => onEditorChange({ ...editor, form: { ...editor.form, ...patch } })}
            />
            <FormSection title="Target">
              <div className="pipeline-span">
                <RoiPicker
                  value={editor.roi}
                  onChange={(roi) => onEditorChange({ ...editor, roi })}
                  modes={["spherical", "cortical", "subcortical"]}
                  subject={subjects[0]}
                />
              </div>
            </FormSection>
          </>
        )}

        {editor.kind === "sim" && (
          <FormSection title="Simulation">
            <>
              <Field
                label="Montages"
                help={
                  wired.some((e) => e.port === "montages")
                    ? "Wired from an optimizer — the names come from its finished run."
                    : "Comma-separated montage names from montage_list.json."
                }
                className="pipeline-span"
              >
                <input
                  className="input"
                  value={editor.montages}
                  data-port="montages"
                  disabled={wired.some((e) => e.port === "montages")}
                  placeholder="L_Insula, R_Insula"
                  onChange={(e) => onEditorChange({ ...editor, montages: e.target.value })}
                  aria-label="Montages"
                />
              </Field>
              <Field label="EEG net">
                <input
                  className="input"
                  value={editor.eegNet}
                  placeholder="GSN-HydroCel-185.csv"
                  onChange={(e) => onEditorChange({ ...editor, eegNet: e.target.value })}
                  aria-label="EEG net"
                />
              </Field>
              <Field label="Currents (mA)">
                <input
                  className="input"
                  value={editor.currents}
                  onChange={(e) => onEditorChange({ ...editor, currents: e.target.value })}
                  aria-label="Currents"
                />
              </Field>
              <Field label="Conductivity">
                <Select
                  value={editor.params.conductivity}
                  onValueChange={(v) => onEditorChange({ ...editor, params: { ...editor.params, conductivity: v } })}
                  options={[
                    { value: "scalar", label: "scalar" },
                    { value: "vn", label: "vn" },
                    { value: "dir", label: "dir" },
                    { value: "mc", label: "mc" },
                  ]}
                />
              </Field>
            </>
          </FormSection>
        )}

        {editor.kind === "analyzer" && (
          <>
            <FormSection title="Analysis">
              <>
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
                    onValueChange={(v) => onEditorChange({ ...editor, space: v as typeof editor.space })}
                    options={[
                      { value: "mesh", label: "Mesh" },
                      { value: "voxel", label: "Voxel" },
                    ]}
                    aria-label="Analysis space"
                  />
                </Field>
                <Field label="Target">
                  <Select
                    value={editor.analysisType}
                    onValueChange={(v) => onEditorChange({ ...editor, analysisType: v as typeof editor.analysisType })}
                    options={[
                      { value: "spherical", label: "Spherical" },
                      { value: "cortical", label: "Cortical" },
                      { value: "subcortical", label: "Subcortical" },
                    ]}
                  />
                </Field>
              </>
            </FormSection>
            {editor.analysisType === "spherical" ? (
              <FormSection title="Sphere">
                <>
                  {(["x", "y", "z", "radius"] as const).map((key) => (
                    <Field key={key} label={key === "radius" ? "Radius" : key.toUpperCase()}>
                      <NumberInput
                        value={editor.sphere[key]}
                        onValueChange={(v) => onEditorChange({ ...editor, sphere: { ...editor.sphere, [key]: v } })}
                        unit="mm"
                        aria-label={key}
                      />
                    </Field>
                  ))}
                  <Field label="Coordinate space">
                    <SegmentedControl
                      value={editor.coordinateSpace}
                      onValueChange={(v) => onEditorChange({ ...editor, coordinateSpace: v as "subject" | "mni" })}
                      options={[
                        { value: "subject", label: "Subject" },
                        { value: "mni", label: "MNI" },
                      ]}
                      aria-label="Coordinate space"
                    />
                  </Field>
                </>
              </FormSection>
            ) : (
              <FormSection title="Region">
                <div className="pipeline-span">
                  <RoiPicker
                    value={editor.roi}
                    onChange={(roi) => onEditorChange({ ...editor, roi })}
                    modes={[editor.analysisType]}
                    subject={subjects[0]}
                  />
                </div>
              </FormSection>
            )}
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
