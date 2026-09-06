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
import { SubjectsField, blockedSubjects, presenceColumns, subjectsBlockedReason } from "../_shared/subjects";
import { getSubjectDetail } from "./api";
import { MontageManager, emptyDraft, type MontageDraft } from "./MontageManager";
import { FlexTab } from "./FlexTab";
import { FreehandTab } from "./FreehandTab";
import { ConductivityDialog, type CustomConductivities } from "./ConductivityDialog";
import { useSimPlan, RunButton } from "./RunControls";
import { CONDUCTIVITY_OPTIONS, OUTPUT_FIELDS, OUTPUT_FIELDS_HELP, type SelectedRow } from "./types";
import { Receipt, RunPanel, RunWork, planDigest, stepsFor, useRunStatusCells } from "../_shared/run";
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
 * U16: the context bar's own subject switcher is gone (U11), so this page's own Subjects table
 * seeds itself from the shell's primary subject the same way `pages/preprocess/index.tsx` does —
 * a change to the primary (the command palette's "Change subject") is folded into the page's own
 * selection rather than silently ignored, but only by *adding* it: unticking it here afterwards
 * must not be fought by every render.
 */
export function seedWithShellSubject(current: string[], shellSubject: string | null): string[] {
  if (!shellSubject || current.includes(shellSubject)) return current;
  return [shellSubject, ...current];
}

/**
 * Subjects a simulation can actually target: every ticked subject that has a head model built —
 * the same rule the Source panel's own subject picker applies (`pages/panels/source/index.tsx`).
 * Falls back to the full ticked list when the project has no `m2m` subjects at all (nothing to
 * compare against, matching this page's pre-U16 behaviour) rather than an always-empty plan.
 */
export function eligibleSubjectsFor(selected: string[], subjectsWithModel: string[]): string[] {
  return selected.filter((id) => subjectsWithModel.length === 0 || subjectsWithModel.includes(id));
}

/** The subset of the shared readiness columns this page's data supports (no dwi/ct detail read). */
const SIM_COLUMNS = presenceColumns<Subject>();

/** The Simulator's steps never vary with the configuration — one montage runs the same five. */
const SIM_STEPS = stepsFor("sim");

function SimulatorPage() {
  const navigate = useNavigate();
  // U16: U11 deleted the context bar's own subject switcher, which was the only writer for
  // `useSubject().batch` — so a multi-subject run is reachable again only through a control this
  // page owns, seeded from (and kept loosely in step with) the shell's primary subject. Page-owned
  // and page-local: unlike the old batch store, unticking a row here never re-scopes another page.
  const { id: shellSubject, subjects } = useSubject();
  // `usePageSession`, not `useState`, for everything the *user* decided (lane N2): this page
  // unmounts on every navigation, so a plain `useState` meant a step onto Results discarded the
  // montage they had assembled and the sections they had opened. A transient (a dialog's open
  // flag, the shell-subject sync sentinel) stays `useState` — reopening a modal on return is not
  // "where they left off".
  const [selectedSubjects, setSelectedSubjects] = usePageSession<string[]>("subjects", () =>
    shellSubject ? [shellSubject] : [],
  );
  const [lastShellSubject, setLastShellSubject] = useState(shellSubject);
  if (shellSubject !== lastShellSubject) {
    setLastShellSubject(shellSubject);
    setSelectedSubjects((prev) => seedWithShellSubject(prev, shellSubject));
  }
  const [tab, setTab] = usePageSession<"montage" | "flex" | "freehand">("sourceTab", "montage");
  const [rows, setRows] = usePageSession<SelectedRow[]>("rows", []);

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
  const scenePane = usePaneController({ pageId: "simulator", name: "run" });

  const subjectsWithModel = useMemo(() => subjects.filter((s) => s.has_m2m).map((s) => s.id), [subjects]);
  const eligible = useMemo(
    () => eligibleSubjectsFor(selectedSubjects, subjectsWithModel),
    [selectedSubjects, subjectsWithModel],
  );
  // J3: the page states *why* a subject cannot be used and the control refuses to tick it —
  // rather than the page silently dropping it from `eligible` on the way to the plan, which is
  // what it did before. The fallback (no m2m subject anywhere) is `eligibleSubjectsFor`'s: with
  // nothing to compare against, nothing is blocked.
  const eligibility = useMemo(
    () => (s: Subject) =>
      s.has_m2m || subjectsWithModel.length === 0
        ? { ok: true }
        : { ok: false, reason: "no head model (m2m)" },
    [subjectsWithModel],
  );
  const subjectsBlocked = subjectsBlockedReason(selectedSubjects, blockedSubjects(subjects, selectedSubjects, eligibility));

  const subjectDetailQueries = useQueries({
    queries: eligible.map((id) => ({ queryKey: ["subject-detail", id], queryFn: () => getSubjectDetail(id) })),
  });
  const subjectNets = useMemo(() => {
    const map: Record<string, string[]> = {};
    eligible.forEach((id, i) => {
      map[id] = subjectDetailQueries[i]?.data?.eeg_nets ?? [];
    });
    return map;
  }, [eligible, subjectDetailQueries]);

  function addRow(row: SelectedRow) {
    setRows((prev) => (prev.some((r) => r.id === row.id) ? prev : [...prev, row]));
  }
  function removeRow(id: string) {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }
  function updateRowCurrents(id: string, currents: string) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, currents } : r)));
  }

  // Selections tied to a subject that leaves the context-bar selection no longer make sense — drop
  // them so the plan and the job list never silently outlive the subject that owns them.
  const visibleRows = useMemo(() => rows.filter((r) => eligible.includes(r.subjectId)), [rows, eligible]);

  const params: GlobalParams = useMemo(
    () => ({ conductivity, electrodeShape, dimensions, gelThickness, outputFields, customConductivities }),
    [conductivity, electrodeShape, dimensions, gelThickness, outputFields, customConductivities],
  );

  const plan = useSimPlan(visibleRows, params, selectedSubjects, subjectsBlocked);
  const overrides = Object.keys(customConductivities).length;
  useRunStatusCells("sim", eligible, plan.model);

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
      rows={visibleRows}
      params={params}
      plan={plan}
      parallelSubjects={parallelSubjects}
      onSubmitted={() => setRows([])}
      label={runLabelFor(visibleRows.length)}
    />
  );

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
            loading={plan.loading}
            refetching={plan.refetching}
            error={plan.error}
            onRefetch={plan.refetch}
            subjects={eligible}
            emptyMessage={plan.blockedReason ?? "Select a montage to see the plan."}
            pinnedJobId={pinnedJobId}
            onPinJob={setPinnedJobId}
            steps={SIM_STEPS}
            parallel={parallelSubjects}
            paneControls={<PaneHeaderControls controller={scenePane} />}
            scene={
              <ScenePane
                mode="montage"
                net={montageNet ?? null}
                pairs={montageDraft?.pairs}
                onPairsChange={tab === "montage" ? setDraftPairs : undefined}
                onRequestPairs={tab === "montage" ? startDraftFromScene : undefined}
                note={tab === "montage" ? undefined : "Flex and free-hand sources carry their own electrode positions — the preview shows the net, not the run."}
              />
            }
          />
        }
          receipt={<Receipt plan={plan.model} blockedReason={plan.blockedReason} />}
          actionBar={<ActionBar digest={digest} blocked={!!plan.blockedReason} primary={runButton} />}
      >
        <RunWork>
          {/*
           * Subjects (J1/J2): the one shared control, first on the page, `data-tier="1"` (§8 —
           * never closed by `RunWork`'s fill controller, matching the contract
           * `firstScreenControls` reads). It is deliberately not a `FormSection`: that primitive
           * registers with the fill controller, which was measured to oscillate this table
           * open/closed once later page content grew after mount.
           *
           * Open by default (R3): every subject-taking workflow shows the selector on first
           * visit, so a user never has to discover that a page takes more than one subject. The
           * disclosure state is page-session memory from there on, so shutting it sticks while
           * the user works — which is the headroom a real 4-pair mTI montage editor needs at
           * 1280×900.
           */}
          <div data-tier="1">
            <SubjectsField
              subjects={subjects}
              value={selectedSubjects}
              onChange={setSelectedSubjects}
              columns={SIM_COLUMNS}
              eligibility={eligibility}
              mode="per-subject"
              defaultOpen
            />
          </div>

          {selectedSubjects.length === 0 ? (
            <EmptyState
              icon={<Workflow size={24} />}
              message={subjects.length === 0 ? "No subjects in this project yet." : "Select a subject above to configure a simulation."}
              actionLabel={subjects.length === 0 ? "Go to Pre-processing" : undefined}
              onAction={subjects.length === 0 ? () => navigate("/preprocess") : undefined}
            />
          ) : (
            <>
              <div data-tier="1">
                <FormSection
                  title="Source"
                  summary={`${visibleRows.length} selected`}
                  helpSlot={
                    <Popover trigger={<IconButton aria-label="About simulation sources" icon={<Info size={13} />} variant="ghost" size="sm" />}>
                      <div style={{ maxWidth: 320 }} className="text-dense">
                        A montage from the catalog, an optimised electrode set from a flex-search run, or a free-hand
                        placement. Every ticked entry becomes one job per selected subject.
                      </div>
                    </Popover>
                  }
                >
                  <div style={{ gridColumn: "1 / -1" }}>
                    <SegmentedControl
                      value={tab}
                      onValueChange={(v) => setTab(v)}
                      options={[
                        { value: "montage", label: "Montage" },
                        { value: "flex", label: "Flex result" },
                        { value: "freehand", label: "Free-hand" },
                      ]}
                      aria-label="Montage source"
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1" }}>
                    {tab === "montage" && (
                      <MontageManager
                        selectedSubjects={eligible}
                        subjectNets={subjectNets}
                        selectedRows={rows}
                        onAddRow={addRow}
                        onRemoveRow={removeRow}
                        onCurrentsChange={updateRowCurrents}
                        draft={montageDraft}
                        onDraftChange={setMontageDraft}
                        onNetChange={setMontageNet}
                      />
                    )}
                    {tab === "flex" && (
                      <FlexTab selectedSubjects={eligible} selectedRows={rows} onAddRow={addRow} onRemoveRow={removeRow} />
                    )}
                    {tab === "freehand" && (
                      <FreehandTab selectedSubjects={eligible} selectedRows={rows} onAddRow={addRow} onRemoveRow={removeRow} />
                    )}
                  </div>
                </FormSection>
              </div>

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
                  <Field label="Gel thickness">
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
                <Field label="Model">
                  <Select value={conductivity} onValueChange={setConductivity} options={CONDUCTIVITY_OPTIONS} />
                </Field>
                <Field label="Tissue values" help="Overrides SimNIBS's per-tissue defaults for this run only.">
                  <Button variant="secondary" onClick={() => setConductivityDialogOpen(true)}>
                    Edit tissue conductivities…
                  </Button>
                </Field>
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
