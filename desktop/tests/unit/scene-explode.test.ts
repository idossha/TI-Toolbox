/**
 * The MNI atlas "Explode" toggle (`scene/explode.ts`, `ScenePane`'s button), 2026-09-23.
 *
 * Pins: left/right regions move to opposite x sides, a region at the centre still moves, a region
 * keeps its shape (one offset per label), progress 0 is the exact original geometry, the skin
 * fades before the regions move, and the button exists on the MNI template only.
 *
 * Every expected value is from the synthetic geometry built here (symmetric about x = 0, so the
 * bounding-box centre is the origin by construction), not from the implementation. The last block
 * reads the REAL packaged MNI guide (`tit/scene/guide-mni`, the bytes `GET /api/guide/*?guide=mni`
 * serves) — the mock's Ernie stand-in drew a different part than the real guide does, which is how
 * a green e2e run once coexisted with a user who could not see the button.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { explodeStage, explodedPositions, regionOffsets } from "../../src/renderer/scene/explode";
import { parseTvsc1 } from "../../src/renderer/scene/tvsc";
import { explodeOffered, labelsAlignment } from "../../src/renderer/pages/_shared/scene/model";

/** Three tiny triangles: label 1 around x = -30, label 2 around x = +30, label 3 at the origin. */
const positions = new Float32Array([
  -31, 0, 0, -29, 1, 0, -30, -1, 1, // label 1 (left)
  29, 0, 0, 31, 1, 0, 30, -1, 1, // label 2 (right)
  -1, 0, 0, 1, 1, 0, 0, -1, 0, // label 3 (centre, centroid (0, 0, 0))
]);
const labels = new Uint16Array([1, 1, 1, 2, 2, 2, 3, 3, 3]);
const at = (array: Float32Array, v: number) => Array.from(array.subarray(v * 3, v * 3 + 3));

describe("regionOffsets", () => {
  const offsets = regionOffsets(positions, labels);

  it("moves the left region to -x and the right region to +x, by the same amount", () => {
    const left = at(offsets, 0);
    const right = at(offsets, 3);
    expect(left[0]).toBeLessThan(0);
    expect(right[0]).toBeGreaterThan(0);
    expect(left[0]).toBeCloseTo(-right[0]!, 5);
    // Further apart once exploded.
    const exploded = explodedPositions(positions, offsets, 1);
    expect(at(exploded, 3)[0]! - at(exploded, 0)[0]!).toBeGreaterThan(at(positions, 3)[0]! - at(positions, 0)[0]!);
  });

  it("still moves a region whose centroid is the centre", () => {
    expect(Math.hypot(...at(offsets, 6))).toBeGreaterThan(1);
  });

  it("translates each region rigidly: every vertex of a label gets the same offset", () => {
    for (const first of [0, 3, 6]) {
      expect(at(offsets, first + 1)).toEqual(at(offsets, first));
      expect(at(offsets, first + 2)).toEqual(at(offsets, first));
    }
  });
});

describe("explodedPositions / explodeStage", () => {
  it("progress 0 is the exact original geometry", () => {
    const stage = explodeStage(0);
    expect(stage).toEqual({ veil: 0, offset: 0 });
    const drawn = explodedPositions(positions, regionOffsets(positions, labels), stage.offset);
    expect(Array.from(drawn)).toEqual(Array.from(positions));
  });

  it("fades the skin fully before the regions start to move, and ends fully exploded", () => {
    const early = explodeStage(0.2);
    expect(early.veil).toBeGreaterThan(0);
    expect(early.offset).toBe(0);
    expect(explodeStage(0.35)).toEqual({ veil: 1, offset: 0 });
    expect(explodeStage(1)).toEqual({ veil: 1, offset: 1 });
    // Monotone, so running the timeline backwards collapses the regions before the skin returns.
    let previous = 0;
    for (let p = 0; p <= 1.0001; p += 0.05) {
      const { offset } = explodeStage(p);
      expect(offset).toBeGreaterThanOrEqual(previous);
      previous = offset;
    }
  });
});

describe("explodeOffered", () => {
  it("is offered on the MNI template with a labelled atlas, and nowhere else", () => {
    expect(explodeOffered("mni", null, true)).toBe(true);
    expect(explodeOffered("mni", null, false)).toBe(false);
    expect(explodeOffered("default", null, true)).toBe(false);
    // A subject's own head, even if the page asked for MNI elsewhere.
    expect(explodeOffered("default", "ernie", true)).toBe(false);
  });
});

describe("the real MNI guide (tit/scene/guide-mni)", () => {
  const root = join(__dirname, "../../../tit/scene/guide-mni");
  const tvsc = (rel: string) => {
    const bytes = readFileSync(join(root, rel));
    return parseTvsc1(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  };
  const manifest = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8")) as {
    parts: Array<{ id: string; files: { tvsc: string } }>;
    atlases: Array<{ id: string; aligned_to: string; files: { tvsc: string }; legend_file: string }>;
  };

  it("has atlases to check", () => {
    expect(manifest.atlases.length).toBeGreaterThan(0);
  });

  it("offers Explode on every packaged MNI atlas: its labels align with the part it is drawn on", () => {
    for (const atlas of manifest.atlases) {
      const part = manifest.parts.find((entry) => entry.id === atlas.aligned_to);
      expect(part, atlas.id).toBeDefined();
      const alignment = labelsAlignment(tvsc(part!.files.tvsc), tvsc(atlas.files.tvsc));
      expect(alignment, atlas.id).toEqual({ aligned: true, reason: null });
      expect(explodeOffered("mni", null, alignment.aligned)).toBe(true);
    }
  });

  it("CIT168 lateralized: all 32 regions are on the surface, and each hemisphere explodes to its own side", () => {
    const atlas = manifest.atlases.find((entry) => entry.id.startsWith("CIT168_labeling_lateralized"))!;
    const legend = JSON.parse(readFileSync(join(root, atlas.legend_file), "utf8")).legend as Array<{ label: number; name: string }>;
    const payload = tvsc(atlas.files.tvsc);
    const present = new Set(payload.labels!);
    expect(legend).toHaveLength(32);
    for (const row of legend) expect(present.has(row.label), row.name).toBe(true);
    const offsets = regionOffsets(payload.positions, payload.labels!);
    const xOf = new Map<number, number>();
    payload.labels!.forEach((label, v) => xOf.set(label, offsets[v * 3]!));
    const left = legend.filter((row) => row.name.startsWith("Left-"));
    const right = legend.filter((row) => row.name.startsWith("Right-"));
    expect(left).toHaveLength(16);
    expect(right).toHaveLength(16);
    for (const row of left) expect(xOf.get(row.label), row.name).toBeLessThan(0);
    for (const row of right) expect(xOf.get(row.label), row.name).toBeGreaterThan(0);
  });
});
