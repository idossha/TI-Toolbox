// @vitest-environment jsdom
/**
 * The three heights render ONE table component. This asserts that the same `JobsTable` produces
 * the same columns and the same 28px row at both densities — the property that makes "the panel
 * and the page cannot disagree" true by construction rather than by two lists being kept in sync.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JobsTable } from "../../src/renderer/app/jobs-rail/JobsTable";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

const NOW = Date.parse("2026-09-02T12:05:00Z");

function job(over: Partial<JobStatus> = {}): JobStatus {
  return {
    id: "j1",
    kind: "sim",
    state: "running",
    subject_ids: ["ernie"],
    created_at: "2026-09-02T12:00:00Z",
    started_at: "2026-09-02T12:00:00Z",
    finished_at: null,
    progress: null,
    liveness: null,
    waiting_on: [],
    exit_code: null,
    error: null,
    artifacts: [],
    cpu_percent: 42.5,
    rss: 1024 * 1024 * 512,
    ...over,
  } as unknown as JobStatus;
}

function headers(container: HTMLElement): string[] {
  return [...container.querySelectorAll("thead th")].map((th) => th.textContent?.trim().replace(/\s+/g, " ") ?? "");
}

describe("JobsTable at three heights", () => {
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

  function render(density: "panel" | "page", jobs: JobStatus[] = [job()], props: Record<string, unknown> = {}) {
    act(() => {
      root.render(
        <JobsTable jobs={jobs} now={NOW} density={density} selectedId={null} onSelect={() => {}} {...props} />,
      );
    });
  }

  it("carries the same eight columns at both densities", () => {
    render("panel");
    const panel = headers(container);
    render("page");
    expect(headers(container)).toEqual(panel);
    expect(panel.map((h) => h.replace(/[▲▼]/g, "").trim())).toEqual([
      "State",
      "Kind",
      "Subjects",
      "Stage",
      "Elapsed",
      "CPU",
      "RSS",
      "Waiting on",
    ]);
  });

  it("pins --row-h to 28px at both densities (one shipped density)", () => {
    for (const density of ["panel", "page"] as const) {
      render(density);
      const table = container.querySelector<HTMLElement>(".jobs-table");
      expect(table?.style.getPropertyValue("--row-h")).toBe("28px");
    }
  });

  it("gives each height its own testid so both can be on screen at once", () => {
    render("page");
    expect(container.querySelector("[data-testid='jobs-table']")).not.toBeNull();
    render("panel");
    expect(container.querySelector("[data-testid='jobs-panel-table']")).not.toBeNull();
    expect(container.querySelector("[data-testid='jobs-table']")).toBeNull();
  });

  it("renders elapsed, CPU and RSS as right-aligned tabular numbers", () => {
    render("page");
    const row = container.querySelector("tbody tr")!;
    const cells = [...row.querySelectorAll("td")].map((td) => td.textContent?.trim());
    expect(cells).toContain("5m 0s");
    expect(cells).toContain("42.5 %");
    const numeric = [...row.querySelectorAll("td[data-align='right']")];
    expect(numeric).toHaveLength(3);
  });

  it("shows a skeleton on first load, not on refetch", () => {
    render("page", [], { loading: true });
    expect(container.querySelector(".skeleton-rows")).not.toBeNull();
    expect(container.querySelector("tbody tr")).toBeNull();
  });

  it("puts a failed load inline in the surface that failed, never a toast", () => {
    render("page", [], { error: new Error("HTTP 503"), onRetry: () => {} });
    const inline = container.querySelector(".inline-error");
    expect(inline).not.toBeNull();
    expect(inline?.textContent).toContain("Could not load jobs.");
    expect(inline?.textContent).toContain("HTTP 503");
  });

  it("selects a row by clicking it", () => {
    const onSelect = vi.fn();
    render("page", [job({ id: "j9" })], { onSelect });
    act(() => {
      container.querySelector<HTMLElement>("tbody tr")!.click();
    });
    expect(onSelect).toHaveBeenCalledWith("j9");
  });

  it("marks the selected row so the detail pane and the table agree", () => {
    render("page", [job({ id: "j9" })], { selectedId: "j9" });
    expect(container.querySelector("tbody tr[data-selected='true']")).not.toBeNull();
  });

  it("states the empty case in the table body", () => {
    render("page", [], { emptyMessage: "No jobs match these filters." });
    expect(container.textContent).toContain("No jobs match these filters.");
  });
});
