// @vitest-environment jsdom
/**
 * The montage form's slot pickers and the one cursor they share with the 3-D pane
 * (`ui/ElectrodePairsEditor.tsx`, DECISIONS 2026-10-28 "channel k is Ek+ and Ek-"):
 *  - an electrode set in one slot is listed in every other slot's picker as "Already E1+" and
 *    cannot be picked there;
 *  - a pick moves the cursor to the next empty slot; clearing a slot parks the cursor on it.
 *
 * The cursor is observed through a fake `onActiveSlotChange`, the prop the Simulator page wires to
 * the scene pane. Expected slots are the flattened `pair * 2 + pole` arithmetic on a 4-slot draft.
 */
import React, { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ElectrodePairsEditor, type ElectrodePair } from "../../src/renderer/ui/ElectrodePairsEditor";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let pairsNow: ElectrodePair[] = [];
const onSlot = vi.fn();

function Harness() {
  const [pairs, setPairs] = useState<ElectrodePair[]>([
    ["", ""],
    ["", ""],
  ]);
  pairsNow = pairs;
  return (
    <ElectrodePairsEditor
      mode="net"
      electrodes={["F3", "F4", "P3", "P4"]}
      pairs={pairs}
      onPairsChange={setPairs}
      onActiveSlotChange={onSlot}
      pairStep={2}
      freehandPairs={[]}
      onFreehandPairsChange={() => {}}
    />
  );
}

describe("ElectrodePairsEditor slot pickers", () => {
  let root: Root;
  let container: HTMLDivElement;
  beforeEach(() => {
    onSlot.mockClear();
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    act(() => root.render(<Harness />));
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });
  const click = (element: Element) => act(() => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  const prefix = (slot: number) => `pair-${Math.floor(slot / 2)}-${slot % 2 === 0 ? "a" : "b"}`;
  const open = (slot: number) => click(container.querySelector(`.electrode-slot[data-slot="${slot}"] [role="combobox"]`)!);
  const row = (slot: number, id: string) => document.querySelector(`[data-testid="${prefix(slot)}-row-${id}"]`)!;
  const done = (slot: number) => click(document.querySelector(`[data-testid="${prefix(slot)}-done"]`)!);

  it("a pick advances to the next empty slot, and the electrode is taken in every other slot", () => {
    open(0);
    expect(onSlot).toHaveBeenLastCalledWith(0);
    click(row(0, "F3"));
    expect(pairsNow).toEqual([
      ["F3", ""],
      ["", ""],
    ]);
    expect(onSlot).toHaveBeenLastCalledWith(1);
    done(0);

    open(2);
    expect(row(2, "F3").getAttribute("aria-disabled")).toBe("true");
    expect(document.querySelector(`[data-testid="${prefix(2)}-reason-F3"]`)?.textContent).toBe("Already E1+");
    click(row(2, "F3"));
    expect(pairsNow[1]).toEqual(["", ""]);
    click(row(2, "P3"));
    expect(pairsNow[1]).toEqual(["P3", ""]);
    expect(onSlot).toHaveBeenLastCalledWith(3); // the next empty slot scanning forward from E2+ is E2-
  });

  it("clearing a slot parks the cursor on that slot", () => {
    open(1);
    click(row(1, "F4"));
    expect(onSlot).toHaveBeenLastCalledWith(2);
    click(row(1, "F4")); // the chosen electrode again: the slot is cleared
    expect(pairsNow[0]).toEqual(["", ""]);
    expect(onSlot).toHaveBeenLastCalledWith(1);
  });
});
