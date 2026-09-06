// @vitest-environment jsdom
/**
 * The channel legend (N2).
 *
 * What is worth pinning here is not that a button renders, but that the legend and the scene agree
 * on the *same* channel colour: if `channelCss` and the point colours ever drift apart, "pair 2 is
 * orange" stops being true in one of the two places and the user has no way to tell which.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ChannelLegend, channelLabel } from "../../src/renderer/ui/ChannelLegend";
import { channelCss } from "../../src/renderer/pages/_shared/scene/model";
import { SCENE_PALETTE } from "../../src/renderer/scene/palette";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("channelLabel", () => {
  it("reads as the channel it is, with a placeholder for the slot nobody filled yet", () => {
    expect(channelLabel(["E1", "E2"])).toBe("E1 → E2");
    expect(channelLabel(["E1", ""])).toBe("E1 → —");
  });
});

describe("ChannelLegend", () => {
  it("draws one chip per pair, marks the active one, and reports a click as that channel", () => {
    const clicked: number[] = [];
    act(() =>
      root.render(
        <ChannelLegend
          pairs={[
            ["Fp1", "Fp2"],
            ["C3", "C4"],
            ["P3", "P4"],
            ["O1", "O2"],
          ]}
          activeChannel={2}
          onActivate={(c) => clicked.push(c)}
        />,
      ),
    );
    const chips = [...host.querySelectorAll<HTMLButtonElement>(".channel-chip")];
    expect(chips.map((c) => c.textContent)).toEqual(["Fp1 → Fp2", "C3 → C4", "P3 → P4", "O1 → O2"]);
    expect(chips.map((c) => c.dataset.active)).toEqual(["false", "false", "true", "false"]);
    // The active pair is stated by more than its own hue: the hues already mean "which pair".
    expect(chips[2]?.getAttribute("aria-pressed")).toBe("true");
    act(() => {
      chips[0]?.click();
    });
    expect(clicked).toEqual([0]);
  });

  it("uses the SAME colour the scene draws that channel's dots in", () => {
    act(() => root.render(<ChannelLegend pairs={[["Fp1", "Fp2"], ["C3", "C4"], ["P3", "P4"], ["O1", "O2"]]} activeChannel={0} />));
    const chips = [...host.querySelectorAll<HTMLButtonElement>(".channel-chip")];
    chips.forEach((chip, channel) => {
      // The RENDERER's palette is the one source: the chip, the dot shader and this assertion all
      // read `SCENE_PALETTE.channels`, so a colour change cannot land in one of the three only.
      const rgb = (SCENE_PALETTE.channels[channel] as number[]).map((v: number) => Math.round(v * 255));
      expect(chip.dataset.color).toBe(`rgb(${rgb.join(",")})`);
      expect(chip.dataset.color).toBe(channelCss(channel));
    });
    // Four pairs, four distinct chips — the mTI case.
    expect(new Set(chips.map((c) => c.dataset.color)).size).toBe(4);
  });

  it("renders nothing at all when the montage has no pairs yet", () => {
    act(() => root.render(<ChannelLegend pairs={[]} activeChannel={null} />));
    expect(host.querySelector(".channel-legend")).toBeNull();
  });
});
