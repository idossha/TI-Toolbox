import { useMutation } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { openNativeScene, exportNativeScene } from "../../../viewer/native";
import { RoiSpaceControl, type RoiValue } from "../roi";
import { targetPreviewRoi } from "./targetPreviewModel";
import { ScenePane } from "./ScenePane";

/**
 * The 3D target pane and the Subject | MNI control that sits above it.
 *
 * Three claims, each with the failure it prevents:
 *
 *  - **One space, two controls.** The switch here and the one inside the ROI picker's panel are
 *    the same component writing the same `RoiValue.space` (`docs/dev/DECISIONS.md § 2026-09-17`).
 *    Two fields is how a user selects MNI above the pane, leaves the picker saying Subject, and
 *    gets a job that ran on whichever one the config builder happened to read.
 *  - **Subject space draws the row's subject**, not a stand-in: charm's islands, an atlas this
 *    subject does not have and a half-built head model are all invisible on someone else's head.
 *    `<ScenePane>` falls back to the packaged guide and says so when there is no head model yet.
 *  - **MNI space draws MNI152**, the anatomy the coordinates and atlases are actually defined on.
 *
 * The ROI *mode* still decides whether there is a pane at all: an atlas target (cortical or
 * subcortical, or a row that has not chosen yet) gets `<ScenePane>`, and the modes with no anatomy
 * to draw — a saved ROI CSV, a spherical target, a mask file — get the native TetraVox button,
 * with the space control above it either way.
 */
export function TargetPreview({ subject, roi, onRoiChange }: {
  subject: string | undefined; roi: RoiValue | undefined; onRoiChange?: (roi: RoiValue) => void;
}) {
  const target = targetPreviewRoi(roi);
  const space = roi?.space ?? "subject";
  const preview = useMutation({ mutationFn: async () => {
    const response = await fetch("/api/scene/target-preview", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, roi: target }),
    });
    const result = await response.json() as { scene?: Record<string, unknown>; detail?: string };
    if (!response.ok || !result.scene) throw new Error(result.detail ?? "Could not prepare a native target scene.");
    await openNativeScene(await exportNativeScene(result.scene, "target-preview"));
  } });

  const spaceSwitch = roi && onRoiChange ? (
    <div className="scene-pane-space" data-testid="scene-pane-space">
      <span className="field-help">Space</span>
      <RoiSpaceControl value={roi} onChange={onRoiChange} label="Target space" id="scene-pane-space-control" />
    </div>
  ) : null;

  if (!roi || roi.mode === "cortical" || roi.mode === "subcortical") {
    return <div className="scene-pane-wrap" data-testid="target-preview">
      {spaceSwitch}
      <ScenePane mode="target"
        subject={space === "mni" ? null : subject}
        guide={space === "mni" ? "mni" : "default"}
        atlas={roi?.atlas ?? (roi?.mode === "subcortical" && space === "subject" ? "labeling.nii.gz" : null)}
        regions={roi?.regions}
        onAtlasChange={(atlas, kind) => onRoiChange?.(kind === "subcortical"
          ? { mode: "subcortical", atlas, space, tissues: "GM", regions: [] }
          : { mode: "cortical", atlas, space, regions: [] })}
        onRegionsChange={(regions, atlas) => onRoiChange?.(roi?.mode === "subcortical"
          ? { ...roi, atlas: atlas ?? roi.atlas, regions }
          : { mode: "cortical", space, atlas: atlas ?? (roi?.mode === "cortical" ? roi.atlas : undefined), regions })} />
    </div>;
  }
  return <div data-testid="target-preview" style={{ padding: "var(--space-3)" }}>
    {spaceSwitch}
    <p className="field-help">Inspect this subject-specific target in native TetraVox.</p>
    <Button disabled={!subject || !target || preview.isPending || !window.tit?.openNativeTetravox} onClick={() => preview.mutate()}>{preview.isPending ? "Preparing target…" : "Open target in TetraVox"}</Button>
    {preview.error && <p role="alert">{preview.error.message}</p>}
  </div>;
}
