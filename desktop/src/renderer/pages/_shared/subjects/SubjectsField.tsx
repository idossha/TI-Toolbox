/**
 * `SubjectsField` — the one subject control (plan §3, J1-J4).
 *
 * Before this, four pages solved one problem four ways: Pre-processing a readiness table held
 * open, Simulator a collapsed summary opening `ui/SubjectPicker`, Optimizer a `Field` +
 * `MultiSelect` with its own blocked wording, Analyzer a third variant, plus the Source panel's
 * own filtered picker. A user learned the control three times and each page invented its own
 * words for "this subject cannot run".
 *
 * The grammar, identical on every page:
 *
 *   Subjects   ernie · one job per subject                      [ Change subjects… ]
 *   ─ when open ─────────────────────────────────────────────────────────────────────
 *   [filter…]                                                            [ Done ]
 *   ☑ | Subject | Present                        | Why not
 *   ☑ | ernie   | raw fastsurfer m2m dwi         |
 *   ☐ | 101     | raw ·m2m·                      | no GSN-HydroCel-185 leadfield
 *
 * The page supplies only *what a subject has* (`columns`) and *whether it can be used here*
 * (`eligibility`). Everything else — the summary line, the disclosure, the filter, select-all,
 * the row shape, the reason — belongs to this file, so it cannot drift between pages.
 *
 * Deliberately NOT a `FormSection`: `ui/Layout.tsx`'s section registers with `RunWork`'s fill
 * controller, which was measured to oscillate a subject table open/closed once later page content
 * grew after mount (Simulator and Analyzer both carry that note). A page still wraps this in its
 * own `data-tier="1"` div, which is what `_metrics.ts`'s `firstScreenControls` reads.
 */
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useState } from "react";
import { usePageSession } from "../../../app/pageSession";
import { Button } from "../../../ui/Button";
import { SelectionList, type SelectionItem } from "../../../ui/SelectionList";
import { Chip } from "../../../ui/Status";
import { subjectsSummary } from "./model";
import type { SubjectColumn, SubjectLike, SubjectsFieldProps } from "./types";
import "./subjects.css";

function PresenceCell<T extends SubjectLike>({ subject, columns }: { subject: T; columns: SubjectColumn<T>[] }) {
  return (
    <span className="run-presence">
      {columns.map((c) => {
        const on = c.present(subject);
        // A `flag` column is a state, not a presence: shown only when true, and shown as a
        // warning (Pre-processing's "not converted" — DICOMs staged, no BIDS directory yet, which
        // otherwise reads exactly like an empty row).
        if (c.kind === "flag") {
          return on ? (
            <Chip key={c.id} kind="warning" title={c.title}>
              {c.label}
            </Chip>
          ) : null;
        }
        return (
          <Chip key={c.id} kind={on ? "success" : "neutral"} missing={!on} title={c.title}>
            {c.label}
          </Chip>
        );
      })}
    </span>
  );
}

export function SubjectsField<T extends SubjectLike>({
  subjects,
  value,
  onChange,
  columns = [],
  eligibility,
  mode = "per-subject",
  defaultOpen = false,
  minRows = 0,
  fill = false,
  help,
  emptyMessage = "No subjects in this project yet.",
  loading = false,
}: SubjectsFieldProps<T>) {
  const bodyId = useId();
  const [open, setOpen] = usePageSession("subjectsField.open", defaultOpen);
  const [query, setQuery] = usePageSession("subjectsField.query", "");

  // `fill`: the box's height is decided by the ROOM the page has, not by a constant, and ground
  // rows are drawn to the bottom of it. See `types.ts` for the two shapes; the formula is the same
  // in both and it is not circular — `others` is the height of everything in the column EXCEPT
  // this box, so the room it leaves does not depend on how tall this box currently is:
  //
  //     others = scroller.scrollHeight - box.clientHeight
  //     room   = scroller.clientHeight - others
  //
  // On a height-constrained box (the Source panel) the column already fills the scrollport, so
  // that reduces to the box's own height. On a run page it is what is left after the page's own
  // sections — which is also why `max-height` becomes this number rather than `none`: the 176px
  // cap existed so a 40-subject project could not push a page's steps off the first screen, and
  // the measured room keeps that promise without pinning every window to five rows.
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const [fitted, setFitted] = useState<{ rows: number; cap: number }>({ rows: 0, cap: 0 });
  const measure = useCallback(
    (el: HTMLDivElement | null) => {
      if (!el) return;
      const head = el.querySelector("thead");
      const headH = head ? head.getBoundingClientRect().height : 0;
      const row = el.querySelector("tbody tr");
      const rowH = row ? row.getBoundingClientRect().height : 0;
      if (rowH < 1) return;
      // Which of the two shapes this is, asked of the page rather than inferred from the box: a
      // page that stretches the control puts it in a flex column (`.panel-page [data-tier="1"]`),
      // and then the box's own height IS the room — measuring the scrollport instead would hand
      // back the page's own overflow and shrink a box the layout had already sized.
      const field = el.closest(".subjects-field");
      const host = field?.parentElement ?? null;
      const stretched = host !== null && getComputedStyle(host).display === "flex";
      const scroller = el.closest("[data-page-work-scroll]");
      let room = el.clientHeight;
      if (!stretched && scroller) {
        // The COLUMN's own height, never the scrollport's `scrollHeight`: `scrollHeight` is
        // `max(content, box)` and so reports zero slack exactly when there is slack — the same
        // measurement trap `pages/_shared/run/RunWork.tsx` documents for the fill controller.
        // Measured on Pre-processing at 1440x900: scrollport 712px, column 553px, so 159px were
        // free while `scrollHeight` insisted on 712 = 712.
        const column = el.closest(".run-work") ?? scroller.firstElementChild;
        const columnH = column ? column.getBoundingClientRect().height : scroller.scrollHeight;
        // `others` is everything in the column except this box, so it does not move when the box
        // grows: the room below is a fixed point, reached in one step.
        const others = columnH - el.clientHeight;
        const available = scroller.clientHeight - others;
        if (available > 0) room = available;
      }
      // Never smaller than three rows: a page with no room to give must still show a table, not a
      // sliver. Everything above that is the page's own arithmetic.
      room = Math.max(room, headH + rowH * Math.max(3, minRows));
      const rows = Math.max(0, Math.floor((room - headH) / rowH));
      // The cap is written back only on the shape whose height is its own content (a run page). On
      // a stretched box the layout already owns the height, and writing a `max-height` from a
      // measurement OF that height is a ratchet: one short measurement during load would pin the
      // box to it for ever (measured: the Source panel's table stuck at 631px of a 684px column).
      const cap = stretched ? 0 : room;
      setFitted((prev) => (prev.rows === rows && prev.cap === cap ? prev : { rows, cap }));
    },
    [minRows],
  );
  // `observe()` delivers the first callback with the box's current size, so this needs no
  // synchronous measurement of its own — and must not have one: a `setState` called synchronously
  // inside an effect is a cascading render (the repo's `react-hooks` rule rejects it).
  useLayoutEffect(() => {
    // `ResizeObserver` is absent in jsdom and in older engines; the table then renders exactly
    // the rows it has, which is the pre-`fill` behaviour and never a crash.
    if (!fill || !box || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure(box));
    observer.observe(box);
    const scroller = box.closest("[data-page-work-scroll]");
    if (scroller) observer.observe(scroller);
    // The COLUMN too (lane N2, resolving `cl2-notes.md` §8.2). The scrollport is a fixed box, so
    // a section opening beside this table resized neither of the two observed boxes and the table
    // kept the ground rows it had measured against a shorter column — the page then overflowed and
    // `RunWork`'s controller closed a section to pay for it. Arbitration by ordering is what CL2
    // flagged; the rule is that a user-touched section is not slack, so the table yields to it.
    // Safe to observe: `others = columnH - box.clientHeight` is invariant to this box's own height
    // (the column grows and shrinks with it by the same pixels), so re-measuring after the table's
    // own rows change reproduces the same `rows`/`cap` and `setFitted`'s identity check stops
    // there — one step, not a loop.
    const column = box.closest(".run-work");
    if (column) observer.observe(column);
    return () => observer.disconnect();
  }, [fill, box, measure]);
  // Rows arriving or the filter narrowing the list does not always resize an observed box —
  // re-measure on the next frame, once the change has laid out.
  const subjectCount = subjects.length;
  useEffect(() => {
    if (!fill || !box) return;
    const frame = requestAnimationFrame(() => measure(box));
    return () => cancelAnimationFrame(frame);
  }, [fill, box, measure, subjectCount, query, open]);

  const summary = subjectsSummary(value, mode);
  const targetRows = Math.max(minRows, fill ? fitted.rows : 0);

  /* The page's vocabulary, mapped onto the one selection grammar (plan C1). Everything a subject
     row *is* — its presence chips and its "why not" — is data on a `SelectionItem`; everything a
     selection *does* — click, ⇧-range, ⌘-toggle, ⌘A, Esc, the checkbox column, the filter, All ·
     None, the badge — belongs to `ui/SelectionList` and is therefore identical here, on the ex
     buckets, in the ROI picker and on the Jobs page. This control keeps only what is genuinely
     about subjects: the collapsed summary line with J4's semantics, the disclosure, and the
     measured room its table grows into.

     An ineligible subject stays SELECTABLE on purpose (J3) — `reason`, never `disabled`: its
     reason is the sentence the action bar and the Run button then print, so a user who ticks it is
     told exactly what is wrong with it. `All` still takes only the eligible ones, which is why
     they are separated here rather than by disabling the row. */
  const items = useMemo<SelectionItem[]>(
    () =>
      subjects.map((s) => {
        const verdict = eligibility ? eligibility(s) : { ok: true };
        return {
          id: s.id,
          label: s.id,
          detail: columns.length > 0 ? <PresenceCell subject={s} columns={columns} /> : undefined,
          reason: verdict.ok ? undefined : (verdict.reason ?? "cannot be used here"),
          data: { eligible: verdict.ok ? "true" : "false" },
        };
      }),
    [subjects, columns, eligibility],
  );

  /* `All` must never create a blocked run, so the ineligible subjects are handed to the list as
     `bulkExclude`: still tickable one at a time (J3), never swept in by All / ⌘A / the header box. */
  const ineligible = useMemo(
    () => (eligibility ? subjects.filter((s) => !eligibility(s).ok).map((s) => s.id) : []),
    [eligibility, subjects],
  );

  return (
    <div
      className="subjects-field"
      data-testid="subjects-field"
      data-mode={mode}
      data-open={open ? "true" : "false"}
      data-fill={fill ? "true" : undefined}
      data-selected={value.length}
    >
      <div className="subjects-field-head">
        <span className="text-eyebrow subjects-field-title">Subjects</span>
        <span className="subjects-field-summary" data-testid="subjects-summary" title={summary.text}>
          {summary.count === 0 ? (
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
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={open ? bodyId : undefined}
          data-testid="subjects-change"
        >
          {open ? "Done" : "Change subjects…"}
        </Button>
      </div>

      {open && (
        <div className="subjects-field-body" id={bodyId}>
          <SelectionList
            items={items}
            value={value}
            onChange={onChange}
            bulkExclude={ineligible}
            mode={mode === "single" ? "single" : "multi"}
            label="Subjects"
            headers={{ label: "Subject", detail: columns.length > 0 ? "Present" : undefined, reason: "Why not" }}
            query={query}
            onQueryChange={setQuery}
            filterPlaceholder="Filter subjects…"
            filterTestId="subjects-filter"
            idPrefix="subject"
            rowClassName="subject-picker-row"
            scrollTestId="subjects-field-table"
            scrollRef={setBox}
            scrollFill={fill}
            maxHeight={fill && fitted.cap > 0 ? fitted.cap : undefined}
            minRows={targetRows}
            loading={loading}
            emptyMessage={emptyMessage}
          />
        </div>
      )}
    </div>
  );
}
