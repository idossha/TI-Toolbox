import type { Region } from "./api";
import type { Pair, SceneRegionRef } from "../../_shared/scene/model";

export const exportRegionKey = (region: {
  name: string;
  hemi?: string | null;
}): string => (region.hemi ? `${region.hemi}.${region.name}` : region.name);

export function selectedSceneRegions(
  catalog: Region[],
  selected: string[],
): SceneRegionRef[] {
  return catalog
    .filter((region) => selected.includes(exportRegionKey(region)))
    .map(({ id, name, hemi }) => ({ id, name, ...(hemi ? { hemi } : {}) }));
}

/** Saved simulation metadata, never a similarly named montage from the editable catalog. */
export function readExportMontage(text: string): {
  net: string;
  pairs: Pair[];
} {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object")
    throw new Error("The simulation configuration is invalid.");
  const config = value as Record<string, unknown>;
  if (typeof config.eeg_net !== "string" || !config.eeg_net.trim())
    throw new Error("This simulation has no recorded EEG net.");
  const raw = config.electrode_pairs;
  if (
    !Array.isArray(raw) ||
    raw.length === 0 ||
    raw.some(
      (pair) =>
        !Array.isArray(pair) ||
        pair.length !== 2 ||
        pair.some((name) => typeof name !== "string" || !name.trim()),
    )
  ) {
    throw new Error("This simulation has no valid recorded electrode pairs.");
  }
  return { net: config.eeg_net, pairs: raw as Pair[] };
}

/** The generic custom-file resolver uses scalar display defaults even for segmentation files.
 * Rendering settings belong to this preview; they never alter the source volume or export config.
 * Tetravox classifies labels from voxel values, not from the filename or these display settings.
 */
export function segmentationPreviewScene<
  T extends { layers: Record<string, unknown>[] },
>(scene: T): T {
  return {
    ...scene,
    layers: scene.layers.map((layer) =>
      layer.kind === "volume"
        ? {
            ...layer,
            interpolation: "nearest",
            labelMode: "both",
            outlineWidthPx: 2,
            showIn3D: true,
            selectedLabels: [],
            // Label zero is the outside-of-atlas background, never an export region.
            threshold: {
              lo: 0.5,
              hi: null,
              symmetric: false,
              mode: "hide",
              softEdge: 0,
            },
          }
        : layer,
    ),
  };
}
