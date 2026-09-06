/**
 * The pieces the Results preview is built from (program U14). Presentation only — every number and
 * every string comes from the parsers beside this file, which are the unit-tested part.
 */
import { useMemo, type ReactNode } from "react";
import { Copy, FolderOpen } from "lucide-react";
import { IconButton } from "../../../ui/Button";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { DefinitionList } from "../../../ui/Feedback";
import { Chip } from "../../../ui/Status";
import { notify } from "../../../ui/Toast";
import { artifactUrl, type Artifact } from "../api";
import type { SummaryRow } from "./simulation";
import type { ExTable } from "./ex";
import type { FlexElectrode } from "./flex";

/** A flush section of the preview: an 11px eyebrow over its content, no card, no border box. */
export function PreviewSection({
  title,
  actions,
  children,
  testid,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  testid?: string;
}) {
  return (
    <section className="results-preview-section" data-testid={testid}>
      <div className="results-preview-section-head">
        <span className="results-eyebrow">{title}</span>
        {actions}
      </div>
      {children}
    </section>
  );
}

/** The label/value rows. `DefinitionList` is the read-only pair primitive (DESIGN.md §5). */
export function SummaryRows({ rows, testid }: { rows: SummaryRow[]; testid?: string }) {
  if (rows.length === 0) return null;
  return (
    <div data-testid={testid}>
      <DefinitionList
        entries={rows.map((r) => [r.label, r.mono ? <span className="mono">{r.value}</span> : r.value] as [string, ReactNode])}
      />
    </div>
  );
}

/** Electrode pairs as chips — "F7 → P7", one per stimulation channel. */
export function PairChips({ pairs, testid }: { pairs: string[]; testid?: string }) {
  if (pairs.length === 0) return null;
  return (
    <div className="results-pair-chips" data-testid={testid}>
      {pairs.map((p) => (
        <Chip key={p} kind="field">
          {p}
        </Chip>
      ))}
    </div>
  );
}

/** A bucket of electrode names (ex-search's four poles), as one wrapped mono line per bucket. */
export function BucketList({ buckets }: { buckets: { label: string; electrodes: string[] }[] }) {
  if (buckets.length === 0) return null;
  return (
    <DefinitionList
      entries={buckets.map(
        (b) => [b.label, <span className="mono">{b.electrodes.join(" ")}</span>] as [string, ReactNode],
      )}
    />
  );
}

/**
 * The run's PNGs as thumbnails through the files route. `loading="lazy"` because a flex run can
 * carry a 2.7 MB skin-region render and the pane must not block on it to show its numbers.
 */
export function FigureGrid({ figures, onOpen }: { figures: Artifact[]; onOpen: (path: string) => void }) {
  if (figures.length === 0) return null;
  return (
    <div className="results-figures" data-testid="results-figures">
      {figures.map((f) => (
        <button
          key={f.path}
          type="button"
          className="results-figure"
          title={f.label ?? f.path}
          onClick={() => onOpen(f.path)}
        >
          <img src={artifactUrl(f.path)} alt="" loading="lazy" />
          <span className="results-figure-label">{f.label ?? f.path.split("/").pop()}</span>
        </button>
      ))}
    </div>
  );
}

const FIELD_KINDS: Record<string, string> = { nifti: "NIfTI", mesh: "mesh", csv: "CSV", json: "JSON", pdf: "PDF" };

/** The field files of a simulation: a kind badge, the catalog's own label, then the file name. The
 * row opens the file; the trailing icon reveals it in the host's file manager, so the two actions
 * `ArtifactList` offers survive at a third of its row height. */
export function FieldFileList({
  files,
  onOpen,
  onReveal,
}: {
  files: Artifact[];
  onOpen: (path: string) => void;
  onReveal?: (path: string) => void;
}) {
  if (files.length === 0) return <p className="field-help">This simulation has no field files yet.</p>;
  return (
    <ul className="results-file-list" data-testid="results-field-files">
      {files.map((f) => (
        <li key={f.path}>
          <button type="button" className="results-file" onClick={() => onOpen(f.path)} title={f.path}>
            <Chip kind="neutral">{FIELD_KINDS[f.kind] ?? f.kind}</Chip>
            <span className="results-file-label">{f.label ?? f.path.split("/").pop()}</span>
            <span className="results-file-name mono">{f.path.split("/").pop()}</span>
          </button>
          {onReveal && (
            <IconButton
              size="sm"
              aria-label={`Reveal ${f.label ?? f.path}`}
              icon={<FolderOpen size={13} />}
              onClick={() => onReveal(f.path)}
            />
          )}
        </li>
      ))}
    </ul>
  );
}

/** The ranked `final_output.csv` rows, or a flex run's electrode positions — one table primitive.
 * `labels` renames a header without renaming the column (see `EX_COLUMN_LABELS`). */
export function RankedTable({
  table,
  emptyMessage,
  labels,
}: {
  table: ExTable;
  emptyMessage: string;
  labels?: Record<string, string>;
}) {
  const columns = useMemo<DataTableColumn<(string | number | null)[]>[]>(
    () =>
      table.columns.map((name, i) => ({
        header: labels?.[name] ?? name,
        cell: ({ row }) => {
          const v = row.original[i];
          return typeof v === "number" ? Number(v.toFixed(4)).toString() : String(v ?? "");
        },
        numeric: table.rows.length > 0 && table.rows.every((r) => typeof r[i] === "number"),
      })),
    [table, labels],
  );
  return <DataTable data={table.rows} columns={columns} emptyMessage={emptyMessage} />;
}

export function ElectrodePositionTable({ electrodes }: { electrodes: FlexElectrode[] }) {
  const table = useMemo<ExTable>(
    () => ({
      columns: ["Channel", "Array", "x", "y", "z"],
      rows: electrodes.map((e) => [e.channel, e.array, e.x, e.y, e.z]),
    }),
    [electrodes],
  );
  if (electrodes.length === 0) return null;
  return <RankedTable table={table} emptyMessage="No optimized positions in this run." />;
}

/**
 * The path, demoted to one mono line at the foot of the pane with a copy control — U14's whole
 * point: *"the path becomes one mono line at the bottom … never the headline"*.
 *
 * Split into a shrinking head and a pinned tail rather than truncated at a fixed character budget.
 * The rule this serves (checklist item 4) is that the informative end of a container path is its
 * tail — `…/Simulations/Thalamus`, not `/mnt/example/derivatives/…` — and the tail here survives
 * every pane width, including the 320px minimum, whereas a `truncatePathLeft(path, N)` with a
 * budget wide enough for the expanded pane would be right-ellipsized (tail lost) in the narrow one.
 * `direction: rtl` is not used: it reorders the leading `/` to the end of the visible run, which is
 * the bug `outputsTree.ts::truncatePathLeft` documents.
 */
export function PathLine({ path }: { path: string }) {
  if (!path) return null;
  // The last two segments are the ones that name the output; everything before them may shrink.
  const lastSlash = path.lastIndexOf("/");
  const cut = lastSlash > 0 ? path.lastIndexOf("/", lastSlash - 1) : -1;
  const head = cut > 0 ? path.slice(0, cut) : "";
  const tail = cut > 0 ? path.slice(cut) : path;
  return (
    <div className="results-preview-path" data-testid="results-preview-path">
      <span className="results-eyebrow">Path</span>
      <span className="mono text-caption results-preview-path-value" title={path}>
        <span className="results-preview-path-head">{head}</span>
        <span className="results-preview-path-tail">{tail}</span>
      </span>
      <IconButton
        size="sm"
        aria-label="Copy path"
        data-testid="results-copy-path"
        icon={<Copy size={13} />}
        onClick={() => {
          void navigator.clipboard
            ?.writeText(path)
            .then(() => notify.success("Path copied."))
            .catch(() => notify.error("Could not copy the path."));
        }}
      />
    </div>
  );
}
