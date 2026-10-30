// @vitest-environment jsdom
/**
 * Settings ▸ Simulator: the user's own defaults for new simulation jobs (2026-10-30).
 *
 * Pins: a new job runs with the user's defaults; a job's own Job settings change that job only and
 * never reach the defaults or another row; the dialog's Reset to defaults returns to the user's
 * defaults, not the factory ones; Restore factory defaults clears them; and only the changes from
 * the factory are stored, so they survive a restart.
 * Where the numbers come from: the factory side is `defaultJobSettings()` (pinned on its own in
 * app-defaults.test.ts); every user-side value is one this test sets, so each expectation is the
 * value set here (groundTruth: authored).
 * Reproduce: cd desktop && npx vitest run tests/unit/simulator-user-defaults.test.tsx
 * Deliberately elsewhere: the MNI/NIfTI and carrier-only rules of the shared form
 * (simulator-nifti-options.test.ts, simulator-defaults.test.ts).
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { JobSettingsDialog } from "../../src/renderer/pages/simulator/JobSettingsDialog";
import { defaultJobSettings, emptyRow, settingsFor, type JobSettings, type SelectedRow } from "../../src/renderer/pages/simulator/types";
import { resolveSimulatorDefaults, useSimulatorDefaults } from "../../src/renderer/pages/simulator/userDefaults";
import { SimulatorDefaultsCard } from "../../src/renderer/pages/settings/SimulatorDefaultsCard";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const KEY = "tit-simulator-defaults";
const factory = defaultJobSettings();
/** The user's defaults in this test: unlike the factory in every group the dialog shows. */
const mine: JobSettings = {
  ...factory,
  electrodeShape: "rect",
  dimensions: [10, 5],
  gelThickness: 3,
  conductivity: "vn",
  outputFields: ["TI_max", "TI_avg"],
  writeNiftis: true,
  mapToMni: true,
  mapToFsavg: true,
};
const job = (over: Partial<SelectedRow> = {}): SelectedRow => ({
  ...emptyRow("ernie", "montage", "GSN-HydroCel-185.csv"),
  name: "F3_F4",
  kind: "uni_polar",
  pairs: [["E1", "E2"], ["E3", "E4"]],
  ...over,
});
const userDefaults = () => resolveSimulatorDefaults(useSimulatorDefaults.getState().saved);

let root: Root | undefined;
function render(element: ReturnType<typeof createElement>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // The schema is loaded by tests/unit/setup-app-defaults.ts; tell withAppDefaults so.
  client.setQueryData(["schema"], true);
  root = createRoot(container);
  act(() => root!.render(createElement(QueryClientProvider, { client }, element)));
}
const byLabel = (label: string) => document.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`)!;
const byText = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text)!;
const click = (el: HTMLElement) => act(() => el.click());

beforeEach(() => {
  const store = new Map<string, string>(); // this jsdom's localStorage has no clear()
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) },
  });
  useSimulatorDefaults.getState().setSimulatorDefaults(null);
});
afterEach(() => {
  if (root) act(() => root!.unmount());
  root = undefined;
  document.body.innerHTML = "";
});

describe("the user's Simulator defaults", () => {
  it("a new job runs with them", () => {
    useSimulatorDefaults.getState().setSimulatorDefaults(mine);
    const fresh = job();
    expect(fresh.settings).toBeUndefined();
    expect(buildSimulationConfig(fresh, userDefaults() as GlobalParams)).toMatchObject({
      electrode_shape: "rect",
      electrode_dimensions: [10, 5],
      gel_thickness: 3,
      conductivity: "vn",
      output_fields: ["TI_max", "TI_avg"],
      map_to_vol: true,
      map_to_mni: true,
      map_to_fsavg: true,
    });
  });

  it("stores only the changes from the factory defaults, and reads them back after a restart", async () => {
    useSimulatorDefaults.getState().setSimulatorDefaults({ ...factory, gelThickness: 3 });
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({ gelThickness: 3 });
    vi.resetModules();
    const reloaded = await import("../../src/renderer/pages/simulator/userDefaults");
    // A fresh module graph is a restart: its store reads what the last one wrote.
    expect(resolveSimulatorDefaults(reloaded.useSimulatorDefaults.getState().saved)).toEqual({ ...factory, gelThickness: 3 });
  });

  it("ignores a stored value of the wrong type or for no field", () => {
    expect(resolveSimulatorDefaults({ gelThickness: "3", bogus: 1, dimensions: [6, 6] } as never)).toEqual({ ...factory, dimensions: [6, 6] });
  });

  it("a job's own settings change that job only, never the defaults or another row", () => {
    useSimulatorDefaults.getState().setSimulatorDefaults(mine);
    const edited = job();
    const other = job();
    const onSave = vi.fn();
    render(createElement(JobSettingsDialog, { row: edited, defaults: userDefaults(), onClose: () => {}, onSave }));
    click([...document.querySelectorAll("label")].find((l) => l.textContent === "Map fields to fsaverage")!.querySelector("button")!);
    click(byText("Done"));
    const own = onSave.mock.calls[0]![0] as JobSettings;
    expect(own).toEqual({ ...mine, mapToFsavg: false });
    // The row keeps its own settings; the defaults and every other row are as they were.
    expect(userDefaults()).toEqual(mine);
    expect(settingsFor(other, userDefaults())).toEqual(mine);
    expect(buildSimulationConfig({ ...edited, settings: own }, userDefaults() as GlobalParams).map_to_fsavg).toBe(false);
    expect(buildSimulationConfig(other, userDefaults() as GlobalParams).map_to_fsavg).toBe(true);
  });

  it("the dialog's Reset to defaults returns to the user's defaults, not the factory ones", () => {
    useSimulatorDefaults.getState().setSimulatorDefaults(mine);
    const custom = job({ settings: { ...factory, gelThickness: 9 } });
    const onSave = vi.fn();
    render(createElement(JobSettingsDialog, { row: custom, defaults: userDefaults(), onClose: () => {}, onSave }));
    expect(byLabel("Write NIfTI volumes").getAttribute("aria-checked")).toBe("false");
    click(byText("Reset to defaults"));
    expect(byLabel("Write NIfTI volumes").getAttribute("aria-checked")).toBe("true");
    expect(byLabel("Also in MNI space").getAttribute("aria-checked")).toBe("true");
    click(byText("Done"));
    // Settings equal to the defaults are not the job's own: it follows the user's defaults again.
    expect(onSave).toHaveBeenCalledWith(undefined);
  });

  it("Settings ▸ Simulator saves a change at once and restores the factory defaults", () => {
    render(createElement(SimulatorDefaultsCard));
    expect(byText("Restore factory defaults").disabled).toBe(true);
    // The same rule as the job dialog: MNI NIfTIs are NIfTIs.
    click(byLabel("Also in MNI space"));
    expect(userDefaults()).toEqual({ ...factory, writeNiftis: true, mapToMni: true });
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({ writeNiftis: true, mapToMni: true });
    click(byText("Restore factory defaults"));
    expect(userDefaults()).toEqual(factory);
    expect(window.localStorage.getItem(KEY)).toBeNull();
    expect(byLabel("Write NIfTI volumes").getAttribute("aria-checked")).toBe("false");
    expect(byText("Restore factory defaults").disabled).toBe(true);
  });

  it("Settings ▸ Simulator never saves a form with no output field", () => {
    useSimulatorDefaults.getState().setSimulatorDefaults({ ...factory, outputFields: ["TI_max"] });
    render(createElement(SimulatorDefaultsCard));
    const tiMax = [...document.querySelectorAll("label")].find((l) => l.textContent === "TI_max")!.querySelector("button")!;
    click(tiMax);
    expect(document.body.textContent).toContain("Select at least one output field.");
    expect(userDefaults().outputFields).toEqual(["TI_max"]);
  });
});
