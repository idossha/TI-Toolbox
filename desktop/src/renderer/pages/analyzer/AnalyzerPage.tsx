/**
 * Analyzer page — parity source `tit/gui/analyzer_tab.py` (see PARITY.md). Single/group mode,
 * subject(s) + simulation, mesh/voxel space, field selector, spherical/cortical/subcortical
 * target, a Plan panel, and a Results section for the simulation's existing analyses.
 *
 * Uses plain component state rather than the react-hook-form + ajv infra: the config here is
 * really a *batch* of `AnalyzerConfig` objects (one per sphere row, see PARITY.md), which does
 * not map onto a single schema-validated form the way a one-shot Run screen does. Matches the
 * existing `pages/overview/index.tsx` precedent of plain `useState` for non-trivial screens.
 *
 * Cortical/subcortical targets reuse the shared `pages/_shared/roi` picker (P3), per the build
 * plan. Spherical does **not**: that picker's spherical mode unions multiple rows into one
 * combined `SphericalROI` (flex-search's semantics) — `AnalyzerConfig.center`/`.radius` are a
 * single point, and `tit/gui/analyzer_tab.py` runs N sphere rows as N *separate* analyses
 * (`build_single_analysis_commands`), never a union. Reusing the shared spherical panel here
 * would silently misrepresent what Run does, so this page keeps its own `SphereRows` for that
 * one mode (see PARITY.md and the report to the orchestrator).
 */
import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FormSection, PageLayout, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Field } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Toggle";
import { Button } from "../../ui/Button";
import { Callout, EmptyState } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { useSubject } from "../../app/subjectContext";
import { usePageSession } from "../../app/pageSession";
import { subjectsBlockedReason } from "../_shared/subjects";
import { ExistingOutputsDialog, planCounts, RunPanel, RunWork, planDigest, planModelFrom, stepsFor, useRunShortcut, type PlanModel, type PlanResult as SharedPlanResult } from "../_shared/run";
import {
  RoiPicker,
  emptyRoi,
  isRoiComplete,
  type RoiMode,
  type RoiValue,
} from "../_shared/roi";
import { ScenePane } from "../_shared/scene";
import { TI_NORMAL_VOXEL_HELP } from "./fields";
import {
  AnalyzerJobRows,
  analyzerJobsSummary,
  emptyAnalyzerRow,
  isRunnableAnalyzerRow,
  type AnalyzerRow,
  type AnalyzerSubject,
} from "./JobRows";
import { EMPTY_SPHERE, SphereRows, type Sphere } from "./SphereRows";
import { ResultsPanel } from "./ResultsPanel";
import { viewerSearch } from "../results";
import {
  buildConfig,
  sphereComplete,
  type Space,
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
 * A group analysis is one job over one simulation name (`run_group_analysis` reads the same
 * simulation out of every subject's derivatives), so rows that disagree are a state the page must
 * refuse rather than silently resolve to the first row's answer.
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
  return null;
}

export function AnalyzerPage() {
  const navigate = useNavigate();
  const { id: shellSubject, subjects } = useSubject();
  /*
   * 2026-09-06 jobs rework (maintainer): "we need a list of jobs in a table that allows users
   * flexibility in what they input to the job". The page-level Subjects table and the single
   * Simulation combobox are gone — a ROW names its subject, its simulation, its space and its
   * field, which is 2.5.0's Subject × Simulation pair table with the two per-job choices that had
   * no business being global folded in.
   *
   * `usePageSession` for what the user chose (lane N2): this page unmounts on every navigation.
   */
  const [rows, setRows] = usePageSession<AnalyzerRow[]>("jobRows", []);
  const [group, setGroup] = usePageSession("group", false);
  const [tissueType, setTissueType] = usePageSession("tissue", "GM");
  const [analysisType, setAnalysisTypeState] = usePageSession<AnalysisType>("analysisType", "spherical");
  const [coordinateSpace, setCoordinateSpace] = usePageSession<"subject" | "mni">("coordinateSpace", "subject");
  const [spheres, setSpheres] = usePageSession<Sphere[]>("spheres", () => [{ ...EMPTY_SPHERE }]);
  const [roiValue, setRoiValue] = usePageSession<RoiValue>("roi", () => emptyRoi("cortical"));
  const [overwrite, setOverwrite] = usePageSession("overwrite", false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
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
    setRows([emptyAnalyzerRow({ subjectId: shellSubject ?? subjects[0]?.id ?? "" })]);
  }

  const runnableRows = rows.filter(isRunnableAnalyzerRow);
  const cohort = cohortSubjects(rows);
  const firstRow = runnableRows[0];
  const primarySubjectId = firstRow?.subjectId ?? rows[0]?.subjectId ?? null;
  // In group mode every row shares one space (`groupMismatchReason` refuses otherwise), so the ROI
  // space is the first runnable row's; with no rows yet it is mesh's subject space.
  const space: Space = firstRow?.space ?? "mesh";
  const roiSpace: "subject" | "mni" = space === "mesh" ? "subject" : "mni";
  const effectiveSubjectIds = group ? cohort : runnableRows.map((r) => r.subjectId);

  // Derived-field resets happen inside the setter that changes the driving field, not a
  // `useEffect` watching it — one render, no `react-hooks/set-state-in-effect` violation.
  function setAnalysisType(next: AnalysisType) {
    setAnalysisTypeState(next);
    if (next !== "spherical") setRoiValue(emptyRoi(next as RoiMode, roiSpace));
  }
  function setRows2(next: AnalyzerRow[]) {
    setRows(next);
    // A row switching to voxel moves the ROI into MNI space and back — the same reset the old
    // page-level Space segment did, driven by the rows that now own the choice.
    const nextSpace = next.filter(isRunnableAnalyzerRow)[0]?.space ?? "mesh";
    if (nextSpace !== space && analysisType !== "spherical") {
      setRoiValue(emptyRoi(analysisType as RoiMode, nextSpace === "mesh" ? "subject" : "mni"));
    }
  }
  // Group mode analyses one cohort with one sphere: N sphere rows are N separate single-subject
  // analyses in 2.5.0 and cannot be folded into a cohort job.
  function setGroupMode(next: boolean) {
    setGroup(next);
    if (next && spheres.length > 1) setSpheres((s) => [s[0] as Sphere]);
  }

  const targetReady =
    analysisType === "spherical"
      ? spheres.length > 0 && spheres.every(sphereComplete)
      : isRoiComplete(roiValue);
  const groupMismatch = group ? groupMismatchReason(rows) : null;
  const configsValid = runnableRows.length > 0 && targetReady && !groupMismatch;

  /**
   * One `AnalyzerConfig` per (row × sphere) — 2.5.0's `build_single_analysis_commands`, where N
   * sphere rows are N *separate* analyses and never a union. In group mode the rows are the cohort
   * instead: one config per sphere, carrying every row's subject in `subject_ids`.
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
        const targets = analysisType === "spherical" ? spheres : [EMPTY_SPHERE];
        const make = (row: AnalyzerRow, sphere: Sphere) =>
          buildConfig({
            mode: group ? "group" : "single",
            subjectId: group ? null : row.subjectId,
            subjectIds: group ? cohort : [],
            simulation: row.simulation,
            space: row.space,
            tissueType,
            field: row.field,
            analysisType,
            coordinateSpace,
            roiValue,
            sphere,
          });
        if (group) {
          const lead = runnableRows[0];
          return lead ? targets.map((sphere) => make(lead, sphere)) : [];
        }
        return runnableRows.flatMap((row) => targets.map((sphere) => make(row, sphere)));
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
      await Promise.all(
        jobSpecs.map((spec) => submitAnalyzerJob(spec.config, spec.subjectIds, replace, [tag])),
      );
      notify.success(
        configs.length === 1
          ? "Queued: analysis"
          : `Queued: ${configs.length} analyses`,
      );
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
   * The scene pane in `inspect` mode (plan §2.4): the ROI is drawn **where it will be measured**,
   * and the only thing a click may change is the sphere centre.
   *
   * Read-only for regions on purpose — an Analyzer run measures a simulation that already exists,
   * so the pane's job here is to let a user see that the region they typed is the region they
   * meant, not to be a second region editor. The sphere gesture is offered only in subject space
   * and only for the first row: the scene's coordinates are this subject's own millimetres, and an
   * MNI field written from them would be wrong by the whole template transform.
   */
  const sceneCortical = analysisType === "cortical" && roiValue.mode === "cortical";
  const sceneSpherical = analysisType === "spherical";
  const scenePane = usePaneController({ pageId: "analyzer", name: "run" });
  const sceneNote = sceneCortical
    ? undefined
    : sceneSpherical
      ? coordinateSpace === "subject"
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
              atlas={sceneCortical && roiValue.mode === "cortical" ? (roiValue.atlas ?? null) : null}
              regions={sceneCortical && roiValue.mode === "cortical" ? roiValue.regions : undefined}
              onAtlasChange={
                sceneCortical
                  ? (atlas) => setRoiValue({ ...(roiValue as Extract<RoiValue, { mode: "cortical" }>), atlas })
                  : undefined
              }
              onRegionsChange={
                sceneCortical
                  ? (regions) => setRoiValue({ ...(roiValue as Extract<RoiValue, { mode: "cortical" }>), regions })
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
         * page and `data-tier="1"` (§8 — never closed by `RunWork`'s fill controller). It replaces
         * the page-level Subjects table, the Scope segment and the single Simulation combobox: a
         * row names its own subject, simulation, space and field, which is 2.5.0's Subject ×
         * Simulation pair table with "+ Add Pair" and "Quick Add".
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
                <AnalyzerJobRows subjects={jobSubjects} rows={rows} onRowsChange={setRows2} fieldsFor={fieldsFor} />
              )}
            </div>
            <Field
              label="Combine"
              help="One cohort analysis over every row's subject (run_group_analysis), instead of one job per row."
            >
              <label className="checkbox-label-row">
                <Switch checked={group} onCheckedChange={setGroupMode} aria-label="Combine into one group analysis" />
                Combine into one group analysis
              </label>
            </Field>
            {groupMismatch && (
              <div style={{ gridColumn: "1 / -1" }}>
                <Callout kind="warning">{groupMismatch}</Callout>
              </div>
            )}
          </FormSection>
        </div>

        {subjects.length > 0 && (
          <>
            <FormSection
              title="Space options"
              collapsible
              defaultOpen={false}
              summary={space === "voxel" ? `voxel · ${tissueType}` : "mesh · GM"}
            >
              <Field
                label="Tissue"
                htmlFor="analyzer-tissue"
                help="Voxel space only — mesh analyses are gray matter."
                // Voxel space is why TI_normal is unavailable in a row's Field cell — a reason for
                // a disabled option, so it is stated on the form rather than behind an (i).
                note={space === "voxel" ? TI_NORMAL_VOXEL_HELP : undefined}
              >
                <Select
                  id="analyzer-tissue"
                  value={tissueType}
                  onValueChange={setTissueType}
                  disabled={space === "mesh"}
                  options={[
                    { value: "GM", label: "Gray matter (GM)" },
                    { value: "WM", label: "White matter (WM)" },
                    { value: "both", label: "GM + WM (both)" },
                  ]}
                />
              </Field>
            </FormSection>

            <FormSection title="Target" summary={analysisType}>
                <Field label="Region">
                  <SegmentedControl
                    value={analysisType}
                    onValueChange={(v) => setAnalysisType(v as AnalysisType)}
                    options={[
                      { value: "cortical", label: "Cortical" },
                      { value: "subcortical", label: "Subcortical" },
                      { value: "spherical", label: "Spherical" },
                    ]}
                    aria-label="Target region type"
                  />
                </Field>
                <div style={{ gridColumn: "1 / -1" }}>
                  {analysisType === "subcortical" && (
                    <Callout kind="warning" title="Not yet implemented">
                      Subcortical analysis is accepted by the config but the analyzer runner only handles spherical and
                      cortical targets today — a submitted job will complete without producing output. Tracked as a known
                      backend gap (see PARITY.md).
                    </Callout>
                  )}
                  {analysisType === "spherical" ? (
                    <SphereRows
                      spheres={spheres}
                      onSpheresChange={setSpheres}
                      coordinateSpace={coordinateSpace}
                      onCoordinateSpaceChange={setCoordinateSpace}
                      allowMultiple={!group}
                      onOpenViewer={primarySubjectId ? openInViewer : undefined}
                    />
                  ) : (
                    <RoiPicker
                      value={roiValue}
                      onChange={setRoiValue}
                      modes={[analysisType]}
                      subject={primarySubjectId ?? undefined}
                      space={roiSpace}
                    />
                  )}
                </div>
            </FormSection>

            <FormSection title="Output" collapsible defaultOpen={false} summary="CSV + PDF report">
              <div style={{ gridColumn: "1 / -1" }}>
                <ResultsPanel subjectId={primarySubjectId} simulation={firstRow?.simulation || undefined} />
              </div>
            </FormSection>
          </>
        )}
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
  /** Group mode over rows that disagree about simulation, space or field. */
  groupMismatch?: string | null;
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
