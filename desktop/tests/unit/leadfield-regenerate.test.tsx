// @vitest-environment jsdom
/**
 * Regenerating a net's existing leadfield with another electrode (G1-5, 2026-11-01).
 *
 * A net has one leadfield (`<sid>_leadfield_<net>.hdf5`), so "a different electrode needs its own
 * leadfield" means replacing it. Pins: the row editor's leadfield strip offers "Regenerate…" for a
 * net that has one and hands the step the electrode the leadfield records; the step then opens as
 * "Regenerate leadfield", seeded with that electrode (rubber included), and confirms it unchanged.
 * A net with no leadfield still opens "Generate leadfield" at the toolbox defaults (8 mm, 1 mm gel,
 * `x-app-defaults.leadfield`). The 409 → "Replace and rerun" → `overwrite: true` loop on the page is
 * the mock e2e's (`tests/e2e/optimizer.spec.ts`, "an existing leadfield can be regenerated…").
 * The electrode below is authored: any value distinct from the defaults would do.
 * Reproduce: cd desktop && npx vitest run tests/unit/leadfield-regenerate.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Leadfield, LeadfieldElectrode } from "../../src/renderer/pages/optimizer/api";

vi.mock("../../src/renderer/pages/optimizer/api", async (original) => ({
  ...(await original<object>()),
  planLeadfieldEta: vi.fn(async () => ({ minutes: null, system: null })),
}));

const { LeadfieldStrip } = await import("../../src/renderer/pages/optimizer/ExSections");
const { LeadfieldStepDialog } = await import("../../src/renderer/pages/optimizer/LeadfieldStepDialog");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const NET = "GSN-HydroCel-185";
const RECORDED: LeadfieldElectrode = { electrode_shape: "rect", electrode_dimensions: [12, 6], gel_thickness: 2.5, rubber_thickness: 3 };
const existing: Leadfield = { net: NET, path: `/p/leadfields/ernie_leadfield_${NET}.hdf5`, exists: true, size_bytes: 1024, electrode: RECORDED };

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const render = (node: React.ReactNode) =>
  act(() => root.render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>));
const button = (text: string) => [...document.body.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
const input = (label: string) => document.body.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
const heading = () => document.body.querySelector('[role="dialog"] h2')?.textContent;

describe("regenerating an existing leadfield", () => {
  it("the strip offers Regenerate… for a net that has a leadfield and passes its recorded electrode", () => {
    const onGenerate = vi.fn();
    render(
      <LeadfieldStrip leadfields={[existing]} loading={false} nets={[]} selectedNet={NET} subjectId="ernie" onSelectNet={() => {}} onGenerate={onGenerate} generating={false} />,
    );
    const regenerate = button("Regenerate…");
    expect(regenerate, "a Regenerate… action beside the existing leadfield").toBeTruthy();
    act(() => regenerate!.click());
    expect(onGenerate).toHaveBeenCalledWith(NET, RECORDED);
  });

  it("the step opens as Regenerate leadfield, seeded with that electrode, and confirms it", () => {
    const onConfirm = vi.fn();
    const request = { subject: "ernie", net: NET, replaces: RECORDED };
    render(<LeadfieldStepDialog request={request} onCancel={() => {}} onConfirm={onConfirm} />);
    expect(heading()).toBe("Regenerate leadfield");
    expect(document.body.textContent).toContain("regenerating replaces the current one");
    expect(input("Electrode width")?.value).toBe("12");
    expect(input("Electrode height")?.value).toBe("6");
    expect(input("Gel thickness")?.value).toBe("2.5");
    act(() => button("Regenerate")!.click());
    expect(onConfirm).toHaveBeenCalledWith(request, RECORDED);
  });

  it("a net with no leadfield still opens Generate leadfield at the toolbox defaults", () => {
    render(<LeadfieldStepDialog request={{ subject: "101", net: NET }} onCancel={() => {}} onConfirm={() => {}} />);
    expect(heading()).toBe("Generate leadfield");
    expect(input("Electrode width")?.value).toBe("8");
    expect(input("Gel thickness")?.value).toBe("1");
    expect(button("Generate")).toBeTruthy();
  });
});
