import { useMutation } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { openNativeScene, exportNativeScene } from "../../../viewer/native";
import type { RoiValue } from "../roi";
import { targetPreviewRoi } from "./targetPreviewModel";

export function TargetPreview({ subject, roi }: { subject: string | undefined; roi: RoiValue | undefined }) {
  const target = targetPreviewRoi(roi);
  const preview = useMutation({ mutationFn: async () => {
    const response = await fetch("/api/scene/target-preview", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, roi: target }),
    });
    const result = await response.json() as { scene?: Record<string, unknown>; detail?: string };
    if (!response.ok || !result.scene) throw new Error(result.detail ?? "Could not prepare a native target scene.");
    await openNativeScene(await exportNativeScene(result.scene!, "target-preview"));
  } });
  return <div data-testid="target-preview" style={{ padding: "var(--space-3)" }}>
    <p className="field-help">Inspect the selected target in native TetraVox. Edit target settings in the job editor.</p>
    <Button disabled={!subject || !target || preview.isPending || !window.tit?.openNativeTetravox} onClick={() => preview.mutate()}>{preview.isPending ? "Preparing target…" : "Open target in TetraVox"}</Button>
    {!window.tit?.openNativeTetravox && <p className="field-help">Use TI-Toolbox Desktop to open the native viewer.</p>}
    {preview.error && <p role="alert">{preview.error.message}</p>}
  </div>;
}
