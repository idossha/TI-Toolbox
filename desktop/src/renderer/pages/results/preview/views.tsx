/**
 * The pieces the Results preview is built from (program U14). Presentation only — every number and
 * every string comes from the parsers beside this file, which are the unit-tested part.
 */
import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { IconButton } from "../../../ui/Button";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { DefinitionList } from "../../../ui/Feedback";
import { Chip } from "../../../ui/Status";
import { notify } from "../../../ui/Toast";
import { artifactUrl, getTextFile, type Artifact } from "../api";
import { isPdf, PdfCanvas } from "./PdfCanvas";
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
 * The run's figures as thumbnails through the files route. `loading="lazy"` because a flex run can
 * carry a 2.7 MB skin-region render and the pane must not block on it to show its numbers.
 *
 * PDF figures — the analyzer writes its histogram as one, and a stats run writes its null
 * distribution and its size/mass scatter as two more — are rasterised into the same tile as the
 * PNGs by `PdfCanvas`, not handed to Chromium's PDF viewer. They are plots; they get a picture.
 */
export function FigureGrid({
  figures,
  onOpen,
  testid = "results-figures",
}: {
  figures: Artifact[];
  onOpen: (figure: Artifact) => void;
  /** The simulation pane draws one grid twice — beside the channel chips and in Figures — so the
   * two need different ids for a test to address either without a strict-mode collision. */
  testid?: string;
}) {
  if (figures.length === 0) return null;
  return (
    <div className="results-figures" data-testid={testid}>
      {figures.map((f) => (
        <button
          key={f.path}
          type="button"
          className="results-figure"
          data-testid={`results-figure-${f.path.split("/").pop()}`}
          title={f.label ?? f.path}
          onClick={() => onOpen(f)}
        >
          {isPdf(f.path) ? (
            <PdfCanvas className="results-figure-doc" url={artifactUrl(f.path)} label={f.label ?? f.path} />
          ) : (
            <img src={artifactUrl(f.path)} alt="" loading="lazy" />
          )}
          <span className="results-figure-label">{f.label ?? f.path.split("/").pop()}</span>
        </button>
      ))}
    </div>
  );
}

const FIELD_KINDS: Record<string, string> = {
  nifti: "NIfTI",
  mesh: "mesh",
  csv: "CSV",
  json: "JSON",
  pdf: "PDF",
  html: "HTML",
  image: "PNG",
  png: "PNG",
  log: "log",
  text: "TXT",
  npz: "NPZ",
};

/**
 * File kinds the pane can show without leaving the app. The maintainer removed the `View` and
 * `Open` buttons — *"Only have the folder icon"* — so this capability now hangs off the file's
 * NAME, the way the figure thumbnails already work: click the name of a previewable file and it
 * opens inline; a NIfTI or a mesh has no name button, because there is nothing to open it with in
 * this pane and a dead-looking button is worse than plain text.
 */
const TEXT_PREVIEW_KINDS = new Set(["csv", "json", "text", "log", "manifest"]);
const DOC_PREVIEW_KINDS = new Set(["pdf", "html"]);
const IMAGE_PREVIEW_KINDS = new Set(["png", "image", "jpg", "jpeg"]);

export function isPreviewable(kind: string): boolean {
  return TEXT_PREVIEW_KINDS.has(kind) || DOC_PREVIEW_KINDS.has(kind) || IMAGE_PREVIEW_KINDS.has(kind);
}

/** The inline body under an expanded file row. Text is fetched; documents and images are framed. */
function FilePreview({ file }: { file: Artifact }) {
  const isText = TEXT_PREVIEW_KINDS.has(file.kind);
  const text = useQuery({
    queryKey: ["results-file-text", file.path],
    queryFn: () => getTextFile(file.path),
    enabled: isText,
    retry: false,
    staleTime: Infinity,
  });
  if (IMAGE_PREVIEW_KINDS.has(file.kind)) {
    return (
      <div className="results-file-preview" data-testid="results-file-preview">
        <img src={artifactUrl(file.path)} alt={file.label ?? file.path} loading="lazy" />
      </div>
    );
  }
  if (isPdf(file.path)) {
    return (
      <div className="results-file-preview" data-testid="results-file-preview">
        <PdfCanvas className="results-file-pdf" url={artifactUrl(file.path)} label={file.label ?? file.path} />
      </div>
    );
  }
  if (DOC_PREVIEW_KINDS.has(file.kind)) {
    return (
      <div className="results-file-preview" data-testid="results-file-preview">
        <iframe title={file.label ?? file.path} src={artifactUrl(file.path)} sandbox="allow-scripts" />
      </div>
    );
  }
  return (
    <div className="results-file-preview" data-testid="results-file-preview">
      {text.isPending && <p className="field-help">Reading…</p>}
      {text.error && <p className="field-help">Could not read this file.</p>}
      {text.data !== undefined && <pre className="results-file-text mono">{text.data}</pre>}
    </div>
  );
}

/**
 * The artifact rows of every result kind: a kind badge, the file's label, and its name. No trailing
 * control at all.
 *
 * The maintainer, on the version that had one folder icon per row: *"instead of having multiple
 * icons of the folder to open the same folder, let us just have a centralized folder icon in this
 * rail right on top of it"*. Every file of an output lives in that output's own directory, so a
 * column of eleven identical buttons all opened the same folder. The pane header's folder icon is
 * the one that does it; a row that happens to live somewhere else says so in its name column
 * (see `rootDir`) rather than earning an icon back.
 *
 * The preview capability hangs off the file's NAME — click a CSV, JSON, PNG, PDF or HTML name and
 * it opens inline. A NIfTI or a mesh has no name button, because there is nothing in this pane to
 * open it with and a dead-looking button is worse than plain text.
 */
export function FileList({
  files,
  rootDir,
  emptyMessage = "This output has no files yet.",
}: {
  files: Artifact[];
  /** The pane's own directory — the one its header's folder icon opens. A file outside it shows
   * its path relative to it, so "the folder icon opens the folder these files are in" stays true. */
  rootDir?: string;
  emptyMessage?: string;
}) {
  const [openPath, setOpenPath] = useState<string | undefined>(undefined);
  if (files.length === 0) return <p className="field-help">{emptyMessage}</p>;
  const base = rootDir ? rootDir.replace(/\/+$/, "") + "/" : undefined;
  return (
    <ul className="results-file-list" data-testid="results-files">
      {files.map((f) => {
        const name =
          base && f.path.startsWith(base) ? f.path.slice(base.length) : (f.path.split("/").pop() ?? f.path);
        const previewable = isPreviewable(f.kind);
        const open = openPath === f.path;
        const body = (
          <>
            <Chip kind="neutral">{FIELD_KINDS[f.kind] ?? f.kind}</Chip>
            <span className="results-file-label">{f.label ?? name}</span>
            <span className="results-file-name mono">{name}</span>
          </>
        );
        return (
          <li key={f.path} className="results-file-row">
            <div className="results-file-line">
              {previewable ? (
                <button
                  type="button"
                  className="results-file"
                  aria-expanded={open}
                  data-testid={`results-file-${name}`}
                  onClick={() => setOpenPath(open ? undefined : f.path)}
                  title={f.path}
                >
                  {body}
                </button>
              ) : (
                <span className="results-file results-file-static" title={f.path}>
                  {body}
                </span>
              )}
            </div>
            {open && <FilePreview file={f} />}
          </li>
        );
      })}
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
