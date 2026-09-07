/**
 * Analyzer page — parity source `tit/gui/analyzer_tab.py` (see PARITY.md). A Jobs table where one
 * row is one analysis job, a Plan panel, and the 3-D pane showing the active row's target.
 *
 * Uses plain component state rather than the react-hook-form + ajv infra: the config here is
 * really a *batch* of `AnalyzerConfig` objects (one per row, and one per sphere/region a row's
 * target expands into — see PARITY.md), which does not map onto a single schema-validated form
 * the way a one-shot Run screen does. Matches the existing `pages/overview/index.tsx` precedent of
 * plain `useState` for non-trivial screens.
 *
 * **2026-09-06, maintainer, second jobs pass.** Two sections left the page:
 *
 *  - **OUTPUT** ("Analyses of this simulation…") — `pages/results` owns a simulation's existing
 *    analyses, and a run screen restating them was a second place for the same truth.
 *  - **TARGET** — *"we can modify our analysis input per job"*. The target is now a cell of the
 *    row (`JobRows.tsx`), editable in a dialog holding the shared `RoiPicker` scoped to that row.
 *    The 3-D pane draws the **active** row's target, and its region clicks edit that row.
 *
 * Nothing is global any more. The last page-level section, "Space options", held the voxel tissue
 * compartment — and `AnalyzerConfig.tissue_type` is "voxel space only" (`tit/analyzer/config.py`;
 * `analyzer.py` overwrites it with GM in mesh), so it is a property of the ROW's space and is now a
 * control on the row's second line. The work column is the Jobs table and nothing else.
 */
import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FormSection, PageLayout, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { Button } from "../../ui/Button";
import { Callout, EmptyState } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { useSubject } from "../../app/subjectContext";
import { usePageSession } from "../../app/pageSession";
import { subjectsBlockedReason } from "../_shared/subjects";
import { ExistingOutputsDialog, planCounts, RunPanel, RunWork, planDigest, planModelFrom, stepsFor, useRunShortcut, type PlanModel, type PlanResult as SharedPlanResult } from "../_shared/run";
import { isRoiComplete, type RoiValue } from "../_shared/roi";
import { ScenePane } from "../_shared/scene";
import {
  AnalyzerJobRows,
  analyzerJobsSummary,
  emptyAnalyzerRow,
  isPlannableAnalyzerRow,
  isRunnableAnalyzerRow,
  sameTarget,
  type AnalyzerRow,
  type AnalyzerSubject,
} from "./JobRows";
import { EMPTY_SPHERE } from "./SphereRows";
import { viewerSearch } from "../results";
import {
  buildConfig,
  type AnalysisType,
} from "./buildConfig";
import {
  getSimulationDetails,
  newAnalysisTag,
  planAnalyzerBatch,
  submitAnalyzerJob,
  type AnalyzerConfig,
  type AnalyzerJobSpec,
} from "./api";
import { batchReceipt, submitBatch } from "./submitBatch";

/** Same small local hook every other Run screen defines for its debounced Plan query
 *  (`optimizer-flex/index.tsx`, `optimizer-ex/queries.ts`, `simulator/PlanPanel.tsx`) — not
 *  worth centralizing across lanes for one `setTimeout`. Setting `debounced` from inside the
 *  timeout callback (not synchronously in the effect body) is why this is exempt from
 *  `react-hooks/set-state-in-effect`. */
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

/** One analysis runs the same four steps whatever the ROI is. */
const ANALYZER_STEPS = stepsFor("analyzer");

/**
 * The subjects a **group** analysis runs over: the distinct subjects the rows name, in row order
 * (`AnalyzerConfig.subject_ids`). In per-row mode each row is its own single-subject job, so this
 * is only the cohort's membership.
 */
export function cohortSubjects(rows: AnalyzerRow[]): string[] {
  return [...new Set(rows.filter(isRunnableAnalyzerRow).map((r) => r.subjectId))];
}

/**
 * A group analysis is one job over one simulation name in one space, measuring one field in one
 * ROI (`run_group_analysis` reads the same thing out of every subject's derivatives), so rows that
 * disagree are a state the page must refuse rather than silently resolve to the first row's answer.
 */
export function groupMismatchReason(rows: AnalyzerRow[]): string | null {
  const runnable = rows.filter(isRunnableAnalyzerRow);
  if (runnable.length === 0) return null;
  const sims = [...new Set(runnable.map((r) => r.simulation))];
  if (sims.length > 1) return `A group analysis runs one simulation — these rows name ${sims.join(", ")}.`;
  const spaces = [...new Set(runnable.map((r) => r.space))];
  if (spaces.length > 1) return "A group analysis runs in one space — these rows mix mesh and voxel.";
  const fields = [...new Set(runnable.map((r) => r.field))];
  if (fields.length > 1) return "A group analysis measures one field — these rows name more than one.";
  // Tissue only reaches the config in voxel space — the runner overwrites it with GM in mesh
  // (`tit/analyzer/analyzer.py`), so mesh rows that "disagree" build identical configs and refusing
  // them would be a refusal about nothing.
  if (spaces[0] === "voxel") {
    const tissues = [...new Set(runnable.map((r) => r.tissue))];
    if (tissues.length > 1) return "A group analysis measures one tissue — these rows name more than one.";
  }
  // Since the target became a row's own (maintainer, 2026-09-06), a cohort needs the rows to agree
  // about it too — the one ROI the group job is given.
  const lead = runnable[0] as AnalyzerRow;
  if (runnable.some((r) => !sameTarget(lead, r)))
    return "A group analysis measures one target — these rows name more than one.";
  return null;
}

/**
 * The `AnalyzerConfig`-shaped targets one row expands into.
 *
 * A row owns **one** ROI, and normally is one config. Two cases fan out, both 2.5.0's own
 * semantics: `AnalyzerConfig.center`/`.radius` are a single point, so N sphere rows are N separate
 * analyses (`build_single_analysis_commands`, never a union); and with "Combine regions into one
 * ROI" unchecked, each selected region is its own analysis.
 */
export function rowTargets(row: AnalyzerRow): RoiValue[] {
  const roi = row.roi;
  if (roi.mode === "spherical") return roi.spheres.map((s) => ({ ...roi, spheres: [s] }));
  if (roi.mode === "cortical" || roi.mode === "subcortical") {
    if (row.combine || roi.regions.length <= 1) return [roi];
    return roi.regions.map((r) => ({ ...roi, regions: [r] }));
  }
  return [roi];
}

export function AnalyzerPage() {
  const navigate = useNavigate();
  const { id: shellSubject, subjects } = useSubject();
  /*
   * 2026-09-06 jobs rework (maintainer): "we need a list of jobs in a table that allows users
   * flexibility in what they input to the job", then "we can modify our analysis input per job".
   * The page-level Subjects table, the Simulation combobox and the TARGET section are gone — a ROW
   * names its subject, its simulation, its space, its field and its target.
   *
   * `usePageSession` for what the user chose (lane N2): this page unmounts on every navigation.
   */
  const [rows, setRows] = usePageSession<AnalyzerRow[]>("jobRows", []);
  const [group, setGroup] = usePageSession("group", false);
  const [activeRowId, setActiveRowId] = usePageSession<string | null>("activeRow", null);
  const [overwrite, setOverwrite] = usePageSession("overwrite", false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  /**
   * Specs the server refused on the last Run press — what the next press retries (UI-05). Tagged
   * with the specs serialisation it belongs to, so editing the rows retires it without an effect
   * that sets state during render.
   */
  const [retry, setRetry] = useState<{ key: string; specs: AnalyzerJobSpec[] }>({ key: "", specs: [] });
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);

  // One simulation query per project subject — the Simulation cell's options, and the readiness
  // the row's Subject cell states.
  const subjectSimQueries = useQueries({
    queries: subjects.map((s) => ({
      queryKey: ["simulations", s.id],
      queryFn: () => getSimulationDetails(s.id),
      staleTime: 60_000,
    })),
  });
  // Derived every render rather than memoized: `useQueries` hands back a fresh array each render,
  // so a `useMemo` over it cannot preserve identity — this is a map over a project's few subjects.
  const detailsFor = (subjectId: string) => {
    const i = subjects.findIndex((s) => s.id === subjectId);
    return subjectSimQueries[i]?.data ?? [];
  };
  const jobSubjects: AnalyzerSubject[] = subjects.map((s) => {
    const sims = detailsFor(s.id).map((d) => d.name);
    return { id: s.id, simulations: sims, blockedReason: sims.length > 0 ? undefined : "no simulations" };
  });
  const fieldsFor = (subjectId: string, simulation: string): string[] =>
    detailsFor(subjectId).find((d) => d.name === simulation)?.fields ?? [];

  // The table starts with one row on the shell's primary subject, so the page's first act is
  // choosing a simulation rather than discovering an "Add row" button.
  const [seeded, setSeeded] = useState(false);
  if (!seeded && rows.length === 0 && subjects.length > 0) {
    setSeeded(true);
    const first = emptyAnalyzerRow({ subjectId: shellSubject ?? subjects[0]?.id ?? "" });
    setRows([first]);
    setActiveRowId(first.id);
  }

  const runnableRows = rows.filter(isRunnableAnalyzerRow);
  const cohort = cohortSubjects(rows);
  const firstRow = runnableRows[0];
  const primarySubjectId = firstRow?.subjectId ?? rows[0]?.subjectId ?? null;
  // The row the 3-D pane draws and the pane's clicks edit — the Simulator's idiom, here for the
  // target. Falls back to the first row so a pane is never showing nothing while rows exist.
  const activeRow = rows.find((r) => r.id === activeRowId) ?? rows[0] ?? null;
  const effectiveSubjectIds = group ? cohort : runnableRows.map((r) => r.subjectId);

  function setRows2(next: AnalyzerRow[]) {
    setRows(next);
  }

  /** Patches the ACTIVE row's ROI — the writer the 3-D pane's region/atlas picks go through. */
  function patchActiveRoi(roi: RoiValue) {
    if (!activeRow) return;
    setRows(rows.map((r) => (r.id === activeRow.id ? { ...r, roi } : r)));
  }

  // Every runnable row must carry a complete target of its own; the disabled Run says which.
  const incompleteTargetRow = runnableRows.find((r) => !isRoiComplete(r.roi));
  const targetReady = runnableRows.length > 0 && incompleteTargetRow === undefined;
  const groupMismatch = group ? groupMismatchReason(rows) : null;
  const plannableRows = rows.filter(isPlannableAnalyzerRow);
  const configsValid = plannableRows.length > 0 && targetReady && !groupMismatch;

  /**
   * One `AnalyzerConfig` per (row × target) — the row's own ROI, expanded by `rowTargets`. In
   * group mode the rows are the cohort instead: the lead row's target (every row shares it, or
   * `groupMismatchReason` refuses), carrying every row's subject in `subject_ids`.
   *
   * Derived on every render rather than memoized (the precedent `RunControls.tsx`'s `useSimPlan`
   * set): the rows are derived arrays, so a `useMemo` over them could only be keyed on a
   * serialisation — which React Compiler correctly refuses to treat as preserved memoization. The
   * debounce below is keyed on that serialisation instead, which is where identity actually
   * matters.
   */
  const configs: AnalyzerConfig[] = !configsValid
    ? []
    : (() => {
        const make = (row: AnalyzerRow, roi: RoiValue) =>
          buildConfig({
            mode: group ? "group" : "single",
            subjectId: group ? null : row.subjectId,
            subjectIds: group ? cohort : [],
            simulation: row.simulation,
            space: row.space,
            tissueType: row.tissue,
            field: row.field,
            analysisType: roi.mode as AnalysisType,
            coordinateSpace:
              roi.mode === "spherical" ? roi.space : roi.mode === "subcortical" ? roi.atlasSpace : "subject",
            roiValue: roi,
            sphere: roi.mode === "spherical" ? (roi.spheres[0] ?? EMPTY_SPHERE) : EMPTY_SPHERE,
          });
        if (group) {
          const lead = plannableRows[0];
          return lead ? rowTargets(lead).map((roi) => make(lead, roi)) : [];
        }
        return plannableRows.flatMap((row) => rowTargets(row).map((roi) => make(row, roi)));
      })();

  /**
   * Every config with the subjects IT runs over: one row's own subject per job, or the whole
   * cohort on each of a group run's configs.
   */
  const jobSpecs: AnalyzerJobSpec[] = configs.map((config) => ({
    config,
    subjectIds: group ? cohort : [config.subject_id as string],
  }));

  /*
   * Debounced plan, per DESIGN.md's Plan panel ("POST /api/plan/{kind} on debounce") — debounced on
   * the SERIALISATION, not on the array. `configs` is rebuilt every render, so debouncing its
   * identity would re-arm the timer on the render its own resolution caused and never settle.
   */
  const specsKey = useDebounced(JSON.stringify(jobSpecs), 400);
  const debouncedSpecs = useMemo(() => JSON.parse(specsKey) as AnalyzerJobSpec[], [specsKey]);
  const debouncedOverwrite = useDebounced(overwrite, 400);
  const plan = useQuery({
    queryKey: ["analyzer-plan", specsKey, debouncedOverwrite],
    queryFn: () => planAnalyzerBatch(debouncedSpecs, debouncedOverwrite),
    enabled: debouncedSpecs.length > 0,
  });

  async function runNow(replace = overwrite) {
    setRunning(true);
    try {
      const tag = newAnalysisTag();
      // Retry only what was refused last time: re-submitting the accepted ones would run them
      // twice (audit UI-05). `allSettled`, not `all`, so one rejection cannot hide the jobs that
      // WERE accepted — the receipt names both halves.
      const specs = retry.key === specsKey && retry.specs.length > 0 ? retry.specs : jobSpecs;
      const outcome = await submitBatch(specs, (spec) =>
        submitAnalyzerJob(spec.config, spec.subjectIds, replace, [tag]),
      );
      setRetry({ key: specsKey, specs: outcome.rejected.map((entry) => entry.spec) });
      const receipt = batchReceipt(outcome);
      if (outcome.rejected.length === 0) notify.success(receipt);
      else notify.error(receipt);
    } catch {
      notify.error("Could not queue the analysis job(s).");
    } finally {
      setRunning(false);
    }
  }

  function handleRunClick() {
    if (!configsValid) {
      notify.error(blockedReason ?? "Complete the rows and the target before running.");
      return;
    }
    // The one existing-outputs question (C3) — this page used to have none of its own wording at
    // all past a two-button overwrite alert, and no way to run only the new jobs.
    if (!overwrite && counts.existing > 0) {
      setConfirmOpen(true);
      return;
    }
    void runNow();
  }

  function openInViewer() {
    // D3: Freeview is gone; this deep-links into the embedded Tetravox viewer instead,
    // reusing pages/results' ViewerLink query-key convention (kind/subject/simulation/field
    // only -- unlike the old Freeview call, there is no `space` query key to request the MNI
    // template directly, so an MNI-coordinate spherical target opens the same subject-space
    // scene the viewer's own space toggle can switch from there).
    if (!primarySubjectId) return;
    navigate({
      pathname: "/viewer",
      search: viewerSearch({ subject: primarySubjectId, kind: "subject" }),
    });
  }

  const runLabel = configs.length > 1 ? `Queue ${configs.length} jobs` : "Run analysis";

  const blockedReason = blockedReasonFor({
    // The subject clause is still the shared grammar's, but it is now about the subjects the ROWS
    // name rather than a page-level tick list (J3 wording, unchanged).
    subjectsBlocked: subjectsBlockedReason(
      effectiveSubjectIds,
      effectiveSubjectIds
        .map((id) => ({ id, reason: jobSubjects.find((s) => s.id === id)?.blockedReason }))
        .filter((b): b is { id: string; reason: string } => !!b.reason),
    ),
    rowCount: runnableRows.length,
    groupMismatch,
    targetReady,
  });

  // Derived on every render rather than memoized: `effectiveSubjectIds` is itself derived from the
  // rows, so a `useMemo` here could only be keyed on a serialisation. `planModelFrom` is a fold
  // over at most a few dozen plan jobs.
  const planModel: PlanModel | null =
    blockedReason || !plan.data
      ? null
      : planModelFrom("analyzer", plan.data as unknown as SharedPlanResult, effectiveSubjectIds);

  const counts = planCounts(planModel);

  useRunShortcut(handleRunClick);

  const digest = planModel ? planDigest(planModel) : (blockedReason ?? "Resolving the plan…");

  /*
   * The scene pane in `inspect` mode (plan §2.4): the ACTIVE ROW's target is drawn where it will
   * be measured, and a click in the pane edits that row's regions — the same `onRegionsChange` /
   * `onAtlasChange` writers, now pointed at one row rather than at a page-level ROI.
   */
  const activeRoi = activeRow?.roi;
  const sceneCortical = activeRoi?.mode === "cortical";
  const scenePane = usePaneController({ pageId: "analyzer", name: "run" });
  const sceneNote = sceneCortical
    ? undefined
    : activeRoi?.mode === "spherical"
      ? activeRoi.space === "subject"
        ? undefined
        : "Coordinates are typed, not picked — the pane draws the reference guide, not this subject."
      : "Subcortical targets are volumetric — the preview shows the head model, not the label volume.";

  return (
    // No page header: the nav rail already says which page this is (DESIGN.md §2.3).
    <PageLayout
      variant="run"
      rightPaneKind="run"
      paneController={scenePane}
      rightPane={
        <RunPanel
          kind="analyzer"
          plan={planModel}
          loading={plan.isPending && plan.fetchStatus !== "idle"}
          refetching={plan.isRefetching}
          error={plan.error ? "Could not resolve the plan for this configuration." : undefined}
          onRefetch={() => void plan.refetch()}
          subjects={effectiveSubjectIds}
          emptyMessage={blockedReason ?? "Pick a simulation to analyze."}
          pinnedJobId={pinnedJobId}
          onPinJob={setPinnedJobId}
          steps={ANALYZER_STEPS}
          paneControls={<PaneHeaderControls controller={scenePane} />}
          scene={
            <ScenePane
              mode="inspect"
              atlas={sceneCortical && activeRoi.mode === "cortical" ? (activeRoi.atlas ?? null) : null}
              regions={sceneCortical && activeRoi.mode === "cortical" ? activeRoi.regions : undefined}
              onAtlasChange={
                sceneCortical
                  ? (atlas) => patchActiveRoi({ ...(activeRoi as Extract<RoiValue, { mode: "cortical" }>), atlas })
                  : undefined
              }
              onRegionsChange={
                sceneCortical
                  ? (regions) => patchActiveRoi({ ...(activeRoi as Extract<RoiValue, { mode: "cortical" }>), regions })
                  : undefined
              }
              note={sceneNote}
            />
          }
        />
      }
      actionBar={
        <ActionBar
          digest={digest}
          blocked={!!blockedReason}
          primary={
            <Button
              variant="primary"
              loading={running}
              disabled={!!blockedReason}
              onClick={handleRunClick}
              data-testid="run-button"
              title={blockedReason ?? undefined}
            >
              {runLabel}
            </Button>
          }
        />
      }
    >
      <RunWork>
        {/*
         * JOBS (2026-09-06 rework): the one table where the analysis is described, first on the
         * page and `data-tier="1"` (§8 — never closed by `RunWork`'s fill controller). A row names
         * its own subject, simulation, space, field and TARGET, which is 2.5.0's Subject ×
         * Simulation pair table with every per-job choice folded in.
         *
         * It is deliberately not wrapped in a plain `FormSection` alone for the fill controller's
         * sake — the `data-tier="1"` box is what keeps it out of the oscillation lane UC measured.
         */}
        <div data-tier="1">
          <FormSection title="Jobs" summary={analyzerJobsSummary(rows, group)}>
            <div style={{ gridColumn: "1 / -1" }}>
              {subjects.length === 0 ? (
                <EmptyState
                  message="No subjects in this project yet."
                  actionLabel="Go to Simulator"
                  onAction={() => navigate("/simulator")}
                />
              ) : (
                <AnalyzerJobRows
                  subjects={jobSubjects}
                  rows={rows}
                  onRowsChange={setRows2}
                  fieldsFor={fieldsFor}
                  group={group}
                  onGroupChange={setGroup}
                  activeRowId={activeRow?.id ?? null}
                  onActiveRowChange={setActiveRowId}
                  onOpenViewer={primarySubjectId ? openInViewer : undefined}
                />
              )}
            </div>
            {groupMismatch && (
              <div style={{ gridColumn: "1 / -1" }}>
                <Callout kind="warning">{groupMismatch}</Callout>
              </div>
            )}
            {!groupMismatch && incompleteTargetRow && (
              <div style={{ gridColumn: "1 / -1" }}>
                <Callout kind="warning">
                  {`${incompleteTargetRow.subjectId} · ${incompleteTargetRow.simulation} has no target yet — open its Target cell to choose one.`}
                </Callout>
              </div>
            )}
          </FormSection>
        </div>

      </RunWork>

      <ExistingOutputsDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        existing={counts.existing}
        total={counts.jobs}
        noun="analysis output"
        busy={running}
        onDecide={(decision) => {
          setConfirmOpen(false);
          if (decision === "replace") setOverwrite(true);
          void runNow(decision === "replace");
        }}
      />
    </PageLayout>
  );
}

/**
 * Why the plan cannot resolve, in the order the form asks for it. The action bar prints this
 * verbatim and the primary carries it as a tooltip — never a silently disabled button
 * (DESIGN.md §4.2 rule 8).
 */
export function blockedReasonFor(state: {
  subjectsBlocked: string | null;
  /** Rows that name both a subject and a simulation. */
  rowCount: number;
  /** Group mode over rows that disagree about simulation, space, field or target. */
  groupMismatch?: string | null;
  /** Every runnable row carries a complete target of its own. */
  targetReady: boolean;
}): string | null {
  // The table is what is empty, so that is what the button says — before the subject grammar's
  // "select at least one subject", which is not the truth about a page with no rows.
  if (state.rowCount === 0) return "Add a row with a subject and a simulation.";
  // The subject clause is the grammar's own (`pages/_shared/subjects`), so "no subject" and "this
  // subject cannot run" read identically here and on the other three run pages (J3).
  if (state.subjectsBlocked) return state.subjectsBlocked;
  if (state.groupMismatch) return state.groupMismatch;
  if (!state.targetReady) return "Complete the target before running.";
  return null;
}
