import { describe, expect, it } from "vitest";
import { configFor, editorFromNode, editorError, defaultEditor } from "../../src/renderer/pages/pipeline/editors";
const lookup = () => undefined;
const sim = { subject_id: "101", montages: [{ _type: "Montage", name: "test", mode: "net", electrode_pairs: [["F3", "F4"], ["C3", "C4"]], eeg_net: "cap.csv" }], intensities: [1.3, 1.7], electrode_shape: "rectangle", electrode_dimensions: [12, 9], gel_thickness: 5, output_fields: ["TI_max", "hf_sar"], map_to_fsavg: true, conductivity: "vn", aniso_maxratio: 6, aniso_maxcond: 1.8, future_setting: { keep: true } };
describe("pipeline config preservation", () => {
  it("hydrates simulator controls and changes only conductivity", () => {
    const editor = editorFromNode({ kind: "sim", config: sim });
    expect(configFor(editor, lookup, sim)).toEqual(sim);
    if (editor.kind !== "sim") throw Error("wrong editor");
    expect(editor.currents).toBe("1.3, 1.7");
    expect(editor.params.dimensions).toEqual([12, 9]);
    expect(configFor({ ...editor, params: { ...editor.params, conductivity: "mc" } }, lookup, sim, [], editor)).toEqual({ ...sim, conductivity: "mc" });
  });
  it("preserves an analyzer target when changing its simulation", () => {
    const config = { simulation: "old", space: "voxel", analysis_type: "spherical", coordinate_space: "mni", center: [20,10,-4], radius: 8, tissue_type: "WM", field: "custom", extra: [1,2] };
    const editor = editorFromNode({kind:"analyzer",config});
    expect(configFor(editor,lookup,config)).toEqual(config);
    if(editor.kind!=="analyzer") throw Error("wrong editor");
    expect(editor.sphere).toEqual({x:20,y:10,z:-4,radius:8});
    expect(configFor({...editor,simulation:"new"},lookup,config,[],editor)).toEqual({...config,simulation:"new"});
  });
  it("preserves full flex configuration when changing current", () => {
    const config = { goal:"focality", current_mA:2, roi:{_type:"SphericalROI",x:20,y:10,z:-4,radius:8,use_mni:true,volumetric:true}, n_multistart:5, output_folder:"custom", thresholds:"0.2,0.8", detailed_results:true, future_setting:42 };
    const editor=editorFromNode({kind:"flex",config});
    expect(configFor(editor,lookup,config)).toEqual(config);
    if(editor.kind!=="flex") throw Error("wrong editor");
    expect(configFor({...editor,form:{...editor.form,currentMA:3}},lookup,config,[],editor)).toEqual({...config,current_mA:3});
  });
  it("keeps disabled preprocessing flags and unknown config", () => {
    const config={create_m2m:false,run_fastsurfer:false,subject_ids:["101"],custom:true};
    const editor=editorFromNode({kind:"pre",config});
    expect(configFor(editor,lookup,config)).toEqual(config);
    if(editor.kind!=="pre") throw Error("wrong editor");
    expect(configFor({...editor,stages:{...editor.stages,create_m2m:true}},lookup,config,[],editor)).toEqual({...config,create_m2m:true});
  });
});

it("uses resolved catalog montage definitions without dropping existing physics", () => {
  const editor=editorFromNode({kind:"sim",config:sim});
  if(editor.kind!=="sim") throw Error("wrong editor");
  const montage={_type:"Montage",name:"new",mode:"net",electrode_pairs:[["AF3","AF4"],["P3","P4"]],eeg_net:"cap.csv"};
  const next={...editor,montages:"test, new",definitions:[...editor.definitions!,montage]};
  expect(configFor(next,lookup,sim,[],editor)).toEqual({...sim,montages:[...sim.montages,montage]});
});
it("flags invalid and nonobject JSON while retaining last valid config",()=>{
  const editor={kind:"json" as const,nodeKind:"leadfield" as const,text:"{"};
  expect(editorError(editor)).toMatch(/invalid JSON/);
  expect(configFor(editor,lookup,{keep:true})).toEqual({keep:true});
  expect(editorError({...editor,text:"[]"})).toMatch(/JSON object/);
  expect(editorError({...editor,text:'{"value":3}'})).toBeNull();
});
it("restores a NIfTI analyzer target without replacing its coordinate space",()=>{
  const config={analysis_type:"nifti_mask",mask_path:"/mnt/mask.nii.gz",coordinate_space:"mni",simulation:"old"};
  const editor=editorFromNode({kind:"analyzer",config});
  if(editor.kind!=="analyzer") throw Error("wrong editor");
  expect(editor.analysisType).toBe("mask");
  expect(editor.roi).toMatchObject({mode:"mask",space:"mni",path:"/mnt/mask.nii.gz"});
  expect(configFor({...editor,simulation:"new"},lookup,config,[],editor)).toEqual({...config,simulation:"new"});
});

it.each(["flex", "sim", "analyzer"] as const)("initializes shared-builder defaults when adding a %s node", (kind)=>{
  const before=defaultEditor(kind);
  let next=before;
  if(before.kind === "flex") next={...before,roi:{mode:"spherical",space:"subject",volumetric:true,tissues:"GM",spheres:[{x:1,y:2,z:3,radius:4}]}};
  if(before.kind === "sim") next={...before,montages:"test",definitions:sim.montages};
  if(before.kind === "analyzer") next={...before,simulation:"test",sphere:{x:1,y:2,z:3,radius:4}};
  const initial=configFor(next,lookup,undefined,["101"]);
  expect(initial.subject_id).toBe("101");
  if(kind === "flex") expect(initial).toMatchObject({current_mA:1,electrode:expect.any(Object),roi:expect.any(Object)});
  if(kind === "sim") expect(initial).toMatchObject({intensities:[1,1],montages:sim.montages,electrode_shape:"ellipse"});
  if(kind === "analyzer") expect(initial).toMatchObject({simulation:"test",center:[1,2,3],radius:4});
});
