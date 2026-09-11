import { useQuery } from "@tanstack/react-query";
import { Field } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { FormSection } from "../../ui/Layout";
import { RoiPicker } from "../_shared/roi";
import { ExCurrentSection, ExElectrodesSection, MExCarrierSection, MExElectrodesSection } from "../optimizer/ExSections";
import { getEegNets, getLeadfields } from "../optimizer/api";
import { electrodesForNet, netOptions } from "../optimizer/nets";
import { exNodeError, type ExNodeEditor } from "./exNodeEditor";

export function ExNodeSettings({ editor, subjects, onChange, leadfieldBound = false }: { editor: ExNodeEditor; subjects: string[]; leadfieldBound?: boolean; onChange: (next: ExNodeEditor) => void }) {
  const subject = subjects[0];
  const nets = useQuery({ queryKey: ["eeg-nets", subject], queryFn: () => getEegNets(subject!), enabled: !!subject });
  const leadfields = useQuery({ queryKey: ["leadfields", subject], queryFn: () => getLeadfields(subject!), enabled: !!subject });
  const chosen = leadfields.data?.find((item) => item.path === editor.leadfieldHdf);
  const selectedNet = editor.net || chosen?.net || null;
  const retainedLabels = editor.kind === "ex" ? [...editor.ex.pool, ...Object.values(editor.ex.buckets).flat()] : Object.values(editor.mex.buckets).flat();
  const electrodes = [...new Set([...electrodesForNet(nets.data, selectedNet), ...retainedLabels])];
  const options = (leadfields.data ?? []).filter((item) => item.exists).map((item) => ({ value: item.path, label: item.net }));
  if (editor.leadfieldHdf && !options.some((item) => item.value === editor.leadfieldHdf)) options.push({ value: editor.leadfieldHdf, label: editor.leadfieldHdf });
  const error = exNodeError(editor);
  return <>
    <FormSection title="Search">
      <Field label="Run name"><input className="input" aria-label="Run name" placeholder="auto (timestamp)" value={editor.runName} onChange={(event) => onChange({ ...editor, runName: event.target.value })} /></Field>
      {leadfieldBound && <>
        <p>Leadfield comes from the connected node for each subject.</p>
        <Field label="EEG net"><Select aria-label="EEG net" value={selectedNet ?? "__none__"} options={[{ value: "__none__", label: "Choose an EEG net" }, ...netOptions(leadfields.data, nets.data)]} onValueChange={(value) => onChange({ ...editor, net: value === "__none__" ? "" : value })} /></Field>
      </>}
      {!leadfieldBound && <Field label="Leadfield" note={!subject ? "Connect a Subjects node first." : undefined}>
        <Select aria-label="Leadfield" value={editor.leadfieldHdf || "__none__"} options={[{ value: "__none__", label: "Choose a leadfield" }, ...options]} onValueChange={(value) => onChange({ ...editor, leadfieldHdf: value === "__none__" ? "" : value })} />
      </Field>}
      {(nets.isError || leadfields.isError) && <p role="alert">Could not load electrode or leadfield choices. <button type="button" onClick={() => { void nets.refetch(); void leadfields.refetch(); }}>Retry</button></p>}
    </FormSection>
    <FormSection title="Target"><RoiPicker value={editor.roi} onChange={(roi) => onChange({ ...editor, roi })} modes={["saved", "subcortical", "mask"]} subject={subject} />{error && <p role="alert">{error}</p>}</FormSection>
    {editor.kind === "ex" ? <>
      <ExElectrodesSection form={editor.ex} onChange={(patch) => onChange({ ...editor, ex: { ...editor.ex, ...patch } })} electrodes={electrodes} disabled={!editor.leadfieldHdf && !selectedNet} />
      <ExCurrentSection form={editor.ex} onChange={(patch) => onChange({ ...editor, ex: { ...editor.ex, ...patch } })} />
    </> : <>
      <MExElectrodesSection form={editor.mex} onChange={(patch) => onChange({ ...editor, mex: { ...editor.mex, ...patch } })} electrodes={electrodes} disabled={!editor.leadfieldHdf && !selectedNet} />
      <MExCarrierSection form={editor.mex} onChange={(patch) => onChange({ ...editor, mex: { ...editor.mex, ...patch } })} />
    </>}
  </>;
}
