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
import { Combobox } from "../../ui/Combobox";
import { Button } from "../../ui/Button";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { useSubject } from "../../app/subjectContext";
import { usePageSession } from "../../app/pageSession";
import { SubjectsField, blockedSubjects, subjectsBlockedReason, type SubjectColumn } from "../_shared/subjects";
import { ExistingOutputsDialog, planCounts, RunPanel, RunWork, planDigest, planModelFrom, stepsFor, useRunShortcut, type PlanModel, type PlanResult as SharedPlanResult } from "../_shared/run";
import {
  RoiPicker,
  emptyRoi,
  isRoiComplete,
  type RoiMode,
  type RoiValue,
} from "../_shared/roi";
import { ScenePane } from "../_shared/scene";
import {
  FIELD_REGISTRY,
  TI_NORMAL_VOXEL_HELP,
  fieldSpecForName,
} from "./fields";
import { EMPTY_SPHERE, SphereRows, type Sphere } from "./SphereRows";
import { ResultsPanel } from "./ResultsPanel";
import { viewerSearch } from "../results";
import {
  AUTO_FIELD,
  buildConfig,
  sphereComplete,
  type Mode,
  type Space,
  type AnalysisType,
} from "./buildConfig";
import {
  getSimulationDetails,
  planAnalyzerBatch,
  submitAnalyzerJob,
  type AnalyzerConfig,
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
 * U16: mirrors `pages/simulator/index.tsx`'s own `seedWithShellSubject` — U11 left
 * `useSubject().batch` with no writer, so this page's own Subjects table seeds itself from the
 * shell's primary subject (the command palette's "Change subject") by *adding* it, never by
 * fighting a subject the user has since unticked here.
 */
export function seedWithShellSubject(current: string[], shellSubject: string | null): string[] {
  if (!shellSubject || current.includes(shellSubject)) return current;
  return [shellSubject, ...current];
}

/**
 * `AnalyzerConfig.subject_id`/`.subject_ids` are mutually exclusive by mode (`buildConfig.ts`):
 * Subject mode analyzes exactly the first ticked subject; Group mode analyzes every ticked one.
 * Ticking a second subject without switching to Group must not silently multiply the job.
 */
export function effectiveSubjectIdsFor(mode: Mode, selected: string[]): string[] {
  if (mode === "single") return selected.length > 0 ? [selected[0] as string] : [];
  return selected;
}

export function AnalyzerPage() {
  const navigate = useNavigate();
  // U16: U11 deleted the context bar's own subject switcher, which was the only writer for
  // `useSubject().batch` — Subject mode used to read the shell's primary, Group mode its whole
  // (primary + batch) selection. Both now come from this page's own Subjects table instead,
  // seeded from the shell's primary subject.
  const { id: shellSubject, subjects } = useSubject();
  // `usePageSession` for what the user chose, `useState` for what is transient (lane N2): this
  // page unmounts on every navigation, so a plain `useState` reset the scope, the space, the ROI
  // and the sphere table each time they stepped away — the maintainer's "jumping between tabs
  // resets them". A confirm dialog and the in-flight `running` flag stay local.
  const [selected, setSelected] = usePageSession<string[]>("subjects", () => (shellSubject ? [shellSubject] : []));
  const [lastShellSubject, setLastShellSubject] = useState(shellSubject);
  if (shellSubject !== lastShellSubject) {
    setLastShellSubject(shellSubject);
    setSelected((prev) => seedWithShellSubject(prev, shellSubject));
  }
  const [mode, setModeState] = usePageSession<Mode>("mode", "single");
  const subjectIds = selected;
  const [simulation, setSimulation] = usePageSession<string>("simulation", "");
  const [space, setSpaceState] = usePageSession<Space>("space", "mesh");
  const [tissueType, setTissueType] = usePageSession("tissue", "GM");
  const [field, setField] = usePageSession<string>("field", AUTO_FIELD);
  const [analysisType, setAnalysisTypeState] =
    usePageSession<AnalysisType>("analysisType", "spherical");
  const [coordinateSpace, setCoordinateSpace] = usePageSession<"subject" | "mni">(
    "coordinateSpace",
    "subject",
  );
  const [spheres, setSpheres] = usePageSession<Sphere[]>("spheres", () => [{ ...EMPTY_SPHERE }]);
  const [roiValue, setRoiValue] = usePageSession<RoiValue>("roi", () => emptyRoi("cortical"));
  const [overwrite, setOverwrite] = usePageSession("overwrite", false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);

  const primarySubjectId = selected[0] ?? null;
  const effectiveSubjectIds = effectiveSubjectIdsFor(mode, subjectIds);
  const roiSpace: "subject" | "mni" = space === "mesh" ? "subject" : "mni";

  // Derived-field resets happen inside the setter that changes the driving field (matching
  // `optimizer-flex/index.tsx`'s `setRoi` pattern), not a `useEffect` watching it — one render,
  // no `react-hooks/set-state-in-effect` violation. Mirrors `update_atlas_visibility`'s
  // forced-GM-in-mesh (handled in `buildConfig` instead, since the Tissue control is simply
  // disabled rather than needing its value cleared) and cortical/spherical target reset.
  function setMode(next: Mode) {
    setModeState(next);
    if (next === "group" && spheres.length > 1)
      setSpheres((s) => [s[0] as Sphere]);
    // J4: Subject scope submits ONE job for ONE subject (`AnalyzerConfig.subject_id`). Narrowing
    // the ticked set here, visibly, is the honest form of what `effectiveSubjectIdsFor` used to do
    // silently on the way to the payload — a user could tick three subjects in Subject scope and
    // watch one analysis run.
    if (next === "single") setSelected((prev) => (prev.length > 1 ? [prev[0] as string] : prev));
  }
  function setSpace(next: Space) {
    setSpaceState(next);
    if (analysisType !== "spherical")
      setRoiValue(
        emptyRoi(analysisType as RoiMode, next === "mesh" ? "subject" : "mni"),
      );
  }
  function setAnalysisType(next: AnalysisType) {
    setAnalysisTypeState(next);
    if (next !== "spherical") setRoiValue(emptyRoi(next as RoiMode, roiSpace));
  }

  const simulations = useQuery({
    queryKey: ["simulations", primarySubjectId],
    queryFn: () => getSimulationDetails(primarySubjectId as string),
    enabled: primarySubjectId !== null,
  });
  const selectedSimulation = simulations.data?.find(
    (s) => s.name === simulation,
  );

  // Readiness for the Subjects table (U16): "has run the chosen simulation" — one query per
  // project subject, keyed the same as `simulations` above so the primary subject's row reuses
  // that same cache entry rather than fetching it twice.
  const subjectSimQueries = useQueries({
    queries: subjects.map((s) => ({
      queryKey: ["simulations", s.id],
      queryFn: () => getSimulationDetails(s.id),
      staleTime: 60_000,
    })),
  });
  // Derived on every render rather than memoized, matching `RunControls.tsx`'s own
  // `useSimPlan`: `useQueries` hands back a fresh array each render, so a `useMemo` keyed on it
  // cannot preserve identity anyway — this is a map over at most a project's few dozen subjects.
  const ranSimulation = (id: string): boolean => {
    const i = subjects.findIndex((s) => s.id === id);
    const names = subjectSimQueries[i]?.data?.map((d) => d.name) ?? [];
    // Before a simulation is picked, "ready" means "has run something to analyze"; once one is
    // picked, it means "has run *this* one" — the exact rule Group mode's own note states.
    return simulation ? names.includes(simulation) : names.length > 0;
  };
  const subjectColumns: SubjectColumn<{ id: string }>[] = [{ id: "sim", label: "sim", present: (s) => ranSimulation(s.id) }];
  const eligibility = (s: { id: string }) =>
    ranSimulation(s.id) ? { ok: true } : { ok: false, reason: simulation ? `has not run ${simulation}` : "no simulations" };

  const fieldOptions = useMemo(() => {
    const available =
      selectedSimulation?.fields ?? FIELD_REGISTRY.map((f) => f.name);
    return [
      // Radix Select reserves value="" to mean "no selection shown" (it renders the placeholder
      // instead of the item), so "Auto" needs a real sentinel string here.
      { value: AUTO_FIELD, label: "Auto (TI_max / mTI_max)" },
      ...available.map((name) => ({
        value: name,
        label: name,
        disabled: space === "voxel" && name === "TI_normal",
      })),
    ];
  }, [selectedSimulation, space]);

  const targetReady =
    analysisType === "spherical"
      ? spheres.length > 0 && spheres.every(sphereComplete)
      : isRoiComplete(roiValue);
  const configsValid =
    !!simulation && effectiveSubjectIds.length > 0 && targetReady;

  const configs: AnalyzerConfig[] = useMemo(() => {
    if (!configsValid) return [];
    const base = {
      mode,
      subjectId: primarySubjectId,
      subjectIds,
      simulation,
      space,
      tissueType,
      field,
      analysisType,
      coordinateSpace,
      roiValue,
    };
    if (analysisType === "spherical") {
      return spheres.map((sphere) => buildConfig({ ...base, sphere }));
    }
    return [buildConfig({ ...base, sphere: EMPTY_SPHERE })];
  }, [
    configsValid,
    mode,
    primarySubjectId,
    subjectIds,
    simulation,
    space,
    tissueType,
    field,
    analysisType,
    coordinateSpace,
    spheres,
    roiValue,
  ]);

  // Debounced plan, per DESIGN.md's Plan panel ("POST /api/plan/{kind} on debounce").
  const debouncedConfigs = useDebounced(configs, 400);
  const debouncedSubjectIds = useDebounced(effectiveSubjectIds, 400);
  const debouncedOverwrite = useDebounced(overwrite, 400);
  const plan = useQuery({
    queryKey: [
      "analyzer-plan",
      debouncedConfigs,
      debouncedSubjectIds,
      debouncedOverwrite,
    ],
    queryFn: () =>
      planAnalyzerBatch(
        debouncedConfigs,
        debouncedSubjectIds,
        debouncedOverwrite,
      ),
    enabled: debouncedConfigs.length > 0 && debouncedSubjectIds.length > 0,
  });

  async function runNow(replace = overwrite) {
    setRunning(true);
    try {
      const tag = `analysis:${Date.now()}`;
      await Promise.all(
        configs.map((cfg) =>
          submitAnalyzerJob(cfg, effectiveSubjectIds, replace, [tag]),
        ),
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
      notify.error(
        "Complete the subject, simulation, and target before running.",
      );
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
    subjectsBlocked: subjectsBlockedReason(effectiveSubjectIds, blockedSubjects(subjects, effectiveSubjectIds, eligibility)),
    simulation,
    targetReady,
  });

  const subjectsKey = effectiveSubjectIds.join(",");
  const planModel: PlanModel | null = useMemo(() => {
    if (blockedReason || !plan.data) return null;
    return planModelFrom("analyzer", plan.data as unknown as SharedPlanResult, subjectsKey ? subjectsKey.split(",") : []);
  }, [blockedReason, plan.data, subjectsKey]);

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
         * Subjects (J1/J2): the one shared control, first on the page, `data-tier="1"` (§8 — never
         * closed by `RunWork`'s fill controller, matching the contract `firstScreenControls`
         * reads). Not a `FormSection`: that primitive registers with the fill controller, which
         * was measured to oscillate this table open/closed once `ResultsPanel`'s content grew
         * after a simulation was picked.
         *
         * The mode is the page's scope: Subject = one job for one subject, Group = one job over
         * all of them (J4), and the control enforces whichever is current.
         */}
        <div data-tier="1">
          <SubjectsField
            subjects={subjects}
            value={selected}
            onChange={setSelected}
            columns={subjectColumns}
            eligibility={eligibility}
            mode={mode === "group" ? "grouped" : "single"}
            /* Open on first visit (R3), like every other subject-taking workflow — and unlike
               them, deliberately with NO `Subjects in parallel` control: a group analysis is one
               job over the whole cohort and a single-subject analysis is one job, so there is
               nothing to run N-at-a-time. */
            defaultOpen
          />
        </div>

        {selected.length === 0 ? (
          <EmptyState
            message={subjects.length === 0 ? "No subjects in this project yet." : "Select a subject above to analyze a simulation."}
            actionLabel={subjects.length === 0 ? "Go to Simulator" : undefined}
            onAction={subjects.length === 0 ? () => navigate("/simulator") : undefined}
          />
        ) : (
          <>
            <div data-tier="1">
              <FormSection title="Scope" summary={`${effectiveSubjectIds.join(", ") || "no subject"} · ${simulation || "no simulation"}`}>
                <Field label="Scope">
                  <SegmentedControl
                    value={mode}
                    onValueChange={(v) => setMode(v as Mode)}
                    options={[
                      { value: "single", label: "Subject" },
                      { value: "group", label: "Group" },
                    ]}
                    aria-label="Analysis scope"
                  />
                </Field>
                <Field
                  label="Simulation"
                  htmlFor="analyzer-simulation"
                  required
                  note={mode === "group" ? "Every selected subject must have run this simulation name." : undefined}
                >
                  <Combobox
                    id="analyzer-simulation"
                    value={simulation || undefined}
                    onValueChange={setSimulation}
                    options={(simulations.data ?? []).map((s) => ({ value: s.name, label: s.name }))}
                    placeholder={
                      primarySubjectId === null
                        ? "Choose a subject first"
                        : simulations.isPending
                          ? "Loading…"
                          : "Select a simulation…"
                    }
                    disabled={primarySubjectId === null}
                  />
                </Field>
                {simulations.isPending && primarySubjectId !== null && (
                  <div style={{ gridColumn: "1 / -1" }}>
                    <Skeleton rows={1} />
                  </div>
                )}
              </FormSection>
            </div>

            <div data-tier="1">
              <FormSection title="Space" summary={`${space} · ${space === "voxel" ? tissueType : "GM"} · ${field === AUTO_FIELD ? "auto" : field}`}>
                <Field label="Space">
                  <SegmentedControl
                    value={space}
                    onValueChange={(v) => setSpace(v as Space)}
                    options={[
                      { value: "mesh", label: "Mesh" },
                      { value: "voxel", label: "Voxel" },
                    ]}
                    aria-label="Analysis space"
                  />
                </Field>
                <Field label="Tissue" htmlFor="analyzer-tissue" help="Voxel space only.">
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
                <Field
                  label="Field"
                  htmlFor="analyzer-field"
                  help={fieldSpecForName(field)?.description ?? "Resolves to TI_max (TI) or mTI_max (mTI)."}
                  // Voxel space is why TI_normal is unavailable — a reason for a disabled option,
                  // so it is stated on the form rather than behind the (i) trigger.
                  note={space === "voxel" ? TI_NORMAL_VOXEL_HELP : undefined}
                >
                  <Select id="analyzer-field" value={field} onValueChange={setField} options={fieldOptions} />
                </Field>
              </FormSection>
            </div>

            <div data-tier="1">
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
                      allowMultiple={mode === "single"}
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
            </div>

            <FormSection title="Output" collapsible defaultOpen={false} summary="CSV + PDF report">
              <div style={{ gridColumn: "1 / -1" }}>
                <ResultsPanel subjectId={primarySubjectId} simulation={simulation || undefined} />
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
export function blockedReasonFor(state: { subjectsBlocked: string | null; simulation: string; targetReady: boolean }): string | null {
  // The subject clause is the grammar's own (`pages/_shared/subjects`), so "no subject" and "this
  // subject cannot run" read identically here and on the other three run pages (J3).
  if (state.subjectsBlocked) return state.subjectsBlocked;
  if (!state.simulation) return "Pick a simulation to analyze.";
  if (!state.targetReady) return "Complete the target before running.";
  return null;
}
