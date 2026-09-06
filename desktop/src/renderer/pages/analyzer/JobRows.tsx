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
 * So the row is the pair again, plus the two per-job choices that were global and had no business
 * being so — the analysis `Space` (mesh/voxel) and the `Field`. Everything that is genuinely a
 * property of the *question being asked* rather than of one job — the ROI, the tissue, the
 * coordinate space — stays global on the page, exactly as it was in 2.5.0.
 *
 * Group mode is a switch over the same rows (`Combine into one group analysis`): the rows name the
 * cohort, and one job is submitted over all of them.
 */
import { useMemo } from "react";
import { Copy, Plus, Users, X } from "lucide-react";
import { Button, IconButton } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { SelectionPicker } from "../../ui/SelectionList";
import { notify } from "../../ui/Toast";
import { AUTO_FIELD, type Space } from "./buildConfig";
import { FIELD_REGISTRY } from "./fields";

/** One row of the table = one (subject, simulation, space, field) analysis job. */
export interface AnalyzerRow {
  id: string;
  subjectId: string;
  simulation: string;
  space: Space;
  field: string;
}

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
  };
}

/** A row is a job once it names a subject and a simulation. */
export function isRunnableAnalyzerRow(row: AnalyzerRow): boolean {
  return !!row.subjectId && !!row.simulation;
}

/**
 * 2.5.0's **Quick Add**: one row per subject that has run `simulation`, minus the ones already in
 * the table. Pure, so the rule ("every subject having this simulation", never one that has not
 * run it) is testable without the page.
 */
export function quickAddRows(
  rows: AnalyzerRow[],
  simulation: string,
  subjectsWithSimulation: string[],
  template: Partial<AnalyzerRow> = {},
): AnalyzerRow[] {
  const already = new Set(rows.filter((r) => r.simulation === simulation).map((r) => r.subjectId));
  return subjectsWithSimulation
    .filter((id) => !already.has(id))
    .map((id) => emptyAnalyzerRow({ ...template, subjectId: id, simulation }));
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
}: {
  subjects: AnalyzerSubject[];
  rows: AnalyzerRow[];
  onRowsChange: (next: AnalyzerRow[]) => void;
  /** Fields a given (subject, simulation) actually wrote; empty falls back to the registry. */
  fieldsFor: (subjectId: string, simulation: string) => string[];
}) {
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
    onRowsChange([...rows, emptyAnalyzerRow(last ?? { subjectId: subjects.find((s) => !s.blockedReason)?.id })]);
  }

  function duplicate(row: AnalyzerRow) {
    const at = rows.findIndex((r) => r.id === row.id);
    onRowsChange([...rows.slice(0, at + 1), { ...row, id: newAnalyzerRowId() }, ...rows.slice(at + 1)]);
  }

  function quickAdd() {
    const simulation = [...rows].reverse().find((r) => r.simulation)?.simulation ?? "";
    if (!simulation) {
      notify.error("Pick a simulation in a row first — Quick add fills in every subject that has run it.");
      return;
    }
    const have = subjects.filter((s) => !s.blockedReason && s.simulations.includes(simulation)).map((s) => s.id);
    const added = quickAddRows(rows, simulation, have, { space: rows[0]?.space, field: rows[0]?.field });
    if (added.length === 0) {
      notify.info(`Every subject that has run "${simulation}" is already in the table.`);
      return;
    }
    onRowsChange([...rows, ...added]);
  }

  const quickAddSimulation = [...rows].reverse().find((r) => r.simulation)?.simulation;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div className="data-table-container" data-testid="analysis-jobs-container">
        <table className="data-table analysis-jobs-table" data-testid="analysis-jobs-table">
          <colgroup>
            <col style={{ width: "22%" }} />
            <col style={{ width: "30%" }} />
            <col style={{ width: "18%" }} />
            <col style={{ width: "20%" }} />
            <col style={{ width: "10%" }} />
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
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.id}
                data-analysis-row={row.id}
                data-subject={row.subjectId || undefined}
                data-simulation={row.simulation || undefined}
                data-runnable={isRunnableAnalyzerRow(row) ? "true" : "false"}
              >
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
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={addRow}>
          Add row
        </Button>
        <Button variant="secondary" size="sm" icon={<Users size={14} />} onClick={quickAdd} disabled={!quickAddSimulation}>
          {quickAddSimulation ? `Quick add: every subject with "${quickAddSimulation}"` : "Quick add"}
        </Button>
      </div>
    </div>
  );
}
