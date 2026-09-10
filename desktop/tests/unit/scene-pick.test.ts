/**
 * `scene/pickId.ts` — the encoding both fragment shaders write and JavaScript reads back.
 *
 * The shaders in `glScene.ts` pack the id by hand (`id & 255u`, `(id >> 8u) & 255u`, …) and divide
 * by 255. If this table and that arithmetic ever disagree, a click selects a *different, existing*
 * marker — a bug that looks like a UI mistake rather than a bad number, which is why the boundary
 * values are enumerated here rather than sampled.
 */
import { describe, expect, it } from "vitest";
import {
  PICK_INDEX_MAX,
  PICK_KIND_MARKER,
  PICK_KIND_REGION,
  decodePickId,
  decodePickPixel,
  encodePickId,
  pickIdToRgb,
  rgbToPickId,
  samePickTarget,
} from "../../src/renderer/scene/pickId";

describe("encodePickId", () => {
  it("packs the kind above the index, exactly as the shader does", () => {
    // Hand-computed: marker 305 -> (1 << 20) | 305 = 1 048 881 = 0x100131 -> bytes 0x31 0x01 0x10.
    expect(encodePickId("marker", 305)).toBe(1_048_881);
    expect(pickIdToRgb(1_048_881)).toEqual([0x31, 0x01, 0x10]);
    expect(encodePickId("region", 1)).toBe(PICK_KIND_REGION * 2 ** 20 + 1);
  });

  it("never collides with the background id, not even for region label 0", () => {
    // Label 0 is "unknown" in every FreeSurfer annotation and is a real, pickable region. If the
    // kind lived anywhere but the high bits, region 0 would encode to 0 and read as empty space.
    expect(encodePickId("region", 0)).not.toBe(0);
    expect(decodePickId(encodePickId("region", 0))).toEqual({ kind: "region", index: 0 });
    expect(encodePickId("marker", 0)).toBe(PICK_KIND_MARKER * 2 ** 20);
  });

  it("throws rather than truncating an index that does not fit", () => {
    expect(() => encodePickId("marker", PICK_INDEX_MAX + 1)).toThrow(RangeError);
    expect(() => encodePickId("marker", -1)).toThrow(RangeError);
    expect(() => encodePickId("marker", 1.5)).toThrow(RangeError);
    expect(encodePickId("region", PICK_INDEX_MAX)).toBe(PICK_KIND_REGION * 2 ** 20 + PICK_INDEX_MAX);
  });
});

describe("the RGB round trip", () => {
  it("survives every byte value exactly through the shader's n/255 conversion", () => {
    // The claim the shader relies on: writing n/255 into an RGBA8 target and reading it back gives
    // n, for every n. If it did not, ids would drift by one and pick the neighbouring electrode.
    for (let n = 0; n < 256; n += 1) {
      expect(Math.round((n / 255) * 255)).toBe(n);
    }
  });

  it("round-trips ids across the whole 24-bit range", () => {
    for (const id of [0, 1, 255, 256, 65_535, 65_536, 1_048_575, 1_048_576, 2_097_151, 16_777_215]) {
      const [r, g, b] = pickIdToRgb(id);
      expect(rgbToPickId(r, g, b)).toBe(id);
    }
  });

  it("round-trips every encodable target", () => {
    for (const kind of ["marker", "region"] as const) {
      for (const index of [0, 1, 2, 63, 255, 4095, PICK_INDEX_MAX]) {
        const [r, g, b] = pickIdToRgb(encodePickId(kind, index));
        expect(decodePickId(rgbToPickId(r, g, b))).toEqual({ kind, index });
      }
    }
  });
});

describe("decodePickId", () => {
  it("reads the cleared framebuffer as nothing", () => {
    // gl.clearColor(0, 0, 0, 0) is what "the user clicked empty space" looks like; no sentinel.
    expect(decodePickId(0)).toBeNull();
    expect(decodePickPixel(new Uint8Array([0, 0, 0, 0]))).toBeNull();
  });

  it("ignores a kind this renderer does not draw", () => {
    // Forward compatibility with a kind 3 some later version writes: unknown means "nothing here",
    // never "marker 12".
    expect(decodePickId((3 << 20) | 12)).toBeNull();
  });

  it("decodes a real pixel", () => {
    expect(decodePickPixel(new Uint8Array([0x31, 0x01, 0x10, 0xff]))).toEqual({ kind: "marker", index: 305 });
  });
});

describe("samePickTarget", () => {
  it("compares by value so an unchanged hover is not a state change", () => {
    expect(samePickTarget({ kind: "marker", index: 3 }, { kind: "marker", index: 3 })).toBe(true);
    expect(samePickTarget({ kind: "marker", index: 3 }, { kind: "region", index: 3 })).toBe(false);
    expect(samePickTarget(null, null)).toBe(true);
    expect(samePickTarget(null, { kind: "marker", index: 0 })).toBe(false);
  });
});
