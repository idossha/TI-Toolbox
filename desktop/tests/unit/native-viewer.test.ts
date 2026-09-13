import { afterEach, describe, expect, it, vi } from "vitest";
import { openNativeScene, exportNativeScene } from "../../src/renderer/viewer/native";

afterEach(() => vi.unstubAllGlobals());
describe("native TetraVox handoff", () => {
  it("passes the container scene path unchanged to the main process", async () => {
    const openNativeTetravox = vi.fn().mockResolvedValue({ok:true});
    vi.stubGlobal("window",{tit:{openNativeTetravox}});
    await openNativeScene("/mnt/project/code/ti-toolbox/viewer/subject.tetravox.json");
    expect(openNativeTetravox).toHaveBeenCalledWith("/mnt/project/code/ti-toolbox/viewer/subject.tetravox.json");
  });
  it("reports native refusal and browser limitations",async()=>{
    vi.stubGlobal("window",{tit:{openNativeTetravox:vi.fn().mockResolvedValue({ok:false,reason:"Install TetraVox first."})}});
    await expect(openNativeScene("/mnt/scene.tetravox.json")).rejects.toThrow("Install TetraVox first.");
    vi.stubGlobal("window",{});
    await expect(openNativeScene("/mnt/scene.tetravox.json")).rejects.toThrow("TI-Toolbox Desktop");
  });
  it("exports the prepared scene before launching its native file",async()=>{
    const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({scene_path:"/mnt/project/target.tetravox.json"})});
    vi.stubGlobal("fetch",fetch);
    const scene={version:2,datasets:[],layers:[]};
    expect(await exportNativeScene(scene,"target-preview")).toBe("/mnt/project/target.tetravox.json");
    expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({scene,name:"target-preview"});
  });
});
