/**
 * The left column: the steps you can add, and the pipelines this project has saved.
 *
 * A step can be added two ways and both must work — click (it lands in the middle of the current
 * viewport) and drag onto the canvas (it lands where it was dropped). The drag carries the kind on
 * a private MIME type so a stray drop of a file or a link is not mistaken for one.
 */
import { useMemo, useState } from "react";
import { Search, Upload } from "lucide-react";
import { KIND_ICON, KIND_TITLE, NODE_KINDS, type NodeKind } from "./graph";
import type { PipelineListEntry } from "./api";

/** The drag's payload type. Private to this page, so nothing else can look like a node drag. */
export const NODE_DRAG_TYPE = "application/x-tit-node-kind";

function ago(seconds: number | undefined): string {
  if (!seconds) return "";
  const delta = Date.now() / 1000 - seconds;
  if (delta < 90) return "just now";
  if (delta < 3600) return `${Math.round(delta / 60)} min ago`;
  if (delta < 86_400) return `${Math.round(delta / 3600)} h ago`;
  return `${Math.round(delta / 86_400)} d ago`;
}

export function Palette({
  saved,
  onAdd,
  onOpen,
  onImport,
}: {
  saved: PipelineListEntry[];
  onAdd: (kind: NodeKind) => void;
  onOpen: (name: string) => void;
  onImport: () => void;
}) {
  const [query, setQuery] = useState("");

  const kinds = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return NODE_KINDS;
    return NODE_KINDS.filter((k) => k.includes(needle) || KIND_TITLE[k].toLowerCase().includes(needle));
  }, [query]);

  const pipelines = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? saved.filter((e) => e.name.toLowerCase().includes(needle)) : saved;
  }, [saved, query]);

  return (
    <aside className="pipeline-palette" aria-label="Steps and saved pipelines">
      <label className="pipeline-palette-search">
        <Search size={12} aria-hidden />
        <input
          type="search"
          value={query}
          placeholder="Filter steps"
          aria-label="Filter steps and saved pipelines"
          data-testid="pipeline-palette-filter"
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <div className="pipeline-palette-scroll">
        <h2 className="pipeline-palette-head">
          <span>Add a step</span>
          <span>{kinds.length}</span>
        </h2>
        {kinds.length === 0 && <p className="pipeline-muted">No step matches “{query}”.</p>}
        {kinds.map((kind) => {
          const Icon = KIND_ICON[kind];
          return (
            <button
              key={kind}
              type="button"
              className="pipeline-palette-item"
              draggable
              title={`${KIND_TITLE[kind]} — click to add, or drag onto the canvas`}
              data-testid={`pipeline-add-${kind}`}
              onDragStart={(e) => {
                e.dataTransfer.setData(NODE_DRAG_TYPE, kind);
                // Some drop targets (and Playwright's own drag) only see `text/plain`.
                e.dataTransfer.setData("text/plain", kind);
                e.dataTransfer.effectAllowed = "copy";
              }}
              onClick={() => onAdd(kind)}
            >
              <Icon size={14} aria-hidden />
              <span>{KIND_TITLE[kind]}</span>
            </button>
          );
        })}

        <h2 className="pipeline-palette-head">
          <span>Saved</span>
          <span>{pipelines.length}</span>
        </h2>
        {pipelines.length === 0 && <p className="pipeline-muted">Nothing saved yet.</p>}
        {pipelines.map((entry) => (
          <button
            key={entry.name}
            type="button"
            className="pipeline-palette-item pipeline-saved-item"
            data-testid={`pipeline-saved-${entry.name}`}
            title={`Open “${entry.name}”`}
            onClick={() => onOpen(entry.name)}
          >
            <span className="pipeline-saved-name">{entry.name}</span>
            <span className="pipeline-saved-meta">
              {entry.nodes === undefined ? "" : `${entry.nodes} ${entry.nodes === 1 ? "step" : "steps"}`}
              {entry.nodes !== undefined && entry.modified_at ? " · " : ""}
              {ago(entry.modified_at)}
            </span>
          </button>
        ))}

        <button type="button" className="pipeline-palette-item" onClick={onImport} data-testid="pipeline-import">
          <Upload size={14} aria-hidden />
          <span>Import JSON…</span>
        </button>
      </div>
    </aside>
  );
}
