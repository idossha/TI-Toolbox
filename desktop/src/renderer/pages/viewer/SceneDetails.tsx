/** Saved-scene previews and metadata stay in the library row, independent of native open. */
import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";
import { Button } from "../../ui/Button";
import { Popover } from "../../ui/Overlay";
import type { SavedScene } from "./api";
import { formatBytes } from "./lib";

export function ScenePreview({ row, active, revision, refresh }: { row: SavedScene; active: boolean; revision: number; refresh(): void }) {
  const frame = useRef<HTMLSpanElement>(null);
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState(false);
  useEffect(() => {
    const preview = window.tit?.previewNativeTetravoxScene;
    if (!active || row.has_thumbnail || !preview || !frame.current) return;
    let cancelled = false;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      setPending(true);
      setError(undefined);
      void preview(row.path).then((result) => {
        if (cancelled) return;
        if (result.ok) refresh();
        else setError(result.reason ?? "Preview unavailable");
      }).catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Preview unavailable");
      }).finally(() => { if (!cancelled) setPending(false); });
    });
    observer.observe(frame.current);
    return () => { cancelled = true; observer.disconnect(); };
  }, [active, row.path, row.has_thumbnail, revision, refresh]);
  return row.has_thumbnail ? (
    <img className="viewer-scene-thumb" src={`/api/files/raw${row.path.replace(/\.tetravox\.json$/, ".png")}?v=${encodeURIComponent(row.modified_at ?? "")}`} alt={`Preview of ${row.name}`} loading="lazy" data-testid={`viewer-scene-preview-${row.slug}`} />
  ) : (
    <span ref={frame} className="viewer-scene-thumb viewer-scene-thumb-empty" title={error ?? (pending ? "Rendering saved scene preview…" : "Scene preview unavailable")} data-testid={`viewer-scene-preview-empty-${row.slug}`} aria-label={pending ? "Generating scene preview" : "Preview unavailable"}>
      {pending ? "…" : "—"}
    </span>
  );
}

function date(value: string | null | undefined): string {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString();
}

/** Modified and Datasets repeat Saved and Layers for most scenes; each shows only when it differs. */
export function SceneInfo({ row }: { row: SavedScene }) {
  const saved = date(row.saved_at);
  const modified = date(row.modified_at);
  return (
    <Popover trigger={<Button variant="ghost" size="sm" icon={<Info size={14} />} aria-label={`Scene information for ${row.name}`} title="Scene information" data-testid={`viewer-scene-info-${row.slug}`} />}>
      <div className="viewer-popover" data-testid={`viewer-scene-details-${row.slug}`}>
        <p className="viewer-popover-title">{row.name}</p>
        <dl className="viewer-scene-details">
          {row.created_at && <><dt>Created</dt><dd>{date(row.created_at)}</dd></>}
          <dt>Saved</dt><dd>{saved}</dd>
          {modified !== saved && <><dt>Modified</dt><dd>{modified}</dd></>}
          <dt>Layers</dt><dd>{row.layer_count ?? "Unavailable"}</dd>
          {row.dataset_count != null && row.dataset_count !== row.layer_count && <><dt>Datasets</dt><dd>{row.dataset_count}</dd></>}
          <dt>Scene file</dt><dd>{row.bytes == null ? "Unavailable" : formatBytes(row.bytes)}</dd>
          <dt>Files</dt><dd>{row.health_message ?? "Not checked"}</dd>
        </dl>
        <p className="viewer-popover-text viewer-scene-path">{row.path}</p>
      </div>
    </Popover>
  );
}
