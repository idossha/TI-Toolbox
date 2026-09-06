/**
 * `<SceneCanvas>` — the React surface of the slim scene (plan S4/S5/S6).
 *
 * It owns the canvas, the interaction loop and the chrome (camera presets, per-surface opacity, the
 * legend). It owns no data: the caller hands it decoded arrays and a selection, and it reports
 * picks back. That is what makes one component serve three pages — `mode` decides what is pickable
 * and the caller decides what a pick means.
 *
 * Three contracts are worth stating, because tests and callers both depend on them:
 *
 *  - **`parts` and `markers` must be referentially stable** (memoise them). They are the upload
 *    trigger: a fresh array literal every render would re-upload 150 k triangles every render.
 *  - **Selection is controlled when the caller passes one** (decision S6: the pane is never the only
 *    way to select, and the form and the pane must not be able to disagree). Uncontrolled use keeps
 *    an internal copy, which is what the gallery does.
 *  - **`window.__scene` exists in dev and gallery builds only** and is the offscreen test's window
 *    onto real state — camera, uploaded counts, selection, fps. A test asserts those numbers; it
 *    never compares a screenshot, because an agent cannot judge a picture but can judge whether the
 *    marker whose projection it computed is the marker that got selected.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { SegmentedControl } from "../ui/SegmentedControl";
import { Slider } from "../ui/Toggle";
import {
  DEFAULT_FOV_Y,
  boundsRadius,
  dampCamera,
  frameDistance,
  orbitBy,
  orientationCaption,
  orientationTitle,
  panBy,
  presetCamera,
  projectToCanvas,
  screenRay,
  unprojectDepth,
  zoomBy,
  type Bounds,
  type CameraPreset,
  type OrbitCamera,
  type Vec3,
} from "./camera";
import {
  MARKER_HOVER,
  MARKER_SELECTED,
  buildLabelStates,
  createGlScene,
  markerStateChannel,
  type GlScene,
  type PickResult,
} from "./glScene";
import { computeBounds, unionBounds } from "./normals";
import { samePickTarget, type PickTarget } from "./pickId";
import { DEFAULT_OPACITY } from "./palette";
import {
  EMPTY_SELECTION,
  MODE_RULES,
  isPickable,
  selectionReducer,
  type SceneMode,
  type SceneSelection,
} from "./selection";
import type { LegendEntry, ScenePart, SceneMarker, ScenePick, SceneStats } from "./types";
import "./scene.css";

/**
 * The dev/e2e state hook (`window.__scene`, and `window.__scenePane` in `ScenePane.tsx`). Absent
 * from a production build — the flag is inlined by Vite, so the handle and its
 * `WEBGL_lose_context` helpers are tree-shaken out rather than merely hidden.
 *
 * Its own flag, `VITE_SCENE_HOOKS=1`, not the design gallery's. They were the same flag until
 * 2026-09-04 and three lanes paid for it: a `--project=real` scene spec needs these hooks and does
 * not need the gallery, so the build it asked for shipped a whole `dev/` route it never opened,
 * and when someone built without the flag the failure read "Design gallery heading not found"
 * (`dev/notes/v3-scene-ia/fix-c-notes.md` open issue 2, `fix-a-notes.md` §5.5). `VITE_INCLUDE_GALLERY`
 * still works on its own for the gallery, and `pree2e` sets both.
 */
export const SCENE_DEBUG =
  import.meta.env.DEV || import.meta.env.VITE_SCENE_HOOKS === "1";

/** An adult head's bounding box in RAS mm. Used only to frame an empty pane: a zero-size box gives
 *  a fit distance of 0, and the first `log(distance)` in the damping step then returns -Infinity. */
const EMPTY_BOUNDS: Bounds = [-80, -105, -70, 80, 90, 95];

const NO_MARKERS: SceneMarker[] = [];

export interface SceneDebugHandle {
  ready: boolean;
  webgl2: boolean;
  contextLost: boolean;
  mode: SceneMode;
  parts: Array<{ id: string; triangles: number; vertices: number; opacity: number }>;
  markers: Array<{ index: number; id: string; world: Vec3 }>;
  selection: SceneSelection;
  hover: PickTarget | null;
  /** The last click's full `ScenePick`, so an offscreen test can assert the world point the
   *  renderer reported against the geometry it should be on. */
  lastPick: ScenePick | null;
  camera: OrbitCamera & { settled: boolean };
  canvas: { widthCss: number; heightCss: number; dpr: number };
  fps: number;
  frames: number;
  stats: SceneStats;
  /** Projects a world point to canvas CSS pixels with the CURRENT camera — the same function the
   *  spec calls itself, exposed so a test can cross-check its own arithmetic against the app's. */
  project(world: Vec3): { x: number; y: number; inFront: boolean };
  /**
   * Renders one frame with the current camera and reads the drawing buffer back at those canvas
   * CSS points — RGBA in [0, 255], one array of four per point.
   *
   * `withMarkers: false` renders the same frame with the marker pass suppressed, so a spec can say
   * "a marker is painted at this pixel" as an exact difference between two frames instead of as a
   * colour model of the shader. `null` when there is no renderer or no camera yet.
   */
  samplePixels(points: Array<[number, number]>, withMarkers?: boolean): number[][] | null;
  /**
   * Overrides `markersOccluded` on the live renderer until the next render that changes the prop.
   *
   * It is what lets a spec show the **defect** and the fix on the same build: with occlusion off,
   * the markers meet an empty depth buffer and every one of them is painted over the head, which is
   * the draw order this pane had until 2026-09-04. A number recorded from a build that no longer
   * exists is a claim; a number measured either side of one switch is a test.
   */
  setMarkerOcclusion(occluded: boolean): boolean;
  /** Forces a context loss through `WEBGL_lose_context`, the only way to exercise the recovery path
   *  deliberately. */
  loseContext(): boolean;
  restoreContext(): boolean;
}

declare global {
  interface Window {
    __scene?: SceneDebugHandle;
  }
}

export interface SceneCanvasProps {
  mode: SceneMode;
  /** Memoise this: it is the upload trigger. */
  parts: ScenePart[];
  /** Memoise this too. */
  markers?: SceneMarker[];
  /**
   * Whether the surfaces hide the markers behind them. Default `true`.
   *
   * `true` for markers that lie ON the anatomy — an EEG net: an electrode round the back of the
   * head has to be behind the head, which is the whole of lane N1's fix. `false` for a marker that
   * names a point INSIDE it (the Analyzer's and Optimizer's sphere centre, which is in the brain by
   * construction): occluding that would hide the only thing telling the user where they put it.
   */
  markersOccluded?: boolean;
  /** Controlled selection. Omit for an uncontrolled pane. */
  selection?: SceneSelection;
  onSelectionChange?: (next: SceneSelection) => void;
  /** Every pick, including `null` for empty space — a caller that wants the raw pick rather than
   *  the reducer's opinion (the Analyzer's sphere centre) uses this. */
  onPick?: (target: PickTarget | null) => void;
  /**
   * The same pick, with the place it happened: the world point under the cursor and the ray it came
   * from (`ScenePick`). This is what "click anywhere on the cortex to put the sphere centre there"
   * is built from; `onPick` alone can only name a region, not locate one.
   *
   * Fired for every click, `null` target included. Only clicks: hover does not read the depth back,
   * because a second `readPixels` stall per mouse move buys feedback nobody acts on.
   */
  onPickAt?: (pick: ScenePick) => void;
  /**
   * What the cursor is over, every time it changes — `null` when it is over nothing.
   *
   * The pane turns this into a **word** ("Hovering: superiorfrontal · lh"). A 3D region highlight
   * with no name is the failure it prevents: the user sees a patch light up and still has to guess
   * which of 70 atlas rows it is, which is exactly the guessing the interactive atlas exists to
   * end. Hover never reads depth back (no `readPixels` stall per mouse move), so it names what was
   * hit and not where.
   */
  onHoverChange?: (target: PickTarget | null) => void;
  /**
   * Whether THIS canvas publishes `window.__scene`. Default `true`.
   *
   * The app retains a mounted panel per page, so three panes can be alive at once and the last one
   * to run its effect wins the single global handle — measured: a spec on the Optimizer read the
   * Simulator's hidden 1x1 canvas. The caller says which one is on screen; a canvas that is not
   * publishes nothing rather than racing for the name.
   */
  publishDebugHandle?: boolean;
  /** Scene bounds; computed from the parts when omitted. */
  bounds?: Bounds;
  /**
   * The sub-box worth *framing*, when it is smaller than what the scene *contains* — the server's
   * `manifest.focus_bbox`, which is the head with the neck cut off at the lowest grey-matter
   * vertex.
   *
   * Everything is still drawn, still pickable and still inside the near/far planes; only the
   * camera's target and fit set are taken from this box, and only its **z floor** filters the fit
   * points. Cutting on the floor alone rather than on the whole box is deliberate: the box is
   * tighter in y as well (a template's jaw), and filtering on that would push a nose or a chin off
   * the edge of a lateral view.
   *
   * Omit it and framing is exactly what it was: every point, in `bounds`.
   */
  focus?: Bounds;
  /** Extra legend rows the page wants (an ROI's name, a montage's channel labels). */
  legend?: LegendEntry[];
  className?: string;
  /** Accessible name for the canvas. */
  label?: string;
}

const PRESET_OPTIONS = [
  { value: "front", label: "F", title: "Front (anterior) — 1" },
  { value: "left", label: "L", title: "Left — 2" },
  { value: "right", label: "R", title: "Right — 3" },
  { value: "top", label: "T", title: "Top — 4" },
];

const formatCount = (n: number): string => n.toLocaleString("en-US").replace(/,/g, " ");

const swatch = (color: readonly [number, number, number]): string =>
  `rgb(${color.map((c) => Math.round(c * 255)).join(",")})`;

export function SceneCanvas({
  mode,
  parts,
  markers: markersProp,
  markersOccluded = true,
  selection,
  onSelectionChange,
  onPick,
  onPickAt,
  onHoverChange,
  publishDebugHandle = true,
  bounds,
  focus,
  legend,
  className,
  label = "3D scene",
}: SceneCanvasProps) {
  const markers = markersProp ?? NO_MARKERS;

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<GlScene | null>(null);
  const goalRef = useRef<OrbitCamera | null>(null);
  const cameraRef = useRef<OrbitCamera | null>(null);
  const settledRef = useRef(true);
  const frameRef = useRef(0);
  const rafRef = useRef(0);
  const lastTimeRef = useRef(0);
  const fpsRef = useRef({ fps: 0, windowStart: 0, windowFrames: 0 });
  const sizeRef = useRef({ widthCss: 1, heightCss: 1, dpr: 1 });
  const hoverRef = useRef<PickTarget | null>(null);
  /** In a ref so a caller may pass an inline callback without tearing down the pointer handlers
   *  (which would drop a drag in progress). */
  const onHoverChangeRef = useRef(onHoverChange);
  const lastPickRef = useRef<ScenePick | null>(null);
  const dragRef = useRef<{ mode: "orbit" | "pan"; startX: number; startY: number; x: number; y: number } | null>(null);
  /** What the current camera should be framed on, mirrored into a ref so the ResizeObserver can
   *  re-frame without being torn down and rebuilt every time the geometry changes. */
  const framingRef = useRef<{ bounds: Bounds; points: Float32Array[] } | null>(null);
  /** False once the user has moved the camera themselves. A resize re-frames only while this is
   *  true: re-framing a view somebody has just orbited to is the pane moving under their hand. */
  const framedRef = useRef(true);

  useEffect(() => {
    onHoverChangeRef.current = onHoverChange;
  }, [onHoverChange]);

  const [webgl2, setWebgl2] = useState<boolean | null>(null);
  const [contextLost, setContextLost] = useState(false);
  const [internalSelection, setInternalSelection] = useState<SceneSelection>(EMPTY_SELECTION);
  const [hover, setHover] = useState<PickTarget | null>(null);
  const [opacities, setOpacities] = useState<Record<string, number>>({});
  const [preset, setPreset] = useState<CameraPreset | "">("reset");
  /**
   * The laterality statement under the preset buttons, kept in React state because the camera
   * itself lives in a ref driven by rAF. Written only when the STRING changes, which for an orbit
   * is once or twice in a whole drag rather than once per frame.
   */
  const [orientation, setOrientation] = useState<{ caption: string; title: string } | null>(null);

  const rules = MODE_RULES[mode];
  const activeSelection = selection ?? internalSelection;
  const selectionRef = useRef(activeSelection);
  // Mirrored into a ref in an effect, not during render (the react-hooks/refs rule, and it is
  // right): the pick handlers need the current selection synchronously, and effects flush before
  // the next user event, so the ref is never stale by the time a click reads it.
  useEffect(() => {
    selectionRef.current = activeSelection;
  }, [activeSelection]);

  const sceneBounds = useMemo<Bounds>(() => {
    const box = bounds ?? unionBounds(parts.map((part) => computeBounds(part.positions)));
    return boundsRadius(box) > 1e-6 ? box : EMPTY_BOUNDS;
  }, [bounds, parts]);
  const radius = useMemo(() => Math.max(1, boundsRadius(sceneBounds)), [sceneBounds]);

  /**
   * The box the camera is aimed at and fitted to — `focus` when the server sent one, otherwise the
   * whole scene. `sceneBounds` stays the whole scene, because the zoom clamp and the near/far
   * planes are derived from it and must still contain what is drawn.
   */
  const framingBounds = useMemo<Bounds>(
    () => (focus && boundsRadius(focus) > 1e-6 ? focus : sceneBounds),
    [focus, sceneBounds],
  );

  /**
   * The points the camera is framed on: every vertex the pane draws **at or above the framing
   * box's floor**, plus the markers, which can sit *outside* the surfaces (an electrode is on the
   * scalp, not in it) and are therefore never filtered — an electrode below the floor keeps
   * itself in frame.
   *
   * Framing on the geometry rather than on its bounding box is what makes the head fill the pane.
   * The box of a head is much bigger than the head — sub-ernie's is 168 x 228 x 229 mm around a
   * skull whose silhouette is nowhere near that — and the sphere around that box is bigger again,
   * which is how a 544 px pane ended up showing a 209 px head (`tests/unit/scene-framing.test.ts`).
   *
   * The floor is the second half of that: a head model's skin runs down the neck to the shoulders
   * (sub-ernie reaches z = −128.9 mm while its grey matter starts at −50.7), so an exact fit to
   * *everything* still spends about a fifth of the pane on neck.
   */
  const fitPoints = useMemo<Float32Array[]>(() => {
    const floorZ = framingBounds === sceneBounds ? -Infinity : framingBounds[2];
    const sets: Float32Array[] = [];
    for (const part of parts) {
      const positions = part.positions;
      if (positions.length < 3) continue;
      if (floorZ === -Infinity) {
        sets.push(positions);
        continue;
      }
      // One pass to count, one to fill: a subarray copy of 70 586 vertices is cheaper than the
      // array-of-arrays a filter/map pair would allocate, and this runs once per subject.
      let kept = 0;
      for (let i = 2; i < positions.length; i += 3) if ((positions[i] as number) >= floorZ) kept += 1;
      if (kept === 0) {
        sets.push(positions);
        continue;
      }
      const above = new Float32Array(kept * 3);
      let w = 0;
      for (let i = 0; i < positions.length; i += 3) {
        if ((positions[i + 2] as number) < floorZ) continue;
        above[w] = positions[i] as number;
        above[w + 1] = positions[i + 1] as number;
        above[w + 2] = positions[i + 2] as number;
        w += 3;
      }
      sets.push(above);
    }
    if (markers.length > 0) {
      const world = new Float32Array(markers.length * 3);
      markers.forEach((marker, index) => {
        world[index * 3] = marker.world[0];
        world[index * 3 + 1] = marker.world[1];
        world[index * 3 + 2] = marker.world[2];
      });
      sets.push(world);
    }
    return sets;
  }, [framingBounds, markers, parts, sceneBounds]);

  /** Every label id that actually occurs on a labelled part — the set `buildLabelStates` dims.
   *  Computed once per parts change: it is a linear pass over the whole vertex array. */
  const knownLabels = useMemo(() => {
    const set = new Set<number>();
    for (const part of parts) {
      if (!part.labels) continue;
      for (let i = 0; i < part.labels.length; i += 1) set.add(part.labels[i] as number);
    }
    return set;
  }, [parts]);

  const requestFrame = useCallback(() => {
    // `settled` is the signal a caller (and an offscreen test) waits on to mean "the view has
    // stopped moving". It has to go false the moment a frame is PENDING, not when the frame runs:
    // a click that sets a new goal returns to the caller before the first rAF fires, and a test
    // that read `settled` in that window saw the previous rest state and sampled a camera
    // mid-flight (measured: yaw -0.858 rad read one damping step into a move to -1.571).
    settledRef.current = false;
    if (rafRef.current !== 0) return;
    lastTimeRef.current = 0;
    const step = (time: number) => {
      rafRef.current = 0;
      const scene = sceneRef.current;
      const goal = goalRef.current;
      const current = cameraRef.current;
      if (!scene || !goal || !current) return;
      const dt = lastTimeRef.current === 0 ? 16 : time - lastTimeRef.current;
      lastTimeRef.current = time;
      const damped = dampCamera(current, goal, dt);
      cameraRef.current = damped.camera;
      settledRef.current = damped.settled;
      scene.render(damped.camera);
      frameRef.current += 1;
      const caption = orientationCaption(damped.camera);
      setOrientation((current) =>
        current?.caption === caption ? current : { caption, title: orientationTitle(damped.camera) },
      );

      const fps = fpsRef.current;
      fps.windowFrames += 1;
      if (fps.windowStart === 0) fps.windowStart = time;
      else if (time - fps.windowStart >= 400) {
        fps.fps = (fps.windowFrames * 1000) / (time - fps.windowStart);
        fps.windowStart = time;
        fps.windowFrames = 0;
      }
      if (damped.settled) {
        // Settled: stop the loop. A pane holding a 60 Hz rAF alive for a static picture is why a
        // laptop's fan turns on while nothing is happening.
        fps.windowStart = 0;
        fps.windowFrames = 0;
        return;
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
  }, []);

  const setGoal = useCallback(
    (next: OrbitCamera) => {
      goalRef.current = next;
      requestFrame();
    },
    [requestFrame],
  );

  // --- context creation -----------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let scene: GlScene | null = null;
    try {
      scene = createGlScene(canvas);
    } catch (error) {
      // A driver that advertises WebGL2 and then fails to compile a shader is indistinguishable, to
      // the user, from a driver with no WebGL2 at all — both get the same readable line (S6).
      console.error("scene: WebGL2 initialisation failed", error);
      scene = null;
    }
    sceneRef.current = scene;
    setWebgl2(scene !== null);
    if (!scene) return;

    const onLost = (event: Event) => {
      // Without preventDefault the context is never restorable and the pane is dead until remount.
      event.preventDefault();
      setContextLost(true);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
    const onRestored = () => {
      const restored = sceneRef.current;
      if (!restored) return;
      restored.restore();
      const size = sizeRef.current;
      restored.resize(size.widthCss, size.heightCss, size.dpr);
      setContextLost(false);
      requestFrame();
    };
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      scene?.dispose();
      sceneRef.current = null;
    };
  }, [requestFrame]);

  // --- sizing ---------------------------------------------------------------------------------
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const apply = () => {
      const rect = wrap.getBoundingClientRect();
      // Capped at 2: a 3x backing store on a 4K display triples the fragment cost for a difference
      // nobody can see on an 11 px marker.
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      sizeRef.current = { widthCss: rect.width, heightCss: rect.height, dpr };
      sceneRef.current?.resize(rect.width, rect.height, dpr);
      // A pane that doubles in width (S7's expand control) keeps the distance that framed the
      // narrow one, and the head stays as small as it was in a pane three times the size. So the
      // distance — and only the distance — is refitted for the new aspect, at the angles the camera
      // already has, and only while the user has not moved it themselves.
      const framing = framingRef.current;
      const goal = goalRef.current;
      if (framedRef.current && framing && goal && rect.width > 0 && rect.height > 0) {
        const distance = frameDistance(
          framing.bounds,
          goal.target,
          goal.fovY,
          rect.width / rect.height,
          goal,
          framing.points,
        );
        goalRef.current = { ...goal, distance };
        if (cameraRef.current && settledRef.current) cameraRef.current = { ...cameraRef.current, distance };
      }
      requestFrame();
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [requestFrame]);

  // --- wheel, as a non-passive listener --------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      const goal = goalRef.current;
      if (!goal) return;
      // React attaches `onWheel` passively, so `preventDefault` from a JSX handler is ignored (with
      // a console warning) and the page scrolls behind the zoom. Hence the manual listener.
      event.preventDefault();
      setPreset("");
      framedRef.current = false;
      setGoal(zoomBy(goal, event.deltaY, radius));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [radius, setGoal]);

  // --- data upload ----------------------------------------------------------------------------
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    scene.setParts(parts);
    setOpacities((previous) => {
      const next: Record<string, number> = {};
      for (const part of parts) {
        const value = previous[part.id] ?? DEFAULT_OPACITY[part.id] ?? part.opacity;
        next[part.id] = value;
        scene.setOpacity(part.id, value);
      }
      return next;
    });
    requestFrame();
  }, [parts, requestFrame, webgl2]);

  useEffect(() => {
    sceneRef.current?.setMarkers(markers);
    requestFrame();
  }, [markers, requestFrame, webgl2]);

  useEffect(() => {
    sceneRef.current?.setMarkerOcclusion(markersOccluded);
    requestFrame();
  }, [markersOccluded, requestFrame, webgl2]);

  // Frame the scene when the geometry changes — i.e. a different subject, or a first load. Not on
  // selection changes: re-framing under the user's hand is how a 3D pane becomes unusable.
  useEffect(() => {
    framingRef.current = { bounds: framingBounds, points: fitPoints };
    const size = sizeRef.current;
    const camera = presetCamera(
      "reset",
      framingBounds,
      size.widthCss / Math.max(1, size.heightCss),
      DEFAULT_FOV_Y,
      fitPoints,
    );
    goalRef.current = camera;
    cameraRef.current = camera;
    settledRef.current = true;
    framedRef.current = true;
    requestFrame();
  }, [fitPoints, framingBounds, requestFrame]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const states = new Uint32Array(markers.length);
    markers.forEach((marker, i) => {
      let state = markerStateChannel(marker.channel);
      if (activeSelection.markers.includes(i)) state |= MARKER_SELECTED;
      if (hover?.kind === "marker" && hover.index === i) state |= MARKER_HOVER;
      states[i] = state;
    });
    scene.setMarkerStates(states);
    requestFrame();
  }, [markers, activeSelection, hover, requestFrame]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    scene.setLabelStates(
      buildLabelStates(knownLabels, activeSelection.regions, hover?.kind === "region" ? hover.index : null),
    );
    requestFrame();
  }, [knownLabels, activeSelection, hover, requestFrame]);

  /** A one-off redraw for a change the damping loop would otherwise sleep through (opacity, a
   *  selection change while the camera is settled). */
  const redraw = useCallback(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    if (scene && camera) scene.render(camera);
  }, []);

  useEffect(redraw, [activeSelection, hover, opacities, redraw]);

  // --- interaction ----------------------------------------------------------------------------
  const canvasPoint = useCallback((event: { clientX: number; clientY: number }) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }, []);

  const pickAt = useCallback(
    (x: number, y: number, depth = false): PickResult | null => {
      const scene = sceneRef.current;
      const camera = cameraRef.current;
      if (!scene || !camera) return null;
      return scene.pick(x, y, camera, {
        markers: isPickable(rules, "marker"),
        regions: isPickable(rules, "region"),
        depth,
      });
    },
    [rules],
  );

  const applyPick = useCallback(
    (target: PickTarget | null) => {
      onPick?.(target);
      const next = selectionReducer(selectionRef.current, { type: "pick", target }, rules);
      if (next === selectionRef.current) return;
      setInternalSelection(next);
      onSelectionChange?.(next);
    },
    [onPick, onSelectionChange, rules],
  );

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      canvas?.focus();
      const point = canvasPoint(event);
      // Middle/right button or Shift pans; plain left orbits. Two gestures, no modifier to discover
      // for the common one.
      const pan = event.button === 1 || event.button === 2 || event.shiftKey;
      dragRef.current = { mode: pan ? "pan" : "orbit", startX: point.x, startY: point.y, x: point.x, y: point.y };
      canvas?.setPointerCapture(event.pointerId);
    },
    [canvasPoint],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const point = canvasPoint(event);
      const drag = dragRef.current;
      const goal = goalRef.current;
      if (drag && goal) {
        const dx = point.x - drag.x;
        const dy = point.y - drag.y;
        drag.x = point.x;
        drag.y = point.y;
        if (dx === 0 && dy === 0) return;
        setPreset("");
        // The camera is the user's now: a pane resize must not re-frame it out from under them.
        framedRef.current = false;
        if (drag.mode === "orbit") setGoal(orbitBy(goal, dx, dy));
        else setGoal(panBy(goal, dx, dy, sizeRef.current.heightCss));
        return;
      }
      // Hover picking is skipped mid-drag: a pick pass per frame is feedback nobody is looking at
      // while the camera is spinning.
      const target = pickAt(point.x, point.y)?.target ?? null;
      if (!samePickTarget(target, hoverRef.current)) {
        hoverRef.current = target;
        setHover(target);
        onHoverChangeRef.current?.(target);
      }
    },
    [canvasPoint, pickAt, setGoal],
  );

  const endDrag = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const drag = dragRef.current;
      dragRef.current = null;
      if (canvasRef.current?.hasPointerCapture(event.pointerId)) {
        canvasRef.current.releasePointerCapture(event.pointerId);
      }
      if (!drag || drag.mode !== "orbit") return;
      const point = canvasPoint(event);
      // Only a press that did not travel counts as a click. Without this, every orbit that happens
      // to end over an electrode also selects it.
      if (Math.abs(point.x - drag.startX) + Math.abs(point.y - drag.startY) > 3) return;
      const camera = cameraRef.current;
      const size = sizeRef.current;
      // Depth on every click, whether or not this caller passes `onPickAt`: a click is a handful
      // per minute, the extra pass is three pixels wide, and making the world point conditional on
      // a prop would mean the same click reports a different amount depending on who mounted the
      // pane — including the debug handle a test reads.
      const hit = pickAt(point.x, point.y, true);
      const target = hit?.target ?? null;
      if (camera) {
        // Where, not just what (`ScenePick`). The depth the pick pass rasterised is the renderer's
        // own answer — the same fragment that decided *which* region — so the point cannot drift
        // from the selection the click made.
        const pick: ScenePick = {
          target,
          xCss: point.x,
          yCss: point.y,
          world:
            hit && hit.ndcDepth !== null
              ? unprojectDepth(camera, point.x, point.y, size.widthCss, size.heightCss, hit.ndcDepth)
              : null,
          ray: screenRay(camera, point.x, point.y, size.widthCss, size.heightCss),
          camera,
        };
        lastPickRef.current = pick;
        onPickAt?.(pick);
      }
      applyPick(target);
    },
    [applyPick, canvasPoint, onPickAt, pickAt],
  );

  const onPointerLeave = useCallback(() => {
    if (dragRef.current) return;
    if (hoverRef.current !== null) {
      hoverRef.current = null;
      setHover(null);
      onHoverChangeRef.current?.(null);
    }
  }, []);

  const applyPreset = useCallback(
    (next: CameraPreset) => {
      const size = sizeRef.current;
      setPreset(next);
      framedRef.current = true;
      setGoal(presetCamera(next, framingBounds, size.widthCss / Math.max(1, size.heightCss), DEFAULT_FOV_Y, fitPoints));
    },
    [fitPoints, framingBounds, setGoal],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLCanvasElement>) => {
      const goal = goalRef.current;
      if (!goal) return;
      const step = event.shiftKey ? 40 : 12;
      const orbit = (dx: number, dy: number) => {
        setPreset("");
        framedRef.current = false;
        setGoal(orbitBy(goal, dx, dy));
      };
      const zoom = (delta: number) => {
        setPreset("");
        framedRef.current = false;
        setGoal(zoomBy(goal, delta, radius));
      };
      const actions: Record<string, () => void> = {
        ArrowLeft: () => orbit(-step, 0),
        ArrowRight: () => orbit(step, 0),
        ArrowUp: () => orbit(0, -step),
        ArrowDown: () => orbit(0, step),
        "+": () => zoom(-60),
        "=": () => zoom(-60),
        "-": () => zoom(60),
        "1": () => applyPreset("front"),
        "2": () => applyPreset("left"),
        "3": () => applyPreset("right"),
        "4": () => applyPreset("top"),
        "0": () => applyPreset("reset"),
        Escape: () => {
          const next = selectionReducer(selectionRef.current, { type: "clear" }, rules);
          if (next === selectionRef.current) return;
          setInternalSelection(next);
          onSelectionChange?.(next);
        },
      };
      const action = actions[event.key];
      if (!action) return;
      event.preventDefault();
      action();
    },
    [applyPreset, onSelectionChange, radius, rules, setGoal],
  );

  const setOpacity = useCallback((partId: string, value: number) => {
    setOpacities((previous) => ({ ...previous, [partId]: value }));
    sceneRef.current?.setOpacity(partId, value);
  }, []);

  // --- the dev/e2e handle ---------------------------------------------------------------------
  useEffect(() => {
    if (!SCENE_DEBUG || !publishDebugHandle) return;
    const handle: SceneDebugHandle = {
      get ready() {
        return sceneRef.current !== null && cameraRef.current !== null && frameRef.current > 0;
      },
      get webgl2() {
        return sceneRef.current !== null;
      },
      get contextLost() {
        return sceneRef.current?.gl.isContextLost() ?? false;
      },
      get mode() {
        return mode;
      },
      get parts() {
        return parts.map((part) => ({
          id: part.id,
          triangles: part.indices.length / 3,
          vertices: part.positions.length / 3,
          opacity: opacities[part.id] ?? part.opacity,
        }));
      },
      get markers() {
        return markers.map((marker, index) => ({ index, id: marker.id, world: marker.world }));
      },
      get selection() {
        return selectionRef.current;
      },
      get hover() {
        return hoverRef.current;
      },
      get lastPick() {
        return lastPickRef.current;
      },
      get camera() {
        const camera = cameraRef.current ?? presetCamera("reset", sceneBounds, 1, DEFAULT_FOV_Y);
        return { ...camera, settled: settledRef.current };
      },
      get canvas() {
        return { ...sizeRef.current };
      },
      get fps() {
        return fpsRef.current.fps;
      },
      get frames() {
        return frameRef.current;
      },
      get stats() {
        const empty: SceneStats = { triangles: 0, vertices: 0, markers: 0, drawCalls: 0, lastFrameMs: 0 };
        return { ...(sceneRef.current?.stats ?? empty) };
      },
      project(world) {
        const camera = cameraRef.current;
        const size = sizeRef.current;
        if (!camera) return { x: NaN, y: NaN, inFront: false };
        const projected = projectToCanvas(camera, world, size.widthCss, size.heightCss);
        return { x: projected.x, y: projected.y, inFront: projected.inFront };
      },
      samplePixels(points, withMarkers = true) {
        const scene = sceneRef.current;
        const camera = cameraRef.current;
        if (!scene || !camera) return null;
        const read = scene.samplePixels(camera, points, { markers: withMarkers });
        // Plain arrays, not typed ones: this crosses Playwright's structured clone, which turns a
        // `Uint8Array` into `{"0":…}` and makes every assertion read like a puzzle.
        return read ? read.map((rgba) => Array.from(rgba)) : null;
      },
      setMarkerOcclusion(occluded) {
        const scene = sceneRef.current;
        if (!scene) return false;
        scene.setMarkerOcclusion(occluded);
        return true;
      },
      loseContext() {
        const ext = sceneRef.current?.loseContextExtension;
        if (!ext) return false;
        ext.loseContext();
        return true;
      },
      restoreContext() {
        // The extension object captured at creation, never re-fetched: `getExtension` answers null
        // once the context is lost, so a lazily fetched handle can lose a context and then never
        // restore it.
        const ext = sceneRef.current?.loseContextExtension;
        if (!ext) return false;
        ext.restoreContext();
        return true;
      },
    };
    window.__scene = handle;
    return () => {
      if (window.__scene === handle) delete window.__scene;
    };
  }, [markers, mode, opacities, parts, sceneBounds, publishDebugHandle]);

  // --- render ---------------------------------------------------------------------------------
  const legendRows = useMemo<LegendEntry[]>(() => {
    const rows: LegendEntry[] = parts.map((part) => ({
      key: part.id,
      label: part.label,
      color: part.color,
      detail: `${formatCount(part.indices.length / 3)} tri`,
    }));
    if (markers.length > 0) {
      rows.push({
        key: "markers",
        label: "Markers",
        color: [0.85, 0.87, 0.9],
        detail:
          activeSelection.markers.length > 0
            ? `${activeSelection.markers.length} of ${markers.length} selected`
            : `${markers.length}`,
      });
    }
    if (activeSelection.regions.length > 0) {
      rows.push({
        key: "regions",
        label: "Highlighted regions",
        color: [0.5, 0.65, 1],
        detail: `${activeSelection.regions.length}`,
      });
    }
    return legend ? [...rows, ...legend] : rows;
  }, [activeSelection, legend, markers.length, parts]);

  if (webgl2 === false) {
    // Decision S6, the one readable line. The page keeps working: every selection this pane could
    // have made is in the form, and the legend still says what the pane would have drawn.
    return (
      <div className={`scene-pane scene-pane-fallback ${className ?? ""}`} data-testid="scene-fallback">
        <p className="scene-fallback-line">
          3D preview unavailable — this display has no WebGL2. Everything the preview selects is also in
          the form beside it.
        </p>
        <ul className="scene-legend scene-legend-static" data-testid="scene-legend">
          {legendRows.map((row) => (
            <li key={row.key}>
              <span className="scene-legend-label">{row.label}</span>
              {row.detail && <span className="scene-legend-detail">{row.detail}</span>}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className={`scene-pane ${className ?? ""}`} ref={wrapRef} data-testid="scene-pane" data-mode={mode}>
      <canvas
        ref={canvasRef}
        className="scene-canvas"
        data-testid="scene-canvas"
        tabIndex={0}
        role="application"
        aria-label={label}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={onPointerLeave}
        onKeyDown={onKeyDown}
        onContextMenu={(event) => event.preventDefault()}
      />

      <div className="scene-chrome scene-chrome-top">
        <SegmentedControl
          aria-label="Camera preset"
          size="sm"
          value={preset}
          onValueChange={(value) => applyPreset(value as CameraPreset)}
          options={PRESET_OPTIONS}
        />
        <Button size="sm" variant="ghost" onClick={() => applyPreset("reset")} title="Reset view — 0">
          Reset
        </Button>
      </div>

      {/* Which way round the subject is. A 3-D head view has no universal convention — from the
          front you face the subject, so their left is on your right; from above, looking down, it
          is on your left — and a viewer that does not state which one it is showing is a viewer
          nobody can trust. Derived from the live camera, so it cannot drift from the projection. */}
      {orientation && (
        <p className="scene-orientation" data-testid="scene-orientation" title={orientation.title}>
          {orientation.caption}
        </p>
      )}

      <div className="scene-chrome scene-chrome-bottom">
        <ul className="scene-legend" data-testid="scene-legend">
          {legendRows.map((row) => (
            <li key={row.key}>
              <span className="scene-legend-swatch" style={{ background: swatch(row.color) }} aria-hidden />
              <span className="scene-legend-label">{row.label}</span>
              {row.detail && <span className="scene-legend-detail">{row.detail}</span>}
            </li>
          ))}
        </ul>
        <div className="scene-opacity" data-testid="scene-opacity">
          {parts.map((part) => (
            <div key={part.id} className="scene-opacity-row">
              <span className="scene-opacity-label">{part.label}</span>
              <Slider
                aria-label={`${part.label} opacity`}
                value={Math.round((opacities[part.id] ?? part.opacity) * 100)}
                onValueChange={(value) => setOpacity(part.id, value / 100)}
                min={0}
                max={100}
                step={1}
                showNumberInput={false}
              />
            </div>
          ))}
        </div>
      </div>

      {contextLost && (
        <div className="scene-overlay" data-testid="scene-context-lost">
          <p>The graphics context was lost. The view restores itself as soon as the driver hands it back.</p>
        </div>
      )}
    </div>
  );
}
