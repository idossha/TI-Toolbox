/**
 * The example-data catalogue as rows, shared by the once-per-project chooser and Help ▸ Example
 * data — one list, two chromes (the maintainer's "no third copy of the list").
 *
 * `mode="choose"` gives each row a checkbox and the caller collects the ticked ids; `mode="manage"`
 * gives each row its own **Download** button with that job's live progress, and says **Installed**
 * for what is already on disk. Both read the same `GET /api/project/example-data`.
 */
import { useQuery } from "@tanstack/react-query";
import { Check, Download } from "lucide-react";
import { Button } from "../../ui/Button";
import { Callout, Skeleton } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import {
  EXAMPLE_DATA_QUERY_KEY,
  formatBytes,
  getExampleData,
  layoutTag,
  type ExampleSample,
} from "./api";
import "./example-data.css";

export interface ExampleDataRowState {
  /** A job for this sample is running; the text is its latest line. */
  busy?: string;
}

export function ExampleDataList({
  mode,
  selected,
  onSelectedChange,
  rowState,
  onDownload,
}: {
  mode: "choose" | "manage";
  /** `choose` only: the ticked sample ids. */
  selected?: readonly string[];
  onSelectedChange?: (ids: string[]) => void;
  rowState?: (sample: ExampleSample) => ExampleDataRowState;
  onDownload?: (sampleId: string) => void;
}) {
  const query = useQuery({ queryKey: EXAMPLE_DATA_QUERY_KEY, queryFn: getExampleData });
  if (query.isPending) return <Skeleton rows={4} />;
  if (query.error || !query.data)
    return <Callout kind="danger">Could not load the example-data catalogue.</Callout>;

  const { samples, status } = query.data;
  const installedOf = (id: string) => status.find((s) => s.id === id)?.installed === true;
  const toggle = (id: string) => {
    const now = selected ?? [];
    onSelectedChange?.(now.includes(id) ? now.filter((x) => x !== id) : [...now, id]);
  };

  return (
    <ul className="example-data-list" data-testid="example-data-list">
      {samples.map((sample) => {
        const installed = installedOf(sample.id);
        const busy = rowState?.(sample).busy;
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
