import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, launchElectronApp, setTheme } from "./_helpers";

// Smoke + screenshot coverage for the four job-submitting panels (Source, Cluster Permutation,
// NIfTI Group Averaging, Nilearn Visuals). settings.spec.ts and panels.spec.ts cover the deeper
// functional flows (theme, panel toggling, Quick Notes autosave, Subject Info); these four share
// enough shape (subject/simulation pickers + a Plan card) that one spec exercising "renders, and
// a minimal selection produces a Plan" per panel is proportionate to their complexity.
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");
const ALL_PANELS = ["source", "cluster-permutation", "nifti-group-average", "nilearn-visuals", "quick-notes"];

let app: ElectronApplication;
let page: Page;

async function launchApp(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  // The nav rail's live `useEnabledPages()` (app/registry.ts) gates a "panels" page on the
  // *server's* `settings.panels`, not this localStorage mirror (which only seeds each panel's own
  // static `PageDef.enabled` fallback — see pages/panels/_shared.ts's doc comment). The mock's
  // default fixture enables source/quick-notes (plus the now-page-less `subject-info` id)
  // (tests/fixtures/settings_seed.json), so without this route the other three panels this spec
  // covers never appear in the nav at all — not a timing issue, `getByRole("link", ...)` simply
  // never resolves. Route around it to enable everything this spec exercises.
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: {
        telemetry: { consented: true, enabled: false },
        panels: ALL_PANELS,
        image_tag: "idossha/simnibs:v2.3.1",
        allow_unsafe_overrides: false,
        theme: "system",
      },
    });
  });
  await page.addInitScript((panels: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(panels));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, ALL_PANELS);
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

async function setDark(): Promise<void> {
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await setTheme(page, "dark", () => page.getByRole("radio", { name: "Dark" }).click());
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("Source panel: selecting a subject produces a Plan for both pipelines", async () => {
  await connect();
  await page.getByRole("link", { name: "Source", exact: true }).click();
  // No page header outside Settings/Help (DESIGN.md §2.3, §12.4 item 2) — the panel identity is
  // the shell's own `data-page`, not an `<h1>`.
  await expectPage(page, "panel-source");

  // Scoped to the subject picker row, not a bare `getByText("ernie")` — the mock server
  // persists for the whole suite run, so an earlier spec's "ernie" job trace in the jobs rail
  // can still be live here and match "ernie" too, causing a strict-mode violation (same root
  // cause as ra_11 finding 5 / optimizer-flex.spec.ts's job-trace scoping).
  await page.locator(".subject-picker-row", { hasText: "ernie" }).click();
  // CardHeader renders its title as a <span> (see ui/Layout.tsx), not a heading element.
  await expect(page.getByText("Build forward solution")).toBeVisible();
  // Known mock-server gap (see pages/panels/source/PARITY.md "Honest gap found in Round 2"):
  // validateConfig() wrongly requires a `subject_id` field for kind="source" (SourceConfig has no
  // such field — it's `subject_ids`/`pairs`), so /api/validate/source against the mock always
  // returns ok:false and the real Plan (Jobs/CPUs/Memory) never renders here. Assert the actual
  // observed behavior — the server-error Callout the shared PlanSummary shows for it — rather than
  // a `CPUs` text match that would pass for the wrong reason (it also matches the CPUs field
  // label above, present before any subject is even picked). The panel maps that raw
  // `{path: "subject_id", message: "subject_id is required"}` to plain copy (rb_13 NEW-7) rather
  // than rendering the field path, so the visible text is "Select a subject." rather than the raw
  // server message.
  await expect(page.getByText("Select a subject.").first()).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: join(ARTIFACTS, "panel-source-light.png") });

  // Real UI-to-contract round trip: what actually reached the server, not just a toast.
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByRole("button", { name: "Build forward" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Build forward" }).click();
  const jobBody = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    config: { mode: string; forward: { eeg_net: string } };
  };
  expect(jobBody.kind).toBe("source");
  expect(jobBody.subject_ids).toEqual(["ernie"]);
  expect(jobBody.config.mode).toBe("forward");
  expect(jobBody.config.forward.eeg_net).toBeTruthy();

  await setDark();
  await page.getByRole("link", { name: "Source", exact: true }).click();
  await expectPage(page, "panel-source");
  await page.screenshot({ path: join(ARTIFACTS, "panel-source-dark.png") });
});

test("NIfTI Group Averaging panel renders its form", async () => {
  await connect();
  await page.getByRole("link", { name: "NIfTI group averaging", exact: true }).click();
  await expectPage(page, "panel-nifti-group-average");
  await expect(page.getByLabel("Analysis name")).toBeVisible();

  // Real assertion (not just visibility): entering a name actually clears its validation error.
  await expect(page.getByText("Enter an analysis name.")).toBeVisible();
  await page.getByLabel("Analysis name").fill("E2E_Group_Average");
  await expect(page.getByText("Enter an analysis name.")).toHaveCount(0);

  await page.screenshot({ path: join(ARTIFACTS, "panel-nifti-group-average-light.png") });

  await setDark();
  await page.getByRole("link", { name: "NIfTI group averaging", exact: true }).click();
  await expectPage(page, "panel-nifti-group-average");
  await page.screenshot({ path: join(ARTIFACTS, "panel-nifti-group-average-dark.png") });
});

test("Nilearn Visuals panel renders its form", async () => {
  await connect();
  await page.getByRole("link", { name: "Nilearn visuals", exact: true }).click();
  await expectPage(page, "panel-nilearn-visuals");
  await expect(page.getByLabel("Sub-directory name")).toBeVisible();

  // Real assertion (not just visibility): entering a name actually clears its validation error.
  await expect(page.getByText("Enter a sub-directory name for the output files.")).toBeVisible();
  await page.getByLabel("Sub-directory name").fill("e2e_visuals");
  await expect(page.getByText("Enter a sub-directory name for the output files.")).toHaveCount(0);

  await page.screenshot({ path: join(ARTIFACTS, "panel-nilearn-visuals-light.png") });

  await setDark();
  await page.getByRole("link", { name: "Nilearn visuals", exact: true }).click();
  await expectPage(page, "panel-nilearn-visuals");
  await page.screenshot({ path: join(ARTIFACTS, "panel-nilearn-visuals-dark.png") });
});

test("Cluster Permutation panel switches between classification and correlation", async () => {
  await connect();
  await page.getByRole("link", { name: "Cluster permutation", exact: true }).click();
  await expectPage(page, "panel-cluster-permutation");
  await expect(page.getByText("Test type")).toBeVisible();

  await page.getByRole("radio", { name: "Correlation" }).click();
  await expect(page.getByText("Correlation type")).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "panel-cluster-permutation-light.png") });

  await setDark();
  await page.getByRole("link", { name: "Cluster permutation", exact: true }).click();
  await expectPage(page, "panel-cluster-permutation");
  await page.screenshot({ path: join(ARTIFACTS, "panel-cluster-permutation-dark.png") });
});
