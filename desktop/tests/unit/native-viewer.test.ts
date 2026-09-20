import { afterEach, describe, expect, it, vi } from "vitest";
import { openNativeScene, exportNativeScene, saveNativeScene, savedNativeScenePath } from "../../src/renderer/viewer/native";

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
  it("treats replacement cancellation as a quiet no-op", async () => {
    vi.stubGlobal("window", { tit: { openNativeTetravox: vi.fn().mockResolvedValue({ ok: false, cancelled: true }) } });
    await expect(openNativeScene("/mnt/scene.tetravox.json")).resolves.toBeUndefined();
  });
  it("exports the prepared scene before launching its native file",async()=>{
    const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({scene_path:"/mnt/project/target.tetravox.json"})});
    vi.stubGlobal("fetch",fetch);
    const scene={version:2,datasets:[],layers:[]};
    expect(await exportNativeScene(scene,"target-preview")).toBe("/mnt/project/target.tetravox.json");
    expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({scene,name:"target-preview"});
  });
});


describe("saving the live native scene", () => {
  it("returns the confirmed project path without posting a builder recipe", async () => {
    const path = "/mnt/project/code/ti-toolbox/viewer/scenes/my-scene.tetravox.json";
    const saveNativeTetravoxScene = vi.fn().mockResolvedValue({ ok: true, path });
    const fetch = vi.fn();
    vi.stubGlobal("window", { tit: { saveNativeTetravoxScene } });
    vi.stubGlobal("fetch", fetch);
    await expect(saveNativeScene("my-scene")).resolves.toBe(path);
    expect(saveNativeTetravoxScene).toHaveBeenCalledWith("my-scene");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not claim a save after cancellation", async () => {
    vi.stubGlobal("window", { tit: { saveNativeTetravoxScene: vi.fn().mockResolvedValue({ ok: false, cancelled: true }) } });
    await expect(saveNativeScene("my-scene")).resolves.toBeNull();
  });
  it.each([
    { ok: false, reason: "Native scene saving is unavailable." },
    { ok: true },
    { ok: true, path: "" },
  ])("rejects a failed or incomplete receipt: %j", async (receipt) => {
    vi.stubGlobal("window", { tit: { saveNativeTetravoxScene: vi.fn().mockResolvedValue(receipt) } });
    await expect(saveNativeScene("my-scene")).rejects.toThrow(receipt.reason ?? "did not confirm");
  });
  it("reports an unavailable native bridge", async () => {
    vi.stubGlobal("window", {});
    await expect(saveNativeScene("my-scene")).rejects.toThrow("compatible TetraVox");
  });
});


describe("reopening saved native scenes", () => {
  it("keeps scene-relative datasets and outside-project absolute fallbacks at the original scene path", async () => {
    const scene = { title: "/api/files/raw/annotation", datasets: [{ label: "/api/files/raw/not-a-file", path: "../../../../derivatives/T1.nii.gz", absPath: "/host/project/derivatives/T1.nii.gz" }, { path: "../../../../../shared/T2.nii.gz", absPath: "/host/shared/T2.nii.gz" }] };
    const path = "/mnt/project/code/ti-toolbox/viewer/scenes/live.tetravox.json";
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect(await savedNativeScenePath(scene, path, "saved-live")).toBe(path);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("exports legacy server references including sidecars", async () => {
    const scene = { datasets: [{ path: "T1.nii.gz", options: { lut: { path: "/api/files/raw/mnt/project/labels.txt" } } }] };
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ scene_path: "/mnt/project/export.tetravox.json" }) });
    vi.stubGlobal("fetch", fetch);
    expect(await savedNativeScenePath(scene, "/mnt/project/original.tetravox.json", "legacy")).toBe("/mnt/project/export.tetravox.json");
    expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({ scene, name: "legacy" });
  });
});
