/**
 * The Optimizer's Run name follows the server's NAME_RE before Run (p19, entity-names-optimizer,
 * 2026-10-22).
 *
 * A Run name is one path component: the flex `output_folder`'s last part, or the Ex/mEx
 * `run_name` under `ex-search/`. `tit.paths.NAME_RE` refuses names outside it — and a flex folder
 * named "Thalamus (L)" (which `flexOutputFolder` let through, rejecting only separators) used to
 * make GET /api/catalog/flex-runs answer 500 for the whole subject (audit_flex #3).
 *
 * Expected verdicts come from the shared table `tests/fixtures/entity_names.json` (typed from the
 * NAME_RE documentation; `tests/test_entity_names.py` holds it to `tit.paths.is_valid_name`), never
 * from the code under test. A blank name is not in that table's sense a name: it means "the
 * runner's timestamp", and is allowed.
 * Reproduce: `cd desktop && npx vitest run tests/unit/optimizer-run-name.test.ts`.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { rowFormReason, runNameReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow } from "../../src/renderer/pages/optimizer/rows";

interface NameCase {
  name: string;
  is_valid_name: boolean;
  why: string;
}
const TABLE = JSON.parse(readFileSync(resolve(__dirname, "../../../tests/fixtures/entity_names.json"), "utf8")) as {
  valid_name_rule: string;
  cases: NameCase[];
};
/**
 * The table's names exactly as they reach the wire. The control's value is trimmed before it is
 * sent (`runName.trim()` in `jobsForRow` and the Ex/mEx builders), so a name with surrounding
 * whitespace (" x", "x\n") is sent as its trimmed self and is judged as that — below, separately.
 * The empty string is the "auto" case, not a name.
 */
const NON_BLANK = TABLE.cases.filter((c) => c.name !== "" && c.name === c.name.trim());

describe("runNameReason follows tit.paths.NAME_RE", () => {
  it("has both verdicts to check", () => {
    expect(NON_BLANK.filter((c) => c.is_valid_name).length).toBeGreaterThan(3);
    expect(NON_BLANK.filter((c) => !c.is_valid_name).length).toBeGreaterThan(3);
  });

  it.each(NON_BLANK)("$name ($why) -> valid=$is_valid_name", ({ name, is_valid_name }) => {
    const reason = runNameReason(name);
    if (is_valid_name) expect(reason).toBeNull();
    else expect(reason).toBe(`A run name may use ${TABLE.valid_name_rule}.`);
  });

  it("judges a padded name by what is sent, its trimmed self", () => {
    expect(runNameReason("  Thalamus_L ")).toBeNull();
    expect(runNameReason(" Thalamus (L) ")).not.toBeNull();
  });

  it("allows a blank name: the runner names the run by its timestamp", () => {
    expect(runNameReason("")).toBeNull();
    expect(runNameReason("   ")).toBeNull();
  });

  it("judges an absolute flex folder by its last component", () => {
    expect(runNameReason("/proj/derivatives/SimNIBS/sub-ernie/flex-search/Thalamus_L")).toBeNull();
    expect(runNameReason("/proj/derivatives/SimNIBS/sub-ernie/flex-search/Thalamus (L)")).not.toBeNull();
  });
});

describe("a row with such a name cannot run, whatever its method", () => {
  it("refuses 'Thalamus (L)' on a flex and an ex row with the server's sentence", () => {
    for (const method of ["flex", "ex"] as const) {
      const row = emptyOptimizerRow({ subjectId: "ernie", method, runName: "Thalamus (L)" });
      expect(rowFormReason(row)).toBe(`A run name may use ${TABLE.valid_name_rule}.`);
    }
  });

  it("does not let a valid name change the row's own verdict", () => {
    const named = emptyOptimizerRow({ subjectId: "ernie", method: "flex", runName: "run 2" });
    const blank = { ...named, runName: "" };
    expect(rowFormReason(named)).toBe(rowFormReason(blank));
  });
});
