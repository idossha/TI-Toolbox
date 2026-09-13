/** Native viewer launches accept project container paths; the main process maps and checks them. */
export async function openNativeScene(path: string): Promise<void> {
  if (!window.tit?.openNativeTetravox) throw new Error("Open TI-Toolbox Desktop to launch native TetraVox.");
  const result = await window.tit.openNativeTetravox(path);
  if (!result.ok) throw new Error(result.reason ?? "TetraVox could not be opened.");
}

export async function exportNativeScene(scene: Record<string, unknown>, name: string): Promise<string> {
  const response = await fetch("/api/view/export", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scene, name }) });
  const result = await response.json() as { scene_path?: string; detail?: string };
  if (!response.ok || !result.scene_path) throw new Error(result.detail ?? "Could not export a native scene.");
  return result.scene_path;
}
