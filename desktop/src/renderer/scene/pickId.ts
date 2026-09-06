/**
 * Colour-ID picking: the map between "what the user clicked" and a 24-bit RGB value written into an
 * off-screen buffer (plan S4).
 *
 * Why colour IDs rather than a CPU ray cast: a ray cast against 150 k triangles is either a
 * millisecond-scale linear scan on every mouse move or a BVH this module has no business owning,
 * and it cannot answer "which *region* is under the cursor" at all without duplicating the label
 * interpolation the shader already does. The GPU already rasterises the exact same geometry with
 * the exact same matrices; asking it which primitive won is one `readPixels` of one pixel.
 *
 * The encoding is pure arithmetic and lives here, apart from any GL call, so a unit test can prove
 * the round trip for every boundary value — and so the shader's own packing (`glScene.ts`) can be
 * read next to the JavaScript that unpacks it.
 *
 * ## Layout of the 24 bits
 * ```
 *  bits 23..20  kind   1 = marker, 2 = region   (0 = background, i.e. "nothing")
 *  bits 19..0   index  the marker's position in the markers array, or the region's label id
 * ```
 * Background is exactly zero, which is what `gl.clearColor(0, 0, 0, 0)` writes, so "the user
 * clicked empty space" needs no sentinel of its own. Region label 0 (`unknown` in every FreeSurfer
 * annotation) still encodes to a non-zero id because the kind bits are set, which is why the kind
 * is in the high bits rather than a separate channel.
 */

export const PICK_KIND_NONE = 0;
export const PICK_KIND_MARKER = 1;
export const PICK_KIND_REGION = 2;

/** 2^20 - 1. More markers than any EEG net (256) and more regions than any atlas (HCP_MMP1 has
 *  360 per hemisphere) by three orders of magnitude. */
export const PICK_INDEX_MAX = 0xfffff;

export type PickKind = "marker" | "region";

export interface PickTarget {
  kind: PickKind;
  /** Marker: its index in the markers array. Region: the atlas label id. */
  index: number;
}

const KIND_TO_CODE: Record<PickKind, number> = { marker: PICK_KIND_MARKER, region: PICK_KIND_REGION };

/** Packs a target into the 24-bit id the shaders write. Throws rather than truncating: a silently
 *  wrapped index picks a *different, existing* marker, which is a bug that looks like a UI mistake
 *  rather than a bad number. */
export function encodePickId(kind: PickKind, index: number): number {
  if (!Number.isInteger(index) || index < 0 || index > PICK_INDEX_MAX) {
    throw new RangeError(`pick index ${index} is outside 0..${PICK_INDEX_MAX}`);
  }
  return (KIND_TO_CODE[kind] << 20) | index;
}

/** `null` for the background id 0 and for any kind this renderer does not draw. */
export function decodePickId(id: number): PickTarget | null {
  if (!Number.isInteger(id) || id <= 0) return null;
  const kind = (id >>> 20) & 0xf;
  const index = id & PICK_INDEX_MAX;
  if (kind === PICK_KIND_MARKER) return { kind: "marker", index };
  if (kind === PICK_KIND_REGION) return { kind: "region", index };
  return null;
}

/** Id -> the three bytes a fragment shader writes. Each byte is exact in an RGBA8 target: `n / 255`
 *  round-trips through the fixed-point conversion without drift, which is why the shader divides by
 *  255 rather than by 256. */
export function pickIdToRgb(id: number): [number, number, number] {
  return [id & 0xff, (id >>> 8) & 0xff, (id >>> 16) & 0xff];
}

/** The three bytes `readPixels` returned -> the id. */
export function rgbToPickId(r: number, g: number, b: number): number {
  return (r & 0xff) | ((g & 0xff) << 8) | ((b & 0xff) << 16);
}

/** The whole read path in one call: bytes from `readPixels` -> what the user clicked. */
export function decodePickPixel(pixel: Uint8Array | Uint8ClampedArray | number[]): PickTarget | null {
  return decodePickId(rgbToPickId((pixel[0] as number) ?? 0, (pixel[1] as number) ?? 0, (pixel[2] as number) ?? 0));
}

/** True when two targets name the same thing — `===` on objects would make every hover a state
 *  change and every state change a re-render. */
export function samePickTarget(a: PickTarget | null, b: PickTarget | null): boolean {
  if (a === null || b === null) return a === b;
  return a.kind === b.kind && a.index === b.index;
}
