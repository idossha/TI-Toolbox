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
function TargetFrame({ scene }: { scene: EmbedViewSpec | null }) {
  const channel = useRef<EmbedChannel | null>(null);
  const latest = useRef(scene);
  const ready = useRef(false);
  const sent = useRef<{ scene: EmbedViewSpec; id: string } | null>(null);
  const sequence = useRef(0);
  const [result, setResult] = useState<{ scene: EmbedViewSpec | null; status: string; loaded: boolean }>({ scene: null, status: "Loading target…", loaded: false });
  const send = useCallback(() => {
    if (!ready.current || !latest.current || sent.current?.scene === latest.current) return;
    const id = `target-${++sequence.current}`;
    sent.current = { scene: latest.current, id };
    channel.current?.post({ type: "load", scene: latest.current, id });
  }, []);
  useEffect(() => { latest.current = scene; send(); }, [scene, send]);
  const connect = useCallback((frame: HTMLIFrameElement, origin: string, timeout: number) => {
    channel.current = createChannel(frame, origin, (message) => {
      if (message.type === "ready") {
        if (!message.caps.webgl2) { setResult({ scene: latest.current, status: "Target preview requires WebGL2.", loaded: false }); return; }
        ready.current = true;
        channel.current?.post({ type: "setPickEvents", enabled: false });
        send();
      } else if (sent.current?.scene === latest.current && message.id === sent.current?.id) {
        if (message.type === "loaded") setResult({ scene: latest.current, status: "", loaded: true });
        else if (message.type === "error") setResult({ scene: latest.current, status: message.message, loaded: false });
        else if (message.type === "progress") setResult({ scene: latest.current, status: `${message.name}: ${message.phase}`, loaded: false });
      }
    }, timeout, () => setResult({ scene: latest.current, status: "The target viewer did not answer. Check that the container includes Tetravox.", loaded: false }));
  }, [send]);
  const disconnect = useCallback(() => {
    channel.current?.post({ type: "reset" });
    channel.current?.dispose();
    channel.current = null;
    ready.current = false;
    sent.current = null;
  }, []);
  const visible = scene !== null && result.scene === scene && result.loaded;
  const status = result.scene === scene ? result.status : "Loading target…";
  return <>
    {scene && status && <p className="field-help" role="status">{status}</p>}
    <div style={{ position: "relative", flex: 1, minHeight: 240, visibility: visible ? "visible" : "hidden" }}>
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
  // The retained frame is hidden during debounce; its engine and anatomy stay available.
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
    <p className="field-help">Lightweight target preview in subject space · Read-only. Edit the target in the job editor.</p>
    {roi?.mode === "saved" && roi.selected.length > 1 && !roi.combine && <p className="field-help">Selected extents are shown together; each target still runs separately.</p>}
    {note && <p className="field-help" role="status">{note}</p>}
    {subject && <TargetFrame key={subject} scene={note ? null : preview.data ?? null} />}
  </div>;
}
