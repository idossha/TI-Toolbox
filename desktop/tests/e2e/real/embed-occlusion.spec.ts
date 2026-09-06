/**
 * **Can the Tetravox embed keep N1 and N2?** — the question the pane migration is gated on
 * (`dev/notes/v3-embed-convergence-plan.md` §3, lane M step 2).
 *
 * N1: *a marker behind the scalp is occluded by the scalp.* N2: *a marker that names a point
 * INSIDE the head is not occluded.* Both are defects the maintainer reported and lane N1 fixed in
 * `src/renderer/scene/`, and the plan says in as many words that if protocol 2 cannot express
 * them the migration is blocked on the protocol rather than on the pane. So this measures it,
 * against the **real** protocol-2 bundle the container serves and the **real** skin surface
 * `tit.scene` builds — no fixture, no mock, no renderer of ours involved at all.
 *
 * The method needs no colour model and no projection matrix, which is what makes it portable
 * between two renderers that share nothing: the same scene is screenshotted with the points layer
 * hidden and with exactly one point in it, and *a point is drawn iff those two pictures differ*.
 * A near point must change pixels; a far one must not. It is the same shape of proof as
 * `tests/e2e/scene.spec.ts`'s "an electrode on the far side of the head is hidden by the scalp",
 * ported rather than re-derived.
 *
 * Run:
 *   TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
 *     bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
 *     tests/e2e/real/embed-occlusion.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, launchElectronApp } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_SCENE_SUBJECT ?? "ernie";
const NET = process.env.TIT_E2E_SCENE_NET ?? "EEG10-10_UI_Jurak_2007.csv";

/** How different two screenshots must be before a point counts as "drawn". */
const DRAWN_PIXELS = 20;

interface Electrode {
  name: string;
  world: [number, number, number];
}

async function serverJson<T>(path: string): Promise<T> {
  const res = await fetch(`${SERVER_URL}${path}`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

/**
 * Everything the probe needs, evaluated in the page: an embed iframe, a scene, and one screenshot
 * per point-set. Returned as counts of differing pixels against the no-points baseline.
 */
async function measure(
  page: Page,
  args: {
    origin: string;
    surfaceUrl: string;
    opacity: number;
    probes: { label: string; point: { id: string; position: [number, number, number] } | null }[];
    preset: string;
  },
): Promise<{ ready: { tvx: unknown; version: unknown; webgl2: unknown }; layers: string[]; diffs: Record<string, number> }> {
  return page.evaluate(async (a) => {
    const iframe = document.createElement("iframe");
    iframe.setAttribute("sandbox", "allow-scripts allow-same-origin");
    iframe.style.cssText = "position:fixed;left:0;top:0;width:640px;height:480px;border:0;z-index:99999";
    const url = new URL("/tetravox/index.html", a.origin);
    url.searchParams.set("embed", "1");
    url.searchParams.set("hostOrigin", a.origin);
    iframe.src = url.href;
    document.body.appendChild(iframe);
    const EMBED_ORIGIN = new URL(iframe.src, location.href).origin;

    let n = 0;
    const pending = new Map<string, (m: Record<string, unknown>) => void>();
    const events: Record<string, unknown>[] = [];
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== EMBED_ORIGIN || event.source !== iframe.contentWindow) return;
      const m = event.data as Record<string, unknown>;
      if (!m || m["tvx"] !== 1) return;
      events.push(m);
      const id = m["id"];
      if (typeof id === "string" && pending.has(id)) {
        pending.get(id)!(m);
        pending.delete(id);
      }
    };
    window.addEventListener("message", onMessage);

    const send = (m: Record<string, unknown>, wantsReply = false): Promise<Record<string, unknown>> => {
      const id = wantsReply ? `h${n++}` : undefined;
      iframe.contentWindow!.postMessage({ tvx: 1, ...m, ...(id ? { id } : {}) }, EMBED_ORIGIN);
      if (!wantsReply) return Promise.resolve({});
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`no reply to ${String(m["type"])}`)), 60_000);
        pending.set(id!, (reply) => {
          clearTimeout(timer);
          resolve(reply);
        });
      });
    };

    /**
     * Send a message that is answered by an *event* rather than a reply, and wait for that event.
     *
     * `setPoints` is documented as "Reply: `layers`", but the `layers` event carries **no `id`** —
     * it is an announcement, not an answer — so a host that awaits it by correlation id waits for
     * ever. Measured against the real 0.4.0 bundle: `send({type:'setPoints'}, true)` never
     * resolves. Waiting for the next `layers` after the send is the honest handshake.
     */
    const sendAndSettle = async (m: Record<string, unknown>, type: string): Promise<void> => {
      const before = events.length;
      await send(m);
      const deadline = Date.now() + 20_000;
      for (;;) {
        if (events.slice(before).some((e) => e["type"] === type)) return;
        if (Date.now() > deadline) throw new Error(`no ${type} after ${String(m["type"])}`);
        await new Promise((r) => setTimeout(r, 25));
      }
    };

    const waitFor = (type: string, timeoutMs = 60_000): Promise<Record<string, unknown>> =>
      new Promise((resolve, reject) => {
        const hit = events.find((e) => e["type"] === type);
        if (hit) return resolve(hit);
        const started = Date.now();
        const tick = setInterval(() => {
          const found = events.find((e) => e["type"] === type);
          if (found) {
            clearInterval(tick);
            resolve(found);
          } else if (Date.now() - started > timeoutMs) {
            clearInterval(tick);
            reject(new Error(`no ${type} within ${timeoutMs} ms`));
          }
        }, 50);
      });

    const trace: string[] = [];
    const ready = await waitFor("ready", 30_000).catch((e) => {
      throw new Error(`no ready (${String(e)}); events so far: ${events.map((x) => String(x["type"])).join(",")}`);
    });
    trace.push("ready");

    const scene = {
      version: 2,
      background: [0, 0, 0, 1],
      datasets: [{ id: "d1", kind: "mesh", name: "skin", path: a.surfaceUrl }],
      layers: [
        {
          id: "l1",
          datasetId: "d1",
          kind: "mesh",
          name: "Skin",
          visible: true,
          opacity: a.opacity,
          colorMode: "solid",
          solidColor: [0.85, 0.72, 0.62, 1],
        },
        {
          id: "l2",
          datasetId: "d1",
          kind: "points",
          name: "Electrodes",
          visible: true,
          points: [],
          color: [0.2, 0.6, 1, 1],
          radiusMm: 5,
        },
      ],
      activeLayerId: "l1",
    };
    const loaded = await send({ type: "load", scene }, true).catch((e) => {
      throw new Error(`load: ${String(e)}; events: ${events.map((x) => String(x["type"]) + (x["type"] === "error" ? `(${String(x["message"])})` : "")).join(",")}`);
    });
    trace.push("loaded");
    if (loaded["type"] === "error") throw new Error(`load failed: ${String(loaded["message"])}`);
    const liveLayers = (loaded["layers"] as { id: string; kind: string }[]) ?? [];
    const meshLayer = liveLayers.find((l) => l.kind === "mesh")!.id;
    const pointsLayer = liveLayers.find((l) => l.kind === "points")!.id;

    await send({ type: "setLayout", kind: "3d" });
    await send({ type: "setCamera", preset: a.preset }, true);
    // One frame's grace after the layout/camera change, so the first screenshot is not of the
    // previous arrangement.
    await new Promise((r) => setTimeout(r, 300));

    const shoot = async (): Promise<ImageData> => {
      const reply = await send({ type: "screenshot", target: "grid", width: 640, height: 480 }, true);
      const img = new Image();
      img.src = String(reply["dataUrl"]);
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      return ctx.getImageData(0, 0, canvas.width, canvas.height);
    };

    const differing = (a1: ImageData, b1: ImageData): number => {
      let count = 0;
      for (let i = 0; i < a1.data.length; i += 4) {
        if (
          a1.data[i] !== b1.data[i] ||
          a1.data[i + 1] !== b1.data[i + 1] ||
          a1.data[i + 2] !== b1.data[i + 2]
        )
          count += 1;
      }
      return count;
    };

    await sendAndSettle({ type: "setPoints", layerId: pointsLayer, points: [] }, "layers");
    const baseline = await shoot();

    const diffs: Record<string, number> = {};
    for (const probe of a.probes) {
      await sendAndSettle(
        { type: "setPoints", layerId: pointsLayer, points: probe.point ? [probe.point] : [] },
        "layers",
      );
      diffs[probe.label] = differing(baseline, await shoot());
    }

    window.removeEventListener("message", onMessage);
    iframe.remove();
    return {
      ready: { tvx: ready["tvx"], version: ready["version"], webgl2: (ready["caps"] as { webgl2?: unknown })?.webgl2 },
      layers: [meshLayer, pointsLayer],
      diffs,
    };
  }, args);
}

test.setTimeout(300_000);

let app: ElectronApplication;
let page: Page;
let electrodes: Record<string, [number, number, number]>;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const body = await serverJson<{ electrodes: Electrode[] }>(
    `/api/scene/electrodes?subject=${SUBJECT}&net=${encodeURIComponent(NET)}`,
  );
  electrodes = Object.fromEntries(body.electrodes.map((e) => [e.name, e.world]));
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  await app?.close();
});

test("the embed reads the GIfTI surface tit.scene builds, over HTTP, with no decoder of ours", async () => {
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: `/api/scene/surface?subject=${SUBJECT}&part=skin&format=gii&wait=60`,
    opacity: 1,
    preset: "A",
    probes: [{ label: "none", point: null }],
  });
  // The bundle the container serves, from the host's own side.
  expect(result.ready.tvx).toBe(1);
  expect(Number(result.ready.version)).toBeGreaterThanOrEqual(2);
  expect(result.ready.webgl2).toBe(true);
  // `load` answered `loaded` with live ids, which only happens once the dataset parsed. A GIfTI
  // the engine could not read is an `error` reply, and `measure` throws on it.
  expect(result.layers).toHaveLength(2);
  console.log(`[embed-occlusion] ready=${JSON.stringify(result.ready)} diffs=${JSON.stringify(result.diffs)}`);
  // The baseline against itself: two screenshots of one unchanged scene are the same picture, so
  // a non-zero diff below is the point and not the renderer breathing.
  expect(result.diffs["none"]).toBe(0);
});

test("N1: over an OPAQUE scalp, an electrode on the far side of the head draws nothing", async () => {
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: `/api/scene/surface?subject=${SUBJECT}&part=skin&format=gii&wait=60`,
    opacity: 1,
    preset: "A", // eye anterior: Fpz is the near pole, Oz the far one
    probes: [
      { label: "near", point: { id: "Fpz", position: electrodes["Fpz"]! } },
      { label: "far", point: { id: "Oz", position: electrodes["Oz"]! } },
    ],
  });
  console.log(`[embed-occlusion] opaque scalp: ${JSON.stringify(result.diffs)}`);
  expect(
    result.diffs["near"],
    "an electrode on the near side of the scalp must be drawn",
  ).toBeGreaterThan(DRAWN_PIXELS);
  expect(
    result.diffs["far"],
    "an electrode behind the scalp must contribute nothing to the frame",
  ).toBe(0);
});

test("N2: a point INSIDE the head is drawn through a translucent surface", async () => {
  // The sphere centre of the Analyzer and the Optimizer is in the brain by construction, and
  // hiding it hides the only thing telling the user where they put it. The scene is the same one,
  // with the surface translucent — which is how the pane draws it in the sphere gesture.
  const centre: [number, number, number] = [0, 10, 20]; // deep in the head, whatever the view
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: `/api/scene/surface?subject=${SUBJECT}&part=skin&format=gii&wait=60`,
    opacity: 0.22,
    preset: "A",
    probes: [{ label: "centre", point: { id: "sphere-centre", position: centre } }],
  });
  console.log(`[embed-occlusion] translucent scalp, centre inside: ${JSON.stringify(result.diffs)}`);
  expect(
    result.diffs["centre"],
    "a marker inside the head must still be visible through a translucent surface",
  ).toBeGreaterThan(DRAWN_PIXELS);
});

test("the two rules are one switch: over a TRANSLUCENT scalp the far electrode is NOT hidden", async () => {
  // The negative control, and the finding that decides the pane's design: the engine draws points
  // in the opaque pass with depth writes on, and a translucent mesh draws in the transparent pass
  // with depth writes OFF. So occlusion is a property of the SURFACE's opacity, not of the point
  // layer — there is no per-layer "depth-test the markers" flag in protocol 2, and none is needed:
  // the pane picks the opacity per gesture, exactly where it picks `markersOccluded` today.
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: `/api/scene/surface?subject=${SUBJECT}&part=skin&format=gii&wait=60`,
    opacity: 0.22,
    preset: "A",
    probes: [{ label: "far", point: { id: "Oz", position: electrodes["Oz"]! } }],
  });
  console.log(`[embed-occlusion] translucent scalp, far electrode: ${JSON.stringify(result.diffs)}`);
  expect(
    result.diffs["far"],
    "this is the measurement N1 depends on: a translucent scalp hides nothing",
  ).toBeGreaterThan(DRAWN_PIXELS);
});
