import { useMutation, useQuery } from "@tanstack/react-query";
import { ScenePane } from "../../_shared/scene";
import {
  useSceneElectrodes,
  useSceneManifest,
} from "../../_shared/scene/queries";
import { markersFromElectrodes } from "../../_shared/scene/model";
import { getTextFile } from "../../results/api";
import { openView } from "../../viewer/api";
import { Button } from "../../../ui/Button";
import { openNativeScene, exportNativeScene } from "../../../viewer/native";
import { getAtlasRegions } from "./api";
import type { Mode } from "./config";
import {
  exportRegionKey,
  readExportMontage,
  selectedSceneRegions,
  segmentationPreviewScene,
} from "./previewModel";

export interface ExportPreviewProps {
  mode: Mode;
  subjectId: string;
  simulationName: string;
  simulationPath?: string;
  atlas: string;
  regions: string[];
  onRegionsChange: (regions: string[]) => void;
  onAtlasChange: (atlas: string) => void;
  montageOnly: boolean;
  diameterMm?: number;
  onLabelsChange?: (labels: number[]) => void;
  labels: number[];
  niftiPath: string;
  fieldName: string;
}

/** Each preview owns its channel: opening an export must not replace the retained Viewer scene. */
export function ExportPreview(props: ExportPreviewProps) {
  const {
    mode,
    subjectId,
    simulationName,
    simulationPath,
    atlas,
    regions,
    onRegionsChange,
    onAtlasChange,
    montageOnly,
    niftiPath,
    fieldName,
  } = props;
  const manifest = useSceneManifest(subjectId || null);
  const catalog = useQuery({
    queryKey: ["atlas-regions", subjectId, atlas],
    queryFn: () => getAtlasRegions(subjectId, atlas),
    enabled: mode === "regions" && !!subjectId,
  });
  const montage = useQuery({
    queryKey: ["export-montage", subjectId, simulationName, simulationPath],
    queryFn: async () =>
      readExportMontage(
        await getTextFile(`${simulationPath}/documentation/config.json`),
      ),
    enabled: mode === "montage" && !!subjectId && !!simulationPath,
    retry: false,
  });
  const electrodes = useSceneElectrodes(
    mode === "montage" ? subjectId || null : null,
    montage.data?.net ?? null,
  );
  const defaultVolume = manifest.data?.volumes.find(
    (volume) => volume.id === "labeling",
  )?.url;
  const volumePath =
    niftiPath.trim() ||
    (defaultVolume?.startsWith("/api/files/raw/")
      ? decodeURIComponent(defaultVolume.slice("/api/files/raw".length))
      : "");
  const volume = useMutation({mutationFn: async () => {
    const scene = mode === "subcortical"
      ? await openView("custom", { subject: subjectId, path: volumePath }, { files: [volumePath] })
      : await openView("simulation", { subject: subjectId, simulation: simulationName, space: "subject", field: fieldName });
    if (mode === "subcortical") {
      const prepared = segmentationPreviewScene(scene.view as { layers: Record<string, unknown>[] });
      prepared.layers = prepared.layers.map((layer) => layer.kind === "volume" ? { ...layer, selectedLabels: props.labels } : layer);
      await openNativeScene(await exportNativeScene(prepared, "export-preview"));
    } else await openNativeScene(scene.path);
  }});

  if (!subjectId)
    return (
      <p className="field-help">
        Choose a subject to preview its export inputs.
      </p>
    );
  if (mode === "subcortical" || mode === "vectors") {
    if (mode === "subcortical" && !volumePath)
      return (
        <p className="field-help">
          Choose a segmentation NIfTI, or use a subject with a segmentation
          volume.
        </p>
      );
    if (mode === "vectors" && !simulationName)
      return (
        <p className="field-help">Choose a simulation to preview its field.</p>
      );
    return <div>
      <p className="field-help">Open the export inputs in native TetraVox. Selected export labels and vector settings remain controlled here.</p>
      <Button onClick={() => volume.mutate()} disabled={volume.isPending || !window.tit?.openNativeTetravox}>{volume.isPending ? "Preparing scene…" : "Open inputs in TetraVox"}</Button>
      {!window.tit?.openNativeTetravox && <p className="field-help">Use TI-Toolbox Desktop to open the native viewer.</p>}
      {volume.error && <p role="alert">{volume.error.message}</p>}
    </div>;
  }

  if (manifest.error)
    return (
      <p className="field-help" role="status">
        Subject preview unavailable: {manifest.error.message}
      </p>
    );
  if (!manifest.data || manifest.data.building)
    return (
      <p className="field-help" role="status">
        Preparing this subject’s anatomy…
      </p>
    );
  if (mode === "regions")
    return (
      <ScenePane
        mode="target"
        subject={subjectId}
        atlas={atlas}
        onAtlasChange={onAtlasChange}
        regions={selectedSceneRegions(catalog.data ?? [], regions)}
        onRegionsChange={(next) => onRegionsChange(next.map(exportRegionKey))}
        note="Click atlas regions to add or remove them from the export. Empty selection exports whole grey matter."
      />
    );
  if (!simulationPath)
    return (
      <p className="field-help">
        Choose a simulation to preview its recorded montage.
      </p>
    );
  const error = montage.error ?? electrodes.error;
  if (error)
    return (
      <p className="field-help" role="status">
        Montage preview unavailable: {error.message}
      </p>
    );
  if (!montage.data || !electrodes.data)
    return (
      <p className="field-help" role="status">
        Reading the simulation’s montage…
      </p>
    );
  const channels = Object.fromEntries(
    montage.data.pairs.flatMap((pair, index) =>
      pair.map((name) => [name, index]),
    ),
  );
  const missing = Object.keys(channels).filter(
    (name) =>
      !electrodes.data.electrodes.some((electrode) => electrode.name === name),
  );
  if (missing.length)
    return (
      <p className="field-help">
        Recorded electrodes missing from this net: {missing.join(", ")}.
      </p>
    );
  const markers = markersFromElectrodes(
    electrodes.data.electrodes,
    channels,
  ).filter((marker) => !montageOnly || marker.channel !== undefined);
  return (
    <ScenePane
      mode="montage"
      subject={subjectId}
      placedMarkers={markers}
      net={montage.data.net}
      showing={{ montage: simulationName, net: montage.data.net }}
      note="Recorded simulation montage on this subject’s head. Electrode markers show positions; export applies the configured dimensions."
    />
  );
}
