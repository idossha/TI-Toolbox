/**
 * `TVSL1` — the streamlines a pane draws (`tit/scene/tvsl.py` is the writer).
 *
 * ```
 * offset  size     field
 * 0       4        magic "TVSL"
 * 4       4        u32 version = 1
 * 8       4        u32 streamlineCount (S)
 * 12      4        u32 pointCount      (P)
 * 16      4        u32 flags           bit0 = per-streamline groups follow
 * 20      12       reserved (zero)
 * 32      12*P     float32 positions, world-RAS mm
 * ...     4*(S+1)  uint32 offsets
 * ...     4*S      uint32 streamline index in the whole tractogram
 * ...     4*S      uint32 group        when flags bit0
 * ```
 *
 * Little-endian, with no scalars: the pane colours a line by its edge's swatch (decision S1). Pure:
 * it takes an `ArrayBuffer` and returns typed arrays.
 */
import { TvscError } from "./tvsc";

export const TVSL_MAGIC = 0x4c535654; // "TVSL" read as a little-endian u32
export const TVSL_VERSION = 1;
export const TVSL_HEADER_BYTES = 32;

export interface Tvsl1 {
  streamlineCount: number;
  pointCount: number;
  positions: Float32Array;
  offsets: Uint32Array;
  index: Uint32Array;
  /** Per streamline; `null` when the flag is clear. */
  groups: Uint32Array | null;
}

/** Decodes a payload; throws naming the field that disagreed, like `parseTvsc1`. */
export function parseTvsl1(buffer: ArrayBuffer): Tvsl1 {
  if (buffer.byteLength < TVSL_HEADER_BYTES) {
    throw new TvscError(`TVSL1: ${buffer.byteLength} bytes is shorter than the ${TVSL_HEADER_BYTES}-byte header`);
  }
  const view = new DataView(buffer);
  const magic = view.getUint32(0, true);
  if (magic !== TVSL_MAGIC) throw new TvscError(`TVSL1: bad magic 0x${magic.toString(16).padStart(8, "0")} (expected "TVSL")`);
  const version = view.getUint32(4, true);
  if (version !== TVSL_VERSION) throw new TvscError(`TVSL1: unsupported version ${version}`);
  const streamlineCount = view.getUint32(8, true);
  const pointCount = view.getUint32(12, true);
  const hasGroups = (view.getUint32(16, true) & 1) !== 0;
  const need = TVSL_HEADER_BYTES + 12 * pointCount + 4 * (streamlineCount + 1) + 4 * streamlineCount + (hasGroups ? 4 * streamlineCount : 0);
  if (buffer.byteLength < need) throw new TvscError(`TVSL1: payload claims ${need} bytes, buffer has ${buffer.byteLength}`);
  let at = TVSL_HEADER_BYTES;
  const positions = new Float32Array(buffer, at, pointCount * 3);
  at += 12 * pointCount;
  const offsets = new Uint32Array(buffer, at, streamlineCount + 1);
  at += 4 * (streamlineCount + 1);
  const index = new Uint32Array(buffer, at, streamlineCount);
  at += 4 * streamlineCount;
  const groups = hasGroups ? new Uint32Array(buffer, at, streamlineCount) : null;
  if (offsets[streamlineCount] !== pointCount) {
    throw new TvscError(`TVSL1: last offset ${offsets[streamlineCount]} is not the point count ${pointCount}`);
  }
  return { streamlineCount, pointCount, positions, offsets, index, groups };
}
