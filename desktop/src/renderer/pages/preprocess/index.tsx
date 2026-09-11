import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { getSurferSettings, putSurferSettings, type SurferSettings } from "../settings/api";
import { Workflow } from "lucide-react";
import { getSubjects, type Subject } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { useSubject } from "../../app/subjectContext";
import { useExecutionPrefs } from "../../app/executionPrefs";
import { usePageSession, usePageSessionRef } from "../../app/pageSession";
import { createAjvResolver } from "../../forms/ajvResolver";
import { Button } from "../../ui/Button";
import { ActionBar } from "../../ui/Chrome";
import { InlineError } from "../../ui/Feedback";
import { PageLayout } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { SubjectsField, notConvertedColumn, presenceColumns, subjectsBlockedReason } from "../_shared/subjects";
import {
  RunPanel,
  RunWork,
  planDigest,
  planModelFrom,
  stepsFor,
  planCounts,
  ExistingOutputsDialog,
  useRunShortcut,
  type PlanModel,
  type PlanStage,
} from "../_shared/run";
import {
  getSubjectDetail,
  planPre,
  submitPreGroup,
  type PlanResult,
  type PreprocessConfig,
  type QsiPrepSettings,
  type QsiReconSettings,
} from "./api";
import { defaultQsiPrepConfig, defaultQsiReconConfig, qsiPrepPreferences, qsiReconPreferences } from "./qsi";
import { QsiPrepDialog } from "./QsiPrepDialog";
import { QsiReconDialog } from "./QsiReconDialog";
import { PreprocessSteps } from "./PreprocessSteps";
import { defaultConfig } from "./config";
import "./preprocess.css";

export type ExistingOutputPolicy = "skip" | "replace";

/** A catalog row plus the two booleans only `GET /api/catalog/subjects/{id}` carries. */
type SubjectRow = Subject & { has_dwi?: boolean; has_ct?: boolean };

/**
 * Pre-processing shows the whole readiness set — this is the general case J3 names, and the other
 * run pages take a subset of the same columns rather than inventing their own.
 */
const PRE_COLUMNS = [...presenceColumns<SubjectRow>({ dwi: true, ct: true }), notConvertedColumn<SubjectRow>()];

export { defaultConfig } from "./config";

export function toSubmitConfig(
  values: PreprocessConfig,
  subjectIds: string[],
  policy: ExistingOutputPolicy,
  preferences?: SurferSettings,
): PreprocessConfig {
  return {
    ...values,
    subject_ids: subjectIds,
    fastsurfer_threads: null,
    freesurfer_threads: null,
    charm_threads: null,
    charm_options: preferences?.charm_options ?? null,
    freesurfer_recon_all: preferences?.freesurfer_recon_all ?? true,
    freesurfer_subregions: preferences?.freesurfer_subregions ?? ["thalamus", "hippo-amygdala"],
    qsiprep_config: values.run_qsiprep ? { ...(preferences?.qsiprep_config ?? values.qsiprep_config ?? defaultQsiPrepConfig()), cpus: preferences?.effective_qsiprep_threads ?? null, memory_gb: preferences?.qsiprep_memory_gb ?? null, omp_threads: preferences?.qsiprep_omp_threads ?? preferences?.effective_qsiprep_threads ?? 1 } : null,
    qsi_recon_config: values.run_qsirecon ? { ...(preferences?.qsi_recon_config ?? values.qsi_recon_config ?? defaultQsiReconConfig()), cpus: preferences?.effective_qsirecon_threads ?? null, memory_gb: preferences?.qsirecon_memory_gb ?? null, omp_threads: preferences?.qsirecon_omp_threads ?? preferences?.effective_qsirecon_threads ?? 1 } : null,
    skip_existing_outputs: policy === "skip",
    replace_existing_outputs: policy === "replace",
  };
}

/** Execution order mirrors `run_pipeline` in `tit/pre/structural.py` exactly. */
/**
 * The stage ids this configuration will run, in `tit.jobs.plans.plan_preprocessing`'s own G1..G6
 * order (FXU1). They are both the plan matrix's columns and the terminal preview's step list, so
 * the two can never disagree about what is about to happen.
 */
export function plannedStageIds(v: PreprocessConfig): string[] {
  const ids: string[] = [];
  if (v.convert_dicom) ids.push("G1");
  if (v.create_m2m) ids.push("G2a");
  if (v.run_fastsurfer) ids.push("G2b");
  if (v.run_freesurfer) ids.push("G2c");
  if (v.run_tissue_analysis) ids.push("G3");
  if (v.run_qsiprep) ids.push("G4");
  if (v.run_qsirecon) ids.push("G5");
  if (v.extract_dti) ids.push("G6");
  // No "report" id: the subject report is an attachment of the job that produced it, so it is
  // neither a stage column nor a job (maintainer, 2026-09-07).
  return ids;
}

/** Column headings for the plan matrix, one per stage above. */
const PRE_STAGE_HEADING: Record<string, string> = {
  G1: "dicom",
  G2a: "charm",
  G2b: "fastsurfer",
  G2c: "freesurfer",
  G3: "tissue",
  G4: "qsiprep",
  G5: "qsirecon",
  G6: "dti",
};

export function plannedSteps(v: PreprocessConfig): string[] {
  const steps: string[] = [];
  if (v.convert_dicom) steps.push("Convert DICOM to NIfTI");
  if (v.create_m2m) steps.push("SimNIBS charm + subject atlas");
  if (v.run_fastsurfer) steps.push("FastSurfer segmentation");
  if (v.run_freesurfer) steps.push("FreeSurfer reconstruction / subregions");
  if (v.run_tissue_analysis) steps.push("Tissue analysis");
  if (v.run_qsiprep) steps.push("QSIPrep");
  if (v.run_qsirecon) steps.push("QSIRecon");
  if (v.extract_dti) steps.push("Extract DTI tensor for SimNIBS");
  return steps;
}

/**
 * Best-effort label for one preprocessing stage's `PlanJob.output_dir`, for kind=pre plans that
 * carry one `PlanJob` per stage (`tit.jobs.plans.plan_preprocessing`'s G1-G6 DAG, wired up
 * server-side in `tit/server/routes/plan.py`) rather than one per subject. Matches the directory
 * conventions `_pre_stage_output_dir` maps each stage flag to; falls back to a generic label for
 * a shared/coarser directory (several stages can touch the same `m2m_<subject>/`) or for a plan
 * response that only carries one row per subject (e.g. an older backend).
 */
export function describePreStageDir(dir: string): string {
  if (/qsirecon/i.test(dir)) return "QSIRecon";
  if (/qsiprep/i.test(dir)) return "QSIPrep";
  if (/fastsurfer/i.test(dir)) return "FastSurfer segmentation";
  if (/freesurfer/i.test(dir)) return "FreeSurfer reconstruction / subregions";
  if (/m2m_/i.test(dir)) return "SimNIBS m2m (charm / atlas / DTI)";
  if (/nifti|dicom|sourcedata/i.test(dir)) return "DICOM to NIfTI";
  return "Output";
}

/**
 * Human-readable stage label for one `PlanJob`. Prefers the server's own `job.stage`/`job.label`
 * (ra_13 finding 12 — not in the contract yet, see `PlanJob` in `api.ts`) over the client-side
 * directory-name guess, so this page picks up the real label the moment a backend starts sending
 * one without any change here.
 */
export function stageLabelFor(job: { stage?: string; label?: string; output_dir: string }): string {
  return job.stage ?? job.label ?? describePreStageDir(job.output_dir);
}

/** The primary's label, from the plan: "Run preprocessing" for one subject, "Queue N jobs" past that. */
export function runLabelFor(subjectCount: number, jobCount: number): string {
  if (subjectCount <= 1) return "Run preprocessing";
  return `Queue ${jobCount || subjectCount} job${(jobCount || subjectCount) === 1 ? "" : "s"}`;
}

/** Debounces a value; the Plan panel re-fetches `POST /api/plan/pre` this long after the last edit. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

function PreprocessPage() {
  const { selection: shellSelection, id: shellSubject } = useSubject();
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  const subjects = useMemo<Subject[]>(() => subjectsQuery.data ?? [], [subjectsQuery.data]);

  // Seeded from the shell's subject spine, then page-owned: the batch table is this page's
  // Tier-1 control and must not re-scope the whole app when a row is unticked.
  // Session-scoped, per page (lane N2): this page unmounts on every navigation, so a plain
  // `useState` here threw the batch selection away every time the user looked at Jobs.
  const [selected, setSelected] = usePageSession<string[]>("subjects", () => shellSelection);
  const [lastShellSubject, setLastShellSubject] = useState(shellSubject);
  if (shellSubject !== lastShellSubject) {
    setLastShellSubject(shellSubject);
    if (shellSubject && !selected.includes(shellSubject)) setSelected([shellSubject, ...selected]);
  }

  const detailQueries = useQueries({
    queries: subjects.map((s) => ({
      queryKey: ["subject-detail", s.id],
      queryFn: () => getSubjectDetail(s.id),
      staleTime: 60_000,
    })),
  });
  // One row model for the shared control: the list row, plus the two booleans (`dwi`, `ct`) that
  // only the per-subject detail carries. A row whose detail has not landed yet simply reads those
  // two columns as missing rather than dropping them, so the table's columns never go ragged.
  const rows = useMemo<SubjectRow[]>(
    () =>
      subjects.map((s, i) => {
        const d = detailQueries[i]?.data;
        return { ...s, has_dwi: d?.has_dwi, has_ct: d?.has_ct };
      }),
    [subjects, detailQueries],
  );

  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const policy: ExistingOutputPolicy = "skip";
  const [qsiPrepOpen, setQsiPrepOpen] = useState(false);
  const [qsiReconOpen, setQsiReconOpen] = useState(false);
  const [existingOpen, setExistingOpen] = useState(false);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);
  // The jobs this Run press started: they keep their log and final status line in the terminal
  // after they finish, instead of the pane emptying itself the moment the run succeeds
  // (maintainer, 2026-09-07). Page-session state, like the pin, so navigating away and back keeps
  // the output; a new Run replaces it.
  const [startedJobIds, setStartedJobIds] = usePageSession<string[]>("startedJobs", []);

  // The checked steps are the user's too (N2). React Hook Form keeps them in its own store, which
  // dies with the component like any other, so the bag seeds `defaultValues` once and a
  // subscription writes every change back. Imperative (`usePageSessionRef`), not `usePageSession`:
  // `form.watch()` returns a fresh object on every render, so mirroring it through React state
  // would re-render on its own output for ever.
  const { read: readConfig, write: writeConfig } = usePageSessionRef<PreprocessConfig>("config");
  const form = useForm<PreprocessConfig>({
    resolver: createAjvResolver<PreprocessConfig>("PreprocessConfig"),
    defaultValues: { ...defaultConfig(), ...readConfig() },
  });
  const preferences = useQuery({ queryKey: ["surfer-settings"], queryFn: getSurferSettings });
  const queryClient = useQueryClient();
  const saveQsi = useMutation({ mutationFn: putSurferSettings,
    onSuccess: (next) => queryClient.setQueryData(["surfer-settings"], next),
    onError: (error) => notify.error(error.message),
  });
  const values = form.watch();
  useEffect(() => {
    const sub = form.watch((v) => writeConfig(v as PreprocessConfig));
    return () => sub.unsubscribe();
  }, [form, writeConfig]);

  const submitConfig = useMemo(() => toSubmitConfig(values, selected, policy, preferences.data), [values, selected, policy, preferences.data]);
  const steps = useMemo(() => plannedSteps(values), [values]);
  const stageIds = useMemo(() => plannedStageIds(values), [values]);
  // Columns = every stage this configuration runs, in run order — not only the ones the plan
  // happened to return a job for (FXU1). `stageIds` is a stable string, so the memo is honest.
  const stageColumns: PlanStage[] = useMemo(
    () => stageIds.map((id) => ({ id, label: PRE_STAGE_HEADING[id] ?? id })),
    [stageIds],
  );
  const previewSteps = useMemo(() => stepsFor("pre", stageIds), [stageIds]);
  const debouncedPlanKey = useDebouncedValue(JSON.stringify({ submitConfig, selected }), 400);

  const planQuery = useQuery({
    queryKey: ["plan-pre", debouncedPlanKey],
    queryFn: () => planPre(submitConfig, selected, false),
    enabled: selected.length > 0 && steps.length > 0,
  });

  // Every page's subject-side blocked wording comes from one function (J3); this page adds only
  // its own second clause. A sourcedata-only subject stays eligible — the DICOM stage is exactly
  // what onboards it (lane FX5) — so this page passes no `eligibility` and can only ever be
  // blocked by an empty selection.
  const blockedReason = subjectsBlockedReason(selected, [])
    ?? (steps.length === 0 ? "Select at least one processing step." : null)
    ?? (preferences.isPending ? "Loading pre-processing preferences…" : preferences.error ? "Could not load pre-processing preferences." : null)
    ?? (values.run_freesurfer && !submitConfig.freesurfer_recon_all && !submitConfig.freesurfer_subregions?.length
      ? "Select at least one FreeSurfer operation." : null);

  const plan: PlanModel | null = useMemo(() => {
    if (blockedReason) return null;
    const result = planQuery.data as PlanResult | undefined;
    if (!result) return null;
    return planModelFrom("pre", result, selected, { stages: stageColumns });
  }, [blockedReason, planQuery.data, selected, stageColumns]);

  const submit = useMutation({
    // The policy comes from the decision, not from the page's own control: the shared
    // existing-outputs dialog is what the user just answered, and pressing "Replace and rerun"
    // there has to mean replace even if the segmented control below still says skip.
    mutationFn: (decision: ExistingOutputPolicy) =>
      submitPreGroup(toSubmitConfig(values, selected, decision, preferences.data), selected, parallelSubjects),
    onSuccess: (result) => {
      // `result.jobs.length` is not one-per-subject: the mock (and the real `plan_preprocessing`
      // DAG it mirrors) expands each subject into one job per configured stage (the subject
      // report is an attachment of the last of those, never a job), so it is reported as a job
      // *count* alongside the subject count the user actually chose.
      notify.success(
        selected.length > 1
          ? `Queued preprocessing for ${selected.length} subjects (${result.jobs.length} jobs).`
          : `Queued preprocessing for ${selected[0]}.`,
      );
      // A new run takes the terminal over: drop any explicit pin and follow this press's jobs.
      setPinnedJobId(null);
      setStartedJobIds(result.jobs.map((job) => job.id));
    },
    onError: () => notify.error("Could not queue preprocessing.", "Check the connection and try again."),
  });

  function runNow(decision: ExistingOutputPolicy = policy): void {
    submit.mutate(decision);
  }

  function handleRunClick(): void {
    // §4.2 rule 8: the primary stays enabled and pressing it with an unresolvable plan says why,
    // rather than a silently dead button.
    if (blockedReason) {
      notify.error(blockedReason);
      return;
    }
    // One question, one wording, on all four run pages (C3): if anything already has output, the
    // shared dialog asks — it is never decided silently by whatever the segmented control says.
    if (counts.existing > 0) {
      setExistingOpen(true);
      return;
    }
    runNow();
  }

  useRunShortcut(handleRunClick);

  const counts = planCounts(plan);
  const digest = plan ? planDigest(plan) : (blockedReason ?? "Resolving the plan…");
  const jobCount = plan?.stats.jobs ?? 0;

  return (
    // No page header: the nav rail already says which page this is (DESIGN.md §2.3).
    <PageLayout
      variant="run"
      rightPaneKind="run"
      rightPane={
        <RunPanel
          kind="pre"
          plan={plan}
          loading={selected.length > 0 && steps.length > 0 && planQuery.isPending && planQuery.fetchStatus !== "idle"}
          refetching={planQuery.isRefetching}
          error={planQuery.error ? "Could not build the plan for the selected subjects." : undefined}
          onRefetch={() => void planQuery.refetch()}
          subjects={selected}
          emptyMessage={blockedReason ?? "Select a subject to see the plan."}
          pinnedJobId={pinnedJobId}
          startedJobIds={startedJobIds}
          onPinJob={setPinnedJobId}
          steps={previewSteps}
          parallel={parallelSubjects}
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
              {runLabelFor(selected.length, jobCount)}
            </Button>
          }
        />
      }
    >
      <RunWork>
        {/* Subjects (J1/J2): the one shared control, first, on every page that takes subjects.
            Open on mount here because batch selection *is* what this page is for — everywhere
            else it opens on the summary row's disclosure. */}
        <div data-tier="1">
          <SubjectsField
            subjects={rows}
            value={selected}
            onChange={setSelected}
            columns={PRE_COLUMNS}
            mode="per-subject"
            defaultOpen
            fill
            loading={subjectsQuery.isPending}
          />
          {subjectsQuery.error && (
            <InlineError message="Could not load the subject list." onAction={() => void subjectsQuery.refetch()} />
          )}
        </div>

        <PreprocessSteps values={values} onChange={(patch) => Object.entries(patch).forEach(([key,value]) => form.setValue(key as keyof PreprocessConfig, value))} onQsiPrep={() => setQsiPrepOpen(true)} onQsiRecon={() => setQsiReconOpen(true)} />

      </RunWork>

      <QsiPrepDialog
        open={qsiPrepOpen}
        onOpenChange={setQsiPrepOpen}
        initial={{ ...defaultQsiPrepConfig(), ...(preferences.data?.qsiprep_config ?? values.qsiprep_config) }}
        onSave={(cfg: QsiPrepSettings) => saveQsi.mutate({ qsiprep_config: qsiPrepPreferences(cfg) })}
      />
      <QsiReconDialog
        open={qsiReconOpen}
        onOpenChange={setQsiReconOpen}
        initial={{ ...defaultQsiReconConfig(), ...(preferences.data?.qsi_recon_config ?? values.qsi_recon_config) }}
        onSave={(cfg: QsiReconSettings) => saveQsi.mutate({ qsi_recon_config: qsiReconPreferences(cfg) })}
      />
      <ExistingOutputsDialog
        open={existingOpen}
        onOpenChange={setExistingOpen}
        existing={counts.existing}
        total={counts.jobs}
        noun="pre-processing output"
        busy={submit.isPending}
        onDecide={(decision) => {
          setExistingOpen(false);
          runNow(decision);
        }}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "preprocess",
  title: "Pre-processing",
  purpose: "Convert, segment, and prepare subjects for simulation.",
  navGroup: "pipeline",
  order: 10,
  icon: Workflow,
  shortcut: "2",
  Component: PreprocessPage,
  enabled: true,
};

export default page;
