import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp, setTheme } from "./_helpers";

/**
 * The System page — the full-height system monitor, pinned above Settings (maintainer,
 * 2026-09-07). The jobs rail's Host tab is the 260 px glance and is covered by `jobs.spec.ts`;
 * everything here is about the page.
 *
 * It runs against the mock server, whose `/ws/system` snapshot answers **every** optional field
 * the 2026-09-07 contract added — so a field the real server stops sending shows up here as a
 * meter that has gone blank, rather than passing because the test only ever saw the degraded
 * payload.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

async function launchApp(width = 1440, height = 900): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width, height });
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

async function openSystem(): Promise<void> {
  await page.getByRole("link", { name: "System", exact: true }).click();
  await expect(page.getByTestId("system-page")).toBeVisible();
  // The gauges only carry numbers once a snapshot has arrived over the socket.
  await expect(page.getByTestId("system-cpu")).toContainText(/\d+(\.\d+)? %/, { timeout: 20_000 });
}

/** True when the page's own box, or the document, is taller than the room it was given. */
async function pageScrolls(): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.querySelector<HTMLElement>('[data-testid="system-page"]');
    if (!el) return true;
    const own = el.scrollHeight > el.clientHeight + 1;
    const doc = document.documentElement.scrollHeight > window.innerHeight + 1;
    return own || doc;
  });
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.afterEach(async () => {
  await app?.close();
});

test("the rail pins System directly above Settings", async () => {
  await launchApp();
  await connect();

  const pinned = page.locator(".nav-section-pinned a");
  await expect(pinned).toHaveText(["System", "Settings", "Help"]);

  // "Above" is a geometric claim, so it is checked geometrically rather than by list order alone.
  const system = (await page.getByRole("link", { name: "System", exact: true }).boundingBox())!;
  const settings = (await page.getByRole("link", { name: "Settings", exact: true }).boundingBox())!;
  expect(system.y).toBeLessThan(settings.y);

  // System takes no ⌘ digit: the rail's ten digits belong to the workflow rows, and the row
  // advertises no chord to assistive tech either.
  await expect(page.getByRole("link", { name: "System", exact: true })).not.toHaveAttribute("aria-keyshortcuts", /./);
});

test("reaches the page from the command palette too", async () => {
  await launchApp();
  await connect();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
  await page.keyboard.type("System");
  await page.getByRole("dialog").getByRole("option", { name: /System/ }).first().click();
  await expect(page.getByTestId("system-page")).toBeVisible();
});

test("every panel is populated from the live stream, in both themes", async () => {
  await launchApp();
  await connect();
  await openSystem();

  // Live, not a stub.
  await expect(page.getByTestId("system-ws-status").locator(".status-dot-success")).toHaveAttribute(
    "title",
    "Live updates connected",
    { timeout: 20_000 },
  );

  // ── band 1: resources ──
  const cpu = page.getByTestId("system-cpu");
  await expect(cpu).toContainText("12 cores");
  await expect(cpu).toContainText("load 1.42 · 1.10 · 0.98");
  // One core row per reported core — not `cpu_count` copies of the average.
  await expect(page.getByTestId("system-cores").locator(".system-core")).toHaveCount(12);

  const memory = page.getByTestId("system-memory");
  await expect(memory).toContainText(/\d+(\.\d+)? %/);
  // The used/cache/buffers/free bar: four segments, because the mock reports the breakdown.
  await expect(page.getByTestId("memory-meter").locator(".system-meter-seg")).toHaveCount(4);
  await expect(memory).toContainText("Cache");
  await expect(page.getByTestId("swap-meter").locator(".system-meter-seg")).toHaveCount(2);

  const storage = page.getByTestId("system-storage");
  await expect(storage).toContainText("/mnt/example");
  await expect(storage).toContainText("/var/lib/docker");
  await expect(page.getByTestId("project-disk-meter").locator(".system-meter-seg")).toHaveCount(2);

  const host = page.getByTestId("system-host");
  await expect(host).toContainText("3 d 04:12");
  await expect(host).toContainText("pid 41");
  // The network rate needs two samples to exist at all; at a 2 s cadence it is there shortly.
  await expect(host.getByText(/↓ .+\/s/)).toBeVisible({ timeout: 20_000 });

  // ── band 2: Docker ──
  const docker = page.getByTestId("system-docker");
  await expect(page.getByTestId("docker-status")).toContainText("Engine 27.3.1");
  await expect(page.getByTestId("docker-df-meter").locator(".system-meter-seg")).toHaveCount(4);
  await expect(docker).toContainText("reclaimable");
  await expect(page.getByTestId("docker-own")).toContainText("idossha/ti-toolbox:3.0.0");
  await expect(page.getByTestId("docker-own")).toContainText("8 cores · 24.0 GB");
  await expect(page.getByTestId("docker-siblings")).toContainText("qsiprep-sub-101");
  await expect(page.getByTestId("docker-images")).toContainText("pennlinc/qsiprep");
  await expect(page.getByTestId("docker-warnings")).toContainText("prune");

  // ── band 2: processes ──
  const processes = page.getByTestId("system-processes");
  await expect(processes).toContainText("simnibs_python");
  // Everything, not a keyword allowlist: `tini` is on no toolbox list and is still listed.
  await expect(processes).toContainText("tini");
  await expect(processes).toContainText(/top \d+ of \d+/);
  // The stop affordance is ONLY on rows the server attributed to a job or a kernel: the fixture's
  // two `sim · ernie` rows (the runner and its meshfix child) have one, tini and gmsh do not.
  await expect(processes.getByRole("button", { name: "Stop sim · ernie" })).toHaveCount(2);
  await expect(processes.getByRole("button", { name: /Stop tini/ })).toHaveCount(0);
  await expect(processes.getByRole("button", { name: /Stop gmsh/ })).toHaveCount(0);

  // Sorting is real: MEM puts the largest RSS first. Asserted against the table's own rows rather
  // than a named fixture process — the mock's process list is shared server state and
  // `jobs.spec.ts`'s Host test terminates one of them, so keying on a name would make this spec
  // pass or fail by file order.
  await processes.getByRole("button", { name: "MEM", exact: true }).click();
  await expect
    .poll(
      async () => {
        const mem = await processes.locator("tbody tr td:nth-child(4)").allInnerTexts();
        const gb = mem.map((t) => {
          const n = Number.parseFloat(t);
          return t.includes("GB") ? n * 1024 : t.includes("MB") ? n : n / 1024;
        });
        return gb.length > 1 && gb.every((v, i) => i === 0 || gb[i - 1]! >= v);
      },
      { timeout: 10_000 },
    )
    .toBe(true);

  // ── band 3: the work ──
  await expect(page.getByTestId("system-jobs")).toBeVisible();

  // The whole point of the layout: one screen at 1440x900.
  expect(await pageScrolls()).toBe(false);
  await page.screenshot({ path: join(ARTIFACTS, "system-light-1440.png") });

  await setTheme(page, "dark", async () => {
    await page.evaluate(() => localStorage.setItem("tit-theme", "dark"));
    await page.reload();
    await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  });
  await openSystem();
  await expect(page.getByTestId("system-cores").locator(".system-core")).toHaveCount(12);
  await expect(page.getByTestId("docker-status")).toContainText("Engine 27.3.1");
  expect(await pageScrolls()).toBe(false);
  await page.screenshot({ path: join(ARTIFACTS, "system-dark-1440.png") });
});

test("fills 1920x1080 without a scroll either", async () => {
  await launchApp(1920, 1080);
  await connect();
  await openSystem();
  await expect(page.getByTestId("system-cores").locator(".system-core")).toHaveCount(12);
  await expect(page.getByTestId("system-processes")).toContainText("simnibs_python");
  expect(await pageScrolls()).toBe(false);
  await page.screenshot({ path: join(ARTIFACTS, "system-light-1920.png") });
});

test("the figures keep updating — it is a monitor, not one snapshot", async () => {
  await launchApp();
  await connect();
  await openSystem();
  const cpu = page.getByTestId("system-cpu").locator(".system-readout-value");
  const first = await cpu.innerText();
  // The mock's CPU is a random walk, so a second value must arrive within a few cadences. This is
  // the assertion that separates "the page rendered" from "the page is live".
  await expect
    .poll(async () => (await cpu.innerText()) !== first, { timeout: 20_000, intervals: [500] })
    .toBe(true);
});
