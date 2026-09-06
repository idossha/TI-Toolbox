/**
 * Pure, stateful decoders for the two streaming wire formats the Docker Engine API uses:
 * newline-delimited JSON (image-pull progress, `/events`) and the 8-byte multiplexed
 * stdout/stderr framing used by `GET /containers/{id}/logs` and `/attach` whenever the
 * container was created with `Tty: false` — every container this client creates (`engine.ts`'s
 * `runJobContainer`) always sets `Tty: false`, so a TTY-mode raw byte stream (no framing at all)
 * is out of scope here; nothing in this program ever creates a container with `Tty: true`.
 *
 * Both decoders are pure buffering state machines with no I/O of their own, specifically so
 * `tests/unit/docker-engine-frames.test.ts` can feed them arbitrary chunk splits (a frame's
 * 8-byte header split across two chunks, a payload split mid-way, three NDJSON objects arriving
 * in one chunk, one line arriving in two chunks) without a socket anywhere in the test — see
 * `dev/spikes/native/docker/REPORT.md` §"framing edge cases" for the exact cases exercised.
 */

export type LogStreamName = "stdin" | "stdout" | "stderr";

export interface LogFrame {
  stream: LogStreamName;
  payload: Buffer;
}

const STREAM_NAMES: Record<number, LogStreamName> = { 0: "stdin", 1: "stdout", 2: "stderr" };
const HEADER_LEN = 8;

/**
 * Demultiplexes Docker's stream-multiplexing frame format:
 * `[STREAM_TYPE(1 byte), 0, 0, 0, SIZE(uint32 big-endian)][SIZE bytes of payload]`, repeated.
 * Docker's own docs (`docs.docker.com/reference/api/engine/version/v1.51/#tag/Container/operation/ContainerLogs`)
 * describe this exact framing for the non-TTY log/attach response body.
 */
export class LogFrameDecoder {
  private buf: Buffer = Buffer.alloc(0);

  /** Feed one chunk; returns every complete frame it now allows, buffering any partial remainder. */
  push(chunk: Buffer): LogFrame[] {
    this.buf = this.buf.length ? Buffer.concat([this.buf, chunk]) : Buffer.from(chunk);
    const frames: LogFrame[] = [];
    for (;;) {
      if (this.buf.length < HEADER_LEN) break;
      const size = this.buf.readUInt32BE(4);
      if (this.buf.length < HEADER_LEN + size) break;
      const streamByte = this.buf[0] ?? 1;
      const payload = Buffer.from(this.buf.subarray(HEADER_LEN, HEADER_LEN + size));
      frames.push({ stream: STREAM_NAMES[streamByte] ?? "stdout", payload });
      this.buf = this.buf.subarray(HEADER_LEN + size);
    }
    return frames;
  }

  /** Bytes still held: either an in-flight partial frame, or (after the stream closed) a genuine truncation. */
  remainder(): Buffer {
    return this.buf;
  }
}

/**
 * Splits a byte/text stream into complete JSON objects, one per newline-delimited line, carrying
 * a partial trailing line forward to the next `push()`. Used for both `POST /images/create`'s
 * pull-progress stream and `GET /events`'s event stream — both are documented as
 * newline-delimited JSON objects, not a single JSON array.
 */
export class NdjsonDecoder<T = Record<string, unknown>> {
  private carry = "";

  push(chunk: Buffer | string): T[] {
    const text = this.carry + (Buffer.isBuffer(chunk) ? chunk.toString("utf8") : chunk);
    const lines = text.split(/\r?\n/);
    this.carry = lines.pop() ?? "";
    const out: T[] = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      out.push(JSON.parse(trimmed) as T);
    }
    return out;
  }

  /** True if a non-empty partial line is still buffered (the stream ended mid-line). */
  hasCarry(): boolean {
    return this.carry.trim().length > 0;
  }
}
