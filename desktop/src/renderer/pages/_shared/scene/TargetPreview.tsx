import { useMutation } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { openNativeScene, exportNativeScene } from "../../../viewer/native";
import type { RoiValue } from "../roi";
import { targetPreviewRoi } from "./targetPreviewModel";
import { ScenePane } from "./ScenePane";

/** Atlas names are selected on bundled reference anatomy; coordinates remain subject-specific. */
export function TargetPreview({ subject, roi, onRoiChange, allowAtlas = true }: {
  subject: string | undefined; roi: RoiValue | undefined; onRoiChange?: (roi: RoiValue) => void; allowAtlas?: boolean;
}) {
  const target = targetPreviewRoi(roi);
  const preview = useMutation({ mutationFn: async () => {
    const response = await fetch("/api/scene/target-preview", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, roi: target }),
    });
    const result = await response.json() as { scene?: Record<string, unknown>; detail?: string };
    if (!response.ok || !result.scene) throw new Error(result.detail ?? "Could not prepare a native target scene.");
    await openNativeScene(await exportNativeScene(result.scene, "target-preview"));
  } });
  if (allowAtlas && (!roi || roi.mode === "cortical" || roi.mode === "subcortical")) {
    return <ScenePane mode="target" atlas={roi?.atlas ?? (roi?.mode === "subcortical" ? "labeling.nii.gz" : null)} regions={roi?.regions}
      onAtlasChange={(atlas, kind) => onRoiChange?.(kind === "subcortical"
        ? { mode: "subcortical", atlas, atlasSpace: "subject", tissues: "GM", regions: [] }
        : { mode: "cortical", atlas, regions: [] })}
      onRegionsChange={(regions, atlas) => onRoiChange?.(roi?.mode === "subcortical"
        ? { ...roi, atlas: atlas ?? roi.atlas ?? "labeling.nii.gz", regions }
        : { mode: "cortical", atlas: atlas ?? (roi?.mode === "cortical" ? roi.atlas : undefined), regions })} />;
  }
  return <div data-testid="target-preview" style={{ padding: "var(--space-3)" }}>
    <p className="field-help">Inspect this subject-specific target in native TetraVox.</p>
    <Button disabled={!subject || !target || preview.isPending || !window.tit?.openNativeTetravox} onClick={() => preview.mutate()}>{preview.isPending ? "Preparing target…" : "Open target in TetraVox"}</Button>
    {preview.error && <p role="alert">{preview.error.message}</p>}
  </div>;
}
