/**
 * One shape for every kind of result the preview pane shows.
 *
 * The maintainer's note, on the Ex-search pane: *"the main numerical things on top, then render
 * the images, then a synthesis of the artifacts at the bottom. Something like the Ex search works
 * fantastically."* That pane was the only one built that way; the analyzer's was a 22-row
 * METRIC/VALUE dump of `results.csv` and a group-statistics run showed the single row `Kind
 * analysis`. This module makes the Ex-search order the *only* order:
 *
 *   header block · key numbers · tables · figures · files · path
 *
 * `sections` is a typed union rather than free `ReactNode` children so that the ordering rule is
 * enforced here, once, instead of restated in five call sites, and so `resultSectionOrder` can be
 * unit-tested without a browser. A caller passes sections in any order; the layout renders them in
 * the canonical one. An unknown result kind passes a header and a files section and gets the same
 * pane as every other kind, one section shorter.
 */
import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { Callout, Skeleton } from "../../../ui/Feedback";
import { IconButton } from "../../../ui/Button";
import type { KeyNumber } from "./metrics";
import type { SummaryRow } from "./simulation";
import type { Artifact } from "../api";
import { isPdf, PdfCanvas } from "./PdfCanvas";

/** The section kinds, in the order the pane renders them. */
export const SECTION_ORDER = [
  "header",
  "notice",
  "metrics",
  "table",
  "custom",
  "figures",
  "files",
  "trailing",
] as const;

export type SectionKind = (typeof SECTION_ORDER)[number];

export type ResultSection =
  /** The compact key/value block that says what this output is. */
  | { kind: "header"; rows: SummaryRow[]; chips?: string[] }
  /** A run that produced nothing, or produced something the reader must be told about. */
  | { kind: "notice"; tone: "info" | "warn" | "danger"; title?: string; message: string }
  /** One or more labelled number grids. */
  | { kind: "metrics"; title?: string; groups: { title: string; metrics: KeyNumber[] }[] }
  /** A ranked or tabular block (ex-search's top montages, a cluster table). */
  | { kind: "table"; title: string; testid?: string; content: ReactNode }
  /** Thumbnails with a lightbox. */
  | { kind: "figures"; title?: string; figures: Artifact[] }
  /** The artifact list. Rendered last, above the path line. */
  | { kind: "files"; title?: string; content: ReactNode }
  /** Anything numerical or tabular a single kind needs and no other does (ex-search's electrode
   * buckets, a simulation's channel chips, an analysis's unrecognised metrics). Ordered with the
   * tables, above the figures. */
  | { kind: "custom"; title?: string; testid?: string; content: ReactNode }
  /**
   * Below the files: the two things a simulation shows that are neither its numbers nor its
   * artifacts — what it *holds* (its analyses and reports, as jumps) and the rendered report
   * itself, which is a document and takes whatever height the pane has left.
   */
  | { kind: "trailing"; title?: string; testid?: string; content: ReactNode };

/**
 * Sections in canonical order, empty ones dropped. Pure, so the ordering contract is a unit test
 * and not a screenshot. Stable within a kind: two `metrics` sections keep the caller's order.
 */
export function orderSections(sections: (ResultSection | false | undefined)[]): ResultSection[] {
  const present = sections.filter((s): s is ResultSection => !!s).filter(nonEmpty);
  return SECTION_ORDER.flatMap((kind) => present.filter((s) => s.kind === kind));
}

function nonEmpty(section: ResultSection): boolean {
  if (section.kind === "header") return section.rows.length > 0 || (section.chips?.length ?? 0) > 0;
  if (section.kind === "metrics") return section.groups.some((g) => g.metrics.length > 0);
  if (section.kind === "figures") return section.figures.length > 0;
  return true;
}

// ----------------------------------------------------------------------- pieces

/** The 11px eyebrow over a flush section — no card, no border box (DESIGN.md §5). */
export function SectionShell({
  title,
  testid,
  children,
}: {
  title?: string;
  testid?: string;
  children: ReactNode;
}) {
  return (
    <section className="results-preview-section" data-testid={testid}>
      {title && (
        <div className="results-preview-section-head">
          <span className="results-eyebrow">{title}</span>
        </div>
      )}
      {children}
    </section>
  );
}

/**
 * One group of key numbers as a two-column table: the label left, the value right.
 *
 * The maintainer, on the first version: *"the numerical values should not be scattered like that
 * of course. Should be clean and organized."* It was a `repeat(auto-fit, minmax(104px, 1fr))` grid
 * of tiles, so ROI's four numbers and Percentiles' three wrapped to different column counts and no
 * two values in the pane shared a right edge.
 *
 * A table fixes that by construction: one column of labels, one of values, right-aligned and set
 * in `tabular-nums`, so digits of the same magnitude line up down the pane and the eye can compare
 * them without reading. The unit is a muted suffix rather than part of the number, for the same
 * reason. Group headings are rows *inside* the table, not floating captions beside it, so the
 * indentation is the table's and cannot drift. The two headline values (ROI mean and max) carry
 * the only bold in the block.
 *
 * The value string arrives already formatted with its unit (see `metrics.ts`) — this component
 * never sees a float and so cannot print sixteen digits of one. It splits the unit back off only
 * to style it, and a value with no space in it (a bare ratio, a count) is left whole.
 */
function splitUnit(value: string): [string, string | undefined] {
  const cut = value.lastIndexOf(" ");
  if (cut <= 0) return [value, undefined];
  return [value.slice(0, cut), value.slice(cut + 1)];
}

export function KeyNumberTable({
  groups,
  testid,
}: {
  groups: { title: string; metrics: KeyNumber[] }[];
  testid?: string;
}) {
  const filled = groups.filter((g) => g.metrics.length > 0);
  if (filled.length === 0) return null;
  return (
    <div className="results-keynumber-columns" data-testid={testid}>
      {filled.map((group) => (
        <table key={group.title} className="results-keynumbers">
          <tbody>
            <tr className="results-keynumber-head">
              <th colSpan={2} scope="colgroup">
                {group.title}
              </th>
            </tr>
            {group.metrics.map((m) => {
              const [number, unit] = splitUnit(m.value);
              return (
                <tr key={m.label} data-lead={m.lead || undefined}>
                  <th scope="row">
                    {m.label}
                    {m.hint && <span className="results-keynumber-hint"> {m.hint}</span>}
                  </th>
                  <td className="mono">
                    {number}
                    {unit && <span className="results-keynumber-unit"> {unit}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ))}
    </div>
  );
}

/**
 * A figure over the pane, dismissed with Escape or a click outside it.
 *
 * A PDF is drawn page by page with `PdfCanvas` and gets a plain prev/next when it has more than
 * one page. Nothing else: no thumbnail rail, no zoom box, no print button — that chrome is what
 * the `<iframe>` this replaced brought with it.
 */
export function Lightbox({
  src,
  title,
  path,
  onClose,
}: {
  /** What to draw — the artifact route, not the file system path. */
  src: string;
  title: string;
  /** The artifact's own path; `src` is a query URL, so the extension is read from here. */
  path: string;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const pdf = isPdf(path);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (!pdf) return;
      if (e.key === "ArrowRight") setPage((p) => Math.min(pages, p + 1));
      if (e.key === "ArrowLeft") setPage((p) => Math.max(1, p - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, pdf, pages]);
  return (
    <div
      className="results-lightbox"
      data-testid="results-lightbox"
      role="dialog"
      aria-label={title}
      onClick={onClose}
    >
      <div className="results-lightbox-bar" onClick={(e) => e.stopPropagation()}>
        <span className="results-lightbox-title">{title}</span>
        {pdf && pages > 1 && (
          <span className="results-lightbox-pager" data-testid="results-lightbox-pager">
            <IconButton
              aria-label="Previous page"
              icon={<ChevronLeft size={14} />}
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            />
            <span className="mono text-caption">
              {page} / {pages}
            </span>
            <IconButton
              aria-label="Next page"
              icon={<ChevronRight size={14} />}
              disabled={page >= pages}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
            />
          </span>
        )}
        <IconButton aria-label="Close preview" icon={<X size={14} />} onClick={onClose} />
      </div>
      {pdf ? (
        <PdfCanvas
          className="results-lightbox-page"
          url={src}
          page={page}
          label={title}
          onPageCount={setPages}
        />
      ) : (
        <img src={src} alt={title} onClick={(e) => e.stopPropagation()} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------- the layout

/**
 * Renders `sections` in canonical order inside the pane's scrolling body. `figures` and `files`
 * need renderers that know about the host bridge, so the page passes them in rather than this
 * module importing Electron-aware code.
 */
export function ResultLayout({
  sections,
  pending,
  renderHeader,
  renderFigures,
}: {
  sections: (ResultSection | false | undefined)[];
  /** A skeleton in place of everything, while the manifests this pane reads are in flight. */
  pending?: boolean;
  renderHeader: (section: Extract<ResultSection, { kind: "header" }>) => ReactNode;
  renderFigures: (section: Extract<ResultSection, { kind: "figures" }>) => ReactNode;
}) {
  const ordered = orderSections(sections);
  if (pending && ordered.length === 0) return <Skeleton height={180} />;
  return (
    <>
      {ordered.map((section, i) => {
        const key = `${section.kind}:${i}`;
        switch (section.kind) {
          case "header":
            return (
              <SectionShell key={key} testid="results-header-block">
                {renderHeader(section)}
              </SectionShell>
            );
          case "notice":
            return (
              <SectionShell key={key}>
                <div data-testid="results-notice">
                  <Callout kind={section.tone === "warn" ? "warning" : section.tone} title={section.title}>
                    {section.message}
                  </Callout>
                </div>
              </SectionShell>
            );
          case "metrics":
            return (
              <SectionShell key={key} title={section.title ?? "Key numbers"} testid="results-key-numbers">
                <KeyNumberTable groups={section.groups} />
              </SectionShell>
            );
          case "table":
            return (
              <SectionShell key={key} title={section.title} testid={section.testid}>
                {section.content}
              </SectionShell>
            );
          case "figures":
            return (
              <SectionShell key={key} title={section.title ?? `Figures · ${section.figures.length}`}>
                {renderFigures(section)}
              </SectionShell>
            );
          case "files":
            return (
              <SectionShell key={key} title={section.title ?? "Files"} testid="results-files-section">
                {section.content}
              </SectionShell>
            );
          case "custom":
          case "trailing":
            return (
              <SectionShell key={key} title={section.title} testid={section.testid}>
                {section.content}
              </SectionShell>
            );
        }
      })}
    </>
  );
}
