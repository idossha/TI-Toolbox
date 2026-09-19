// @vitest-environment jsdom
/**
 * One job, three surfaces, identical strings. The Jobs page's selection list
 * (`pages/jobs/JobsSelectionTable`), the 260px rail (`app/jobs-rail/JobsTable`) and the Summary
 * tab (`app/jobs-rail/JobDetailPane`) all draw their cells from `app/jobs-rail/columns.tsx`.
 * Before this, the page table had its own column list and formatters and kept showing a STAGE
 * column and single latest CPU/RSS values while the Summary showed peak · avg for the same job.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JobsTable } from "../../src/renderer/app/jobs-rail/JobsTable";
import { JobDetailPane } from "../../src/renderer/app/jobs-rail/JobDetailPane";
import { JOB_COLUMNS, jobSummaryRows } from "../../src/renderer/app/jobs-rail/columns";
import { JobsSelectionTable } from "../../src/renderer/pages/jobs/JobsSelectionTable";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

const NOW = Date.parse("2026-09-19T21:01:00Z");

const JOB = {
  id: "345c10b47aa5438e",
  kind: "ex",
  state: "succeeded",
  subject_ids: ["101"],
  created_at: "2026-09-19T20:59:26Z",
  started_at: "2026-09-19T20:59:26Z",
  finished_at: "2026-09-19T21:00:51Z",
  progress: { stage: "search", i: 4, n: 4, pct: 100 },
  liveness: null,
  waiting_on: [],
  exit_code: 0,
  error: null,
  artifacts: [],
  cpu_percent: 98.3,
  rss: 4.14 * 1024 ** 3,
  cpu_percent_peak: 1105.7,
  cpu_percent_avg: 343.9,
  rss_peak: 9819495424,
  rss_avg: 3717900767,
  log_path: null,
} as unknown as JobStatus;

const EXPECTED = { elapsed: "1m 25s", cpu: "1106 % · avg 344 %", rss: "9.1 GB · avg 3.5 GB" };

function texts(root: ParentNode, selector: string): string[] {
  return [...root.querySelectorAll(selector)].map((el) => el.textContent?.trim().replace(/\s+/g, " ") ?? "");
}

describe("one job row model across the page table, the rail and the Summary", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("the shared columns have no STAGE and end in CPU and RSS", () => {
    expect(JOB_COLUMNS.map((c) => c.id)).toEqual(["state", "kind", "subjects", "elapsed", "cpu", "rss"]);
  });

  it("the page's selection list prints the shared strings, without a STAGE column", () => {
    act(() => {
      root.render(<JobsSelectionTable jobs={[JOB]} now={NOW} selected={[]} onSelectedChange={() => {}} />);
    });
    const headers = texts(container, "thead th");
    expect(headers).not.toContain("Stage");
    expect(headers.slice(-5)).toEqual(["Kind", "Subjects", "Elapsed", "CPU", "RSS"]);
    const cells = texts(container, "tbody tr:not(.selection-spacer) td");
    expect(cells).toContain(EXPECTED.elapsed);
    expect(cells).toContain(EXPECTED.cpu);
    expect(cells).toContain(EXPECTED.rss);
    expect(cells).not.toContain("98.3 %");
    expect(cells).not.toContain("4.1 GB");
  });

  it("the rail prints the same strings", () => {
    act(() => {
      root.render(<JobsTable jobs={[JOB]} now={NOW} density="panel" selectedId={null} onSelect={() => {}} />);
    });
    const cells = texts(container, "tbody tr td");
    expect(cells).toContain(EXPECTED.elapsed);
    expect(cells).toContain(EXPECTED.cpu);
    expect(cells).toContain(EXPECTED.rss);
  });

  it("the Summary prints the same strings from the same rows", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    act(() => {
      root.render(
        <QueryClientProvider client={client}>
          <JobDetailPane job={JOB} onOpenJob={() => {}} density="page" />
        </QueryClientProvider>,
      );
    });
    const dd = texts(container, ".definition-list dd");
    expect(dd).toContain(EXPECTED.elapsed);
    expect(dd).toContain(EXPECTED.cpu);
    expect(dd).toContain(EXPECTED.rss);
    // ...and the rows are literally the shared model's, so the check cannot drift either.
    const rows = jobSummaryRows(JOB, NOW);
    expect(rows.map(([, v]) => v)).toEqual(["ex", "101", EXPECTED.elapsed, EXPECTED.cpu, EXPECTED.rss]);
  });
});
