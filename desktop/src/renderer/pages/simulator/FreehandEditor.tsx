/**
 * Free-hand placements — the **author** side only.
 *
 * Maintainer, 2026-09-06: *"there is a button and if the user clicks on it, it opens up the menu.
 * It should not have its own section"* — so this is just the editor card, opened by the Jobs
 * table's "New placement" footer button exactly as "New montage" opens the montage editor
 * (`MontageManager`). Choosing a saved set is a job row's business (its Montage cell lists them),
 * which is why nothing here lists the existing configurations.
 *
 * The draft is page-session state, so closing the editor — or leaving the page — never discards an
 * unfinished placement.
 *
 * Since 2026-09-06 it is also the **placement** UI: the 3-D pane draws the subject's scalp and a
 * click on it writes a coordinate into this table. Maintainer: *"the user experience should be very
 * clear how a user can add an electrode, remove an electrode and it should not be ambiguous which
 * electrode is being manipulated."* Four rules answer that, each with the failure it prevents:
 *
 *  - **Selection comes first, always.** Nothing is placed until a row is selected, and the
 *    selection never moves on its own: click a row, click the scalp, and that row — and only that
 *    row — takes the coordinate. Clicking again moves it. Without this a click always did
 *    *something* and the user had to read the table afterwards to find out what.
 *  - **The selection is shown, not explained.** The row's own colour swatch IS the selector: a
 *    radio target in the first column that fills with the electrode's colour and takes a white
 *    inner dot when it is the one a scalp click writes, with the label in the accent colour and
 *    the number in bold beside it — and the same electrode ringed and enlarged on the scalp.
 *    No sentence anywhere (maintainer, 2026-09-06: *"remove that 'E1 is selected place blah
 *    blah blah'"*), and no row background wash: the cells carry their own surface, so a tint on
 *    the `<tr>` showed only in the gaps between the inputs — maintainer, 2026-09-06: *"this
 *    broken shading is awful ... maybe have a switch to switch between the electrodes"*.
 *  - **Every row has its own colour**, shown as a swatch here and as that dot's colour on the
 *    scalp. Pair colour would put the same hue on two dots, which is the question the user is
 *    trying to answer.
 *  - **Hover joins the two**: a row lights its dot and a dot lights its row, so "which is which"
 *    never needs counting.
 *  - **Add and remove are buttons, not side effects.** Rows come in pairs because an odd count is
 *    never a valid montage, and a click on the scalp never grows the table.
 */
import { useRef } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { Field, TextInput } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { isSafeName, safeNameProblem } from "../_shared/entityNames";
import { putFreehand, type ElectrodePosition, type FreehandConfig } from "./api";
import { useFreehandDraft } from "./freehandDraft";
import { POSITIONS_PER_STEP, isPlaced, isValidPositionCount, positionSwatch, repeatedLabels } from "./freehandPlacement";
import { MIN_ELECTRODE_SEPARATION_MM, coincidentElectrodes } from "./types";
import "./freehand-editor.css";

/** A row still at the origin has not been placed: the origin is inside the head, so no scalp pick
 *  lands there, and a blank row starts there whatever its label says. */
const atOrigin = (p: ElectrodePosition) => p.x === 0 && p.y === 0 && p.z === 0;

/**
 * Why these positions cannot be saved as a placement, or `null` when they can: every row placed
 * (none left at the origin), every coordinate a number, and no two electrodes on one spot — the
 * rules a job built from the placement must meet before SimNIBS puts a pad on the scalp for each.
 */
export function freehandPlacementProblem(positions: ElectrodePosition[]): string | null {
  const label = (p: ElectrodePosition, i: number) => p.label || `E${i + 1}`;
  const unplaced = positions.flatMap((p, i) => (atOrigin(p) ? [label(p, i)] : []));
  if (unplaced.length > 0) {
    return `Place every electrode on the scalp: ${unplaced.join(", ")} ${unplaced.length === 1 ? "is" : "are"} not placed yet.`;
  }
  const bad = positions.findIndex((p) => ![p.x, p.y, p.z].every((v) => typeof v === "number" && Number.isFinite(v)));
  if (bad >= 0) return `${label(positions[bad]!, bad)} has a coordinate that is not a number.`;
  const pairs = Array.from({ length: Math.floor(positions.length / 2) }, (_, i) => {
    const [a, b] = [positions[2 * i]!, positions[2 * i + 1]!];
    return [[a.x, a.y, a.z], [b.x, b.y, b.z]] as [[number, number, number], [number, number, number]];
  });
  const close = coincidentElectrodes(pairs)[0];
  if (close) {
    const [a, b] = close;
    return `${label(positions[a - 1]!, a - 1)} and ${label(positions[b - 1]!, b - 1)} are less than ${MIN_ELECTRODE_SEPARATION_MM} mm apart: each electrode needs its own place on the scalp.`;
  }
  return null;
}

export function FreehandEditor({ subjects: selectedSubjects, onClose }: { subjects: string[]; onClose: () => void }) {
  const queryClient = useQueryClient();

  // One draft for the page (see `freehandDraft.tsx`): the 3-D pane writes into the same rows this
  // table edits, so a click on the scalp and a typed number are the same act.
  const {
    subject: editSubject,
    setSubject: setEditSubject,
    name,
    setName,
    positions,
    setPositions,
    active,
    setActive,
    add,
    remove,
    reset,
    hovered,
    setHovered,
  } = useFreehandDraft();

  const activeEditSubject = editSubject ?? selectedSubjects[0];

  // The radio targets, so ↑/↓ can move focus with the selection.
  const targets = useRef<Array<HTMLButtonElement | null>>([]);

  const save = useMutation({
    mutationFn: () => {
      // FreehandConfig.type is on-disk stim_configs semantics (unipolar/multipolar), not
      // xyz/label — U for a 2-pair (4-position) montage, M for 4+ pairs (8+ positions). See
      // contracts/openapi.yaml's FreehandConfig doc comment / tit/catalog.py::_read_freehand_file.
      const type: FreehandConfig["type"] = positions.length / 2 >= 4 ? "M" : "U";
      return putFreehand(activeEditSubject!, name.trim(), { name: name.trim(), type, electrode_positions: positions });
    },
    onSuccess: () => {
      notify.success(`Saved free-hand configuration "${name.trim()}" for ${activeEditSubject}.`);
      reset();
      // The job row's Montage cell reads this key, so it picks the new set up straight away.
      void queryClient.invalidateQueries({ queryKey: ["freehand", activeEditSubject] });
      onClose();
    },
    onError: (err: unknown) => notify.error("Could not save the free-hand configuration.", err instanceof Error ? err.message : undefined),
  });

  const validCount = isValidPositionCount(positions.length);
  const repeated = repeatedLabels(positions);
  // `tit.catalog.put_freehand_config` holds a new name to `is_safe_name`: refused here, in the
  // server's terms, rather than by a 422 after the click.
  const trimmedName = name.trim();
  const nameProblem = trimmedName && !isSafeName(trimmedName) ? safeNameProblem(trimmedName, "placement") : null;
  const placementProblem = freehandPlacementProblem(positions);
  const saveProblem =
    (!activeEditSubject && "Choose a subject.") ||
    (!trimmedName && "Name the placement.") ||
    nameProblem ||
    (!validCount && "Use 4 positions, or 8, 12, 16 …") ||
    (repeated.length > 0 && `${repeated.join(", ")} is used more than once.`) ||
    placementProblem ||
    null;

  return (
    <Card>
      <CardHeader title="New free-hand placement" />
      <CardBody>
        <div className="form-grid">
          <Field label="Subject" htmlFor="sim-freehand-subject" required>
            <Select
              id="sim-freehand-subject"
              value={activeEditSubject}
              onValueChange={setEditSubject}
              options={selectedSubjects.map((s) => ({ value: s, label: s }))}
              placeholder="Choose a subject"
              disabled={selectedSubjects.length === 0}
            />
          </Field>
          <Field label="Configuration name" htmlFor="sim-freehand-name" required>
            <TextInput id="sim-freehand-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. custom_4electrode" />
            {nameProblem && (
              <span className="field-error" data-testid="freehand-name-error">
                {nameProblem}
              </span>
            )}
          </Field>
        </div>
        <div className="data-table-container scroll-x" style={{ marginTop: "var(--space-3)" }}>
          <table className="data-table freehand-table">
            <thead>
              <tr>
                <th className="freehand-target-col"><span className="visually-hidden">Selected</span></th>
                <th>#</th>
                <th>Label</th>
                <th data-align="right">X (mm)</th>
                <th data-align="right">Y (mm)</th>
                <th data-align="right">Z (mm)</th>
                <th />
              </tr>
            </thead>
            <tbody role="radiogroup" aria-label="Selected electrode">
              {positions.map((pos, i) => (
                <tr
                  key={i}
                  data-testid={`freehand-row-${i}`}
                  data-active={i === active ? "true" : undefined}
                  aria-selected={i === active}
                  data-placed={isPlaced(pos) ? "true" : undefined}
                  /* Clicking the row makes it the one a scalp click writes — the whole answer to
                     "which electrode am I manipulating". Clicking the selected row again clears the
                     selection, so "place nothing" is reachable without a second control. Not
                     `onFocus`: tabbing through the X of row 3 to reach row 4 would silently re-aim
                     the gesture. */
                  onClick={() => setActive(i === active ? null : i)}
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(hovered === i ? null : hovered)}
                >
                  <td className="freehand-target-col">
                    {/* The swatch is the selector. A radio, not a checkbox: exactly one electrode
                        is ever the target, and ↑/↓ moves it without the mouse. */}
                    <button
                      type="button"
                      role="radio"
                      aria-checked={i === active}
                      aria-label={`Target position ${i + 1}`}
                      data-testid={`freehand-target-${i}`}
                      className="freehand-target"
                      ref={(el) => {
                        targets.current[i] = el;
                      }}
                      /* Roving tabstop: one Tab reaches the group, ↑/↓ walks it. */
                      tabIndex={i === (active ?? 0) ? 0 : -1}
                      onClick={(e) => {
                        e.stopPropagation();
                        setActive(i === active ? null : i);
                      }}
                      onKeyDown={(e) => {
                        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
                        e.preventDefault();
                        const next = (i + (e.key === "ArrowDown" ? 1 : positions.length - 1)) % positions.length;
                        setActive(next);
                        targets.current[next]?.focus();
                      }}
                    >
                      <span
                        className="freehand-swatch"
                        data-testid={`freehand-swatch-${i}`}
                        style={{ background: positionSwatch(i) }}
                        aria-hidden
                      />
                    </button>
                  </td>
                  <td className="mono freehand-number">{i + 1}</td>
                  <td className="freehand-label-cell">
                    <TextInput
                      value={pos.label ?? ""}
                      aria-label={`Position ${i + 1} label`}
                      placeholder="optional"
                      onChange={(e) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, label: e.target.value } : row)))}
                    />
                  </td>
                  {(["x", "y", "z"] as const).map((axis) => (
                    <td key={axis} data-align="right">
                      <NumberInput
                        value={pos[axis]}
                        step={0.1}
                        onValueChange={(v) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, [axis]: v ?? 0 } : row)))}
                        aria-label={`Position ${i + 1} ${axis.toUpperCase()}`}
                      />
                    </td>
                  ))}
                  <td>
                    <IconButton
                      aria-label={`Remove position ${i + 1}`}
                      icon={<Trash2 size={14} />}
                      disabled={positions.length <= 2}
                      /* Removing a row renumbers the rest (2.5.0's `deleteChecked`) and drops its
                         dot from the pane, because the dots are derived from these rows. */
                      onClick={(e) => {
                        e.stopPropagation();
                        remove(i);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Muted guidance, not a red error line. The count is wrong for as long as the user is
            still building the table, and colouring that "broken" from the first click says they
            have made a mistake when they have simply not finished; the blocking reason is carried
            by the disabled Save button directly above it (DESIGN.md §6.3). */}
        <span className="field-help">
          Use 4 positions (2 channels, standard TI) or 8, 12, 16 … (an even number of channels from 4, multi-channel mTI).
        </span>
        {/* Unlike the count, a repeated label is a mistake, not an unfinished table: saving would
            keep only one of the positions that share it. */}
        {repeated.length > 0 && (
          <span className="field-error" role="alert" data-testid="freehand-repeated-labels">
            Each position needs its own label: {repeated.join(", ")} is used more than once.
          </span>
        )}
        {/* Unplaced rows are an unfinished table (muted); two electrodes on one spot is a mistake. */}
        {placementProblem && (
          <span
            className={positions.some(atOrigin) ? "field-help" : "field-error"}
            role={positions.some(atOrigin) ? undefined : "alert"}
            data-testid="freehand-placement-problem"
          >
            {placementProblem}
          </span>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-3)" }}>
          {/* A pair at a time: `isValidPositionCount` accepts 4, 8, 12, …, so an odd count is never
              a configuration anyone can save and offering it is offering a dead end. */}
          <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={add}>
            {POSITIONS_PER_STEP > 1 ? "Add channel" : "Add electrode"}
          </Button>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={save.isPending}
              disabled={saveProblem !== null}
              title={saveProblem ?? undefined}
              onClick={() => save.mutate()}
            >
              Save placement
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
