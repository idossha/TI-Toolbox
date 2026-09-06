/**
 * Overview — the project's eagle-eye page and the app's front door (R1,
 * `desktop/IMPLEMENTATION_PLAN.md`; DESIGN.md §2 shape B, wireframes §1).
 *
 * It began as the Subjects page and keeps everything that page answered well — the coverage strip,
 * the presence matrix, the filters, the readiness rows, the workflow links — but it asks the
 * question at project scale: *what is on disk across this project, and what can run next?*
 *
 * Two things changed with the rename:
 *
 * - **One request.** Every fact here comes from `GET /api/catalog/overview`. The page used to fan
 *   out one detail read per subject plus five output lists per subject plus one analyses list per
 *   simulation, capped at 25 subjects — so a bigger project rendered blank count columns. The
 *   server aggregates instead, and the request count no longer grows with the project.
 * - **Five presence states, not two.** `present · partial · pending · failed · absent` (U6's
 *   chips, extended): staged-but-unconverted raw data, a job running right now, and a job that
 *   failed are three different answers that "missing" used to swallow.
 *
 * What it deliberately does not do is browse outputs: the detail pane **links into Results** (Q3)
 * rather than listing runs, because two lists of the same outputs are two answers to one question.
 * The detail pane is not rendered with no row selected, so the table takes its 360 px back (U1).
 */
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Eye, LayoutGrid, Search } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { useStatusCells } from "../../app/statusCells";
import { useSubjectContext } from "../../app/subjectContext";
import { Button } from "../../ui/Button";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { PageLayout } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Chip, StatusDot } from "../../ui/Status";
import { getOverview, type OverviewSubject } from "./api";
import {
  COLUMN_LABEL,
  PRESENCE_COLUMNS,
  blockedReason,
  isReady,
  notConverted,
  overviewStatusValue,
  presenceCells,
  readyFor,
  stages as stagesOf,
} from "./model";
import "./overview.css";

const COLUMNS = "minmax(88px, 1fr) 264px minmax(96px, 1fr) 44px 44px 44px";

type Scope = "all" | "ready" | "incomplete";

function OverviewPage() {
  const navigate = useNavigate();
  const overviewQuery = useQuery({ queryKey: ["overview"], queryFn: getOverview });
  const setSubject = useSubjectContext((s) => s.setSubject);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("all");

  const data = overviewQuery.data;
  const rows: OverviewSubject[] = useMemo(() => data?.subjects ?? [], [data]);
  const stages = useMemo(() => (data ? stagesOf(data) : []), [data]);

  const q = query.trim().toLowerCase();
  const visible = rows.filter((r) => {
    if (q && !r.id.toLowerCase().includes(q)) return false;
    if (scope === "ready") return isReady(r);
    if (scope === "incomplete") return !isReady(r);
    return true;
  });

  const selectedRow = rows.find((r) => r.id === selected);

  useStatusCells([{ id: "counts", value: overviewStatusValue(data), priority: 10 }]);

  // Clicking the selected row again clears the selection, and so does Esc on the table — the only
  // ways back to the full-width table, which is what U1 asks the page to fall back to.
  const choose = useCallback(
    (id: string) => {
      setSelected((prev) => (prev === id ? null : id));
      setSubject(id);
    },
    [setSubject],
  );

  const goResults = useCallback(
    (id: string) => {
      setSubject(id);
      navigate("/results", { state: { subject: id } });
    },
    [navigate, setSubject],
  );

  const detail = selectedRow ? (
    <div className="overview-detail" data-testid="overview-detail">
      <div className="overview-detail-header">{selectedRow.id}</div>
      <div className="overview-detail-body">
        <dl className="overview-kv">
          <dt>Raw MRI</dt>
          <dd>
            {selectedRow.raw === "present"
              ? "converted"
              : notConverted(selectedRow)
                ? "not converted"
                : selectedRow.raw === "pending"
                  ? "running now"
                  : selectedRow.raw === "failed"
                    ? "last run failed"
                    : "none staged"}
          </dd>
          <dt>Head model</dt>
          <dd>{selectedRow.m2m === "present" ? "built" : selectedRow.m2m === "pending" ? "running now" : "not built"}</dd>
          <dt>Surfaces</dt>
          <dd>
            {selectedRow.fastsurfer === "present"
              ? "FastSurfer"
              : selectedRow.freesurfer === "present"
                ? "FreeSurfer"
                : "none"}
          </dd>
          <dt>Leadfield</dt>
          <dd>{selectedRow.leadfields.length ? selectedRow.leadfields.join(", ") : "none"}</dd>
          <dt>EEG nets</dt>
          <dd>{selectedRow.eeg_nets.length ? selectedRow.eeg_nets.join(", ") : "none"}</dd>
          <dt>Diffusion</dt>
          <dd>{selectedRow.dwi === "present" ? "DWI present" : "none"}</dd>
          <dt>CT</dt>
          <dd>{selectedRow.ct === "present" ? "CT present" : "none"}</dd>
        </dl>

        {/* Counts, each a link into Results. Results is the outputs browser (Q3) — this pane never
            grows a tree or a preview of its own, and every count here came from the same single
            overview response as the table's columns. */}
        <p className="overview-eyebrow">Outputs</p>
        <div data-testid="overview-counts">
          {(
            [
              ["Simulations", selectedRow.counts.simulations],
              ["Optimizations", selectedRow.counts.optimizations],
              ["Analyses", selectedRow.counts.analyses],
            ] as const
          ).map(([label, count]) => (
            <button
              key={label}
              type="button"
              className="overview-link"
              data-testid={`overview-link-${label.toLowerCase()}`}
              onClick={() => goResults(selectedRow.id)}
            >
              <span>{label}</span>
              <span className="overview-link-count">{count}</span>
            </button>
          ))}
        </div>
        <Button variant="ghost" size="sm" data-testid="overview-open-results" onClick={() => goResults(selectedRow.id)}>
          Open in Results
        </Button>
      </div>
      <div className="overview-verbs">
        {stages.map((s) => (
          <Button
            key={s.id}
            variant="secondary"
            size="sm"
            data-testid={`overview-verb-${s.id}`}
            disabled={!readyFor(selectedRow, s.id)}
            title={blockedReason(selectedRow, s.id)}
            onClick={() => {
              setSubject(selectedRow.id);
              navigate(s.route, { state: { subject: selectedRow.id } });
            }}
          >
            {s.verb}
          </Button>
        ))}
        <Button
          variant="ghost"
          size="sm"
          icon={<Eye size={14} />}
          data-testid="overview-open-in-viewer"
          disabled={selectedRow.m2m !== "present"}
          onClick={() => {
            setSubject(selectedRow.id);
            navigate(
              { pathname: "/viewer", search: `?kind=subject&subject=${encodeURIComponent(selectedRow.id)}` },
              { state: { subject: selectedRow.id } },
            );
          }}
        >
          Open in viewer
        </Button>
      </div>
    </div>
  ) : undefined;

  if (data && rows.length === 0) {
    return (
      <PageLayout variant="browse">
        <EmptyState icon={<LayoutGrid size={24} />} message="This project has no subjects yet." />
      </PageLayout>
    );
  }

  return (
    <PageLayout variant="browse" rightPaneKind="preview" rightPaneWidth={360} rightPane={detail}>
      <div className="overview-page" style={{ ["--overview-cols" as string]: COLUMNS }}>
        {overviewQuery.error && <Callout kind="danger">Could not load this project's overview.</Callout>}
        {overviewQuery.isPending && <Skeleton rows={4} />}

        <div className="overview-coverage" data-testid="overview-coverage">
          {(data?.totals.coverage ?? []).map((t) => (
            <div key={t.id} className="overview-tile">
              <span className="overview-tile-label">{t.id}</span>
              <span className="overview-tile-value">
                {t.have}/{t.total}
              </span>
              <span className="overview-tile-bar">
                <span style={{ width: `${t.total ? Math.round((100 * t.have) / t.total) : 0}%` }} />
              </span>
            </div>
          ))}
        </div>

        <div className="overview-toolbar">
          <span className="overview-count">
            {visible.length} of {rows.length} subjects
          </span>
          <label className="overview-search">
            <Search size={12} aria-hidden />
            <input
              type="search"
              aria-label="Filter subjects"
              data-testid="overview-filter"
              placeholder="Filter…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <SegmentedControl
            value={scope}
            onValueChange={(v) => setScope(v)}
            size="sm"
            aria-label="Subject scope"
            options={[
              { value: "all", label: "All" },
              { value: "ready", label: "Ready" },
              { value: "incomplete", label: "Incomplete" },
            ]}
          />
        </div>

        <div
          className="overview-table"
          data-testid="overview-table"
          role="grid"
          aria-label="Project overview"
          onKeyDown={(e) => {
            if (e.key === "Escape" && selected !== null) {
              e.stopPropagation();
              setSelected(null);
            }
          }}
        >
          <div className="overview-row overview-head" role="row">
            <span role="columnheader">Subject</span>
            <span role="columnheader" className="overview-presence overview-presence-head">
              {PRESENCE_COLUMNS.map((key) => (
                <span key={key}>{COLUMN_LABEL[key]}</span>
              ))}
            </span>
            <span role="columnheader">Leadfield</span>
            <span role="columnheader" className="overview-num">
              Sim
            </span>
            <span role="columnheader" className="overview-num">
              Opt
            </span>
            <span role="columnheader" className="overview-num">
              Anly
            </span>
          </div>
          {visible.map((r) => (
            <button
              key={r.id}
              type="button"
              role="row"
              aria-selected={r.id === selected}
              className="overview-row"
              data-testid={`overview-row-${r.id}`}
              onClick={() => choose(r.id)}
            >
              <span className="overview-id">{r.id}</span>
              <span className="overview-presence">
                {presenceCells(r).map((p) => (
                  <span key={p.key}>
                    <StatusDot kind={p.kind} pulse={p.pulse} title={p.title} />
                  </span>
                ))}
              </span>
              <span className="overview-net">
                {r.leadfields.length ? <Chip kind="success">{r.leadfields[0]}</Chip> : <span className="text-caption">none</span>}
              </span>
              <span className="overview-num">{r.counts.simulations}</span>
              <span className="overview-num">{r.counts.optimizations}</span>
              <span className="overview-num">{r.counts.analyses}</span>
            </button>
          ))}
          {visible.length === 0 && rows.length > 0 && (
            <EmptyState variant="inline" icon={<Search size={20} />} message="No subjects match this filter." />
          )}
        </div>

        <p className="overview-section-head">Readiness · who can run what next</p>
        <div className="overview-readiness" data-testid="overview-readiness">
          {stages.map((s) => (
            <div key={s.id} className="overview-stage" data-testid={`overview-stage-${s.id}`}>
              <div className="overview-stage-head">
                <span className="overview-stage-name">{s.label}</span>
                <span className="overview-stage-ready">
                  {s.ready.length} of {rows.length} ready
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  data-testid={`overview-run-${s.id}`}
                  disabled={s.ready.length === 0}
                  onClick={() => navigate(s.route)}
                >
                  {s.verb}
                </Button>
              </div>
              <p className="overview-stage-summary">{s.summary}</p>
              <div className="overview-stage-chips">
                {s.ready.map((id) => {
                  // "ready" for Pre-processing also covers a sourcedata-only subject: still worth
                  // flagging, since only the DICOM stage is runnable until it converts.
                  const row = rows.find((r) => r.id === id);
                  const staged = s.id === "preprocess" && row !== undefined && notConverted(row);
                  return (
                    <Chip
                      key={id}
                      kind={staged ? "warning" : "success"}
                      title={staged ? `${id}: not converted -- DICOM staged under sourcedata/` : `${id} can run ${s.label.toLowerCase()}`}
                    >
                      {staged ? `${id} — not converted` : id}
                    </Chip>
                  );
                })}
                {s.blocked.map((b) => (
                  <Chip key={b.subject} kind="warning" title={`${b.subject}: ${b.reason}`}>
                    {b.subject} — {b.reason}
                  </Chip>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "overview",
  title: "Overview",
  purpose: "What is on disk across this project, and what can run next.",
  navGroup: "workspace",
  order: 1,
  icon: LayoutGrid,
  shortcut: "1",
  Component: OverviewPage,
  enabled: true,
};

export default page;
