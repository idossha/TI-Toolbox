/**
 * The desktop's name rules answer exactly what `tests/fixtures/entity_names.json` says — the same
 * table `tests/test_entity_names.py` pins `tit.paths.is_valid_name` and `tit.catalog.is_safe_name`
 * to, so a name the montage editor, the free-hand editor or a run-name field lets through is one
 * the server takes. The verdicts were typed from the server rules' documentation, not computed.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ENTITY_NAME_RULE,
  SAFE_NAME_RULE,
  entityNameProblem,
  isSafeName,
  isValidEntityName,
  safeNameProblem,
} from "../../src/renderer/pages/_shared/entityNames";

interface NameCase {
  name: string;
  is_valid_name: boolean;
  is_safe_name: boolean;
  why: string;
}

const FIXTURE = join(__dirname, "..", "..", "..", "tests", "fixtures", "entity_names.json");
const DATA = JSON.parse(readFileSync(FIXTURE, "utf8")) as { valid_name_rule: string; cases: NameCase[] };
const CASES = DATA.cases;

describe("entity names follow the server's rules (tests/fixtures/entity_names.json)", () => {
  it("the table has both verdicts for both rules", () => {
    expect(new Set(CASES.map((c) => c.is_valid_name))).toEqual(new Set([true, false]));
    expect(new Set(CASES.map((c) => c.is_safe_name))).toEqual(new Set([true, false]));
  });

  it.each(CASES.map((c) => [c.why, c] as const))("isValidEntityName: %s", (_why, c) => {
    expect(isValidEntityName(c.name)).toBe(c.is_valid_name);
  });

  it.each(CASES.map((c) => [c.why, c] as const))("isSafeName: %s", (_why, c) => {
    expect(isSafeName(c.name)).toBe(c.is_safe_name);
  });

  it("a refused name is refused with the rule's sentence, and an accepted one with nothing", () => {
    for (const c of CASES) {
      expect(safeNameProblem(c.name, "montage")).toBe(c.is_safe_name ? null : `A montage name may use ${SAFE_NAME_RULE}.`);
      expect(entityNameProblem(c.name, "run")).toBe(c.is_valid_name ? null : `A run name may use ${ENTITY_NAME_RULE}.`);
    }
    // The server's own words: tests/test_entity_names.py asserts validate_name raises this sentence.
    expect(ENTITY_NAME_RULE).toBe(DATA.valid_name_rule);
  });
});
