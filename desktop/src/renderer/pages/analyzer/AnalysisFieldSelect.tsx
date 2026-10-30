import { Select } from "../../ui/Select";
import { AUTO_FIELD, type Space } from "./buildConfig";
import { FIELD_REGISTRY, fieldSpecForName } from "./fields";

/** The suffix an option carries: why it cannot be picked, or that the analysis will compute it. */
export function fieldOptionNote(name: string, space: Space, saved: string[]): { note?: string; disabled: boolean } {
  if (space === "voxel" && name === "TI_normal") return { note: "mesh only", disabled: true };
  // Nothing known about the simulation (no catalog entry yet): no claim either way.
  if (!saved.length || saved.includes(name) || (name === "TI_max" && saved.includes("mTI_max")) || name === "TI_normal") return { disabled: false };
  // Its conductivity is not kept, so it cannot be computed after the run (tit/volume_fields.py).
  if (name === "hf_power_density") return { note: "not saved", disabled: true };
  return { note: "computed when analysed", disabled: false };
}

/**
 * `available` is the simulation's catalog `fields`: what it saved, read from its field mesh and its
 * NIfTIs (`magnE` included). Every field the analyzer accepts is offered: one the simulation did not
 * save is computed from its channel meshes when the analysis runs (and kept), and says so;
 * `hf_power_density` cannot be, so unsaved it is disabled.
 */
export function AnalysisFieldSelect({value,space,available=[],onChange}: {value:string;space:Space;available?:string[];onChange:(value:string)=>void}) {
  const saved=available.filter((name)=>fieldSpecForName(name) !== undefined);
  const names=FIELD_REGISTRY.map((field)=>field.name);
  const retained=value !== AUTO_FIELD && !names.includes(value) ? [value,...names] : names;
  return <Select value={value} onValueChange={onChange} aria-label="Field" options={[
    {value:AUTO_FIELD,label:"Auto"},...retained.map((name)=>{
      const {note,disabled}=fieldOptionNote(name,space,saved);
      return {value:name,label:note ? `${name} (${note})` : name,disabled};
    }),
  ]}/>;
}
