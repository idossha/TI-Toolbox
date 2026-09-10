/**
 * Per-label atlas colours: the legend's own `"#rrggbb"` becomes the texel the shader paints a
 * region with (`scene/glScene.ts` `buildLabelColors`).
 *
 * The whole colour path is arithmetic — the server has emitted `legend[].color` from the `.annot`
 * colour table (and from `labeling_LUT.txt` for a subcortical volume) since the legend existed, so
 * nothing here parses a file. What can go wrong is the *indexing*: a colour written at the region's
 * `id` (its `.annot` row within its hemisphere) instead of at its `label` (the `uint16` that
 * actually appears in the payload) puts the left hemisphere's colours on the right one's regions,
 * silently and plausibly. Every assertion below is about that.
 */
import { describe, expect, it } from "vitest";
import { buildLabelColors, labelSwatchColor } from "../../src/renderer/scene/glScene";
import { fixtureLegend, hslHex } from "../../src/renderer/dev/sceneFixtures";

const LABEL_STATE_SIZE = 256 * 256;

const texel = (colors: Uint8Array, label: number): [number, number, number] => [
  colors[label * 3] as number,
  colors[label * 3 + 1] as number,
  colors[label * 3 + 2] as number,
];

describe("buildLabelColors", () => {
  it("writes each row's colour at its wire label, not at its .annot row index", () => {
    // The shape the real legend has: `id` repeats across hemispheres (row 1 of lh and row 1 of rh)
    // while `label` does not. Indexing by `id` would collide these two rows onto one texel.
    const colors = buildLabelColors([
      { label: 1, color: "#196428" },
      { label: 2, color: "#7d64a0" },
      { label: 41, color: "#641900" },
    ] as { label: number; color: string }[]);
    expect(texel(colors, 1)).toEqual([0x19, 0x64, 0x28]);
    expect(texel(colors, 2)).toEqual([0x7d, 0x64, 0xa0]);
    expect(texel(colors, 41)).toEqual([0x64, 0x19, 0x00]);
  });

  it("is exactly three bytes per uint16 label id", () => {
    expect(buildLabelColors([]).length).toBe(LABEL_STATE_SIZE * 3);
  });

  it("leaves label 0 black, which is how a fragment says it has no region", () => {
    // Not a detail: `NO_REGION` is 0 in the payload, and the shader reads a black texel as "fall
    // back to the part tint". A legend that tried to colour label 0 would tint the cerebellum and
    // the brainstem — everything the grey-matter tag covers that no cortical atlas describes.
    const colors = buildLabelColors([{ label: 0, color: "#ff0000" }]);
    expect(texel(colors, 0)).toEqual([0, 0, 0]);
  });

  it("skips a row with no colour, an unparseable one, or a label out of range", () => {
    const colors = buildLabelColors([
      { label: 3, color: null },
      { label: 4, color: "red" },
      { label: 5, color: "#abc" },
      { label: 65_536, color: "#ffffff" },
      { label: -2, color: "#ffffff" },
      { label: 6, color: "  #00FF80  " },
    ] as { label: number; color: string | null }[]);
    for (const label of [3, 4, 5]) expect(texel(colors, label)).toEqual([0, 0, 0]);
    // Trimmed and case-insensitive, because a hand-written LUT is neither.
    expect(texel(colors, 6)).toEqual([0x00, 0xff, 0x80]);
  });

  it("gives every region of the fixture atlas a colour of its own", () => {
    // The premise of the whole change: a legend whose swatches all match cannot tell a user which
    // patch is which, which is what the single flat blue did.
    const legend = fixtureLegend();
    const colors = buildLabelColors(legend);
    const seen = new Set(legend.map((row) => texel(colors, row.label).join(",")));
    expect(legend.length).toBeGreaterThan(8);
    expect(seen.size).toBe(legend.length);
    // …and each is the colour the legend actually names, so a pixel test can compute the answer.
    for (const row of legend) {
      expect(texel(colors, row.label)).toEqual([
        parseInt(row.color.slice(1, 3), 16),
        parseInt(row.color.slice(3, 5), 16),
        parseInt(row.color.slice(5, 7), 16),
      ]);
    }
  });
});

describe("labelSwatchColor", () => {
  it("answers the colour the shader draws, normalised, so a swatch cannot drift from the anatomy", () => {
    const legend = [{ label: 7, color: "#AaBbCc" }] as { label: number; color: string }[];
    expect(labelSwatchColor(legend, 7)).toBe("#aabbcc");
  });

  it("answers null for an unknown label and for a row with no usable colour", () => {
    expect(labelSwatchColor([], 7)).toBeNull();
    expect(labelSwatchColor([{ label: 7, color: "" }] as { label: number; color: string }[], 7)).toBeNull();
  });
});

describe("hslHex", () => {
  it("is the closed form the fixture legend's colours come from", () => {
    // Anchors a test can check by hand rather than by rerunning the function.
    expect(hslHex(0, 1, 0.5)).toBe("#ff0000");
    expect(hslHex(120, 1, 0.5)).toBe("#00ff00");
    expect(hslHex(240, 1, 0.5)).toBe("#0000ff");
    expect(hslHex(0, 0, 0.5)).toBe("#808080");
  });
});
