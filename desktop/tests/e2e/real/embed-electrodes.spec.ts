/**
 * **Are the electrodes actually drawn as coloured dots, and is there really no ring?** — the real
 * half of plan `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-B (B1-B5), against the
 * **real** Tetravox embed the container serves, the **real** packaged guide skin surface and the
 * **real** electrode positions. No fixture, no fake, no renderer of ours.
 *
 * The mock e2e (`tests/e2e/scene-pane.spec.ts`) can only prove what the host *sent*: the fake
 * embed has no renderer. Everything downstream of `setPoints` — whether `shape: "dot"` is honoured
 * at all, whether a per-point `color` beats `stateColors`, whether the selected state adds a ring —
 * is a property of the engine, and the only honest way to check it is to read pixels back out.
 *
 * One of the three answers is **no**, and it is recorded as a measurement rather than hidden: the
 * 0.4.0 bundle honours `shape: "dot"` only in its 2-D slice pass, so in a `3d-only` pane the
 * electrodes are still millimetre spheres. The colours, the states, the labels and the absence of
 * a ring — everything else B1-B4 asks for — do hold on this bundle.
 *
 * Method, and why it needs no projection matrix of ours (the same trick as
 * `embed-occlusion.spec.ts`): the scene is screenshotted once with an empty points layer and once
 * with one point, and the pixels that differ *are* the dot. Their centroid is where it is; their
 * count is how big it is; the colour at the centroid is what colour it is; and the radial profile
 * of those pixels is where a selection ring would have to show up — as a non-zero band after a
 * zero one.
 *
 * Run:
 *   cd desktop
 *   VITE_SCENE_HOOKS=1 npx electron-vite build     # not needed by this spec, but see the RUNBOOK
 *   TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=devtoken TIT_E2E_OFFSCREEN=1 \
 *     bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
 *     tests/e2e/real/embed-electrodes.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, launchElectronApp } from "../_helpers";
import { SCENE_PALETTE } from "../../../src/renderer/pages/_shared/scene/model";
import { DOT_RADIUS_PX, channelColor } from "../../../src/renderer/pages/_shared/scene/embedScene";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const NET = process.env.TIT_E2E_SCENE_NET ?? "EEG10-10_UI_Jurak_2007.csv";

/** See the first test for how this number was measured. */
const TOLERANCE = 20;

/** 8-bit channel values for a `vec4` in 0..1 — what a screenshot pixel is compared against. */
function bytes(color: readonly number[]): [number, number, number] {
  return [Math.round((color[0] as number) * 255), Math.round((color[1] as number) * 255), Math.round((color[2] as number) * 255)];
}

/** sRGB byte distance, so a tolerance is one number rather than three. */
function distance(a: readonly number[], b: readonly number[]): number {
  return Math.max(Math.abs(a[0]! - b[0]!), Math.abs(a[1]! - b[1]!), Math.abs(a[2]! - b[2]!));
}

interface DotProbe {
  /** How many pixels this point changed against the empty-layer baseline. */
  pixels: number;
  /** Screen centroid of those pixels. */
  centre: [number, number] | null;
  /** The screenshot colour AT the centroid. */
  colorAtCentre: [number, number, number] | null;
  /**
   * Changed-pixel count per integer radius from the centroid, out to 60 px.
   *
   * Self-calibrating, which is what makes it portable across device pixel ratios: a solid disc
   * rises, falls, reaches zero and STAYS zero; a ring is a non-zero band after a zero one. No
   * assumption about how many screen pixels one `dotRadiusPx` is worth.
   */
  radial: number[];
  /** Bounding-box width/height of the changed pixels, in screenshot pixels. */
  extent: [number, number] | null;
}

interface Measurement {
  ready: { version: unknown; webgl2: unknown };
  probes: Record<string, DotProbe>;
}

/**
 * Load one real scene and probe a series of point-sets against the empty-layer baseline.
 *
 * `layerPatch` is merged into the points layer, so one call can compare `shape: "dot"` against
 * `shape: "sphere"` or one `dotRadiusPx` against another with everything else held fixed.
 */
async function measure(
  page: Page,
  args: {
    origin: string;
    surfaceUrl: string;
    layerPatch: Record<string, unknown>;
    probes: { label: string; points: Record<string, unknown>[] }[];
  },
): Promise<Measurement> {
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

    /** `setPoints` is answered by an id-less `layers` ANNOUNCEMENT, never a correlated reply — so
     *  the host must not await it. Waiting for the next `layers` is the honest handshake. */
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

    const ready = await waitFor("ready", 30_000);

    const scene = {
      version: 2,
      background: [0, 0, 0, 1],
      datasets: [{ id: "d1", kind: "mesh", name: "skin", path: a.surfaceUrl }],
      layers: [
        { id: "l1", datasetId: "d1", kind: "mesh", name: "Skin", visible: true, opacity: 1, colorMode: "solid", solidColor: [0.85, 0.72, 0.62, 1] },
        { id: "l2", datasetId: "d1", kind: "points", name: "Electrodes", visible: true, opacity: 1, pickable: true, points: [], ...a.layerPatch },
      ],
      activeLayerId: "l1",
    };
    const loaded = await send({ type: "load", scene }, true);
    if (loaded["type"] === "error") throw new Error(`load failed: ${String(loaded["message"])}`);
    const liveLayers = (loaded["layers"] as { id: string; kind: string }[]) ?? [];
    const pointsLayer = liveLayers.find((l) => l.kind === "points")!.id;

    await send({ type: "setLayout", kind: "3d" });
    // A named preset, so the projected position of an electrode is the same on every run.
    await send({ type: "setCamera", preset: "A" }, true);
    await new Promise((r) => setTimeout(r, 400));

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

    await sendAndSettle({ type: "setPoints", layerId: pointsLayer, points: [] }, "layers");
    const baseline = await shoot();

    const probes: Record<string, unknown> = {};
    for (const probe of a.probes) {
      await sendAndSettle({ type: "setPoints", layerId: pointsLayer, points: probe.points }, "layers");
      const shot = await shoot();
      const w = shot.width;
      let count = 0;
      let sx = 0;
      let sy = 0;
      let minX = w;
      let maxX = -1;
      let minY = shot.height;
      let maxY = -1;
      const changed = new Uint8Array(shot.width * shot.height);
      for (let i = 0; i < shot.data.length; i += 4) {
        if (shot.data[i] !== baseline.data[i] || shot.data[i + 1] !== baseline.data[i + 1] || shot.data[i + 2] !== baseline.data[i + 2]) {
          const p = i / 4;
          changed[p] = 1;
          const x = p % w;
          const y = Math.floor(p / w);
          count += 1;
          sx += x;
          sy += y;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
      let centre: [number, number] | null = null;
      let colorAtCentre: [number, number, number] | null = null;
      const radial = new Array<number>(60).fill(0);
      if (count > 0) {
        centre = [Math.round(sx / count), Math.round(sy / count)];
        const idx = (centre[1] * w + centre[0]) * 4;
        colorAtCentre = [shot.data[idx]!, shot.data[idx + 1]!, shot.data[idx + 2]!];
        for (let p = 0; p < changed.length; p += 1) {
          if (!changed[p]) continue;
          const d = Math.round(Math.hypot((p % w) - centre[0], Math.floor(p / w) - centre[1]));
          if (d < radial.length) radial[d] = (radial[d] as number) + 1;
        }
      }
      probes[probe.label] = {
        pixels: count,
        centre,
        colorAtCentre,
        radial,
        extent: count > 0 ? [maxX - minX + 1, maxY - minY + 1] : null,
      };
    }

    window.removeEventListener("message", onMessage);
    iframe.remove();
    return { ready: { version: ready["version"], webgl2: (ready["caps"] as { webgl2?: unknown })?.webgl2 }, probes } as unknown as Measurement;
  }, args);
}

test.setTimeout(300_000);

const GUIDE_SKIN = "/api/guide/surface?part=skin&format=gii";
/** Layer-level dot styling, exactly what `embedScene.ts` builds. */
const DOT_LAYER = {
  shape: "dot",
  dotRadiusPx: DOT_RADIUS_PX,
  color: [...SCENE_PALETTE.idle, 1],
  stateColors: { idle: [...SCENE_PALETTE.idle, 1], disabled: [...SCENE_PALETTE.disabled, 1] },
  labelMode: "none",
  offPlaneOpacity: 0.35,
};

let app: ElectronApplication;
let page: Page;
let electrodes: Record<string, [number, number, number]>;
/** The electrode nearest the camera under preset "A" — the one that must be drawn. */
const NEAR = "Fpz";

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const res = await fetch(`${SERVER_URL}/api/guide/electrodes?net=${encodeURIComponent(NET)}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  if (!res.ok) throw new Error(`GET /api/guide/electrodes -> ${res.status}`);
  const body = (await res.json()) as { electrodes: { name: string; world: [number, number, number] }[] };
  electrodes = Object.fromEntries(body.electrodes.map((e) => [e.name, e.world]));
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-dots-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  await app?.close();
});

test("an idle electrode is grey, and toggling it to selected repaints THAT marker in its channel's colour", async () => {
  const idle = { id: NEAR, position: electrodes[NEAR]!, state: "idle", color: [...SCENE_PALETTE.idle, 1] };
  const selected = { id: NEAR, name: NEAR, position: electrodes[NEAR]!, state: "selected", color: [...channelColor(0)] };
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: GUIDE_SKIN,
    layerPatch: DOT_LAYER,
    probes: [
      { label: "idle", points: [idle] },
      { label: "selected", points: [selected] },
      { label: "channel-2", points: [{ ...selected, color: [...channelColor(1)] }] },
    ],
  });
  console.log(`[embed-electrodes] ready=${JSON.stringify(result.ready)} probes=${JSON.stringify(result.probes)}`);
  expect(result.ready.webgl2).toBe(true);

  // Drawn at all.
  expect(result.probes["idle"]!.pixels, "an electrode on the near pole must be drawn").toBeGreaterThan(20);

  // Idle grey, at the dot's own centre.
  //
  // TOLERANCE, measured rather than guessed: the engine shades a dot by a constant factor of
  // ~0.935 (idle 158,166,179 -> 148,155,167; pair 1 0,114,178 -> 0,106,166; pair 2 230,159,0 ->
  // 215,149,0 — the same 0.935 in every channel of every probe), which is the layer's ambient
  // lighting term, not a colour the host chose. 20 covers that at full saturation and is still
  // far below the ~90 that separates any two channel hues.
  expect(distance(result.probes["idle"]!.colorAtCentre!, bytes(SCENE_PALETTE.idle))).toBeLessThanOrEqual(TOLERANCE);

  // Selected: the SAME id, the SAME position, a different colour — pair 1's.
  expect(distance(result.probes["selected"]!.colorAtCentre!, bytes(channelColor(0)))).toBeLessThanOrEqual(TOLERANCE);
  expect(result.probes["selected"]!.centre).toEqual(result.probes["idle"]!.centre);

  // A second channel is a second hue at the same place: this is what makes an mTI montage readable.
  expect(distance(result.probes["channel-2"]!.colorAtCentre!, bytes(channelColor(1)))).toBeLessThanOrEqual(TOLERANCE);
  expect(distance(result.probes["channel-2"]!.colorAtCentre!, result.probes["selected"]!.colorAtCentre!)).toBeGreaterThan(30);
});

test("selecting a dot adds NO ring: the changed pixels are one solid disc and nothing else", async () => {
  const result = await measure(page, {
    origin: SERVER_URL,
    surfaceUrl: GUIDE_SKIN,
    layerPatch: DOT_LAYER,
    probes: [
      { label: "idle", points: [{ id: NEAR, position: electrodes[NEAR]!, state: "idle", color: [...SCENE_PALETTE.idle, 1] }] },
      { label: "selected", points: [{ id: NEAR, name: NEAR, position: electrodes[NEAR]!, state: "selected", color: [...channelColor(0)] }] },
    ],
  });
  console.log(`[embed-electrodes] ring check: ${JSON.stringify(result.probes)}`);
  // The whole point of B2: the state is a COLOUR, and nothing is drawn outside the disc. A
  // `setPointSelection` ring lives at a larger radius than the dot with a gap between the two —
  // which is exactly a non-zero band after a zero one in the radial profile.
  const noRing = (radial: number[]): number => {
    const firstZero = radial.findIndex((n, r) => r > 0 && n === 0);
    if (firstZero < 0) return 0;
    return radial.slice(firstZero).reduce((a1, b1) => a1 + b1, 0);
  };
  expect(noRing(result.probes["idle"]!.radial), "an idle dot must not draw outside its disc").toBe(0);
  expect(noRing(result.probes["selected"]!.radial), "a SELECTED dot must not grow a ring either").toBe(0);
  // And the selected dot is not bigger than the idle one: the state changed the hue and nothing
  // else. (A one-pixel antialias difference is tolerated; a ring or a halo is not.)
  const idleExtent = result.probes["idle"]!.extent!;
  const selectedExtent = result.probes["selected"]!.extent!;
  expect(Math.abs(idleExtent[0] - selectedExtent[0])).toBeLessThanOrEqual(1);
  expect(Math.abs(idleExtent[1] - selectedExtent[1])).toBeLessThanOrEqual(1);
});

test("MEASUREMENT: embed 0.4.0 ignores `shape: \"dot\"` in the 3-D view — the dot pass is 2-D only", async () => {
  // This is a *measurement*, pinned as a test, not a feature check that happens to pass.
  //
  // Plan B1 asks for `shape: "dot"` with a pixel radius. The host sends exactly that. What the
  // engine does with it, read off the bundle the container serves
  // (`0.4.0/assets/index-CdUrh5CF.js`): `uDotPx` — the only consumer of `dotRadiusPx` — is set in
  // the `POINTS_2D` shader path, i.e. the SLICE views. The 3-D pass has no such uniform and draws
  // an instanced millimetre sphere. So in the pane, which is `layout: "3d-only"`, `dotRadiusPx` is
  // inert and the drawn size comes from `radiusMm`.
  //
  // Everything else B1-B4 asks for survives that: the colour, the state, the labels and the
  // absence of a ring are all engine-independent (the two tests above measure them on this same
  // bundle). Only the *shape* is deferred, and the fix is the TX lane's — which is why this is
  // written to FAIL the day it lands, rather than being quietly dropped.
  const point = { id: NEAR, position: electrodes[NEAR]!, state: "idle", color: [...SCENE_PALETTE.idle, 1] };
  const probe = async (patch: Record<string, unknown>) =>
    (await measure(page, { origin: SERVER_URL, surfaceUrl: GUIDE_SKIN, layerPatch: { ...DOT_LAYER, ...patch }, probes: [{ label: "p", points: [point] }] })).probes["p"]!;

  const r5 = await probe({ dotRadiusPx: 5 });
  const r15 = await probe({ dotRadiusPx: 15 });
  const sphereSmall = await probe({ shape: "sphere", radiusMm: 4 });
  const sphereLarge = await probe({ shape: "sphere", radiusMm: 12 });
  console.log(
    `[embed-electrodes] dotRadiusPx 5 -> ${r5.pixels}px ${JSON.stringify(r5.extent)}; 15 -> ${r15.pixels}px ${JSON.stringify(r15.extent)}; ` +
      `sphere radiusMm 4 -> ${sphereSmall.pixels}px; 12 -> ${sphereLarge.pixels}px`,
  );

  // The measurement, stated three ways.
  expect(r15.pixels, "dotRadiusPx changes nothing in the 3-D view (0.4.0)").toBe(r5.pixels);
  expect(r5.pixels, "…and a `dot` is exactly the millimetre sphere of the same layer").toBe(sphereSmall.pixels);
  expect(sphereLarge.pixels / sphereSmall.pixels, "radiusMm IS what drives the drawn size today").toBeGreaterThan(3);

  // The layer keeps `radiusMm: 4`, so this deferral costs nothing visually: the electrodes are the
  // size they have always been, and only their colour changed.
  expect(r5.extent![0]).toBeLessThan(30);
});
