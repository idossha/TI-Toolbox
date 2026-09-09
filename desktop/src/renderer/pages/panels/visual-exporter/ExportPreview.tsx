import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScenePane } from "../../_shared/scene";
import {
  useSceneElectrodes,
  useSceneManifest,
} from "../../_shared/scene/queries";
import { markersFromElectrodes } from "../../_shared/scene/model";
import { getTextFile } from "../../results/api";
import { openView } from "../../viewer/api";
import "../../../viewer/viewer.css";
import { EmbedFrame } from "../../../viewer/EmbedFrame";
import { createChannel, type EmbedChannel } from "../../../viewer/channel";
import { normalizeLayers, type EmbedViewSpec } from "../../../viewer/protocol";
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
function VolumeFrame({
  scene,
  labels,
  onLabelsChange,
}: {
  scene: EmbedViewSpec;
  labels: number[];
  onLabelsChange?: (labels: number[]) => void;
}) {
  const latest = useRef({ labels, onLabelsChange });
  useEffect(() => {
    latest.current = { labels, onLabelsChange };
  }, [labels, onLabelsChange]);
  const layerIds = useRef<string[]>([]);
  const channel = useRef<EmbedChannel | null>(null);
  const [status, setStatus] = useState("Loading preview…");
  const connect = useCallback(
    (frame: HTMLIFrameElement, origin: string, timeout: number) => {
      channel.current = createChannel(
        frame,
        origin,
        (message) => {
          if (message.type === "ready") {
            if (!message.caps.webgl2) {
              setStatus("3D preview requires WebGL2.");
              return;
            }
            channel.current?.post({
              type: "setPickEvents",
              enabled: !!latest.current.onLabelsChange,
            });
            channel.current?.post({ type: "load", scene });
          } else if (message.type === "loaded") {
            setStatus("");
            layerIds.current = normalizeLayers(message.layers)
              .filter((layer) => layer.kind === "volume")
              .map((layer) => layer.id);
            if (latest.current.onLabelsChange)
              for (const layerId of layerIds.current)
                channel.current?.post({
                  type: "updateLayer",
                  layerId,
                  patch: {
                    selectedLabels: latest.current.labels,
                    showIn3D: true,
                  },
                });
          } else if (
            message.type === "pick" &&
            message.label &&
            latest.current.onLabelsChange
          ) {
            const id = message.label.id;
            if (id > 0)
              latest.current.onLabelsChange(
                latest.current.labels.includes(id)
                  ? latest.current.labels.filter((value) => value !== id)
                  : [...latest.current.labels, id],
              );
          } else if (message.type === "error") setStatus(message.message);
          else if (message.type === "progress")
            setStatus(`${message.name}: ${message.phase}`);
        },
        timeout,
        () =>
          setStatus(
            "The viewer did not answer. Check that the container includes Tetravox.",
          ),
      );
    },
    [scene],
  );
  useEffect(() => {
    if (onLabelsChange)
      for (const layerId of layerIds.current)
        channel.current?.post({
          type: "updateLayer",
          layerId,
          patch: { selectedLabels: labels },
        });
  }, [labels, onLabelsChange]);
  const disconnect = useCallback(() => {
    channel.current?.post({ type: "reset" });
    channel.current?.dispose();
    channel.current = null;
  }, []);
  return (
    <div
      style={{
        height: "100%",
        minHeight: 280,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {status && (
        <p className="field-help" role="status">
          {status}
        </p>
      )}
      <div style={{ position: "relative", flex: 1, minHeight: 240 }}>
        <EmbedFrame
          connect={connect}
          disconnect={disconnect}
          title="Export volume preview"
          presentation="viewport"
          testId="export-volume-frame"
          className="tvx-frame"
        />
      </div>
    </div>
  );
}

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
    labels,
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
  const volume = useQuery({
    queryKey: [
      "export-volume",
      mode,
      subjectId,
      simulationName,
      volumePath,
      fieldName,
    ],
    queryFn: ({ signal }) =>
      mode === "subcortical"
        ? openView(
            "custom",
            { subject: subjectId, path: volumePath },
            { files: [volumePath], dry_run: true, signal },
          ).then((result) => ({
            ...result,
            view: segmentationPreviewScene(
              result.view as unknown as EmbedViewSpec,
            ),
          }))
        : openView(
            "simulation",
            {
              subject: subjectId,
              simulation: simulationName,
              space: "subject",
              field: fieldName,
            },
            { dry_run: true, signal },
          ),
    enabled:
      !!subjectId &&
      ((mode === "subcortical" && !!volumePath) ||
        (mode === "vectors" && !!simulationName)),
    retry: false,
  });

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
    if (volume.error)
      return (
        <p className="field-help" role="status">
          Preview unavailable: {volume.error.message}
        </p>
      );
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <p className="field-help">
          {mode === "subcortical"
            ? `Segmentation volume · ${labels.length ? `export labels ${labels.join(", ")}` : "export whole volume"}. Pick labelled regions in the preview or the form; selected labels are outlined within the full atlas.`
            : `Field context for ${simulationName}. Vector arrows and their sampling are generated during export.`}
        </p>
        {volume.data ? (
          <VolumeFrame
            key={`${mode}:${subjectId}:${simulationName}:${volumePath}:${fieldName}`}
            scene={volume.data.view as unknown as EmbedViewSpec}
            labels={labels}
            onLabelsChange={
              mode === "subcortical" ? props.onLabelsChange : undefined
            }
          />
        ) : (
          <p className="field-help" role="status">
            Resolving preview…
          </p>
        )}
      </div>
    );
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
