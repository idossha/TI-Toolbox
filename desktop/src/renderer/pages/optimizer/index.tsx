/**
 * Optimizer — one page for every search, described as a **jobs table** (lane OJ, 2026-09-06).
 *
 * U7 merged `optimizer-flex` and `optimizer-ex` into one page because both ask "where do the
 * electrodes go for this target". What that merge kept from the PyQt tabs was the *shape* of a
 * tab: one page-level subject set, one method segment, one global TARGET / ELECTRODES / COST form.
 * The maintainer's screenshot of it ("No subjects selected", a global Subjects list) came with the
 * ask that closes the gap:
 *
 * > "create something similar logically to the Simulator and Analyzer: choose a subject, then an
 * > optimisation approach (Flex, Ex, mEx…) and configure each job exactly how they want, so users
 * > create a list of jobs and run them."
 *
 * So the page is now the same §4.7 grammar as the other two run pages: **one row is one search**,
 * the row owns its subject, its method, its net or leadfield, its goal, its target and its whole
 * form, and there is nothing global left — per 2.5.0 there never was anything global here, because
 * the "Global Parameters" box was per *tab*, which is per method, which is per row.
 *
 * What did not change: `POST /api/plan/{kind}` per job, `planModelFrom`, the existing-outputs
 * dialog (C3), the disabled-Run grammar (§4.2 rule 8) and the one shared `RoiPicker` — only their
 * scope did, from the page to the row.
 *
 * One deliberate difference from the Simulator: **one Run click is one submission per job kind**,
 * not one submission full stop. `POST /api/jobs/groups` takes a single `kind`
 * (`tit/jobs/plans.py::GROUP_KINDS`), so a table mixing Flex and Ex rows cannot be one group
 * without a server change. The page states this in its own success message rather than pretending
 * otherwise; `PARITY.md` carries it as the open contract item.
 */
import { useEffect, useMemo, useState } from "react";
import { Info, Target, Workflow } from "lucide-react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { PageDef } from "../../app/registry";
import { useSubject } from "../../app/subjectContext";
import { useExecutionPrefs } from "../../app/executionPrefs";
import { usePageSession } from "../../app/pageSession";
import { useJobsStream } from "../../app/jobs/useJobsStream";
import { PageLayout, FormSection, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { Button, IconButton } from "../../ui/Button";
import { Popover } from "../../ui/Overlay";
import { Callout, EmptyState } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { getAtlases, type Atlas, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { subjectsBlockedReason } from "../_shared/subjects";
import {
  RunPanel,
  RunWork,
  planCounts,
  ExistingOutputsDialog,
  mergePlanResults,
  planDigest,
  planModelFrom,
  stepsFor,
  submitJobGroup,
  useRunShortcut,
  type GroupKind,
  type PlanKind,
  type PlanModel,
  type PlanResult,
  type PlanStage,
} from "../_shared/run";
import { ScenePane } from "../_shared/scene";
import { TargetPreview } from "../_shared/scene/TargetPreview";
import { viewerSearch } from "../results";
import { getEegNets, getLeadfields, planFor, submitLeadfieldJob, validateFor, type EegNet, type Leadfield } from "./api";
import { leadfieldPathFor } from "./nets";
import { OptimizerJobRows, type OptimizerSubject } from "./JobRows";
import { automaticRunName, flexOutputFolder, jobsForRow, rowFormReason, type OptimizerJobSpec } from "./plan";
import {
  emptyOptimizerRow,
  isRunnableOptimizerRow,
  optimizerJobsSummary,
  OPT_METHOD_LABEL,
  rowPlanKind,
  type OptimizerRow,
} from "./rows";
import "./optimizer.css";

/** The plan grid's columns: the three families, counted per subject (`cellDetail="counts"`). */
const PLAN_STAGES: PlanStage[] = [
  { id: "flex", label: "Flex" },
  { id: "ex", label: "Ex" },
  { id: "mex", label: "mEx" },
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
 * Atlas paths, resolved **per (subject, atlas kind)** from the same query key the picker uses — a
 * cache hit, not a second request.
 *
 * Per subject, not once: an atlas id (`"DK40"`) is the same string for every subject but its path
 * is not (`derivatives/…/sub-<id>/…`). Now that a row names its own subject, a page-wide resolver
 * would point every job at the first row's anatomy — the U16 defect, made per row.
 */
interface AtlasKey {
  subject: string;
  kind: "cortical" | "subcortical";
  space: "subject" | "mni" | undefined;
}

function atlasKeyOf(subject: string, roi: RoiValue): AtlasKey | null {
  if (!subject) return null;
  if (roi.mode === "cortical") return { subject, kind: "cortical", space: undefined };
  if (roi.mode === "subcortical") return { subject, kind: "subcortical", space: roi.atlasSpace };
  return null;
}

function atlasKeyId(k: AtlasKey): string {
  return `${k.subject}|${k.kind}|${k.space ?? ""}`;
}

/** One query per distinct (subject, kind, space) the table asks about; react-query de-duplicates
 *  the rest, so N rows on one subject cost one request. */
function useAtlasResolver(keys: AtlasKey[]): (subject: string, roi: RoiValue) => (atlas: string) => AtlasLookup | undefined {
  const results = useQueries({
    queries: keys.map((k) => ({
      queryKey: k.kind === "subcortical" ? ["atlases", k.subject, "subcortical", k.space] : ["atlases", k.subject, "cortical"],
      queryFn: () => getAtlases(k.subject, k.kind, k.space),
    })),
  });
  const byId: Record<string, Atlas[] | undefined> = {};
  keys.forEach((k, i) => {
    byId[atlasKeyId(k)] = results[i]?.data;
  });
  return (subject: string, roi: RoiValue) => {
    const key = atlasKeyOf(subject, roi);
    const list = key ? byId[atlasKeyId(key)] : undefined;
    return (atlasId: string) => list?.find((a) => a.id === atlasId);
  };
}

function OptimizerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: shellSubject, subjects: projectSubjects } = useSubject();
  const jobsStream = useJobsStream();
  const completedLeadfields = Object.values(jobsStream.jobs)
    .filter((job) => job.kind === "leadfield" && job.state === "succeeded")
    .map((job) => job.id).sort().join(",");
  useEffect(() => {
    if (completedLeadfields) void queryClient.invalidateQueries({ queryKey: ["leadfields"] });
  }, [completedLeadfields, queryClient]);


  // `usePageSession` for everything the user decided (lane N2): the page unmounts on every
  // navigation, and a table of assembled jobs is exactly the thing a step onto Results must not
  // throw away.
  const [rows, setRows] = usePageSession<OptimizerRow[]>("jobRows", []);
  const [leadfieldJobs, setLeadfieldJobs] = usePageSession<Record<string, string>>("leadfieldJobs", {});
  const [activeRowId, setActiveRowId] = usePageSession<string | null>("activeRow", null);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);
  // The jobs this Run press started: they keep their log and final status line in the terminal
  // after they finish, instead of the pane emptying itself the moment the run succeeds
  // (maintainer, 2026-09-07). Page-session state, like the pin, so navigating away and back keeps
  // the output; a new Run replaces it.
  const [startedJobIds, setStartedJobIds] = usePageSession<string[]>("startedJobs", []);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const scenePane = usePaneController({ pageId: "optimizer", name: "run" });

  // Only subjects with a head model are asked about: `GET /api/catalog/{leadfields,atlases}`
  // answers 404 for a subject with no `m2m_<id>/`, and react-query retries a failure three times.
  const modelled = useMemo(() => projectSubjects.filter((s) => s.has_m2m).map((s) => s.id), [projectSubjects]);

  const netQueries = useQueries({
    queries: modelled.map((id) => ({ queryKey: ["eeg-nets", id], queryFn: () => getEegNets(id), staleTime: 60_000 })),
  });
  const netsBySubject: Record<string, EegNet[] | undefined> = {};
  modelled.forEach((id, i) => {
    netsBySubject[id] = netQueries[i]?.data;
  });

  // Leadfields are only fetched once the table actually has an Ex/mEx row: a 3 GB HDF5 listing is
  // a directory read, but a page with no exhaustive search has nothing to do with the answer.
  const wantsLeadfields = rows.some((r) => r.method === "ex");
  const leadfieldQueries = useQueries({
    queries: modelled.map((id) => ({ queryKey: ["leadfields", id], queryFn: () => getLeadfields(id), enabled: wantsLeadfields, staleTime: 60_000 })),
  });
  const leadfieldsBySubject: Record<string, Leadfield[] | undefined> = {};
  modelled.forEach((id, i) => {
    leadfieldsBySubject[id] = leadfieldQueries[i]?.data;
  });

  // The page starts with one row on the shell's subject: a table whose first act is "press Add
  // job" would make the page's own subject a thing to discover (the Simulator's own seeding).
  const [seeded, setSeeded] = useState(false);
  if (!seeded && rows.length === 0 && modelled.length > 0) {
    setSeeded(true);
    const first = emptyOptimizerRow({ subjectId: shellSubject && modelled.includes(shellSubject) ? shellSubject : modelled[0] });
    setRows([first]);
    setActiveRowId(first.id);
  }

  const atlasKeys = useMemo(() => {
    const seen = new Map<string, AtlasKey>();
    for (const row of rows) {
      for (const roi of [row.roi, row.nonRoi]) {
        const k = atlasKeyOf(row.subjectId, roi);
        if (k) seen.set(atlasKeyId(k), k);
      }
    }
    return [...seen.values()];
  }, [rows]);
  const atlasFor = useAtlasResolver(atlasKeys);

  const leadfieldFor = (subject: string, net: string | null): string | null =>
    leadfieldPathFor(leadfieldsBySubject[subject], net);
  const hasLeadfield = (row: OptimizerRow): boolean => leadfieldFor(row.subjectId, row.net) !== null;

  const runnableRows = rows.filter((r) => isRunnableOptimizerRow(r, hasLeadfield));
  // Stable identity, so the plan model is not rebuilt on every render: subject ids carry no commas
  // (they are BIDS labels), so the joined string is a faithful key for the list.
  const planSubjectsSig = [...new Set(runnableRows.map((r) => r.subjectId))].join(",");
  const planSubjects = useMemo(() => (planSubjectsSig ? planSubjectsSig.split(",") : []), [planSubjectsSig]);

  /**
   * Every job the table will queue, in row order — the one list the plan, the digest, the count
   * and the submission all read, so none of them can promise a job another does not queue.
   *
   * Derived every render rather than memoized, and then **debounced as a string**: `useQueries`
   * hands back a fresh array each render, so every resolver above it is a fresh closure and a
   * `useMemo` over them could only ever be keyed on a serialisation anyway (the Simulator's
   * `useSimPlan` reached the same conclusion). Debouncing the JSON and parsing it back is what
   * makes `debouncedJobs` stable — a new array identity every 400 ms would re-arm its own timer.
   */
  const jobs = runnableRows.flatMap((row) => jobsForRow(row, { atlas: atlasFor, leadfield: leadfieldFor }));
  const jobsSig = JSON.stringify(jobs);
  const debouncedSig = useDebounced(jobsSig, 400);
  const debouncedJobs = useMemo(() => JSON.parse(debouncedSig) as OptimizerJobSpec[], [debouncedSig]);

  // One `POST /api/plan/{kind}` per job, exactly as the Simulator plans one per (subject, montage)
  // row: a job's config is its own, so it is the only thing that can be planned.
  const planQueries = useQueries({
    queries: debouncedJobs.map((job) => ({
      queryKey: ["plan", job.kind, job.rowId, job.subject, JSON.stringify(job.config), false],
      queryFn: async () => {
        if (job.stage !== "flex") return { plan: await planFor(job.kind, job.config, [job.subject], false), config: job.config };
        const config = job.config as Record<string, unknown>;
        // Ask the server for this subject's root, then plan the exact destination we will submit.
        const base = await planFor(job.kind, { ...config, output_folder: null }, [job.subject], false);
        const folder = base.jobs[0]?.output_dir;
        if (!folder) throw new Error("The server did not resolve the run folder.");
        const resolved = { ...config, output_folder: flexOutputFolder(folder, String(config.output_folder ?? ""), automaticRunName(job.rowId)) };
        return { plan: await planFor(job.kind, resolved, [job.subject], false), config: resolved };
      },
    })),
  });

  const planResults = planQueries.map((q) => q.data?.plan as PlanResult | undefined);
  const allPlanned = planResults.length > 0 && planResults.every((r) => r !== undefined) && planQueries.every((q) => q.isSuccess && !q.isFetching);
  /** The signature the derived plan objects are keyed on: which queries have answered, and when. */
  const planSig = `${debouncedSig.length}:${planQueries.map((q) => `${q.status}@${q.dataUpdatedAt}`).join("|")}`;

  /** `merged.jobs[i]` → the family column that job belongs in. Built alongside the merge so the
   *  grid's `stageFor` never has to guess a kind back out of an output directory. */
  const stageByJobIndex = useMemo(() => {
    const out: string[] = [];
    debouncedJobs.forEach((job, i) => {
      for (let k = 0; k < (planResults[i]?.jobs.length ?? 0); k++) out.push(job.stage);
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- planResults is a fresh array every render.
  }, [planSig]);

  const merged = useMemo(
    () => (allPlanned ? mergePlanResults(planResults as PlanResult[]) : undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- planResults is a fresh array every render.
    [allPlanned, planSig],
  );

  const subjectsBlocked = subjectsBlockedReason(
    planSubjects,
    planSubjects
      .map((id) => ({ id, reason: projectSubjects.find((s) => s.id === id)?.has_m2m === false ? "no head model (m2m)" : undefined }))
      .filter((b): b is { id: string; reason: string } => !!b.reason),
  );

  const blockedReason = useMemo<string | null>(() => {
    // §4.7 rule 3: the disabled sentence states the TABLE being empty before it states anything
    // about subjects — an empty table is not a subject problem.
    if (rows.length === 0) return "Add a search job.";
    if (runnableRows.length === 0) return "Complete a job: choose a subject, a target, and (for Ex/mEx) a leadfield.";
    if (subjectsBlocked) return subjectsBlocked;
    for (const [i, row] of runnableRows.entries()) {
      const reason = rowFormReason(row);
      if (reason) return `Job ${rows.indexOf(row) + 1}: ${reason}`;
      void i;
    }
    if (jobs.length === 0) return "No job resolves to a target yet.";
    if (jobsSig !== debouncedSig || !allPlanned) return "Resolving the run folders…";
    return null;
  }, [rows, runnableRows, subjectsBlocked, jobs, jobsSig, debouncedSig, allPlanned]);

  /** The panel's own kind — the family of the first job, which is what its step list describes. */
  const planKind: PlanKind = runnableRows[0] ? rowPlanKind(runnableRows[0]) : "flex";

  const plan: PlanModel | null = useMemo(
    () =>
      merged
        ? planModelFrom(planKind, merged, planSubjects, {
            blockedReason,
            stages: PLAN_STAGES,
            stageFor: (_job, index) => stageByJobIndex[index] ?? "flex",
          })
        : null,
    [merged, planKind, planSubjects, blockedReason, stageByJobIndex],
  );

  const planLoading = planQueries.some((q) => q.isPending && q.fetchStatus !== "idle");
  const planRefetching = planQueries.some((q) => q.isRefetching);
  const planError = planQueries.some((q) => q.error);
  function refetchPlan(): void {
    for (const q of planQueries) void q.refetch();
  }

  const counts = planCounts(plan);
  const digest = plan ? planDigest(plan) : (blockedReason ?? "Resolving the plan…");

  const generateLeadfield = useMutation({
    mutationFn: ({ subject, net }: { subject: string; net: string }) => submitLeadfieldJob(subject, net),
    onSuccess: (job, { subject, net }) => {
      setLeadfieldJobs((previous) => ({ ...previous, [JSON.stringify([subject, net])]: job.id }));
      notify.success(`Queued: leadfield generation for ${net}`);
      void queryClient.invalidateQueries({ queryKey: ["leadfields", subject] });
    },
    onError: () => notify.error("Could not queue the leadfield job."),
  });

  function leadfieldGenerationState(subject: string, net: string | null): string | null {
    if (!net) return null;
    if (generateLeadfield.isPending && generateLeadfield.variables?.subject === subject && generateLeadfield.variables.net === net) return "Queuing…";
    const id = leadfieldJobs[JSON.stringify([subject, net])];
    if (!id) return null;
    const state = jobsStream.jobs[id]?.state;
    if (!state || state === "queued") return "Queued…";
    if (state === "running") return "Generating…";
    if (state === "succeeded" && !leadfieldFor(subject, net)) return "Finishing…";
    return null;
  }

  const submit = useMutation({
    mutationFn: async (overwriteFlag: boolean) => {
      if (jobs.length === 0) throw new Error("Complete a job row.");
      // `POST /api/jobs/groups` takes ONE kind (`GROUP_KINDS`), so a mixed table is one group per
      // kind — in kind order, so the message can name them. Everything else about the submission
      // is unchanged: each job travels as its own `subject_configs` entry carrying its own
      // subject, and the server forces each config's `subject_id` to match.
      const byKind = new Map<GroupKind, OptimizerJobSpec[]>();
      if (jobsSig !== debouncedSig || !allPlanned) throw new Error("Wait for the current plan.");
      for (const [index, job] of jobs.entries()) {
        const resolved = { ...job, config: planQueries[index]!.data!.config };
        byKind.set(job.kind, [...(byKind.get(job.kind) ?? []), resolved]);
      }

      // Validate one representative config per kind before anything is queued (the flex path's
      // long-standing behaviour, now covering every kind the table holds).
      for (const [kind, group] of byKind) {
        const validation = await validateFor(kind, group[0]!.config).catch(() => null);
        if (validation && !validation.ok) {
          setValidationErrors(validation.errors.map((e) => `${kind}: ${e.path}: ${e.message}`));
          throw new Error("invalid");
        }
      }
      setValidationErrors([]);

      const startedIds: string[] = [];
      for (const [kind, group] of byKind) {
        const subjectIds = [...new Set(group.map((j) => j.subject))];
        const result = await submitJobGroup(kind, group[0]!.config, subjectIds, parallelSubjects, {
          subjectConfigs: group.map((j) => ({ subject_id: j.subject, config: j.config })),
          tags: group.length > 1 ? [`${kind}-batch`] : [],
          overwrite: overwriteFlag,
        });
        startedIds.push(...result.jobs.map((job) => job.id));
      }
      return { jobs: jobs.length, kinds: [...byKind.keys()], startedIds };
    },
    onSuccess: async ({ jobs: n, kinds, startedIds }) => {
      notify.success(
        n === 1
          ? `Queued: ${OPT_METHOD_LABEL[kinds[0] as keyof typeof OPT_METHOD_LABEL] ?? kinds[0]} search.`
          : `Queued ${n} searches in ${kinds.length} group${kinds.length === 1 ? "" : "s"} (${kinds.join(", ")}).`,
      );
      // A new run takes the terminal over: drop any explicit pin and follow this press's jobs.
      setPinnedJobId(null);
      setStartedJobIds(startedIds);
      await queryClient.invalidateQueries({ queryKey: ["plan"] });
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
    // The one existing-outputs question (C3), unchanged.
    if (counts.existing > 0) {
      setConfirmOverwrite(true);
      return;
    }
    submit.mutate(false);
  }
  useRunShortcut(handleRunClick);

  const runLabel = jobs.length > 1 ? `Run ${jobs.length} searches` : "Run search";

  const jobSubjects: OptimizerSubject[] = useMemo(() => {
    const anyModel = projectSubjects.some((s) => s.has_m2m);
    return projectSubjects.map((s) => ({
      id: s.id,
      blockedReason: s.has_m2m || !anyModel ? undefined : "no head model (m2m)",
    }));
  }, [projectSubjects]);

  // Cortical targets retain atlas picking; other targets show read-only extents from the form.
  const activeRow = rows.find((r) => r.id === activeRowId) ?? rows[0] ?? null;
  const sceneCortical = !!activeRow && activeRow.method === "flex" && activeRow.roi.mode === "cortical";

  function patchActiveRoi(next: RoiValue): void {
    if (!activeRow) return;
    setRows(rows.map((r) => (r.id === activeRow.id ? { ...r, roi: next } : r)));
  }

  function openViewer(): void {
    const subject = activeRow?.subjectId;
    if (!subject) return;
    navigate({ pathname: "/viewer", search: viewerSearch({ subject, kind: "subject" }) });
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
          /* Summary columns (Flex · Ex · mEx), so a cell counts its jobs. */
          cellDetail="counts"
          loading={planLoading}
          refetching={planRefetching}
          error={planError ? "Could not build the plan for this search." : undefined}
          onRefetch={refetchPlan}
          subjects={planSubjects}
          emptyMessage={blockedReason ?? "Add a job to see the plan."}
          pinnedJobId={pinnedJobId}
          startedJobIds={startedJobIds}
          onPinJob={setPinnedJobId}
          steps={stepsFor(planKind)}
          parallel={parallelSubjects}
          paneControls={<PaneHeaderControls controller={scenePane} />}
          scene={
            activeRow?.roi.mode !== "cortical"
              ? <TargetPreview subject={activeRow?.subjectId} roi={activeRow?.roi} />
              : <ScenePane
              mode="target"
              atlas={sceneCortical && activeRow?.roi.mode === "cortical" ? (activeRow.roi.atlas ?? null) : null}
              regions={sceneCortical && activeRow?.roi.mode === "cortical" ? activeRow.roi.regions : undefined}
              onAtlasChange={
                sceneCortical && activeRow?.roi.mode === "cortical"
                  ? (atlas) => patchActiveRoi({ ...(activeRow.roi as Extract<RoiValue, { mode: "cortical" }>), atlas })
                  : undefined
              }
              onRegionsChange={
                sceneCortical && activeRow?.roi.mode === "cortical"
                  ? (regions) => patchActiveRoi({ ...(activeRow.roi as Extract<RoiValue, { mode: "cortical" }>), regions })
                  : undefined
              }
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
      <RunWork fill={false}>
        {/*
         * JOBS: the one table where a run is described, first on the page and `data-tier="1"` (§8 —
         * never closed by the fill controller). It replaces the page-level Subjects table *and* the
         * global TARGET / ELECTRODES / OBJECTIVE / SOLVER sections: every one of those was a
         * property of a search, and a search is a row.
         *
         * Deliberately not a `FormSection` at the top level for the same reason the Simulator's is
         * not: that primitive registers with the fill controller, which was measured to oscillate a
         * page's first table open/closed once later content grew after mount.
         */}
        <div data-tier="1">
          <FormSection
            title="Jobs"
            summary={optimizerJobsSummary(rows, runnableRows)}
            helpSlot={
              <Popover trigger={<IconButton aria-label="About search jobs" icon={<Info size={13} />} variant="ghost" size="sm" />}>
                <div style={{ maxWidth: 360 }} className="text-dense">
                  One row is one search. Each row picks its own subject and its own method — flex over free
                  electrode positions, or an exhaustive two-channel (Ex) or four-pair (mEx) search over a
                  precomputed leadfield — and carries its own target, goal and parameters. Duplicate a row to
                  run the same search on another subject.
                </div>
              </Popover>
            }
          >
            <div style={{ gridColumn: "1 / -1" }}>
              {projectSubjects.length === 0 ? (
                <EmptyState
                  icon={<Workflow size={24} />}
                  message="No subjects in this project yet."
                  actionLabel="Go to Pre-processing"
                  onAction={() => navigate("/preprocess")}
                />
              ) : (
                <OptimizerJobRows
                  subjects={jobSubjects}
                  netsBySubject={netsBySubject}
                  leadfieldsBySubject={leadfieldsBySubject}
                  rows={rows}
                  onRowsChange={setRows}
                  activeRowId={activeRowId}
                  onActiveRowChange={setActiveRowId}
                  onGenerateLeadfield={(subject, net) => generateLeadfield.mutate({ subject, net })}
                  leadfieldGenerationState={leadfieldGenerationState}
                  onOpenViewer={openViewer}
                />
              )}
            </div>
          </FormSection>
        </div>

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
        existing={counts.existing}
        total={counts.jobs}
        noun="search output"
        busy={submit.isPending}
        onDecide={(decision) => {
          setConfirmOverwrite(false);
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
