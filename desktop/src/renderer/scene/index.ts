/**
 * `renderer/scene/` — the slim scene renderer (plan of record `docs/dev/HISTORY.md § 2026-09-04 (scene service)`,
 * decisions S1, S4, S5, S6).
 *
 * ## What this is
 *
 * A WebGL2 renderer with **no runtime dependency** — no three.js, no `@tetravox/*`, no matrix
 * library, nothing but the browser's own `WebGL2RenderingContext` — that draws exactly four things:
 *
 *   1. two translucent triangle surfaces (skin, grey matter),
 *   2. point markers (electrodes; a sphere centre),
 *   3. a highlighted region set on a labelled surface,
 *   4. nothing else.
 *
 * It exists so a user can *choose*: electrodes on the Simulator, a target on the Optimizer, a
 * verified ROI on the Analyzer. **The scene is a form control, not a viewer** (S1) — one that
 * happens to be three-dimensional.
 *
 * ## Non-goals, verbatim from S1
 *
 * These belong to the Tetravox embed on the Viewer page (`renderer/viewer/`), and adding any of
 * them here is how TI-Toolbox ends up maintaining a second general-purpose viewer — the failure the
 * microservice split exists to prevent:
 *
 *   - **no volume slicing** — no slice planes, no crosshair, no 2D panes;
 *   - **no colormaps** — no scalar-to-colour mapping, no colour bar, no window/level;
 *   - **no field overlays** — TI_max, E-field magnitude and every other result stay on the Viewer;
 *   - **no publication screenshots** — no capture, no export, no camera bookmarking;
 *   - **no layer tree** — two named surfaces and one marker set, not an arbitrary layer stack;
 *   - **no loading** — the caller hands over decoded arrays; this module never fetches a URL,
 *     resolves a path, or knows a subject id.
 *
 * ## Shape of the module
 *
 * Everything a test needs to reason about is pure and GPU-free, which is what makes a renderer
 * testable without a GPU (S4):
 *
 * | File | What it is | Tested by |
 * |---|---|---|
 * | `camera.ts` | orbit -> view matrix, projection, screen ray, damping, presets | `scene-camera.test.ts` |
 * | `tvsc.ts` | the `TVSC1` wire format (plan §2.3), parse and encode | `scene-tvsc.test.ts` |
 * | `normals.ts` | area-weighted vertex normals, bounds | `scene-normals.test.ts` |
 * | `pickId.ts` | the 24-bit colour-id encoding both shaders write | `scene-pick.test.ts` |
 * | `selection.ts` | what a pick means per mode | `scene-selection.test.ts` |
 * | `glScene.ts` | the only file that touches WebGL | the offscreen Electron run |
 * | `SceneCanvas.tsx` | the React surface, `window.__scene` | `tests/e2e/scene.spec.ts` |
 */
export { SceneCanvas, SCENE_DEBUG, type SceneCanvasProps, type SceneDebugHandle } from "./SceneCanvas";
export {
  DEFAULT_FOV_Y,
  FIT_FILL,
  PITCH_LIMIT,
  PRESET_ANGLES,
  boundsCentre,
  boundsRadius,
  cameraBasis,
  cameraPosition,
  dampCamera,
  depthRange,
  fitDistance,
  fitDistanceToPoints,
  frameDistance,
  lookAt,
  dominantAxis,
  multiply,
  orbitBy,
  panBy,
  perspective,
  presetCamera,
  projectPoint,
  projectToCanvas,
  screenRay,
  unprojectDepth,
  viewDepthFromNdc,
  viewMatrix,
  screenAnatomy,
  viewProjection,
  zoomBy,
  type AnatomicalAxis,
  type Bounds,
  type CameraPreset,
  type Mat4,
  type OrbitCamera,
  type Ray,
  type Vec3,
  type ViewAngles,
} from "./camera";
export { computeBounds, computeVertexNormals, unionBounds } from "./normals";
export {
  TVSC_FLAG_LABELS,
  TVSC_HEADER_BYTES,
  TVSC_MAGIC,
  TVSC_VERSION,
  TvscError,
  encodeTvsc1,
  parseTvsc1,
  tvscByteLength,
  type Tvsc1,
} from "./tvsc";
export {
  PICK_INDEX_MAX,
  PICK_KIND_MARKER,
  PICK_KIND_NONE,
  PICK_KIND_REGION,
  decodePickId,
  decodePickPixel,
  encodePickId,
  pickIdToRgb,
  rgbToPickId,
  samePickTarget,
  type PickKind,
  type PickTarget,
} from "./pickId";
export {
  EMPTY_SELECTION,
  MODE_RULES,
  isPickable,
  isSelected,
  selectionReducer,
  type SceneMode,
  type SceneSelection,
  type SelectionAction,
  type SelectionRules,
} from "./selection";
export {
  DEFAULT_OPACITY,
  MARKER_SIZE_PX,
  SCENE_CATEGORICAL,
  SCENE_PALETTE,
  categoricalColor,
  rgbToHex,
  type ScenePalette,
} from "./palette";
export {
  buildLabelStates,
  buildLabelColors,
  labelSwatchColor,
  createGlScene,
  decodePackedDepth,
  type GlScene,
  type PickOptions,
  type PickResult,
} from "./glScene";
export type { LegendEntry, Rgb, ScenePart, SceneMarker, ScenePick, SceneStats } from "./types";
