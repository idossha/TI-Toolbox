/**
 * The Analyzer's **Jobs table** — one row per analysis job, and the row owns its inputs.
 *
 * Maintainer, 2026-09-06: *"This is also true for the Analyzer — we need a list of jobs in a table
 * that allows users flexibility in what they input to the job."* 2.5.0's analyzer tab was a
 * `Subject × Simulation` pair table with "+ Add Pair" and a "Quick Add" that filled in every
 * subject having a given simulation; group vs single was read off the row count. v3 had replaced
 * it with a page-level Subjects table plus a single Simulation combobox, which cannot express
 * "ernie/Thalamus and 101/Motor" at all.
 *
 * So the row is the pair again, plus every per-job choice that was global and had no business
 * being so — the analysis `Space` (mesh/voxel), the `Field`, and (maintainer, second pass) the
 * **Target**: *"we can modify our analysis input per job"*. The row's Target cell states the
 * target in words and opens the shared `RoiPicker` scoped to that row; the page-level TARGET
 * section is gone, as is the OUTPUT section (Results owns a simulation's existing analyses).
 *
 * Two layout rules the cell obeys, because a target changing must not move a row:
 *
 *  1. the columns are fixed percentages (`<colgroup>`), so a longer target cannot widen a column;
 *  2. the Target cell truncates to one line and carries the full text in `title`.
 *
 * Group mode is a switch over the same rows (`Combine into one group analysis`), living on the
 * table's own footer line beside `+ Add row`: the rows name the cohort, one job is submitted over
 * all of them, and rows that disagree about the simulation, the space, the field **or the target**
 * are refused with the reason on the Run button.
 */
import { useMemo, useState } from "react";
import { Copy, Info, Plus, Target as TargetIcon, X } from "lucide-react";
import { Button, IconButton } from "../../ui/Button";
import { Dialog, Popover } from "../../ui/Overlay";
import { Switch, Checkbox } from "../../ui/Toggle";
import { Select } from "../../ui/Select";
import { SelectionPicker } from "../../ui/SelectionList";
import { RoiPicker, emptyRoi, isRoiComplete, type RoiRegion, type RoiValue } from "../_shared/roi";
import { AUTO_FIELD, type Space } from "./buildConfig";
import { FIELD_REGISTRY } from "./fields";
import "./analyzer-page.css";

/**
 * One row of the table = one (subject, simulation, space, field, target) analysis job.
 *
 * `roi` is the row's own target — the same `RoiValue` the shared picker edits, in its cortical,
 * subcortical or spherical mode. `combine` is the picker's "Combine regions into one ROI":
 * checked, the row's regions are one ROI on one config (the config's `region` list); unchecked,
 * each region is its own analysis, which is what 2.5.0's per-sphere rows already did.
 */
export interface AnalyzerRow {
  id: string;
  subjectId: string;
  simulation: string;
  space: Space;
  field: string;
  roi: RoiValue;
  combine: boolean;
}

/** The three target modes the analyzer runner understands (`saved` is an ex/mEx target). */
export const ANALYZER_ROI_MODES = ["cortical", "subcortical", "spherical"] as const;

let rowSeq = 0;

export function newAnalyzerRowId(): string {
  rowSeq += 1;
  return `analysis-${rowSeq}`;
}

/** A blank row, seeded with whatever the previous row decided (2.5.0's "+ Add Pair"). */
export function emptyAnalyzerRow(seed?: Partial<AnalyzerRow>): AnalyzerRow {
  return {
    id: newAnalyzerRowId(),
    subjectId: seed?.subjectId ?? "",
    simulation: seed?.simulation ?? "",
    space: seed?.space ?? "mesh",
    field: seed?.field ?? AUTO_FIELD,
    roi: seed?.roi ?? emptyRoi("spherical"),
    combine: seed?.combine ?? true,
  };
}

/** A row is a job once it names a subject and a simulation. */
export function isRunnableAnalyzerRow(row: AnalyzerRow): boolean {
  return !!row.subjectId && !!row.simulation;
}

/** A runnable row can be *planned* once its own target is complete too. */
export function isPlannableAnalyzerRow(row: AnalyzerRow): boolean {
  return isRunnableAnalyzerRow(row) && isRoiComplete(row.roi);
}

/** `lh.insula` — the hemisphere is part of a cortical region's identity. */
function regionLabel(r: RoiRegion): string {
  return r.hemi ? `${r.hemi}.${r.name}` : r.name;
}

function num(v: number | undefined): string {
  return v === undefined ? "?" : String(v);
}

/** Up to two names, then a count — the target line has room for two, never for nine. */
function joinNames(names: string[]): string {
  if (names.length <= 2) return names.join(" + ");
  return `${names.slice(0, 2).join(" + ")} + ${names.length - 2} more`;
}

/**
 * The row's target **in words** — the whole second line of the row, and its `title`.
 *
 * It gets a full line of its own (maintainer, 2026-09-06: *"line 2 = the Target as a full-width
 * readable line"*), so it states everything that changes what is measured: the atlas, the regions
 * and whether they are one ROI or one job each; the sphere's radius, its coordinate space and its
 * volumetric compartment. An incomplete target says so rather than printing half a coordinate.
 */
export function analyzerTargetLabel(roi: RoiValue, combine = true): string {
  if (!isRoiComplete(roi)) return "Choose a target…";
  if (roi.mode === "spherical") {
    const spheres = roi.spheres.map((s) => `${num(s.x)},${num(s.y)},${num(s.z)} r${num(s.radius)} mm`);
    const parts = [`Sphere ${joinNames(spheres)}`, roi.space === "mni" ? "MNI" : "Subject"];
    if (roi.volumetric) parts.push(`volumetric ${roi.tissues}`);
    return parts.join(" · ");
  }
  if (roi.mode === "saved") return "Choose a target…";
  const names = roi.regions.map(regionLabel);
  // Cortical and subcortical both name their atlas: a region name means little without the
  // parcellation it came from, and both panels choose one.
  const head = `${roi.mode === "cortical" ? "Cortical" : "Subcortical"} · ${roi.atlas} · ${joinNames(names)}`;
  if (names.length < 2) return head;
  // What the combine checkbox actually decides, stated where the decision is visible: one ROI, or
  // one analysis per region.
  return `${head} (${combine ? "combined" : "separate jobs"})`;
}

/** Two rows agree about their target when the picker's whole value agrees. */
export function sameTarget(a: AnalyzerRow, b: AnalyzerRow): boolean {
  return JSON.stringify([a.roi, a.combine]) === JSON.stringify([b.roi, b.combine]);
}

/**
 * The Jobs section's summary: how many rows are jobs, over how many subjects, and — in group mode
 * — that they fold into one. The count the disabled-Run grammar and the plan grid then agree with.
 */
export function analyzerJobsSummary(rows: AnalyzerRow[], group: boolean): string {
  const runnable = rows.filter(isRunnableAnalyzerRow);
  if (rows.length === 0) return "no rows yet";
  const subjects = new Set(runnable.map((r) => r.subjectId)).size;
  const incomplete = rows.length - runnable.length;
  const head =
    runnable.length === 0
      ? "no complete row"
      : group
        ? `one group analysis over ${subjects} subject${subjects === 1 ? "" : "s"}`
        : `${runnable.length} analysis job${runnable.length === 1 ? "" : "s"} · ${subjects} subject${subjects === 1 ? "" : "s"}`;
  return incomplete > 0 ? `${head} · ${incomplete} incomplete` : head;
}

export interface AnalyzerSubject {
  id: string;
  /** Simulation names this subject has run — the row's Simulation cell's options. */
  simulations: string[];
  /** `undefined` when usable here; otherwise why not (J3 wording). */
  blockedReason?: string;
}

export function AnalyzerJobRows({
  subjects,
  rows,
  onRowsChange,
  fieldsFor,
  group,
  onGroupChange,
  activeRowId,
  onActiveRowChange,
  onOpenViewer,
}: {
  subjects: AnalyzerSubject[];
  rows: AnalyzerRow[];
  onRowsChange: (next: AnalyzerRow[]) => void;
  /** Cohort mode — the switch lives on the table's own footer line, beside `+ Add row`. */
  group: boolean;
  onGroupChange: (next: boolean) => void;
  /** Fields a given (subject, simulation) actually wrote; empty falls back to the registry. */
  fieldsFor: (subjectId: string, simulation: string) => string[];
  /** The row the 3-D pane is drawing — highlighted here, exactly as the Simulator's table does. */
  activeRowId: string | null;
  onActiveRowChange: (id: string) => void;
  /** Spherical targets offer "Open T1 in viewer"; omitted, the button is not drawn. */
  onOpenViewer?: () => void;
}) {
  /** Which row's target dialog is open, if any, and the target it had when it opened. */
  const [targetRowId, setTargetRowId] = useState<string | null>(null);
  const [targetDraft, setTargetDraft] = useState<{ roi: RoiValue; combine: boolean } | null>(null);

  const subjectItems = useMemo(
    () =>
      subjects.map((s) => ({
        id: s.id,
        label: s.id,
        reason: s.blockedReason,
        // Listed with the reason, unselectable — the subject grammar's J3 rule, inside the row.
        disabled: !!s.blockedReason,
      })),
    [subjects],
  );

  const patch = (id: string, next: Partial<AnalyzerRow>) =>
    onRowsChange(rows.map((r) => (r.id === id ? { ...r, ...next } : r)));

  function simulationsOf(subjectId: string): string[] {
    return subjects.find((s) => s.id === subjectId)?.simulations ?? [];
  }

  function fieldOptions(row: AnalyzerRow) {
    const available = fieldsFor(row.subjectId, row.simulation);
    const names = available.length > 0 ? available : FIELD_REGISTRY.map((f) => f.name);
    return [
      // Radix Select reserves value="" for "no selection shown", so "Auto" needs a real sentinel.
      { value: AUTO_FIELD, label: "Auto" },
      ...names.map((name) => ({
        value: name,
        label: name,
        // TI_normal is a surface field and is not exported to NIfTI.
        disabled: row.space === "voxel" && name === "TI_normal",
      })),
    ];
  }

  function addRow() {
    const last = rows[rows.length - 1];
    const seed = last ?? { subjectId: subjects.find((s) => !s.blockedReason)?.id };
    const next = emptyAnalyzerRow(seed);
    onRowsChange([...rows, next]);
    onActiveRowChange(next.id);
  }

  function duplicate(row: AnalyzerRow) {
    const at = rows.findIndex((r) => r.id === row.id);
    const copy = { ...row, id: newAnalyzerRowId() };
    onRowsChange([...rows.slice(0, at + 1), copy, ...rows.slice(at + 1)]);
    onActiveRowChange(copy.id);
  }

  const targetRow = rows.find((r) => r.id === targetRowId) ?? null;

  /** Cancel puts back the target the row had when the dialog opened. */
  function cancelTarget() {
    if (targetRow && targetDraft) patch(targetRow.id, targetDraft);
    setTargetRowId(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div className="data-table-container" data-testid="analysis-jobs-table-container">
        <table className="data-table analysis-jobs-table" data-testid="analysis-jobs-table">
          {/*
            Fixed widths in pixels, not percentages (maintainer, 2026-09-06: the cells were
            printing "Choose a sim…", "M…" and a truncated atlas name). Space needs 80px to print
            "Voxel", Field 110px for "mTI_normal", Subject 150px for the longest id a project has;
            Simulation takes whatever is left, because a montage name is the one cell whose length
            nobody controls. `table-layout: fixed` (analyzer-page.css) makes them authoritative.
          */}
          <colgroup>
            <col style={{ width: "150px" }} />
            <col />
            <col style={{ width: "104px" }} />
            <col style={{ width: "110px" }} />
            <col style={{ width: "72px" }} />
          </colgroup>
          <thead>
            <tr>
              <th>Subject</th>
              <th>Simulation</th>
              <th>Space</th>
              <th>Field</th>
              <th />
            </tr>
          </thead>
          {rows.map((row, i) => {
            const label = analyzerTargetLabel(row.roi, row.combine);
            return (
              /*
                One job is one `<tbody>` of TWO rows (maintainer: "a thicker two-line row"): line 1
                is `Subject · Simulation · Space · Field` at full width, line 2 is the target as a
                readable sentence across the whole table. A `<tbody>` per job — rather than a
                `rowspan` or a second `<table>` — is what lets the two lines share one hover, one
                active wash and one set of row attributes while each line keeps its own cells.
              */
              <tbody
                key={row.id}
                className="analysis-job-group"
                data-analysis-row={row.id}
                data-subject={row.subjectId || undefined}
                data-simulation={row.simulation || undefined}
                data-runnable={isRunnableAnalyzerRow(row) ? "true" : "false"}
                data-target-ready={isRoiComplete(row.roi) ? "true" : "false"}
                data-active={activeRowId === row.id ? "true" : undefined}
                aria-selected={activeRowId === row.id}
                onClick={(e) => {
                  // A click on a control in the row is that control's, not the row's.
                  if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
                  onActiveRowChange(row.id);
                }}
                onFocus={() => onActiveRowChange(row.id)}
              >
                <tr className="analysis-job-line1" tabIndex={0}>
                  <td data-cell="subject">
                    <SelectionPicker
                      mode="single"
                      label="Subject"
                      items={subjectItems}
                      value={row.subjectId ? [row.subjectId] : []}
                      onChange={(v) => {
                        const next = v[0];
                        if (!next) return;
                        // A simulation the new subject has not run is not a job — clear it rather
                        // than carrying a row the plan will refuse.
                        const keeps = simulationsOf(next).includes(row.simulation);
                        patch(row.id, { subjectId: next, simulation: keeps ? row.simulation : "" });
                      }}
                      placeholder="Subject"
                      headers={{ label: "Subject", reason: "Why not" }}
                      hideBulk
                      idPrefix={`analysis-subject-${row.id}`}
                      triggerTestId={`analysis-subject-${row.id}`}
                    />
                  </td>
                  <td data-cell="simulation">
                    <Select
                      value={simulationsOf(row.subjectId).includes(row.simulation) ? row.simulation : undefined}
                      onValueChange={(v) => patch(row.id, { simulation: v, field: AUTO_FIELD })}
                      options={simulationsOf(row.subjectId).map((s) => ({ value: s, label: s }))}
                      placeholder={row.subjectId ? (simulationsOf(row.subjectId).length === 0 ? "No simulations" : "Choose a simulation") : "Pick a subject"}
                      disabled={!row.subjectId || simulationsOf(row.subjectId).length === 0}
                      aria-label="Simulation"
                    />
                  </td>
                  <td data-cell="space">
                    <Select
                      value={row.space}
                      onValueChange={(v) =>
                        // Voxel space cannot analyze TI_normal, so a row switching into it drops back
                        // to Auto rather than planning a field that will not resolve.
                        patch(row.id, { space: v as Space, field: v === "voxel" && row.field === "TI_normal" ? AUTO_FIELD : row.field })
                      }
                      options={[
                        { value: "mesh", label: "Mesh" },
                        { value: "voxel", label: "Voxel" },
                      ]}
                      aria-label="Space"
                    />
                  </td>
                  <td data-cell="field">
                    <Select
                      value={row.field}
                      onValueChange={(v) => patch(row.id, { field: v })}
                      options={fieldOptions(row)}
                      aria-label="Field"
                    />
                  </td>
                  <td data-cell="actions" className="montage-actions">
                    <IconButton aria-label={`Duplicate row ${i + 1}`} icon={<Copy size={14} />} onClick={() => duplicate(row)} />
                    <IconButton
                      aria-label={`Remove row ${i + 1}`}
                      icon={<X size={14} />}
                      onClick={() => onRowsChange(rows.filter((r) => r.id !== row.id))}
                    />
                  </td>
                </tr>
                <tr className="analysis-job-line2">
                  {/* Line 2: the whole target, across the whole table. It STATES the target and
                      opens the shared picker scoped to this row; "Target" is a caption here rather
                      than a column header, because the line is not a column. */}
                  <td data-cell="target" colSpan={5}>
                    <button
                      type="button"
                      className="analysis-target-button"
                      data-testid={`analysis-target-${row.id}`}
                      data-empty={isRoiComplete(row.roi) ? undefined : "true"}
                      title={label}
                      aria-label={`Target for row ${i + 1}: ${label}`}
                      onClick={() => {
                        onActiveRowChange(row.id);
                        setTargetDraft({ roi: row.roi, combine: row.combine });
                        setTargetRowId(row.id);
                      }}
                    >
                      <span className="analysis-target-caption text-eyebrow">Target</span>
                      <TargetIcon size={12} aria-hidden />
                      <span className="analysis-target-text">{label}</span>
                    </button>
                  </td>
                </tr>
              </tbody>
            );
          })}
        </table>
      </div>

      {/* One footer line: the add gesture on the left, the cohort switch right-aligned on the same
          row (maintainer, 2026-09-06). The switch is not a `Field` — a "Combine" label above a
          control that already reads "Combine into one group analysis" said it twice. */}
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }} data-testid="analysis-jobs-footer">
        <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={addRow}>
          Add row
        </Button>
        <div
          style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-2)" }}
          data-testid="analysis-combine-row"
        >
          {/* The help trigger sits outside the <label> on purpose — inside it, opening the popover
              would also toggle the switch. */}
          <label className="checkbox-label-row">
            <Switch checked={group} onCheckedChange={onGroupChange} aria-label="Combine into one group analysis" />
            Combine into one group analysis
          </label>
          <Popover
            trigger={
              <button type="button" className="field-help-trigger" aria-label="Help">
                <Info size={12} aria-hidden />
              </button>
            }
          >
            <div className="field-help-popover">
              <div className="field-help-popover-title">Combine into one group analysis</div>
              One cohort analysis over every row&apos;s subject (run_group_analysis), instead of one job per row.
              Every row must name the same simulation, space, field and target.
            </div>
          </Popover>
        </div>
      </div>

      {/*
        The row's target editor. A dialog rather than a popover because the picker itself opens an
        atlas combobox and a region dialog — overlays a popover would have to survive.

        Organised as one structure whatever the mode (maintainer, 2026-09-06): a fixed 560px width,
        the mode segmented control full-width across the top, the picker's own label-left form
        under it, and the row's own "Combine regions into one ROI" as the last line with its help
        inline. `Cancel` restores the target the row had when the dialog opened, which is the only
        thing that makes a Cancel button honest here — the picker edits the row live.
      */}
      <Dialog
        open={targetRow !== null}
        onOpenChange={(open) => {
          if (!open) setTargetRowId(null);
        }}
        title="Analysis target"
        description={
          targetRow
            ? `${targetRow.subjectId || "no subject"} · ${targetRow.simulation || "no simulation"}`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={cancelTarget} data-testid="analysis-target-cancel">
              Cancel
            </Button>
            <Button variant="primary" onClick={() => setTargetRowId(null)} data-testid="analysis-target-done">
              Done
            </Button>
          </>
        }
      >
        {targetRow && (
          <div className="analysis-target-editor" data-testid="analysis-target-editor" data-row={targetRow.id}>
            <RoiPicker
              value={targetRow.roi}
              onChange={(roi) => patch(targetRow.id, { roi })}
              modes={[...ANALYZER_ROI_MODES]}
              subject={targetRow.subjectId || undefined}
              space={targetRow.space === "voxel" ? "mni" : "subject"}
              onOpenViewer={onOpenViewer}
            />
            {targetRow.roi.mode !== "spherical" && (
              /* One line, not two: the checkbox and the (i) that explains it, the same shape as
                 the Combine switch on the table's footer. The paragraph this replaces said in two
                 sentences what the target line now says in one word ("combined"). */
              <div className="analysis-target-combine" data-testid="analysis-target-combine">
                <Checkbox
                  checked={targetRow.combine}
                  onCheckedChange={(on) => patch(targetRow.id, { combine: on })}
                  label="Combine regions into one ROI"
                />
                <Popover
                  trigger={
                    <button type="button" className="field-help-trigger" aria-label="Help">
                      <Info size={12} aria-hidden />
                    </button>
                  }
                >
                  <div className="field-help-popover">
                    <div className="field-help-popover-title">Combine regions into one ROI</div>
                    On, the selected regions are measured together as one ROI. Off, each region is its own
                    analysis — one job per region.
                  </div>
                </Popover>
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
}
