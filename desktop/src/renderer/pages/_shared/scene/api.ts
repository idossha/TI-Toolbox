/**
 * The six `GET /api/scene/*` fetchers (plan of record `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §2.1, built
 * by lane SCA) and the polling rule a cold cache needs.
 *
 * The **shapes below are the contract's**, read out of the generated `api/schema.d.ts` (`npm run
 * gen:api` ← `contracts/openapi.v1.json` ← `contracts/openapi.v1.yaml`) rather than hand-written
 * a second time. Lane SCC typed them by hand because the six paths were not in the generated
 * `paths` map yet and regenerating a file several lanes share was not its change to make
 * (`docs/dev/HISTORY.md § 2026-09-04 (scene service)` §6.7); they are generated now. *Failure it prevents:* a
 * hand-typed `built_ms: number` or `world: [number, number, number]` says the server always sends
 * something it does not, and nothing fails until the value is missing at runtime. What the routes
 * really answer with is pinned on the Python side by
 * `tests/test_scene_routes.py::test_every_scene_json_response_matches_the_contract_schema`, so
 * these types and the server cannot drift apart silently.
 *
 * The transport stays plain `fetch` with `credentials: "same-origin"` rather than
 * `api/client.ts`'s `openapi-fetch` client — the pattern `pages/_shared/run/logCatalog.ts`
 * already uses — because of the two rules below, which a client that throws on every non-2xx
 * cannot express. It is the same session cookie either way.
 *
 * Two rules, each with the failure it prevents:
 *
 *  - **A `202` is normal, not an error.** A cold cache answers 202 + `Retry-After: 1` with a body
 *    that says `cache.state === "building"`; the pane shows "Building…" and polls. A fetcher that
 *    threw on a non-2xx would turn the first visit to a subject into an error box.
 *  - **A `404` is a *readable state*, not a crash.** A subject with no head model, or an atlas the
 *    subject does not have, answers 404 with a sentence naming what is missing. That sentence is
 *    what the pane shows, so the user is told which file is absent instead of "failed to load".
 */
import { parseTvsc1, type Tvsc1 } from "../../../scene/tvsc";
import type { paths } from "../../../api/schema";

/** The JSON body one scene operation answers 200 with, as the contract declares it. */
type SceneBody<P extends keyof paths> = paths[P] extends {
  get: { responses: { 200: { content: { "application/json": infer B } } } };
}
  ? B
  : never;

type ManifestBody = SceneBody<"/api/scene/manifest">;
type RegionsBody = SceneBody<"/api/scene/regions">;
type ElectrodesBody = SceneBody<"/api/scene/electrodes">;

/** One surface part of the manifest (`parts[]`). */
export type SceneManifestPart = ManifestBody["parts"][number];
export type SceneManifestNet = ManifestBody["nets"][number];
export type SceneManifestAtlas = ManifestBody["atlases"][number];
export type SceneManifestVolume = ManifestBody["volumes"][number];

export interface SceneManifest extends ManifestBody {
  /** `true` when this body came back with HTTP 202 — the caller polls rather than draws. */
  building: boolean;
}

/**
 * One legend row of `GET /api/scene/regions`.
 *
 * `label` is the `uint16` value in the payload; `id` is the `.annot` row index — the integer
 * `FlexConfig.AtlasROI.label` and `GET /api/catalog/atlases/regions` both use — and `hemi`
 * disambiguates it, because lh row 5 and rh row 5 are different regions. Keeping both is what lets
 * a pick in the pane become a region in the form and back (measured against the live container:
 * `/api/catalog/atlases/regions?subject=ernie&atlas=DK40&hemi=lh` returns
 * `{id: 1, name: "bankssts", hemi: "lh"}` and the scene legend's first row is
 * `{label: 1, id: 1, hemi: "lh", name: "bankssts"}`).
 */
export type SceneLegendRow = RegionsBody["legend"][number];

export interface SceneRegions extends RegionsBody {
  building: boolean;
}

export type SceneElectrode = ElectrodesBody["electrodes"][number];
export type SceneElectrodes = ElectrodesBody;

/**
 * A scene request that failed in a way the user can act on. `status` is the HTTP code and
 * `message` is the server's own `detail` sentence ("ernie has no cortical atlas 'Foo'; available:
 * DK40, HCP_MMP1, a2009s") — printed verbatim by the pane rather than replaced with a generic one.
 */
export class SceneError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "SceneError";
  }
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    /* not JSON, or empty */
  }
  return `${res.url} failed with HTTP ${res.status}`;
}

async function getJson<T>(url: string): Promise<{ body: T; building: boolean }> {
  const res = await fetch(url, { credentials: "same-origin", headers: { accept: "application/json" } });
  if (res.status === 202) return { body: (await res.json()) as T, building: true };
  if (!res.ok) throw new SceneError(res.status, await detailOf(res));
  return { body: (await res.json()) as T, building: false };
}

const q = (value: string): string => encodeURIComponent(value);

export async function getSceneManifest(subject: string): Promise<SceneManifest> {
  const { body, building } = await getJson<Omit<SceneManifest, "building">>(`/api/scene/manifest?subject=${q(subject)}`);
  return { ...body, building };
}

export async function getSceneRegions(subject: string, atlas: string): Promise<SceneRegions> {
  const { body, building } = await getJson<Omit<SceneRegions, "building">>(
    `/api/scene/regions?subject=${q(subject)}&atlas=${q(atlas)}`,
  );
  return { ...body, building };
}

export async function getSceneElectrodes(subject: string, net: string): Promise<SceneElectrodes> {
  const { body } = await getJson<SceneElectrodes>(`/api/scene/electrodes?subject=${q(subject)}&net=${q(net)}`);
  return body;
}

export function surfaceUrl(subject: string, part: string): string {
  return `/api/scene/surface?subject=${q(subject)}&part=${part}`;
}

export function labelsUrl(subject: string, atlas: string): string {
  return `/api/scene/labels?subject=${q(subject)}&atlas=${q(atlas)}`;
}

// ------------------------------------------------------------------------------------- the guide

/**
 * The **fixed guide scene** (`docs/dev/v3-implementation-plan.md` R4): one immutable head, packaged
 * with the installation, that the three run panes draw instead of the first selected research
 * subject.
 *
 * Why the pane stopped drawing the subject, each with the failure it prevents:
 *
 *  - a fresh project has no head model, so the pane's only content was "run charm first";
 *  - ticking a second subject started a cache-cold extraction of a 184 MB mesh;
 *  - and a click on one subject's anatomy could write a subject-RAS millimetre coordinate into a
 *    configuration that runs on a *different* subject — wrong in a way nothing downstream can
 *    detect. The guide's own `space` says `guide-ras`, and the pane refuses to write a coordinate
 *    from it at all.
 *
 * The bodies are shaped like the scene's on purpose (`parts`, `nets`, `atlases`, `bbox`,
 * `focus_bbox`), so one pane component and one ViewSpec builder consume either. The types come
 * from the generated `api/schema.d.ts`, not from a second hand-written copy.
 */
type GuideManifestBody = SceneBody<"/api/guide/manifest">;
type GuideRegionsBody = SceneBody<"/api/guide/regions">;
type GuideElectrodesBody = SceneBody<"/api/guide/electrodes">;

export type GuideManifest = GuideManifestBody;
export type GuideRegions = GuideRegionsBody;
export type GuideElectrodes = GuideElectrodesBody;

/** The guide is never "building": it ships built. Kept so `<ScenePane>` reads one shape. */
export type GuideManifestPart = GuideManifestBody["parts"][number];

export async function getGuideManifest(): Promise<GuideManifest> {
  const { body } = await getJson<GuideManifest>("/api/guide/manifest");
  return body;
}

export async function getGuideRegions(atlas: string): Promise<GuideRegions> {
  const { body } = await getJson<GuideRegions>(`/api/guide/regions?atlas=${q(atlas)}`);
  return body;
}

export async function getGuideElectrodes(net: string): Promise<GuideElectrodes> {
  const { body } = await getJson<GuideElectrodes>(`/api/guide/electrodes?net=${q(net)}`);
  return body;
}

/**
 * A `TVSC1` payload — a guide surface, or the per-vertex labels aligned to `gm`.
 *
 * Binary, not JSON: 145 402 triangles as JSON numbers is ~9 MB of text to parse on the main
 * thread. `parseTvsc1` is the independent reader the Python encoder is tested against
 * (`tests/test_scene_tvsc.py` writes the fixture `scene-tvsc.test.ts` reads), so a change to
 * either end fails a test rather than drawing a scrambled head.
 */
export async function getGuideTvsc(url: string): Promise<Tvsc1 | null> {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new SceneError(res.status, await detailOf(res));
  return parseTvsc1(await res.arrayBuffer());
}

export function guideSurfaceUrl(part: string): string {
  return `/api/guide/surface?part=${q(part)}&format=tvsc`;
}

export function guideLabelsUrl(atlas: string): string {
  return `/api/guide/labels?atlas=${q(atlas)}&format=tvsc`;
}

export type { Tvsc1 };
