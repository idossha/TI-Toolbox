// Contract parity of server.mjs with tit.server: POST /auth/logout and the same-origin WebSocket
// policy. Spawns the mock on a private port; the upgrade handshake is done with node:http so no
// WebSocket client library is needed.
import { spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// pid-derived so two agents running `vitest` concurrently in separate worktrees don't collide on
// a fixed port (ra_11 finding 4).
const PORT = 9300 + (process.pid % 500);
const TOKEN = "unit-token";
const BASE = `http://127.0.0.1:${PORT}`;
let child: ChildProcess;

// Real-bytes mode for the in-app viewer: a throwaway data root with one "volume", one document
// and one file just outside it, so the raw route's jail and its Range/ETag semantics can be
// exercised without shipping a real NIfTI as a fixture.
const dataRoot = mkdtempSync(join(tmpdir(), "tit-mock-raw-"));
const RAW_BYTES = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
const rawFile = join(dataRoot, "m2m_ernie", "T1.nii.gz");
const outsideFile = join(dataRoot, "..", "outside-secret.nii.gz");

beforeAll(async () => {
  mkdirSync(join(dataRoot, "m2m_ernie"), { recursive: true });
  writeFileSync(rawFile, RAW_BYTES);
  writeFileSync(join(dataRoot, "m2m_ernie", "report.html"), "<html>x</html>");
  writeFileSync(outsideFile, "secret");
  child = spawn(process.execPath, [join(__dirname, "server.mjs")], {
    env: { ...process.env, TIT_MOCK_PORT: String(PORT), TIT_MOCK_TOKEN: TOKEN, TIT_MOCK_WS_INTERVAL_MS: "100", TIT_MOCK_DATA_ROOT: dataRoot },
    stdio: "ignore",
  });
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error("mock server did not start");
}, 15_000);

afterAll(async () => {
  if (child.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    child.once("exit", () => resolve());
    child.kill();
  });
});

async function sessionCookie(): Promise<string> {
  const res = await fetch(`${BASE}/auth/session?token=${TOKEN}`, { redirect: "manual" });
  expect(res.status).toBe(303);
  const setCookie = res.headers.get("set-cookie") ?? "";
  const m = /tit_session=([^;]+)/.exec(setCookie);
  if (!m) throw new Error(`no session cookie in ${setCookie}`);
  return `tit_session=${m[1]}`;
}

/** HTTP status of the /ws/system upgrade handshake; 101 means the socket was accepted. */
function upgradeStatus(headers: Record<string, string>): Promise<number> {
  return new Promise((resolve, reject) => {
    const req = request({
      host: "127.0.0.1",
      port: PORT,
      path: "/ws/system",
      headers: {
        connection: "Upgrade",
        upgrade: "websocket",
        "sec-websocket-version": "13",
        "sec-websocket-key": Buffer.from("0123456789abcdef").toString("base64"),
        ...headers,
      },
    });
    req.on("upgrade", (res, socket) => {
      socket.destroy();
      resolve(res.statusCode ?? 0);
    });
    req.on("response", (res) => {
      res.resume();
      resolve(res.statusCode ?? 0);
    });
    req.on("error", reject);
    req.end();
  });
}

describe("mock server: POST /auth/logout", () => {
  it("ends a cookie session (204, cookie cleared, id forgotten)", async () => {
    // A real browser attaches Sec-Fetch-Site to a same-origin fetch; without it (or a matching
    // Origin) a cookie-authenticated mutation is now CSRF-blocked (see the CSRF describe below),
    // so this proof header is what makes the call legitimate, not a workaround.
    const sameOrigin = { "sec-fetch-site": "same-origin" };
    const cookie = await sessionCookie();
    expect((await fetch(`${BASE}/api/version`, { headers: { cookie } })).status).toBe(200);
    const res = await fetch(`${BASE}/auth/logout`, { method: "POST", headers: { cookie, ...sameOrigin } });
    expect(res.status).toBe(204);
    expect(res.headers.get("set-cookie")).toMatch(/^tit_session=;.*Max-Age=0/);
    expect((await fetch(`${BASE}/api/version`, { headers: { cookie } })).status).toBe(401);
    expect((await fetch(`${BASE}/auth/logout`, { method: "POST", headers: { cookie, ...sameOrigin } })).status).toBe(401);
  });

  it("requires auth, accepts Bearer, and rejects GET", async () => {
    expect((await fetch(`${BASE}/auth/logout`, { method: "POST" })).status).toBe(401);
    expect((await fetch(`${BASE}/auth/logout`, { method: "POST", headers: { authorization: `Bearer ${TOKEN}` } })).status).toBe(204);
    expect((await fetch(`${BASE}/auth/logout`)).status).toBe(405);
  });
});

// Parity with tit/server/auth.py's `_cookie_csrf_ok` (ra_14 finding #7; rb_12 flagged the mock as
// missing this rule, so a renderer call that forgets to be same-origin couldn't be caught against
// the mock). Bearer auth is exempt throughout — only a cookie-authenticated, state-changing
// request needs to prove it came from this app's own origin.
describe("mock server: cookie CSRF (parity with tit/server/auth.py)", () => {
  it("blocks a cookie-authed mutation with a foreign Origin, no Origin/Sec-Fetch-Site, or cross-site Sec-Fetch-Site", async () => {
    const cookie = await sessionCookie();
    const put = (headers: Record<string, string>) => fetch(`${BASE}/api/catalog/notes`, { method: "PUT", headers: { cookie, "content-type": "application/json", ...headers }, body: JSON.stringify({ text: "x" }) });
    expect((await put({ origin: "http://evil.example" })).status).toBe(403);
    expect((await put({})).status).toBe(403); // neither Origin nor Sec-Fetch-Site present
    expect((await put({ "sec-fetch-site": "cross-site" })).status).toBe(403);
  });

  it("allows a cookie-authed mutation with a matching Origin or Sec-Fetch-Site: same-origin, and any GET regardless", async () => {
    const cookie = await sessionCookie();
    const put = (headers: Record<string, string>) => fetch(`${BASE}/api/catalog/notes`, { method: "PUT", headers: { cookie, "content-type": "application/json", ...headers }, body: JSON.stringify({ text: "x" }) });
    expect((await put({ origin: BASE })).status).toBe(200);
    expect((await put({ "sec-fetch-site": "same-origin" })).status).toBe(200);
    expect((await fetch(`${BASE}/api/catalog/notes`, { headers: { cookie, origin: "http://evil.example" } })).status).toBe(200); // safe method
  });

  it("exempts Bearer auth from the CSRF check", async () => {
    const res = await fetch(`${BASE}/api/catalog/notes`, {
      method: "PUT",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json", origin: "http://evil.example" },
      body: JSON.stringify({ text: "x" }),
    });
    expect(res.status).toBe(200);
  });
});

describe("mock server: /ws/system origin policy", () => {
  it("allows an absent Origin and a same-origin one; rejects foreign origins before auth", async () => {
    const auth = { authorization: `Bearer ${TOKEN}` };
    expect(await upgradeStatus(auth)).toBe(101);
    expect(await upgradeStatus({ ...auth, origin: BASE })).toBe(101);
    expect(await upgradeStatus({ ...auth, origin: "http://evil.example" })).toBe(403);
    expect(await upgradeStatus({ ...auth, origin: `http://localhost:${PORT}` })).toBe(403); // host must match byte-for-byte
    expect(await upgradeStatus({ origin: "http://evil.example" })).toBe(403);
    expect(await upgradeStatus({})).toBe(401);
  });
});

// Parity with tit/server/routes/files.py::raw, so an e2e run can feed the in-app viewer real
// bytes through the same URL shape the real server serves.
describe("mock server: GET/HEAD /api/files/raw/{path}", () => {
  const auth = { authorization: `Bearer ${TOKEN}` };
  const rawUrl = (path: string) => `${BASE}/api/files/raw${path}`;

  it("streams the whole file as opaque bytes, never encoded", async () => {
    const res = await fetch(rawUrl(rawFile), { headers: auth });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/octet-stream");
    expect(res.headers.get("content-length")).toBe(String(RAW_BYTES.length));
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("accept-ranges")).toBe("bytes");
    expect(res.headers.get("content-encoding")).toBeNull();
    expect(Buffer.from(await res.arrayBuffer()).equals(RAW_BYTES)).toBe(true);
  });

  it("answers a range with 206 and revalidates with 304", async () => {
    const ranged = await fetch(rawUrl(rawFile), { headers: { ...auth, range: "bytes=0-99" } });
    expect(ranged.status).toBe(206);
    expect(ranged.headers.get("content-range")).toBe(`bytes 0-99/${RAW_BYTES.length}`);
    expect((await ranged.arrayBuffer()).byteLength).toBe(100);

    const etag = ranged.headers.get("etag") ?? "";
    expect(etag).not.toBe("");
    const revalidated = await fetch(rawUrl(rawFile), { headers: { ...auth, "if-none-match": etag } });
    expect(revalidated.status).toBe(304);

    const unsatisfiable = await fetch(rawUrl(rawFile), { headers: { ...auth, range: `bytes=${RAW_BYTES.length + 10}-` } });
    expect(unsatisfiable.status).toBe(416);
    expect(unsatisfiable.headers.get("content-range")).toBe(`bytes */${RAW_BYTES.length}`);
  });

  it("HEAD returns the headers with no body", async () => {
    const res = await fetch(rawUrl(rawFile), { method: "HEAD", headers: auth });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-length")).toBe(String(RAW_BYTES.length));
    expect((await res.arrayBuffer()).byteLength).toBe(0);
  });

  it("refuses anything outside the data root, a document extension, or a missing file", async () => {
    expect((await fetch(rawUrl(outsideFile), { headers: auth })).status).toBe(403);
    expect((await fetch(rawUrl(join(dataRoot, "m2m_ernie", "..", "..", "outside-secret.nii.gz")), { headers: auth })).status).toBe(403);
    expect((await fetch(rawUrl(join(dataRoot, "m2m_ernie", "report.html")), { headers: auth })).status).toBe(403);
    expect((await fetch(rawUrl(join(dataRoot, "m2m_ernie", "nope.nii.gz")), { headers: auth })).status).toBe(404);
    expect((await fetch(rawUrl(rawFile))).status).toBe(401);
  });

  it("gives GET /api/view/{kind} a Tetravox ViewSpec v2 scene whose dataset paths resolve through this route", async () => {
    const spec = (await (await fetch(`${BASE}/api/view/subject?subject=ernie`, { headers: auth })).json()) as {
      scene: { version: number; datasets: { path: string }[] };
    };
    const dataset = spec.scene.datasets[0]!;
    expect(spec.scene.version).toBe(2);
    expect(dataset.path.startsWith("/api/files/raw/")).toBe(true);
    expect(dataset.path.endsWith("/T1.nii.gz")).toBe(true);
    expect((await fetch(`${BASE}${dataset.path}`, { method: "HEAD", headers: auth })).status).toBe(200);
  });
});

// VE (docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)): one resolution, two addressings. `view`
// is what the embed at /tetravox/ is posted; `scene` is the host-path document written to disk.
describe("POST /api/view/open", () => {
  it("names a file the Tetravox app will treat as a scene, in both path languages", async () => {
    const res = await fetch(`${BASE}/api/view/open`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
      body: JSON.stringify({ kind: "subject", subject: "ernie" }),
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { name: string; path: string; host_path: string };
    // `.tetravox.json`, not `.tvx.json`: the app classifies anything else as data.
    expect(body.name.endsWith(".tetravox.json")).toBe(true);
    expect(body.path).toContain("/code/ti-toolbox/viewer/");
    expect(body.host_path).toContain("/code/ti-toolbox/viewer/");
    expect(body.path).not.toBe(body.host_path);
  });

  it("gives the scene filesystem paths, never /api/files/raw URLs — the app reads files", async () => {
    const res = await fetch(`${BASE}/api/view/open`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
      body: JSON.stringify({ kind: "subject", subject: "ernie" }),
    });
    const body = (await res.json()) as { scene: { datasets: { path: string; absPath: string }[] } };
    expect(body.scene.datasets.length).toBeGreaterThan(0);
    for (const dataset of body.scene.datasets) {
      expect(dataset.path.startsWith("/api/")).toBe(false);
      expect(dataset.absPath.startsWith("/api/")).toBe(false);
    }
  });

  it("gives `view` the /api/files/raw URLs the embed fetches back through this origin", async () => {
    const res = await fetch(`${BASE}/api/view/open`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
      body: JSON.stringify({ kind: "subject", subject: "ernie" }),
    });
    const body = (await res.json()) as {
      view: { datasets: { path: string }[] };
      scene: { datasets: { path: string }[] };
    };
    expect(body.view.datasets.length).toBeGreaterThan(0);
    for (const dataset of body.view.datasets) expect(dataset.path.startsWith("/api/files/raw/")).toBe(true);
    // The same resolution, twice addressed: same datasets, same order, different language. This is
    // the property that keeps the file list, the file on disk and the picture on screen in step.
    expect(body.view.datasets.length).toBe(body.scene.datasets.length);
  });
});

// Defect 1 (docs/dev/HISTORY.md § 2026-09-04 (scene service) §5a/§7.2, fix-round lane FIX-C): one
// `server.mjs` process backs a whole `npx playwright test` invocation (`playwright.config.ts`'s
// `webServer`), so a job an earlier spec FILE created and never itself drove to a terminal state
// keeps `isReady()`'s same-(kind,subject) exclusivity slot for every later file too. Server.mjs's
// `tick()` now cancels a `queued` job once it has waited past `TIT_MOCK_QUEUE_WATCHDOG_MS` (default
// 90 000, overridable here so this proves the mechanism in milliseconds). This block spins up its
// own server instance — a tiny watchdog would make the *shared* `child` above flaky for every other
// describe in this file — on its own port, and needs no `TIT_MOCK_DATA_ROOT`.
describe("mock server: queue watchdog (defect 1 — no job outlives the spec file that created it)", () => {
  const WD_PORT = PORT + 1;
  const WD_BASE = `http://127.0.0.1:${WD_PORT}`;
  const WD_TOKEN = "watchdog-token";
  const WD_MS = 200;
  let wdChild: ChildProcess;
  const auth = { authorization: `Bearer ${WD_TOKEN}`, "content-type": "application/json" };

  beforeAll(async () => {
    wdChild = spawn(process.execPath, [join(__dirname, "server.mjs")], {
      env: { ...process.env, TIT_MOCK_PORT: String(WD_PORT), TIT_MOCK_TOKEN: WD_TOKEN, TIT_MOCK_QUEUE_WATCHDOG_MS: String(WD_MS) },
      stdio: "ignore",
    });
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      try {
        if ((await fetch(`${WD_BASE}/api/health`)).ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error("watchdog mock server did not start");
  }, 15_000);

  afterAll(async () => {
    if (wdChild.exitCode !== null) return;
    await new Promise<void>((resolve) => {
      wdChild.once("exit", () => resolve());
      wdChild.kill();
    });
  });

  async function submitJob(subjectIds: string[]) {
    const res = await fetch(`${WD_BASE}/api/jobs`, {
      method: "POST",
      headers: auth,
      // No `__mock_fast`: `runTimeline` then takes 6000-10000ms, comfortably longer than `WD_MS`,
      // so job A is still legitimately `running` (not naturally finished) when B's watchdog fires —
      // proving the cancel came from the watchdog, not from A completing on its own.
      body: JSON.stringify({ kind: "analyzer", subject_ids: subjectIds, config: {} }),
    });
    expect(res.status).toBe(201);
    return ((await res.json()) as { id: string }).id;
  }
  async function jobState(id: string): Promise<string> {
    const res = await fetch(`${WD_BASE}/api/jobs/${id}`, { headers: auth });
    return ((await res.json()) as { status: { state: string } }).status.state;
  }

  it("cancels a job queued behind a same-kind, same-subject job once it outlives the watchdog, and leaves the running one alone", async () => {
    const a = await submitJob(["ernie"]);
    const b = await submitJob(["ernie"]); // same kind + subject as A: isReady() queues this behind A
    expect(await jobState(a)).toBe("running");
    expect(await jobState(b)).toBe("queued");

    const deadline = Date.now() + WD_MS + 2000;
    let bState = await jobState(b);
    while (bState === "queued" && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 50));
      bState = await jobState(b);
    }
    expect(bState).toBe("cancelled");

    // A was never blocked on anything and must be untouched by a watchdog scoped to `queued` jobs.
    expect(await jobState(a)).toBe("running");

    const events = (await (await fetch(`${WD_BASE}/api/jobs/${b}/events`, { headers: auth })).json()) as Array<{ type: string; logger?: string }>;
    expect(events.some((e) => e.type === "log" && e.logger === "mock.watchdog")).toBe(true);
  });

  it("does not touch a job that starts running immediately (nothing to queue behind)", async () => {
    const solo = await submitJob(["101"]); // distinct subject: never queued at all
    expect(await jobState(solo)).toBe("running");
    await new Promise((r) => setTimeout(r, WD_MS + 300));
    expect(await jobState(solo)).toBe("running");
  });
});

// Defect 1's other half: the watchdog above cannot catch a job that is only seconds old (the
// critic's own measurement — `layout.spec.ts` saw a leftover `analyzer`/`ernie` job 3 SECONDS into
// its natural ~10.1s `runTimeline` lifetime, legitimately still "running", not stuck by any
// duration a watchdog could use). `POST /api/__mock/reset` is the explicit per-file boundary
// `tests/e2e/_helpers.ts::resetMockJobs` calls from `launchElectronApp` instead. Uses the file's
// shared `child`/`BASE`/`TOKEN` — nothing else in this file touches job state.
describe("mock server: POST /api/__mock/reset (defect 1's explicit per-file boundary)", () => {
  const auth = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };

  it("cancels-and-forgets every non-terminal job, reports the count, and leaves a fresh server empty", async () => {
    const submit = async (subjectIds: string[]) =>
      ((await (await fetch(`${BASE}/api/jobs`, { method: "POST", headers: auth, body: JSON.stringify({ kind: "analyzer", subject_ids: subjectIds, config: {} }) })).json()) as { id: string }).id;
    const a = await submit(["ernie"]); // running immediately
    const b = await submit(["ernie"]); // queued behind A — exactly the leftover shape critic measured

    const before = (await (await fetch(`${BASE}/api/jobs/${a}`, { headers: auth })).json()) as { status: { state: string } };
    expect(before.status.state).toBe("running"); // still 3-ish ms old, well inside its natural lifetime — the case a watchdog cannot see

    const res = await fetch(`${BASE}/api/__mock/reset`, { method: "POST", headers: auth });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ jobs_cleared: 2 }); // A (running) + B (queued): both non-terminal, both counted

    expect((await fetch(`${BASE}/api/jobs/${a}`, { headers: auth })).status).toBe(404);
    expect((await fetch(`${BASE}/api/jobs/${b}`, { headers: auth })).status).toBe(404);
    expect(await (await fetch(`${BASE}/api/jobs`, { headers: auth })).json()).toEqual([]);
  });

  it("is a no-op (0 cleared) when nothing is left running — idempotent, safe to call unconditionally", async () => {
    const res = await fetch(`${BASE}/api/__mock/reset`, { method: "POST", headers: auth });
    expect(await res.json()).toEqual({ jobs_cleared: 0 });
  });

  it("requires auth, like every other /api/* route", async () => {
    expect((await fetch(`${BASE}/api/__mock/reset`, { method: "POST" })).status).toBe(401);
  });
});

// The six `/api/scene/*` routes answer a subject-level problem with the sentence the REAL server
// sends, not the one it stopped sending. Until 2026-09-04 every one of them replied
// `Unknown subject: <id>`; `tit/server/routes/scene.py::_scene_subject` has said something
// actionable since lane FIX-B's round, and a mock that lags means a spec can be written — and pass
// for ever — against wording the product no longer uses (`fix-b-notes.md` O2, `verify-notes.md`
// open issues). Lane CL1.
describe("mock server: /api/scene/* subject errors mirror tit/server/routes/scene.py", () => {
  const auth = { authorization: `Bearer ${TOKEN}` };
  const SCENE_ROUTES = [
    "/api/scene/manifest?subject=",
    "/api/scene/surface?part=gm&subject=",
    "/api/scene/labels?atlas=DK40&subject=",
    "/api/scene/regions?atlas=DK40&subject=",
    "/api/scene/electrodes?net=GSN-HydroCel-185&subject=",
    "/api/scene/volume-legend?id=labeling&subject=",
  ] as const;

  async function detailOf(path: string): Promise<{ status: number; detail: string }> {
    const res = await fetch(`${BASE}${path}`, { headers: auth });
    const body = (await res.json()) as { detail?: string };
    return { status: res.status, detail: body.detail ?? "" };
  }

  it("names the subjects the project does have, in natural order, on all six routes", async () => {
    for (const route of SCENE_ROUTES) {
      const { status, detail } = await detailOf(`${route}zzz`);
      expect(status, route).toBe(404);
      // The real server's sentence verbatim, modulo this fixture's own subject list.
      expect(detail, route).toBe("This project has no subject 'zzz'. It has: 101, ernie, MNI152.");
      expect(detail, route).not.toContain("Unknown subject");
    }
  });

  it("still answers 200 for a subject that does have a head model", async () => {
    for (const route of SCENE_ROUTES) {
      const res = await fetch(`${BASE}${route}ernie`, { headers: auth });
      expect(res.status, route).toBe(200);
    }
  });
});

// The other branch of the same helper, on its own instance: the shipped fixtures give every
// subject a head model, and adding a fourth to `subjects.json` would move counts five other suites
// assert ("3 subjects · 3 m2m · 1 leadfield"). `TIT_MOCK_SUBJECTS_NO_M2M` reaches the branch
// without touching them.
describe("mock server: /api/scene/* on a subject with no head model", () => {
  const M_PORT = PORT + 2;
  const M_BASE = `http://127.0.0.1:${M_PORT}`;
  const M_TOKEN = "no-m2m-token";
  let mChild: ChildProcess;
  const auth = { authorization: `Bearer ${M_TOKEN}` };

  beforeAll(async () => {
    mChild = spawn(process.execPath, [join(__dirname, "server.mjs")], {
      env: { ...process.env, TIT_MOCK_PORT: String(M_PORT), TIT_MOCK_TOKEN: M_TOKEN, TIT_MOCK_SUBJECTS_NO_M2M: "101" },
      stdio: "ignore",
    });
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      try {
        if ((await fetch(`${M_BASE}/api/health`)).ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error("no-m2m mock server did not start");
  }, 15_000);

  afterAll(async () => {
    if (mChild.exitCode !== null) return;
    await new Promise<void>((resolve) => {
      mChild.once("exit", () => resolve());
      mChild.kill();
    });
  });

  it("says what is missing and what to run, on all six routes", async () => {
    const expected =
      "101 has no head model yet: m2m_101/ does not exist. Run Pre-processing (charm) on 101 to create it.";
    for (const route of [
      "/api/scene/manifest?subject=",
      "/api/scene/surface?part=gm&subject=",
      "/api/scene/labels?atlas=DK40&subject=",
      "/api/scene/regions?atlas=DK40&subject=",
      "/api/scene/electrodes?net=GSN-HydroCel-185&subject=",
      "/api/scene/volume-legend?id=labeling&subject=",
    ]) {
      const res = await fetch(`${M_BASE}${route}101`, { headers: auth });
      expect(res.status, route).toBe(404);
      expect(((await res.json()) as { detail: string }).detail, route).toBe(expected);
    }
  });

  it("leaves every other subject alone", async () => {
    expect((await fetch(`${M_BASE}/api/scene/manifest?subject=ernie`, { headers: auth })).status).toBe(200);
  });
});

/**
 * Generic per-subject job groups (IMPLEMENTATION_PLAN.md R3). The mock has to answer the same
 * shapes the real route does, because `batch.spec.ts` reads its scheduler states as the gate
 * evidence for the concurrency cap.
 */
describe("POST /api/jobs/groups beyond preprocessing", () => {
  const auth = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };

  function simConfig(subject: string) {
    return {
      subject_id: subject,
      montages: [{ _type: "Montage", name: "m1", mode: "net", electrode_pairs: [["E1", "E2"]] }],
      __mock_fast: true,
    };
  }

  async function submit(body: Record<string, unknown>) {
    return fetch(`${BASE}/api/jobs/groups`, { method: "POST", headers: auth, body: JSON.stringify(body) });
  }

  it("rejects a sim config missing a schema-required field, the way the real backend does", async () => {
    // Regression: the app POSTed a sim config with no `subject_id`/`montages`, this mock accepted
    // it, and the real runner died on `deserialize_config(SimulationConfig, ...)`. Required fields
    // now come from contracts/generated/config.schema.json, so e2e fails where the real backend would.
    const bad = await fetch(`${BASE}/api/jobs`, {
      method: "POST",
      headers: auth,
      body: JSON.stringify({ kind: "sim", config: { subject_id: "ernie" }, subject_ids: ["ernie"] }),
    });
    expect(bad.status).toBe(422);
    expect(String(((await bad.json()) as { detail: string }).detail)).toContain("montages is required");

    // The group route checks the config it would actually generate (subject_id already forced).
    const badGroup = await submit({ kind: "sim", config: { montages: [] }, subject_ids: ["ernie"], parallel_subjects: 1 });
    expect(badGroup.status).toBe(422);

    // `__mock_*` configs stay exempt: they are this mock's synthetic jobs, never app-built.
    const synthetic = await fetch(`${BASE}/api/jobs`, {
      method: "POST",
      headers: auth,
      body: JSON.stringify({ kind: "sim", config: { __mock_fast: true }, subject_ids: ["ernie"] }),
    });
    expect(synthetic.status).toBe(201);
  });

  it("creates one queued job per subject, each config carrying only its own subject id", async () => {
    const res = await submit({ kind: "sim", config: simConfig("ernie"), subject_ids: ["ernie", "101"], parallel_subjects: 1 });
    expect(res.status).toBe(201);
    const body = (await res.json()) as { group_id: string; jobs: { id: string; state: string; kind: string; subject_ids: string[] }[] };
    expect(body.jobs).toHaveLength(2);
    expect(body.jobs.map((j) => j.kind)).toEqual(["sim", "sim"]);
    expect(body.jobs.map((j) => j.subject_ids[0])).toEqual(["ernie", "101"]);
    // The whole group exists after this ONE request — nothing is withheld for a later POST — and
    // the cap is admission, so at most `parallel_subjects` of them can already be running.
    expect(body.jobs.filter((j) => j.state === "running").length).toBeLessThanOrEqual(1);
    expect(body.jobs.every((j) => ["queued", "running"].includes(j.state))).toBe(true);

    for (const job of body.jobs) {
      const detail = (await (await fetch(`${BASE}/api/jobs/${job.id}`, { headers: auth })).json()) as {
        spec: { config: { subject_id: string } };
      };
      expect(detail.spec.config.subject_id).toBe(job.subject_ids[0]);
    }
  });

  it("takes per-subject configs, including several jobs for one subject", async () => {
    const res = await submit({
      kind: "sim",
      config: simConfig("ernie"),
      subject_ids: ["ernie"],
      subject_configs: [
        { subject_id: "ernie", config: { ...simConfig("ernie"), tag: "a" } },
        { subject_id: "ernie", config: { ...simConfig("ernie"), tag: "b" } },
      ],
      parallel_subjects: 2,
    });
    expect(res.status).toBe(201);
    const body = (await res.json()) as { jobs: { id: string }[] };
    expect(body.jobs).toHaveLength(2);
  });

  it("refuses a cohort kind and a subject outside subject_ids", async () => {
    // A grouped analyzer run is ONE job over the cohort — it has no per-subject cap.
    expect((await submit({ kind: "analyzer", config: {}, subject_ids: ["ernie"], parallel_subjects: 1 })).status).toBe(422);
    const stray = await submit({
      kind: "sim",
      config: simConfig("ernie"),
      subject_ids: ["ernie"],
      subject_configs: [{ subject_id: "999", config: simConfig("999") }],
      parallel_subjects: 1,
    });
    expect(stray.status).toBe(422);
  });
});

describe("mock server: PlanCost.eta_minutes (parity with tit/jobs/eta.py)", () => {
  const auth = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };

  async function planCost(kind: string, config: Record<string, unknown>, subject_ids = ["ernie"]) {
    const res = await fetch(`${BASE}/api/plan/${kind}`, {
      method: "POST",
      headers: auth,
      body: JSON.stringify({ config, subject_ids }),
    });
    expect(res.status).toBe(200);
    return ((await res.json()) as { cost: { eta_minutes: number | null; system: { emulated: boolean } | null } }).cost;
  }

  it("scales a leadfield estimate with the electrode count of the net", async () => {
    // The number the Optimizer's Generate button shows. One FEM solve per electrode, so the
    // 256-electrode cap must cost more than the 185-electrode one — the property the old
    // hardcoded "≈40 min" could not have.
    const small = await planCost("leadfield", { subject_id: "ernie", eeg_net: "GSN-HydroCel-185" });
    const big = await planCost("leadfield", { subject_id: "ernie", eeg_net: "EGI_template" });
    expect(big.eta_minutes!).toBeGreaterThan(small.eta_minutes!);
    expect(small.system?.emulated).toBe(true);
  });

  it("has no leadfield estimate for a net it cannot size", async () => {
    const cost = await planCost("leadfield", { subject_id: "ernie", eeg_net: "no-such-net" });
    expect(cost.eta_minutes).toBeNull();
  });

  it("scales a simulation estimate with the electrode pairs and the subjects", async () => {
    const ti = { _type: "Montage", name: "m1", mode: "net", electrode_pairs: [["E1", "E2"], ["E3", "E4"]] };
    const mti = { ...ti, electrode_pairs: [...ti.electrode_pairs, ["E5", "E6"], ["E7", "E8"]] };
    const one = await planCost("sim", { subject_id: "ernie", montages: [ti] });
    const four = await planCost("sim", { subject_id: "ernie", montages: [mti] });
    const two = await planCost("sim", { subject_id: "ernie", montages: [ti] }, ["ernie", "101"]);
    expect(four.eta_minutes!).toBeGreaterThan(one.eta_minutes!);
    expect(two.eta_minutes!).toBeGreaterThan(one.eta_minutes!);
  });
});
