import { Plus, Trash2 } from "lucide-react";
import { IconButton, Button } from "./Button";
import { SelectionPicker, type SelectionItem } from "./SelectionList";
import { SegmentedControl } from "./SegmentedControl";
import { CoordinateInput, type Coordinate } from "./CoordinateInput";
import { channelCss } from "../pages/_shared/scene/model";

export type ElectrodePair = [string, string];

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
}) {
  /* One grammar (plan C2): each slot of a pair opens the SAME list every other picker on the page
     opens, in single-select mode — filter, keyboard, `N of M`. It was a `Select` combo, which is a
     different control with a different keyboard and a different way of searching 185 names, so a
     user who had learned to pick electrodes for an ex bucket had to learn it again here.
     The pairs model itself is unchanged: `[a, b]` strings, which is what lane EL's scene pane and
     `buildConfig` both read. */
  const options: SelectionItem[] = electrodes.map((e) => ({ id: e, label: e }));

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
            <div key={i} className="electrode-pair-row" data-active-pair={activeSlot !== undefined && Math.floor(activeSlot / 2) === i ? "true" : undefined}>
              {/* The pair's own channel colour, from the ONE palette (`channelCss`, Okabe-Ito) —
                  never a literal here, so the editor and the dots in the scene cannot drift. */}
              <span className="electrode-pair-index" style={{ color: channelCss(i) }}>
                {i + 1}
              </span>
              <SelectionPicker
                items={options}
                value={pair[0] ? [pair[0]] : []}
                onChange={(v) => onPairsChange(pairs.map((p, idx) => (idx === i ? [v[0] ?? "", p[1]] : p)))}
                mode="single"
                label={`Pair ${i + 1} electrode A`}
                title={`Pair ${i + 1} — electrode A`}
                headers={{ label: "Electrode" }}
                filterPlaceholder="Filter electrodes…"
                idPrefix={`pair-${i}-a`}
                onOpen={() => onActiveSlotChange?.(i * 2)}
                placeholder="Electrode A"
                disabled={disabled}
              />
              <SelectionPicker
                items={options}
                value={pair[1] ? [pair[1]] : []}
                onChange={(v) => onPairsChange(pairs.map((p, idx) => (idx === i ? [p[0], v[0] ?? ""] : p)))}
                mode="single"
                label={`Pair ${i + 1} electrode B`}
                title={`Pair ${i + 1} — electrode B`}
                headers={{ label: "Electrode" }}
                filterPlaceholder="Filter electrodes…"
                idPrefix={`pair-${i}-b`}
                onOpen={() => onActiveSlotChange?.(i * 2 + 1)}
                placeholder="Electrode B"
                disabled={disabled}
              />
              <IconButton
                aria-label={`Remove pair ${i + 1}`}
                icon={<Trash2 size={14} />}
                disabled={disabled}
                onClick={() => onPairsChange(pairs.filter((_, idx) => idx !== i))}
              />
            </div>
          ))
        : freehandPairs.map((pair, i) => (
            <div key={i} className="electrode-pair-row" data-active-pair={activeSlot !== undefined && Math.floor(activeSlot / 2) === i ? "true" : undefined}>
              {/* The pair's own channel colour, from the ONE palette (`channelCss`, Okabe-Ito) —
                  never a literal here, so the editor and the dots in the scene cannot drift. */}
              <span className="electrode-pair-index" style={{ color: channelCss(i) }}>
                {i + 1}
              </span>
              <CoordinateInput value={pair[0]} onValueChange={(c) => onFreehandPairsChange(freehandPairs.map((p, idx) => (idx === i ? [c, p[1]] : p)))} disabled={disabled} />
              <CoordinateInput value={pair[1]} onValueChange={(c) => onFreehandPairsChange(freehandPairs.map((p, idx) => (idx === i ? [p[0], c] : p)))} disabled={disabled} />
              <IconButton
                aria-label={`Remove pair ${i + 1}`}
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
            ? onPairsChange([...pairs, ["", ""]])
            : onFreehandPairsChange([
                ...freehandPairs,
                [
                  { x: undefined, y: undefined, z: undefined },
                  { x: undefined, y: undefined, z: undefined },
                ],
              ])
        }
      >
        Add pair
      </Button>
    </div>
  );
}
