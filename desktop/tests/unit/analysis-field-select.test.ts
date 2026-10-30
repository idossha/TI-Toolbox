/**
 * The Analyzer's Field dropdown offers the fields the analyzer accepts, and says which ones the
 * simulation did not save (2026-10-22, p04; on-demand fields 2026-10-30).
 *
 * The dropdown is told a simulation's catalog `fields`: what it saved, read from its field mesh and
 * its NIfTIs. Those include `magnE` (the carriers' volumes, which the analyzer does not analyse) and,
 * before the catalog was fixed, truncated names like `peak`/`avg`/`max`; picking one was accepted by
 * the page and then failed at run time with "Unknown field". So the options never come from the
 * catalog: they are the registry, read here from `tit/constants.py`'s `FIELD_REGISTRY` -- the list
 * `select_field_file` checks -- not from the desktop's own mirror. An unsaved field is computed by
 * the analysis from the channel meshes (`tit/volume_fields.py`), so it is offered plainly, except
 * `hf_power_density`, whose conductivity is not kept.
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
/** The registry less `mTI_max`, the mTI spelling of `TI_max` (`select_field_file` maps it). */
const OFFERED = ACCEPTED.filter((name) => name !== "mTI_max");

/** The options the component hands its `Select` (no DOM needed: it is a plain function of props). */
function options(available: string[], { value = AUTO_FIELD, space = "voxel" as Space, carrierOnly = false } = {}): SelectOption[] {
  const element = AnalysisFieldSelect({ value, space, available, carrierOnly, onChange: () => {} }) as ReactElement<{ options: SelectOption[] }>;
  return element.props.options;
}

const option = (available: string[], name: string, space: Space = "voxel") => options(available, { space }).find((o) => o.value === name);

describe("AnalysisFieldSelect", () => {
  it("reads seven analyzer fields from the Python registry", () => {
    expect(ACCEPTED).toEqual(["TI_max", "mTI_max", "TI_normal", "TI_avg", "hf_peak", "hf_sar", "hf_power_density"]);
  });

  it("offers every accepted field in registry order, whatever the catalog sent", () => {
    for (const available of [["TI_max", "magnE", "peak"], ["magnE"], [], ["mTI_max", "max", "normE", "TI_normal"], ["TI_avg", "avg", "sar"]]) {
      expect(options(available).map((o) => o.value)).toEqual([AUTO_FIELD, ...OFFERED]);
    }
  });

  it("names a field the simulation saved plainly, mTI_max counting as TI_max", () => {
    // A default simulation's field mesh: TI_max, hf_peak, hf_sar.
    expect(option(["TI_max", "hf_peak", "hf_sar"], "hf_peak")).toEqual({ value: "hf_peak", label: "hf_peak", disabled: false });
    expect(option(["mTI_max", "hf_peak", "hf_sar"], "TI_max")).toEqual({ value: "TI_max", label: "TI_max", disabled: false });
  });

  it("lists a field the simulation did not save plainly: the analysis computes it", () => {
    expect(option(["TI_max", "hf_peak", "hf_sar"], "TI_avg")).toEqual({ value: "TI_avg", label: "TI_avg", disabled: false });
    // A simulation from before the new defaults: TI_max only, so its carrier fields are computed.
    expect(option(["TI_max", "magnE"], "hf_sar")).toEqual({ value: "hf_sar", label: "hf_sar", disabled: false });
  });

  it("disables an unsaved hf_power_density: its conductivity is not kept", () => {
    expect(option(["TI_max", "hf_peak", "hf_sar"], "hf_power_density")).toEqual({ value: "hf_power_density", label: "hf_power_density (not saved)", disabled: true });
    expect(option(["TI_max", "hf_power_density"], "hf_power_density")?.disabled).toBe(false);
  });

  it("makes no claim when the catalog names no analysable field", () => {
    for (const o of options(["magnE"], { space: "mesh" }).slice(1)) {
      expect(o.label).toBe(o.value);
      expect(o.disabled).toBe(false);
    }
  });

  it("still marks TI_normal mesh-only in voxel space", () => {
    expect(option(["TI_max", "TI_normal"], "TI_normal")).toEqual({ value: "TI_normal", label: "TI_normal (mesh only)", disabled: true });
    expect(option(["TI_max"], "TI_normal", "mesh")).toEqual({ value: "TI_normal", label: "TI_normal", disabled: false });
  });

  it("offers a carrier-only simulation its carrier fields only, Auto being hf_peak", () => {
    // ΔF = 0: no envelope, so TI_max, TI_avg and TI_normal can never be analysed; Auto, which
    // the analyzer resolves to hf_peak for such a run (default_field), says so and stays valid.
    const carriers = options(["hf_peak", "hf_sar"], { carrierOnly: true });
    expect(carriers.map((o) => o.value)).toEqual([AUTO_FIELD, "hf_peak", "hf_sar", "hf_power_density"]);
    expect(carriers[0]).toEqual({ value: AUTO_FIELD, label: "Auto (hf_peak)", disabled: false });
    expect(carriers.find((o) => o.value === "hf_power_density")?.disabled).toBe(true); // not saved
    // A row still on an envelope field shows it, disabled, until it is changed.
    const stale = options(["hf_peak", "hf_sar"], { carrierOnly: true, value: "TI_max" });
    expect(stale[0]).toEqual({ value: "TI_max", label: "TI_max (carrier-only run)", disabled: true });
    expect(options(["TI_max"])[0]).toEqual({ value: AUTO_FIELD, label: "Auto", disabled: false });
  });
});
