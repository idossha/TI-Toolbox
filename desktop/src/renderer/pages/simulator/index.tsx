import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, Info, Workflow } from "lucide-react";
import { useQueries } from "@tanstack/react-query";
import type { Subject } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { useSubject } from "../../app/subjectContext";
import { useExecutionPrefs } from "../../app/executionPrefs";
import { usePageSession } from "../../app/pageSession";
import { EmptyState } from "../../ui/Feedback";
import { ActionBar } from "../../ui/Chrome";
import { FormSection, PageLayout, PaneHeaderControls, usePaneController } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Button, IconButton } from "../../ui/Button";
import { Checkbox } from "../../ui/Toggle";
import { Popover } from "../../ui/Overlay";
import { subjectsBlockedReason } from "../_shared/subjects";
import { getSubjectDetail } from "./api";
import { JobsTable, emptyDraft, type JobSubject, type MontageDraft } from "./MontageManager";
import { FreehandTab } from "./FreehandTab";
import { ConductivityDialog, type CustomConductivities } from "./ConductivityDialog";
import "./simulator-page.css";
import { useSimPlan, RunButton } from "./RunControls";
import {
  CONDUCTIVITY_OPTIONS,
  OUTPUT_FIELDS,
  OUTPUT_FIELDS_HELP,
  emptyRow,
  isRunnableRow,
  type MontageSource,
  type SelectedRow,
} from "./types";
import { RunPanel, RunWork, planDigest, stepsFor } from "../_shared/run";
import { ScenePane, withSlot } from "../_shared/scene";
import type { GlobalParams } from "./buildConfig";

/** The collapsed ELECTRODES section states its own values (DESIGN.md v3 §4.2 rule 5). */
export function electrodeSummary(shape: "ellipse" | "rect", dims: [number, number], gel: number): string {
  return `${shape === "ellipse" ? "ellipse" : "rectangle"} · ${dims[0]}×${dims[1]} mm · gel ${gel} mm`;
}

/** Same, for CONDUCTIVITY: the model plus how many tissue values were overridden. */
export function conductivitySummary(model: string, overrides: number): string {
  const label = CONDUCTIVITY_OPTIONS.find((o) => o.value === model)?.label ?? model;
  return `${label.toLowerCase()} · ${overrides === 0 ? "SimNIBS defaults" : `${overrides} override${overrides === 1 ? "" : "s"}`}`;
}

/** The primary's label, from the plan. */
export function runLabelFor(rowCount: number): string {
  if (rowCount <= 1) return "Run simulation";
  return `Run ${rowCount} simulations`;
}

/**
 * The Jobs section's summary line: how many rows are jobs, over how many subjects — the sentence
 * 2.5.0's "This will run N simulation(s)" confirmation made, stated continuously rather than only
 * at the moment of pressing Run.
 */
export function jobsSummary(rows: SelectedRow[]): string {
  const runnable = rows.filter(isRunnableRow);
  if (rows.length === 0) return "no jobs yet";
  const subjects = new Set(runnable.map((r) => r.subjectId)).size;
  const incomplete = rows.length - runnable.length;
  const head =
    runnable.length === 0
      ? "no complete job"
      : `${runnable.length} job${runnable.length === 1 ? "" : "s"} · ${subjects} subject${subjects === 1 ? "" : "s"}`;
  return incomplete > 0 ? `${head} · ${incomplete} incomplete` : head;
}

/**
 * This page's readiness verdict per subject, handed to the Jobs table's own Subject cell — the
 * subject grammar's J3 rule ("state *why*, and refuse to pick it") applied inside a row rather
 * than in a page-wide table (which is the control the jobs rework removed: the row owns the
 * subject now, so a global subject set had nothing left to decide).
 */
export function jobSubjectsFrom(subjects: Subject[]): JobSubject[] {
  const anyModel = subjects.some((s) => s.has_m2m);
  return subjects.map((s) => ({
    id: s.id,
    blockedReason: s.has_m2m || !anyModel ? undefined : "no head model (m2m)",
  }));
}

/** The Simulator's steps never vary with the configuration — one montage runs the same five. */
const SIM_STEPS = stepsFor("sim");

function SimulatorPage() {
  const navigate = useNavigate();
  const { id: shellSubject, subjects } = useSubject();
  // `usePageSession`, not `useState`, for everything the *user* decided (lane N2): this page
  // unmounts on every navigation, so a plain `useState` meant a step onto Results discarded the
  // jobs they had assembled and the sections they had opened.
  const [rows, setRows] = usePageSession<SelectedRow[]>("jobRows", []);

  const [conductivity, setConductivity] = usePageSession("conductivity", "scalar");
  const [customConductivities, setCustomConductivities] = usePageSession<CustomConductivities>("conductivityOverrides", {});
  const [conductivityDialogOpen, setConductivityDialogOpen] = useState(false);
  const [electrodeShape, setElectrodeShape] = usePageSession<"ellipse" | "rect">("electrodeShape", "ellipse");
  const [dimensions, setDimensions] = usePageSession<[number, number]>("electrodeDims", [8, 8]);
  const [gelThickness, setGelThickness] = usePageSession("gelThickness", 4);
  const [outputFields, setOutputFields] = usePageSession<string[]>("outputFields", ["TI_max"]);
  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);
  // The montage editor's state, lifted here (SCC): the scene pane and the pairs editor are two
  // editors of ONE draft, which is what makes "click an electrode" and "pick it in the form" the
  // same act rather than two states that can disagree (plan decision S6).
  const [montageDraft, setMontageDraft] = usePageSession<MontageDraft | null>("montageDraft", null);
  const [montageNet, setMontageNet] = usePageSession<string | undefined>("montageNet", undefined);
  // Click-to-visualise: the job row the user clicked, drawn on the guide pane as its net's
  // electrodes plus its own pairs — read-only (no `onPairsChange`), so looking at a chosen montage
  // can never edit it. The draft, when one is open, is what the pane is FOR and wins.
  const [montagePreview, setMontagePreview] = useState<{ net: string; name: string; pairs: [string, string][] } | null>(null);
  const [activeSource, setActiveSource] = useState<MontageSource | null>(null);
  const scenePane = usePaneController({ pageId: "simulator", name: "run" });

  const jobSubjects = useMemo(() => jobSubjectsFrom(subjects), [subjects]);
  const usable = useMemo(() => jobSubjects.filter((s) => !s.blockedReason).map((s) => s.id), [jobSubjects]);

  const subjectDetailQueries = useQueries({
    queries: usable.map((id) => ({ queryKey: ["subject-detail", id], queryFn: () => getSubjectDetail(id), staleTime: 60_000 })),
  });
  // Derived every render, not memoized: `useQueries` hands back a fresh array each render, so a
  // `useMemo` over it could only be keyed on a serialisation (see `RunControls.tsx`'s `useSimPlan`).
  const subjectNets: Record<string, string[]> = {};
  usable.forEach((id, i) => {
    subjectNets[id] = subjectDetailQueries[i]?.data?.eeg_nets ?? [];
  });

  // The page starts with one empty job row seeded on the shell's primary subject: a table whose
  // first act is "press Add job" would make the page's own subject a thing to discover.
  const [seeded, setSeeded] = useState(false);
  if (!seeded && rows.length === 0 && usable.length > 0) {
    setSeeded(true);
    setRows([emptyRow(shellSubject && usable.includes(shellSubject) ? shellSubject : (usable[0] as string))]);
  }

  /** Rows that are actually jobs: a half-filled row is shown, never planned or submitted. */
  const runnableRows = useMemo(() => rows.filter(isRunnableRow), [rows]);
  const planSubjects = useMemo(() => [...new Set(runnableRows.map((r) => r.subjectId))], [runnableRows]);

  const params: GlobalParams = useMemo(
    () => ({ conductivity, electrodeShape, dimensions, gelThickness, outputFields, customConductivities }),
    [conductivity, electrodeShape, dimensions, gelThickness, outputFields, customConductivities],
  );

  // The subject clause of the blocked sentence is still the shared grammar's, but it is now about
  // the subjects the ROWS name rather than a page-level tick list.
  const subjectsBlocked = subjectsBlockedReason(
    planSubjects,
    planSubjects
      .map((id) => ({ id, reason: jobSubjects.find((s) => s.id === id)?.blockedReason }))
      .filter((b): b is { id: string; reason: string } => !!b.reason),
  );

  const plan = useSimPlan(runnableRows, params, planSubjects, runnableRows.length === 0 ? null : subjectsBlocked);
  const overrides = Object.keys(customConductivities).length;

  const digest = plan.model ? planDigest(plan.model) : (plan.blockedReason ?? "Resolving the plan…");

  function setDraftPairs(pairs: [string, string][]): void {
    setMontageDraft((draft) => (draft ? { ...draft, pairs } : { ...emptyDraft(), pairs }));
  }
  /** A pick with no montage open starts one, with that electrode already in pair 1 slot A —
   *  otherwise the first click on the pane would do nothing and the gesture would be undiscoverable. */
  function startDraftFromScene(electrode: string): void {
    const fresh = emptyDraft();
    setMontageDraft({ ...fresh, pairs: withSlot(fresh.pairs, 0, electrode) });
  }
  const runButton = (
    <RunButton
      rows={runnableRows}
      params={params}
      plan={plan}
      parallelSubjects={parallelSubjects}
      /* 2.5.0 kept its job cards after a run, and so does the table: the rows are what the user
         built, and a queued batch is very often the thing you then tweak and run again. */
      onSubmitted={() => undefined}
      label={runLabelFor(runnableRows.length)}
    />
  );

  const previewIsMontage = activeSource === null || activeSource === "montage";

  return (
    <>
      <PageLayout
        variant="run"
        rightPaneKind="run"
        paneController={scenePane}
        rightPane={
          <RunPanel
            kind="sim"
            plan={plan.model}
            /* Summary columns (Montage · Flex · Free-hand), so a cell counts its jobs. */
            cellDetail="counts"
            loading={plan.loading}
            refetching={plan.refetching}
            error={plan.error}
            onRefetch={plan.refetch}
            subjects={planSubjects}
            emptyMessage={plan.blockedReason ?? "Add a job to see the plan."}
            pinnedJobId={pinnedJobId}
            onPinJob={setPinnedJobId}
            steps={SIM_STEPS}
            parallel={parallelSubjects}
            paneControls={<PaneHeaderControls controller={scenePane} />}
            scene={
              <ScenePane
                mode="montage"
                net={(montageDraft ? montageNet : (montagePreview?.net ?? montageNet)) ?? null}
                pairs={montageDraft?.pairs ?? (previewIsMontage ? montagePreview?.pairs : undefined)}
                showing={previewIsMontage && !montageDraft && montagePreview ? { montage: montagePreview.name, net: montagePreview.net } : null}
                onPairsChange={montageDraft ? setDraftPairs : undefined}
                onRequestPairs={startDraftFromScene}
                note={
                  previewIsMontage
                    ? undefined
                    : "Flex and free-hand jobs carry their own electrode positions — the preview shows the net, not the run."
                }
              />
            }
          />
        }
          actionBar={<ActionBar digest={digest} blocked={!!plan.blockedReason} primary={runButton} />}
      >
        <RunWork>
          {/*
           * JOBS (2026-09-06 rework): the one table where a run is described, first on the page and
           * `data-tier="1"` (§8 — never closed by `RunWork`'s fill controller). It replaces the
           * page-level Subjects table *and* the three source tabs: a row carries its own subject,
           * its own source, its own montage and its own currents, which is what 2.5.0's job cards
           * did and what the v3 cross-product could not express.
           *
           * It is deliberately not a `FormSection`: that primitive registers with the fill
           * controller, which was measured to oscillate the page's first table open/closed once
           * later page content grew after mount.
           */}
          <div data-tier="1">
            <FormSection
              title="Jobs"
              summary={jobsSummary(rows)}
              helpSlot={
                <Popover trigger={<IconButton aria-label="About simulation jobs" icon={<Info size={13} />} variant="ghost" size="sm" />}>
                  <div style={{ maxWidth: 340 }} className="text-dense">
                    One row is one simulation job. Each row picks its own subject and its own source — a montage from the
                    catalog, an optimised electrode set from a flex-search run, or a saved free-hand placement — and carries
                    its own currents. Duplicate a row to run the same job on another subject.
                  </div>
                </Popover>
              }
            >
              <div style={{ gridColumn: "1 / -1" }}>
                {subjects.length === 0 ? (
                  <EmptyState
                    icon={<Workflow size={24} />}
                    message="No subjects in this project yet."
                    actionLabel="Go to Pre-processing"
                    onAction={() => navigate("/preprocess")}
                  />
                ) : (
                  <JobsTable
                    subjects={jobSubjects}
                    subjectNets={subjectNets}
                    rows={rows}
                    onRowsChange={setRows}
                    draft={montageDraft}
                    onDraftChange={setMontageDraft}
                    onNetChange={setMontageNet}
                    onPreviewChange={setMontagePreview}
                    onActiveSourceChange={setActiveSource}
                  />
                )}
              </div>
            </FormSection>
          </div>

          {subjects.length > 0 && (
            <>
              <FormSection
                title="Electrodes"
                collapsible
                defaultOpen={false}
                changed={electrodeShape !== "ellipse" || dimensions[0] !== 8 || dimensions[1] !== 8 || gelThickness !== 4}
                summary={electrodeSummary(electrodeShape, dimensions, gelThickness)}
              >
                {/* Shape, dimensions and gel thickness are one decision about one object, and
                    three narrow controls; `.field-row-inline` keeps them on a single line. */}
                <div className="field-row-inline">
                  <Field label="Shape">
                    <SegmentedControl
                      value={electrodeShape}
                      onValueChange={(v) => setElectrodeShape(v as "ellipse" | "rect")}
                      options={[
                        { value: "ellipse", label: "Ellipse" },
                        { value: "rect", label: "Rectangle" },
                      ]}
                      aria-label="Electrode shape"
                    />
                  </Field>
                  <Field label="Dimensions">
                    <div style={{ display: "flex", gap: "var(--space-2)" }}>
                      <NumberInput value={dimensions[0]} onValueChange={(v) => setDimensions([v ?? 8, dimensions[1]])} unit="w" step={0.5} min={0} aria-label="Electrode width" />
                      <NumberInput value={dimensions[1]} onValueChange={(v) => setDimensions([dimensions[0], v ?? 8])} unit="h" step={0.5} min={0} aria-label="Electrode height" />
                    </div>
                  </Field>
                  <Field label="Gel thickness" className="sim-gel-field">
                    <NumberInput value={gelThickness} onValueChange={(v) => setGelThickness(v ?? 4)} step={0.5} min={0} unit="mm" />
                  </Field>
                </div>
              </FormSection>

              <FormSection
                title="Conductivity"
                collapsible
                defaultOpen={false}
                changed={conductivity !== "scalar" || overrides > 0}
                summary={conductivitySummary(conductivity, overrides)}
              >
                <div className="field-row-inline">
                  <Field label="Model">
                    <Select value={conductivity} onValueChange={setConductivity} options={CONDUCTIVITY_OPTIONS} />
                  </Field>
                  <Field label="Tissue values" help="Overrides SimNIBS's per-tissue defaults for this run only.">
                    <Button variant="secondary" onClick={() => setConductivityDialogOpen(true)}>
                      Edit tissue conductivities…
                    </Button>
                  </Field>
                </div>
              </FormSection>

              <FormSection
                title="Output fields"
                collapsible
                defaultOpen={false}
                changed={outputFields.length !== 1 || outputFields[0] !== "TI_max"}
                error={outputFields.length === 0}
                summary={outputFields.join(", ") || "none"}
                helpSlot={
                  <Popover trigger={<IconButton aria-label="Output fields help" icon={<Info size={13} />} variant="ghost" size="sm" />}>
                    <div style={{ maxWidth: 360, whiteSpace: "pre-wrap" }} className="text-dense">
                      {OUTPUT_FIELDS_HELP}
                    </div>
                  </Popover>
                }
              >
                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
                    {OUTPUT_FIELDS.map((f) => (
                      <label key={f.name} title={f.description} className="checkbox-label-row">
                        <Checkbox
                          checked={outputFields.includes(f.name)}
                          onCheckedChange={(checked) => setOutputFields((prev) => (checked ? [...prev, f.name] : prev.filter((n) => n !== f.name)))}
                        />
                        {f.name}
                      </label>
                    ))}
                  </div>
                  {outputFields.length === 0 && <span className="field-error">Select at least one output field.</span>}
                </div>
              </FormSection>

              {/*
               * Free-hand placements are AUTHORED here and CHOSEN in a job row's Montage cell — the
               * same split the montage catalog has (its editor is inside the table's own "New
               * montage"). Collapsed by default: writing electrode coordinates by hand is rare
               * next to picking a montage.
               */}
              <FormSection title="Free-hand placements" collapsible defaultOpen={false} summary="author XYZ electrode sets">
                <div style={{ gridColumn: "1 / -1" }}>
                  <FreehandTab subjects={usable} />
                </div>
              </FormSection>
            </>
          )}
        </RunWork>
      </PageLayout>
      <ConductivityDialog open={conductivityDialogOpen} onOpenChange={setConductivityDialogOpen} value={customConductivities} onSave={setCustomConductivities} />
    </>
  );
}

const page: PageDef = {
  id: "simulator",
  title: "Simulator",
  purpose: "Configure and run TI / mTI simulations.",
  navGroup: "pipeline",
  order: 20,
  icon: Zap,
  // DESIGN.md §9 binding shortcut map: Simulator is Cmd/Ctrl+3.
  shortcut: "3",
  Component: SimulatorPage,
  enabled: true,
};

export default page;
