/**
 * The Pre-processing plan matrix's stage columns (`plannedStageIds`) equal the server planner's
 * stage tags for all 256 combinations of the eight step flags.
 *
 * The table is `tests/fixtures/pre_stages.json`, written by `dev/gen_pre_stages.py` from
 * `tit.jobs.plans.plan_preprocessing` (the source of truth); `tests/test_preprocess_stage_parity.py`
 * fails when it is stale. A column the planner never makes would be a stray matrix column, since
 * `planModelFrom` appends stages it does not know.
 * Reproduce: cd desktop && npx vitest run tests/unit/preprocess-stage-parity.test.ts
 */
import { describe, expect, it } from "vitest";
import table from "../../../tests/fixtures/pre_stages.json";
import { defaultConfig, plannedStageIds } from "../../src/renderer/pages/preprocess/index";

describe("plannedStageIds follows plan_preprocessing", () => {
  it("has every flag combination to check", () => {
    expect(table).toHaveLength(256);
  });

  it.each(table.map((entry, i) => [i, entry] as const))("combination %i", (_i, { flags, stages }) => {
    expect(plannedStageIds({ ...defaultConfig(), ...flags })).toEqual(stages);
  });
});
