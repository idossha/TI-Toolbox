import { Select } from "../../ui/Select";
import { AUTO_FIELD, type Space } from "./buildConfig";
import { FIELD_REGISTRY, fieldSpecForName } from "./fields";

/**
 * `available` is the simulation's catalog `fields`: everything its NIfTIs carry, `magnE` included.
 * Only names the analyzer accepts are offered (`fieldSpecForName` knows the registry and the mTI
 * spelling `mTI_max`); with none of those, the whole registry is, as when the catalog says nothing.
 */
export function AnalysisFieldSelect({value,space,available=[],onChange}: {value:string;space:Space;available?:string[];onChange:(value:string)=>void}) {
  const analysable=available.filter((name)=>fieldSpecForName(name) !== undefined);
  const names=analysable.length ? analysable : FIELD_REGISTRY.map((field)=>field.name);
  const retained=value !== AUTO_FIELD && !names.includes(value) ? [value,...names] : names;
  return <Select value={value} onValueChange={onChange} aria-label="Field" options={[
    {value:AUTO_FIELD,label:"Auto"},...retained.map((name)=>({value:name,label:space === "voxel" && name === "TI_normal" ? `${name} (mesh only)` : name,disabled:space === "voxel" && name === "TI_normal"})),
  ]}/>;
}
