// @vitest-environment jsdom
/**
 * `PlanSummary` (ra_12 #7): the one Plan-panel shape every run page adopts instead of inventing
 * its own vocabulary/layout. Covers the four states a page composes it in.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PlanSummary } from "../../src/renderer/ui/PlanSummary";

describe("PlanSummary", () => {
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
  });

  function render(el: React.ReactElement) {
    act(() => root.render(el));
  }

  it("idle: shows the idle message, no definition list", () => {
    render(<PlanSummary idleMessage="Pick a subject and ROI to see the plan." />);
    expect(container.textContent).toContain("Pick a subject and ROI to see the plan.");
    expect(container.querySelector(".definition-list")).toBeNull();
  });

  it("idle: falls back to a default sentence when no idleMessage is given", () => {
    render(<PlanSummary />);
    expect(container.textContent).toContain("Nothing to plan yet.");
  });

  it("loading: shows skeletons, not the definition list or the idle message", () => {
    render(<PlanSummary loading idleMessage="should not show" />);
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("should not show");
    expect(container.querySelector(".definition-list")).toBeNull();
  });

  it("error: shows the error callout instead of the definition list", () => {
    render(<PlanSummary error="The server could not resolve this plan." />);
    expect(container.textContent).toContain("Could not load the plan.");
    expect(container.textContent).toContain("The server could not resolve this plan.");
    expect(container.querySelector(".definition-list")).toBeNull();
  });

  it("resolved: renders Jobs, CPUs, Memory, Outputs, Waits as a DefinitionList, in that order", () => {
    render(
      <PlanSummary
        jobs={2}
        cpus={8}
        memoryGb={16}
        outputs={[{ label: "sub-ernie -> TI_max.msh", willOverwrite: true }, { label: "sub-101 -> TI_max.msh" }]}
        waits={["sub-ernie: waiting on flex-search"]}
      />,
    );
    const terms = Array.from(container.querySelectorAll(".definition-list dt")).map((el) => el.textContent);
    expect(terms).toEqual(["Jobs", "CPUs", "Memory", "Outputs", "Waits"]);
    expect(container.textContent).toContain("16 GB");
    expect(container.textContent).toContain("sub-ernie -> TI_max.msh (overwrites)");
    expect(container.textContent).toContain("sub-101 -> TI_max.msh");
    expect(container.textContent).not.toContain("sub-101 -> TI_max.msh (overwrites)");
    expect(container.textContent).toContain("sub-ernie: waiting on flex-search");
  });

  it("resolved with no outputs/waits: shows the placeholders, not empty cells", () => {
    render(<PlanSummary jobs={0} cpus={0} memoryGb={0} />);
    expect(container.querySelector(".definition-list")!.textContent).toContain("none"); // Waits
    const dds = Array.from(container.querySelectorAll(".definition-list dd")).map((el) => el.textContent);
    expect(dds[3]).toBe("—"); // Outputs, empty
  });

  it("warnings slot: only rendered when there is at least one warning", () => {
    render(<PlanSummary jobs={1} cpus={1} memoryGb={1} />);
    expect(container.querySelector(".callout-warning")).toBeNull();
    render(<PlanSummary jobs={1} cpus={1} memoryGb={1} warnings={["This will overwrite an existing simulation."]} />);
    expect(container.querySelector(".callout-warning")).not.toBeNull();
    expect(container.textContent).toContain("Before you run this");
    expect(container.textContent).toContain("This will overwrite an existing simulation.");
  });
});
