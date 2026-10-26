/**
 * The Analyzer's Field dropdown offers only fields the analyzer accepts (2026-10-22, p04).
 *
 * The dropdown lists a simulation's catalog `fields`. Those include `magnE` (the carriers'
 * volumes, which the analyzer does not analyse) and, before the catalog was fixed, truncated
 * names like `peak`/`avg`/`max`; picking one was accepted by the page and then failed at run
 * time with "Unknown field". The accepted set is read here from `tit/constants.py`'s
 * `FIELD_REGISTRY` -- the list `select_field_file` checks -- not from the desktop's own mirror.
 *
 * Run: cd desktop && npx vitest run tests/unit/analysis-field-select.test.ts
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { AnalysisFieldSelect } from "../../src/renderer/pages/analyzer/AnalysisFieldSelect";
import { AUTO_FIELD, type Space } from "../../src/renderer/pages/analyzer/buildConfig";
import type { SelectOption } from "../../src/renderer/ui/Select";

/** `FIELD_REGISTRY`'s names, read from the Python source: `name=FIELD_X` against `FIELD_X = "..."`. */
function pythonRegistryNames(): string[] {
  const source = readFileSync(join(__dirname, "..", "..", "..", "tit", "constants.py"), "utf8");
  const constants = new Map(
    [...source.matchAll(/^(FIELD_[A-Z_]+) = "([A-Za-z_]+)"/gm)].map((m) => [m[1], m[2]] as const),
  );
  const registry = source.slice(source.indexOf("FIELD_REGISTRY"), source.indexOf("def get_field_names"));
  return [...registry.matchAll(/name=(FIELD_[A-Z_]+)/g)].map((m) => constants.get(m[1]) as string);
}

const ACCEPTED = pythonRegistryNames();

/** The options the component hands its `Select` (no DOM needed: it is a plain function of props). */
function options(available: string[], { value = AUTO_FIELD, space = "voxel" as Space } = {}): SelectOption[] {
  const element = AnalysisFieldSelect({ value, space, available, onChange: () => {} }) as ReactElement<{ options: SelectOption[] }>;
  return element.props.options;
}

describe("AnalysisFieldSelect", () => {
  it("reads seven analyzer fields from the Python registry", () => {
    expect(ACCEPTED).toEqual(["TI_max", "mTI_max", "TI_normal", "TI_avg", "hf_peak", "hf_sar", "hf_power_density"]);
  });

  it("drops catalog fields the analyzer would reject", () => {
    expect(options(["TI_max", "magnE", "peak"]).map((o) => o.value)).toEqual([AUTO_FIELD, "TI_max"]);
    // What the catalog used to send for sub-101/L_Insula and for any mTI run.
    expect(options(["TI_max", "avg", "magnE", "peak", "sar"]).map((o) => o.value)).toEqual([AUTO_FIELD, "TI_max"]);
    expect(options(["magnE", "max", "peak"]).map((o) => o.value)).not.toContain("max");
  });

  it("keeps every field a TI or mTI simulation really wrote, in catalog order", () => {
    expect(options(["TI_avg", "TI_max", "hf_peak", "hf_sar", "magnE"]).map((o) => o.value)).toEqual([
      AUTO_FIELD, "TI_avg", "TI_max", "hf_peak", "hf_sar",
    ]);
    expect(options(["TI_avg", "hf_peak", "hf_sar", "mTI_max", "magnE"]).map((o) => o.value)).toEqual([
      AUTO_FIELD, "TI_avg", "hf_peak", "hf_sar", "mTI_max",
    ]);
  });

  it("offers only accepted names or Auto, whatever the catalog sent", () => {
    for (const available of [["TI_max", "magnE", "peak"], ["magnE"], [], ["mTI_max", "max", "normE", "TI_normal"]]) {
      for (const option of options(available)) {
        expect(option.value === AUTO_FIELD || ACCEPTED.includes(option.value)).toBe(true);
      }
    }
  });

  it("falls back to the registry when the catalog names no analysable field", () => {
    const fallback = options(["magnE"], { space: "mesh" }).map((o) => o.value);
    expect(fallback.slice(1).sort()).toEqual(["TI_avg", "TI_max", "TI_normal", "hf_peak", "hf_power_density", "hf_sar"]);
    expect(fallback.slice(1).every((name) => ACCEPTED.includes(name))).toBe(true);
  });

  it("still marks TI_normal mesh-only in voxel space", () => {
    const normal = options(["TI_max", "TI_normal"]).find((o) => o.value === "TI_normal");
    expect(normal).toEqual({ value: "TI_normal", label: "TI_normal (mesh only)", disabled: true });
    const meshNormal = options(["TI_max", "TI_normal"], { space: "mesh" }).find((o) => o.value === "TI_normal");
    expect(meshNormal?.disabled).toBe(false);
  });
});
