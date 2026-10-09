/**
 * The Simulator's flex-row default current: the run's own (optimised split, else current_mA per
 * channel, else 1 mA), the same order as the server's `flex_currents`. The table is
 * `tests/fixtures/flex_currents.json`, which tests/test_flex_simulation_resolver.py also reads.
 * Reproduce: cd desktop && npx vitest run tests/unit/flex-currents.test.ts
 */
import { expect, it } from "vitest";
import table from "../../../tests/fixtures/flex_currents.json";
import { flexCurrents } from "../../src/renderer/pages/simulator/FlexTab";
import type { FlexRun } from "../../src/renderer/pages/simulator/api";

it.each(table)("$case", ({ manifest, pairs, currents }) => {
  const run = { name: "r", manifest } as unknown as FlexRun;
  expect(flexCurrents(run, pairs).split(",").map(Number)).toEqual(currents);
});

it("a run the catalog does not know falls back to 1 mA per channel", () => {
  expect(flexCurrents(undefined, 2)).toBe("1.0,1.0");
});
