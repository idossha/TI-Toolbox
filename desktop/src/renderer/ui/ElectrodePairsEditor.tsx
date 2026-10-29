import { Plus, Trash2 } from "lucide-react";
import { IconButton, Button } from "./Button";
import { SelectionPicker, type SelectionItem } from "./SelectionList";
import { SegmentedControl } from "./SegmentedControl";
import { CoordinateInput, type Coordinate } from "./CoordinateInput";
import { advanceSlot, channelCss, channelName, electrodeSlotName, withSlot } from "../pages/_shared/scene/model";

export type ElectrodePair = [string, string];

/**
 * Removes the whole group of `step` pairs that pair `index` belongs to, so a montage built in
 * two-pair channels can never be left with an odd number of pairs. `step === 1` is the plain
 * "remove this row".
 */
export function removeGroup<T>(pairs: T[], index: number, step: number): T[] {
  if (step <= 1) return pairs.filter((_, i) => i !== index);
  const start = Math.floor(index / step) * step;
  return pairs.filter((_, i) => i < start || i >= start + step);
}

/**
 * Basic pairs editor: electrode-net mode picks two labels from `electrodes` per pair; free-hand
 * mode collects a coordinate per side. Page agents extend this for montage-specific chrome
 * (per-pair current, save/load) — this covers the shared shape only.
 */
export function ElectrodePairsEditor({
  mode,
  onModeChange,
  electrodes,
  pairs,
  onPairsChange,
  freehandPairs,
  onFreehandPairsChange,
  activeSlot,
  onActiveSlotChange,
  disabled,
  pairStep = 1,
}: {
  mode: "net" | "freehand";
  /**
   * Omitted where the caller has only one mode to offer — and then the switcher is not drawn at
   * all. `pages/simulator/MontageManager.tsx` passed `() => {}`, which rendered a control that
   * moved and snapped back: a montage built on an EEG net has no free-hand mode to switch to.
   */
  onModeChange?: (mode: "net" | "freehand") => void;
  electrodes: string[];
  pairs: ElectrodePair[];
  onPairsChange: (pairs: ElectrodePair[]) => void;
  freehandPairs: [Coordinate, Coordinate][];
  onFreehandPairsChange: (pairs: [Coordinate, Coordinate][]) => void;
  /**
   * The slot the next pick fills, **flattened**: `pair * 2 + column`. The form's focus and the
   * 3-D pane's active-pair cursor are one thing (lane EL), so opening a slot's picker here moves
   * the cursor there and a pick in the pane fills the slot the form is showing.
   */
  activeSlot?: number;
  onActiveSlotChange?: (slot: number) => void;
  disabled?: boolean;
  /**
   * How many channels (electrode pairs) one "add" adds and one "remove" removes. A TI montage is
   * two channels and an mTI montage an even number from four, so the Simulator passes 2 and an odd
   * channel count can never be produced by the buttons (`Montage.simulation_mode` accepts 2 or
   * 4+, never 3). Defaults to 1 for every other caller.
   */
  pairStep?: number;
}) {
  /* One grammar (plan C2): each electrode slot opens the SAME list every other picker on the page
     opens, in single-select mode — filter, keyboard, `N of M`. It was a `Select` combo, which is a
     different control with a different keyboard and a different way of searching 185 names, so a
     user who had learned to pick electrodes for an ex bucket had to learn it again here.
     The pairs model itself is unchanged: `[Ek+, Ek-]` strings, which is what the scene pane and
     `buildConfig` both read. Naming is the app's one convention (`electrodeSlotName`): channel k
     is electrodes Ek+ and Ek-, never "pair k" or "A"/"B". */
  /** The options for one slot: an electrode already set in ANOTHER slot is listed, named by the
   *  slot holding it, and cannot be picked — one electrode cannot be two poles. */
  const optionsFor = (slot: number): SelectionItem[] => {
    const used = new Map<string, number>();
    pairs.forEach((pair, i) =>
      pair.forEach((name, pole) => {
        if (name) used.set(name, i * 2 + pole);
      }),
    );
    return electrodes.map((e) => {
      const at = used.get(e);
      return at === undefined || at === slot ? { id: e, label: e } : { id: e, label: e, disabled: true, reason: `Already ${electrodeSlotName(at)}` };
    });
  };
  /** Writes slot `slot` and moves the cursor the way a scene click does: on to the next empty slot
   *  after a pick, onto the slot itself after a clear. */
  const setSlot = (slot: number, name: string) => {
    const next = withSlot(pairs, slot, name);
    onPairsChange(next);
    onActiveSlotChange?.(name ? advanceSlot(next, slot) : slot);
  };
  const slotPicker = (i: number, pole: 0 | 1) => {
    const slot = i * 2 + pole;
    const name = electrodeSlotName(slot);
    return (
      <span className="electrode-slot" data-slot={slot} data-active-slot={activeSlot === slot ? "true" : undefined}>
        {/* The slot's role stays on screen once it is filled — "E193" alone does not say which
            pole of which channel it is. */}
        <span className="electrode-slot-role" style={{ color: channelCss(i) }}>
          {name}
        </span>
        <SelectionPicker
          items={optionsFor(slot)}
          value={pairs[i]?.[pole] ? [pairs[i]![pole]] : []}
          onChange={(v) => setSlot(slot, v[0] ?? "")}
          mode="single"
          label={`${channelName(i)} ${name} electrode`}
          title={`${channelName(i)} — ${name}`}
          headers={{ label: "Electrode", reason: "In use" }}
          filterPlaceholder="Filter electrodes…"
          idPrefix={`pair-${i}-${pole === 0 ? "a" : "b"}`}
          onOpen={() => onActiveSlotChange?.(slot)}
          placeholder="Choose…"
          disabled={disabled}
        />
      </span>
    );
  };
  const removeLabel = (i: number) =>
    pairStep > 1 ? `Remove channels ${i + 1}\u2013${i + pairStep}` : `Remove channel ${i + 1}`;

  return (
    <div className="electrode-pairs">
      {/* DESIGN.md §4.2 rule 9 — where the electrode positions come from is a two-option
          exclusive choice, so it is one 28px segment row, not a stack of radios. Drawn only when
          the caller can actually act on it: a control that cannot change anything is worse than
          no control, because the user has to click it to find that out. */}
      {onModeChange && (
        <SegmentedControl
          value={mode}
          onValueChange={(v) => onModeChange(v as "net" | "freehand")}
          options={[
            { value: "net", label: "From EEG net" },
            { value: "freehand", label: "Free-hand coordinates" },
          ]}
          disabled={disabled}
          aria-label="Electrode source"
        />
      )}
      {mode === "net"
        ? pairs.map((pair, i) => (
            <div key={i} className="electrode-pair-row" data-channel={i} data-active-pair={activeSlot !== undefined && Math.floor(activeSlot / 2) === i ? "true" : undefined}>
              {/* The channel's own colour, from the ONE palette (`channelCss`, Okabe-Ito) —
                  never a literal here, so the editor and the dots in the scene cannot drift. */}
              <span className="electrode-pair-index" style={{ color: channelCss(i) }}>
                {channelName(i)}
              </span>
              {slotPicker(i, 0)}
              {slotPicker(i, 1)}
              <IconButton
                aria-label={removeLabel(i)}
                icon={<Trash2 size={14} />}
                disabled={disabled || (pairStep > 1 && i % pairStep !== 0)}
                onClick={() => onPairsChange(removeGroup(pairs, i, pairStep))}
              />
            </div>
          ))
        : freehandPairs.map((pair, i) => (
            <div key={i} className="electrode-pair-row" data-active-pair={activeSlot !== undefined && Math.floor(activeSlot / 2) === i ? "true" : undefined}>
              <span className="electrode-pair-index" style={{ color: channelCss(i) }}>
                {channelName(i)}
              </span>
              <CoordinateInput value={pair[0]} onValueChange={(c) => onFreehandPairsChange(freehandPairs.map((p, idx) => (idx === i ? [c, p[1]] : p)))} disabled={disabled} />
              <CoordinateInput value={pair[1]} onValueChange={(c) => onFreehandPairsChange(freehandPairs.map((p, idx) => (idx === i ? [p[0], c] : p)))} disabled={disabled} />
              <IconButton
                aria-label={`Remove channel ${i + 1}`}
                icon={<Trash2 size={14} />}
                disabled={disabled}
                onClick={() => onFreehandPairsChange(freehandPairs.filter((_, idx) => idx !== i))}
              />
            </div>
          ))}
      <Button
        variant="ghost"
        size="sm"
        icon={<Plus size={14} />}
        disabled={disabled}
        onClick={() =>
          mode === "net"
            ? onPairsChange([...pairs, ...Array.from({ length: pairStep }, () => ["", ""] as ElectrodePair)])
            : onFreehandPairsChange([
                ...freehandPairs,
                [
                  { x: undefined, y: undefined, z: undefined },
                  { x: undefined, y: undefined, z: undefined },
                ],
              ])
        }
      >
        {pairStep > 1 ? `Add ${pairStep} channels` : "Add channel"}
      </Button>
    </div>
  );
}
