/**
 * The Optimizer's **Jobs table** — one row per search, and the row owns its inputs.
 *
 * The grammar is the one the Simulator and the Analyzer already speak (DESIGN.md §4.7, lane JB):
 *
 *  * a **two-line entry** per job — line 1 is what the job *is*
 *    (`Subject · Method · Net/Leadfield · Goal`), line 2 is what it will *do* (the target in
 *    words, then the method's own summary), and the whole of line 2 is the button that opens the
 *    row's editor;
 *  * **fixed geometry**: a `<colgroup>` whose widths come from `resolveOptColumnWidths` (which
 *    sums to the container by construction) plus `table-layout: fixed`, so a row switching from
 *    Flex to mEx changes what is *inside* its cells and moves nothing anywhere else;
 *  * **resizable columns** on the header boundaries, persisted under this table's own key;
 *  * an **active-row wash** covering both lines — one job, one highlight — which is also what the
 *    3-D pane is drawing (`onActiveRowChange`).
 *
 * The row editor is a dialog **per method**, assembled from the very same `FlexSections` /
 * `ExSections` this page already had, scoped to one row's own form state. Nothing was rewritten
 * to fit the table: the sections took `{form, onChange}` from the start, which is exactly what a
 * row can hand them.
 */
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Copy, Pencil, Plus, Target as TargetIcon, X } from "lucide-react";
import { Button, IconButton } from "../../ui/Button";
import { Dialog } from "../../ui/Overlay";
import { Field, TextInput } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { SelectionPicker } from "../../ui/SelectionList";
import { RoiPicker, type RoiValue } from "../_shared/roi";
import type { EegNet, Leadfield } from "./api";
import { ElectrodesSection, ObjectiveSection, PostRunSection, SolverSection } from "./FlexSections";
import { ExCurrentSection, ExElectrodesSection, LeadfieldStrip, MExCarrierSection, MExElectrodesSection } from "./ExSections";
import { formatBytes } from "./exConfig";
import { electrodesForNet, leadfieldPathFor, netKey, netOptions } from "./nets";
import { flexFormForMethod, isFlexMethod, GOAL_LABEL, OPT_METHODS, optimizerAvoidLabel, optimizerMethodSummary, optimizerTargetLabel, roiModesFor, rowGoal, withMethod, emptyOptimizerRow, newOptimizerRowId, readStoredOptColumns, resolveOptColumnWidths, writeStoredOptColumns, type OptColumnKey, type OptColumnWidths, type OptimizerRow, type OptMethod, type StoredOptColumns } from "./rows";
import type { OptGoal } from "./flexConfig";
import "./optimizer.css";

/** A subject as the table sees it: usable, or listed with the reason it is not. */
export interface OptimizerSubject {
  id: string;
  /** `undefined` when the subject has a head model; otherwise the J3 wording. */
  blockedReason?: string;
}

const GOAL_OPTIONS: { value: OptGoal; label: string }[] = [
  { value: "mean", label: "mean" },
  { value: "max", label: "max" },
  { value: "focality", label: "focality" },
  { value: "focality_tf", label: "focality_tf" },
];

/** One header boundary — pointer capture and arrow keys, the pane divider's own gesture. */
function ColumnHandle({ label, width, onResize }: { label: string; width: number; onResize: (next: number) => void }) {
  return (
    <button
      type="button"
      className="opt-col-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      tabIndex={0}
      onPointerDown={(e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = width;
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        const onMove = (ev: PointerEvent) => onResize(startWidth + (ev.clientX - startX));
        const onUp = () => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      }}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        e.stopPropagation();
        onResize(width + (e.key === "ArrowRight" ? 16 : -16));
      }}
    />
  );
}

/** Measures the table container and resolves the colgroup against it. */
function useColumnWidths(): {
  box: React.MutableRefObject<HTMLDivElement | null>;
  width: number;
  cols: OptColumnWidths;
  setColumn: (key: OptColumnKey, px: number) => void;
} {
  const box = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  const [stored, setStored] = useState<StoredOptColumns>(() =>
    readStoredOptColumns(typeof window === "undefined" ? undefined : window.localStorage),
  );
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const cols = useMemo(() => resolveOptColumnWidths(width, stored), [width, stored]);
  function setColumn(key: OptColumnKey, px: number): void {
    setStored((prev) => {
      const next = { ...prev, [key]: Math.round(px) };
      writeStoredOptColumns(typeof window === "undefined" ? undefined : window.localStorage, next);
      return next;
    });
  }
  return { box, width, cols, setColumn };
}

export function OptimizerJobRows({
  subjects,
  netsBySubject,
  leadfieldsBySubject,
  rows,
  onRowsChange,
  activeRowId,
  onActiveRowChange,
  onGenerateLeadfield,
  generatingLeadfield,
  onOpenViewer,
}: {
  subjects: OptimizerSubject[];
  /** `GET /api/catalog/eeg-nets` per subject — a row's own net options. */
  netsBySubject: Record<string, EegNet[] | undefined>;
  /** `GET /api/catalog/leadfields` per subject — the Ex/mEx Leadfield cell's options. */
  leadfieldsBySubject: Record<string, Leadfield[] | undefined>;
  rows: OptimizerRow[];
  onRowsChange: (next: OptimizerRow[]) => void;
  activeRowId: string | null;
  onActiveRowChange: (id: string) => void;
  /** Queues leadfield generation for (subject, net) — the "create one" the refusal offers. */
  onGenerateLeadfield: (subject: string, net: string) => void;
  generatingLeadfield: boolean;
  onOpenViewer?: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const { box, width, cols, setColumn } = useColumnWidths();

  const patch = (id: string, next: Partial<OptimizerRow>) =>
    onRowsChange(rows.map((r) => (r.id === id ? { ...r, ...next } : r)));

  // Derived, not synchronised: a row removed while its editor is open resolves to `null` here and
  // the editor renders nothing — there is no state to put back in step, so there is no effect.
  /**
   * Keyboard on the table: ↑/↓ move the active row (the wash and the 3-D pane follow), Enter opens
   * that row's editor. Typing inside a cell's own control is that control's, so the handler steps
   * aside for anything that is not the row itself.
   */
  function onTableKeyDown(e: React.KeyboardEvent<HTMLTableElement>): void {
    if (rows.length === 0) return;
    const inControl = (e.target as HTMLElement).closest("input, textarea, [role='combobox'], [role='dialog']");
    if (e.key === "Enter") {
      if (inControl) return;
      const id = activeRowId ?? rows[0]?.id;
      if (!id) return;
      e.preventDefault();
      setEditingId(id);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    if (inControl) return;
    e.preventDefault();
    const at = rows.findIndex((r) => r.id === activeRowId);
    const next = e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : Math.max(0, (at === -1 ? 0 : at) - 1);
    onActiveRowChange(rows[next]!.id);
    e.currentTarget.querySelectorAll<HTMLElement>("tbody tr.opt-job-line1")[next]?.focus();
  }

  const editing = rows.find((r) => r.id === editingId) ?? null;

  /** Subject options for one row: the whole project, blocked ones listed with their reason. */
  function subjectItems(row: OptimizerRow) {
    return subjects.map((s) => {
      const reason = s.blockedReason ?? leadfieldReason(row, s.id);
      return { id: s.id, label: s.id, reason, disabled: !!reason };
    });
  }

  /** Why this subject cannot run THIS row — the Ex/mEx half of the J3 wording. */
  function leadfieldReason(row: OptimizerRow, subject: string): string | undefined {
    if (isFlexMethod(row.method)) return undefined;
    const lfs = leadfieldsBySubject[subject];
    // Still loading: a picker must not call a subject "no leadfield" while its request is in flight.
    if (lfs === undefined) return undefined;
    return lfs.some((lf) => lf.exists) ? undefined : "no leadfield — create one first";
  }

  /** The Net / Leadfield cell's options for a row. */
  function netCellOptions(row: OptimizerRow): { value: string; label: string; disabled?: boolean }[] {
    const nets = netsBySubject[row.subjectId];
    const lfs = leadfieldsBySubject[row.subjectId];
    if (isFlexMethod(row.method)) {
      // Flex places electrodes freely; a net is only needed to MAP the result onto real positions.
      return [
        { value: OPTIMISED, label: "Optimised positions" },
        ...(nets ?? []).map((n) => ({ value: netKey(n.name), label: netKey(n.name) })),
      ];
    }
    // Ex/mEx: the leadfields this subject actually has, then the nets it does not — listed with
    // the reason, unselectable, so "there is no leadfield for GSN-HydroCel-185" is a fact the cell
    // states rather than an option that silently fails.
    const ready = (lfs ?? []).filter((lf) => lf.exists);
    const readyKeys = new Set(ready.map((lf) => netKey(lf.net)));
    return [
      ...ready.map((lf) => ({ value: netKey(lf.net), label: `${netKey(lf.net)} · ${formatBytes(lf.size_bytes)}` })),
      ...netOptions(lfs, nets)
        .filter((o) => !readyKeys.has(o.value))
        .map((o) => ({ value: o.value, label: `${o.label} — no leadfield`, disabled: true })),
    ];
  }

  function addRow(): void {
    const last = rows[rows.length - 1];
    const seed = last
      ? { subjectId: last.subjectId, method: last.method, net: last.net }
      : { subjectId: subjects.find((s) => !s.blockedReason)?.id };
    const next = emptyOptimizerRow(seed);
    onRowsChange([...rows, next]);
    // Active, NOT open: adding a row and configuring it are two acts (coordinator, 2026-09-06).
    // A dialog that opens itself takes the keyboard away from someone adding three rows in a row.
    onActiveRowChange(next.id);
  }

  function duplicate(row: OptimizerRow): void {
    const at = rows.findIndex((r) => r.id === row.id);
    const copy = { ...row, id: newOptimizerRowId() };
    onRowsChange([...rows.slice(0, at + 1), copy, ...rows.slice(at + 1)]);
    onActiveRowChange(copy.id);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div className="data-table-container" ref={box} data-testid="opt-jobs-table-container">
        <table className="data-table opt-jobs-table" onKeyDown={onTableKeyDown} data-testid="opt-jobs-table">
          <colgroup>
            <col style={{ width: width ? cols.subject : "17%" }} />
            <col style={{ width: width ? cols.method : "24%" }} />
            <col style={{ width: width ? cols.net : "36%" }} />
            <col style={{ width: width ? cols.goal : "23%" }} />
            <col style={{ width: width ? cols.actions : "96px" }} />
          </colgroup>
          <thead>
            <tr>
              <th data-column="subject">
                Subject
                <ColumnHandle label="Subject" width={cols.subject} onResize={(w) => setColumn("subject", w)} />
              </th>
              <th data-column="method">
                Method
                <ColumnHandle label="Method" width={cols.method} onResize={(w) => setColumn("method", w)} />
              </th>
              <th data-column="net">
                {/* The column is one idea under two names: what carries the electrodes. Flex reads
                    it as an EEG net to map onto, Ex/mEx as the leadfield the search runs over. */}
                Net / leadfield
                <ColumnHandle label="Net" width={cols.net} onResize={(w) => setColumn("net", w)} />
              </th>
              <th data-column="goal">
                Goal
                <ColumnHandle label="Goal" width={cols.goal} onResize={(w) => setColumn("goal", w)} />
              </th>
              <th data-column="actions" />
            </tr>
          </thead>
          {rows.map((row, i) => {
            const goal = rowGoal(row);
            const target = optimizerTargetLabel(row.roi);
            const avoid = optimizerAvoidLabel(row);
            const line2 = [target, avoid, optimizerMethodSummary(row)].filter(Boolean).join(" · ");
            const active = activeRowId === row.id;
            const claim = (e: React.MouseEvent) => {
              if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
              onActiveRowChange(row.id);
            };
            return (
              /* One job is one `<tbody>` of two `<tr>`s — the Analyzer's shape, so the two lines
                 share one hover, one wash and one set of row attributes. */
              <tbody
                key={row.id}
                className="opt-job-group"
                data-opt-row={row.id}
                data-subject={row.subjectId || undefined}
                data-method={row.method}
                data-net={row.net ?? undefined}
                data-target-ready={target === "Choose a target…" ? "false" : "true"}
                data-active={active ? "true" : undefined}
                aria-selected={active}
                onClick={claim}
                /* A single click only moves the active-row focus; the *second* click is the one
                   that means "let me change this" — the same gesture a file gets in a file list. */
                onDoubleClick={(e) => {
                  if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
                  onActiveRowChange(row.id);
                  setEditingId(row.id);
                }}
                onFocus={() => onActiveRowChange(row.id)}
              >
                <tr className="opt-job-line1" tabIndex={0}>
                  <td data-cell="subject">
                    <SelectionPicker
                      mode="single"
                      label="Subject"
                      items={subjectItems(row)}
                      value={row.subjectId ? [row.subjectId] : []}
                      onChange={(v) => {
                        const next = v[0];
                        if (!next) return;
                        // A net/leadfield the new subject does not have is not a job — clear it
                        // rather than carrying a row the plan will refuse.
                        const keeps =
                          row.net === null ||
                          row.net === OPTIMISED ||
                          (isFlexMethod(row.method)
                            ? (netsBySubject[next] ?? []).some((n) => netKey(n.name) === row.net)
                            : leadfieldPathFor(leadfieldsBySubject[next], row.net) !== null);
                        patch(row.id, { subjectId: next, net: keeps ? row.net : null });
                      }}
                      placeholder="Subject"
                      headers={{ label: "Subject", reason: "Why not" }}
                      hideBulk
                      idPrefix={`opt-subject-${row.id}`}
                      triggerTestId={`opt-subject-${row.id}`}
                    />
                  </td>
                  <td data-cell="method">
                    <Select
                      value={row.method}
                      onValueChange={(v) => onRowsChange(rows.map((r) => (r.id === row.id ? withMethod(r, v as OptMethod) : r)))}
                      options={OPT_METHODS.map((m) => ({ value: m.value, label: m.label }))}
                      aria-label="Method"
                    />
                  </td>
                  <td data-cell="net">
                    <Select
                      value={netCellValue(row)}
                      onValueChange={(v) => patch(row.id, { net: v === OPTIMISED ? null : v })}
                      options={netCellOptions(row)}
                      placeholder={row.subjectId ? (isFlexMethod(row.method) ? "Optimised positions" : "No leadfield — create one") : "Pick a subject"}
                      disabled={!row.subjectId || netCellOptions(row).length === 0}
                      aria-label={isFlexMethod(row.method) ? "EEG net" : "Leadfield"}
                    />
                  </td>
                  <td data-cell="goal">
                    {goal === null ? (
                      // Ex/mEx enumerate montages and rank them by the ROI field; there is no goal
                      // to choose, so the cell says so rather than offering a dead control.
                      <span className="opt-goal-na" title="Ex and mEx rank every montage by the ROI field — there is no optimisation goal to choose.">
                        —
                      </span>
                    ) : (
                      <Select
                        value={goal}
                        onValueChange={(v) => patch(row.id, { flex: { ...row.flex, goal: v as OptGoal } })}
                        options={GOAL_OPTIONS}
                        // Flex adaptive / Flex Pareto ARE focality: the method cell already made
                        // this choice, and a second control that could disagree with it is the
                        // thing the method vocabulary exists to remove.
                        disabled={row.method !== "flex"}
                        aria-label="Goal"
                      />
                    )}
                  </td>
                  {/* One actions cell for the whole two-line job, its buttons on line 1. The flex
                      row is an inner <div>, not the <td> itself: `display: flex` on a cell makes
                      the browser drop its `rowSpan`, which left the other 29px of the cell
                      unpainted — a white notch at the right edge of every active row. */}
                  <td data-cell="actions" className="opt-actions" rowSpan={2}>
                    <div className="opt-actions-row">
                    <IconButton aria-label={`Duplicate job ${i + 1}`} icon={<Copy size={14} />} onClick={() => duplicate(row)} />
                    <IconButton
                      aria-label={`Edit job ${i + 1}`}
                      icon={<Pencil size={14} />}
                      onClick={() => {
                        onActiveRowChange(row.id);
                        setEditingId(row.id);
                      }}
                    />
                    <IconButton
                      aria-label={`Remove job ${i + 1}`}
                      icon={<X size={14} />}
                      onClick={() => onRowsChange(rows.filter((r) => r.id !== row.id))}
                    />
                    </div>
                  </td>
                </tr>
                <tr className="opt-job-line2">
                  {/* Line 2 states the target and the search, and IS the way into the row's own
                      editor — the Analyzer's target button, widened to carry the method summary
                      too, because an optimisation's cost is the other half of "what will this
                      row do". */}
                  <td data-cell="target" colSpan={4}>
                    <button
                      type="button"
                      className="opt-target-button"
                      data-testid={`opt-target-${row.id}`}
                      data-empty={target === "Choose a target…" ? "true" : undefined}
                      title={line2}
                      aria-label={`Configure job ${i + 1}: ${line2}`}
                      onClick={() => {
                        onActiveRowChange(row.id);
                        setEditingId(row.id);
                      }}
                    >
                      <span className="opt-target-caption text-eyebrow">Target</span>
                      <TargetIcon size={12} aria-hidden />
                      <span className="opt-target-text">{line2}</span>
                    </button>
                  </td>
                </tr>
              </tbody>
            );
          })}
        </table>
      </div>

      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }} data-testid="opt-jobs-footer">
        <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={addRow}>
          Add job
        </Button>
      </div>

      <RowEditor
        row={editing}
        onClose={() => setEditingId(null)}
        onChange={(next) => patch(next.id, next)}
        nets={editing ? (netsBySubject[editing.subjectId] ?? []) : []}
        leadfields={editing ? leadfieldsBySubject[editing.subjectId] : undefined}
        onGenerateLeadfield={onGenerateLeadfield}
        generatingLeadfield={generatingLeadfield}
        onOpenViewer={onOpenViewer}
      />
    </div>
  );
}

/** The sentinel the Net cell uses for "no mapping, keep the optimiser's own coordinates" — Radix
 *  reserves `value=""` for "nothing selected", so the absence needs a real value. */
const OPTIMISED = "__optimised__";

function netCellValue(row: OptimizerRow): string | undefined {
  if (isFlexMethod(row.method)) return row.net ?? OPTIMISED;
  return row.net ?? undefined;
}

/**
 * The row's editor: one dialog per method, built from this page's existing form sections scoped to
 * one row. There is no page-level copy of any of these controls any more — a section that
 * configures a search belongs to the search, which is the row.
 */
function RowEditor({
  row,
  onClose,
  onChange,
  nets,
  leadfields,
  onGenerateLeadfield,
  generatingLeadfield,
  onOpenViewer,
}: {
  row: OptimizerRow | null;
  onClose: () => void;
  onChange: (next: OptimizerRow) => void;
  nets: EegNet[];
  leadfields: Leadfield[] | undefined;
  onGenerateLeadfield: (subject: string, net: string) => void;
  generatingLeadfield: boolean;
  onOpenViewer?: () => void;
}) {
  if (!row) return null;

  const flexForm = flexFormForMethod(row.flex, row.method);
  /**
   * The Objective section's own Goal control and the row's Goal cell are one decision. A goal that
   * leaves `focality` also leaves the adaptive/Pareto *methods*, because those two ARE focality
   * with a mode — without this the section would offer a change the method then silently reverted.
   */
  const patchFlex = (p: Partial<typeof row.flex>) => {
    const flex = { ...row.flex, ...p };
    if (p.goal !== undefined && p.goal !== "focality" && row.method !== "flex") {
      onChange({ ...withMethod(row, "flex"), flex });
      return;
    }
    onChange({ ...row, flex });
  };
  const patchEx = (p: Partial<typeof row.ex>) => onChange({ ...row, ex: { ...row.ex, ...p } });
  const patchMex = (p: Partial<typeof row.mex>) => onChange({ ...row, mex: { ...row.mex, ...p } });
  const electrodes = electrodesForNet(nets, row.net);
  const method = OPT_METHODS.find((m) => m.value === row.method);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`${method?.label ?? row.method} search`}
      description={`${row.subjectId || "no subject"}${rowGoal(row) ? ` · ${GOAL_LABEL[rowGoal(row) as OptGoal]}` : ""}`}
      footer={
        <Button variant="primary" onClick={onClose} data-testid="opt-row-done">
          Done
        </Button>
      }
    >
      <div className="optimizer-row-editor" data-testid="opt-row-editor" data-row={row.id} data-method={row.method}>
        {/* Ex/mEx: the leadfield is a GATE, not a form field (wireframes §4) — and now a gate for
            THIS row's subject, which is the fact the page-level strip could never state once rows
            could name different subjects. */}
        {!isFlexMethod(row.method) && (
          <LeadfieldStrip
            leadfields={leadfields}
            loading={leadfields === undefined}
            nets={nets}
            selectedNet={row.net}
            onSelectNet={(n) => onChange({ ...row, net: n })}
            onGenerate={(n) => row.subjectId && onGenerateLeadfield(row.subjectId, n)}
            generating={generatingLeadfield}
          />
        )}

        <Field label="Run name" htmlFor={`opt-run-name-${row.id}`} help="Defaults to a timestamp.">
          <TextInput
            id={`opt-run-name-${row.id}`}
            value={row.runName}
            onChange={(e) => onChange({ ...row, runName: e.target.value })}
            placeholder="auto (timestamp)"
          />
        </Field>

        <section className="optimizer-row-target" data-testid="opt-row-target">
          <h4 className="text-eyebrow">Target</h4>
          <RoiPicker
            value={row.roi}
            onChange={(roi: RoiValue) => onChange({ ...row, roi })}
            modes={roiModesFor(row.method)}
            subject={row.subjectId || undefined}
            allowCombine={row.method === "ex"}
            onOpenViewer={row.roi.mode === "spherical" ? onOpenViewer : undefined}
          />
        </section>

        {isFlexMethod(row.method) && (
          <>
            <ObjectiveSection
              form={flexForm}
              onChange={patchFlex}
              nonRoi={row.nonRoi}
              onNonRoiChange={(nonRoi) => onChange({ ...row, nonRoi })}
              subject={row.subjectId || undefined}
            />
            <ElectrodesSection form={flexForm} onChange={patchFlex} />
            <SolverSection form={flexForm} onChange={patchFlex} eegNets={nets} />
            <PostRunSection form={flexForm} onChange={patchFlex} eegNets={nets} />
          </>
        )}
        {row.method === "ex" && (
          <>
            <ExElectrodesSection form={row.ex} onChange={patchEx} electrodes={electrodes} disabled={!row.net} />
            <ExCurrentSection form={row.ex} onChange={patchEx} />
          </>
        )}
        {row.method === "mex" && (
          <>
            <MExElectrodesSection form={row.mex} onChange={patchMex} electrodes={electrodes} disabled={!row.net} />
            <MExCarrierSection form={row.mex} onChange={patchMex} />
          </>
        )}
      </div>
    </Dialog>
  );
}
