/**
 * `ParticipantsField` — the one control for a *list* of participants (fix round, lane FIX-D,
 * defect 3).
 *
 * The grammar is `pages/_shared/subjects/SubjectsField`'s, to the word:
 *
 *   Subjects   3 subjects · 101, ernie, MNI152 · one job over all subjects     [ Add subject ]
 *   # | Subject | Simulation | Group   | Why not
 *   1 | 101     | L_Insula   | Group1  |
 *   2 | ernie   | —          | Group1  | no simulation chosen
 *
 * What differs from `SubjectsField`, and why:
 *   - **rows, not a set.** The same subject may appear twice (a paired test, a diff pair), which a
 *     set control cannot express — lane SUB's measured reason for not converting these three
 *     panels. The summary line says so outright when it happens (`4 rows · 3 subjects · …`).
 *   - **no filter, no select-all.** Both are set operations over a catalog. This table is the
 *     study design itself: every row is there because someone added it.
 *   - **always open.** There is nothing to disclose — the rows *are* the page's first decision.
 *
 * Everything else is deliberately identical: the 28 px `--surface-2` header band, the eyebrow
 * title, the one-line summary carrying J4's semantics, the table with real column headers, the
 * "Why not" column that only exists when some row has a reason, the warning-coloured reason text,
 * and the filler rows that stop a three-row table ending in a hard edge halfway up the pane.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type MouseEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button, IconButton } from "../../../ui/Button";
import { TextInput } from "../../../ui/Field";
import { Checkbox } from "../../../ui/Toggle";
import { Skeleton } from "../../../ui/Feedback";
import {
  applyClick,
  selectAllVisible,
  selectionBadge,
  selectNoneVisible,
  type SelectionItem,
  type SelectionState,
} from "../../../ui/SelectionList";
import { blockedParticipants, participantsSummary } from "./model";
import type { ParticipantsFieldProps } from "./types";
import "./participants.css";

export function ParticipantsField<R>({
  rows,
  rowId,
  subjectOf,
  columns,
  subjectCell,
  simulationCell,
  eligibility,
  note,
  onAdd,
  addLabel = "Add subject",
  onRemove,
  minRows = 0,
  fill = false,
  help,
  loading = false,
  emptyMessage = "No participants yet.",
}: ParticipantsFieldProps<R>) {
  // `fill`: how many ground rows reach the bottom of the box, measured. See `types.ts` for why
  // this cannot oscillate — the box's height does not depend on what is inside it.
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const [fitRows, setFitRows] = useState(0);
  const measure = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const head = el.querySelector("thead");
    const headH = head ? head.getBoundingClientRect().height : 0;
    const body = el.querySelector("tbody tr");
    const rowH = body ? body.getBoundingClientRect().height : 0;
    if (rowH < 1) return;
    const fits = Math.max(0, Math.floor((el.clientHeight - headH) / rowH));
    setFitRows((prev) => (prev === fits ? prev : fits));
  }, []);
  // `observe()` delivers the first callback with the box's current size, so this needs no
  // synchronous measurement of its own — and must not have one: a `setState` called synchronously
  // inside an effect is a cascading render (the repo's `react-hooks` rule rejects it).
  useLayoutEffect(() => {
    if (!fill || !box) return;
    const observer = new ResizeObserver(() => measure(box));
    observer.observe(box);
    return () => observer.disconnect();
  }, [fill, box, measure]);
  // Adding or removing a row does not resize the box (its height comes from the other column), so
  // the observer never fires for it — re-measure on the next frame, after that row has laid out.
  useEffect(() => {
    if (!fill || !box) return;
    const frame = requestAnimationFrame(() => measure(box));
    return () => cancelAnimationFrame(frame);
  }, [fill, box, measure, rows.length]);

  /* The one selection grammar (plan C1), over rows rather than over a catalog. This table's cells
     are live controls — a subject `Select`, a simulation `Combobox` — so a whole-row click cannot
     be the selection gesture without stealing every click meant for them: the checkbox column IS
     the gesture here, and it carries the same ⇧-range and ⌘-toggle rules as everywhere else, from
     the same `applyClick`. What that buys is the bulk removal these panels never had — a
     twelve-row paired design was twelve trash clicks — plus the filter and the `N of M` badge the
     other lists have.

     Selection is deliberately NOT lifted to the page: it is a transient gesture about which rows
     to remove, not part of the study design the page persists. */
  const [selection, setSelection] = useState<SelectionState>({ value: [], anchor: null });
  const [query, setQuery] = useState("");

  const q = query.trim().toLowerCase();
  const visibleRows = useMemo(
    () => (q ? rows.filter((r) => `${rowId(r)} ${subjectOf(r)}`.toLowerCase().includes(q)) : rows),
    [rows, q, rowId, subjectOf],
  );
  const visibleItems = useMemo<SelectionItem[]>(() => visibleRows.map((r) => ({ id: rowId(r), label: rowId(r) })), [visibleRows, rowId]);
  // A row that has been removed is not still selected.
  const live = useMemo(() => new Set(rows.map(rowId)), [rows, rowId]);
  const selected = selection.value.filter((id) => live.has(id));
  const allVisibleSelected = visibleItems.length > 0 && visibleItems.every((i) => selected.includes(i.id));

  function toggleRow(e: MouseEvent, id: string): void {
    setSelection(applyClick({ value: selected, anchor: selection.anchor }, visibleItems, id, {
      toggle: !e.shiftKey,
      range: e.shiftKey,
    }));
  }

  const summary = participantsSummary(rows.map(subjectOf), rows.length, note);
  const blocked = blockedParticipants(rows, eligibility);
  /* The "Why not" column exists only while some row has a why-not — the same rule (and the same
     measured reason) as `SubjectsField`: an always-present column that is empty for every row is a
     quarter of the table's width spent on nothing. */
  const anyReason = blocked.length > 0;
  const targetRows = Math.max(minRows, fill ? fitRows : 0);
  const totalColumns = 4 + columns.length + (anyReason ? 1 : 0) + (onRemove ? 1 : 0);

  return (
    <div className="participants-field" data-testid="participants-field" data-rows={rows.length} data-subjects={summary.subjects}>
      <div className="participants-field-head">
        <span className="text-eyebrow participants-field-title">Subjects</span>
        <span className="participants-field-summary" data-testid="participants-summary">
          {summary.subjects === 0 ? (
            <span className="mono">{summary.text}</span>
          ) : (
            <>
              {summary.lead && <>{summary.lead} · </>}
              <span className="mono">{summary.names}</span>
              {` · ${summary.note}`}
            </>
          )}
        </span>
        {help}
        {rows.length > 1 && (
          <TextInput
            className="participants-filter"
            aria-label="Filter participants"
            placeholder="Filter…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="participants-filter"
          />
        )}
        {rows.length > 1 && (
          <span className="participants-bulk">
            <Button
              variant="ghost"
              size="sm"
              disabled={visibleItems.length === 0 || allVisibleSelected}
              onClick={() => setSelection({ value: selectAllVisible(selected, visibleItems), anchor: selection.anchor })}
              data-testid="participant-select-all"
            >
              All
            </Button>
            <span className="selection-bulk-sep" aria-hidden>
              ·
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={selected.length === 0}
              onClick={() => setSelection({ value: selectNoneVisible(selected, visibleItems), anchor: null })}
              data-testid="participant-select-none"
            >
              None
            </Button>
            <span className="selection-badge text-caption tabular-nums" data-testid="participant-count">
              {selectionBadge(selected.length, rows.length)}
            </span>
          </span>
        )}
        {onRemove && selected.length > 0 && rows.length > selected.length && (
          <Button
            variant="secondary"
            size="sm"
            icon={<Trash2 size={14} />}
            onClick={() => {
              for (const id of selected) onRemove(id);
              setSelection({ value: [], anchor: null });
            }}
            data-testid="participants-remove-selected"
          >
            Remove {selected.length}
          </Button>
        )}
        {onAdd && (
          <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={onAdd} data-testid="participants-add">
            {addLabel}
          </Button>
        )}
      </div>

      {loading && <Skeleton rows={3} />}
      {!loading && (
        <div className="participants-scroll" data-fill={fill ? "true" : undefined} ref={setBox} data-testid="participants-field-table">
          <table className="participants-table">
            <thead>
              <tr>
                <th scope="col" className="participants-check">
                  <Checkbox
                    checked={allVisibleSelected ? true : selected.length > 0 ? "indeterminate" : false}
                    onCheckedChange={(on) =>
                      setSelection({
                        value: on ? selectAllVisible(selected, visibleItems) : selectNoneVisible(selected, visibleItems),
                        anchor: null,
                      })
                    }
                    disabled={visibleItems.length === 0}
                    aria-label="Select all participants"
                  />
                </th>
                <th scope="col" className="participants-index">
                  #
                </th>
                <th scope="col">Subject</th>
                <th scope="col">Simulation</th>
                {columns.map((c) => (
                  <th key={c.id} scope="col" style={c.width ? { width: c.width } : undefined}>
                    {c.header}
                  </th>
                ))}
                {anyReason && <th scope="col">Why not</th>}
                {onRemove && <th scope="col" className="participants-remove" aria-label="Remove" />}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, i) => {
                const id = rowId(row);
                const verdict = eligibility ? eligibility(row) : { ok: true };
                return (
                  <tr
                    key={id}
                    className="participant-row"
                    data-testid={`participant-row-${id}`}
                    data-eligible={verdict.ok ? "true" : "false"}
                    data-selected={selected.includes(id) ? "true" : "false"}
                  >
                    <td className="participants-check" onClick={(e) => toggleRow(e, id)}>
                      <Checkbox checked={selected.includes(id)} onCheckedChange={() => undefined} aria-label={`Select row ${i + 1}`} />
                    </td>
                    <td className="participants-index tabular">{i + 1}</td>
                    <td>{subjectCell(row, i)}</td>
                    <td>{simulationCell(row, i)}</td>
                    {columns.map((c) => (
                      <td key={c.id}>{c.cell(row, i)}</td>
                    ))}
                    {anyReason && (
                      <td>
                        {!verdict.ok && (
                          <span className="participants-reason" data-testid={`participant-reason-${id}`}>
                            {verdict.reason ?? "cannot be used here"}
                          </span>
                        )}
                      </td>
                    )}
                    {onRemove && (
                      <td className="participants-remove">
                        <IconButton
                          aria-label={`Remove row ${i + 1}`}
                          icon={<Trash2 size={14} />}
                          variant="ghost"
                          size="sm"
                          disabled={rows.length <= 1}
                          onClick={() => onRemove(id)}
                        />
                      </td>
                    )}
                  </tr>
                );
              })}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={totalColumns} className="field-help">
                    {rows.length === 0 ? emptyMessage : `No row matches “${query.trim()}”.`}
                  </td>
                </tr>
              )}
              {visibleRows.length > 0 &&
                Array.from({ length: Math.max(0, targetRows - visibleRows.length) }, (_, i) => (
                  <tr key={`filler-${i}`} className="participants-filler" aria-hidden>
                    <td colSpan={totalColumns} />
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
