import { describe, expect, it } from "vitest";
import { capDisplacements } from "../../src/renderer/pages/_shared/scene/displacements";

describe("Flex cap displacement annotations", () => {
  it("joins in pair order by name and reports independently known straight-line lengths", () => {
    const result = capDisplacements([{ x: 0, y: 0, z: 0 }, { x: 10, y: 0, z: 0 }], [["A", "B"]], [
      { id: "B", label: "B", world: [10, 0, 12], channel: 0 },
      { id: "A", label: "A", world: [3, 4, 0], channel: 0 },
    ]);
    expect(result.map((item) => item.label)).toEqual(["A: 5.0 mm", "B: 12.0 mm"]);
    expect(result[0]?.to).toEqual([3, 4, 0]);
    expect(result[1]?.from).toEqual([10, 0, 0]);
  });
  it("does not substitute a different electrode for an unavailable cap position", () => {
    expect(capDisplacements([{ x: 1, y: 2, z: 3 }], [["missing", "also-missing"]], [])).toEqual([]);
  });
  it("does not annotate invalid or unmatched original coordinates", () => {
    expect(capDisplacements([{ x: NaN, y: 0, z: 0 }], [["A", "B"]], [
      { id: "A", label: "A", world: [0, 0, 0], channel: 0 },
      { id: "B", label: "B", world: [0, 0, 0], channel: 0 },
    ])).toEqual([]);
  });
});
