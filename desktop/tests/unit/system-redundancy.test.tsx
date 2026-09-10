// @vitest-environment jsdom
/**
 * **The zero-redundancy audit.** Every metric appears on the System page exactly once.
 *
 * The page showed the same number in two places more than once while it was being built — a CPU
 * percentage in its own tile and again in a chart legend, disk free in a tile and in the meter
 * caption under it, the load average in two cards, uptime in a card header and in its own row.
 * Each of those is a place a reader has to check whether the two agree, and each was found by
 * eye, late, in a screenshot.
 *
 * So the rule is enforced two ways, and the second is the one that matters:
 *
 * 1. `METRIC_HOME` assigns every metric one owning card, and each card publishes its own list as
 *    `data-metrics`. A structural check that no metric is claimed by two cards.
 * 2. **The rendered DOM** is searched for the literal figures a fixture snapshot produces, and
 *    each must occur exactly once. This is what catches a duplicate that was never *declared* —
 *    which is how every real instance of the bug happened.
 *
 * uPlot is mocked (it needs a real canvas 2D context, which jsdom has not); the timeline's legend,
 * which is where the CPU and memory percentages live, is ordinary DOM and is asserted here.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SystemSnapshot } from "../../src/renderer/api/client";

class FakeUPlot {
  constructor() {}
  setSize() {}
  setData() {}
  destroy() {}
}
vi.mock("uplot", () => ({ default: FakeUPlot }));
vi.mock("uplot/dist/uPlot.min.css", () => ({}));

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", FakeResizeObserver);

const GB = 1024 ** 3;
/** Inside the page's own five-minute window, which is measured against the real clock. */
const NOW_S = Date.now() / 1000;

/**
 * Deliberately unique figures. Every number below is distinguishable from every other one, so
 * "this string occurs twice in the page" can only mean the metric is rendered twice — not that
 * two different metrics happened to round to the same value.
 */
const SNAPSHOT: SystemSnapshot = {
  ts: NOW_S - 2,
  cpu_percent: 41.3,
  cpu_count: 12,
  cpu_per_core: [3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25],
  load_avg: [1.11, 2.22, 3.33],
  uptime_s: 3 * 86_400 + 4 * 3600 + 12 * 60,
  mem: { total: 32 * GB, available: 17.7 * GB, used: 9.4 * GB, percent: 29.7, free: 12.1 * GB, cached: 5.8 * GB, buffers: 0.9 * GB },
  swap: { total: 4 * GB, used: 0.4 * GB, free: 3.6 * GB, percent: 11 },
  disk: { total: 1000 * GB, free: 412.5 * GB, percent: 58.8, path: "/mnt/example" },
  disk_docker: null,
  own: { pid: 4141, cpu_percent: 3.2, rss: 210 * 1024 ** 2 },
  kernels: 1,
  net: { bytes_sent: 1, bytes_recv: 2 },
  process_total: 59,
  processes: [
    {
      pid: 4231,
      ppid: 40,
      name: "simnibs_python",
      cmdline: "simnibs_python -m tit.sim spec.json",
      cpu_percent: 55.5,
      rss: 1.8 * GB,
      mem_percent: 5.6,
      threads: 8,
      status: "running",
      started: 0,
      relevant: true,
      owner_kind: "job",
      owner_id: "job-1",
      owner_label: "sim · ernie",
    },
  ],
  docker: {
    reachable: true,
    latency_ms: 3.4,
    version: "27.3.1",
    api_version: "1.47",
    error: "",
    df: {
      images_size: 61.7 * GB,
      images_count: 7,
      images_reclaimable: 24.3 * GB,
      containers_size: 0.8 * GB,
      containers_count: 3,
      volumes_size: 9.6 * GB,
      volumes_count: 4,
      volumes_reclaimable: 2 * GB,
      build_cache_size: 3.1 * GB,
    },
    own: {
      id: "e086e5826ed6",
      name: "ti-toolbox-tit-1",
      image: "idossha/ti-toolbox:3.0.0",
      image_id: "sha256:9c1f",
      state: "running",
      status: "running",
      health: "healthy",
      started_at: "",
      restarts: 0,
      cpu_limit: 8,
      mem_limit: 24 * GB,
      mounts: [{ source: "/host/projects/000", destination: "/mnt/example", mode: "rw" }],
    },
    containers: [{ id: "9f2c", name: "qsiprep-sub-101", image: "pennlinc/qsiprep:0.22.0", state: "running", status: "Up 4 minutes" }],
    images: [{ repo_tag: "idossha/ti-toolbox:3.0.0", size: 19 * GB }],
    warnings: [],
  },
} as unknown as SystemSnapshot;

const STORAGE = {
  project_dir: "/mnt/example",
  total_bytes: 246 * 1024 ** 3,
  total_files: 15_100,
  scanned_at: Date.now() / 1000 - 180,
  duration_s: 42.7,
  scanning: false,
  partial: false,
  kinds: [
    { kind: "flex_search", label: "Flex search", bytes: 181 * 1024 ** 3, files: 4120 },
    { kind: "simulations", label: "Simulations", bytes: 42 * 1024 ** 3, files: 860 },
  ],
  largest: [{ name: "sub-101 · Flex search", kind: "flex_search", bytes: 122 * 1024 ** 3 }],
};
vi.mock("../../src/renderer/pages/system/storageApi", () => ({
  useStorage: () => ({ data: STORAGE, isLoading: false, isError: false }),
  getStorage: async () => STORAGE,
}));

vi.mock("../../src/renderer/ws/useSystemStream", () => ({
  useSystemStream: () => ({ status: "open", samples: [SNAPSHOT, { ...SNAPSHOT, ts: NOW_S }], attempt: 0 }),
}));

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

async function renderPage(): Promise<void> {
  const { default: page } = await import("../../src/renderer/pages/system/index");
  const Page = page.Component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Page />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

/** How many times `needle` appears in the page's visible text. */
function occurrences(needle: string): number {
  const text = container.textContent ?? "";
  return text.split(needle).length - 1;
}

describe("METRIC_HOME (the structural half)", () => {
  it("gives every metric exactly one owning card", async () => {
    const { METRIC_HOME, metricsOf } = await import("../../src/renderer/pages/system/model");
    const keys = Object.keys(METRIC_HOME);
    const cards = new Set(Object.values(METRIC_HOME));
    const covered = [...cards].flatMap((c) => metricsOf(c));
    expect(covered.sort()).toEqual(keys.sort());
    // …and every card claims at least one metric, so a card cannot quietly stop declaring.
    for (const card of cards) expect(metricsOf(card).length).toBeGreaterThan(0);
  });

  it("is what the cards actually publish, with no metric claimed twice", async () => {
    await renderPage();
    const declared = [...container.querySelectorAll<HTMLElement>("[data-metrics]")].flatMap((el) =>
      (el.dataset.metrics ?? "").split(" ").filter(Boolean),
    );
    expect(declared.length).toBe(new Set(declared).size);
    const { METRIC_HOME } = await import("../../src/renderer/pages/system/model");
    // Every metric that has a home is on screen — no card silently stops rendering.
    expect(declared.sort()).toEqual(Object.keys(METRIC_HOME).sort());
  });
});

describe("the rendered page shows each figure exactly once", () => {
  it("prints the CPU and memory percentages only in the timeline legend", async () => {
    await renderPage();
    // These are the two numbers that were duplicated first, into per-metric tiles.
    expect(occurrences("41.3 %")).toBe(1);
    expect(occurrences("29.7 %")).toBe(1);
    const legend = container.querySelector('[data-testid="timeline-legend"]')!;
    expect(legend.textContent).toContain("41.3 %");
    expect(legend.textContent).toContain("29.7 %");
  });

  it("prints disk free once, in Storage", async () => {
    await renderPage();
    expect(occurrences("412.5 GB")).toBe(1);
    expect(container.querySelector('[data-testid="system-storage"]')!.textContent).toContain("412.5 GB");
  });

  it("separates the machine's limit from the project's share of it", async () => {
    await renderPage();
    const storage = container.querySelector('[data-testid="system-storage"]')!;
    expect(storage.querySelector('[data-testid="storage-system"]')).not.toBeNull();
    expect(storage.querySelector('[data-testid="storage-project"]')).not.toBeNull();
    // The project total is printed once, in its own half.
    expect(occurrences("246.0 GB")).toBe(1);
    expect(container.querySelector('[data-testid="project-total"]')!.textContent).toBe("246.0 GB");
    // …and it is stated as a share of the disk it competes for, so "246 GB" means something.
    expect(storage.textContent).toContain("% of the system disk");
    // The card says how old its own numbers are — it is a scan, not a live sample.
    expect(container.querySelector('[data-testid="storage-age"]')!.textContent).toMatch(/scanned .* ago/);
  });

  it("keeps the by-kind breakdown behind a disclosure", async () => {
    await renderPage();
    expect(container.querySelector('[data-testid="storage-kinds"]')).toBeNull();
    expect(container.querySelector('[data-testid="storage-kinds-toggle"]')).not.toBeNull();
  });

  it("prints the load average and uptime once each, in Host", async () => {
    await renderPage();
    for (const n of ["1.11", "2.22", "3.33"]) expect(occurrences(n)).toBe(1);
    expect(occurrences("3 d 04:12")).toBe(1);
    const host = container.querySelector('[data-testid="system-host"]')!;
    expect(host.textContent).toContain("1.11");
    expect(host.textContent).toContain("3 d 04:12");
  });

  it("prints the container's mounts once, in Docker", async () => {
    await renderPage();
    expect(occurrences("/mnt/example (rw)")).toBe(1);
    expect(container.querySelector('[data-testid="system-docker"]')!.textContent).toContain("/mnt/example (rw)");
  });

  it("prints the Docker disk figures once, in Storage — not also in the Docker card", async () => {
    await renderPage();
    // `docker system df` answers "what is filling this disk", which is Storage's question.
    expect(occurrences("24.3 GB")).toBe(1);
    const storage = container.querySelector('[data-testid="system-storage"]')!;
    expect(storage.textContent).toContain("24.3 GB");
    expect(container.querySelector('[data-testid="system-docker"]')!.textContent).not.toContain("24.3 GB");
  });

  it("keeps the largest-images list behind a disclosure, so it costs no height by default", async () => {
    await renderPage();
    expect(container.querySelector('[data-testid="docker-images"]')).toBeNull();
    expect(container.querySelector('[data-testid="docker-images-toggle"]')).not.toBeNull();
  });

  it("has no jobs strip at all", async () => {
    await renderPage();
    // The rail is on every screen and `pages/jobs` is the full list. A third view of the same rows
    // was this page's largest redundancy, and it took its height from the process table.
    expect(container.querySelector('[data-testid="system-jobs"]')).toBeNull();
    expect(container.textContent).not.toContain("Recently finished");
    expect(container.textContent).not.toContain("No jobs running");
  });

  it("draws one core bar per core, in the timeline's footer and nowhere else", async () => {
    await renderPage();
    expect(container.querySelectorAll(".system-core")).toHaveLength(12);
    const timeline = container.querySelector('[data-testid="system-timeline"]')!;
    expect(timeline.querySelectorAll(".system-core")).toHaveLength(12);
  });
});
