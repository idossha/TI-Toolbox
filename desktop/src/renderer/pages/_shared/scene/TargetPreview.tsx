import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmbedFrame } from "../../../viewer/EmbedFrame";
import { createChannel, type EmbedChannel } from "../../../viewer/channel";
import type { EmbedViewSpec } from "../../../viewer/protocol";
import type { RoiValue } from "../roi";
import { targetPreviewRoi, type TargetPreviewRoi } from "./targetPreviewModel";
import "../../../viewer/viewer.css";

type PreviewRequest = { subject: string; roi: TargetPreviewRoi };

async function getTargetPreview(body: PreviewRequest, signal: AbortSignal): Promise<EmbedViewSpec> {
  const response = await fetch("/api/scene/target-preview", {
    method: "POST", credentials: "same-origin", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `Target preview failed (HTTP ${response.status}).`);
  }
  return (payload as { scene: EmbedViewSpec }).scene;
}

/** Own channel and viewport; no shared Viewer state or target-editing event handlers. */
function TargetFrame({ scene }: { scene: EmbedViewSpec }) {
  const channel = useRef<EmbedChannel | null>(null);
  const [status, setStatus] = useState("Loading target…");
  const connect = useCallback((frame: HTMLIFrameElement, origin: string, timeout: number) => {
    channel.current = createChannel(frame, origin, (message) => {
      if (message.type === "ready") {
        if (!message.caps.webgl2) { setStatus("Target preview requires WebGL2."); return; }
        channel.current?.post({ type: "setPickEvents", enabled: false });
        channel.current?.post({ type: "load", scene });
      } else if (message.type === "loaded") setStatus("");
      else if (message.type === "error") setStatus(message.message);
      else if (message.type === "progress") setStatus(`${message.name}: ${message.phase}`);
    }, timeout, () => setStatus("The target viewer did not answer. Check that the container includes Tetravox."));
  }, [scene]);
  const disconnect = useCallback(() => {
    channel.current?.post({ type: "reset" });
    channel.current?.dispose();
    channel.current = null;
  }, []);
  return <>
    {status && <p className="field-help" role="status">{status}</p>}
    <div style={{ position: "relative", flex: 1, minHeight: 240 }}>
      <EmbedFrame connect={connect} disconnect={disconnect} title="Target preview" presentation="viewport" testId="target-preview-frame" className="tvx-frame" />
    </div>
  </>;
}

export function TargetPreview({ subject, roi }: { subject: string | undefined; roi: RoiValue | undefined }) {
  const target = targetPreviewRoi(roi);
  const requestKey = subject && target ? JSON.stringify({ subject, roi: target }) : "";
  const [settledKey, setSettledKey] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setSettledKey(requestKey), 250);
    return () => clearTimeout(timer);
  }, [requestKey]);
  // The CURRENT key owns the observer, so input edits abort the old request immediately.
  // Its frame is hidden during debounce; a late response cannot restore a previous target.
  const preview = useQuery({
    queryKey: ["scene", "target-preview", requestKey],
    queryFn: ({ signal }) => getTargetPreview(JSON.parse(requestKey) as PreviewRequest, signal),
    enabled: !!requestKey && requestKey === settledKey,
    staleTime: 60_000, gcTime: 5 * 60_000, retry: false, refetchOnWindowFocus: false,
  });
  let note: string | null = null;
  if (!subject) note = "Choose a subject to preview its target.";
  else if (!target) note = "Complete the target in the job editor to preview it.";
  else if (requestKey !== settledKey || preview.isPending) note = "Preparing target preview…";
  else if (preview.error) note = `Preview unavailable: ${preview.error.message}`;
  return <div data-testid="target-preview" style={{ height: "100%", minHeight: 280, display: "flex", flexDirection: "column" }}>
    <p className="field-help">Target extent in subject space · Read-only preview. Edit the target in the job editor.</p>
    {roi?.mode === "saved" && roi.selected.length > 1 && !roi.combine && <p className="field-help">Selected extents are shown together; each target still runs separately.</p>}
    {note ? <p className="field-help" role="status">{note}</p> : preview.data ? <TargetFrame key={requestKey} scene={preview.data} /> : null}
  </div>;
}
