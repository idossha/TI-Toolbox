/**
 * The WebGL2 half of the slim scene (plan S4). Four draws and nothing else.
 *
 * No runtime dependency: no three.js, no `@tetravox/*`, no matrix library — `camera.ts` is the
 * only maths and it is pure. Everything stateful is here, and everything here is stateful, so the
 * parts a test needs to reason about (camera, parser, normals, pick ids, selection) can be tested
 * with no GPU at all and this file is exercised end to end by one offscreen Electron run.
 *
 * ## Draw order, and why
 *
 * Nested shells and a set of markers that sit ON the outer one:
 *
 *  1. Every **opaque** surface (opacity 1), one plain draw each, blending off, depth test and
 *     depth WRITE on — so it hides its own inner sheets and everything behind it.
 *  2. The **second-nearest sheet** of every translucent surface, outermost first, depth test on
 *     (against 1), write OFF.
 *  3. The **nearest sheet** of every translucent surface, innermost first, depth test on, write OFF.
 *  4. A **depth-only pre-pass** of every surface, both faces, colour writes off and depth writes
 *     on, pushed `MARKER_OCCLUSION_BIAS_MM` away from the eye.
 *  5. **Markers**, depth-tested against that, depth write on.
 *
 * Step 1 exists because opacity 1 was not enough on its own: the sheet path weights alpha by a
 * fresnel term (`alpha * (0.42 + 0.58 * fresnel)`), so a face-on fragment of a surface asked to be
 * opaque was drawn at alpha 0.42 and the sheets behind it showed through — the grey matter's inner
 * layers reading through its outer surface (maintainer, 2026-09-06). It is also the cheap path: one
 * draw instead of five.
 *
 * ## Resolving sheets before blending (2026-09-06)
 *
 * Steps 2 and 3 used to be *"back faces, then front faces"* — `cullFace(FRONT)` then
 * `cullFace(BACK)`, which is exact only for a closed shell whose triangles are all wound outward.
 * Neither of ours is: SimNIBS' grey matter is a folded, partly inward-wound open surface, so a
 * single culled draw rasterises **every** triangle the ray crosses inside a gyrus and blends them
 * in triangle-buffer order. That is the artefact the maintainer photographed on the Optimizer pane:
 * shards of cortex showing through the scalp and jagged holes where skin, GM and a tinted region
 * overlap, changing shape as the camera moves because the order is the buffer's, not the eye's.
 *
 * The fix is Tetravox's, ported (their `packages/engine/src/render/surface-depth.ts`,
 * `render/passes/mesh.ts` and `shaders/mesh.ts` at `829cd08`, ARCHITECTURE §7.2): **resolve which
 * depth sheet a pixel shows before blending anything into it.** Per surface, per phase:
 *
 *   a. render the surface depth-only into an off-screen `DEPTH_COMPONENT24` texture with culling
 *      disabled — that texture now holds the depth of the **nearest** sheet at every pixel;
 *   b. for the far phase, render it depth-only again, discarding every fragment at or in front of
 *      that first depth — a one-layer depth peel, giving the **second-nearest** sheet;
 *   c. render the surface for colour with culling still disabled, discarding every fragment whose
 *      `gl_FragCoord.z` differs from the resolved sheet by more than one depth24 step.
 *
 * Exactly one fragment per pixel per sheet therefore survives, so a translucent surface composites
 * as two smooth sheets — the near wall of the fold and the far one — with no dependence on winding
 * and with no triangle ever sorted on the CPU. It is a *bounded* two-sheet approximation, exactly
 * as §7.2 says: a third crossing deeper inside a sulcus is dropped rather than mis-ordered, which
 * is the trade a translucent anatomical shell wants.
 *
 * Ordering between surfaces is unchanged and is what the two phases are for: far sheets outermost
 * first, near sheets innermost first, which is back-to-front for nested shells.
 *
 * The cost is one extra rasterisation of each surface per frame (three depth-only passes and one
 * colour pass per surface, against two colour passes before) plus two screen-sized depth textures,
 * reallocated only on resize.
 *
 * Steps 1 and 2 are back-to-front for nested closed shells without sorting a single triangle. Depth
 * writes stay off there because a translucent fragment that writes depth rejects everything behind
 * it — the grey matter vanishes inside the head, which is exactly the bug that ordering exists to
 * prevent, and it is also why step 3 cannot come first: a depth buffer holding the nearest surface
 * would reject the back faces and the whole inner shell.
 *
 * Steps 3 and 4 are the fix for the defect the maintainer reported on 2026-09-04 — *"the EEG net
 * visualisation looks wrong; the electrode positions look wrong"*. The markers used to be drawn
 * FIRST, opaque and depth-writing, on the premise that the thing being chosen must never be hidden
 * by anatomy. The cost of that premise, measured on the gallery fixture from the front preset:
 * **12 of 12 electrodes on the far hemisphere were painted over the head** (up to 157/255 per
 * channel through two translucent shells), 112 to 190 mm behind the scalp the ray crossed first. A
 * user therefore saw all 75 electrodes of a net at once, front and back superimposed, which is what
 * "the positions look wrong" means. Composing the head first and only then filling the depth buffer
 * keeps both properties: the shells still show through each other, and a marker behind the scalp is
 * hidden by it.
 *
 * ## Picking
 *
 * A second pass into an off-screen RGBA8 framebuffer writes a 24-bit id per fragment (`pickId.ts`)
 * and reads back one pixel. It is scissored to a 3x3 box around the cursor, so the fragment cost is
 * three pixels however large the surfaces are, and it uses the *same* matrices as the visible pass,
 * so what the user clicked and what the renderer thinks they clicked cannot drift.
 *
 * It also uses the same **faces**: both of them, like the visible pass, never the front ones only.
 * That is `drawPickSequence`'s job and its comment says what culling them cost.
 *
 * Region ids come from a `flat`-qualified per-vertex label varying: flat means the provoking
 * vertex's label wins for the whole triangle instead of being interpolated into a meaningless
 * average across a region boundary. That is a WebGL2-only qualifier and is the reason this is not
 * a WebGL1 renderer.
 *
 * A pick can also report *where*, not just *what*: with `PickOptions.depth` the same sequence runs
 * a second time writing the packed window depth instead of the id, and `camera.ts`'s
 * `unprojectDepth` turns that one number into the world point under the cursor.
 */
import { multiply, perspective, viewMatrix, type Mat4, type OrbitCamera } from "./camera";
import { orientFacesToMajorityLabel } from "./labelFaces";
import { computeVertexNormals } from "./normals";
import { decodePickPixel, PICK_KIND_MARKER, PICK_KIND_REGION, type PickTarget } from "./pickId";
import { MARKER_SIZE_PX, SCENE_PALETTE, type ScenePalette } from "./palette";
import type { ScenePart, SceneMarker, SceneStats } from "./types";

/**
 * How far the depth-only pre-pass pushes the surfaces away from the eye before a marker is tested
 * against them, in world millimetres (§"Draw order" step 3).
 *
 * Without it an electrode would have to be strictly in front of the scalp to survive, and it is
 * not: the served skin is a *simplified* surface, so an electrode projected onto the original mesh
 * lands within 1.81 mm of it on either side (lane SCA's measurement over every net of every
 * subject). At a bias of 0 roughly half of every net would be culled by a fraction of a millimetre
 * of decimation error — a far worse defect than the one this fix is for.
 *
 * 4 mm is therefore more than twice the worst measured error, and two orders of magnitude below the
 * ~190 mm an electrode on the far hemisphere sits behind the near scalp, so it separates "sitting
 * on the surface" from "behind the head" with a wide margin at both ends. It is applied as a
 * translation along the view axis, so it is the same number of millimetres everywhere in the frame
 * rather than a `polygonOffset` in unresolvable depth units nobody can state in mm.
 */
export const MARKER_OCCLUSION_BIAS_MM = 4;

/** Label-state texture: 256x256 R8UI covers every `uint16` label id in 64 KB. */
const LABEL_TEX_SIDE = 256;
export const LABEL_STATE_SIZE = LABEL_TEX_SIDE * LABEL_TEX_SIDE;
/** Bits in a label-state byte. */
export const LABEL_SELECTED = 1;
export const LABEL_HOVER = 2;
export const LABEL_DIMMED = 4;

/** Marker-state bits; the channel index + 1 lives above bit 8. */
export const MARKER_SELECTED = 1;
export const MARKER_HOVER = 2;
export const markerStateChannel = (channel: number | undefined): number =>
  channel === undefined ? 0 : (Math.max(0, Math.floor(channel)) + 1) << 8;

const SURFACE_VS = `#version 300 es
precision highp float;
precision highp int;
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
layout(location=2) in uint aLabel;
uniform mat4 uViewProj;
uniform mat4 uView;
uniform bool uUseLabels;
uniform highp usampler2D uLabelState;
out vec3 vNormalView;
out vec3 vViewDir;
flat out highp uint vLabel;
// 1 at a selected vertex, 0 at an unselected one, interpolated across a triangle that straddles
// the boundary of the selection. It is a SIGNED FIELD whose 0.5 contour is the boundary, not a
// membership test: what reads it is fwidth(), which turns the contour into a line of constant
// SCREEN width. The colour of a fragment never comes from it -- that is vLabel's job, and vLabel
// is flat, so a boundary triangle is entirely one region's colour and never a blend of two.
//
// The distinction cost a defect on 2026-09-06. Treating 0 < vSelect < 1 as "on the rim" paints the
// WHOLE of every boundary triangle, and a decimated cortex has long thin ones: the maintainer saw
// a jagged white border of uncoloured shards around every selected label, not an outline.
out float vSelect;
void main() {
  vec4 viewPos = uView * vec4(aPos, 1.0);
  vNormalView = mat3(uView) * aNormal;
  vViewDir = -viewPos.xyz;
  vLabel = aLabel;
  float sel = 0.0;
  if (uUseLabels) {
    uint s = texelFetch(uLabelState, ivec2(int(aLabel & 255u), int(aLabel >> 8u)), 0).r;
    sel = ((s & 1u) != 0u) ? 1.0 : 0.0;
  }
  vSelect = sel;
  gl_Position = uViewProj * vec4(aPos, 1.0);
}`;

/**
 * The tolerance on a resolved sheet depth, as a fraction of the window-depth range.
 *
 * Tetravox compares for *equality* within one depth24 step (`1/16777215`), which works because its
 * pre-pass and its colour pass rasterise into buffers of the same sample count. Ours do not: the
 * canvas is created with `antialias: true`, so the colour pass writes into a **multisampled**
 * buffer while the pre-pass writes into a single-sampled depth texture. At a triangle edge a
 * multisample fragment is shaded once for partial coverage and its `gl_FragCoord.z` is the pixel
 * centre's, which can sit a long way from the depth the single-sampled pre-pass recorded for the
 * same pixel — measured on the folded fixture, up to 19/255 of colour error appearing as a dropped
 * fragment at every facet edge of the 64x32 grid.
 *
 * So the test is a **bound**, not an equality: keep what is at or in front of the resolved sheet
 * and drop what is behind it. The pre-pass recorded the minimum depth over the surface, so nothing
 * can be meaningfully in front of it, and the bound admits exactly one sheet while being blind to
 * the sub-pixel disagreement multisampling introduces. `1e-5` of the [0, 1] window range is about
 * 170 depth24 steps — three orders of magnitude above the quantisation, and (at the near/far
 * planes `projection` sets for a head) three orders of magnitude below the millimetres that
 * separate one wall of a gyrus from the next.
 */
const SHEET_EPS = "1.0e-5";

/** Rest saturation of an atlas colour: enough hue to name the region, muted enough that the
 *  cortex still reads as anatomy rather than as a pie chart. */
const REST_SATURATION = "0.55";
/** …and how far it is dimmed towards the background at rest. */
const REST_VALUE = "0.86";

/**
 * Half-width, in pixels, of the selection outline — so the drawn line is ~2.4 px, which is one
 * clean edge at dpr 2 and a visible one at dpr 1.
 *
 * It is a screen-space width by construction (see the `fwidth` use below), which is the whole
 * correction: the outline this replaced was "every fragment of a triangle that straddles the
 * boundary", whose width on screen was the width of whatever triangle it landed on.
 */
const EDGE_PX = "1.2";

/**
 * The surface fragment shader, in two variants.
 *
 * `sheet` compiles in the §"Resolving sheets" discard: keep this fragment only if it is the sheet
 * the pre-pass resolved for this pixel. The opaque and pick paths do not want it, so it is a
 * compile-time branch rather than a uniform — a `discard` behind a runtime `if` costs every
 * fragment of every pass the early-z it would otherwise keep.
 */
const surfaceFs = (sheet: "none" | "near" | "peeled"): string => `#version 300 es
precision highp float;
precision highp int;
in vec3 vNormalView;
in vec3 vViewDir;
in float vSelect;
flat in highp uint vLabel;
uniform vec3 uBaseColor;
uniform vec3 uSelectedColor;
uniform vec3 uHoverColor;
uniform vec3 uDimColor;
uniform float uOpacity;
uniform bool uUseLabels;
uniform highp usampler2D uLabelState;
uniform sampler2D uLabelColor;
${sheet === "none" ? "" : "uniform highp sampler2D uSheetDepth;"}
${sheet === "peeled" ? "uniform highp sampler2D uSheetPeel;" : ""}
out vec4 outColor;
void main() {
${
  sheet === "none"
    ? ""
    : `  // One sheet per pixel: anything behind the depth the pre-pass resolved is a buried
  // triangle, whatever its winding.
  float sheetZ = texelFetch(uSheetDepth, ivec2(gl_FragCoord.xy), 0).r;
  if (gl_FragCoord.z > sheetZ + ${SHEET_EPS}) discard;`
}
${
  sheet === "peeled"
    ? `  // …and, for the second sheet, anything at or in front of the FIRST one, which the near
  // phase has already drawn.
  float firstZ = texelFetch(uSheetPeel, ivec2(gl_FragCoord.xy), 0).r;
  if (gl_FragCoord.z <= firstZ + ${SHEET_EPS}) discard;`
    : ""
}
  vec3 N = normalize(vNormalView);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(vViewDir);
  // A fixed head light in view space: the light follows the camera, so nothing the user orbits to
  // is ever in shadow. A fixed WORLD light leaves the far side of the head unreadably black.
  vec3 L = normalize(vec3(0.32, 0.38, 1.0));
  vec3 color = uBaseColor;
  float alpha = uOpacity;
  bool solid = false;
  if (uUseLabels) {
    ivec2 uv = ivec2(int(vLabel & 255u), int(vLabel >> 8u));
    uint s = texelFetch(uLabelState, uv, 0).r;
    // The label's own colour, straight out of the .annot colour table (or the volume LUT), which
    // setLabelColors uploaded at the same index as its state. Label 0 is "no region" and its
    // texel is left black, which is how a fragment says it has no atlas colour of its own.
    vec3 atlas = texelFetch(uLabelColor, uv, 0).rgb;
    bool tinted = vLabel != 0u && any(greaterThan(atlas, vec3(0.0)));
    if (tinted) {
      // At rest: the atlas hue, desaturated towards its own luma and dimmed a little, so a
      // parcellated cortex still reads as a cortex.
      float luma = dot(atlas, vec3(0.2126, 0.7152, 0.0722));
      color = mix(vec3(luma), atlas, ${REST_SATURATION}) * ${REST_VALUE};
    }
    if ((s & 4u) != 0u) color = uDimColor;
    if ((s & 1u) != 0u) {
      // Selected: the label's OWN colour at full saturation, never a uniform blue.
      color = tinted ? atlas : uSelectedColor;
      solid = true;
    }
    if ((s & 2u) != 0u) {
      // Hover: the same colour, brightened. An atlas colour brightened towards white stays the
      // same hue, so hovering never renames a region.
      color = tinted ? mix(atlas, vec3(1.0), 0.45) : uHoverColor;
      solid = true;
    }
  }
  float lambert = max(dot(N, L), 0.0);
  // Silhouette boost: a constant-alpha shell reads as fog, a fresnel-weighted one reads as a
  // surface with an edge, which is what makes a translucent shell legible at 0.22 opacity.
  float fresnel = pow(1.0 - abs(dot(N, V)), 1.6);
  vec3 shaded = color * (0.30 + 0.70 * lambert) + vec3(0.09) * fresnel;
  // The "none" variant IS the opaque path: fully opaque, whatever uOpacity says. The fresnel
  // weighting below multiplies a face-on fragment's alpha by 0.42, so a surface asked to be
  // opaque still showed the sulcal walls behind it — the bleed-through the grey matter had.
${
  sheet === "none"
    ? "  float a = 1.0;"
    : "  float a = solid ? max(alpha, 0.92) : clamp(alpha * (0.42 + 0.58 * fresnel), 0.0, 1.0);"
}
  if (uUseLabels) {
    // The selection outline: the 0.5 contour of vSelect, drawn EDGE_PX wide in screen space.
    //
    // fwidth(vSelect) is how much the field changes across one pixel, so dividing the distance to
    // the contour by it converts "how far am I from the boundary, in field units" into "how far am
    // I from the boundary, in pixels" — which is why the line is the same weight on a huge triangle
    // and on a sliver, and why it cannot swallow a boundary triangle whole the way a plain
    // 0 < vSelect < 1 test did. Where nothing is selected, or everything is, the field is constant,
    // fwidth is 0, and the guard leaves the line off entirely.
    float width = fwidth(vSelect);
    float edge = width > 1.0e-5
      ? 1.0 - smoothstep(0.0, width * ${EDGE_PX}, abs(vSelect - 0.5))
      : 0.0;
    // DARKENED, not whitened. A dark line reads as a border against every atlas colour, including
    // the light ones; the white it replaced was indistinguishable from a specular highlight and,
    // being lighter than most of the palette, is what made the shards so loud. Selection is
    // therefore carried by three signals — full saturation, raised opacity and this line — so it
    // survives any colour vision without hue doing the work.
    shaded = mix(shaded, shaded * 0.12, edge);
    a = max(a, edge * 0.95);
  }
  outColor = vec4(shaded, a);
}`;

/**
 * The depth-only pre-pass (§"Resolving sheets" step a). It writes no colour at all: the framebuffer
 * it renders into has `drawBuffers([NONE])` and only a depth attachment, so the fragment shader has
 * no output and the whole pass costs the vertex work plus depth writes.
 *
 * It must produce *exactly* the depth the colour pass will compute, which it does by construction —
 * same vertex shader, same uniforms, and no `discard` anywhere in the surface colour path.
 */
const SHEET_DEPTH_FS = `#version 300 es
precision highp float;
void main() {}`;

/** The same, peeling one layer: keep only what is strictly behind the sheet already resolved, so
 *  the result is the second-nearest sheet (§"Resolving sheets" step b). */
const SHEET_PEEL_FS = `#version 300 es
precision highp float;
uniform highp sampler2D uSheetDepth;
void main() {
  float first = texelFetch(uSheetDepth, ivec2(gl_FragCoord.xy), 0).r;
  if (gl_FragCoord.z <= first + ${SHEET_EPS}) discard;
}`;

const SURFACE_PICK_FS = `#version 300 es
precision highp float;
precision highp int;
flat in highp uint vLabel;
uniform uint uKind;
out vec4 outColor;
void main() {
  uint id = (uKind << 20) | (vLabel & 1048575u);
  outColor = vec4(float(id & 255u), float((id >> 8u) & 255u), float((id >> 16u) & 255u), 255.0) / 255.0;
}`;

const MARKER_VS = `#version 300 es
precision highp float;
precision highp int;
layout(location=0) in vec2 aCorner;
layout(location=1) in vec3 aCenter;
layout(location=2) in uint aState;
layout(location=3) in uint aIndex;
uniform mat4 uViewProj;
uniform vec2 uViewportPx;
uniform float uSizePx;
uniform vec3 uMarkerColor;
uniform vec3 uSelectedColor;
uniform vec3 uHoverColor;
uniform vec3 uChannel0;
uniform vec3 uChannel1;
uniform vec3 uChannel2;
uniform vec3 uChannel3;
uniform vec3 uChannel4;
uniform vec3 uChannel5;
out vec2 vCorner;
out vec3 vColor;
flat out highp uint vIndex;
flat out highp uint vState;
void main() {
  vec4 clip = uViewProj * vec4(aCenter, 1.0);
  // Hover grows the dot; SELECTION does not. Selection is said in hue alone (the pane's whole
  // electrode contract): a selected marker keeps
  // the idle one's footprint exactly, which is what makes "no ring, no second glyph" a pixel test
  // — the changed pixels are one solid disc with the same bounding box, not a disc plus a band.
  float scale = ((aState & 2u) != 0u) ? 1.25 : 1.0;
  // Screen-constant size without gl_PointSize: offsetting clip.xy by (ndc offset * w) survives the
  // perspective divide exactly, and an instanced quad has none of the driver-dependent point-sprite
  // behaviour (clamped sizes, missing gl_PointCoord) that would make a marker unpickable on one GPU.
  clip.xy += (aCorner * (uSizePx * scale) / uViewportPx * 2.0) * clip.w;
  gl_Position = clip;
  vCorner = aCorner * 2.0;
  uint ch = aState >> 8u;
  vec3 c = uMarkerColor;
  if (ch == 1u) c = uChannel0;
  else if (ch == 2u) c = uChannel1;
  else if (ch == 3u) c = uChannel2;
  else if (ch == 4u) c = uChannel3;
  else if (ch == 5u) c = uChannel4;
  else if (ch >= 6u) c = uChannel5;
  if ((aState & 1u) != 0u && ch == 0u) c = uSelectedColor;
  if ((aState & 2u) != 0u) c = uHoverColor;
  vColor = c;
  vIndex = aIndex;
  vState = aState;
}`;

const MARKER_FS = `#version 300 es
precision highp float;
precision highp int;
in vec2 vCorner;
in vec3 vColor;
out vec4 outColor;
void main() {
  float r = length(vCorner);
  if (r > 1.0) discard;
  vec3 c = vColor * (0.78 + 0.22 * (1.0 - r));
  outColor = vec4(c, smoothstep(1.0, 0.80, r));
}`;

const MARKER_PICK_FS = `#version 300 es
precision highp float;
precision highp int;
in vec2 vCorner;
flat in highp uint vIndex;
out vec4 outColor;
void main() {
  if (length(vCorner) > 1.0) discard;
  uint id = (1u << 20) | (vIndex & 1048575u);
  outColor = vec4(float(id & 255u), float((id >> 8u) & 255u), float((id >> 16u) & 255u), 255.0) / 255.0;
}`;

/**
 * Depth, packed into the four bytes of the same RGBA8 pick target.
 *
 * `gl_FragCoord.z` is the window depth in [0, 1]; splitting it over four channels keeps 32 bits of
 * fixed point, which at the distance a head is viewed from is a few microns — far below the
 * quantisation of anything the answer is used for. The subtraction is the standard carry-removal:
 * without it each channel keeps the higher channels' fraction and the decode drifts.
 *
 * A separate pass rather than a second colour attachment: the pass is three pixels wide (the pick
 * is scissored), so a second rasterisation of the same geometry costs the vertex work and nothing
 * else, and MRT would have made every other draw in this file declare two outputs.
 */
const DEPTH_FS = `#version 300 es
precision highp float;
out vec4 outColor;
void main() {
  vec4 enc = fract(gl_FragCoord.z * vec4(1.0, 255.0, 65025.0, 16581375.0));
  enc -= enc.yzww * vec4(1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0, 0.0);
  outColor = enc;
}`;

/** The same, for a marker: the round cutout has to be identical to `MARKER_PICK_FS`'s or the depth
 *  would be read from a corner of the quad the id pass discarded. */
const MARKER_DEPTH_FS = `#version 300 es
precision highp float;
in vec2 vCorner;
out vec4 outColor;
void main() {
  if (length(vCorner) > 1.0) discard;
  vec4 enc = fract(gl_FragCoord.z * vec4(1.0, 255.0, 65025.0, 16581375.0));
  enc -= enc.yzww * vec4(1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0, 0.0);
  outColor = enc;
}`;

/** Inverse of the packing above: four bytes -> window depth in [0, 1]. */
export function decodePackedDepth(pixel: Uint8Array | Uint8ClampedArray | number[]): number {
  const r = ((pixel[0] as number) ?? 0) / 255;
  const g = ((pixel[1] as number) ?? 0) / 255;
  const b = ((pixel[2] as number) ?? 0) / 255;
  const a = ((pixel[3] as number) ?? 0) / 255;
  return r + g / 255 + b / 65025 + a / 16581375;
}

export interface PickOptions {
  markers: boolean;
  regions: boolean;
  /** Also read back the depth of the winning fragment, so the caller can say *where* on the
   *  surface the click landed. Off for hover (it doubles the readback stall for feedback nobody
   *  acts on); on for a click. */
  depth?: boolean;
}

export interface PickResult {
  /** What was hit, or `null` for empty space. */
  target: PickTarget | null;
  /** Normalised device depth of the winning fragment, `null` when nothing was hit or the caller
   *  did not ask for it. `camera.ts`'s `unprojectDepth` turns it into a world point. */
  ndcDepth: number | null;
}

export interface GlScene {
  readonly gl: WebGL2RenderingContext;
  /**
   * `WEBGL_lose_context`, captured while the context was alive. Dev and e2e only — it is the only
   * way to exercise the loss/restore path deliberately, and it must be captured up front because
   * `getExtension` returns null on an already-lost context.
   */
  readonly loseContextExtension: WEBGL_lose_context | null;
  /** Uploads (or re-uploads) the surfaces. Normals are computed here when the part has none. */
  setParts(parts: ScenePart[]): void;
  setMarkers(markers: SceneMarker[]): void;
  /** One byte per marker: `MARKER_SELECTED | MARKER_HOVER | channelBits`. */
  setMarkerStates(states: Uint32Array): void;
  /** 65 536 bytes, indexed by label id: `LABEL_SELECTED | LABEL_HOVER | LABEL_DIMMED`. */
  setLabelStates(states: Uint8Array): void;
  /**
   * Three bytes per label id — the label's own RGB from the `.annot` colour table or the volume
   * LUT (`legend[].color` of `GET /api/{scene,guide}/regions`), packed by `buildLabelColors`.
   *
   * A label whose texel is black has no atlas colour and falls back to the part's flat tint and the
   * palette's selection blue, which is what a scene with no legend renders as.
   */
  setLabelColors(colors: Uint8Array): void;
  setOpacity(partId: string, opacity: number): void;
  /**
   * Whether the markers are hidden by the surfaces (default `true`, §"Draw order" step 3).
   *
   * `true` for markers that lie ON the anatomy — an EEG net, where an electrode round the back of
   * the head must be behind the head. `false` for a marker that names a point INSIDE it, which is
   * what the Analyzer's and Optimizer's sphere centre is: it sits in the brain by construction, so
   * occluding it would hide the only thing telling the user where they put it. It is a property of
   * what the markers *mean*, not of the renderer, and the two kinds are never mixed in one scene
   * (`ScenePane.tsx` draws either a net or a single sphere centre, never both).
   */
  setMarkerOcclusion(occluded: boolean): void;
  /** Backing-store size in device pixels; `cssWidth`/`cssHeight` set the projection's aspect. */
  resize(cssWidth: number, cssHeight: number, dpr: number): void;
  render(camera: OrbitCamera): void;
  /** `null` only when the pick could not run at all (disposed, lost context, cursor off the
   *  canvas); a click on empty space is a result with a `null` target. */
  pick(xCss: number, yCss: number, camera: OrbitCamera, options: PickOptions): PickResult | null;
  /**
   * Renders one frame and reads the drawing buffer back at the given canvas CSS points — the
   * "judge a number, not a picture" hook (`docs/PRINCIPLES.md` §7).
   *
   * It has to render the frame itself: the context is created with `preserveDrawingBuffer: false`,
   * so a `readPixels` from a later task reads a buffer the compositor has already discarded. Doing
   * the draw and the read in one call keeps them in the same task, which is the only place the
   * contents are defined.
   *
   * `options.markers: false` suppresses the marker pass, so a test can take the SAME frame with and
   * without the markers and say "a marker is painted at this pixel" as an exact pixel difference
   * rather than as a colour model of the shader. Every other pass is untouched, so with the markers
   * drawn last the two frames are byte-identical wherever no marker won a fragment.
   *
   * `null` when the scene is disposed or the context is lost. Each returned array is a fresh
   * `Uint8Array(4)` of RGBA in [0, 255]; a point outside the canvas reads back all zeros.
   */
  samplePixels(
    camera: OrbitCamera,
    pointsCss: ReadonlyArray<readonly [number, number]>,
    options?: { markers?: boolean },
  ): Uint8Array[] | null;
  /** Rebuilds every GL object from the retained CPU data after `webglcontextrestored`. */
  restore(): void;
  dispose(): void;
  readonly stats: SceneStats;
}

interface UploadedPart {
  part: ScenePart;
  vao: WebGLVertexArrayObject;
  buffers: WebGLBuffer[];
  indexCount: number;
  hasLabels: boolean;
}

interface Program {
  program: WebGLProgram;
  uniforms: Record<string, WebGLUniformLocation | null>;
}

/**
 * TypeScript 5.7 split typed arrays by their backing buffer, so a plain `Float32Array` (which is
 * `Float32Array<ArrayBufferLike>`) is no longer assignable to `BufferSource`, which wants an
 * `ArrayBuffer`-backed view. Nothing here allocates a `SharedArrayBuffer` — the data comes from
 * `fetch` and from `parseTvsc1` — so the assertion is sound and lives in exactly one place rather
 * than at every upload.
 */
const asBufferSource = (view: ArrayBufferView): BufferSource => view as BufferSource;

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("scene: gl.createShader returned null");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader) ?? "(no log)";
    gl.deleteShader(shader);
    throw new Error(`scene: shader failed to compile: ${log}`);
  }
  return shader;
}

function link(gl: WebGL2RenderingContext, vsSource: string, fsSource: string, names: string[]): Program {
  const vs = compile(gl, gl.VERTEX_SHADER, vsSource);
  const fs = compile(gl, gl.FRAGMENT_SHADER, fsSource);
  const program = gl.createProgram();
  if (!program) throw new Error("scene: gl.createProgram returned null");
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program) ?? "(no log)";
    gl.deleteProgram(program);
    throw new Error(`scene: program failed to link: ${log}`);
  }
  const uniforms: Record<string, WebGLUniformLocation | null> = {};
  for (const name of names) uniforms[name] = gl.getUniformLocation(program, name);
  return { program, uniforms };
}

const SURFACE_UNIFORMS = [
  "uViewProj",
  "uView",
  "uBaseColor",
  "uSelectedColor",
  "uHoverColor",
  "uDimColor",
  "uOpacity",
  "uUseLabels",
  "uLabelState",
  "uLabelColor",
  "uSheetDepth",
  "uSheetPeel",
];
const SURFACE_PICK_UNIFORMS = ["uViewProj", "uView", "uKind"];
const MARKER_UNIFORMS = [
  "uViewProj",
  "uViewportPx",
  "uSizePx",
  "uMarkerColor",
  "uSelectedColor",
  "uHoverColor",
  "uChannel0",
  "uChannel1",
  "uChannel2",
  "uChannel3",
  "uChannel4",
  "uChannel5",
];

/**
 * Creates the renderer, or returns `null` when the browser has no WebGL2 (decision S6: the pane is
 * never the only way, so a missing context is a caller-visible `null` and one readable line in the
 * UI, not a thrown error that blanks the page).
 */
export function createGlScene(
  canvas: HTMLCanvasElement,
  palette: ScenePalette = SCENE_PALETTE,
): GlScene | null {
  const gl = canvas.getContext("webgl2", {
    alpha: false,
    antialias: true,
    depth: true,
    stencil: false,
    // The pane is a form control that redraws on interaction; a discrete GPU spun up for it costs
    // battery for no gain on a laptop, and the default is what the Viewer's embed asks for too.
    powerPreference: "default",
    preserveDrawingBuffer: false,
  }) as WebGL2RenderingContext | null;
  if (!gl) return null;
  return buildScene(canvas, gl, palette);
}

/**
 * The renderer proper, with `gl` as a non-nullable parameter.
 *
 * Split out of `createGlScene` for a TypeScript reason worth writing down: a null check does not
 * narrow a variable inside a *hoisted function declaration*, because the declaration could in
 * principle be called before the check runs. Every helper below is one, so the alternative was
 * either forty non-null assertions or turning them all into arrow functions in dependency order.
 */
function buildScene(canvas: HTMLCanvasElement, gl: WebGL2RenderingContext, palette: ScenePalette): GlScene {
  let parts: UploadedPart[] = [];
  let markers: SceneMarker[] = [];
  let markerStates: Uint32Array = new Uint32Array(0);
  let labelStates: Uint8Array = new Uint8Array(LABEL_STATE_SIZE);
  let labelColors: Uint8Array = new Uint8Array(LABEL_STATE_SIZE * 3);
  const opacity = new Map<string, number>();

  let drawWidth = Math.max(1, canvas.width);
  let drawHeight = Math.max(1, canvas.height);
  let cssWidth = drawWidth;
  let cssHeight = drawHeight;
  let devicePixelRatioValue = 1;

  let surfaceProgram = link(gl, SURFACE_VS, surfaceFs("none"), SURFACE_UNIFORMS);
  /** The same shader with the resolved-sheet bound compiled in (§"Resolving sheets" step c), for
   *  the nearest sheet and for the peeled second one. */
  let surfaceNearProgram = link(gl, SURFACE_VS, surfaceFs("near"), SURFACE_UNIFORMS);
  let surfacePeelProgram = link(gl, SURFACE_VS, surfaceFs("peeled"), SURFACE_UNIFORMS);
  let sheetDepthProgram = link(gl, SURFACE_VS, SHEET_DEPTH_FS, ["uViewProj", "uView", "uUseLabels", "uLabelState"]);
  let sheetPeelProgram = link(gl, SURFACE_VS, SHEET_PEEL_FS, [
    "uViewProj",
    "uView",
    "uUseLabels",
    "uLabelState",
    "uSheetDepth",
  ]);
  let surfacePickProgram = link(gl, SURFACE_VS, SURFACE_PICK_FS, SURFACE_PICK_UNIFORMS);
  let surfaceDepthProgram = link(gl, SURFACE_VS, DEPTH_FS, ["uViewProj", "uView"]);
  let markerProgram = link(gl, MARKER_VS, MARKER_FS, MARKER_UNIFORMS);
  let markerPickProgram = link(gl, MARKER_VS, MARKER_PICK_FS, ["uViewProj", "uViewportPx", "uSizePx"]);
  let markerDepthProgram = link(gl, MARKER_VS, MARKER_DEPTH_FS, ["uViewProj", "uViewportPx", "uSizePx"]);

  let labelTexture = createLabelTexture(gl);
  let labelColorTexture = createLabelColorTexture(gl);
  let sheets = createSheetTargets(gl, drawWidth, drawHeight);
  let quad = createQuadBuffer(gl);
  let markerVao: WebGLVertexArrayObject | null = null;
  let markerBuffers: WebGLBuffer[] = [];
  let pick = createPickTarget(gl, drawWidth, drawHeight);

  const stats: SceneStats = { triangles: 0, vertices: 0, markers: 0, drawCalls: 0, lastFrameMs: 0 };
  const pixel = new Uint8Array(4);
  let disposed = false;
  /** Set only for the duration of one `samplePixels({ markers: false })` call. */
  let suppressMarkers = false;
  let markerOcclusion = true;

  function createLabelTexture(context: WebGL2RenderingContext): WebGLTexture {
    const tex = context.createTexture();
    if (!tex) throw new Error("scene: gl.createTexture returned null");
    context.bindTexture(context.TEXTURE_2D, tex);
    context.texStorage2D(context.TEXTURE_2D, 1, context.R8UI, LABEL_TEX_SIDE, LABEL_TEX_SIDE);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.NEAREST);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.NEAREST);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_S, context.CLAMP_TO_EDGE);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_T, context.CLAMP_TO_EDGE);
    return tex;
  }

  /**
   * One RGB texel per label id, at the same index as its state byte: the label's own colour from
   * the `.annot` colour table (or the subcortical volume LUT). All black until `setLabelColors`
   * says otherwise, which is a scene with no atlas colours and the flat-tint behaviour of before.
   */
  function createLabelColorTexture(context: WebGL2RenderingContext): WebGLTexture {
    const tex = context.createTexture();
    if (!tex) throw new Error("scene: gl.createTexture returned null");
    context.bindTexture(context.TEXTURE_2D, tex);
    context.texStorage2D(context.TEXTURE_2D, 1, context.RGB8, LABEL_TEX_SIDE, LABEL_TEX_SIDE);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.NEAREST);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.NEAREST);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_S, context.CLAMP_TO_EDGE);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_T, context.CLAMP_TO_EDGE);
    return tex;
  }

  /**
   * The two screen-sized `DEPTH_COMPONENT24` textures the sheet resolution writes into, and the one
   * framebuffer that carries them (§"Resolving sheets"). `drawBuffers([NONE])` — there is no colour
   * attachment, so no colour is written and the canvas' own multisampled buffer is never touched.
   */
  function createSheetTargets(context: WebGL2RenderingContext, width: number, height: number) {
    const framebuffer = context.createFramebuffer();
    const near = context.createTexture();
    const far = context.createTexture();
    if (!framebuffer || !near || !far) throw new Error("scene: sheet depth allocation failed");
    for (const tex of [near, far]) {
      context.bindTexture(context.TEXTURE_2D, tex);
      context.texStorage2D(context.TEXTURE_2D, 1, context.DEPTH_COMPONENT24, width, height);
      context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.NEAREST);
      context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.NEAREST);
      context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_S, context.CLAMP_TO_EDGE);
      context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_T, context.CLAMP_TO_EDGE);
    }
    context.bindTexture(context.TEXTURE_2D, null);
    context.bindFramebuffer(context.FRAMEBUFFER, framebuffer);
    context.drawBuffers([context.NONE]);
    context.readBuffer(context.NONE);
    context.bindFramebuffer(context.FRAMEBUFFER, null);
    return { framebuffer, near, far };
  }

  function createQuadBuffer(context: WebGL2RenderingContext): WebGLBuffer {
    const buffer = context.createBuffer();
    if (!buffer) throw new Error("scene: gl.createBuffer returned null");
    context.bindBuffer(context.ARRAY_BUFFER, buffer);
    context.bufferData(
      context.ARRAY_BUFFER,
      new Float32Array([-0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, 0.5]),
      context.STATIC_DRAW,
    );
    return buffer;
  }

  function createPickTarget(context: WebGL2RenderingContext, width: number, height: number) {
    const framebuffer = context.createFramebuffer();
    const color = context.createTexture();
    const depth = context.createRenderbuffer();
    if (!framebuffer || !color || !depth) throw new Error("scene: could not create the pick target");
    context.bindTexture(context.TEXTURE_2D, color);
    context.texImage2D(context.TEXTURE_2D, 0, context.RGBA8, width, height, 0, context.RGBA, context.UNSIGNED_BYTE, null);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.NEAREST);
    context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.NEAREST);
    context.bindRenderbuffer(context.RENDERBUFFER, depth);
    context.renderbufferStorage(context.RENDERBUFFER, context.DEPTH_COMPONENT24, width, height);
    context.bindFramebuffer(context.FRAMEBUFFER, framebuffer);
    context.framebufferTexture2D(context.FRAMEBUFFER, context.COLOR_ATTACHMENT0, context.TEXTURE_2D, color, 0);
    context.framebufferRenderbuffer(context.FRAMEBUFFER, context.DEPTH_ATTACHMENT, context.RENDERBUFFER, depth);
    context.bindFramebuffer(context.FRAMEBUFFER, null);
    return { framebuffer, color, depth, width, height };
  }

  function buffer(data: ArrayBufferView, target: number): WebGLBuffer {
    const buf = gl.createBuffer();
    if (!buf) throw new Error("scene: gl.createBuffer returned null");
    gl.bindBuffer(target, buf);
    gl.bufferData(target, asBufferSource(data), gl.STATIC_DRAW);
    return buf;
  }

  function uploadPart(part: ScenePart): UploadedPart {
    const vao = gl.createVertexArray();
    if (!vao) throw new Error("scene: gl.createVertexArray returned null");
    gl.bindVertexArray(vao);
    // `vLabel` is flat, so the LAST corner of a triangle decides the whole triangle's region — for
    // its colour and for what a click on it picks. Rotating each border triangle onto a majority
    // corner first is what keeps a region border on the mesh edges between the two regions instead
    // of a triangle-wide saw-tooth either side of it (`labelFaces.ts`). Winding is preserved, so
    // the normals below and the outward orientation are unaffected.
    const indices =
      part.labels != null
        ? orientFacesToMajorityLabel(part.indices, part.labels)
        : part.indices;
    const normals = part.normals ?? computeVertexNormals(part.positions, indices);
    const buffers: WebGLBuffer[] = [];
    buffers.push(buffer(part.positions, gl.ARRAY_BUFFER));
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    buffers.push(buffer(normals, gl.ARRAY_BUFFER));
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
    const labels = part.labels ?? null;
    // A part with no atlas still needs attribute 2 bound: an unbound integer attribute reads as an
    // undefined constant on some drivers, and the label it produces is then a random region id.
    buffers.push(buffer(labels ?? new Uint16Array(part.positions.length / 3), gl.ARRAY_BUFFER));
    gl.enableVertexAttribArray(2);
    gl.vertexAttribIPointer(2, 1, gl.UNSIGNED_SHORT, 0, 0);
    buffers.push(buffer(indices, gl.ELEMENT_ARRAY_BUFFER));
    gl.bindVertexArray(null);
    return { part, vao, buffers, indexCount: indices.length, hasLabels: labels !== null };
  }

  function uploadMarkers(): void {
    if (markerVao) gl.deleteVertexArray(markerVao);
    for (const buf of markerBuffers) gl.deleteBuffer(buf);
    markerBuffers = [];
    markerVao = null;
    if (markers.length === 0) return;
    const centres = new Float32Array(markers.length * 3);
    const indices = new Uint32Array(markers.length);
    markers.forEach((marker, i) => {
      centres[i * 3] = marker.world[0];
      centres[i * 3 + 1] = marker.world[1];
      centres[i * 3 + 2] = marker.world[2];
      indices[i] = i;
    });
    const vao = gl.createVertexArray();
    if (!vao) throw new Error("scene: gl.createVertexArray returned null");
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    markerBuffers.push(buffer(centres, gl.ARRAY_BUFFER));
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(1, 1);
    const stateBuffer = gl.createBuffer();
    if (!stateBuffer) throw new Error("scene: gl.createBuffer returned null");
    gl.bindBuffer(gl.ARRAY_BUFFER, stateBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, asBufferSource(resizedStates()), gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribIPointer(2, 1, gl.UNSIGNED_INT, 0, 0);
    gl.vertexAttribDivisor(2, 1);
    markerBuffers.push(stateBuffer);
    markerBuffers.push(buffer(indices, gl.ARRAY_BUFFER));
    gl.enableVertexAttribArray(3);
    gl.vertexAttribIPointer(3, 1, gl.UNSIGNED_INT, 0, 0);
    gl.vertexAttribDivisor(3, 1);
    gl.bindVertexArray(null);
    markerVao = vao;
  }

  /** The state array padded or trimmed to the marker count, so a stale selection from the previous
   *  net can never index past the buffer. */
  function resizedStates(): Uint32Array {
    if (markerStates.length === markers.length) return markerStates;
    const next = new Uint32Array(markers.length);
    next.set(markerStates.subarray(0, Math.min(markerStates.length, markers.length)));
    markerStates = next;
    return next;
  }

  function setUniformMatrix(program: Program, name: string, value: Mat4): void {
    const location = program.uniforms[name];
    if (location) gl.uniformMatrix4fv(location, false, value);
  }

  function setUniform3f(program: Program, name: string, value: readonly [number, number, number]): void {
    const location = program.uniforms[name];
    if (location) gl.uniform3f(location, value[0], value[1], value[2]);
  }

  function setUniform1f(program: Program, name: string, value: number): void {
    const location = program.uniforms[name];
    if (location) gl.uniform1f(location, value);
  }

  function setUniform1i(program: Program, name: string, value: number): void {
    const location = program.uniforms[name];
    if (location) gl.uniform1i(location, value);
  }

  function projection(camera: OrbitCamera): { vp: Mat4; view: Mat4; vpPushed: Mat4; viewPushed: Mat4 } {
    const aspect = cssWidth / Math.max(1, cssHeight);
    const near = Math.max(camera.distance * 0.01, 0.1);
    const far = camera.distance * 10 + 1000;
    const proj = perspective(camera.fovY, aspect, near, far);
    const view = viewMatrix(camera);
    // The same view with every point `MARKER_OCCLUSION_BIAS_MM` further from the eye. View space
    // looks down -z, so a translation along the view axis is one entry of the matrix — not a
    // multiply — and it pushes by that many millimetres uniformly, which is what makes the bias
    // statable in mm instead of in depth-buffer units.
    const viewPushed: Mat4 = [...view];
    viewPushed[14] = view[14] - MARKER_OCCLUSION_BIAS_MM;
    return { vp: multiply(proj, view), view, vpPushed: multiply(proj, viewPushed), viewPushed };
  }

  /** Sorted innermost-first. `order` defaults to the array position, so a caller that lists
   *  `[gm, skin]` gets the right nesting without thinking about it. */
  function ordered(): UploadedPart[] {
    return [...parts].sort((a, b) => (a.part.order ?? 0) - (b.part.order ?? 0));
  }

  function bindSurfaceCommon(program: Program, vp: Mat4, view: Mat4): void {
    gl.useProgram(program.program);
    setUniformMatrix(program, "uViewProj", vp);
    setUniformMatrix(program, "uView", view);
  }

  /** `cull` is the face to drop, or `null` for "draw both faces" — the state is set here rather
   *  than at the call site so a pass cannot enable culling and then forget which face it culls. */
  function drawSurface(uploaded: UploadedPart, program: Program, cull: number | null): void {
    if (cull === null) {
      gl.disable(gl.CULL_FACE);
    } else {
      gl.enable(gl.CULL_FACE);
      gl.cullFace(cull);
    }
    gl.bindVertexArray(uploaded.vao);
    gl.drawElements(gl.TRIANGLES, uploaded.indexCount, gl.UNSIGNED_INT, 0);
    stats.drawCalls += 1;
  }

  /** Texture units, fixed so no pass has to remember what another one bound. */
  const UNIT_LABEL_STATE = 0;
  const UNIT_LABEL_COLOR = 1;
  const UNIT_SHEET_DEPTH = 2;
  const UNIT_SHEET_PEEL = 3;

  /**
   * Draws one surface as exactly one resolved depth sheet (§"Resolving sheets").
   *
   * `level` is which sheet: 0 the nearest, 1 the second-nearest. Culling is disabled throughout —
   * that is the point, since neither of our surfaces is reliably wound — so the sheet a pixel gets
   * is decided by depth alone and a folded, inward-wound gyrus behaves exactly like a closed shell.
   *
   * The caller has already bound both sheet programs' per-surface uniforms; this restores the
   * blended state and the default framebuffer before it returns, so the loop above it reads as the
   * plain sequence of draws it was before.
   */
  function drawResolvedSheet(uploaded: UploadedPart, level: 0 | 1, vp: Mat4, view: Mat4): void {
    // (a) nearest sheet, depth only, into `sheets.near`.
    gl.bindFramebuffer(gl.FRAMEBUFFER, sheets.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, sheets.near, 0);
    gl.disable(gl.BLEND);
    gl.depthMask(true);
    gl.clearDepth(1);
    gl.clear(gl.DEPTH_BUFFER_BIT);
    bindSurfaceCommon(sheetDepthProgram, vp, view);
    setUniform1i(sheetDepthProgram, "uUseLabels", 0);
    drawSurface(uploaded, sheetDepthProgram, null);

    if (level === 1) {
      // (b) peel one layer: what is strictly behind the nearest sheet, into `sheets.far`.
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, sheets.far, 0);
      gl.clear(gl.DEPTH_BUFFER_BIT);
      bindSurfaceCommon(sheetPeelProgram, vp, view);
      setUniform1i(sheetPeelProgram, "uUseLabels", 0);
      gl.activeTexture(gl.TEXTURE0 + UNIT_SHEET_DEPTH);
      gl.bindTexture(gl.TEXTURE_2D, sheets.near);
      setUniform1i(sheetPeelProgram, "uSheetDepth", UNIT_SHEET_DEPTH);
      drawSurface(uploaded, sheetPeelProgram, null);
    }

    // (c) colour, keeping only the fragments the resolved depth bounds admit.
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.enable(gl.BLEND);
    gl.depthMask(false);
    const program = level === 1 ? surfacePeelProgram : surfaceNearProgram;
    gl.useProgram(program.program);
    gl.activeTexture(gl.TEXTURE0 + UNIT_SHEET_DEPTH);
    gl.bindTexture(gl.TEXTURE_2D, level === 1 ? sheets.far : sheets.near);
    setUniform1i(program, "uSheetDepth", UNIT_SHEET_DEPTH);
    if (level === 1) {
      gl.activeTexture(gl.TEXTURE0 + UNIT_SHEET_PEEL);
      gl.bindTexture(gl.TEXTURE_2D, sheets.near);
      setUniform1i(program, "uSheetPeel", UNIT_SHEET_PEEL);
    }
    drawSurface(uploaded, program, null);
  }

  function bindMarkerCommon(program: Program, vp: Mat4): void {
    gl.useProgram(program.program);
    setUniformMatrix(program, "uViewProj", vp);
    const viewport = program.uniforms.uViewportPx;
    if (viewport) gl.uniform2f(viewport, drawWidth, drawHeight);
    setUniform1f(program, "uSizePx", MARKER_SIZE_PX * devicePixelRatioValue);
  }

  /** The caller has already bound the program and its uniforms through `bindMarkerCommon`; this is
   *  only the instanced draw, shared by the visible and the pick pass. */
  function drawMarkers(): void {
    if (suppressMarkers) return;
    if (!markerVao || markers.length === 0) return;
    gl.bindVertexArray(markerVao);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, markers.length);
    stats.drawCalls += 1;
  }

  /**
   * The geometry of a pick, run once for the id and once (when asked) for the depth, so the two
   * reads cannot disagree about which fragment won.
   *
   * **Both faces of every surface are drawn**, which is the rule the visible pass follows (back
   * faces then front faces, §"Draw order"). Culling back faces here instead — as this did until
   * 2026-09-04 — makes the pick skip any surface whose nearest triangle at that pixel happens to
   * face away, and return whatever is behind it: measured by lane SCC on sub-ernie's DK40 at canvas
   * pixel (588, 264), the pick named region 12 at 908.2 mm where the surface the user was looking
   * at was region 27 at 887.5 mm — a different gyrus, 20.7 mm nearer, with nothing on screen to say
   * so. A pick may only ever name something the eye can see.
   */
  function drawPickSequence(
    matrices: { vp: Mat4; view: Mat4; vpPushed: Mat4; viewPushed: Mat4 },
    options: PickOptions,
    surface: Program,
    marker: Program,
    /**
     * This is the **depth** run of the sequence, not the id run.
     *
     * The two runs answer different questions and therefore need different geometry. The id run may
     * only rasterise a surface that can name a region. The depth run answers "where did I click",
     * and the honest answer is the frontmost surface the user can actually SEE — so it adds every
     * surface that is **opaque**, and still skips the translucent ones, which are veils being
     * looked through rather than things being aimed at.
     *
     * Both halves are a measured defect. Gating the depth run on `hasLabels` made `pick.world`
     * null for every click on the scalp, which is the whole of the Simulator's free-hand placement
     * (2026-09-06: every scalp click left the position row at 0). Including the translucent skin
     * put the sphere centre 35 mm in front of the cortex the user was aiming at
     * (`scene.spec.ts`'s "reports where the click landed"), because the pane draws the scalp at
     * 0.22 exactly so the cortex can be aimed at through it. Opacity is the signal that separates
     * them, and it is the same signal the eye uses.
     */
    depthPass = false,
  ): void {
    const { vp, view, vpPushed, viewPushed } = matrices;
    // The surfaces are drawn when a region is selectable **or** when a depth is being read, and the
    // second half is not the same question as the first. "Which region did I click" and "where did
    // I click" are separate: the Analyzer's and Optimizer's sphere panes select nothing at all
    // (`MODE_RULES.inspect` is `regions: "none"`) and still need the point on the anatomy under the
    // cursor, which is the whole of `onPickAt`. Gating the anatomy on selectability made
    // `pick.world` silently null in exactly the mode that was built for it (measured 2026-09-04
    // against the container: every click in spherical mode left the form's x/y/z at 0).
    if (options.regions || options.depth) {
      bindSurfaceCommon(surface, vp, view);
      const kind = surface.uniforms.uKind;
      if (kind) gl.uniform1ui(kind, PICK_KIND_REGION);
      for (const uploaded of ordered()) {
        // Id run: only a labelled surface can produce a region id — an unlabelled one would write
        // label 0 and resolve as a region nobody clicked. Depth run: every surface the user can
        // see through no veil, i.e. every labelled one plus every opaque one.
        const opaque = (opacity.get(uploaded.part.id) ?? uploaded.part.opacity) >= 1;
        if (uploaded.hasLabels || (depthPass && opaque)) drawSurface(uploaded, surface, null);
      }
    }
    if (options.markers) {
      // What the eye can see, the cursor can hit — and, since 2026-09-04, only that. The visible
      // pass hides a marker behind the scalp (§"Draw order" steps 3 and 4), so this pass has to
      // hide it identically: a click that selected an electrode the user cannot see would be the
      // same defect wearing a mouse. Until that date this line was a bare `clear(DEPTH)` on the
      // opposite premise — that markers were always drawn over everything.
      //
      // The depth the id pass above left is cleared first and rebuilt from the pre-pass, because
      // that pass draws only the LABELLED surfaces and only when a region is selectable at all,
      // while a marker is occluded by any surface, labelled or not.
      gl.clear(gl.DEPTH_BUFFER_BIT);
      if (markerOcclusion) {
        gl.colorMask(false, false, false, false);
        bindSurfaceCommon(surfaceDepthProgram, vpPushed, viewPushed);
        for (const uploaded of ordered()) drawSurface(uploaded, surfaceDepthProgram, null);
        gl.colorMask(true, true, true, true);
      }
      gl.disable(gl.CULL_FACE);
      bindMarkerCommon(marker, vp);
      drawMarkers();
    }
  }

  const loseContextExtension = gl.getExtension("WEBGL_lose_context");

  const scene: GlScene = {
    gl,
    loseContextExtension,
    stats,

    setParts(next) {
      for (const uploaded of parts) {
        gl.deleteVertexArray(uploaded.vao);
        for (const buf of uploaded.buffers) gl.deleteBuffer(buf);
      }
      parts = next.map((part, i) => uploadPart({ ...part, order: part.order ?? i }));
      stats.triangles = parts.reduce((sum, p) => sum + p.indexCount / 3, 0);
      stats.vertices = parts.reduce((sum, p) => sum + p.part.positions.length / 3, 0);
      for (const part of next) if (!opacity.has(part.id)) opacity.set(part.id, part.opacity);
    },

    setMarkers(next) {
      markers = next;
      stats.markers = next.length;
      markerStates = new Uint32Array(next.length);
      next.forEach((marker, i) => {
        markerStates[i] = markerStateChannel(marker.channel);
      });
      uploadMarkers();
    },

    setMarkerStates(states) {
      markerStates = states;
      const buf = markerBuffers[1];
      if (buf && states.length === markers.length) {
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, asBufferSource(states));
      }
    },

    setLabelStates(states) {
      labelStates = states.length === LABEL_STATE_SIZE ? states : padLabels(states);
      gl.bindTexture(gl.TEXTURE_2D, labelTexture);
      gl.texSubImage2D(
        gl.TEXTURE_2D,
        0,
        0,
        0,
        LABEL_TEX_SIDE,
        LABEL_TEX_SIDE,
        gl.RED_INTEGER,
        gl.UNSIGNED_BYTE,
        labelStates,
      );
    },

    setLabelColors(colors) {
      labelColors =
        colors.length === LABEL_STATE_SIZE * 3 ? colors : padLabelColors(colors);
      gl.bindTexture(gl.TEXTURE_2D, labelColorTexture);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texSubImage2D(
        gl.TEXTURE_2D,
        0,
        0,
        0,
        LABEL_TEX_SIDE,
        LABEL_TEX_SIDE,
        gl.RGB,
        gl.UNSIGNED_BYTE,
        labelColors,
      );
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
    },

    setOpacity(partId, value) {
      opacity.set(partId, Math.min(1, Math.max(0, value)));
    },

    setMarkerOcclusion(occluded) {
      markerOcclusion = occluded;
    },

    resize(nextCssWidth, nextCssHeight, dpr) {
      cssWidth = Math.max(1, Math.round(nextCssWidth));
      cssHeight = Math.max(1, Math.round(nextCssHeight));
      devicePixelRatioValue = dpr;
      const w = Math.max(1, Math.round(cssWidth * dpr));
      const h = Math.max(1, Math.round(cssHeight * dpr));
      if (w === drawWidth && h === drawHeight && canvas.width === w && canvas.height === h) return;
      drawWidth = w;
      drawHeight = h;
      canvas.width = w;
      canvas.height = h;
      gl.deleteFramebuffer(pick.framebuffer);
      gl.deleteTexture(pick.color);
      gl.deleteRenderbuffer(pick.depth);
      pick = createPickTarget(gl, w, h);
      // The sheet textures are read by `texelFetch(…, ivec2(gl_FragCoord.xy))`, so they have to be
      // exactly the size of the drawing buffer or a resolved depth would be read from the wrong
      // pixel — `texStorage2D` is immutable, hence a reallocation rather than a resize.
      gl.deleteFramebuffer(sheets.framebuffer);
      gl.deleteTexture(sheets.near);
      gl.deleteTexture(sheets.far);
      sheets = createSheetTargets(gl, w, h);
    },

    render(camera) {
      if (disposed || gl.isContextLost()) return;
      const started = performance.now();
      stats.drawCalls = 0;
      const { vp, view, vpPushed, viewPushed } = projection(camera);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, drawWidth, drawHeight);
      gl.disable(gl.SCISSOR_TEST);
      gl.clearColor(palette.background[0], palette.background[1], palette.background[2], 1);
      gl.clearDepth(1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.enable(gl.BLEND);
      gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

      const list = ordered();
      gl.activeTexture(gl.TEXTURE0 + UNIT_LABEL_STATE);
      gl.bindTexture(gl.TEXTURE_2D, labelTexture);
      gl.activeTexture(gl.TEXTURE0 + UNIT_LABEL_COLOR);
      gl.bindTexture(gl.TEXTURE_2D, labelColorTexture);
      // All three surface programs read the same units and the same palette, so a pass never has
      // to remember what another one bound.
      for (const program of [surfaceProgram, surfaceNearProgram, surfacePeelProgram]) {
        bindSurfaceCommon(program, vp, view);
        setUniform1i(program, "uLabelState", UNIT_LABEL_STATE);
        setUniform1i(program, "uLabelColor", UNIT_LABEL_COLOR);
        setUniform3f(program, "uSelectedColor", palette.selected);
        setUniform3f(program, "uHoverColor", palette.hover);
        setUniform3f(program, "uDimColor", palette.dim);
      }
      // A surface at full opacity takes the plain opaque path instead of the sheet machinery: one
      // draw, depth written and depth-tested against itself, no blending. Two things depend on it.
      // The sheet path's fresnel weighting multiplies a face-on fragment's alpha by 0.42, so a
      // surface asked for opacity 1 still showed what was behind it — the grey matter's sulcal
      // walls read through its own outer surface. And the depth this pass writes is what makes a
      // translucent shell outside it (the skin) disappear where the opaque one covers it.
      const isOpaque = (uploaded: UploadedPart): boolean =>
        (opacity.get(uploaded.part.id) ?? uploaded.part.opacity) >= 1;
      const opaqueParts = list.filter(isOpaque);
      const translucent = list.filter((uploaded) => !isOpaque(uploaded));

      // 1. the opaque surfaces, innermost first (order is irrelevant here — the depth buffer
      //    decides), writing depth.
      gl.depthMask(true);
      gl.disable(gl.BLEND);
      gl.useProgram(surfaceProgram.program);
      for (const uploaded of opaqueParts) {
        setUniform3f(surfaceProgram, "uBaseColor", uploaded.part.color);
        setUniform1f(surfaceProgram, "uOpacity", 1);
        setUniform1i(surfaceProgram, "uUseLabels", uploaded.hasLabels ? 1 : 0);
        // Both faces: neither of our surfaces is reliably wound, so culling would punch holes in a
        // folded gyrus. Depth resolves the sheet instead, exactly as in the translucent path.
        drawSurface(uploaded, surfaceProgram, null);
      }
      gl.enable(gl.BLEND);
      gl.depthMask(false);

      // 2 + 3. the translucent surfaces: phase 1 the far sheet of each, outermost first; phase 2
      //        the near sheet, innermost first. Back-to-front for nested shells, with the sheet
      //        itself resolved by depth rather than by winding (§"Resolving sheets"). Depth writes
      //        are off, but the depth TEST is on, so the opaque pass above occludes them.
      const phases: Array<{ items: UploadedPart[]; level: 0 | 1 }> = [
        { items: [...translucent].reverse(), level: 1 },
        { items: translucent, level: 0 },
      ];
      for (const phase of phases) {
        for (const uploaded of phase.items) {
          for (const program of [surfaceNearProgram, surfacePeelProgram]) {
            gl.useProgram(program.program);
            setUniform3f(program, "uBaseColor", uploaded.part.color);
            setUniform1f(program, "uOpacity", opacity.get(uploaded.part.id) ?? uploaded.part.opacity);
            setUniform1i(program, "uUseLabels", uploaded.hasLabels ? 1 : 0);
          }
          drawResolvedSheet(uploaded, phase.level, vp, view);
        }
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, drawWidth, drawHeight);

      // 3. depth-only pre-pass: no colour, depth on, both faces, pushed away from the eye. The head
      //    is already composited, so this only decides what the markers are allowed to cover. It is
      //    skipped for markers that are not meant to be occluded (`setMarkerOcclusion`), which
      //    leaves the depth buffer empty and every marker in front of everything, as before.
      gl.depthMask(true);
      if (markerOcclusion) {
        gl.colorMask(false, false, false, false);
        bindSurfaceCommon(surfaceDepthProgram, vpPushed, viewPushed);
        for (const uploaded of list) drawSurface(uploaded, surfaceDepthProgram, null);
        gl.colorMask(true, true, true, true);
      }

      // 4. markers, over the head and depth-tested against it: an electrode on the far side of the
      //    scalp is hidden by it, the way a person expects a head to work.
      gl.disable(gl.CULL_FACE);
      bindMarkerCommon(markerProgram, vp);
      // Channel 0 means "in no channel": neutral grey, never the accent — see `palette.idle`.
      setUniform3f(markerProgram, "uMarkerColor", palette.idle);
      setUniform3f(markerProgram, "uSelectedColor", palette.selected);
      setUniform3f(markerProgram, "uHoverColor", palette.hover);
      setUniform3f(markerProgram, "uChannel0", palette.channels[0]);
      setUniform3f(markerProgram, "uChannel1", palette.channels[1]);
      setUniform3f(markerProgram, "uChannel2", palette.channels[2]);
      setUniform3f(markerProgram, "uChannel3", palette.channels[3]);
      setUniform3f(markerProgram, "uChannel4", palette.channels[4]);
      setUniform3f(markerProgram, "uChannel5", palette.channels[5]);
      drawMarkers();

      gl.bindVertexArray(null);
      gl.depthMask(true);
      stats.lastFrameMs = performance.now() - started;
    },

    pick(xCss, yCss, camera, options) {
      if (disposed || gl.isContextLost()) return null;
      const devX = Math.round(xCss * devicePixelRatioValue);
      const devY = Math.round(yCss * devicePixelRatioValue);
      if (devX < 0 || devY < 0 || devX >= drawWidth || devY >= drawHeight) return null;
      // readPixels' origin is bottom-left; a mouse event's is top-left.
      const readY = drawHeight - 1 - devY;
      const matrices = projection(camera);
      gl.bindFramebuffer(gl.FRAMEBUFFER, pick.framebuffer);
      gl.viewport(0, 0, drawWidth, drawHeight);
      // Rasterise three pixels instead of two million: the vertex work is unchanged but the
      // fragment cost of a pick stops scaling with the surface budget.
      gl.enable(gl.SCISSOR_TEST);
      gl.scissor(Math.max(0, devX - 1), Math.max(0, readY - 1), 3, 3);
      gl.disable(gl.BLEND);
      gl.enable(gl.DEPTH_TEST);
      gl.depthMask(true);
      gl.clearColor(0, 0, 0, 0);
      gl.clearDepth(1);
      // Both buffers, every time. The id pass does not necessarily write the three pixels it reads
      // — a pick can now legitimately draw nothing at all where a marker is occluded and no region
      // is selectable — and a scissor box that is not cleared hands back the id an earlier pick
      // left in the same texels. That would resolve as "you clicked the electrode you clicked last
      // time it was in front of the head".
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      drawPickSequence(matrices, options, surfacePickProgram, markerPickProgram);
      gl.readPixels(devX, readY, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      const target = decodePickPixel(pixel);
      const hit = target?.kind === "marker" && target.index >= markers.length ? null : target;

      let ndcDepth: number | null = null;
      if (options.depth === true) {
        // The same three pixels again, with a fragment shader that writes the depth instead of the
        // id. Re-running the sequence rather than reading the depth buffer left over from the id
        // pass is not redundancy: that buffer was cleared before the markers were drawn, so it no
        // longer describes a region that won.
        //
        // It runs whether or not the id pass named something, because the id pass only draws what
        // is *selectable* — see `drawPickSequence`. Background is told apart from geometry by the
        // clear colour: white decodes to a packed depth of 1, the far plane, which no fragment of
        // a framed scene ever reaches.
        gl.clearColor(1, 1, 1, 1);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        gl.clearColor(0, 0, 0, 0);
        drawPickSequence(matrices, options, surfaceDepthProgram, markerDepthProgram, true);
        gl.readPixels(devX, readY, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
        const packed = decodePackedDepth(pixel);
        ndcDepth = packed >= 1 - 1e-6 ? null : packed * 2 - 1;
      }

      gl.bindVertexArray(null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.disable(gl.SCISSOR_TEST);
      return { target: hit, ndcDepth };
    },

    samplePixels(camera, pointsCss, options) {
      if (disposed || gl.isContextLost()) return null;
      suppressMarkers = options?.markers === false;
      try {
        scene.render(camera);
      } finally {
        suppressMarkers = false;
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.disable(gl.SCISSOR_TEST);
      const out: Uint8Array[] = [];
      for (const [xCss, yCss] of pointsCss) {
        const devX = Math.round(xCss * devicePixelRatioValue);
        const devY = Math.round(yCss * devicePixelRatioValue);
        // readPixels' origin is bottom-left; a canvas coordinate's is top-left.
        const readY = drawHeight - 1 - devY;
        const rgba = new Uint8Array(4);
        if (devX >= 0 && readY >= 0 && devX < drawWidth && readY < drawHeight) {
          gl.readPixels(devX, readY, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, rgba);
        }
        out.push(rgba);
      }
      return out;
    },

    restore() {
      // Every GL object died with the context; the CPU-side data did not, which is the whole point
      // of keeping `parts`/`markers`/`labelStates` here rather than only on the GPU.
      surfaceProgram = link(gl, SURFACE_VS, surfaceFs("none"), SURFACE_UNIFORMS);
      surfaceNearProgram = link(gl, SURFACE_VS, surfaceFs("near"), SURFACE_UNIFORMS);
      surfacePeelProgram = link(gl, SURFACE_VS, surfaceFs("peeled"), SURFACE_UNIFORMS);
      sheetDepthProgram = link(gl, SURFACE_VS, SHEET_DEPTH_FS, ["uViewProj", "uView", "uUseLabels", "uLabelState"]);
      sheetPeelProgram = link(gl, SURFACE_VS, SHEET_PEEL_FS, [
        "uViewProj",
        "uView",
        "uUseLabels",
        "uLabelState",
        "uSheetDepth",
      ]);
      surfacePickProgram = link(gl, SURFACE_VS, SURFACE_PICK_FS, SURFACE_PICK_UNIFORMS);
      surfaceDepthProgram = link(gl, SURFACE_VS, DEPTH_FS, ["uViewProj", "uView"]);
      markerProgram = link(gl, MARKER_VS, MARKER_FS, MARKER_UNIFORMS);
      markerPickProgram = link(gl, MARKER_VS, MARKER_PICK_FS, ["uViewProj", "uViewportPx", "uSizePx"]);
      markerDepthProgram = link(gl, MARKER_VS, MARKER_DEPTH_FS, ["uViewProj", "uViewportPx", "uSizePx"]);
      labelTexture = createLabelTexture(gl);
      labelColorTexture = createLabelColorTexture(gl);
      sheets = createSheetTargets(gl, drawWidth, drawHeight);
      quad = createQuadBuffer(gl);
      pick = createPickTarget(gl, drawWidth, drawHeight);
      const sourceParts = parts.map((uploaded) => uploaded.part);
      parts = [];
      markerVao = null;
      markerBuffers = [];
      scene.setParts(sourceParts);
      const savedStates = markerStates;
      scene.setMarkers(markers);
      if (savedStates.length === markers.length) scene.setMarkerStates(savedStates);
      scene.setLabelStates(labelStates);
      scene.setLabelColors(labelColors);
    },

    dispose() {
      disposed = true;
      if (gl.isContextLost()) return;
      for (const uploaded of parts) {
        gl.deleteVertexArray(uploaded.vao);
        for (const buf of uploaded.buffers) gl.deleteBuffer(buf);
      }
      parts = [];
      if (markerVao) gl.deleteVertexArray(markerVao);
      for (const buf of markerBuffers) gl.deleteBuffer(buf);
      gl.deleteBuffer(quad);
      gl.deleteTexture(labelTexture);
      gl.deleteTexture(labelColorTexture);
      gl.deleteFramebuffer(pick.framebuffer);
      gl.deleteTexture(pick.color);
      gl.deleteRenderbuffer(pick.depth);
      gl.deleteFramebuffer(sheets.framebuffer);
      gl.deleteTexture(sheets.near);
      gl.deleteTexture(sheets.far);
      for (const program of [
        surfaceProgram,
        surfaceNearProgram,
        surfacePeelProgram,
        sheetDepthProgram,
        sheetPeelProgram,
        surfacePickProgram,
        surfaceDepthProgram,
        markerProgram,
        markerPickProgram,
        markerDepthProgram,
      ]) {
        gl.deleteProgram(program.program);
      }
    },
  };

  scene.setLabelStates(labelStates);
  return scene;
}

function padLabels(states: Uint8Array): Uint8Array {
  const padded = new Uint8Array(LABEL_STATE_SIZE);
  padded.set(states.subarray(0, Math.min(states.length, LABEL_STATE_SIZE)));
  return padded;
}

function padLabelColors(colors: Uint8Array): Uint8Array {
  const padded = new Uint8Array(LABEL_STATE_SIZE * 3);
  padded.set(colors.subarray(0, Math.min(colors.length, LABEL_STATE_SIZE * 3)));
  return padded;
}

/**
 * The per-label RGB texture payload from a legend, for `GlScene.setLabelColors`.
 *
 * One entry per legend row: `label` is the `uint16` that appears in the payload the surface was
 * built with, and `color` is the row's `"#rrggbb"` — the `.annot` colour table's own RGB for a
 * cortical parcellation, the `labeling_LUT.txt` RGB for a subcortical volume label. Both arrive on
 * `legend[].color` of `GET /api/scene/regions` and `GET /api/guide/regions` already; this is only
 * the packing.
 *
 * Rows with no colour, an unparseable colour, or a label outside the 16-bit range are skipped, and
 * their texels stay black — which the shader reads as "this label has no atlas colour", falling
 * back to the part tint and the palette blue. Pure, so the mapping is unit-testable with no GPU.
 */
export function buildLabelColors(
  legend: ReadonlyArray<{ label?: number | null; color?: string | null }>,
): Uint8Array {
  const colors = new Uint8Array(LABEL_STATE_SIZE * 3);
  for (const row of legend) {
    const label = row.label;
    if (typeof label !== "number" || !Number.isInteger(label) || label <= 0 || label >= LABEL_STATE_SIZE) {
      continue;
    }
    const hex = typeof row.color === "string" ? row.color.trim() : "";
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) continue;
    const at = label * 3;
    colors[at] = parseInt(hex.slice(1, 3), 16);
    colors[at + 1] = parseInt(hex.slice(3, 5), 16);
    colors[at + 2] = parseInt(hex.slice(5, 7), 16);
  }
  return colors;
}

/** The `"#rrggbb"` one label renders as, for a legend swatch or a picker row — the same value the
 *  shader draws, so a swatch and the anatomy under it can never disagree. `null` when the legend
 *  carries no colour for that label. */
export function labelSwatchColor(
  legend: ReadonlyArray<{ label?: number | null; color?: string | null }>,
  label: number,
): string | null {
  for (const row of legend) {
    if (row.label !== label) continue;
    const hex = typeof row.color === "string" ? row.color.trim() : "";
    return /^#[0-9a-fA-F]{6}$/.test(hex) ? hex.toLowerCase() : null;
  }
  return null;
}

/** Builds the label-state array a highlighted region set implies: selected regions marked, every
 *  other *known* region dimmed, hover on top. Pure, so the shading rule is unit-testable. */
export function buildLabelStates(
  knownLabels: Iterable<number>,
  selected: Iterable<number>,
  hovered: number | null,
): Uint8Array {
  const states = new Uint8Array(LABEL_STATE_SIZE);
  const selectedSet = new Set(selected);
  if (selectedSet.size > 0) {
    for (const label of knownLabels) {
      if (label >= 0 && label < LABEL_STATE_SIZE) states[label] = LABEL_DIMMED;
    }
    for (const label of selectedSet) {
      if (label >= 0 && label < LABEL_STATE_SIZE) states[label] = LABEL_SELECTED;
    }
  }
  if (hovered !== null && hovered >= 0 && hovered < LABEL_STATE_SIZE) {
    states[hovered] = ((states[hovered] as number) & ~LABEL_DIMMED) | LABEL_HOVER;
  }
  return states;
}

export { PICK_KIND_MARKER, PICK_KIND_REGION };
