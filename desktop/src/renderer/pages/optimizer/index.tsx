/**
 * Optimizer — one page for all three searches (program U7, DESIGN.md v3 §9). `optimizer-flex` and
 * `optimizer-ex` were two nav entries copied from the PyQt tab strip, not two workflows: both ask
 * "where do the electrodes go for this target", and both end in one job on the same rail. A
 * `Method ⟨Flex │ Ex │ mEx⟩` segment is the first row of the work pane, one shared `RoiPicker`
 * serves all three, and the right pane is the shared `RunPanel` with the segment's kind.
 *
 * Every control of both predecessors is accounted for in `PARITY.md`, including the ones that
 * moved to another page or were deliberately dropped.
 */
import { useEffect, useMemo, useState } from "react";
import { Target } from "lucide-react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { Subject } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { useSubject } from "../../app/subjectContext";
import { useExecutionPrefs } from "../../app/executionPrefs";
import { usePageSession } from "../../app/pageSession";
import { useStatusCells } from "../../app/statusCells";
import { useJobsStream } from "../../app/jobs/useJobsStream";
import { PageLayout, FormSection, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { Button } from "../../ui/Button";
import { Field, TextInput } from "../../ui/Field";
import { SegmentedControl } from "../../ui/SegmentedControl";

import { Callout } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { RoiPicker, emptyRoi, roiToConfig, getAtlases, type Atlas, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { SubjectsField, blockedSubjects, presenceColumns, subjectsBlockedReason, type SubjectColumn } from "../_shared/subjects";
import {
  RunPanel,
  RunWork,
  Receipt,
  receiptFrom,
  ExistingOutputsDialog,
  planDigest,
  planModelFrom,
  stepsFor,
  submitJobGroup,
  useRunShortcut,
  type GroupKind,
  type PlanKind,
  type PlanModel,
  type PlanResult,
} from "../_shared/run";
import { ScenePane } from "../_shared/scene";
import { viewerSearch } from "../results";
import { getEegNets, getLeadfields, planFor, submitLeadfieldJob, validateFor, type FlexConfigWire, type Leadfield } from "./api";
import { buildFlexConfig, defaultFlexFormState, flexSubmissions, jobKindFor, type FlexFormState } from "./flexConfig";
import {
  buildExConfig,
  buildMExConfig,
  defaultExFormState,
  defaultMExFormState,
  exSubmissions,
  exTargets,
  EX_BUCKET_KEYS,
  MEX_BUCKET_KEYS,
  type ExFormState,
  type MExFormState,
} from "./exConfig";
import { defaultNet as defaultNetFor, electrodesForNet, leadfieldPathFor } from "./nets";
import { exCost, flexCost, mexCost } from "./cost";
import { ElectrodesSection, ObjectiveSection, PostRunSection, SolverSection } from "./FlexSections";
import { ExCurrentSection, ExElectrodesSection, LeadfieldStrip, MExCarrierSection, MExElectrodesSection } from "./ExSections";
import "./optimizer.css";

export type Method = "flex" | "ex" | "mex";

const METHOD_OPTIONS: { value: Method; label: string; title: string }[] = [
  { value: "flex", label: "Flex", title: "Differential-evolution search over free electrode positions" },
  { value: "ex", label: "Ex", title: "Exhaustive two-channel search over a precomputed leadfield" },
  { value: "mex", label: "mEx", title: "Exhaustive four-pair (mTI) search over a precomputed leadfield" },
];

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

/**
 * Resolves an atlas id to its path for `roiToConfig` / `exTargets`, **per subject**, from the same
 * query key the picker uses internally — a cache hit for the primary subject, not a second request.
 *
 * Per subject, not once: an atlas id (`"aparc.DKTatlas+aseg.mgz"`, `"DK40"`) is the same string for
 * every subject but its path is not (`derivatives/freesurfer/sub-<id>/mri/…`). Since U16 a run page
 * can queue the same optimisation for several subjects, so resolving the path once for the primary
 * and reusing it would point every job in the batch at the first subject's anatomy.
 */
interface AtlasLookups {
  /** The per-subject atlas resolver `roiToConfig` / `exTargets` take. */
  lookup: (subject: string) => (atlas: string) => AtlasLookup | undefined;
  /** True once this subject's atlas list has actually landed. A readiness column must not call a
   *  subject "no target" while its own query is still in flight. */
  ready: (subject: string) => boolean;
}

function useAtlasLookups(subjects: string[], value: RoiValue): AtlasLookups {
  const kind = value.mode === "cortical" ? "cortical" : value.mode === "subcortical" ? "subcortical" : undefined;
  const space = value.mode === "subcortical" ? value.atlasSpace : undefined;
  const results = useQueries({
    queries: subjects.map((subject) => ({
      queryKey: kind === "subcortical" ? ["atlases", subject, "subcortical", space] : ["atlases", subject, "cortical"],
      queryFn: () => getAtlases(subject, kind as "cortical" | "subcortical", space),
      enabled: kind !== undefined,
    })),
  });
  const bySubject: Record<string, Atlas[] | undefined> = {};
  const readyBySubject: Record<string, boolean> = {};
  subjects.forEach((subject, i) => {
    bySubject[subject] = results[i]?.data;
    readyBySubject[subject] = results[i]?.isSuccess === true;
  });
  return {
    lookup: (subject: string) => (atlasId: string) => bySubject[subject]?.find((a) => a.id === atlasId),
    ready: (subject: string) => readyBySubject[subject] === true,
  };
}

/**
 * Merge one plan per ex/mEx target into a single `PlanResult`, so one grid shows every run the
 * press of Run will queue — the columns become the **targets**, which is what an optimizer has
 * instead of stages.
 *
 * Each job is stamped with its target's name in `PlanJob.label`, the field `stageIdOf` reads
 * before falling back to `basename(output_dir)`. Without it the column id would be the resolved
 * run directory, which is the same string for every target until a run name is typed — a
 * three-target plan would collapse into one column and under-report what Run will queue.
 */
function mergePlanResults(sources: { label: string; result: PlanResult | undefined }[]): PlanResult | undefined {
  const present = sources.filter((s): s is { label: string; result: PlanResult } => s.result !== undefined);
  if (present.length === 0) return undefined;
  const first = present[0] as { label: string; result: PlanResult };
  return {
    ...first.result,
    jobs: present.flatMap((s) => s.result.jobs.map((j) => ({ ...j, label: s.label }))),
    lock_conflicts: present.flatMap((s) => s.result.lock_conflicts ?? []),
    warnings: Array.from(new Set(present.flatMap((s) => s.result.warnings ?? []))),
  };
}

function OptimizerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: shellSubject, selection, subjects: projectSubjects } = useSubject();
  const stream = useJobsStream();

  // `usePageSession` for everything the user decided, `useState` for what is transient (lane N2):
  // the page unmounts on every navigation, so a plain `useState` threw away the method, the ROI
  // and the typed run name the moment they looked at Results. A confirm dialog and a stale
  // validation list are not "where they left off" and stay local.
  const [method, setMethod] = usePageSession<Method>("method", "flex");
  const [runName, setRunName] = usePageSession("runName", "");
  const [overwrite, setOverwrite] = usePageSession("overwrite", false);
  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);
  const scenePane = usePaneController({ pageId: "optimizer", name: "run" });

  // One ROI value per method family: switching Flex ↔ Ex must not silently discard a target the
  // other method cannot express (a saved CSV is not a sphere table), and switching back restores it.
  const [flexRoi, setFlexRoiState] = usePageSession<RoiValue>("flexRoi", () => emptyRoi("cortical"));
  const [nonRoi, setNonRoi] = usePageSession<RoiValue>("nonRoi", () => emptyRoi("cortical"));
  const [exRoi, setExRoi] = usePageSession<RoiValue>("exRoi", () => emptyRoi("saved"));
  function setFlexRoi(next: RoiValue) {
    setFlexRoiState(next);
    // Parity `_sync_nonroi_mode`: keep the non-ROI picker on the ROI's mode, in one render.
    setNonRoi((prev) => (prev.mode === next.mode ? prev : emptyRoi(next.mode)));
  }

  const [flexForm, setFlexForm] = usePageSession<FlexFormState>("flexForm", defaultFlexFormState);
  const [exForm, setExForm] = usePageSession<ExFormState>("exForm", defaultExFormState);
  const [mexForm, setMexForm] = usePageSession<MExFormState>("mexForm", defaultMExFormState);
  const patchFlex = (patch: Partial<FlexFormState>) => setFlexForm((f) => ({ ...f, ...patch }));
  const patchEx = (patch: Partial<ExFormState>) => setExForm((f) => ({ ...f, ...patch }));
  const patchMex = (patch: Partial<MExFormState>) => setMexForm((f) => ({ ...f, ...patch }));

  const isExFamily = method !== "flex";

  // U16: the subject set is the page's, not the shell's. U11 deleted the context bar's batch
  // control, which left `useSubject().batch` with no writer and this page unable to reach a
  // multi-subject run at all. Seeded from the shell's current subject and kept in step with it
  // exactly as Pre-processing's own batch table does — a page control must not re-scope the app.
  const [subjects, setSubjects] = usePageSession<string[]>("subjects", () => selection);
  const [lastShellSubject, setLastShellSubject] = useState(shellSubject);
  if (shellSubject !== lastShellSubject) {
    setLastShellSubject(shellSubject);
    if (shellSubject && !subjects.includes(shellSubject)) setSubjects([shellSubject, ...subjects]);
  }
  /** The subject whose catalog fills the shared controls (nets, atlases, saved ROIs). */
  const subjectId = subjects[0] ?? null;
  // Only subjects with a head model: `GET /api/catalog/{leadfields,atlases}` answers **404** for a
  // subject with no `m2m_<id>/` (measured on Dataset 000's `sub-test` and `sub-102`), and React
  // Query retries a failure three times — 14 requests per such subject per page visit against 6
  // for a real one, in the container's own access log. A subject with no head model can have
  // neither a leadfield nor an atlas, so asking is never worth one request, let alone four.
  const allSubjectIds = useMemo(() => projectSubjects.filter((s) => s.has_m2m).map((s) => s.id), [projectSubjects]);

  const eegNets = useQuery({ queryKey: ["eeg-nets", subjectId], queryFn: () => getEegNets(subjectId as string), enabled: subjectId !== null });
  // One leadfield query per PROJECT subject (Ex/mEx only): the HDF5 lives under that subject's own
  // derivatives, so a batch run needs every subject's path — and the Subjects table's `leadfield`
  // column has to answer for a subject the user has not ticked yet, which is when the answer is
  // still useful. Cheap (`GET /api/catalog/leadfields?subject=…` is a directory read) and cached.
  const leadfieldSubjects = useMemo(() => (isExFamily ? allSubjectIds : []), [isExFamily, allSubjectIds]);
  const leadfieldQueries = useQueries({
    queries: leadfieldSubjects.map((s) => ({ queryKey: ["leadfields", s], queryFn: () => getLeadfields(s) })),
  });
  const leadfieldsBySubject: Record<string, Leadfield[] | undefined> = {};
  const leadfieldsReady: Record<string, boolean> = {};
  leadfieldSubjects.forEach((s, i) => {
    leadfieldsBySubject[s] = leadfieldQueries[i]?.data;
    leadfieldsReady[s] = leadfieldQueries[i]?.isSuccess === true;
  });
  // The strip states the PRIMARY subject's leadfields — index 0 of the query list is the first
  // subject of the project, which is not the same thing once the list covers every subject.
  const primaryLeadfields = leadfieldQueries[leadfieldSubjects.indexOf(subjectId ?? "")];

  const [pickedNet, setPickedNet] = usePageSession<string | null>("net", null);
  // Default to a net that already has a leadfield, derived at render so an explicit pick wins and
  // there is nothing to synchronise. Every net identity on this page is the BARE name (`nets.ts`).
  const net = pickedNet ?? defaultNetFor(leadfieldsBySubject[subjectId ?? ""], eegNets.data);
  const leadfieldHdf = leadfieldPathFor(leadfieldsBySubject[subjectId ?? ""], net);
  const electrodes = electrodesForNet(eegNets.data, net);

  const generateLeadfield = useMutation({
    mutationFn: (n: string) => submitLeadfieldJob(subjectId as string, n),
    onSuccess: (_d, n) => {
      notify.success(`Queued: leadfield generation for ${n}`);
      void queryClient.invalidateQueries({ queryKey: ["leadfields", subjectId] });
    },
    onError: () => notify.error("Could not queue the leadfield job."),
  });

  // Every project subject, not only the ticked ones: the Subjects table states per-subject
  // readiness ("this subject has no such target") BEFORE it is ticked, which is the whole point of
  // a readiness column. React Query de-duplicates and caches these by subject, and the same cache
  // entries are what the submit path resolves each job's own atlas path from.
  const flexAtlasLookups = useAtlasLookups(allSubjectIds, flexRoi);
  const nonRoiAtlasLookups = useAtlasLookups(allSubjectIds, nonRoi);
  const exAtlasLookups = useAtlasLookups(allSubjectIds, exRoi);
  const flexAtlasLookup = flexAtlasLookups.lookup(subjectId ?? "");
  const nonRoiAtlasLookup = nonRoiAtlasLookups.lookup(subjectId ?? "");
  const exAtlasLookup = exAtlasLookups.lookup(subjectId ?? "");

  const flexRoiConfig = useMemo(() => roiToConfig(flexRoi, flexAtlasLookup), [flexRoi, flexAtlasLookup]);
  const isFocality = flexForm.goal === "focality" || flexForm.goal === "focality_tf";
  const nonRoiConfig = useMemo(
    () => (isFocality && flexForm.nonRoiMethod === "specific" ? roiToConfig(nonRoi, nonRoiAtlasLookup) : undefined),
    [isFocality, flexForm.nonRoiMethod, nonRoi, nonRoiAtlasLookup],
  );

  // The plan's target list (and the grid's columns) come from the primary subject; a target's
  // *name* is subject-independent, only its resolved atlas path is not — which is why the submit
  // path re-resolves per subject rather than reusing these.
  const targets = useMemo(
    () => (isExFamily ? exTargets(exRoi, exAtlasLookup, method === "ex") : []),
    [isExFamily, exRoi, exAtlasLookup, method],
  );

  // Both of this page's per-subject blockers are `eligibility` (J3), so the Subjects table refuses
  // to tick a subject that cannot run and the action bar's sentence is the grammar's own — one
  // wording for "this subject cannot run", shared with Pre-processing, Simulator and Analyzer.
  //
  // 1. The leadfield: `sub-101` may have its own matrix for one net and none for another.
  // 2. The target: an atlas region exists per subject, and Dataset 000 proves it — `sub-ernie` has
  //    `aparc.DKTatlas+aseg.mgz` from FreeSurfer, `sub-101` has only SimNIBS's `labeling.nii.gz`.
  //    Without this the plan grid would show a row for 101 (the server plans every id it is given)
  //    while `exSubmissions` silently dropped it for having no resolvable target — a plan that
  //    promises a job Run never queues. Saved-ROI targets are name-only, so a missing CSV on the
  //    second subject is still only caught by the runner (open issue in this lane's notes).
  //
  // Each check answers only for a subject whose own query has landed: a readiness column must not
  // call a subject "no leadfield" while its request is still in flight.
  const eligibility = (s: { id: string; has_m2m?: boolean }) => {
    if (s.has_m2m === false) return { ok: false, reason: "no head model (m2m)" };
    if (!isExFamily) return { ok: true };
    if (net && leadfieldsReady[s.id] && !leadfieldPathFor(leadfieldsBySubject[s.id], net)) {
      return { ok: false, reason: `no ${net} leadfield` };
    }
    if (targets.length > 0 && exAtlasLookups.ready(s.id) && exTargets(exRoi, exAtlasLookups.lookup(s.id), method === "ex").length === 0) {
      return { ok: false, reason: "this target does not exist for it" };
    }
    return { ok: true };
  };
  const subjectsBlocked = subjectsBlockedReason(subjects, blockedSubjects(projectSubjects, subjects, eligibility));

  /** The readiness columns this page can answer: a head model always, a leadfield in Ex/mEx. */
  const subjectColumns: SubjectColumn<{ id: string }>[] = [
    ...(presenceColumns<Subject>().filter((c) => c.id === "m2m") as unknown as SubjectColumn<{ id: string }>[]),
    ...(isExFamily
      ? [
          {
            id: "leadfield",
            label: "leadfield",
            title: net ? `A precomputed ${net} leadfield` : "A precomputed leadfield for the selected net",
            present: (s: { id: string }) => !!net && !!leadfieldPathFor(leadfieldsBySubject[s.id], net),
          },
        ]
      : []),
  ];

  const jobKind = method === "flex" ? jobKindFor(flexForm) : method;
  const planKind: PlanKind = method === "flex" ? "flex" : method;

  const flexConfig: FlexConfigWire | undefined = useMemo(
    () => (flexRoiConfig ? buildFlexConfig(subjects[0] ?? "", flexForm, flexRoiConfig, nonRoiConfig) : undefined),
    [subjects, flexForm, flexRoiConfig, nonRoiConfig],
  );

  const debouncedFlex = useDebounced(flexConfig, 400);
  const debouncedSubjects = useDebounced(subjects, 400);
  const debouncedOverwrite = useDebounced(overwrite, 400);
  const debouncedExKey = useDebounced(JSON.stringify({ exForm, mexForm, targets, runName, leadfieldHdf }), 400);

  const flexPlan = useQuery({
    queryKey: ["plan", jobKind, debouncedFlex, debouncedSubjects, debouncedOverwrite],
    queryFn: () => planFor(jobKind, debouncedFlex as FlexConfigWire, debouncedSubjects, debouncedOverwrite),
    enabled: method === "flex" && debouncedFlex !== undefined && debouncedSubjects.length > 0,
  });

  // One plan request per target, each asking for EVERY selected subject: `_plan_ex`/`_plan_mex`
  // loop over `subject_ids` and resolve `pm.ex_search_run(sid, run_name)` per subject (the
  // leadfield path in the config is not part of that resolution), so N subjects × M targets is
  // M requests, and the merged grid is subjects (rows) × targets (columns).
  const exPlans = useQueries({
    queries:
      isExFamily && leadfieldHdf && subjectId
        ? targets.map((t) => ({
            queryKey: ["plan", method, debouncedSubjects, leadfieldHdf, debouncedExKey, t.roiName],
            queryFn: () =>
              planFor(
                method,
                method === "ex"
                  ? buildExConfig(subjectId, leadfieldHdf, exForm, t, runName)
                  : buildMExConfig(subjectId, leadfieldHdf, mexForm, t, runName),
                debouncedSubjects,
                overwrite,
              ),
          }))
        : [],
  });

  const blockedReason = useMemo<string | null>(() => {
    if (subjects.length === 0) return subjectsBlocked;
    if (method === "flex") {
      if (!flexRoiConfig) return "Complete the ROI definition.";
      if (isFocality && flexForm.nonRoiMethod === "specific" && !nonRoiConfig) return "Complete the non-ROI region, or switch it to “everything else”.";
      if (flexForm.goal === "focality" && flexForm.focalityMode === "manual" && !flexForm.manualThresholds.trim()) return "Enter at least one E-field threshold.";
      if (flexForm.enableMapping && !flexForm.eegNet) return "Select an EEG net for the mapped-electrode simulation.";
      if (flexForm.visualizeSkinElectrodes && !flexForm.skinVisualizationNet) return "Select a visualization EEG net.";
      return null;
    }
    if (!net) return "Select an EEG net.";
    if (!leadfieldHdf) return "Generate a leadfield for this net first.";
    // The per-subject clause keeps its old position: after the page-wide preconditions, before the
    // form's own completeness checks — but the sentence is now the grammar's (J3), so it reads the
    // same here as on the other three run pages.
    if (subjectsBlocked) return subjectsBlocked;
    if (method === "ex" && exForm.electrodeMode === "bucketed" && EX_BUCKET_KEYS.some((k) => (exForm.buckets[k] ?? []).length === 0)) return "Fill in every electrode bucket.";
    if (method === "ex" && exForm.electrodeMode === "all" && exForm.pool.length < 4) return "Add at least four electrodes to the pool.";
    if (method === "mex" && MEX_BUCKET_KEYS.some((k) => (mexForm.buckets[k] ?? []).length === 0)) return "Fill in all eight electrode buckets.";
    if (targets.length === 0) return "Select at least one saved ROI, or an atlas region.";
    return null;
  }, [subjects, subjectsBlocked, method, flexRoiConfig, isFocality, flexForm, nonRoiConfig, net, leadfieldHdf, exForm, mexForm, targets]);

  const mergedExResult = useMemo(
    () => mergePlanResults(targets.map((t, i) => ({ label: t.roiName, result: exPlans[i]?.data as PlanResult | undefined }))),
    [targets, exPlans],
  );
  const planResult = method === "flex" ? (flexPlan.data as PlanResult | undefined) : mergedExResult;
  const plan: PlanModel | null = useMemo(
    () => (planResult ? planModelFrom(planKind, planResult, subjects, { blockedReason }) : null),
    [planResult, planKind, subjects, blockedReason],
  );

  const planLoading = method === "flex" ? flexPlan.isPending && flexPlan.fetchStatus !== "idle" : exPlans.some((q) => q.isPending && q.fetchStatus !== "idle");
  const planRefetching = method === "flex" ? flexPlan.isRefetching : exPlans.some((q) => q.isRefetching);
  const planError = method === "flex" ? !!flexPlan.error : exPlans.some((q) => q.error);
  function refetchPlan(): void {
    if (method === "flex") void flexPlan.refetch();
    else for (const q of exPlans) void q.refetch();
  }

  const costLine = method === "flex" ? flexCost(flexForm).line : method === "ex" ? exCost(exForm).line : mexCost(mexForm).line;
  const receipt = receiptFrom(plan);
  const digest = plan ? `${planDigest(plan)}${plan.blockedReason ? "" : ` · ${costLine}`}` : (blockedReason ?? "Resolving the plan…");

  const lastJob = useMemo(() => {
    const kinds = ["flex", "flex_adaptive", "flex_pareto", "ex", "mex"];
    const mine = Object.values(stream.jobs).filter((j) => kinds.includes(j.kind));
    return mine.sort((a, b) => Date.parse(b.created_at ?? "") - Date.parse(a.created_at ?? ""))[0];
  }, [stream.jobs]);

  useStatusCells([
    { id: "lastJob", label: "Job", value: lastJob ? `${lastJob.kind} · ${lastJob.state}` : null, priority: 10 },
    { id: "planCost", label: "Plan", value: plan && !plan.blockedReason ? planDigest(plan) : null, priority: 20 },
  ]);

  /**
   * One `POST /api/jobs/groups` for a whole batch of runs, whatever the method (R3). `runs` is
   * already one entry per job — per subject for flex, per (subject, target) for ex/mEx — so each
   * becomes its own `subject_configs` entry under one group id and one scheduler-enforced cap.
   */
  async function submitGroup(
    kind: GroupKind,
    runs: { subject: string; config: unknown }[],
    tags: string[],
    overwriteFlag: boolean,
  ): Promise<void> {
    const subjectIds = [...new Set(runs.map((r) => r.subject))];
    await submitJobGroup(kind, runs[0]!.config, subjectIds, parallelSubjects, {
      subjectConfigs: runs.map((r) => ({ subject_id: r.subject, config: r.config })),
      tags,
      overwrite: overwriteFlag,
    });
  }

  const submit = useMutation({
    mutationFn: async (overwriteFlag: boolean) => {
      if (method === "flex") {
        if (!flexRoiConfig) throw new Error("Complete the ROI definition.");
        // Each subject's ROI is resolved against that subject's own atlases (`useAtlasLookups`).
        const runs = flexSubmissions(subjects, flexForm, (subject) => ({
          roi: roiToConfig(flexRoi, flexAtlasLookups.lookup(subject)),
          nonRoi: isFocality && flexForm.nonRoiMethod === "specific" ? roiToConfig(nonRoi, nonRoiAtlasLookups.lookup(subject)) : undefined,
        }));
        if (runs.length === 0) throw new Error("Complete the ROI definition.");
        const validation = await validateFor(jobKind, runs[0]!.config).catch(() => null);
        if (validation && !validation.ok) {
          setValidationErrors(validation.errors.map((e) => `${e.path}: ${e.message}`));
          throw new Error("invalid");
        }
        setValidationErrors([]);
        // ONE request for the batch (R3): the group is created queued in a single
        // `POST /api/jobs/groups` carrying `parallel_subjects`, and the scheduler releases the
        // members that-many-at-a-time. This used to be an awaited `for` loop of `POST /api/jobs`,
        // which decided nothing about concurrency — the server admitted whatever fit its budget.
        // Each subject's config is already resolved against its own atlases, so every run goes in
        // as its own `subject_configs` entry (and the server forces each config's `subject_id`).
        await submitGroup(
          jobKind as GroupKind,
          runs,
          subjects.length > 1 ? ["flex-batch"] : [],
          overwriteFlag,
        );
        return runs.length;
      }
      const runs = exSubmissions(
        method,
        subjects,
        (subject) => ({
          leadfieldHdf: leadfieldPathFor(leadfieldsBySubject[subject], net),
          targets: exTargets(exRoi, exAtlasLookups.lookup(subject), method === "ex"),
        }),
        { ex: exForm, mex: mexForm },
        runName,
      );
      await submitGroup(method, runs, subjects.length > 1 ? [`${method}-batch`] : [], overwriteFlag);
      return runs.length;
    },
    onSuccess: (n) => {
      notify.success(
        n > 1
          ? `Queued ${n} ${method} runs (${parallelSubjects > 1 ? `${parallelSubjects} at a time` : "one at a time"}).`
          : `Queued: ${method} search for ${subjects[0]}.`,
      );
      setPinnedJobId(null);
    },
    onError: (e) => {
      if ((e as Error).message !== "invalid") notify.error("Could not queue the search.");
    },
  });

  function handleRunClick(): void {
    // §4.2 rule 8: the primary stays enabled; pressing it with an unresolvable plan says why.
    if (blockedReason) {
      notify.error(blockedReason);
      return;
    }
    // The one existing-outputs question (C3): asked whenever anything already has output, with
    // Skip as a real answer — before, "Cancel" was the only alternative to overwriting.
    if (!overwrite && receipt.existing > 0) {
      setConfirmOverwrite(true);
      return;
    }
    submit.mutate(overwrite);
  }
  useRunShortcut(handleRunClick);

  // Ex/mEx queue one job per (subject × target) — the label counts what Run will actually submit.
  const exRunCount = subjects.length * targets.length;
  const runLabel =
    method === "flex"
      ? subjects.length > 1
        ? `Run flex search for ${subjects.length} subjects`
        : "Run flex search"
      : exRunCount > 1
        ? `Run ${exRunCount} ${method === "ex" ? "ex" : "mEx"} searches`
        : `Run ${method === "ex" ? "ex" : "mEx"} search`;

  /*
   * The scene pane in `target` mode (plan §2.4). What a click means depends on what the ROI picker
   * is currently expressing, because that is the thing it has to stay in sync with:
   *
   *  - flex + cortical  -> add/remove that atlas region, straight into `flexRoi.regions`;
   *  - flex + spherical -> move the sphere centre, but ONLY in subject space: the scene's
   *    coordinates are the head model's own millimetres, and writing them into an MNI field would
   *    be off by the whole subject-to-template transform with nothing on screen to say so;
   *  - anything else (subcortical, a saved ROI CSV, ex/mEx) -> the anatomy, read-only, and a line
   *    saying why. A volumetric atlas id is not a cortical `.annot`, so asking `/api/scene/regions`
   *    for one would 404 the whole pane for a target the form can express perfectly well.
   */
  const sceneCortical = method === "flex" && flexRoi.mode === "cortical";
  const sceneSpherical = method === "flex" && flexRoi.mode === "spherical";
  const sceneSphereSpace = flexRoi.mode === "spherical" ? flexRoi.space : "subject";
  const sceneNote =
    sceneCortical || (sceneSpherical && sceneSphereSpace === "subject")
      ? undefined
      : sceneSpherical
        ? "Coordinates are typed, not picked — the pane draws the reference guide, not this subject."
        : method === "flex"
          ? "Subcortical targets are volumetric — pick them in the form; the pane shows the reference guide."
          : "Ex and mEx targets are saved ROIs — pick them in the form; the pane shows the reference guide.";

  function openViewer(): void {
    if (!subjectId) return;
    navigate({ pathname: "/viewer", search: viewerSearch({ subject: subjectId, kind: "subject" }) });
  }

  return (
    <PageLayout
      className="page-run page-optimizer"
      variant="run"
      paneController={scenePane}
      rightPane={
        <RunPanel
          kind={planKind}
          jobKinds={["flex", "ex", "mex"]}
          plan={plan}
          loading={planLoading}
          refetching={planRefetching}
          error={planError ? "Could not build the plan for this search." : undefined}
          onRefetch={refetchPlan}
          subjects={subjects}
          emptyMessage={blockedReason ?? "Choose a target to see the plan."}
          pinnedJobId={pinnedJobId}
          onPinJob={setPinnedJobId}
          steps={stepsFor(planKind)}
          parallel={parallelSubjects}
          paneControls={<PaneHeaderControls controller={scenePane} />}
          scene={
            <ScenePane
              mode="target"
              atlas={sceneCortical && flexRoi.mode === "cortical" ? (flexRoi.atlas ?? null) : null}
              regions={sceneCortical && flexRoi.mode === "cortical" ? flexRoi.regions : undefined}
              onRegionsChange={
                sceneCortical
                  ? (regions) => setFlexRoi({ ...(flexRoi as Extract<RoiValue, { mode: "cortical" }>), regions })
                  : undefined
              }
              note={sceneNote}
            />
          }
        />
      }
      receipt={<Receipt plan={plan} policy={overwrite ? "replace" : "skip"} blockedReason={blockedReason} />}
      actionBar={
        <ActionBar
          digest={digest}
          blocked={!!blockedReason}
          primary={
            <Button
              variant="primary"
              loading={submit.isPending}
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
      {/* `fill={false}`: the Optimizer's sections are already sized to the pane (B3 measured it as
          the densest of the four run pages), so the fill controller has nothing to add and would
          only fight the method segment's own show/hide. */}
      <RunWork fill={false}>
        {/* Subjects (J1/J2): the one shared control, first on the page. It moved out of the method
            row — a summary line plus a table is not a form field, and every other run page states
            its subject set in exactly this shape. Adding subjects runs the same search on each. */}
        <div data-tier="1">
          <SubjectsField
            subjects={projectSubjects}
            value={subjects}
            onChange={setSubjects}
            columns={subjectColumns}
            eligibility={eligibility}
            mode="per-subject"
            defaultOpen
          />
        </div>

        <div data-tier="1">
          <div className="optimizer-method-row">
            <SegmentedControl
              aria-label="Method"
              value={method}
              onValueChange={(v) => setMethod(v as Method)}
              options={METHOD_OPTIONS.map((o) => ({ value: o.value, label: o.label, title: o.title }))}
            />
            <Field label="Run name" htmlFor="optimizer-run-name" help="Defaults to a timestamp.">
              <TextInput id="optimizer-run-name" value={runName} onChange={(e) => setRunName(e.target.value)} placeholder="auto (timestamp)" />
            </Field>
          </div>
          {isExFamily && (
            <LeadfieldStrip
              leadfields={primaryLeadfields?.data}
              loading={!!primaryLeadfields?.isPending && primaryLeadfields.fetchStatus !== "idle"}
              nets={eegNets.data}
              selectedNet={net}
              onSelectNet={setPickedNet}
              onGenerate={(n) => generateLeadfield.mutate(n)}
              generating={generateLeadfield.isPending}
            />
          )}
        </div>

        <div data-tier="1">
          <FormSection title="Target">
            {/* `FormSection` lays its children out as a two-column `.form-grid`; the picker is one
                object and takes the whole row, or every atlas control is squeezed into half a pane. */}
            <div className="optimizer-span">
              {method === "flex" ? (
                <RoiPicker
                  value={flexRoi}
                  onChange={setFlexRoi}
                  modes={["cortical", "subcortical", "spherical"]}
                  subject={subjectId ?? undefined}
                  onOpenViewer={flexRoi.mode === "spherical" ? openViewer : undefined}
                />
              ) : (
                <RoiPicker value={exRoi} onChange={setExRoi} modes={["saved", "subcortical"]} subject={subjectId ?? undefined} allowCombine={method === "ex"} />
              )}
            </div>
          </FormSection>
        </div>

        <div data-tier="1">
          {method === "flex" && (
            <ObjectiveSection form={flexForm} onChange={patchFlex} nonRoi={nonRoi} onNonRoiChange={setNonRoi} subject={subjectId ?? undefined} />
          )}
          {method === "ex" && <ExElectrodesSection form={exForm} onChange={patchEx} electrodes={electrodes} disabled={!net} />}
          {method === "mex" && <MExElectrodesSection form={mexForm} onChange={patchMex} electrodes={electrodes} disabled={!net} />}
        </div>

        {method === "flex" && (
          <>
            <ElectrodesSection form={flexForm} onChange={patchFlex} />
            <SolverSection form={flexForm} onChange={patchFlex} eegNets={eegNets.data ?? []} />
            <PostRunSection form={flexForm} onChange={patchFlex} eegNets={eegNets.data ?? []} />
          </>
        )}
        {method === "ex" && <ExCurrentSection form={exForm} onChange={patchEx} />}
        {method === "mex" && <MExCarrierSection form={mexForm} onChange={patchMex} />}


        {validationErrors.length > 0 && (
          <Callout kind="danger" title="The server rejected this configuration">
            {validationErrors.map((e) => (
              <span key={e} style={{ display: "block" }}>
                {e}
              </span>
            ))}
          </Callout>
        )}
      </RunWork>

      <ExistingOutputsDialog
        open={confirmOverwrite}
        onOpenChange={setConfirmOverwrite}
        existing={receipt.existing}
        total={receipt.jobs}
        noun="search output"
        busy={submit.isPending}
        onDecide={(decision) => {
          setConfirmOverwrite(false);
          if (decision === "replace") setOverwrite(true);
          submit.mutate(decision === "replace");
        }}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "optimizer",
  title: "Optimizer",
  purpose: "Search electrode placement for a target ROI — flex, exhaustive, or multipolar.",
  navGroup: "pipeline",
  order: 30,
  icon: Target,
  shortcut: "4",
  Component: OptimizerPage,
  enabled: true,
};

export default page;
