import { useQuery } from "@tanstack/react-query";
import { getMontages } from "../simulator/api";
import { buildSimulationConfig } from "../simulator/buildConfig";
import { Select } from "../../ui/Select";
import { Field } from "../../ui/Field";
import type { SimEditor } from "./editors";

export function MontageSelection({editor, disabled, onChange}: {editor: SimEditor; disabled: boolean; onChange: (next: SimEditor) => void}) {
  const catalog = useQuery({queryKey:["montages"], queryFn:getMontages});
  const net = catalog.data?.nets[editor.eegNet];
  const available = {...net?.uni_polar, ...net?.multi_polar};
  const selected = editor.montages.split(",").map((n) => n.trim()).filter(Boolean);
  const names = [...new Set([...selected, ...Object.keys(available)])];
  return <>
    <Field label="EEG net"><Select aria-label="EEG net" value={editor.eegNet || "__none__"} disabled={disabled}
      options={[{value:"__none__",label:"Choose an EEG net"}, ...[...new Set([editor.eegNet,...Object.keys(catalog.data?.nets ?? {})].filter(Boolean))].map((value)=>({value,label:value}))]}
      onValueChange={(value)=>onChange({...editor,eegNet:value==="__none__"?"":value,montages:"",definitions:[]})}/></Field>
    <Field label="Montages" className="pipeline-span" help={disabled ? "Uses montages from the connected optimizer run." : "Saved definitions include their electrode pairs."}>
      <div role="group" aria-label="Montages">
        {catalog.isPending && <span>Loading montages…</span>}
        {catalog.isError && <span role="alert">Could not load montages. <button type="button" onClick={()=>void catalog.refetch()}>Retry</button></span>}
        {!catalog.isPending && !catalog.isError && !names.length && <span>No montages available for this net.</span>}
        {names.map((name)=><label key={name} style={{display:"flex",gap:8,padding:"4px 0"}}><input type="checkbox" disabled={disabled} checked={selected.includes(name)} onChange={(event)=>{
          const next=selected.filter((n)=>n!==name); if(event.target.checked) next.push(name);
          const definitions=next.flatMap((n)=>{
            const existing=editor.definitions?.find((m)=>m.name===n); if(existing) return [existing];
            const pairs=available[n]; if(!pairs) return [];
            return buildSimulationConfig({id:n,subjectId:"",source:"montage",name:n,eegNet:editor.eegNet,currents:editor.currents,pairs:pairs as [string,string][]},editor.params).montages as Record<string,unknown>[];
          });
          onChange({...editor,montages:next.join(", "),definitions});
        }}/>{name}</label>)}
      </div>
    </Field>
  </>;
}
