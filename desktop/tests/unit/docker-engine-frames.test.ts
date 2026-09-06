import { describe, expect, it } from "vitest";
import { LogFrameDecoder, NdjsonDecoder } from "../../src/main/docker/frames";

/** Builds one raw 8-byte-header + payload frame, exactly as `frames.ts`'s own writer would. */
function rawFrame(streamType: number, text: string): Buffer {
  const payload = Buffer.from(text, "utf8");
  const header = Buffer.alloc(8);
  header.writeUInt8(streamType, 0);
  header.writeUInt32BE(payload.length, 4);
  return Buffer.concat([header, payload]);
}

describe("LogFrameDecoder", () => {
  it("decodes a single whole frame delivered in one chunk", () => {
    const decoder = new LogFrameDecoder();
    const frames = decoder.push(rawFrame(1, "hello\n"));
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ stream: "stdout", payload: Buffer.from("hello\n") });
    expect(decoder.remainder().length).toBe(0);
  });

  it("decodes stdout(1) and stderr(2) distinctly, and maps stream type 0 to stdin", () => {
    const decoder = new LogFrameDecoder();
    const frames = decoder.push(Buffer.concat([rawFrame(1, "out"), rawFrame(2, "err"), rawFrame(0, "in")]));
    expect(frames.map((f) => f.stream)).toEqual(["stdout", "stderr", "stdin"]);
    expect(frames.map((f) => f.payload.toString())).toEqual(["out", "err", "in"]);
  });

  it("handles a frame whose 8-byte header is split across two chunks", () => {
    const decoder = new LogFrameDecoder();
    const whole = rawFrame(1, "split-header");
    const first = decoder.push(whole.subarray(0, 3)); // header cut mid-way (only 3 of 8 header bytes)
    expect(first).toHaveLength(0);
    expect(decoder.remainder().length).toBe(3);
    const second = decoder.push(whole.subarray(3));
    expect(second).toHaveLength(1);
    expect(second[0]?.payload.toString()).toBe("split-header");
    expect(decoder.remainder().length).toBe(0);
  });

  it("handles a frame whose payload is split across three chunks", () => {
    const decoder = new LogFrameDecoder();
    const whole = rawFrame(2, "0123456789");
    expect(decoder.push(whole.subarray(0, 8))).toHaveLength(0); // exactly the header, no payload yet
    expect(decoder.push(whole.subarray(8, 12))).toHaveLength(0); // 4 of 10 payload bytes
    const frames = decoder.push(whole.subarray(12)); // remaining 6 payload bytes
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ stream: "stderr", payload: Buffer.from("0123456789") });
  });

  it("decodes back-to-back frames arriving as one chunk, then more after a gap", () => {
    const decoder = new LogFrameDecoder();
    const batch1 = Buffer.concat([rawFrame(1, "a"), rawFrame(1, "b"), rawFrame(1, "c")]);
    expect(decoder.push(batch1).map((f) => f.payload.toString())).toEqual(["a", "b", "c"]);
    const batch2 = rawFrame(2, "d");
    expect(decoder.push(batch2).map((f) => f.payload.toString())).toEqual(["d"]);
  });

  it("leaves a genuinely truncated final frame in remainder() rather than throwing", () => {
    const decoder = new LogFrameDecoder();
    const whole = rawFrame(1, "truncated-tail");
    const frames = decoder.push(whole.subarray(0, whole.length - 3)); // stream ends 3 bytes short
    expect(frames).toHaveLength(0);
    expect(decoder.remainder().length).toBe(whole.length - 3);
  });

  it("handles a zero-length payload frame", () => {
    const decoder = new LogFrameDecoder();
    const frames = decoder.push(rawFrame(1, ""));
    expect(frames).toHaveLength(1);
    expect(frames[0]?.payload.length).toBe(0);
  });
});

describe("NdjsonDecoder", () => {
  it("parses three objects delivered in one chunk", () => {
    const decoder = new NdjsonDecoder<{ n: number }>();
    const objs = decoder.push('{"n":1}\n{"n":2}\n{"n":3}\n');
    expect(objs).toEqual([{ n: 1 }, { n: 2 }, { n: 3 }]);
    expect(decoder.hasCarry()).toBe(false);
  });

  it("carries a partial trailing line to the next push()", () => {
    const decoder = new NdjsonDecoder<{ status: string }>();
    const first = decoder.push('{"status":"pulling"}\n{"status":"downloa');
    expect(first).toEqual([{ status: "pulling" }]);
    expect(decoder.hasCarry()).toBe(true);
    const second = decoder.push('ding"}\n');
    expect(second).toEqual([{ status: "downloading" }]);
    expect(decoder.hasCarry()).toBe(false);
  });

  it("reassembles one line split across three chunks with no newline in any of them", () => {
    const decoder = new NdjsonDecoder<{ ok: boolean }>();
    expect(decoder.push('{"ok"')).toEqual([]);
    expect(decoder.push(":tr")).toEqual([]);
    expect(decoder.push("ue}\n")).toEqual([{ ok: true }]);
  });

  it("accepts Buffer chunks (not just strings), matching how engine.ts feeds it from a socket", () => {
    const decoder = new NdjsonDecoder<{ x: number }>();
    const objs = decoder.push(Buffer.from('{"x":1}\n{"x":2}\n', "utf8"));
    expect(objs).toEqual([{ x: 1 }, { x: 2 }]);
  });

  it("ignores blank lines (a trailing \\n\\n) without emitting an empty object", () => {
    const decoder = new NdjsonDecoder();
    expect(decoder.push('{"a":1}\n\n')).toEqual([{ a: 1 }]);
  });
});
