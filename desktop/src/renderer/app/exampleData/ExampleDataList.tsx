/**
 * The example-data catalogue as rows, shared by the once-per-project chooser and Help ▸ Example
 * data — one list, two chromes (the maintainer's "no third copy of the list").
 *
 * `mode="choose"` gives each row a checkbox and the caller collects the ticked ids; `mode="manage"`
 * gives each row its own **Download** button with that sample's live progress, and says
 * **Installed** for what is already on disk. Both read the same `GET /api/example-data`.
 *
 * Progress comes from **polling that one endpoint**, not from the jobs stream: the server answers
 * each sample's `downloading`/`received`/`total` alongside `installed`, so a row needs no state of
 * its own. The poll runs only while something is in flight and stops by itself when nothing is.
 */
import { useQuery } from "@tanstack/react-query";
import { Check, Download } from "lucide-react";
import { Button } from "../../ui/Button";
import { Callout, Skeleton } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import {
  EXAMPLE_DATA_POLL_MS,
  EXAMPLE_DATA_QUERY_KEY,
  formatBytes,
  getExampleData,
  layoutTag,
  progressText,
} from "./api";
import "./example-data.css";

export function ExampleDataList({
  mode,
  selected,
  onSelectedChange,
  onDownload,
}: {
  mode: "choose" | "manage";
  /** `choose` only: the ticked sample ids. */
  selected?: readonly string[];
  onSelectedChange?: (ids: string[]) => void;
  onDownload?: (sampleId: string) => void;
}) {
  const query = useQuery({
    queryKey: EXAMPLE_DATA_QUERY_KEY,
    queryFn: getExampleData,
    // Poll only while a download is in flight; `false` stops it the moment none is.
    refetchInterval: (q) =>
      q.state.data?.status.some((s) => s.downloading) ? EXAMPLE_DATA_POLL_MS : false,
  });
  if (query.isPending) return <Skeleton rows={4} />;
  if (query.error || !query.data)
    return <Callout kind="danger">Could not load the example-data catalogue.</Callout>;

  const { samples, status } = query.data;
  const statusOf = (id: string) => status.find((s) => s.id === id);
  const toggle = (id: string) => {
    const now = selected ?? [];
    onSelectedChange?.(now.includes(id) ? now.filter((x) => x !== id) : [...now, id]);
  };

  return (
    <ul className="example-data-list" data-testid="example-data-list">
      {samples.map((sample) => {
        const sampleStatus = statusOf(sample.id);
        const installed = sampleStatus?.installed === true;
        const busy = progressText(sampleStatus);
        const failed = sampleStatus?.error;
        const checked = (selected ?? []).includes(sample.id);
        const row = (
          <>
            <span className="example-data-head">
              <span className="example-data-title">{sample.title}</span>
              <Chip kind={sample.layout === "headmodel" ? "success" : "neutral"}>
                {layoutTag(sample.layout)}
              </Chip>
              <span className="example-data-size">{formatBytes(sample.bytes)}</span>
            </span>
            <span className="example-data-description">{sample.description}</span>
          </>
        );
        return (
          <li key={sample.id} className="example-data-row" data-testid={`example-data-row-${sample.id}`}>
            {mode === "choose" ? (
              <label className="example-data-choose">
                <input
                  type="checkbox"
                  checked={checked}
                  data-testid={`example-data-check-${sample.id}`}
                  onChange={() => toggle(sample.id)}
                />
                <span className="example-data-body">{row}</span>
              </label>
            ) : (
              <div className="example-data-choose">
                <span className="example-data-body">
                  {row}
                  <span className="example-data-meta">
                    <a href={sample.source_url} target="_blank" rel="noreferrer">
                      {sample.source}
                    </a>
                    {" · "}
                    {sample.licence}
                  </span>
                  {failed && (
                    <span
                      className="example-data-error"
                      data-testid={`example-data-error-${sample.id}`}
                    >
                      {failed}
                    </span>
                  )}
                </span>
                {installed ? (
                  <span className="example-data-installed" data-testid={`example-data-installed-${sample.id}`}>
                    <Check size={14} aria-hidden /> Installed
                  </span>
                ) : (
                  <Button
                    size="sm"
                    disabled={busy !== undefined}
                    data-testid={`example-data-download-${sample.id}`}
                    onClick={() => onDownload?.(sample.id)}
                  >
                    <Download size={14} aria-hidden /> {busy ?? "Download"}
                  </Button>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
