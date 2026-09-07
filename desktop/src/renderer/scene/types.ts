/**
 * The data the scene draws. Decoded arrays only — this module never fetches, never parses a path
 * and never knows a subject id (plan S1: it is a form control, not a viewer).
 */
import type { Bounds, OrbitCamera, Ray, Vec3 } from "./camera";
import type { PickTarget } from "./pickId";

/** 0..1 per channel, sRGB. Shaders want numbers, so the palette is numeric (`palette.ts`) and the
 *  CSS tokens it mirrors are named there. */
export type Rgb = [number, number, number];

/** One triangle surface. Two of them at most, in practice: skin and grey matter. */
export interface ScenePart {
  /** Stable id — "skin", "gm". Also the key for the opacity control and the legend row. */
  id: string;
  /** Legend text. */
  label: string;
  positions: Float32Array;
  indices: Uint32Array;
  /** Per-vertex atlas label ids; `null` on a part with no atlas (the skin). */
  labels?: Uint16Array | null;
  /** Precomputed normals. Omit and the renderer computes them once on upload. */
  normals?: Float32Array | null;
  color: Rgb;
  /** 0..1. The per-surface opacity control writes this, unless `opacityLocked`. */
  opacity: number;
  /** Fixed at `opacity`: no slider is offered and no page-session value can override it. The grey
   *  matter is locked opaque — it is the anatomy being aimed at, not a veil over something else. */
  opacityLocked?: boolean;
  /**
   * Painter's order, smallest first. Two nested translucent shells are drawn inner-then-outer with
   * depth writes off; drawn the other way round the outer shell's fragments reject the inner one's
   * and the brain disappears inside the head.
   */
  order?: number;
}

/** A point marker: an electrode, or a sphere centre. */
export interface SceneMarker {
  /** Stable id — the electrode name ("Fp1"). What `onSelectionChange` reports back up. */
  id: string;
  label: string;
  world: Vec3;
  /** Channel/pair index, coloured from `palette.channels`. Undefined = unassigned. */
  channel?: number;
}

/** One row of the legend. The legend is DOM, not painted into the canvas: a painted legend cannot
 *  be read by a test, translated, or selected, and it has to be re-implemented for every theme. */
export interface LegendEntry {
  key: string;
  label: string;
  color: Rgb;
  /** Right-aligned count or note ("77 032 triangles", "2 selected"). */
  detail?: string;
}

/**
 * A pick, with the *place* it happened — what `onPickAt` reports (lane SCC's request, §6.1 of
 * `dev/notes/v3-scene-ia/scc-notes.md`).
 *
 * `onPick` answers "which region", which is enough to add a region to an ROI and not enough to put
 * a sphere centre where the user clicked. This carries the world point under the cursor as well, so
 * a page can write it straight into a form field, plus the ray it came from — for a caller that
 * wants to intersect its own geometry (a plane, a saved ROI) rather than the surface that was hit.
 */
export interface ScenePick {
  /** What was hit; `null` for empty space (which is still reported, so a caller can clear). */
  target: PickTarget | null;
  /** Cursor position in canvas CSS pixels. */
  xCss: number;
  yCss: number;
  /**
   * The world point (subject RAS, mm) on the anatomy under the cursor — `null` only when the ray
   * missed everything. It is on `ray`, at the depth the renderer's own pick pass rasterised.
   *
   * Independent of `target`: `target` names what is *selectable* in this mode (and is `null` in a
   * mode that selects nothing), while `world` is simply where the click landed.
   */
  world: Vec3 | null;
  /** The camera ray through that pixel. */
  ray: Ray;
  /** The camera at the moment of the pick — everything else here is derived from it, and a caller
   *  that wants to re-derive anything should use this rather than read the camera back later. */
  camera: OrbitCamera;
}

export interface SceneStats {
  /** Triangles actually uploaded to the GPU, summed over parts. */
  triangles: number;
  vertices: number;
  markers: number;
  drawCalls: number;
  /** Milliseconds of the last `render()` call, measured on the CPU side of the submit. */
  lastFrameMs: number;
}

export type { Bounds, OrbitCamera, Ray, Vec3 };
