/**
 * **Tetravox embed protocol** — the host half of the contract in the tetravox repo's
 * `docs/EMBED.md`.
 *
 * SOURCE OF TRUTH, copied here rather than imported:
 *
 *   repo    /Users/idohaber/00_development/tetravox-wt-embed-p2
 *   file    packages/embed/src/protocol.ts
 *   commit  dd9c06a   ("feat(embed): host protocol 2 — a points layer, the point tool, pick and
 *           the camera", 2026-09-04)
 *
 * TI-Toolbox integrates with Tetravox as a *service*, not as a dependency
 * (`docs/dev/HISTORY.md § 2026-09-02 (UX redesign)` D1/D3): the embed is a directory in the container image and
 * this repo carries no Tetravox source. So the message interfaces below are a verbatim copy of
 * that file's, with exactly two mechanical deviations, both forced by the un-vendoring and both
 * marked `TI DEVIATION` where they occur:
 *
 *  1. the upstream file's `import type { Layer, LayoutKind, ProbeResult, ViewSpec, vec3 } from
 *     '@tetravox/engine'` is replaced by the local structural declarations in §0. Nothing here may
 *     import `@tetravox/*`.
 *  2. the guards are the HOST's half: upstream's `isHostMessage`/`acceptMessage` validate what an
 *     *embed* receives; this file keeps `isEmbedMessage` (upstream's, verbatim) and adds
 *     `acceptEmbedMessage`, the mirror `docs/EMBED.md` §3 tells every host to write.
 *
 * The `tvx` envelope is still 1 for protocol-2 bundles: additive feature levels move through
 * `ready.version` and `/tetravox/manifest.json.protocol`, not this wire discriminator. When the
 * embed ships a new feature level, re-copy the additive interfaces and update the commit above.
 */

// ------------------------------------------------------------------------------------------------
// §0. TI DEVIATION — the `@tetravox/engine` types this protocol references, declared structurally.
// ------------------------------------------------------------------------------------------------

/** World-RAS millimetres. Upstream: `@tetravox/engine`'s `vec3`. */
export type vec3 = [number, number, number];
/** 0..1 RGBA. Upstream: `@tetravox/engine`'s `vec4`. */
export type vec4 = [number, number, number, number];

/** Upstream `LayoutKind`, plus the documented single-pane aliases accepted by protocol 2. */
export type LayoutKind = "1x1" | "1x3" | "1x3-horizontal" | "2x2" | "3d-only" | "1+3" | "3d+1" | "3d" | "axial" | "coronal" | "sagittal";

/** §7.5's camera presets: anterior, posterior, left, right, superior, inferior. */
export type CameraPreset = 1 | 2 | 3 | 4 | 5 | 6 | "A" | "P" | "L" | "R" | "S" | "I";

/** The 3-D camera fields a host may read and patch. */
export interface Camera3D {
  target: vec3;
  distance: number;
  rotation: vec4;
  fovYDeg?: number;
  orthographic?: boolean;
  near?: number;
  far?: number;
  [key: string]: unknown;
}

/**
 * A layer as the HOST reads one.
 *
 * The engine's `Layer` is a discriminated union over volume/mesh/points/iso kinds with ~40 fields
 * between them, and reproducing it here would be exactly the "copy of Tetravox in the TI repo"
 * that D3 removed. The host renders a name, a checkbox, a slider and a colormap label, so those
 * are typed and everything else stays reachable through the index signature — which is also what
 * keeps this forward-compatible with an embed that adds fields (the protocol is additive-only).
 */
export interface EmbedLayer {
  id: string;
  name?: string;
  kind?: string;
  visible?: boolean;
  opacity?: number;
  colormap?: string;
  [key: string]: unknown;
}

/** One row of a probe answer. Upstream `ProbeRow`, narrowed to the fields a host renders. */
export interface ProbeRow {
  layerId: string;
  layerName?: string;
  kind?: string;
  value?: number | vec3;
  labelId?: number;
  labelName?: string;
  elementId?: number;
  tag?: number;
  tagName?: string;
  fields?: { name: string; value: number | number[] }[];
  [key: string]: unknown;
}

/** Upstream `ProbeResult`, narrowed the same way. */
export interface ProbeResult {
  world: vec3;
  mni?: vec3;
  rows: ProbeRow[];
  [key: string]: unknown;
}

// ------------------------------------------------------------------------------------------------
// Envelope (upstream, verbatim)
// ------------------------------------------------------------------------------------------------

/** The value of the `tvx` envelope field. Bumped only by a breaking change. */
export const PROTOCOL_VERSION = 1;

/** The query parameter that puts the renderer in embed mode, and the one that names the host. */
export const EMBED_PARAM = "embed";
export const HOST_ORIGIN_PARAM = "hostOrigin";

/** Every message carries these. `id` is present on a request that wants a reply, and on its reply. */
export interface Envelope {
  tvx: typeof PROTOCOL_VERSION;
  type: string;
  id?: string;
}

// ------------------------------------------------------------------------------------------------
// Host → embed
// ------------------------------------------------------------------------------------------------

/**
 * "Are you there?" — answered with {@link ReadyMessage}.
 *
 * The embed also posts `ready` **unprompted** the moment it boots, so a host that mounted the
 * iframe and started listening before `load` fires never has to poll. `hello` exists for the other
 * order: a host that attached its listener late, or one re-attaching after its own re-render, can
 * ask instead of waiting for an event that already went past.
 */
export interface HelloMessage extends Envelope {
  type: "hello";
}

/**
 * Replace the scene with `scene` (a `ViewSpec`, version 2).
 *
 * **Dataset refs are URLs.** `DatasetRef.path` may be an absolute `http(s)://` URL, which is used
 * as-is, or a relative or root-relative one (`data/T1.nii.gz`, `/api/files/raw/T1.nii.gz`), which
 * is resolved against `baseUrl` — and `baseUrl` itself defaults to the embed document's own
 * `baseURI`, so a host serving data from its own origin can send exactly the paths its server
 * publishes and send no `baseUrl` at all.
 *
 * `fingerprint` may be `''` or absent — see {@link EmbedDatasetRef}.
 *
 * The reply is {@link LoadedMessage} carrying this message's `id`, or {@link ErrorMessage}.
 */
export interface LoadMessage extends Envelope {
  type: "load";
  scene: EmbedViewSpec;
  baseUrl?: string;
}

export interface SetThemeMessage extends Envelope {
  type: "setTheme";
  theme: "light" | "dark";
}

export interface SetLayoutMessage extends Envelope {
  type: "setLayout";
  kind: LayoutKind;
}

/** Move the crosshair to a world-RAS millimetre triple. Emits {@link CursorMessage}. */
export interface SetCursorMessage extends Envelope {
  type: "setCursor";
  world: vec3;
}

export interface SetLayerVisibleMessage extends Envelope {
  type: "setLayerVisible";
  layerId: string;
  visible: boolean;
}

export interface SetLayerOpacityMessage extends Envelope {
  type: "setLayerOpacity";
  layerId: string;
  /** Clamped to `[0, 1]`. */
  opacity: number;
}

/**
 * Patch any layer field — colormap, scale, threshold, clip planes, field selection, tag styles,
 * contour flags. The patch is handed to `Engine.updateLayer` unchanged.
 *
 * Deliberately untyped as `Record<string, unknown>` rather than `Partial<Layer>`: the host is
 * another process and its patch has been through JSON, so it is data to be validated by the engine
 * that owns the field, not a value this file can promise the shape of.
 */
export interface UpdateLayerMessage extends Envelope {
  type: "updateLayer";
  layerId: string;
  patch: Record<string, unknown>;
}

export interface SetActiveLayerMessage extends Envelope {
  type: "setActiveLayer";
  layerId: string | null;
}

/**
 * Capture a PNG. The reply is {@link ScreenshotReplyMessage} carrying `id` and a `data:` URL.
 *
 * `id` is **required** here, unlike on most messages: a screenshot is worth several megabytes of
 * base64 and there is no point posting one nobody asked to correlate.
 */
export interface ScreenshotMessage extends Envelope {
  type: "screenshot";
  id: string;
  /** Default `'grid'` — the whole view grid, which is what a host asking for "a picture" means. */
  target?: "view" | "grid";
  /** Required when `target` is `'view'`; ignored otherwise. */
  viewId?: string;
  width?: number;
  height?: number;
}

/** Ask for the live scene as a `ViewSpec`. The reply is {@link SceneMessage}. */
export interface SerializeMessage extends Envelope {
  type: "serialize";
  id: string;
}

/** Probe every layer at a world point without moving the cursor. Reply: {@link ProbeReplyMessage}. */
export interface ProbeMessage extends Envelope {
  type: "probe";
  id: string;
  world: vec3;
}

/**
 * Give the viewer keyboard focus.
 *
 * An iframe does not receive key events until something inside it is focused, and a host that has
 * just shown the frame has no way to focus across the boundary.
 */
export interface FocusMessage extends Envelope {
  type: "focus";
}

/**
 * Unload everything: every dataset closed, every worker terminated, an empty scene.
 *
 * `worker.terminate()` is the only way a dataset's wasm heap comes back, so this is the message a
 * host sends when it navigates away from the viewer but keeps the iframe mounted. Emits
 * `status: 'idle'` and an empty {@link LayersMessage}.
 */
export interface ResetMessage extends Envelope {
  type: "reset";
}

// ------------------------------------------------------------------------------------------------
// Protocol 2 (2026-09-04) — points, pick events and the camera. Appended and optional.
// ------------------------------------------------------------------------------------------------

export interface SetPointToolMessage extends Envelope {
  type: "setPointTool";
  layerId: string | null;
  mode?: "select" | "place";
  template?: { color?: vec4; radiusMm?: number; group?: string };
}

export interface SetPointSelectionMessage extends Envelope {
  type: "setPointSelection";
  layerId: string;
  pointId: string | null;
}

export interface SetPointsMessage extends Envelope {
  type: "setPoints";
  layerId: string;
  points: EmbedPoint[];
}

export interface SetPickEventsMessage extends Envelope {
  type: "setPickEvents";
  enabled: boolean;
}

export interface GetCameraMessage extends Envelope {
  type: "getCamera";
  id: string;
}

export interface SetCameraMessage extends Envelope {
  type: "setCamera";
  preset?: CameraPreset;
  patch?: Partial<Camera3D>;
}

export type HostMessage =
  | HelloMessage
  | LoadMessage
  | SetThemeMessage
  | SetLayoutMessage
  | SetCursorMessage
  | SetLayerVisibleMessage
  | SetLayerOpacityMessage
  | UpdateLayerMessage
  | SetActiveLayerMessage
  | ScreenshotMessage
  | SerializeMessage
  | ProbeMessage
  | FocusMessage
  | ResetMessage
  | SetPointToolMessage
  | SetPointSelectionMessage
  | SetPointsMessage
  | SetPickEventsMessage
  | GetCameraMessage
  | SetCameraMessage;

/**
 * One host message minus the envelope fields the channel fills in.
 *
 * Distributive on purpose: a bare `Omit<HostMessage, "tvx">` over a union keeps only the keys
 * every member shares (`type`, `id`), so `{ type: "load", scene }` would not type-check against
 * it. `M extends HostMessage ? … : never` distributes the `Omit` across the members instead.
 */
export type HostPayload = HostMessage extends infer M ? (M extends HostMessage ? Omit<M, "tvx"> : never) : never;

/** The same, for a request whose correlation id the channel assigns. */
export type HostRequest = HostMessage extends infer M ? (M extends HostMessage ? Omit<M, "tvx" | "id"> : never) : never;

/** Every `type` a host may send. The runtime half of the {@link HostMessage} union. */
export const HOST_MESSAGE_TYPES = [
  "hello",
  "load",
  "setTheme",
  "setLayout",
  "setCursor",
  "setLayerVisible",
  "setLayerOpacity",
  "updateLayer",
  "setActiveLayer",
  "screenshot",
  "serialize",
  "probe",
  "focus",
  "reset",
  "setPointTool",
  "setPointSelection",
  "setPoints",
  "setPickEvents",
  "getCamera",
  "setCamera",
] as const satisfies readonly HostMessage["type"][];

// ------------------------------------------------------------------------------------------------
// Embed → host
// ------------------------------------------------------------------------------------------------

/**
 * What this embed can do. Posted **unprompted on boot** and again in reply to every `hello`.
 *
 * `caps.webgl2` is the one a host must branch on: Chromium M137 removed the automatic SwiftShader
 * fallback, so a blocklisted driver gives `getContext('webgl2') === null` and the viewer can render
 * nothing at all. A host that ignores this shows its user an empty box.
 *
 * TI DEVIATION: upstream types `version` as `typeof PROTOCOL_VERSION`. It is widened to
 * `number | string` here because the e2e fake embed
 * (`desktop/tests/e2e/fixtures/fake-embed/index.html`, owned by lane W3a) posts
 * `version: "fake"`, and a host that rejected it would be testing the double rather than the
 * contract. Nothing in this host branches on the value; see w5-viewer-notes.md.
 */
export interface ReadyMessage extends Envelope {
  type: "ready";
  version: number | string;
  caps: {
    webgl2: boolean;
    /** `Capabilities.renderer` — the unmasked GL renderer string, absent without a context. */
    renderer?: string;
    /** `EXT_texture_norm16`. Absent without a context. */
    norm16?: boolean;
  };
}

/**
 * The viewer's coarse state.
 *
 * `'no-webgl2'` is terminal for the life of the page — nothing a host sends will make a context
 * appear — and is the state to show an error in. `'error'` is per-operation and recoverable: the
 * next successful `load` returns to `'ready'`.
 */
export interface StatusMessage extends Envelope {
  type: "status";
  phase: "idle" | "loading" | "ready" | "error" | "no-webgl2";
  message?: string;
}

/**
 * Per-dataset load progress, mirrored from the engine's own `progress` event.
 *
 * `done`/`total` are bytes where the phase knows a size and units of work where it does not, and
 * `total` is `0` for a phase that cannot say — a determinate bar must therefore check it.
 */
export interface ProgressMessage extends Envelope {
  type: "progress";
  datasetId: string;
  name: string;
  phase: string;
  done: number;
  total: number;
}

/** One entry per dataset the load actually opened. */
export interface LoadedDataset {
  id: string;
  name: string;
  kind: "volume" | "mesh";
  bytes?: number;
}

/**
 * A `load` finished. Carries the request's `id`.
 *
 * **The ids are not the ids the host sent.** `Engine.load` re-adds every dataset, so the spec's
 * `DatasetId`s and `LayerId`s are gone the moment the load succeeds and the live ones here are what
 * every later `setLayerVisible` / `updateLayer` / `setActiveLayer` must name. That is the reason
 * this message carries the whole layer array rather than an "ok".
 *
 * TI DEVIATION: `datasets` is widened to accept a bare id string per entry. The fake embed posts
 * `datasets: ["ds0", …]`; {@link normalizeLoadedDatasets} folds both shapes into `LoadedDataset[]`.
 */
export interface LoadedMessage extends Envelope {
  type: "loaded";
  datasets: (LoadedDataset | string)[];
  layers: (EmbedLayer | string)[];
}

/** The layer array changed, for any reason — a load, a patch, a user click in the layer panel. */
export interface LayersMessage extends Envelope {
  type: "layers";
  layers: EmbedLayer[];
}

/**
 * The crosshair moved — by a click in a pane, a key, or the host's own `setCursor`.
 *
 * Throttled to 30 Hz upstream. A drag across a pane moves the cursor once per frame, and a host
 * that re-renders on every one of those is a host that drops frames inside the viewer.
 *
 * TI DEVIATION: `space` is optional here (upstream requires it) — the fake embed echoes only
 * `world`, and the host already knows the scene's space from the server.
 */
export interface CursorMessage extends Envelope {
  type: "cursor";
  world: vec3;
  /** Present only when some volume carries the corresponding transform. */
  mni?: vec3;
  tkr?: vec3;
  /** Which space the coordinate bar is currently showing, as its stable key. */
  space?: string;
}

/** The reply to {@link ProbeMessage}: one row per layer that had something to say at that point. */
export interface ProbeReplyMessage extends Envelope {
  type: "probe";
  id: string;
  result: ProbeResult;
}

export interface ScreenshotReplyMessage extends Envelope {
  type: "screenshot";
  id: string;
  /** `data:image/png;base64,…`. */
  dataUrl: string;
}

/** The reply to {@link SerializeMessage}: `Engine.serialize()`, whose refs are the loaded URLs. */
export interface SceneMessage extends Envelope {
  type: "scene";
  id: string;
  spec: EmbedViewSpec;
}

/**
 * Something failed. Carries the `id` of the request that failed, when there was one.
 *
 * `code` is the engine's own error code where one exists (`parse`, `io`, `oom`, `cancelled`) and
 * absent otherwise; `message` is always present and always human-readable. A host should show
 * `message` and branch on `code`, never the other way round.
 */
export interface ErrorMessage extends Envelope {
  type: "error";
  code?: string;
  message: string;
}

// ------------------------------------------------------------------------------------------------
// Protocol 2 (2026-09-04) — opt-in events and camera replies.
// ------------------------------------------------------------------------------------------------

export interface PickMessage extends Envelope {
  type: "pick";
  kind: "point" | "tri" | "tet" | "slice" | "cursor";
  world: vec3;
  viewId?: string;
  layerId?: string;
  pointId?: string;
  elementId?: number;
  label?: { id: number; name?: string; layerId: string };
  tag?: { id: number; name?: string; layerId: string };
  modifiers: { shift: boolean; ctrl: boolean; alt: boolean; meta: boolean };
  probe: ProbeResult;
}

export interface PointToolMessage extends Envelope {
  type: "pointTool";
  event: Record<string, unknown>;
}

export interface CameraMessage extends Envelope {
  type: "camera";
  camera: Camera3D;
}

export type EmbedMessage =
  | ReadyMessage
  | StatusMessage
  | ProgressMessage
  | LoadedMessage
  | LayersMessage
  | CursorMessage
  | ProbeReplyMessage
  | ScreenshotReplyMessage
  | SceneMessage
  | ErrorMessage
  | PickMessage
  | PointToolMessage
  | CameraMessage;

/** Every `type` an embed may send. The runtime half of the {@link EmbedMessage} union. */
export const EMBED_MESSAGE_TYPES = [
  "ready",
  "status",
  "progress",
  "loaded",
  "layers",
  "cursor",
  "probe",
  "screenshot",
  "scene",
  "error",
  "pick",
  "pointTool",
  "camera",
] as const satisfies readonly EmbedMessage["type"][];

// ------------------------------------------------------------------------------------------------
// The host-facing ViewSpec subset
// ------------------------------------------------------------------------------------------------

/**
 * A `DatasetRef` as a **host** can write one.
 *
 * Two fields of the real `DatasetRef` are optional here, and both for the same reason — a host
 * cannot know them: `fingerprint` is computed in the worker that read the file's bytes, and
 * `absPath` is a filesystem path an embed does not have.
 *
 * What `tit.server` actually emits (`tit/viewspec.py::to_tetravox_viewspec`, contract in
 * `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)`) sets **both** `path` and `absPath` to the
 * same origin-relative `/api/files/raw/<path>` string, and `fingerprint` to `""`.
 */
export interface EmbedDatasetRef {
  id: string;
  kind: "volume" | "mesh";
  name: string;
  /** Absolute `http(s)://`, or relative/root-relative — resolved against `LoadMessage.baseUrl`. */
  path: string;
  absPath?: string;
  fingerprint?: string;
  /** `path` is resolved against **the dataset's own URL**: a sidecar travels with it. */
  sidecars?: {
    lut?: { path: string; absPath?: string };
    opt?: { path: string; absPath?: string };
  };
}

/** One inline point of a protocol-2 points layer. */
export interface EmbedPoint {
  id?: string;
  position: vec3;
  name?: string;
  state?: "idle" | "selected" | "disabled";
  /**
   * An explicit colour **wins over `stateColors`**, and an `idle` point is never state-coloured
   * at all: embed 0.4.0 normalises a point with
   * `if (state === undefined || state === "idle" || color !== undefined) return point;`
   * before consulting `stateColors`. A host that wants per-point colour therefore sets this on
   * every point, including the idle ones (`pages/_shared/scene/embedScene.ts`).
   */
  color?: vec4;
  radiusMm?: number;
  /**
   * Dot radius in device-independent pixels for **this** point.
   *
   * **Not honoured by embed 0.4.0**, which reads the dot radius from the layer only
   * (`p1(layer)` clamps `layer.dotRadiusPx` to 0.5-64 px). Declared here because it is the field
   * an upstream fix should honour and the host already sends it for the active channel.
   */
  radiusPx?: number;
  group?: string;
  ordinal?: number;
  value?: number;
  [key: string]: unknown;
}

/** A protocol-2 points layer a host can write inline. */
export interface EmbedPointsLayer {
  id: string;
  datasetId: string;
  kind: "points";
  name?: string;
  visible?: boolean;
  opacity?: number;
  pickable?: boolean;
  points: EmbedPoint[];
  shape?: "sphere" | "dot";
  radiusMm?: number;
  /** Dot radius in device-independent pixels; used only when `shape` is `"dot"`. Clamped by the
   *  embed to `[0.5, 64]`, defaulting to 4. */
  dotRadiusPx?: number;
  color?: vec4;
  labelMode?: "none" | "names" | "labels";
  /** `"points"` draws each label in its own point's colour; anything else uses the theme ink. */
  labelColorSource?: "points" | "theme";
  /** Consulted only for a point that carries **no** `color` and whose `state` is not `idle`
   *  (see {@link EmbedPoint.color}); `selected` is deliberately unset by the run-page pane. */
  stateColors?: { idle?: vec4; selected?: vec4; disabled?: vec4 };
  offPlaneOpacity?: number;
  [key: string]: unknown;
}

/**
 * A `ViewSpec` as a **host** can write one: `datasets` and `layers`, everything else optional.
 *
 * The full `ViewSpec` requires `slices`, `view3d`, `layout`, `cursor`, `radiological`,
 * `background`, `lighting`, `annotations` and `transparency`; the embed fills every absent key from
 * the engine's own empty scene, captured at boot before anything is loaded. A host that *does* send
 * a camera gets exactly the camera it sent — and `tit.server` sends all of them.
 */
export interface EmbedViewSpec {
  version?: 1 | 2;
  datasets: EmbedDatasetRef[];
  layers: Record<string, unknown>[];
  activeLayerId?: string | null;
  [key: string]: unknown;
}

// ------------------------------------------------------------------------------------------------
// Guards — the HOST half (see this file's header, deviation 2)
// ------------------------------------------------------------------------------------------------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Is this a Tetravox embed message?
 *
 * Envelope only: `tvx === 1` and a `type` this build knows. It deliberately does **not** validate
 * the payload — the field a message carries is validated by whatever consumes it. What it does
 * guarantee is that `msg.type` may be switched on exhaustively.
 */
export function isEmbedMessage(v: unknown): v is EmbedMessage {
  if (!isRecord(v)) return false;
  if (v["tvx"] !== PROTOCOL_VERSION) return false;
  const type = v["type"];
  return typeof type === "string" && (EMBED_MESSAGE_TYPES as readonly string[]).includes(type);
}

/** The two things about a `MessageEvent` that decide whether to trust it. */
export interface Incoming {
  source: unknown;
  origin: string;
  data: unknown;
}

export interface AcceptOptions {
  /** The window a message must have come from — the iframe's `contentWindow`, not a sibling. */
  expectedSource: unknown;
  /** The origin the embed is served from. `'*'` accepts any origin and is for tests only. */
  embedOrigin: string;
}

/**
 * The whole trust decision, as one pure function — `docs/EMBED.md` §3's "you must do the mirror
 * check", and the reason this module has no `window` in it.
 *
 * Returns the message when it is one to act on, and `null` for every other case: wrong window,
 * wrong origin, not ours, a type this build does not know. `null` is not an error and must not be
 * reported as one — on a page with any other `postMessage` traffic at all (Vite HMR, React
 * DevTools, Electron's own bridges) most events reaching this function are somebody else's.
 *
 * Both checks, never either: the origin check alone passes a sibling iframe served from the same
 * origin, which — since the embed IS same-origin here (see `TetravoxFrame.tsx`) — is precisely the
 * case that matters.
 */
export function acceptEmbedMessage(event: Incoming, opts: AcceptOptions): EmbedMessage | null {
  if (event.source !== opts.expectedSource) return null;
  if (opts.embedOrigin !== "*" && event.origin !== opts.embedOrigin) return null;
  if (!isEmbedMessage(event.data)) return null;
  return event.data;
}

/**
 * The embed's URL for a host at `origin`, per `docs/EMBED.md` §2.
 *
 * `hostOrigin` is the only origin the embed will accept a message from, compared as an exact
 * string, so it is percent-encoded. Omitting it would leave a viewer that renders and ignores
 * everything — which is the embed's deliberate default for a host it cannot authenticate.
 */
export function embedUrl(origin: string, path = "/tetravox/index.html", presentation: "full" | "viewport" = "full"): string {
  const url = `${origin}${path}?${EMBED_PARAM}=1&${HOST_ORIGIN_PARAM}=${encodeURIComponent(origin)}`;
  return presentation === "viewport" ? `${url}&presentation=viewport` : url;
}

/** `LoadedMessage.datasets`, whichever of the two shapes arrived (see the TI DEVIATION there). */
export function normalizeLoadedDatasets(datasets: LoadedMessage["datasets"]): LoadedDataset[] {
  return datasets.map((d) => (typeof d === "string" ? { id: d, name: d, kind: "volume" as const } : d));
}

/** `LoadedMessage.layers`, same tolerance. */
export function normalizeLayers(layers: (EmbedLayer | string)[]): EmbedLayer[] {
  return layers.map((l) => (typeof l === "string" ? { id: l, name: l, visible: true, opacity: 1 } : l));
}
