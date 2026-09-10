// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ProjectInsights,
  activityCalendar,
  formatStorage,
  type ProjectSummary,
} from "../../src/renderer/pages/overview/ProjectInsights";

(
  globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
const summary: ProjectSummary = {
  identity: { name: "Example study", path: "/mnt/study", created_at: null },
  storage: {
    state: "ready",
    total_bytes: 3072,
    derivatives: [{ name: "SimNIBS", bytes: 2048, children: [{ name: "Head models", bytes: 1024 }, { name: "Simulations", bytes: 1024 }] }],
    other_bytes: 1024,
    scanned_at: "2026-09-09T12:00:00Z",
  },
  activity: {
    days: [{ date: "2026-09-09", count: 3 }],
    recent: [
      {
        id: "job-1",
        kind: "sim",
        state: "succeeded",
        subject_ids: ["101"],
        created_at: "2026-09-09T11:00:00Z",
      },
    ],
    last_activity_at: "2026-09-09T11:00:00Z",
    history_since: "2026-09-09T11:00:00Z",
  },
};

describe("project information", () => {
  let root: Root;
  let container: HTMLDivElement;
  let client: QueryClient;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-09T23:00:00Z"));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });
  afterEach(() => {
    act(() => root.unmount());
    client.clear();
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  async function render(data?: ProjectSummary) {
    if (data) client.setQueryData(["project-summary"], data);
    await act(async () =>
      root.render(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <ProjectInsights />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
  }
  it("uses UTC days across a leap year and fills only absent days with zero", () => {
    const days = activityCalendar(
      [{ date: "2024-02-29", count: 7 }],
      new Date("2024-03-01T00:30:00+01:00"),
    );
    expect(days).toHaveLength(365);
    expect(days.at(-1)).toEqual({ date: "2024-02-29", count: 7 });
    expect(days[0]).toEqual({ date: "2023-03-02", count: 0 });
  });
  it("shows known identity, a storage breakdown and counted activity without inventing creation dates", async () => {
    await render(summary);
    expect(container.textContent).toContain("Example study");
    expect(container.textContent).toContain("/mnt/study");
    expect(container.textContent).toContain("3 KiB");
    expect(container.textContent).toContain("SimNIBS");
    expect(container.querySelectorAll(".project-storage-child")).toHaveLength(2);
    expect(container.textContent).toContain("Other");
    expect(container.textContent).not.toContain("Created");
    const days = container.querySelectorAll(".project-calendar-day");
    expect(days).toHaveLength(365);
    const today = container.querySelector<HTMLButtonElement>(
      '[aria-label="2026-09-09: 3 recorded jobs"]',
    )!;
    act(() => today.click());
    expect(today.getAttribute("aria-pressed")).toBe("true");
    expect(container.textContent).toContain("2026-09-09: 3 recorded jobs.");
    expect(container.querySelector("details")).toBeNull();
    expect(container.textContent).not.toContain("Recent activity");
  });
  it("polls a pending scan and replaces unknown storage with measured data", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(summary)));
    vi.stubGlobal("fetch", fetcher);
    await render({
      ...summary,
      storage: {
        ...summary.storage,
        state: "scanning",
        total_bytes: null,
        derivatives: [],
        other_bytes: null,
      },
    });
    expect(container.textContent).toContain("Measuring project data");
    expect(container.textContent).not.toContain("3 KiB");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2010);
    });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("3 KiB");
  });
  it("keeps storage failures distinct from empty project storage", async () => {
    await render({
      ...summary,
      storage: {
        ...summary.storage,
        state: "error",
        total_bytes: null,
        other_bytes: null,
        derivatives: [],
      },
    });
    expect(container.textContent).toContain("Storage scan unavailable");
    expect(container.textContent).not.toContain("0 B");
    expect(formatStorage(0)).toBe("0 B");
  });
});
