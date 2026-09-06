/**
 * Results section: analyses of the selected subject + simulation, with an "Open in viewer" quick
 * action into the embedded Tetravox viewer (D3 -- Freeview/Gmsh are gone), and a link to the
 * Results page for the full summary table / PDF / artifact list. Originally reproduced that whole
 * detail view here too (mirroring the "Gmsh Visualization" box in `tit/gui/analyzer_tab.py` plus
 * every analysis's own outputs) — trimmed per the task brief to avoid duplicating
 * `pages/results`'s `AnalysesPanel`, which already owns that view. See PARITY.md.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowRight, FlaskConical } from "lucide-react";
import { useJobsStream } from "../../app/jobs/useJobsStream";
import { Cluster } from "../../ui/Layout";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Button } from "../../ui/Button";
import { viewerSearch } from "../results";
import { getAnalyses, type Analysis } from "./api";

export function ResultsPanel({
  subjectId,
  simulation,
}: {
  subjectId: string | null;
  simulation: string | undefined;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);

  const analyses = useQuery({
    queryKey: ["analyses", subjectId, simulation],
    queryFn: () => getAnalyses(subjectId as string, simulation as string),
    enabled: subjectId !== null && !!simulation,
  });

  // Invalidate on job transitions from the jobs store, never per log line (DESIGN.md/lane rules):
  // any `analyzer` job for this subject reaching `succeeded` means this simulation's analyses
  // list may have grown. `JobStatus` carries no `config`, so this can't be scoped to the exact
  // simulation — a coarser, subject-scoped refetch trigger is the best available signal.
  const jobsState = useJobsStream();
  const succeededAnalyzerJobs = Object.values(jobsState.jobs).filter(
    (j) =>
      j.kind === "analyzer" &&
      j.state === "succeeded" &&
      subjectId !== null &&
      j.subject_ids.includes(subjectId),
  ).length;
  useEffect(() => {
    if (succeededAnalyzerJobs > 0)
      void queryClient.invalidateQueries({
        queryKey: ["analyses", subjectId, simulation],
      });
  }, [succeededAnalyzerJobs, subjectId, simulation, queryClient]);

  const selectedAnalysis =
    analyses.data?.find((a) => a.name === selected) ?? null;

  const navigate = useNavigate();

  function goToResults() {
    const params = new URLSearchParams({ tab: "analyses" });
    if (subjectId) params.set("subject", subjectId);
    if (simulation) params.set("simulation", simulation);
    navigate(`/results?${params.toString()}`);
  }

  function openInViewer(a: Analysis) {
    if (!subjectId || !simulation) return;
    navigate({
      pathname: "/viewer",
      search: viewerSearch({
        subject: subjectId,
        simulation,
        field: a.field,
        kind: "analysis",
      }),
    });
  }

  // The viewer action lives in the selected analysis's own Card header (below), not as a table
  // column — matching `pages/results/index.tsx`'s Analyses tab. A table row has no room for a
  // full "Open in …" button at 36px density without either clipping or shrinking it past
  // legibility (DESIGN.md's Table Actions row is for icon-scale glyphs, not full sentences).
  const columns = useMemo<DataTableColumn<Analysis>[]>(
    () => [
      {
        header: "Analysis",
        accessorKey: "name",
        cell: ({ getValue }) => (
          <span className="mono text-dense">{getValue() as string}</span>
        ),
      },
      { header: "Space", accessorKey: "space" },
      { header: "Field", accessorKey: "field" },
      { header: "ROI", accessorKey: "roi" },
    ],
    [],
  );

  // Flush, never a Card: this renders INSIDE a `FormSection` on the run shape, and DESIGN.md
  // §4.2 rule 4 forbids a box inside a form group. It was a Card while the section was always
  // collapsed; FXU1's fill rule opens it, which is what surfaced the violation.
  // The not-yet-chosen state is the SAME table, empty, with its reason in the body — DESIGN.md
  // §4.4: "empty: `emptyMessage`, one line, inside the table body". It was a bare paragraph, which
  // told the user less (the columns they will get are part of the answer) and left the bottom of
  // the work pane as ground: at 1280x800 the Analyzer's last measured band was 100 % empty.
  if (subjectId === null || !simulation) {
    return (
      <div data-testid="analyses-table">
        <DataTable
          data={[]}
          columns={columns}
          emptyMessage="Pick a subject and a simulation above to list its analyses."
        />
      </div>
    );
  }

  return (
    <>
      <Cluster justify="between" align="center">
        <p className="field-help" style={{ margin: 0 }}>
          Analyses of this simulation. Open the Results page for each one&apos;s summary table, PDF report and artifacts.
        </p>
        <span style={{ display: "flex", gap: "var(--space-2)" }}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ["analyses", subjectId, simulation],
              })
            }
          >
            Refresh
          </Button>
          <Button variant="secondary" size="sm" icon={<ArrowRight size={14} />} onClick={goToResults}>
            View in Results
          </Button>
        </span>
      </Cluster>
      <div>
        {analyses.isPending && <Skeleton height={120} />}
        {analyses.error && (
          <Callout kind="danger">
            Could not load analyses for this simulation.
          </Callout>
        )}
        {analyses.data && analyses.data.length === 0 && (
          <EmptyState
            icon={<FlaskConical size={24} />}
            message="No analyses for this simulation yet — run one above."
          />
        )}
        {analyses.data && analyses.data.length > 0 && (
          <div data-testid="analyses-table">
            <DataTable
              data={analyses.data}
              columns={columns}
              getRowId={(a) => a.name}
              onRowClick={(a) => setSelected(a.name)}
              emptyMessage="No analyses yet."
            />
          </div>
        )}

        {selectedAnalysis && (
          <div
            style={{
              marginTop: "var(--space-3)",
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
              padding: "var(--space-2) var(--space-3)",
              background: "var(--surface-2)",
              borderRadius: "var(--radius-controls)",
            }}
          >
            <span className="mono text-dense">{selectedAnalysis.name}</span>
            <Chip kind="neutral">{selectedAnalysis.space}</Chip>
            <Chip kind="field">{selectedAnalysis.field}</Chip>
            <div style={{ flex: 1 }} />
            {(selectedAnalysis.msh || selectedAnalysis.nifti) && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => openInViewer(selectedAnalysis)}
              >
                Open in viewer
              </Button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
