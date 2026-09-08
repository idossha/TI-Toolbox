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
import { IconButton } from "../../ui/Button";
import { Popover } from "../../ui/Overlay";
import { subjectsBlockedReason } from "../_shared/subjects";
import { getSubjectDetail } from "./api";
import { JobsTable, emptyDraft, type JobSubject, type MontageDraft } from "./MontageManager";
import { JobSettingsDialog } from "./JobSettingsDialog";
import "./simulator-page.css";
import { useSimPlan, RunButton } from "./RunControls";
import {
  DEFAULT_JOB_SETTINGS,
  emptyRow,
  isRunnableRow,
  type JobSettings,
  type MontagePreview,
  type MontageSource,
  type SelectedRow,
} from "./types";
import { RunPanel, RunWork, planDigest, stepsFor } from "../_shared/run";
import { ScenePane, withSlot } from "../_shared/scene";
import type { GlobalParams } from "./buildConfig";
import { FreehandDraftProvider, useFreehandDraft } from "./freehandDraft";
import { markerIndexOfRow, placementMarkers, rowOfMarkerIndex, savedMarkers } from "./freehandPlacement";

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

  /**
   * The settings a **new** row starts with: the ones the user last edited in a row's own dialog,
   * falling back to the built-in defaults. Not a page-level form any more (2026-09-06): the three
   * sections that used to sit under the table are gone, because every job now carries its own
   * electrodes, conductivity and output fields. Seeding from the last-edited row is what someone
   * assembling a batch expects — they configure one job and add the next like it — while `Reset to
   * defaults` in the dialog always means the built-ins.
   */
  const [seedSettings, setSeedSettings] = usePageSession<JobSettings | null>("jobSettingsSeed", null);
  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJob", null);
  // The jobs this Run press started: they keep their log and final status line in the terminal
  // after they finish, instead of the pane emptying itself the moment the run succeeds
  // (maintainer, 2026-09-07). Page-session state, like the pin, so navigating away and back keeps
  // the output; a new Run replaces it.
  const [startedJobIds, setStartedJobIds] = usePageSession<string[]>("startedJobs", []);
  // The montage editor's state, lifted here (SCC): the scene pane and the pairs editor are two
  // editors of ONE draft, which is what makes "click an electrode" and "pick it in the form" the
  // same act rather than two states that can disagree (plan decision S6).
  const [montageDraft, setMontageDraft] = usePageSession<MontageDraft | null>("montageDraft", null);
  const [montageNet, setMontageNet] = usePageSession<string | undefined>("montageNet", undefined);
  // Click-to-visualise: the job row the user clicked, drawn on the guide pane as its net's
  // electrodes plus its own pairs — read-only (no `onPairsChange`), so looking at a chosen montage
  // can never edit it. The draft, when one is open, is what the pane is FOR and wins.
  const [montagePreview, setMontagePreview] = useState<MontagePreview | null>(null);
  const [activeSource, setActiveSource] = useState<MontageSource | null>(null);
  /** The row whose own settings are being edited (`null` = the dialog is closed). */
  const [settingsRowId, setSettingsRowId] = useState<string | null>(null);
  const scenePane = usePaneController({ pageId: "simulator", name: "run" });
  const freehand = useFreehandDraft();

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

  /**
   * What a row that carries no settings of its own runs with, and what `Reset to defaults` returns
   * to: the built-ins (`DEFAULT_JOB_SETTINGS`), not a page control. A row seeded from the last
   * edited one carries a copy, so it shows as customised and is unaffected by anything else.
   */
  const params: GlobalParams = DEFAULT_JOB_SETTINGS as GlobalParams;

  // The subject clause of the blocked sentence is still the shared grammar's, but it is now about
  // the subjects the ROWS name rather than a page-level tick list.
  const subjectsBlocked = subjectsBlockedReason(
    planSubjects,
    planSubjects
      .map((id) => ({ id, reason: jobSubjects.find((s) => s.id === id)?.blockedReason }))
      .filter((b): b is { id: string; reason: string } => !!b.reason),
  );

  const plan = useSimPlan(runnableRows, params, planSubjects, runnableRows.length === 0 ? null : subjectsBlocked);

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
  /**
   * **Which head the pane draws.** The free-hand editor's subject while it is open — a placement is
   * a coordinate in that subject's own mesh and in no other — then the previewed row's subject,
   * then the shell's. `null` falls the pane back to the packaged guide, which is still the right
   * answer for a project whose head models do not exist yet.
   */
  const sceneSubject =
    (freehand.open ? (freehand.subject ?? usable[0]) : null) ?? montagePreview?.subject ?? shellSubject ?? usable[0] ?? null;

  /** The dots: the rows being placed, or the saved set the previewed job row runs. */
  const placedDots = useMemo(
    () => (freehand.open ? placementMarkers(freehand.positions) : montagePreview?.positions ? savedMarkers(montagePreview.positions) : undefined),
    [freehand.open, freehand.positions, montagePreview],
  );

  /**
   * The two ends of "which electrode is this". A row index is NOT a dot index — a blank row draws
   * no dot — so both directions go through `freehandPlacement`'s pair of converters.
   */
  const hoveredDot = freehand.open && freehand.hovered !== null ? markerIndexOfRow(freehand.positions, freehand.hovered) : -1;
  // Hover lights a dot; SELECTION rings and enlarges one. Two different signals, because they
  // answer two different questions ("which row is my cursor on" and "which electrode does the next
  // click move"), and they are frequently both true of different rows at once.
  const selectedDot = freehand.open && freehand.active !== null ? markerIndexOfRow(freehand.positions, freehand.active) : -1;
  const highlightMarkers = useMemo(() => (hoveredDot >= 0 ? [hoveredDot] : undefined), [hoveredDot]);
  const selectedMarkers = useMemo(() => (selectedDot >= 0 ? [selectedDot] : undefined), [selectedDot]);

  const runButton = (
    <RunButton
      rows={runnableRows}
      params={params}
      plan={plan}
      parallelSubjects={parallelSubjects}
      /* 2.5.0 kept its job cards after a run, and so does the table: the rows are what the user
         built, and a queued batch is very often the thing you then tweak and run again. */
      onSubmitted={(jobIds) => {
        // A new run takes the terminal over: drop any explicit pin and follow this press's jobs,
        // which stay in the pane after they finish (maintainer, 2026-09-07).
        setPinnedJobId(null);
        setStartedJobIds(jobIds);
      }}
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
            startedJobIds={startedJobIds}
            onPinJob={setPinnedJobId}
            steps={SIM_STEPS}
            parallel={parallelSubjects}
            paneControls={<PaneHeaderControls controller={scenePane} />}
            scene={
              <ScenePane
                mode="montage"
                /* The subject's own scalp, so a click on it is a millimetre in the head the job
                   runs on (maintainer, 2026-09-06). The guide remains the fallback and remains
                   what the Optimizer and the Analyzer draw. */
                subject={sceneSubject}
                onPlace={freehand.open ? freehand.place : undefined}
                onPlacedPick={freehand.open ? (index) => freehand.setActive(rowOfMarkerIndex(freehand.positions, index)) : undefined}
                onPlacedHover={
                  freehand.open ? (index) => freehand.setHovered(index === null ? null : rowOfMarkerIndex(freehand.positions, index)) : undefined
                }
                highlightMarkers={highlightMarkers}
                selectedMarkers={selectedMarkers}
                placedMarkers={placedDots}
                net={(montageDraft ? montageNet : (montagePreview?.net ?? montageNet)) ?? null}
                pairs={montageDraft?.pairs ?? (previewIsMontage ? montagePreview?.pairs : undefined)}
                showing={
                  !montageDraft && montagePreview
                    ? montagePreview.positions
                      ? /* A free-hand set has no net; say what it IS, so the chip never reads
                           "Showing: my_set · undefined". */
                        { montage: montagePreview.name, net: `${montagePreview.positions.length} placed positions` }
                      : previewIsMontage && montagePreview.net
                        ? { montage: montagePreview.name, net: montagePreview.net }
                        : null
                    : null
                }
                onPairsChange={montageDraft ? setDraftPairs : undefined}
                onRequestPairs={startDraftFromScene}
                note={
                  freehand.open || previewIsMontage || montagePreview?.positions
                    ? undefined
                    : "Flex jobs carry their own electrode positions — the preview shows the net, not the run."
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
                    defaults={params}
                    seedSettings={seedSettings ?? undefined}
                    onEditSettings={(row) => setSettingsRowId(row.id)}
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
        </RunWork>
      </PageLayout>
      <JobSettingsDialog
        row={rows.find((r) => r.id === settingsRowId) ?? null}
        defaults={params}
        onClose={() => setSettingsRowId(null)}
        onSave={(settings: JobSettings | undefined) => {
          setRows((prev) => prev.map((r) => (r.id === settingsRowId ? { ...r, settings } : r)));
          // The last row the user configured is what the next one starts from.
          setSeedSettings(settings ?? null);
          setSettingsRowId(null);
        }}
      />
    </>
  );
}

/**
 * The free-hand draft is provided ABOVE the page so the 3-D pane (rendered from
 * `PageLayout`'s `rightPane`) and the editor's table are two views of one array — a click on the
 * scalp and a typed millimetre are the same act. See `freehandDraft.tsx`.
 */
function SimulatorPageWithFreehandDraft() {
  return (
    <FreehandDraftProvider>
      <SimulatorPage />
    </FreehandDraftProvider>
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
  Component: SimulatorPageWithFreehandDraft,
  enabled: true,
};

export default page;
