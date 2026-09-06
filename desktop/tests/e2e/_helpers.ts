import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { _electron as electron, expect, type ElectronApplication, type Locator, type Page } from "@playwright/test";

/** The repository root Electron is pointed at (desktop/, whose package.json "main" is out/main). */
const APP_ROOT = join(__dirname, "..", "..");

/**
 * A test run must not hijack the monitor (`src/main/window.ts`).
 *
 * On macOS every launch here used to raise a window and steal the keyboard focus — 15 times per
 * `npm run e2e`, once per spec file, and again per `beforeEach` in the specs that relaunch.
 * `TIT_E2E_OFFSCREEN=1` tells main to build the window and never show it, to hide the dock icon
 * and to swallow notification banners. The renderer still runs on the real GPU and screenshots
 * identically, which is what these tests actually assert on.
 *
 * **Default on darwin only.** Linux CI runs under Xvfb, where there is no monitor to hijack and
 * where the shown-window path is the one worth exercising. `TIT_E2E_HEADED=1` restores visible
 * windows everywhere — main gives that variable priority — and is the debugging opt-in.
 *
 * An explicit `TIT_E2E_OFFSCREEN` in the environment is always honoured, so a Linux developer can
 * ask for quiet runs too.
 */
export function offscreenEnv(env: NodeJS.ProcessEnv = process.env): Record<string, string> {
  if (env.TIT_E2E_HEADED === "1") return {};
  if (env.TIT_E2E_OFFSCREEN !== undefined) return { TIT_E2E_OFFSCREEN: env.TIT_E2E_OFFSCREEN };
  return process.platform === "darwin" ? { TIT_E2E_OFFSCREEN: "1" } : {};
}

/**
 * Defect 1 (`dev/notes/v3-scene-ia/critic-notes.md` §5a/§7.2, fix-round lane FIX-C): `npx
 * playwright test`'s `default` project starts exactly one `tests/mock-server/server.mjs` process
 * for the WHOLE invocation (`playwright.config.ts`'s `webServer`, `workers: 1`), so a job an
 * earlier spec FILE created and never itself drove to a terminal state keeps its exclusivity slot
 * (same kind + subject, or a `group_id`) for every later file too — measured forcing
 * `layout.spec.ts`'s right pane to the Terminal tab instead of Scene on all four run pages and
 * blowing its dead-space budget by up to 11 points, purely from a leftover `analyzer`/`ernie` job
 * that was 3 SECONDS old (legitimately still inside its own ~10.1s natural lifetime — a job age or
 * "stuck too long" watchdog, `server.mjs`'s own `QUEUE_WATCHDOG_MS`, cannot distinguish that from a
 * job actively progressing 3 seconds into a file that has not finished yet). Only an explicit
 * per-file boundary — every launch forgets whatever an earlier one left running — closes that gap,
 * so `launchElectronApp` calls it before every launch rather than leaving it to an `afterAll` in
 * every spec, which is exactly how the leak happened in the first place.
 *
 * Gated on the mock's own default token, `"mock-token"` (`playwright.config.ts`'s `TIT_E2E_TOKEN
 * ??= "mock-token"`, which fires only when nothing set a real one): a `--project=real` run against
 * the live container always sets `TIT_E2E_TOKEN` to that container's own generated token first, so
 * this is always false there and the call never fires — never a network request toward the
 * container the maintainer is using, not even a harmless one. Best-effort beyond that gate too: the
 * mock's `POST /api/__mock/reset` (`tests/mock-server/server.mjs`) is the only thing that should
 * ever answer it, so any other failure (not up yet, timed out) is swallowed — the very next thing
 * every spec does is wait on the app itself, which fails loudly on its own if the mock is not up.
 */
async function resetMockJobs(): Promise<void> {
  if (process.env.TIT_E2E_TOKEN !== "mock-token") return;
  const url = process.env.TIT_E2E_SERVER_URL;
  if (!url) return;
  try {
    await fetch(`${url}/api/__mock/reset`, {
      method: "POST",
      headers: { authorization: `Bearer ${process.env.TIT_E2E_TOKEN}` },
      signal: AbortSignal.timeout(2000),
    });
  } catch {
    /* best-effort — see doc comment above */
  }
}

/**
 * Launches the built app the way every spec needs it: its own user-data directory, and offscreen
 * unless the developer asked for windows.
 *
 * Named `launchElectronApp`, not `launchApp`: most specs already wrap this in their own local
 * `launchApp()` that also assigns the module-level `app`/`page`, and a shared export of that name
 * shadows into a recursive call.
 *
 * The environment is spread onto `process.env` rather than replacing it — `electron.launch({ env })`
 * REPLACES the child's environment, and dropping PATH/HOME from an Electron launch fails in ways
 * that look nothing like the cause. Pass `env` to add spec-specific variables.
 */
export async function launchElectronApp(
  options: { userDataDir?: string; env?: Record<string, string>; args?: string[] } = {}
): Promise<ElectronApplication> {
  await resetMockJobs();
  const userDataDir = options.userDataDir ?? mkdtempSync(join(tmpdir(), "tit-e2e-"));
  return electron.launch({
    args: [APP_ROOT, ...(options.args ?? [])],
    env: { ...process.env, TIT_USER_DATA_DIR: userDataDir, ...offscreenEnv(), ...(options.env ?? {}) },
  });
}

export type Theme = "light" | "dark";

/**
 * Flips the theme and waits for `data-theme` to land, having first turned off CSS transitions via
 * `prefers-reduced-motion` (`ui/base.css` honours it). Without this, a screenshot taken right
 * after a theme change can catch buttons mid colour-transition — `components.css`'s
 * `transition: background-color` runs for ~150ms after `data-theme` changes, and a handful of
 * specs used to grab the frame immediately (rb_13 NEW-3: measured as e.g.
 * `rgb(128,131,135)`, ~40% of the way from `--surface` to `#161c24`, on "Select all" and
 * "Generate leadfield" in `preprocess-dark.png` / `optimizer-ex-dark.png`).
 *
 * `page.emulateMedia` is a context-level setting, so it survives an in-app navigation or a full
 * `page.reload()` later in the same test — call this once before the *first* theme change in a
 * spec and every later flip in that test stays covered.
 *
 * Pass `via` to drive the change through the real UI (a Settings/Gallery theme control) or through
 * `localStorage` + `reload()` — whatever the spec is actually exercising. Omit it to just stamp
 * `data-theme` directly (the common case: a spec that only wants the dark screenshot, not to test
 * how theme gets set).
 */
export async function setTheme(page: Page, theme: Theme, via?: () => Promise<void>): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  if (via) {
    await via();
  } else {
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

/**
 * Navigates by the nav rail's stable id (`data-testid="nav-item-<id>"`, set by `app/NavRail.tsx`)
 * rather than by the label text, so a Stage-2 rename of a page's title does not break every spec
 * that visits it. `label` is the v1 fallback and stays for as long as any page's spec still keys
 * on the visible name: below 1440px the rail is icons only (DESIGN.md §9, program Q1), and the
 * label is then the tooltip's, not the row's, so the id is the only reliable handle.
 */
export async function gotoPage(page: Page, id: string, label?: string): Promise<void> {
  await page.locator(".nav-rail").waitFor();
  const byId = page.getByTestId(`nav-item-${id}`);
  if ((await byId.count()) > 0) {
    await byId.click();
    return;
  }
  if (label) {
    const byLabel = page.getByRole("link", { name: label, exact: true });
    if ((await byLabel.count()) > 0) {
      await byLabel.click();
      return;
    }
    // Not in the rail at all: a `hidden` page (navGroup "dev") is reachable only from the
    // palette, which is what "hidden" means in `app/registry.ts`. Navigating the way a user
    // would keeps the spec honest instead of asserting a rail entry that should not exist.
    await openPalette(page);
    await page.getByTestId("palette-input").fill(label);
    await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${label}`) }).first().click();
    await expect(page.getByTestId("palette-input")).toHaveCount(0);
    return;
  }
  throw new Error(`no nav item "${id}" in the rail (and no label fallback given)`);
}

/**
 * Puts a `FormSection` (by its visible title) into the state a test needs, **converging** instead
 * of checking once and acting.
 *
 * The failure it prevents, measured on 2026-09-04: `RunWork`'s fill controller opens sections over
 * rAF passes for a page nobody has touched yet, so a body that is absent when a spec counts it can
 * be present a frame later when the click actually lands — and the click then *closes* the section
 * the spec was trying to open. `segmented-idiom.spec.ts` failed that way deterministically on the
 * Simulator at 1280x900 (Electrodes: read closed, clicked, ended closed), and the same check-then-
 * act shape is in `simulator.spec.ts`. Reading `aria-expanded` immediately before each click and
 * letting the controller settle after it converges in two clicks at worst.
 *
 * It also insists the state is the **user's** (`data-fill-user`), not one the controller happens to
 * have produced: a section the controller opened is still the controller's to close on the next
 * content growth, and a spec that merely found it open has no promise it will still be open two
 * statements later. Measured: `segmented-idiom.spec.ts` read Pre-processing's "Existing outputs"
 * as open, and the controller had closed it again by the next assertion. Clicking twice when the
 * state is already right is deliberate — that is how a user makes a state stick, and the rule this
 * helper leans on is the product's, not the test's.
 */
export async function setSectionOpen(page: Page, title: string, open: boolean): Promise<Locator> {
  const section = page.locator('[data-page-active="true"] .form-section', { hasText: title }).first();
  const trigger = section.locator(".form-section-header-trigger");
  const want = open ? "open" : "closed";
  await expect(trigger).toBeVisible();
  for (let i = 0; i < 6; i += 1) {
    const expanded = (await trigger.getAttribute("aria-expanded")) === String(open);
    const mine = (await section.getAttribute("data-fill-user")) === want;
    if (expanded && mine) break;
    await trigger.click();
    await page.waitForTimeout(150);
  }
  await expect(trigger).toHaveAttribute("aria-expanded", String(open));
  await expect(section).toHaveAttribute("data-fill-user", want);
  return section;
}

/** ⌘K / Ctrl+K, then wait for the palette to actually be on screen. */
export async function openPalette(page: Page): Promise<void> {
  await page.keyboard.press(`${process.platform === "darwin" ? "Meta" : "Control"}+k`);
  await expect(page.getByTestId("palette-input")).toBeVisible();
}

/** The modifier Playwright needs for an app shortcut on this platform. */
export const MOD = process.platform === "darwin" ? "Meta" : "Control";

/**
 * Asserts which screen is on, by the shell's `data-page` attribute (`app/Shell.tsx`).
 *
 * Not `toHaveURL`: the app runs a MemoryRouter, so the document URL is the server origin for the
 * whole session and a route assertion against it can only ever fail. Not a heading either —
 * DESIGN.md v2 removed page headers. The attribute is the app's own statement of what it is
 * showing, which is the thing worth asserting.
 */
export async function expectPage(page: Page, id: string): Promise<void> {
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", id);
}

/** Asserts the subject the whole shell is scoped to (`data-subject`, same rationale). */
export async function expectSubject(page: Page, id: string): Promise<void> {
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", id);
}

// ---------------------------------------------------------------------------------------------
// Real-server smoke helpers (v3-pipelines program, lane S2, decisions P4-P6). Additive only —
// every `tests/e2e/*.spec.ts` above still drives the mock server through its own inline
// connect/select code; these exist for `tests/e2e/real/*.spec.ts`, which all point at a live
// `tit.server` (`TIT_E2E_SERVER_URL` + `TIT_E2E_TOKEN`) instead.
// ---------------------------------------------------------------------------------------------

/**
 * Connects the launcher to a real (non-mock) server and waits for the shell to render subjects.
 * Every real spec starts here so the connect dance (`launcher.spec.ts`'s own inline version)
 * exists exactly once — a change to the launcher's field ids only needs updating here.
 */
export async function connectReal(page: Page, opts: { url?: string; token?: string } = {}): Promise<void> {
  const url = opts.url ?? process.env.TIT_E2E_SERVER_URL;
  const token = opts.token ?? process.env.TIT_E2E_TOKEN;
  if (!url || !token) {
    throw new Error("connectReal needs TIT_E2E_SERVER_URL and TIT_E2E_TOKEN (or url/token options)");
  }
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", url);
  await page.fill("#token", token);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", url).href, { timeout: 30_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 30_000 });
}

/** Scopes the shell to a subject through the command palette — the only subject control that
 *  exists outside a page's own batch table (U6). Mirrors the inline pattern every mock spec
 *  already uses, exported once for the real specs. */
export async function selectSubject(page: Page, id: string): Promise<void> {
  await openPalette(page);
  await page.getByTestId("palette-input").fill(id);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${id}`) }).first().click();
  await expectSubject(page, id);
}

/** Expands the jobs rail to its 260px panel (⌘J / Ctrl+J). */
export async function openJobsPanel(page: Page): Promise<void> {
  await page.keyboard.press(`${MOD}+j`);
  await expect(page.locator(".jobs-rail-expanded")).toHaveCount(1);
}

/** Switches the expanded jobs panel's tab (`app/jobs-rail/JobsPanel.tsx`'s `[Jobs][Console][Host]
 *  [Report]` segment). Panel pages (Source, Cluster Permutation, NIfTI averaging, Nilearn) have no
 *  page-local `job-terminal` of their own — this is their "page terminal" equivalent. */
export async function selectJobsPanelTab(page: Page, name: "Jobs" | "Console" | "Host" | "Report"): Promise<void> {
  await page.getByRole("radiogroup", { name: "Jobs panel" }).getByRole("radio", { name, exact: true }).click();
}

/**
 * Waits for a job of `kind` to appear as a trace in the collapsed jobs rail (`.job-trace`, whose
 * `.job-trace-kind` span carries the raw kind string — "sim", "flex", "analyzer", "source", …).
 * This is the "jobs rail shows the new job" assertion every real spec makes right after Run.
 */
export async function waitForJobTrace(page: Page, kind: string, opts: { timeoutMs?: number } = {}): Promise<Locator> {
  const trace = page.locator(".job-trace", { hasText: kind }).first();
  await expect(trace).toBeVisible({ timeout: opts.timeoutMs ?? 20_000 });
  return trace;
}

/**
 * Cancels a running job from the UI: clicks its rail trace (which selects it and expands the
 * panel — `app/jobs-rail/JobsRail.tsx`), Stop, confirms, and asserts the terminal "cancelled"
 * state (`jobs.spec.ts`'s own flow, reused unchanged for the real long-kind specs — sim/flex,
 * program P4's `started -> cancel` behaviour).
 */
export async function cancelJobFromRail(page: Page, kind: string, opts: { timeoutMs?: number } = {}): Promise<void> {
  const trace = await waitForJobTrace(page, kind, opts);
  await trace.click();
  await expect(page.locator(".jobs-rail-expanded")).toHaveCount(1);
  const detail = page.getByTestId("job-detail");
  await expect(detail).toBeVisible({ timeout: 10_000 });
  const stop = detail.getByRole("button", { name: "Stop", exact: true });
  await expect(stop).toBeVisible({ timeout: opts.timeoutMs ?? 20_000 });
  await stop.click();
  await page.getByRole("button", { name: "Stop job" }).click();
  await expect(detail.getByText("cancelled", { exact: true })).toBeVisible({ timeout: 15_000 });
}

/**
 * Writes the exact JSON body a real spec posted to `/api/jobs` (or `/api/jobs/groups`) to
 * `tests/smoke/payloads/<kind>.json`, so Level A (`tests/smoke`, lane S1) can replay precisely
 * what the UI sent instead of a hand-typed guess at the config shape (program P5 — the flex
 * failure this whole harness exists to catch was exactly a UI/runner config divergence). `kind`
 * carries a variant suffix when a page has several ("sim-mti", "analyzer-voxel").
 */
export function recordPayload(kind: string, body: unknown): void {
  const dir = join(__dirname, "..", "..", "..", "tests", "smoke", "payloads");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${kind}.json`), `${JSON.stringify(body, null, 2)}\n`);
}

/** The host path the shared dev container's `/mnt/000` project mount resolves to (see this lane's
 *  brief) — real specs build cleanup paths from it, never a literal elsewhere. */
export const PROJECT_HOST_ROOT = "/Users/idohaber/datasets/000";

/**
 * For a page with no output-naming field visible in its own request body shape (its config carries
 * `marker` — e.g. an analysis/output name this spec supplied — somewhere inside a container path
 * a finished job reports), returns the project-relative directory up to and including `marker`, so
 * cleanup targets the real directory the server actually created instead of a guessed convention.
 * `null` when `marker` is not in the path at all (nothing to clean up from this artifact).
 */
export function smokeDirFromArtifactPath(artifactPath: string, marker: string): string | null {
  const rel = artifactPath.replace(/^\/mnt\/000\/?/, "");
  const idx = rel.indexOf(marker);
  if (idx === -1) return null;
  return rel.slice(0, idx + marker.length);
}

/**
 * Deletes exactly the given project-relative output paths after a real run (program P6: "namespaced
 * and cleaned up", "never overwrite a pre-existing output"). Refuses to touch anything whose own
 * final path segment does not contain "smoke" — a typo'd or stale path can then only ever no-op
 * (nothing exists there / it isn't deleted) rather than silently reaching into a pre-existing
 * subject's real output.
 */
export function cleanupSmokeOutputs(relPaths: string[]): void {
  for (const rel of relPaths) {
    const base = rel.split("/").filter(Boolean).pop() ?? "";
    if (!/smoke/i.test(base)) {
      throw new Error(`cleanupSmokeOutputs: refusing to delete "${rel}" — its own name has no "smoke" in it`);
    }
    const abs = join(PROJECT_HOST_ROOT, rel);
    if (existsSync(abs)) rmSync(abs, { recursive: true, force: true });
  }
}

/** The subset of `JobStatus` these helpers read — never the full generated type, so a schema
 *  change elsewhere cannot break this file. */
export interface JobStatusLite {
  id: string;
  kind: string;
  state: string;
  subject_ids: string[];
  error?: { type?: string; message?: string; last_lines?: string[] } | null;
  artifacts?: { path: string; kind?: string; label?: string }[];
}

const JOB_TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled", "skipped", "lost"]);

/**
 * One `GET /api/jobs/<id>`, via Node's own `fetch` rather than `page.request` — deliberately NOT
 * routed through the Electron page's own request context. `page.request` shares state with the
 * page's browser context (proxy/session config an offscreen Electron `BrowserWindow` does not set
 * up the same way a normal browser context does) and was observed to hang indefinitely mid-suite
 * with zero CPU on either side (no error, no timeout, no retry — the polling loop's own `await`
 * simply never returned), stalling a passed job behind a test that never finished. A 10s
 * `AbortController` bounds every single request so a bad one surfaces as a normal poll-and-retry
 * rather than a silent hang.
 *
 * `tit/server/routes/jobs.py`'s single-job route (unlike the list route, and unlike a submit
 * response) answers `{spec, status}` — a `JobDetail`, not a bare `JobStatus` — so `state`/`kind`/
 * `artifacts` live under `.status`, not at the top level. Reading the bare body as `JobStatusLite`
 * silently produced `state: undefined` on a 200 OK (never an error, never a state
 * `JOB_TERMINAL_STATES` would match), which is what actually caused the "did not reach a terminal
 * state within Xms" failures on jobs that had, per the server's own job list, already succeeded —
 * unwrapped here once, for every caller.
 */
async function getJobStatus(url: string, token: string, jobId: string): Promise<JobStatusLite | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(`${url}/api/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { status?: JobStatusLite } & Partial<JobStatusLite>;
    return (body.status ?? (body as JobStatusLite)) ?? null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Polls `GET /api/jobs/<id>` directly against the server (not through the UI/WS) until the job
 * reaches a terminal state. The real specs use this to assert *completion* (program P4) on the
 * server's own record rather than guessing how long a UI refetch cycle takes; "started" is already
 * asserted a moment earlier from `waitForJobTrace`. `page` is accepted (unused) to keep every call
 * site's signature stable — see `getJobStatus`'s doc comment for why it is not used to make the
 * request itself.
 */
export async function waitForJobTerminal(
  _page: Page,
  opts: { url: string; token: string; jobId: string; timeoutMs: number; pollMs?: number },
): Promise<JobStatusLite> {
  const deadline = Date.now() + opts.timeoutMs;
  const pollMs = opts.pollMs ?? 3000;
  for (;;) {
    const job = await getJobStatus(opts.url, opts.token, opts.jobId);
    if (job && JOB_TERMINAL_STATES.has(job.state)) return job;
    if (Date.now() > deadline) {
      throw new Error(`waitForJobTerminal: job ${opts.jobId} did not reach a terminal state within ${opts.timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

/**
 * Polls `GET /api/jobs/<id>` until the job is either `running` or has already reached a terminal
 * state — whichever comes first. Some kinds this program tracks as known-broken (flex's ROI-shape
 * bug, program §0) fail within seconds of submission rather than ever reaching "started", so a
 * real spec that only knew how to wait for "running" would time out reporting the wrong thing. The
 * caller branches on the returned state: `running` -> assert the rail/terminal, then cancel;
 * anything terminal -> the job never ran long enough to cancel, and the caller reports why.
 */
export async function waitForJobRunningOrTerminal(
  _page: Page,
  opts: { url: string; token: string; jobId: string; timeoutMs: number; pollMs?: number },
): Promise<JobStatusLite> {
  const deadline = Date.now() + opts.timeoutMs;
  const pollMs = opts.pollMs ?? 1500;
  for (;;) {
    const job = await getJobStatus(opts.url, opts.token, opts.jobId);
    if (job && (job.state === "running" || JOB_TERMINAL_STATES.has(job.state))) return job;
    if (Date.now() > deadline) {
      throw new Error(`waitForJobRunningOrTerminal: job ${opts.jobId} stayed queued past ${opts.timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

/**
 * Answers the one shared existing-outputs question (plan C3,
 * `pages/_shared/run/ExistingOutputsDialog.tsx`) if it appears. Every run page asks it before it
 * submits whenever some of the planned jobs already have output — so a spec that presses Run has
 * to answer it, and a spec whose plan happens to be all-new must not wait for a dialog that never
 * comes. Both are covered: the wait is short and its absence is not a failure.
 */
export async function answerExistingOutputs(page: Page, decision: "skip" | "replace" = "skip"): Promise<void> {
  const button = page.getByTestId(`existing-outputs-${decision}`);
  try {
    await button.waitFor({ state: "visible", timeout: 2_000 });
  } catch {
    return;
  }
  await button.click();
}
