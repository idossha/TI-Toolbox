/**
 * `scene/tvsl.ts` against bytes the Python writer produced (`tests/scene/make_fixtures.py`).
 * The expected arrays are the literals handed to that writer, not anything this parser returned.
 * Run: cd desktop && npx vitest run tests/unit/tvsl.test.ts
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { TVSL_HEADER_BYTES, parseTvsl1 } from "../../src/renderer/scene/tvsl";
import { TvscError } from "../../src/renderer/scene/tvsc";

function fixture(): ArrayBuffer {
  const bytes = readFileSync(join(__dirname, "..", "fixtures", "scene", "two-lines.tvsl"));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

describe("parseTvsl1", () => {
  it("reads the Python writer's bytes", () => {
    const parsed = parseTvsl1(fixture());
    expect(parsed.streamlineCount).toBe(2);
    expect(parsed.pointCount).toBe(5);
    expect(Array.from(parsed.positions)).toEqual([1.5, -2, 3, 4, 5.5, -6, 7, 8, 9.5, -10, 11, 12, 13, -14, 15]);
    expect(Array.from(parsed.offsets)).toEqual([0, 3, 5]);
    expect(Array.from(parsed.index)).toEqual([99000, 7]);
    expect(Array.from(parsed.groups ?? [])).toEqual([1, 0]);
  });

  it("names what is wrong with a bad payload", () => {
    expect(() => parseTvsl1(new ArrayBuffer(4))).toThrow(TvscError);
    const bad = fixture().slice(0);
    new DataView(bad).setUint32(0, 0x12345678, true);
    expect(() => parseTvsl1(bad)).toThrow(/bad magic/);
    const version = fixture().slice(0);
    new DataView(version).setUint32(4, 2, true);
    expect(() => parseTvsl1(version)).toThrow(/unsupported version 2/);
    expect(() => parseTvsl1(fixture().slice(0, TVSL_HEADER_BYTES + 8))).toThrow(/claims/);
    const short = fixture().slice(0);
    // The closing offset must be the point count, or a draw reads past the buffer.
    new DataView(short).setUint32(TVSL_HEADER_BYTES + 12 * 5 + 8, 4, true);
    expect(() => parseTvsl1(short)).toThrow(/last offset 4/);
  });
});
