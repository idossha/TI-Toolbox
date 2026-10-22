/**
 * The Visual Exporter's "Queued: … → <hint>" names a path inside the folder the server plans for
 * that mode (package p38, 2026-10-22).
 *
 * The expected folders are `tests/fixtures/plan_output_dirs.json`, written by
 * `dev/gen_plan_output_dirs.py` from the real `POST /api/plan/blender` (kept current by
 * `tests/test_plan_output_dirs_fixture.py`); nothing here is retyped. The hint is relative to
 * `derivatives/ti-toolbox/` and the regions hint spells both formats as `{stl|ply}`, one job each,
 * so each alternative is expanded for the format the case planned.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/visual-exporter-output-hint.test.ts
 */
import { describe, expect, it } from "vitest";
import table from "../../../tests/fixtures/plan_output_dirs.json";
import { outputHint } from "../../src/renderer/pages/panels/visual-exporter/config";

type Mode = Parameters<typeof outputHint>[0];

const MODE_FOR_TYPE: Record<string, Mode> = {
  RegionConfig: "regions",
  VectorConfig: "vectors",
  MontageConfig: "montage",
  SubcorticalConfig: "subcortical",
};
const FORMATS = ["stl", "ply"];

/** The hint with every `{a|b}` resolved to the alternative of `format` (STL first, as the hint spells it). */
function expand(hint: string, format: string): string {
  return hint.replace(/\{([^}|]+)\|([^}]+)\}/g, (_, a: string, b: string) => (FORMATS.indexOf(format) === 0 ? a : b));
}

// The panel never sends an output_dir, so only the cases without one describe what it queues.
const cases = (table as unknown as { cases: { id: string; kind: string; config: Record<string, string>; jobs: { output_dir: string }[] }[] }).cases.filter(
  (c) => c.kind === "blender" && c.config._type && !("output_dir" in c.config),
);

describe("outputHint lies under the folder the plan reports", () => {
  it("has every export mode to check", () => {
    expect(new Set(cases.map((c) => MODE_FOR_TYPE[c.config._type!]))).toEqual(new Set(Object.values(MODE_FOR_TYPE)));
  });

  for (const c of cases) {
    it(c.id, () => {
      const mode = MODE_FOR_TYPE[c.config._type!]!;
      const hint = `derivatives/ti-toolbox/${expand(outputHint(mode, c.config.subject_id!, c.config.simulation_name ?? ""), c.config.format ?? "stl")}`;
      const planned = c.jobs[0]!.output_dir;
      expect(hint === planned || hint.startsWith(`${planned}/`), `${hint} is inside ${planned}`).toBe(true);
    });
  }
});
