/**
 * The example-data catalogue as **datasets with parts**, shared by the once-per-project chooser and
 * Help ▸ Example data — one list, two chromes (the maintainer's "no third copy of the list").
 *
 * Each dataset is a heading (title, one-line description, and in `manage` its provenance and
 * licence) over its parts, and every part is its own `PartRow`: independently downloadable,
 * independently detected. That is the whole reason for the shape — the old catalogue's head-model
 * *sample* contained the NIfTIs, so deleting `sub-ernie/anat` flipped a 590 MB head model still
 * sitting on disk to "not installed".
 *
 * Progress comes from **polling `GET /api/example-data`**, not from the jobs stream: the server
 * answers each part's `downloading`/`queued`/`received`/`total` alongside `installed`, so a row
 * needs no state of its own. The poll runs only while something is in flight and stops by itself.
 */
import { useQuery } from "@tanstack/react-query";
import { Callout, Skeleton } from "../../ui/Feedback";
import { EXAMPLE_DATA_POLL_MS, EXAMPLE_DATA_QUERY_KEY, getExampleData, isBusy } from "./api";
import { PartRow } from "./PartRow";
import "./example-data.css";

export function ExampleDataList({
  mode,
  selected,
  onSelectedChange,
  onDownload,
}: {
  mode: "choose" | "manage";
  /** `choose` only: the ticked part ids (`ernie/headmodel`). */
  selected?: readonly string[];
  onSelectedChange?: (ids: string[]) => void;
  onDownload?: (partId: string, force?: boolean) => void;
}) {
  const query = useQuery({
    queryKey: EXAMPLE_DATA_QUERY_KEY,
    queryFn: getExampleData,
    // Poll only while a download is in flight or waiting; `false` stops it the moment none is.
    refetchInterval: (q) =>
      q.state.data?.status.some(isBusy) ? EXAMPLE_DATA_POLL_MS : false,
  });
  if (query.isPending) return <Skeleton rows={4} />;
  if (query.error || !query.data)
    return <Callout kind="danger">Could not load the example-data catalogue.</Callout>;

  const { datasets, status } = query.data;
  const statusOf = (id: string) => status.find((s) => s.id === id);
  const toggle = (id: string) => {
    const now = selected ?? [];
    onSelectedChange?.(now.includes(id) ? now.filter((x) => x !== id) : [...now, id]);
  };

  return (
    <div className="example-data-list" data-testid="example-data-list">
      {datasets.map((dataset) => (
        <section
          key={dataset.id}
          className="example-dataset"
          data-testid={`example-data-dataset-${dataset.id}`}
        >
          <header className="example-dataset-head">
            <h4 className="example-dataset-title">{dataset.title}</h4>
            <p className="example-dataset-description">{dataset.description}</p>
            {mode === "manage" && (
              <p className="example-dataset-meta">
                <a href={dataset.source_url} target="_blank" rel="noreferrer">
                  {dataset.source}
                </a>
                {" · "}
                {dataset.licence}
              </p>
            )}
          </header>
          <ul className="example-part-list">
            {dataset.parts.map((part) => (
              <PartRow
                key={part.id}
                part={part}
                status={statusOf(part.id)}
                mode={mode}
                checked={(selected ?? []).includes(part.id)}
                onToggle={toggle}
                onDownload={onDownload}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
