import { Select } from "../../ui/Select";
import { AUTO_FIELD, type Space } from "./buildConfig";
import { FIELD_REGISTRY } from "./fields";

export function AnalysisFieldSelect({value,space,available=[],onChange}: {value:string;space:Space;available?:string[];onChange:(value:string)=>void}) {
  const names=available.length ? available : FIELD_REGISTRY.map((field)=>field.name);
  const retained=value !== AUTO_FIELD && !names.includes(value) ? [value,...names] : names;
  return <Select value={value} onValueChange={onChange} aria-label="Field" options={[
    {value:AUTO_FIELD,label:"Auto"},...retained.map((name)=>({value:name,label:space === "voxel" && name === "TI_normal" ? `${name} (mesh only)` : name,disabled:space === "voxel" && name === "TI_normal"})),
  ]}/>;
}
