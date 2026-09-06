/**
 * Results — the outputs browser (program U4, DESIGN.md §2 shape B, wireframes §6).
 *
 * v3 replaces the v2 page, which was the PyQt tab strip in a browser: a `Subject` dropdown over
 * five tabs (Simulations / Flex / Ex / Analyses / Group), each with its own split view, under an
 * 86 px page header. Three problems the shape below fixes:
 *
 * - the dropdown hid the project. You could not see that `101` had one output and `MNI152` none
 *   without selecting each in turn. The left column shows every subject and its count at once.
 * - the tabs were a filing system, not a question anyone asks. "What has this subject produced?"
 *   is one tree with type badges and a filter, not five tabs to click through.
 * - the header restated the nav label. It is gone (checklist item 2).
 *
 * Layout: subject list 200 · outputs tree flex · preview `clamp(380px, 40%, 560px)`. The preview
 * is PageLayout's right pane and is **not rendered** when the subject has no outputs — the tree
 * takes its width (U1: never an empty pane).
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Eye,
  FolderOpen,
  FolderTree,
  Search,
} from "lucide-react";
import { getSubjects } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { usePageSession } from "../../app/pageSession";
import { usePageActive } from "../../app/pageActivity";
import { SUBJECT_PARAM, SUBJECT_SYNC_STATE } from "../../app/subjectSpine";
import { useSubjectContext } from "../../app/subjectContext";
import { isElectron } from "../../env";
import { Button, IconButton } from "../../ui/Button";
import { ArtifactList, type ArtifactItem } from "../../ui/Jobs";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { PageLayout, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Chip } from "../../ui/Status";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { notify } from "../../ui/Toast";
import {
  artifactUrl,
  getAnalyses,
  getAnalysisSummary,
  getExRunResults,
  getExRuns,
  getFlexRuns,
  getReports,
  getSimulationsFor,
  getTextFile,
  reportUrl,
  type Artifact,
  type SimulationDetail,
  type TableData,
} from "./api";
import { EX_COLUMN_LABELS, exRunConfigPath, parseExRunConfig, rankExRows, type ExTable } from "./preview/ex";
import { flexManifestSummary, flexPositionsPath, flexSummaryPath, parseFlexPositions, parseFlexSummaryText } from "./preview/flex";
import { parseSimulationConfig, simulationConfigPath } from "./preview/simulation";
import {
  BucketList,
  ElectrodePositionTable,
  FieldFileList,
  FigureGrid,
  PairChips,
  PathLine,
  PreviewSection,
  RankedTable,
  SummaryRows,
} from "./preview/views";
import {
  analysisArtifacts,
  filterOutputs,
  GROUP_SUBJECT,
  treeRows,
  truncatePathLeft,
  type OutputFilter,
  type OutputNode,
  type SubjectOutputs,
  type TreeRow,
} from "./outputsTree";
import { subjectRows, useSubjectOutputs } from "./useOutputs";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import "./results.css";

// ----------------------------------------------------------------------- host actions

/** The artifact route in a new tab — the browser sends the session cookie on a normal navigation. */
function viewArtifact(path: string): void {
  window.open(artifactUrl(path), "_blank", "noopener");
}

/** `TitBridge.openPath`, falling back to the in-browser tab when there is no native shell. */
function openArtifact(path: string): void {
  const fn = isElectron ? window.tit?.openPath : undefined;
  if (fn) void fn(path);
  else viewArtifact(path);
}

/** `TitBridge.showItemInFolder` (P9's host↔container path mapping); `undefined` outside Electron. */
function reveal(path: string): void {
  const fn = isElectron ? window.tit?.showItemInFolder : undefined;
  if (fn) void fn(path);
  else
    notify.info(
      "Reveal in file manager isn't available outside the Electron app.",
    );
}

function artifactItems(artifacts: Artifact[]): ArtifactItem[] {
  return artifacts.map((a) => ({
    path: a.path,
    kind: a.kind,
    label: a.label ?? a.path.split("/").pop() ?? a.path,
  }));
}

/** Artifact kinds the preview renders as a thumbnail rather than as a row (U14's "figures"). The
 * real catalog labels a PNG `image` (`tit/catalog.py::_ARTIFACT_KIND_BY_EXT`); the fixtures and the
 * ex/flex run rows say `png`. Both are the same thing to this pane. */
const IMAGE_KINDS = new Set(["png", "image", "jpg", "jpeg"]);

/** A simulation's own field files, from the catalog's `niftis`/`meshes` — the same projection the
 * outputs tree makes, kept here so the preview can show them with kind badges (U14). */
function simulationFieldFiles(sim: SimulationDetail): Artifact[] {
  return [
    ...sim.niftis.map((n) => ({
      path: n.path,
      kind: "nifti",
      label: `${n.field} · ${n.space}${n.tissue ? ` · ${n.tissue}` : ""}`,
    })),
    ...sim.meshes.map((m) => ({ path: m.path, kind: "mesh", label: `${m.kind} mesh` })),
  ];
}

// ----------------------------------------------------------------------- viewer deep link

/**
 * "Open in viewer" — a deep link to the Viewer page, not a launch. D3 removed X11 from the runtime,
 * so there is no Freeview and no Gmsh to hand a file to.
 *
 * The query goes on the ROUTER's URL — the app is a `MemoryRouter`, so that is the only query the
 * Viewer page can read from a navigation — and the subject also rides in the router state so the
 * shell's subject switcher re-scopes with it.
 */
export interface ViewerLink {
  subject: string;
  simulation?: string;
  field?: string;
  kind?: "subject" | "simulation" | "analysis";
}

export function viewerSearch(link: ViewerLink): string {
  const params = new URLSearchParams();
  params.set("kind", link.kind ?? (link.simulation ? "simulation" : "subject"));
  params.set("subject", link.subject);
  if (link.simulation) params.set("simulation", link.simulation);
  if (link.field) params.set("field", link.field);
  return `?${params.toString()}`;
}

export function useOpenInViewer(): (link: ViewerLink) => void {
  const navigate = useNavigate();
  return useCallback(
    (link: ViewerLink) =>
      navigate(
        { pathname: "/viewer", search: viewerSearch(link) },
        { state: { subject: link.subject } },
      ),
    [navigate],
  );
}

/** The viewer link a tree node stands for. `undefined` for a node with no subject-space field. */
export function viewerLinkFor(
  subject: string,
  node: OutputNode,
): ViewerLink | undefined {
  if (subject === GROUP_SUBJECT) return undefined;
  if (node.kind === "simulation") return { subject, simulation: node.label };
  if (node.kind === "analysis") {
    const simulation = node.label.split(" / ")[0];
    return { subject, simulation, kind: "analysis" };
  }
  return { subject };
}

// ----------------------------------------------------------------------- small views

function FilterBox({
  value,
  onChange,
  placeholder,
  testid,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  testid: string;
  label: string;
}) {
  return (
    <div className="results-filter">
      <Search size={12} aria-hidden />
      <input
        type="search"
        aria-label={label}
        data-testid={testid}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function TableDataView({
  table,
  emptyMessage,
}: {
  table: TableData | undefined;
  emptyMessage: string;
}) {
  const columns = useMemo<DataTableColumn<unknown[]>[]>(
    () =>
      (table?.columns ?? []).map((name, i) => ({
        header: name,
        cell: ({ row }) => {
          const v = row.original[i];
          return typeof v === "number"
            ? v.toFixed(4).replace(/\.?0+$/, "")
            : String(v ?? "");
        },
        numeric: table?.rows.every((r) => typeof r[i] === "number"),
      })),
    [table],
  );
  return (
    <DataTable
      data={table?.rows ?? []}
      columns={columns}
      emptyMessage={emptyMessage}
    />
  );
}

// ----------------------------------------------------------------------- preview pane

/**
 * The preview of one node (program U14). What it is, not where it is: the pane opens with a
 * summary built from the run's own manifest — a simulation's `documentation/config.json`, a flex
 * run's `flex_meta.json` (already inlined by the catalog as `FlexRun.manifest`) plus its
 * `summary.txt` and `electrode_positions.json`, an ex/mEx run's `run_config.json` — then the files
 * it produced, then its figures. The container path is one mono line at the foot with a copy
 * control; before U14 it was the headline of a pane whose only other content was a button.
 *
 * Every catalog query key here is one `useSubjectOutputs` already primed, so naming the artifacts
 * of an ex-search run or an analysis costs no extra request. The three manifest reads are the only
 * new traffic, one small file each, cached for the session (`staleTime: Infinity` — a finished run
 * does not rewrite its own config).
 */
function Preview({
  subject,
  node,
  paneControls,
  onSelectNode,
}: {
  subject: string;
  node: OutputNode;
  /** `ui/Layout`'s `PaneHeaderControls` — collapse and expand, in the pane's own header (U13). */
  paneControls?: ReactNode;
  /** Select another node in the tree, for the analyses and reports a simulation holds. */
  onSelectNode?: (id: string) => void;
}) {
  const openInViewer = useOpenInViewer();
  const link = viewerLinkFor(subject, node);
  const preview = node.preview;
  const isSimulation = node.kind === "simulation";
  const isFlex = node.kind === "flex";
  const isExRun = preview.type === "exRun";
  const reportId = preview.type === "report" ? preview.reportId : undefined;
  const isReportNode = node.kind === "report";

  const sims = useQuery({
    queryKey: ["results-simulations", subject],
    queryFn: () => getSimulationsFor(subject),
    enabled: isSimulation,
  });
  const flexRuns = useQuery({
    queryKey: ["results-flex-runs", subject],
    queryFn: () => getFlexRuns(subject),
    enabled: isFlex,
  });
  const reports = useQuery({
    queryKey: ["results-reports", subject],
    queryFn: () => getReports(subject),
    enabled: isSimulation,
  });
  const simAnalyses = useQuery({
    queryKey: ["results-analyses", subject, isSimulation ? node.label : ""],
    queryFn: () => getAnalyses(subject, node.label),
    enabled: isSimulation,
  });
  const exList = useQuery({
    queryKey: ["results-ex-runs", subject, preview.type === "exRun" ? preview.kind : "ex"],
    queryFn: () => getExRuns(subject, preview.type === "exRun" ? preview.kind : "ex"),
    enabled: isExRun,
  });
  const exResults = useQuery({
    queryKey: [
      "results-ex-run-results",
      subject,
      preview.type === "exRun" ? preview.kind : "ex",
      preview.type === "exRun" ? preview.run : "",
    ],
    queryFn: () =>
      getExRunResults((preview as { run: string }).run, subject, (preview as { kind: "ex" | "mex" }).kind),
    enabled: isExRun,
  });
  const analysisList = useQuery({
    queryKey: ["results-analyses", subject, preview.type === "analysis" ? preview.simulation : ""],
    queryFn: () => getAnalyses(subject, (preview as { simulation: string }).simulation),
    enabled: preview.type === "analysis",
  });
  const analysisSummary = useQuery({
    queryKey: [
      "results-analysis-summary",
      subject,
      preview.type === "analysis" ? preview.simulation : "",
      preview.type === "analysis" ? preview.name : "",
    ],
    queryFn: () =>
      getAnalysisSummary(
        (preview as { name: string }).name,
        subject,
        (preview as { simulation: string }).simulation,
      ),
    enabled: preview.type === "analysis",
  });

  // The three manifest files the catalog does not inline. `retry: false`: a run written by an older
  // toolbox has no `summary.txt`, and one 404 must not cost the pane three round trips.
  const manifestQuery = (path: string | undefined, enabled: boolean) => ({
    queryKey: ["results-file-text", path ?? ""],
    queryFn: () => getTextFile(path!),
    enabled: enabled && !!path,
    retry: false,
    staleTime: Infinity,
  });
  const simConfig = useQuery(manifestQuery(node.path ? simulationConfigPath(node.path) : undefined, isSimulation));
  const flexSummary = useQuery(manifestQuery(node.path ? flexSummaryPath(node.path) : undefined, isFlex));
  const flexPositions = useQuery(manifestQuery(node.path ? flexPositionsPath(node.path) : undefined, isFlex));
  const exConfig = useQuery(manifestQuery(node.path ? exRunConfigPath(node.path) : undefined, isExRun));

  const simulation = isSimulation ? sims.data?.find((s) => s.name === node.label) : undefined;
  const flexRun = isFlex ? flexRuns.data?.find((r) => r.name === node.label) : undefined;
  const exRun = isExRun ? exList.data?.find((r) => r.run_name === (preview as { run: string }).run) : undefined;

  /** Every artifact this node names, whichever catalog read carries them. */
  const artifacts: Artifact[] = useMemo(() => {
    if (isSimulation) return simulation ? simulationFieldFiles(simulation) : [];
    if (isFlex) return flexRun?.artifacts ?? (preview.type === "artifacts" ? preview.artifacts : []);
    if (isExRun) return exRun?.artifacts ?? [];
    if (preview.type === "analysis") {
      const a = analysisList.data?.find((x) => x.name === preview.name);
      return a ? analysisArtifacts(a) : [];
    }
    if (node.kind === "report") return [{ path: node.path, kind: "html", label: "Report file" }];
    return preview.type === "artifacts" ? preview.artifacts : [];
  }, [isSimulation, isFlex, isExRun, simulation, flexRun, exRun, preview, node, analysisList.data]);

  const figures = useMemo(() => artifacts.filter((a) => IMAGE_KINDS.has(a.kind)), [artifacts]);
  const files = useMemo(() => artifacts.filter((a) => !IMAGE_KINDS.has(a.kind)), [artifacts]);

  const simSummary = useMemo(
    () => (simConfig.data ? parseSimulationConfig(simConfig.data) : undefined),
    [simConfig.data],
  );
  const flexRows = useMemo(
    () => [
      ...flexManifestSummary(flexRun?.manifest).rows,
      ...(flexSummary.data ? parseFlexSummaryText(flexSummary.data) : []),
    ],
    [flexRun?.manifest, flexSummary.data],
  );
  const flexElectrodes = useMemo(
    () => (flexPositions.data ? parseFlexPositions(flexPositions.data) : []),
    [flexPositions.data],
  );
  const exSummary = useMemo(() => (exConfig.data ? parseExRunConfig(exConfig.data) : undefined), [exConfig.data]);
  const exTop = useMemo(() => rankExRows(exResults.data as ExTable | undefined), [exResults.data]);

  const simReports = (reports.data ?? []).filter((r) => simulation?.report_ids.includes(r.id));

  /** The report iframe, sandboxed here as well as by the route's own CSP (`files.py::REPORT_CSP`). */
  const reportFrame = (id: string) => (
    <iframe
      className="results-report-frame"
      data-testid="results-report-frame"
      title={isReportNode ? node.label : `${node.label} report`}
      src={reportUrl(id)}
      sandbox="allow-scripts"
    />
  );

  let body: ReactNode;
  let flush = false;
  if (isReportNode && reportId) {
    // A report node IS the document (U14: "reports keep their iframe"), so it gets the whole pane.
    flush = true;
    body = reportFrame(reportId);
  } else if (isSimulation) {
    body = (
      <>
        <PreviewSection title="Simulation" testid="results-summary-simulation">
          {simConfig.isPending && <Skeleton height={120} />}
          {simSummary ? (
            <>
              <SummaryRows rows={simSummary.rows} testid="results-summary-rows" />
              <PairChips pairs={simSummary.pairs} testid="results-pair-chips" />
            </>
          ) : (
            !simConfig.isPending && (
              <p className="field-help">
                This run has no <span className="mono">documentation/config.json</span>; its settings were not recorded.
              </p>
            )
          )}
        </PreviewSection>
        <PreviewSection title={`Field files · ${files.length}`}>
          <FieldFileList files={files} onOpen={openArtifact} onReveal={reveal} />
        </PreviewSection>
        {(simAnalyses.data?.length || simReports.length > 0) && (
          <PreviewSection title="Holds" testid="results-holds">
            <div className="results-holds">
              {(simAnalyses.data ?? []).map((a) => (
                <button
                  key={a.name}
                  type="button"
                  className="results-hold"
                  onClick={() => onSelectNode?.(`analysis:${subject}:${node.label}/${a.name}`)}
                >
                  <Chip kind="neutral">analysis</Chip>
                  {a.name}
                </button>
              ))}
              {simReports.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="results-hold"
                  onClick={() => onSelectNode?.(`report:${subject}:${r.id}`)}
                >
                  <Chip kind="neutral">report</Chip>
                  {r.title}
                </button>
              ))}
            </div>
          </PreviewSection>
        )}
        {reportId && (
          // The rendered report, inline under the numbers rather than behind a toggle: it is the
          // densest thing a simulation holds, and a 490x800 pane that stops after eight rows is
          // exactly the dead space U1 measures. It fills whatever height the summary leaves.
          <PreviewSection title="Report" testid="results-report-section">
            <div className="results-report-inline">{reportFrame(reportId)}</div>
          </PreviewSection>
        )}
      </>
    );
  } else if (isFlex) {
    body = (
      <>
        <PreviewSection title="Flex search" testid="results-summary-flex">
          {flexSummary.isPending && flexRows.length === 0 && <Skeleton height={120} />}
          <SummaryRows rows={flexRows} testid="results-summary-rows" />
        </PreviewSection>
        {flexElectrodes.length > 0 && (
          <PreviewSection title="Final electrode positions" testid="results-flex-positions">
            <ElectrodePositionTable electrodes={flexElectrodes} />
          </PreviewSection>
        )}
        {figures.length > 0 && (
          <PreviewSection title={`Figures · ${figures.length}`}>
            <FigureGrid figures={figures} onOpen={viewArtifact} />
          </PreviewSection>
        )}
      </>
    );
  } else if (isExRun) {
    body = (
      <>
        <PreviewSection title={preview.type === "exRun" && preview.kind === "mex" ? "mEx search" : "Ex search"} testid="results-summary-ex">
          {exConfig.isPending && <Skeleton height={100} />}
          <SummaryRows rows={exSummary?.rows ?? []} testid="results-summary-rows" />
          <BucketList buckets={exSummary?.buckets ?? []} />
        </PreviewSection>
        <PreviewSection title="Top 10 montages by composite index">
          {exResults.isPending ? (
            <Skeleton height={160} />
          ) : exResults.error ? (
            <Callout kind="danger">Could not load results for this run.</Callout>
          ) : (
            <div data-testid="results-ex-table">
              <RankedTable table={exTop} labels={EX_COLUMN_LABELS} emptyMessage="No rows in this run's results table." />
            </div>
          )}
        </PreviewSection>
        {figures.length > 0 && (
          <PreviewSection title={`Figures · ${figures.length}`}>
            <FigureGrid figures={figures} onOpen={viewArtifact} />
          </PreviewSection>
        )}
      </>
    );
  } else if (preview.type === "analysis") {
    body = analysisSummary.isPending ? (
      <Skeleton height={160} />
    ) : analysisSummary.error ? (
      <Callout kind="danger">Could not load the summary table.</Callout>
    ) : (
      <div data-testid="results-analysis-table">
        <TableDataView table={analysisSummary.data} emptyMessage="No rows in this analysis's summary." />
      </div>
    );
  } else {
    body = <SummaryRows rows={[{ label: "Kind", value: node.kind }]} />;
  }

  return (
    <div className="results-preview" data-testid="results-preview">
      <div className="results-preview-header">
        <span className="results-preview-title" title={node.label}>
          {node.label}
        </span>
        <div className="results-preview-header-actions">
          {node.path && (
            <IconButton
              aria-label="Open externally"
              icon={<ExternalLink size={14} />}
              onClick={() => openArtifact(node.path)}
            />
          )}
          {node.path && (
            <IconButton
              aria-label="Reveal in file manager"
              icon={<FolderOpen size={14} />}
              onClick={() => reveal(node.path)}
            />
          )}
        </div>
        {paneControls}
      </div>
      <div className={flush ? "results-preview-body results-preview-body-flush" : "results-preview-body"}>{body}</div>
      {!isSimulation && files.length > 0 && (
        <div className="results-preview-artifacts">
          <p className="results-eyebrow">Files</p>
          <ArtifactList
            artifacts={artifactItems(files)}
            onOpen={(a) => openArtifact(a.path)}
            onView={(a) => viewArtifact(a.path)}
            onReveal={(a) => reveal(a.path)}
          />
        </div>
      )}
      <div className="results-preview-foot">
        <PathLine path={node.path} />
        {link && (
          <Button
            variant="secondary"
            size="sm"
            data-testid="results-open-in-viewer"
            icon={<Eye size={14} />}
            onClick={() => openInViewer(link)}
          >
            Open in viewer
          </Button>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------- the page

const FILTER_SEGMENTS: { value: OutputFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "simulation", label: "Sim" },
  { value: "flex", label: "Flex" },
  { value: "exmex", label: "Ex" },
  { value: "analysis", label: "Analysis" },
  { value: "report", label: "Report" },
];

function relative(iso: string | undefined): string {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (!Number.isFinite(days)) return "";
  if (days <= 0) return "today";
  if (days === 1) return "1 d";
  if (days < 30) return `${days} d`;
  return `${Math.floor(days / 30)} mo`;
}

function ResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const active = usePageActive();
  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: () => getSubjects(),
  });
  const globalSubject = useSubjectContext((s) => s.subjectId);
  const setGlobalSubject = useSubjectContext((s) => s.setSubject);
  usePageScrollMemory();

  const ids = useMemo(
    () => (subjectsQuery.data ?? []).map((s) => s.id),
    [subjectsQuery.data],
  );
  const [pickedSubject, setPickedSubject] = usePageSession<string | undefined>(
    "subject",
    undefined,
  );
  const subject =
    pickedSubject ??
    (globalSubject && ids.includes(globalSubject) ? globalSubject : ids[0]);

  const outputs = useSubjectOutputs(ids, subject);
  const current: SubjectOutputs | undefined =
    subject === GROUP_SUBJECT
      ? outputs.group
      : subject
        ? outputs.bySubject[subject]
        : undefined;

  const [subjectQuery, setSubjectQuery] = usePageSession("subjectQuery", "");
  const [treeQuery, setTreeQuery] = usePageSession("treeQuery", "");
  const [filter, setFilter] = usePageSession<OutputFilter>("filter", "all");
  const [collapsed, setCollapsed] = usePageSession<ReadonlySet<string>>("collapsedGroups", () => new Set<string>());
  const [pickedId, setPickedId] = usePageSession<string | undefined>("pickedNode", undefined);
  const [activeKey, setActiveKey] = usePageSession<string | undefined>("activeRow", undefined);
  const treeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!active || location.state?.[SUBJECT_SYNC_STATE]) return;
    const stateSubject = typeof location.state?.subject === "string" ? location.state.subject : null;
    const linkedSubject = new URLSearchParams(location.search).get(SUBJECT_PARAM) ?? stateSubject;
    if (!linkedSubject) return;
    // A subject's "View in Results" action intentionally changes this destination. A plain tab
    // visit has no subject instruction and leaves its filters, selection and preview intact.
    setPickedSubject(linkedSubject);
    setPickedId(undefined);
    setActiveKey(undefined);
  }, [active, location.key, location.search, location.state, setPickedSubject, setPickedId, setActiveKey]);

  const filtered = useMemo(
    () => (current ? filterOutputs(current, filter, treeQuery) : undefined),
    [current, filter, treeQuery],
  );
  const rows = useMemo(
    () => (filtered ? treeRows(filtered, collapsed) : []),
    [filtered, collapsed],
  );
  const nodes = useMemo(
    () => rows.flatMap((r) => (r.type === "node" ? [r.node] : [])),
    [rows],
  );

  // Derived, never an effect: the selection is "what the user picked, if it is still on screen,
  // else the first node". Landing on a subject with outputs and an empty preview pane would be a
  // 490 px column of "select something", which is the dead space U1 exists to stop — and a
  // `useEffect` that assigns it would render the empty pane once on every subject change.
  const selected = nodes.find((n) => n.id === pickedId) ?? nodes[0];
  const selectedId = selected?.id;

  const visibleSubjects = useMemo(() => {
    const q = subjectQuery.trim().toLowerCase();
    return subjectRows(ids).filter((id) => !q || id.toLowerCase().includes(q));
  }, [ids, subjectQuery]);

  const chooseSubject = useCallback(
    (id: string) => {
      setPickedSubject(id);
      setPickedId(undefined);
      setActiveKey(undefined);
      if (id !== GROUP_SUBJECT) setGlobalSubject(id);
    },
    [setActiveKey, setGlobalSubject, setPickedId, setPickedSubject],
  );

  const toggleGroup = useCallback((label: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }, [setCollapsed]);

  // The roving focus is stored as a row KEY, not an index: a filter keystroke or a collapse changes
  // every index but not the identity of the row the user was on. It falls back to the selected
  // node's row, so arrowing always starts from what is on screen.
  const keyedIndex = rows.findIndex((r) => r.key === activeKey);
  const activeIndex =
    keyedIndex >= 0
      ? keyedIndex
      : Math.max(
          0,
          rows.findIndex((r) => r.type === "node" && r.node.id === selectedId),
        );

  const onTreeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (rows.length === 0) return;
      const row: TreeRow | undefined =
        rows[Math.min(activeIndex, rows.length - 1)];
      const goto = (i: number): void => {
        e.preventDefault();
        setActiveKey(rows[Math.max(0, Math.min(rows.length - 1, i))]?.key);
      };
      if (e.key === "ArrowDown") goto(activeIndex + 1);
      else if (e.key === "ArrowUp") goto(activeIndex - 1);
      else if (e.key === "Home") goto(0);
      else if (e.key === "End") goto(rows.length - 1);
      else if (
        (e.key === "ArrowRight" || e.key === "ArrowLeft") &&
        row?.type === "group" &&
        row.expanded === (e.key === "ArrowLeft")
      ) {
        e.preventDefault();
        toggleGroup(row.group.label);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (row?.type === "node") setPickedId(row.node.id);
        else if (row?.type === "group") toggleGroup(row.group.label);
      }
    },
    [rows, activeIndex, setActiveKey, setPickedId, toggleGroup],
  );

  const wide = useWideTree(treeRef);

  // U13: stretch / collapse / expand, from the shared primitive. `enabled` is "this subject has an
  // output to preview", so a subject with nothing does not own ⌘⇧I and cannot be left in a
  // collapsed state the pane it no longer renders would have to explain.
  const hasPreview = !!(current && current.total > 0 && selected && subject);
  const pane = // `minWidth: 320` — the preview is §2.1's `clamp(380px, 40%, 560px)` document pane and keeps its
  // own floor; only the ceiling grew.
  usePaneController({ pageId: "results", name: "preview", minWidth: 320, enabled: hasPreview });

  const treePane = (
    <div className="results-tree-pane" data-testid="results-tree-pane">
      <div className="results-tree-toolbar">
        <FilterBox
          value={treeQuery}
          onChange={setTreeQuery}
          placeholder="Filter outputs…"
          testid="results-tree-filter"
          label="Filter outputs"
        />
        <SegmentedControl
          value={filter}
          onValueChange={(v) => setFilter(v)}
          options={FILTER_SEGMENTS}
          size="sm"
          aria-label="Output kind"
        />
      </div>
      <div
        className="results-tree"
        data-testid="results-tree"
        role="tree"
        aria-label="Outputs"
        tabIndex={0}
        ref={treeRef}
        onKeyDown={onTreeKeyDown}
      >
        <div data-testid="results-tree-rows">
          {subjectsQuery.error && (
            <Callout kind="danger">Could not load the subject list.</Callout>
          )}
          {!current && outputs.pending && <Skeleton height={160} />}
          {current && current.total === 0 && (
            <EmptyState
              variant="inline"
              icon={<FolderTree size={20} />}
              message={`${subject} has no outputs yet.`}
              actionLabel="Run a simulation"
              onAction={() => navigate("/simulator")}
            />
          )}
          {filtered && filtered.total === 0 && current && current.total > 0 && (
            <EmptyState
              variant="inline"
              icon={<Search size={20} />}
              message="No outputs match this filter."
            />
          )}
          {rows.map((row, i) =>
            row.type === "group" ? (
              <button
                key={row.key}
                type="button"
                className="results-group-row"
                role="treeitem"
                aria-expanded={row.expanded}
                aria-level={1}
                tabIndex={-1}
                data-active={i === activeIndex || undefined}
                onClick={() => {
                  setActiveKey(row.key);
                  toggleGroup(row.group.label);
                }}
              >
                {row.expanded ? (
                  <ChevronDown size={12} aria-hidden />
                ) : (
                  <ChevronRight size={12} aria-hidden />
                )}
                {row.group.label}
                <span className="results-group-count">{row.group.count}</span>
              </button>
            ) : (
              <button
                key={row.key}
                type="button"
                className="results-node"
                role="treeitem"
                aria-level={2}
                aria-selected={row.node.id === selectedId}
                tabIndex={-1}
                data-testid={`results-node-${row.node.id}`}
                data-active={i === activeIndex || undefined}
                title={row.node.path}
                onClick={() => {
                  setActiveKey(row.key);
                  setPickedId(row.node.id);
                }}
              >
                <span className="results-node-label">{row.node.label}</span>
                <span className="results-node-badges">
                  {row.node.badges.map((b) => (
                    <Chip
                      key={b}
                      kind={b === "TI" || b === "mTI" ? "field" : "neutral"}
                    >
                      {b}
                    </Chip>
                  ))}
                </span>
                {wide && (
                  <span className="results-node-path">{truncatePathLeft(row.node.path, 44)}</span>
                )}
                <span className="results-node-created">
                  {relative(row.node.created)}
                </span>
              </button>
            ),
          )}
        </div>
      </div>
    </div>
  );

  return (
    <PageLayout
      variant="browse"
      rightPaneKind="preview"
      paneController={pane}
      rightPane={
        current && current.total > 0 ? (
          selected && subject ? (
            <Preview
              subject={subject}
              node={selected}
              paneControls={<PaneHeaderControls controller={pane} />}
              onSelectNode={setPickedId}
            />
          ) : (
            <div className="results-preview" data-testid="results-preview">
              <div className="results-preview-body">
                <EmptyState
                  variant="inline"
                  icon={<FolderTree size={20} />}
                  message="Select an output to preview it."
                />
              </div>
            </div>
          )
        ) : undefined
      }
    >
      <div className="results-browse">
        <div className="results-subjects" data-testid="results-subjects">
          <FilterBox
            value={subjectQuery}
            onChange={setSubjectQuery}
            placeholder="Filter…"
            testid="results-subject-filter"
            label="Filter subjects"
          />
          {subjectsQuery.isPending && <Skeleton height={80} />}
          <ul
            className="results-subject-list"
            role="listbox"
            aria-label="Subjects"
          >
            {visibleSubjects.map((id) => {
              const outs =
                id === GROUP_SUBJECT ? outputs.group : outputs.bySubject[id];
              return (
                <li
                  key={id}
                  className={
                    id === GROUP_SUBJECT ? "results-subject-group" : undefined
                  }
                >
                  <button
                    type="button"
                    role="option"
                    aria-selected={id === subject}
                    className="results-subject"
                    data-testid={`results-subject-${id}`}
                    onClick={() => chooseSubject(id)}
                  >
                    <span className="results-subject-id">{id}</span>
                    {outs && (
                      <span className="results-subject-count">
                        {outs.total}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
        {treePane}
      </div>
    </PageLayout>
  );
}

/**
 * True once the tree column is wide enough to carry the path beside the badges (the 1440 column of
 * wireframes §6). Measured on the element, not on `window.innerWidth`: the same page in a narrower
 * window with the preview collapsed earns the column too.
 */
function useWideTree(ref: React.RefObject<HTMLDivElement | null>): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) =>
      setWide((entries[0]?.contentRect.width ?? 0) >= 480),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return wide;
}

const page: PageDef = {
  id: "results",
  title: "Results",
  purpose: "Browse simulation, optimization and analysis outputs.",
  navGroup: "explore",
  order: 70,
  icon: FolderTree,
  shortcut: "6",
  Component: ResultsPage,
  enabled: true,
};

export default page;
