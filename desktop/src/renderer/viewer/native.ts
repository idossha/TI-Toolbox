/** Native viewer launches accept project container paths; the main process maps and checks them. */
export async function openNativeScene(path: string): Promise<void> {
  if (!window.tit?.openNativeTetravox) throw new Error("Open TI-Toolbox Desktop to launch native TetraVox.");
  const result = await window.tit.openNativeTetravox(path);
  if (result.cancelled) return;
  if (!result.ok) throw new Error(result.reason ?? "TetraVox could not be opened.");
}

export async function exportNativeScene(scene: Record<string, unknown>, name: string): Promise<string> {
  const response = await fetch("/api/view/export", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scene, name }) });
  const result = await response.json() as { scene_path?: string; detail?: string };
  if (!response.ok || !result.scene_path) throw new Error(result.detail ?? "Could not export a native scene.");
  return result.scene_path;
}

/** Save only a confirmed snapshot of the running native viewer, never the builder recipe. */
export async function saveNativeScene(name: string): Promise<string | null> {
  if (!window.tit?.saveNativeTetravoxScene) throw new Error("Saving a live scene requires TI-Toolbox Desktop and a compatible TetraVox.");
  const result = await window.tit.saveNativeTetravoxScene(name);
  if (result.cancelled) return null;
  if (!result.ok || !result.path) throw new Error(result.reason ?? "TetraVox did not confirm that the scene was saved.");
  return result.path;
}
