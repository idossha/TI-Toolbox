/**
 * Viewer state — one zustand store per app, holding the postMessage channel to the Tetravox embed
 * and everything the surrounding chrome (layer list, cursor readout, load rows, layout switcher,
 * the shell's status bar) renders.
 *
 * The public surface is `status`, `scene`, `layers`, `cursor`/`space`, `progress`, and the actions
 * that drive them — what `viewer/TetravoxFrame.tsx` renders from and what `pages/viewer/index.tsx`
 * registers into the status bar (DESIGN.md §10, §11, program U5). `channel` is a `postMessage` pipe
 * to an iframe served from `/tetravox/` by `tit.server`; every action is a message and every piece
 * of state is an event coming back.
 *
 * `layout`/`setLayout` and `screenshotUrl`/`screenshot()` lived here for the inspector's Layout and
 * Screenshot blocks, which U5 deleted along with the rest of the inspector (image chrome is the
 * embed's own toolbar's job now, not a second copy drawn by the host) — removed rather than kept as
 * unreached exports. `serializeScene()` went the same way with the inspector's Scene block; nothing
 * on the v3 page has anywhere to put a "Save scene" affordance, and the protocol's `serialize`/
 * `scene` message pair is unaffected — a future host action can still ask for it.
 *
 * Three consequences worth knowing before editing:
 *
 *  1. **Layer ids change on load.** `Engine.load` re-adds every dataset, so the ids in the scene
 *     document the server built are gone the moment `loaded` arrives, and the ids in that message
 *     are what later `setLayerVisible`/`setLayerOpacity` must name. `layers` mirrors the *live*
 *     ids, never the scene's.
 *  2. **Nothing here is authoritative.** Visibility and opacity are applied optimistically so the
 *     inspector feels immediate, and then overwritten by the embed's own `layers` event. A
 *     divergence resolves towards the embed, which is the thing actually rendering.
 *  3. **Teardown is the iframe's.** The only way a dataset's wasm heap comes back is
 *     `worker.terminate()`; unmounting the frame does that for every worker at once, and `reset`
 *     is what a host sends when it keeps the frame mounted. `disconnect()` does both, in that
 *     order.
 */
import { create } from "zustand";
import {
  HANDSHAKE_TIMEOUT_MS,
  createChannel,
  type EmbedChannel,
} from "./channel";

export { HANDSHAKE_TIMEOUT_MS, REQUEST_TIMEOUT_MS } from "./channel";
import {
  normalizeLayers,
  normalizeLoadedDatasets,
  type EmbedLayer,
  type EmbedMessage,
  type EmbedViewSpec,
  type LoadedDataset,
  type ProbeResult,
  type vec3,
} from "./protocol";

/**
 * `'no-embed'` is new in v3 and is not an error: it means `/tetravox/` answered nothing, or
 * answered something that never said `ready` — an image built without the embed bundle. The page
 * shows a designed state naming the image version, not a stack trace.
 */
export type ViewerStatus = "idle" | "loading" | "ready" | "no-webgl2" | "no-embed" | "error";

/** Where this scene's coordinates live. Labels the cursor readout; never re-registers data. */
export type ViewerSpace = "subject" | "mni";

/**
 * One row of the loading overlay: which file, how big, how far.
 *
 * `bytes` starts at 0 and is filled from the embed's own `progress.total`: a Tetravox ViewSpec v2
 * carries no file size (`tit/viewspec.py` never stats the file), so the byte count in the UI is
 * the loader's, reported as it streams. A row therefore reads "T1.nii.gz · reading" before it can
 * read "13.1 MB".
 */
export interface DatasetProgress {
  id: string;
  name: string;
  bytes: number;
  phase: string;
  done: number;
  total: number;
  error?: string;
}

interface ViewerState {
  status: ViewerStatus;
  /** Set when `status === 'error'`; an inline message, never a toast. */
  error: string | null;
  /**
   * The embed answered the handshake (`ready`), whatever it then said about WebGL2.
   *
   * Separate from `status` because `status` only leaves `'idle'` once a scene is loading: a host
   * that has something to tell the embed the moment it boots — the app theme, see
   * `pages/viewer/index.tsx` — needs "the channel is live" without waiting for a scene.
   */
  embedReady: boolean;
  /** The embed's GL renderer string, for the status bar and the no-WebGL2 state. */
  renderer: string | null;
  /** The scene as handed to the embed. */
  scene: EmbedViewSpec | null;
  /** Mirror of the embed's live layers — the `hidden3DLayer` hint's only remaining consumer. */
  layers: EmbedLayer[];
  /**
   * Mirror of the datasets behind those layers: the scene's until `loaded` replaces them with the
   * live ones (whose `bytes` the embed learned by reading the file — a ViewSpec carries no size).
   */
  datasets: LoadedDataset[];
  space: ViewerSpace;
  cursor: vec3 | null;
  progress: DatasetProgress[];

  connect: (frame: HTMLIFrameElement, embedOrigin: string, timeoutMs?: number) => void;
  disconnect: () => void;
  /** Test seam and the `no-webgl2` path: what `TetravoxFrame` feeds every accepted message into. */
  handleMessage: (message: EmbedMessage) => void;
  setSpace: (space: ViewerSpace) => void;

  loadScene: (scene: EmbedViewSpec) => void;
  setLayerVisible: (layerId: string, visible: boolean) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  setCursor: (world: vec3) => void;
  setTheme: (theme: "light" | "dark") => void;
  focusCanvas: () => void;
  probe: (world: vec3) => Promise<ProbeResult | null>;
}

// The channel: a non-reactive companion to the store, exactly as the engine handle used to be.
// It is `viewer/channel.ts` now, shared with the run pages' scene panes — see that file's header
// for why there is one message layer for every embed host in the app rather than one each.
let channel: EmbedChannel | null = null;
/** Set while a `load` is in flight so a `ready` from a reloaded frame re-sends it. */
let pendingScene: EmbedViewSpec | null = null;

export const useViewerStore = create<ViewerState>((set, get) => ({
  status: "idle",
  error: null,
  embedReady: false,
  renderer: null,
  scene: null,
  layers: [],
  datasets: [],
  space: "subject",
  cursor: null,
  progress: [],

  connect: (frame, embedOrigin, timeoutMs = HANDSHAKE_TIMEOUT_MS) => {
    channel?.dispose();
    channel = createChannel(frame, embedOrigin, get().handleMessage, timeoutMs, () => {
      // Only a frame that never spoke is a missing embed. `embedReady`, not `status`, is the right
      // guard: a host with a subject already selected calls `loadScene` the moment its view query
      // resolves, which moves `status` to `"loading"` well before the handshake could time out —
      // checking `status === "idle"` here would then never fire again, and a dead embed would show
      // a stuck loading spinner forever instead of the `no-embed` state (found while testing the
      // reload button: the common case, a subject already picked on mount, made `no-embed`
      // unreachable). `embedReady` is set exactly once, by an accepted `ready`, and by nothing else.
      if (!get().embedReady) set({ status: "no-embed" });
    });
    // `hello` covers the other ordering: the embed posts `ready` unprompted at boot, and this
    // listener may well have been attached after that went past.
    channel.post({ type: "hello" });
  },

  disconnect: () => {
    channel?.post({ type: "reset" });
    channel?.dispose();
    channel = null;
    pendingScene = null;
    set({
      status: "idle",
      embedReady: false,
      scene: null,
      layers: [],
      datasets: [],
      progress: [],
      cursor: null,
      error: null,
    });
  },

  handleMessage: (message) => {
    switch (message.type) {
      case "ready": {
        const renderer = message.caps.renderer ?? null;
        if (!message.caps.webgl2) {
          set({ status: "no-webgl2", embedReady: true, renderer, error: null });
          return;
        }
        set({ embedReady: true, renderer, error: null });
        // A frame that reloaded (or one that booted after `loadScene` was called) gets the scene
        // now: the store, not the page, owns "the viewer should be showing this".
        if (pendingScene !== null) {
          set({ status: "loading" });
          channel?.post({ type: "load", scene: pendingScene });
        }
        return;
      }
      case "status": {
        const phase = message.phase;
        if (phase === "error") set({ status: "error", error: message.message ?? "The viewer reported an error." });
        else if (phase === "no-webgl2") set({ status: "no-webgl2" });
        else if (phase === "ready") set({ status: "ready", error: null });
        else set({ status: phase });
        return;
      }
      case "progress": {
        set((s) => {
          const row: DatasetProgress = {
            id: message.datasetId,
            name: message.name,
            bytes: Math.max(message.total, 0),
            phase: message.phase,
            done: message.done,
            total: message.total,
          };
          const index = s.progress.findIndex((p) => p.id === message.datasetId);
          if (index < 0) return { progress: [...s.progress, row] };
          const next = s.progress.slice();
          next[index] = { ...next[index], ...row };
          return { progress: next };
        });
        return;
      }
      case "loaded": {
        set((s) => ({
          status: "ready",
          error: null,
          layers: withPreservedLayerFields(normalizeLayers(message.layers), s.layers),
          datasets: withPreservedDatasetFields(normalizeLoadedDatasets(message.datasets), s.datasets),
        }));
        pendingScene = null;
        return;
      }
      case "layers": {
        set((s) => ({ layers: withPreservedLayerFields(normalizeLayers(message.layers), s.layers) }));
        return;
      }
      case "cursor": {
        set({ cursor: message.world });
        return;
      }
      case "error": {
        set({ status: "error", error: message.message });
        return;
      }
      default:
        // `probe` and `scene` are answers, resolved by their id in the channel.
        return;
    }
  },

  setSpace: (space) => set({ space }),

  loadScene: (scene) => {
    // A machine already known to be unable to render (no context, or nothing ever answered) is
    // not about to load anything: adopting the scene's own nominal cursor/progress here would give
    // the status bar's `ras` cell a value for a crosshair that was never actually shown on
    // anything, which is exactly the placeholder-cell failure §11 exists to prevent.
    const cannotRender = get().status === "no-webgl2" || get().status === "no-embed";
    pendingScene = scene;
    const layers = Array.isArray(scene.layers) ? (scene.layers as EmbedLayer[]) : [];
    const datasets = Array.isArray(scene.datasets) ? scene.datasets : [];
    set({
      scene,
      // The scene's own layer ids until `loaded` replaces them with the live ones — so the
      // 3D-hint derivation has something to read while the first bytes are still in flight.
      layers: layers.map((l) => ({ ...l })),
      // The scene's own dataset rows (names are file basenames, sizes unknown) until `loaded`
      // brings the live ids and the byte counts the loader measured.
      datasets: datasets.map((d) => ({ id: d.id, name: d.name, kind: d.kind === "mesh" ? ("mesh" as const) : ("volume" as const) })),
      cursor: cannotRender ? null : cursorOf(scene),
      progress: cannotRender ? [] : datasets.map((d) => ({ id: d.id, name: d.name, bytes: 0, phase: "queued", done: 0, total: 0 })),
      error: null,
    });
    if (cannotRender) return;
    set({ status: "loading" });
    channel?.post({ type: "load", scene });
  },

  setLayerVisible: (layerId, visible) => {
    set((s) => ({ layers: s.layers.map((l) => (l.id === layerId ? { ...l, visible } : l)) }));
    channel?.post({ type: "setLayerVisible", layerId, visible });
  },

  setLayerOpacity: (layerId, opacity) => {
    set((s) => ({ layers: s.layers.map((l) => (l.id === layerId ? { ...l, opacity } : l)) }));
    channel?.post({ type: "setLayerOpacity", layerId, opacity });
  },

  setCursor: (world) => {
    set({ cursor: world });
    channel?.post({ type: "setCursor", world });
  },

  setTheme: (theme) => {
    channel?.post({ type: "setTheme", theme });
  },

  focusCanvas: () => {
    channel?.post({ type: "focus" });
  },

  probe: async (world) => {
    if (channel === null) return null;
    try {
      const reply = await channel.request<Extract<EmbedMessage, { type: "probe" }>>({ type: "probe", world }, "probe");
      return reply.result;
    } catch {
      return null;
    }
  },
}));

/**
 * Keep the descriptive fields the embed did not send back: `name`, `kind` and `datasetId`.
 *
 * The protocol's `loaded`/`layers` carry the engine's full `Layer[]`, all three included. A build
 * that sends only ids (the e2e fake embed does) would otherwise blank every row in the inspector
 * down to `L0`, `L1` — so an incoming layer missing one of those inherits it from the mirror's
 * entry for the same id, falling back to the same POSITION when the ids were re-issued by the load
 * (which is exactly when this matters: `Engine.load` re-adds every dataset and the scene's ids are
 * gone). `kind` and `datasetId` are inherited for the same reason names are: the inspector needs
 * "is this a mesh?" to explain an empty 3D pane, and "which dataset?" to show a size.
 *
 * Nothing else is inherited. Visibility, opacity and every other live property always come from the
 * embed, which is the thing actually rendering.
 */
function withPreservedLayerFields(incoming: EmbedLayer[], previous: EmbedLayer[]): EmbedLayer[] {
  return incoming.map((layer, index) => {
    const prior = previous.find((p) => p.id === layer.id) ?? previous[index];
    if (prior === undefined) return layer;
    const patch: Partial<EmbedLayer> = {};
    const named = typeof layer.name === "string" && layer.name !== "" && layer.name !== layer.id;
    if (!named && typeof prior.name === "string" && prior.name !== "") patch.name = prior.name;
    if (typeof layer.kind !== "string" && typeof prior.kind === "string") patch.kind = prior.kind;
    if (layer["datasetId"] === undefined && prior["datasetId"] !== undefined) patch["datasetId"] = prior["datasetId"];
    return Object.keys(patch).length === 0 ? layer : { ...layer, ...patch };
  });
}

/**
 * Same idea for the dataset mirror: the live ids and `bytes` come from `loaded`, the human name and
 * the volume/mesh kind fall back to the scene's row at the same position when the embed sent only
 * an id string (the fake embed's shape, and `normalizeLoadedDatasets`' widening).
 */
function withPreservedDatasetFields(incoming: LoadedDataset[], previous: LoadedDataset[]): LoadedDataset[] {
  return incoming.map((dataset, index) => {
    const prior = previous.find((p) => p.id === dataset.id) ?? previous[index];
    if (prior === undefined) return dataset;
    const named = dataset.name !== "" && dataset.name !== dataset.id;
    return {
      ...dataset,
      name: named ? dataset.name : prior.name,
      kind: dataset.kind ?? prior.kind,
      bytes: dataset.bytes ?? prior.bytes,
    };
  });
}

// -------------------------------------------------------------------------------------------
// Scene readers — a ViewSpec is `Record<string, unknown>` past its two required arrays, so these
// are the only places that guess at a field, and each one falls back rather than throwing.
// -------------------------------------------------------------------------------------------

function cursorOf(scene: EmbedViewSpec): vec3 | null {
  const cursor = scene["cursor"];
  if (!Array.isArray(cursor) || cursor.length !== 3) return null;
  if (!cursor.every((v) => typeof v === "number" && Number.isFinite(v))) return null;
  return [cursor[0], cursor[1], cursor[2]] as vec3;
}

/** Test seam: the channel is module state, exactly as the engine handle was. */
export function __resetViewerChannelForTests(): void {
  channel?.dispose();
  channel = null;
  pendingScene = null;
}
