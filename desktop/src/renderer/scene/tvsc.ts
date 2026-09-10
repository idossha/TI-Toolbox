/**
 * `TVSC1` — the one wire format the scene service and this renderer share (plan §2.3, decision S3).
 *
 * ```
 * offset size  field
 * 0      4     magic "TVSC"
 * 4      4     u32 version = 1
 * 8      4     u32 vertexCount
 * 12     4     u32 indexCount          (0 for a labels-only payload)
 * 16     4     u32 flags               bit0 = per-vertex u16 labels follow
 * 20     12    reserved (zero)
 * 32     12*V  float32 positions, world-RAS mm, x y z
 * ...    4*I   uint32 indices          (triangles)
 * ...    2*V   uint16 labels           when flags bit0; padded to a 4-byte boundary
 * ```
 *
 * Little-endian throughout — every platform this ships on is little-endian, and a byte-order flag
 * nobody can generate the other value for is a field that is never tested. The header is 32 bytes
 * so that the `Float32Array` view onto the positions is 4-byte aligned without a copy.
 *
 * Normals are not in the format: they are ~40 % more bytes for something the browser recomputes in
 * a few milliseconds (`normals.ts`), and a normal that disagrees with its positions is a class of
 * bug that cannot exist if it is never transmitted.
 *
 * This file is pure: it takes an `ArrayBuffer` and returns typed arrays. Fetching is the caller's.
 */

export const TVSC_MAGIC = 0x43535654; // "TVSC" read as a little-endian u32
export const TVSC_VERSION = 1;
export const TVSC_HEADER_BYTES = 32;
/** flags bit0: `2 * vertexCount` bytes of `uint16` labels follow the indices. */
export const TVSC_FLAG_LABELS = 1;

export interface Tvsc1 {
  version: number;
  vertexCount: number;
  indexCount: number;
  flags: number;
  /** `3 * vertexCount` floats, world-RAS mm. */
  positions: Float32Array;
  /** `indexCount` entries, or `null` for a labels-only payload. */
  indices: Uint32Array | null;
  /** `vertexCount` entries when flags bit0 is set, else `null`. */
  labels: Uint16Array | null;
  /** Triangles, i.e. `indexCount / 3`. */
  triangles: number;
  /** Total bytes the payload claims, header included. Compared against the buffer by the parser. */
  byteLength: number;
}

export class TvscError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TvscError";
  }
}

/** Bytes a payload of this shape occupies, labels padded up to a 4-byte boundary. */
export function tvscByteLength(vertexCount: number, indexCount: number, hasLabels: boolean): number {
  const labelBytes = hasLabels ? Math.ceil((2 * vertexCount) / 4) * 4 : 0;
  return TVSC_HEADER_BYTES + 12 * vertexCount + 4 * indexCount + labelBytes;
}

export interface ParseOptions {
  /**
   * Scan every index and reject one that points past the last vertex. On by default: an
   * out-of-range index is not a visual glitch but undefined behaviour in `drawElements` — a black
   * pane, a lost context, or (measured on some drivers) a whole tab. The scan is a linear pass over
   * ~450 k `uint32` at the 150 k-triangle budget, under a millisecond.
   */
  validateIndices?: boolean;
}

/**
 * Decodes a `TVSC1` payload. Throws `TvscError` with a message naming the field that disagreed —
 * a parser that returns `null` on every kind of malformed input tells the pane "no data" when the
 * truth is "the server sent 4 bytes of an HTML error page".
 *
 * The typed arrays are views onto `buffer` where alignment permits and copies where it does not
 * (`Uint32Array` needs a 4-byte-aligned offset, which a labels-only payload of odd vertex count
 * would otherwise break).
 */
export function parseTvsc1(buffer: ArrayBuffer, byteOffset = 0, options: ParseOptions = {}): Tvsc1 {
  const available = buffer.byteLength - byteOffset;
  if (available < TVSC_HEADER_BYTES) {
    throw new TvscError(`TVSC1: ${available} bytes is shorter than the ${TVSC_HEADER_BYTES}-byte header`);
  }
  const view = new DataView(buffer, byteOffset);
  const magic = view.getUint32(0, true);
  if (magic !== TVSC_MAGIC) {
    throw new TvscError(`TVSC1: bad magic 0x${magic.toString(16).padStart(8, "0")} (expected "TVSC")`);
  }
  const version = view.getUint32(4, true);
  if (version !== TVSC_VERSION) throw new TvscError(`TVSC1: unsupported version ${version}`);
  const vertexCount = view.getUint32(8, true);
  const indexCount = view.getUint32(12, true);
  const flags = view.getUint32(16, true);
  const hasLabels = (flags & TVSC_FLAG_LABELS) !== 0;

  if (indexCount % 3 !== 0) throw new TvscError(`TVSC1: indexCount ${indexCount} is not a multiple of 3`);
  const byteLength = tvscByteLength(vertexCount, indexCount, hasLabels);
  if (available < byteLength) {
    throw new TvscError(`TVSC1: payload claims ${byteLength} bytes, buffer has ${available}`);
  }

  const posOffset = byteOffset + TVSC_HEADER_BYTES;
  const positions = readFloat32(buffer, posOffset, vertexCount * 3);

  const idxOffset = posOffset + 12 * vertexCount;
  const indices = indexCount === 0 ? null : readUint32(buffer, idxOffset, indexCount);

  let labels: Uint16Array | null = null;
  if (hasLabels) {
    labels = readUint16(buffer, idxOffset + 4 * indexCount, vertexCount);
  }

  if (indices && options.validateIndices !== false) {
    let max = 0;
    for (let i = 0; i < indices.length; i += 1) {
      const v = indices[i] as number;
      if (v > max) max = v;
    }
    if (vertexCount === 0 || max >= vertexCount) {
      throw new TvscError(`TVSC1: index ${max} points past the last of ${vertexCount} vertices`);
    }
  }

  return { version, vertexCount, indexCount, flags, positions, indices, labels, triangles: indexCount / 3, byteLength };
}

/** A view when the offset is aligned, a copy when it is not — `new Float32Array(buffer, offset)`
 *  throws on a misaligned offset rather than coping, and a thrown "start offset must be a multiple
 *  of 4" is a uselessly indirect way to report a payload that is otherwise fine. */
function readFloat32(buffer: ArrayBuffer, offset: number, length: number): Float32Array {
  if (offset % 4 === 0) return new Float32Array(buffer, offset, length);
  return new Float32Array(buffer.slice(offset, offset + 4 * length));
}

function readUint32(buffer: ArrayBuffer, offset: number, length: number): Uint32Array {
  if (offset % 4 === 0) return new Uint32Array(buffer, offset, length);
  return new Uint32Array(buffer.slice(offset, offset + 4 * length));
}

function readUint16(buffer: ArrayBuffer, offset: number, length: number): Uint16Array {
  if (offset % 2 === 0) return new Uint16Array(buffer, offset, length);
  return new Uint16Array(buffer.slice(offset, offset + 2 * length));
}

export interface EncodeInput {
  positions: Float32Array | number[];
  indices?: Uint32Array | number[] | null;
  labels?: Uint16Array | number[] | null;
}

/**
 * Writes a `TVSC1` payload. This exists for two callers only — the committed fixture generator
 * (`scripts/make-scene-fixtures.ts`) and the dev gallery, which builds its synthetic head in the
 * browser and then round-trips it through the real parser so the gallery exercises the wire format
 * rather than a shortcut past it.
 *
 * It is deliberately NOT what the parser's expected values are derived from: a writer checked
 * against its own reader proves only that the two agree (house rule 9). The unit test derives its
 * expectations from the geometry and from an independent `DataView` walk.
 */
export function encodeTvsc1(input: EncodeInput): ArrayBuffer {
  const positions = input.positions instanceof Float32Array ? input.positions : Float32Array.from(input.positions);
  if (positions.length % 3 !== 0) throw new TvscError(`TVSC1: ${positions.length} position floats is not a multiple of 3`);
  const vertexCount = positions.length / 3;
  const indices =
    input.indices == null
      ? null
      : input.indices instanceof Uint32Array
        ? input.indices
        : Uint32Array.from(input.indices);
  const labels =
    input.labels == null ? null : input.labels instanceof Uint16Array ? input.labels : Uint16Array.from(input.labels);
  if (labels && labels.length !== vertexCount) {
    throw new TvscError(`TVSC1: ${labels.length} labels for ${vertexCount} vertices`);
  }
  const indexCount = indices ? indices.length : 0;
  const buffer = new ArrayBuffer(tvscByteLength(vertexCount, indexCount, labels != null));
  const view = new DataView(buffer);
  view.setUint32(0, TVSC_MAGIC, true);
  view.setUint32(4, TVSC_VERSION, true);
  view.setUint32(8, vertexCount, true);
  view.setUint32(12, indexCount, true);
  view.setUint32(16, labels ? TVSC_FLAG_LABELS : 0, true);
  // bytes 20..31 stay zero: `new ArrayBuffer` is zero-filled, and the reserved block is where a
  // version 2 puts its extra counts.
  new Float32Array(buffer, TVSC_HEADER_BYTES, positions.length).set(positions);
  const idxOffset = TVSC_HEADER_BYTES + 12 * vertexCount;
  if (indices) new Uint32Array(buffer, idxOffset, indexCount).set(indices);
  if (labels) new Uint16Array(buffer, idxOffset + 4 * indexCount, vertexCount).set(labels);
  return buffer;
}
