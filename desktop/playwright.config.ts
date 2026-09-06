import { defineConfig } from "@playwright/test";
import { join } from "node:path";

// Run against a real server by exporting TIT_E2E_SERVER_URL + TIT_E2E_TOKEN; otherwise a mock
// server is started for the run on a pid-derived port so that two agents building this repo in
// parallel worktrees never collide on a fixed port, output directory, or artifacts directory
// (ra_11 finding 4). `realServer` must be captured before the `??=` defaults below run, or it
// would always see its own default and never take the real-server branch.
const realServer = process.env.TIT_E2E_SERVER_URL;

const PORT = Number(process.env.TIT_MOCK_PORT ?? 8790 + (process.pid % 500));
// Playwright workers re-`require` this config file in their own process, so a bare
// `process.pid` here picks up a different pid per worker (rb_13 NEW-8: test-results/ split
// across 73440/73442/74049 within one `npm run e2e`). Writing the id onto `process.env` — not
// just a local `const` — fixes it: the first process to load this config (the CLI's own, before
// any worker is forked) sets it once, and every worker Node forks afterwards inherits that
// already-set environment, so its own `??=` is a no-op and reuses the same id.
process.env.TIT_E2E_RUN_ID ??= String(process.pid);
const RUN = process.env.TIT_E2E_RUN_ID;
process.env.TIT_E2E_SERVER_URL ??= `http://127.0.0.1:${PORT}`;
process.env.TIT_E2E_TOKEN ??= "mock-token";
process.env.TIT_E2E_ARTIFACTS ??= join(__dirname, "tests/e2e/artifacts", RUN);

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  outputDir: `test-results/${RUN}`,
  webServer: realServer
    ? undefined
    : {
        command: "node tests/mock-server/server.mjs",
        url: `http://127.0.0.1:${PORT}/api/health`,
        reuseExistingServer: false,
        env: {
          TIT_MOCK_PORT: String(PORT),
          TIT_MOCK_TOKEN: "mock-token",
          TIT_MOCK_WS_INTERVAL_MS: process.env.TIT_MOCK_WS_INTERVAL_MS ?? "500",
          TIT_MOCK_DATA_ROOT: process.env.TIT_MOCK_DATA_ROOT ?? "",
        },
        timeout: 15_000,
      },
  // `default` is every spec Playwright already ran before this project existed (v3-pipelines
  // program S2, decision P5) -- `testIgnore` keeps `tests/e2e/real/**` out of it unconditionally,
  // so a bare `npx playwright test` / `npm run e2e` (mock server, no TIT_E2E_SERVER_URL) is
  // byte-for-byte the run it always was: same files, same webServer, same everything above. The
  // `real` project is appended only when `TIT_E2E_SERVER_URL` is set, so it does not exist (and
  // cannot silently run against the mock's `webServer`, which real specs never expect) otherwise;
  // `npx playwright test --project real ...` is how a lane invokes it (README's "against a real
  // server" section), never bare `npm run e2e` (whose `pree2e` rebuild would race a concurrent
  // build from another lane).
  projects: [
    { name: "default", testIgnore: /\/tests\/e2e\/real\// },
    ...(realServer ? [{ name: "real", testDir: "tests/e2e/real" }] : []),
  ],
});
