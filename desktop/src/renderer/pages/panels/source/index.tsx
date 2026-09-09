import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Waves, Play } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { SubjectsField, presenceColumns } from "../../_shared/subjects";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { NumberInput } from "../../../ui/NumberInput";
import { Button } from "../../../ui/Button";
import { EmptyState } from "../../../ui/Feedback";
import { ExistingOutputsDialog } from "../../_shared/run/ExistingOutputsDialog";
import { notify } from "../../../ui/Toast";
import { isPanelEnabled } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { ExtensionRunPanel, useExtensionJobs } from "../ExtensionRunPanel";
import { createSourceJob, getSubjectDetail, planSource, validateSource, type SourceConfig } from "./api";
import { buildForwardConfig } from "./config";

/** The same readiness vocabulary every other page uses; this panel's data carries no dwi/ct. */
const SOURCE_COLUMNS = presenceColumns<{ id: string; has_raw: boolean; has_fastsurfer: boolean; has_freesurfer: boolean; has_m2m: boolean }>();

const SPACING_OPTIONS = [
  { value: "5", label: "5" },
  { value: "6", label: "6" },
  { value: "7", label: "7" },
];

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

/** Maps `{path, message}` server validation errors to plain sentences — never surfaces a raw
 * JSON-schema field path (e.g. "subject_id") to the user. Unrecognised paths fall back to the
 * server's own message rather than the path. */
function mapErrors(errors: { path: string; message: string }[]): string[] {
  return errors.map((e) => {
    switch (e.path) {
      case "subject_id":
      case "subject_ids":
        return "Select a subject.";
      case "pairs":
        return "Select at least one subject with a simulation.";
      default:
        return e.message;
    }
  });
}

function SourcePlan({ config, subjectIds }: { config: SourceConfig | null; subjectIds: string[] }) {
  const debouncedKey = useDebounced(config ? JSON.stringify({ config, subjectIds }) : "", 350);
  const parsed = debouncedKey ? (JSON.parse(debouncedKey) as { config: SourceConfig; subjectIds: string[] }) : null;
  const validateQuery = useQuery({
    queryKey: ["validate-source", debouncedKey],
    queryFn: () => validateSource(parsed!.config),
    enabled: parsed !== null && parsed.subjectIds.length > 0,
  });
  const plan = useQuery({
    queryKey: ["plan-source", debouncedKey],
    queryFn: () => planSource(parsed!.config, parsed!.subjectIds, false),
    enabled: parsed !== null && parsed.subjectIds.length > 0 && validateQuery.data?.ok === true,
  });

  if (!config || subjectIds.length === 0) return <p className="field-help">Pick a subject to see the plan.</p>;
  const serverErrors = mapErrors(validateQuery.data?.errors ?? []);
  return (
    <PlanSummary
      plan={plan.data}
      loading={validateQuery.isPending || plan.isFetching}
      error={validateQuery.error || plan.error ? "Could not compute the plan." : undefined}
      serverErrors={serverErrors}
    />
  );
}

function SourcePanel() {
  const navigate = useNavigate();
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  usePageScrollMemory();
  const jobs = useExtensionJobs();
  const [selected, setSelected] = usePageSession<string[]>("subjects", []);

  const allSubjects = useMemo(() => subjectsQuery.data ?? [], [subjectsQuery.data]);
  const subjectsWithModel = useMemo(() => allSubjects.filter((s) => s.has_m2m), [allSubjects]);
  // J3: a subject without a head model is *shown and explained* rather than filtered out of the
  // list — "my subject is missing from this page" is not a diagnosis a user can act on.
  const eligibility = (s: { has_m2m: boolean }) => (s.has_m2m ? { ok: true } : { ok: false, reason: "no head model (m2m)" });

  const detailQueries = useQueries({ queries: selected.map((id) => ({ queryKey: ["subject-detail", id], queryFn: () => getSubjectDetail(id) })) });
  const firstDetail = detailQueries[0]?.data;
  const eegNets = firstDetail?.eeg_nets ?? [];

  // --- Build forward solution ---
  const [net, setNet] = usePageSession<string | undefined>("forward.net", undefined);
  const [fwdSpacing, setFwdSpacing] = usePageSession("forward.spacing", "5");
  const [cpus, setCpus] = usePageSession<number | undefined>("forward.cpus", 1);
  const [fwdRunning, setFwdRunning] = useState(false);
  const [fwdConfirm, setFwdConfirm] = useState(false);

  // Re-pick a default net when the available list changes (new subject selection, or the first
  // subject's caps finish loading) — adjusted during render, not a `useEffect`, matching
  // `optimizer-flex/index.tsx`'s `setRoi` pattern (react-hooks/set-state-in-effect).
  const eegNetsKey = eegNets.join(",");
  const [prevEegNetsKey, setPrevEegNetsKey] = useState(eegNetsKey);
  if (eegNetsKey !== prevEegNetsKey) {
    setPrevEegNetsKey(eegNetsKey);
    if (!net || !eegNets.includes(net)) setNet(eegNets[0]);
  }

  const forwardConfig: SourceConfig | null =
    selected.length > 0 && net ? buildForwardConfig({ subjectIds: selected, eegNet: net, fsaverageSpacing: Number(fwdSpacing), cpus: cpus ?? 1, overwrite: false }) : null;

  /** The one signal that this run cannot start: the disabled button, with this as its tooltip. */
  const forwardBlocked = forwardConfig
    ? null
    : selected.length === 0
      ? "Select at least one subject first."
      : "No EEG net available for the selected subject.";

  const [existingForward, setExistingForward] = useState(0);

  async function handleForwardClick() {
    if (!forwardConfig) {
      notify.error(selected.length === 0 ? "Select at least one subject first." : "No EEG net available for the selected subject.");
      return;
    }
    setFwdRunning(true);
    try {
      const plan = await planSource(forwardConfig, selected, false);
      const existing = plan.jobs.filter((job) => job.exists).length;
      setExistingForward(existing);
      if (existing > 0) setFwdConfirm(true);
      else await runForward(false);
    } catch {
      notify.error("Could not check existing forward solutions. Try again before running.");
    } finally {
      setFwdRunning(false);
    }
  }

  async function runForward(overwrite: boolean) {
    if (!forwardConfig) return;
    setFwdRunning(true);
    try {
      const job = await createSourceJob({ ...forwardConfig, forward: { ...forwardConfig.forward!, overwrite } }, selected, overwrite);
      jobs.trackJob(job);
      notify.success(selected.length === 1 ? `Queued: forward solution for ${selected[0]}` : `Queued ${selected.length} forward-solution jobs`);
    } catch {
      notify.error("Could not queue the forward-solution job.");
    } finally {
      setFwdRunning(false);
      setFwdConfirm(false);
    }
  }

  return (
    <PageLayout rightPane={
      <ExtensionRunPanel kind="source" subjects={selected} {...jobs} plan={
        <>
          <section aria-label="Forward solution plan">
            <h3 className="card-title">Forward solution</h3>
            <SourcePlan config={forwardConfig} subjectIds={selected} />
          </section>
        </>
      } />
    }>
      <div className="panel-page extension-inputs">
        <div className="panel-page-split">
          <div className="panel-page-col">
        {/* L1: Subjects is the page's first SECTION, not a card titled "Subjects" wrapped around a
            control that already says "Subjects" — which is what this was, and which printed the
            word twice, 40px apart. The page-level (i) moves into the control's own help slot, the
            same place the four run pages put it. */}
        <div data-tier="1">
          <SubjectsField
            subjects={allSubjects}
            value={selected}
            onChange={setSelected}
            columns={SOURCE_COLUMNS}
            eligibility={eligibility}
            mode="per-subject"
            defaultOpen
            loading={subjectsQuery.isPending}
          />
          {subjectsQuery.data && subjectsWithModel.length === 0 && (
            <EmptyState icon={<Waves size={24} />} message="No subjects with a head model yet." actionLabel="Run pre-processing" onAction={() => navigate("/preprocess")} />
          )}
        </div>

          </div>
          <div className="panel-page-col">
            <Card>
              <CardHeader title="Build forward solution" />
              <CardBody>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                  <Field label="EEG net" htmlFor="source-fwd-net">
                    <Select id="source-fwd-net" value={net} onValueChange={setNet} options={eegNets.map((n) => ({ value: n, label: n }))} placeholder={eegNets.length ? "Select…" : "No caps available"} />
                  </Field>
                  <Field label="fsaverage spacing" htmlFor="source-fwd-spacing">
                    <Select id="source-fwd-spacing" value={fwdSpacing} onValueChange={setFwdSpacing} options={SPACING_OPTIONS} />
                  </Field>
                  <Field label="CPUs" htmlFor="source-fwd-cpus" help="SimNIBS FEM workers used while computing the leadfield.">
                    <NumberInput id="source-fwd-cpus" value={cpus} onValueChange={setCpus} min={1} step={1} />
                  </Field>
                  <Button variant="primary" size="lg" icon={<Play size={14} />} loading={fwdRunning} onClick={handleForwardClick} disabled={!!forwardBlocked} title={forwardBlocked ?? undefined}>
                    Build forward
                  </Button>
                </div>
              </CardBody>
            </Card>


          </div>
        </div>
      </div>

      <ExistingOutputsDialog
        open={fwdConfirm}
        onOpenChange={setFwdConfirm}
        existing={existingForward}
        total={selected.length}
        noun="forward solution"
        busy={fwdRunning}
        onDecide={(decision) => void runForward(decision === "replace")}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-source",
  title: "Source",
  purpose: "Build EEG forward solutions.",
  navGroup: "panels",
  order: 100,
  icon: Waves,
  Component: SourcePanel,
  enabled: isPanelEnabled("source"),
};

export default page;
