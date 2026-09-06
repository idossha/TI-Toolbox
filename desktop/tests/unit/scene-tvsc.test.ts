/**
 * `scene/tvsc.ts` against real fixture files (plan §2.3, house rule 9).
 *
 * Two independent sources of truth, neither of which is this parser:
 *
 *  1. **Lane SCA's fixtures** (`tests/fixtures/scene/{tri-surface,labels-only,labelled-surface}.tvsc`),
 *     written by `tests/scene/make_fixtures.py` on the Python side. Their expected contents are the
 *     authored formula from the plan — `x = i*1.5`, `y = 40 - i*7.25`, `z = -12 + i*i*3` — retyped
 *     here, and every field is also read out of the bytes with a plain `DataView` walk before the
 *     parser is allowed near them. This is the "one test in each language reads a fixture the other
 *     wrote" clause of §2.3.
 *  2. **This lane's ellipsoid fixtures** (`skin.tvsc`, `gm.tvsc`, written by
 *     `scripts/make-scene-fixtures.ts`), whose vertex count, triangle count, byte length, bounding
 *     box, one exact vertex and one label are all closed-form consequences of the grid parameters,
 *     computed here from those parameters rather than read back from anything the generator emitted.
 *
 * The encoder is never used to produce an expected value for the decoder.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  TVSC_HEADER_BYTES,
  TvscError,
  encodeTvsc1,
  parseTvsc1,
  tvscByteLength,
} from "../../src/renderer/scene/tvsc";
import { computeBounds } from "../../src/renderer/scene/normals";

const FIXTURES = join(__dirname, "..", "fixtures", "scene");

function load(name: string): ArrayBuffer {
  const file = readFileSync(join(FIXTURES, name));
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer;
}

// --- lane SCA's fixtures: the authored ground truth, retyped ------------------------------------

/** The plan's authored position formula, not read from any file the generator wrote. */
const authoredPosition = (i: number): [number, number, number] => [i * 1.5, 40.0 - i * 7.25, -12.0 + i * i * 3.0];
const AUTHORED_VERTEX_COUNT = 5;
const AUTHORED_TRIANGLES = [
  [0, 1, 2],
  [2, 3, 4],
  [0, 2, 4],
];
const AUTHORED_LABELS = [0, 7, 65535, 3, 1];

/** A second reader: the header fields straight out of the bytes, at the offsets the spec table
 *  gives, with no help from the module under test. */
function walkHeader(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  return {
    magic: String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3)),
    version: view.getUint32(4, true),
    vertexCount: view.getUint32(8, true),
    indexCount: view.getUint32(12, true),
    flags: view.getUint32(16, true),
    reserved: [20, 24, 28].map((offset) => view.getUint32(offset, true)),
  };
}

describe("parseTvsc1 on the cross-language fixtures", () => {
  const cases: Array<{ file: string; bytes: number; indexCount: number; flags: number; labels: boolean }> = [
    { file: "tri-surface.tvsc", bytes: 128, indexCount: 9, flags: 0, labels: false },
    { file: "labels-only.tvsc", bytes: 104, indexCount: 0, flags: 1, labels: true },
    { file: "labelled-surface.tvsc", bytes: 140, indexCount: 9, flags: 1, labels: true },
  ];

  for (const testCase of cases) {
    it(`${testCase.file}: header, positions, indices and labels match the authored spec`, () => {
      const buffer = load(testCase.file);
      expect(buffer.byteLength).toBe(testCase.bytes);

      // The independent reader first, so a parser that agrees with a wrong file still fails.
      const header = walkHeader(buffer);
      expect(header.magic).toBe("TVSC");
      expect(header.version).toBe(1);
      expect(header.vertexCount).toBe(AUTHORED_VERTEX_COUNT);
      expect(header.indexCount).toBe(testCase.indexCount);
      expect(header.flags).toBe(testCase.flags);
      expect(header.reserved).toEqual([0, 0, 0]);
      // The byte length the spec's own formula predicts, arrived at without the module's helper.
      const labelBytes = testCase.labels ? Math.ceil((2 * AUTHORED_VERTEX_COUNT) / 4) * 4 : 0;
      expect(32 + 12 * AUTHORED_VERTEX_COUNT + 4 * testCase.indexCount + labelBytes).toBe(testCase.bytes);

      const parsed = parseTvsc1(buffer);
      expect(parsed.version).toBe(1);
      expect(parsed.vertexCount).toBe(AUTHORED_VERTEX_COUNT);
      expect(parsed.indexCount).toBe(testCase.indexCount);
      expect(parsed.triangles).toBe(testCase.indexCount / 3);
      expect(parsed.byteLength).toBe(testCase.bytes);

      for (let i = 0; i < AUTHORED_VERTEX_COUNT; i += 1) {
        const expected = authoredPosition(i);
        // Every one of these is exactly representable in float32 (1.5, 7.25 and 3.0 are dyadic),
        // so this is an equality, not a tolerance.
        expect([parsed.positions[i * 3], parsed.positions[i * 3 + 1], parsed.positions[i * 3 + 2]]).toEqual(expected);
      }

      if (testCase.indexCount === 0) {
        expect(parsed.indices).toBeNull();
      } else {
        expect(Array.from(parsed.indices ?? [])).toEqual(AUTHORED_TRIANGLES.flat());
      }

      if (testCase.labels) {
        expect(Array.from(parsed.labels ?? [])).toEqual(AUTHORED_LABELS);
      } else {
        expect(parsed.labels).toBeNull();
      }
    });
  }

  it("reads the label block at the offset the INDEX block ends at, not at a fixed offset", () => {
    // labels-only and labelled-surface carry the same five labels but a different index block
    // between the positions and them. A reader that computes the label offset from the header
    // alone (rather than accumulating) reads 36 bytes early on one of the two.
    const labelsOnly = parseTvsc1(load("labels-only.tvsc"));
    const labelled = parseTvsc1(load("labelled-surface.tvsc"));
    expect(Array.from(labelsOnly.labels ?? [])).toEqual(AUTHORED_LABELS);
    expect(Array.from(labelled.labels ?? [])).toEqual(AUTHORED_LABELS);
  });
});

// --- this lane's ellipsoid fixtures: closed-form expectations -----------------------------------

/** Must match `FIXTURE_SKIN` / `FIXTURE_GM` in `src/renderer/dev/sceneFixtures.ts`; typed here so a
 *  change to the generator fails this test instead of silently moving the expectations. */
const SKIN = { rx: 78, ry: 98, rz: 88, u: 64, v: 32 };
const GM = { rx: 64, ry: 82, rz: 70, u: 64, v: 32, thetaBands: 4, phiBands: 8 };

describe("parseTvsc1 on the ellipsoid fixtures", () => {
  it("skin.tvsc has the vertex, triangle and byte counts the grid parameters imply", () => {
    const parsed = parseTvsc1(load("skin.tvsc"));
    expect(parsed.vertexCount).toBe((SKIN.u + 1) * (SKIN.v + 1)); // 2145
    expect(parsed.triangles).toBe(2 * SKIN.u * SKIN.v); // 4096
    expect(parsed.byteLength).toBe(32 + 12 * 2145 + 4 * 12288); // 74 924
    expect(parsed.labels).toBeNull();
  });

  it("skin.tvsc's bounding box is exactly the semi-axes", () => {
    const parsed = parseTvsc1(load("skin.tvsc"));
    // The grid samples theta = pi/2 (i = v/2, v even) and phi = 0, pi/2, pi, 3pi/2 (u a multiple of
    // 4), so every extremum is hit exactly and the radii are exactly representable in float32.
    expect(Array.from(computeBounds(parsed.positions))).toEqual([
      -SKIN.rx,
      -SKIN.ry,
      -SKIN.rz,
      SKIN.rx,
      SKIN.ry,
      SKIN.rz,
    ]);
  });

  it("skin.tvsc's equatorial vertex at phi = 0 is (rx, 0, 0)", () => {
    const parsed = parseTvsc1(load("skin.tvsc"));
    const index = (SKIN.v / 2) * (SKIN.u + 1); // i = 16, j = 0
    expect(parsed.positions[index * 3]).toBe(SKIN.rx);
    expect(Math.abs(parsed.positions[index * 3 + 1] as number)).toBeLessThan(1e-4);
    expect(Math.abs(parsed.positions[index * 3 + 2] as number)).toBeLessThan(1e-4);
  });

  it("gm.tvsc carries one label per vertex, banded as the generator documents", () => {
    const parsed = parseTvsc1(load("gm.tvsc"));
    const cols = GM.u + 1;
    const rows = GM.v + 1;
    expect(parsed.labels?.length).toBe(cols * rows);
    expect(parsed.byteLength).toBe(32 + 12 * 2145 + 4 * 12288 + Math.ceil((2 * 2145) / 4) * 4); // 79 216
    // label = 1 + band(theta) * phiBands + band(phi), recomputed here from the band counts.
    const expectedLabel = (i: number, j: number) =>
      1 +
      Math.min(GM.thetaBands - 1, Math.floor((i * GM.thetaBands) / rows)) * GM.phiBands +
      Math.min(GM.phiBands - 1, Math.floor((j * GM.phiBands) / cols));
    for (const [i, j] of [
      [0, 0],
      [8, 12],
      [16, 32],
      [32, 64],
    ]) {
      expect(parsed.labels?.[(i as number) * cols + (j as number)]).toBe(expectedLabel(i as number, j as number));
    }
    const distinct = new Set(parsed.labels ?? []);
    expect(distinct.size).toBe(GM.thetaBands * GM.phiBands); // 32
  });
});

// --- failure modes -----------------------------------------------------------------------------

describe("parseTvsc1 rejects", () => {
  const good = load("tri-surface.tvsc");

  it("a buffer shorter than the header", () => {
    expect(() => parseTvsc1(new ArrayBuffer(16))).toThrow(TvscError);
  });

  it("bad magic", () => {
    const bytes = new Uint8Array(good.slice(0));
    bytes[0] = 0x54 + 1;
    expect(() => parseTvsc1(bytes.buffer)).toThrow(/bad magic/);
  });

  it("an unsupported version", () => {
    const bytes = new Uint8Array(good.slice(0));
    new DataView(bytes.buffer).setUint32(4, 2, true);
    expect(() => parseTvsc1(bytes.buffer)).toThrow(/version 2/);
  });

  it("an index count that is not a multiple of 3", () => {
    const bytes = new Uint8Array(good.slice(0));
    new DataView(bytes.buffer).setUint32(12, 8, true);
    expect(() => parseTvsc1(bytes.buffer)).toThrow(/multiple of 3/);
  });

  it("a payload longer than the buffer it arrived in", () => {
    const bytes = new Uint8Array(good.slice(0));
    new DataView(bytes.buffer).setUint32(8, 500, true);
    expect(() => parseTvsc1(bytes.buffer)).toThrow(/buffer has/);
  });

  it("an index pointing past the last vertex", () => {
    // Undefined behaviour in drawElements, not a visual glitch: worth a thrown error rather than a
    // black pane or a lost context.
    const bytes = new Uint8Array(good.slice(0));
    const view = new DataView(bytes.buffer);
    const indexOffset = TVSC_HEADER_BYTES + 12 * 5;
    view.setUint32(indexOffset, 5, true);
    expect(() => parseTvsc1(bytes.buffer)).toThrow(/points past the last of 5 vertices/);
  });

  it("but skips the index scan when asked to", () => {
    const bytes = new Uint8Array(good.slice(0));
    new DataView(bytes.buffer).setUint32(TVSC_HEADER_BYTES + 60, 5, true);
    expect(() => parseTvsc1(bytes.buffer, 0, { validateIndices: false })).not.toThrow();
  });
});

describe("tvscByteLength", () => {
  it("pads the label block up to a 4-byte boundary", () => {
    // 5 vertices -> 10 label bytes -> 12 with padding. The odd vertex count is exactly why
    // labels-only.tvsc is 104 rather than 102 bytes.
    expect(tvscByteLength(5, 0, true)).toBe(32 + 60 + 12);
    expect(tvscByteLength(5, 0, false)).toBe(32 + 60);
    expect(tvscByteLength(4, 6, true)).toBe(32 + 48 + 24 + 8);
  });
});

describe("encodeTvsc1", () => {
  it("produces bytes the cross-language fixture's own header walk accepts", () => {
    // The encoder exists for the fixture generator and the gallery; this checks it writes the
    // header the SPEC describes (offsets and values retyped above), not that it agrees with the
    // parser.
    const buffer = encodeTvsc1({
      positions: [0, 1, 2, 3, 4, 5, 6, 7, 8],
      indices: [0, 1, 2],
      labels: [4, 5, 6],
    });
    const header = walkHeader(buffer);
    expect(header).toEqual({ magic: "TVSC", version: 1, vertexCount: 3, indexCount: 3, flags: 1, reserved: [0, 0, 0] });
    expect(buffer.byteLength).toBe(32 + 36 + 12 + 8);
    const view = new DataView(buffer);
    expect(view.getFloat32(32, true)).toBe(0);
    expect(view.getFloat32(32 + 8 * 4, true)).toBe(8);
    expect(view.getUint32(32 + 36 + 4, true)).toBe(1);
    expect(view.getUint16(32 + 36 + 12 + 2, true)).toBe(5);
  });

  it("refuses a label array that does not match the vertex count", () => {
    expect(() => encodeTvsc1({ positions: [0, 0, 0], labels: [1, 2] })).toThrow(TvscError);
  });
});
