import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Waves, Play, Info } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { SubjectsField, presenceColumns } from "../../_shared/subjects";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { NumberInput } from "../../../ui/NumberInput";
import { Checkbox } from "../../../ui/Toggle";
import { Button, IconButton } from "../../../ui/Button";
import { EmptyState } from "../../../ui/Feedback";
import { AlertDialog, Tooltip } from "../../../ui/Overlay";
import { notify } from "../../../ui/Toast";
import { isPanelEnabled } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { createSourceJob, getSimulationsFor, getSubjectDetail, planSource, validateSource, type SourceConfig } from "./api";
import { buildForwardConfig, buildFsavgConfig } from "./config";

/** The same readiness vocabulary every other page uses; this panel's data carries no dwi/ct. */
const SOURCE_COLUMNS = presenceColumns<{ id: string; has_raw: boolean; has_fastsurfer: boolean; has_freesurfer: boolean; has_m2m: boolean }>();

const SPACING_OPTIONS = [
  { value: "5", label: "5" },
  { value: "6", label: "6" },
  { value: "7", label: "7" },
];

const FSAVG_FIELDS: { name: string; label: string; help: string; defaultOn: boolean }[] = [
  { name: "TI_max", label: "TI max", help: "Envelope modulation depth, maximised over direction (V/m).", defaultOn: true },
  { name: "TI_normal", label: "TI normal", help: "Modulation depth along the cortical surface normal (V/m).", defaultOn: true },
  { name: "hf_peak", label: "hf peak", help: "Largest instantaneous magnitude of the summed carrier fields (V/m).", defaultOn: false },
  { name: "hf_sar", label: "hf SAR", help: "Sum of carrier power — proportional to SAR but not calibrated ((V/m)^2).", defaultOn: false },
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
      error={plan.error ? "Could not compute the plan." : undefined}
      serverErrors={serverErrors}
    />
  );
}

function SourcePanel() {
  const navigate = useNavigate();
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  usePageScrollMemory();
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

  function handleForwardClick() {
    if (!forwardConfig) {
      notify.error(selected.length === 0 ? "Select at least one subject first." : "No EEG net available for the selected subject.");
      return;
    }
    setFwdConfirm(true);
  }

  async function runForward(overwrite: boolean) {
    if (!forwardConfig) return;
    setFwdRunning(true);
    try {
      await createSourceJob({ ...forwardConfig, forward: { ...forwardConfig.forward!, overwrite } }, selected, overwrite);
      notify.success(selected.length === 1 ? `Queued: forward solution for ${selected[0]}` : `Queued ${selected.length} forward-solution jobs`);
    } catch {
      notify.error("Could not queue the forward-solution job.");
    } finally {
      setFwdRunning(false);
      setFwdConfirm(false);
    }
  }

  // --- Map fields to fsaverage ---
  const [perSubjectSim, setPerSubjectSim] = usePageSession<Record<string, string>>("fsaverage.simulations", {});
  const [fields, setFields] = usePageSession<string[]>("fsaverage.fields", () => FSAVG_FIELDS.filter((f) => f.defaultOn).map((f) => f.name));
  const [fsavgSpacing, setFsavgSpacing] = usePageSession("fsaverage.spacing", "5");
  const [workers, setWorkers] = usePageSession<number | undefined>("fsaverage.workers", 1);
  const [fsavgRunning, setFsavgRunning] = useState(false);
  const [fsavgConfirm, setFsavgConfirm] = useState(false);

  const simQueries = useQueries({ queries: selected.map((id) => ({ queryKey: ["simulations", id], queryFn: () => getSimulationsFor(id) })) });

  const pairs = selected
    .map((id, i) => ({ subject_id: id, simulation: perSubjectSim[id] ?? simQueries[i]?.data?.[0]?.name }))
    .filter((p): p is { subject_id: string; simulation: string } => !!p.simulation);

  const fsavgConfig: SourceConfig | null =
    pairs.length > 0 && fields.length > 0 ? buildFsavgConfig({ pairs, fields, fsaverageSpacing: Number(fsavgSpacing), workers: workers ?? 1, overwrite: false }) : null;

  function handleFsavgClick() {
    if (!fsavgConfig) {
      notify.error(pairs.length === 0 ? "Select at least one subject with a simulation." : "Pick at least one field to project.");
      return;
    }
    setFsavgConfirm(true);
  }

  async function runFsavg(overwrite: boolean) {
    if (!fsavgConfig) return;
    setFsavgRunning(true);
    try {
      await createSourceJob({ ...fsavgConfig, fsavg_map: { ...fsavgConfig.fsavg_map!, overwrite } }, pairs.map((p) => p.subject_id), overwrite);
      notify.success(pairs.length === 1 ? `Queued: fsaverage mapping for ${pairs[0]!.subject_id}` : `Queued ${pairs.length} fsaverage-mapping jobs`);
    } catch {
      notify.error("Could not queue the fsaverage-mapping job.");
    } finally {
      setFsavgRunning(false);
      setFsavgConfirm(false);
    }
  }

  function toggleField(name: string, on: boolean) {
    setFields((prev) => (on ? [...prev, name] : prev.filter((f) => f !== name)));
  }

  return (
    <PageLayout>
      <div className="panel-page">
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
            fill
            loading={subjectsQuery.isPending}
            help={
              <Tooltip label="Build EEG forward solutions and map simulation fields to fsaverage.">
                <IconButton icon={<Info size={13} />} aria-label="About this page" variant="ghost" size="sm" />
              </Tooltip>
            }
          />
          {subjectsQuery.data && subjectsWithModel.length === 0 && (
            <EmptyState icon={<Waves size={24} />} message="No subjects with a head model yet." actionLabel="Run pre-processing" onAction={() => navigate("/preprocess")} />
          )}
        </div>

        {/* The two pipelines are ALWAYS on the page, disabled until a subject is chosen (defect 4:
            an empty state shows the shape of what will appear). Before this the page answered "no
            subject yet" with one sentence and 400 px of ground — measured 82.3 % dead at 1280x800
            — and a user could not see what the page was even for without first picking someone. */}
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
                  <SourcePlan config={forwardConfig} subjectIds={selected} />
                  <Button variant="primary" size="lg" icon={<Play size={14} />} loading={fwdRunning} onClick={handleForwardClick} disabled={selected.length === 0}>
                    Build forward
                  </Button>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Map fields to fsaverage" />
              <CardBody>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                  {selected.length === 0 && (
                    <Field label="Simulation">
                      <span className="field-help">One row per selected subject.</span>
                    </Field>
                  )}
                  {selected.map((id, i) => (
                    <Field key={id} label={`Simulation — ${id}`} htmlFor={`source-fsavg-sim-${id}`}>
                      <Select
                        id={`source-fsavg-sim-${id}`}
                        value={perSubjectSim[id] ?? simQueries[i]?.data?.[0]?.name}
                        onValueChange={(v) => setPerSubjectSim((prev) => ({ ...prev, [id]: v }))}
                        options={(simQueries[i]?.data ?? []).map((s) => ({ value: s.name, label: s.name }))}
                        placeholder={simQueries[i]?.data?.length ? "Select…" : "No simulations yet"}
                      />
                    </Field>
                  ))}
                  <Field label="Fields">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
                      {FSAVG_FIELDS.map((f) => (
                        <Checkbox key={f.name} checked={fields.includes(f.name)} onCheckedChange={(on) => toggleField(f.name, on)} label={f.label} />
                      ))}
                    </div>
                  </Field>
                  <Field label="fsaverage spacing" htmlFor="source-fsavg-spacing">
                    <Select id="source-fsavg-spacing" value={fsavgSpacing} onValueChange={setFsavgSpacing} options={SPACING_OPTIONS} />
                  </Field>
                  <Field label="Workers" htmlFor="source-fsavg-workers" help="Subjects projected in parallel (1 = serial).">
                    <NumberInput id="source-fsavg-workers" value={workers} onValueChange={setWorkers} min={1} step={1} />
                  </Field>
                  <SourcePlan config={fsavgConfig} subjectIds={pairs.map((p) => p.subject_id)} />
                  <Button variant="primary" size="lg" icon={<Play size={14} />} loading={fsavgRunning} onClick={handleFsavgClick} disabled={selected.length === 0}>
                    Map to fsaverage
                  </Button>
                </div>
              </CardBody>
            </Card>
          </div>
        </div>
      </div>

      <AlertDialog
        open={fwdConfirm}
        onOpenChange={setFwdConfirm}
        title="Build forward solution?"
        description="If a forward solution already exists for a selected subject, it will be overwritten."
        confirmLabel="Build forward"
        confirmVariant="primary"
        onConfirm={() => void runForward(true)}
      />
      <AlertDialog
        open={fsavgConfirm}
        onOpenChange={setFsavgConfirm}
        title="Map fields to fsaverage?"
        description="If a projection already exists for a selected subject and simulation, it will be overwritten."
        confirmLabel="Map to fsaverage"
        confirmVariant="primary"
        onConfirm={() => void runFsavg(true)}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-source",
  title: "Source",
  purpose: "Build EEG forward solutions and map simulation fields to fsaverage.",
  navGroup: "panels",
  order: 100,
  icon: Waves,
  Component: SourcePanel,
  enabled: isPanelEnabled("source"),
};

export default page;
