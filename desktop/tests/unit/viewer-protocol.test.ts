/**
 * `viewer/protocol.ts` — the trust boundary, driven directly.
 *
 * This is the file that decides whether a `message` event is a Tetravox reply or somebody else's
 * traffic, and it is deliberately window-free so every branch can be exercised without a browser:
 * a boundary that can only be tested end to end is a boundary whose failure modes are never
 * tested. The cases below are the four ways in (`acceptEmbedMessage` returns `null`) plus the URL
 * contract and the two shape-tolerance helpers.
 */
import { describe, expect, it } from "vitest";
import {
  EMBED_MESSAGE_TYPES,
  PROTOCOL_VERSION,
  acceptEmbedMessage,
  embedUrl,
  isEmbedMessage,
  normalizeLayers,
  normalizeLoadedDatasets,
  type EmbedMessage,
} from "../../src/renderer/viewer/protocol";

const FRAME = { name: "the iframe's contentWindow" };
const ORIGIN = "http://127.0.0.1:8790";
const READY: EmbedMessage = { tvx: 1, type: "ready", version: 1, caps: { webgl2: true } };

function incoming(overrides: Partial<{ source: unknown; origin: string; data: unknown }> = {}) {
  return { source: FRAME, origin: ORIGIN, data: READY, ...overrides };
}

describe("acceptEmbedMessage", () => {
  it("accepts a well-formed message from the expected frame and origin", () => {
    expect(acceptEmbedMessage(incoming(), { expectedSource: FRAME, embedOrigin: ORIGIN })).toEqual(READY);
  });

  it("rejects a message from a different window on the right origin (a sibling iframe)", () => {
    const sibling = { name: "another same-origin frame" };
    expect(acceptEmbedMessage(incoming({ source: sibling }), { expectedSource: FRAME, embedOrigin: ORIGIN })).toBeNull();
  });

  it("rejects a message from the right window on a different origin", () => {
    expect(acceptEmbedMessage(incoming({ origin: "https://evil.example" }), { expectedSource: FRAME, embedOrigin: ORIGIN })).toBeNull();
  });

  it("rejects traffic that is not ours — no envelope, wrong version, unknown type", () => {
    const opts = { expectedSource: FRAME, embedOrigin: ORIGIN };
    expect(acceptEmbedMessage(incoming({ data: { type: "ready" } }), opts)).toBeNull();
    expect(acceptEmbedMessage(incoming({ data: { tvx: 2, type: "ready" } }), opts)).toBeNull();
    expect(acceptEmbedMessage(incoming({ data: { tvx: 1, type: "somethingNew" } }), opts)).toBeNull();
    expect(acceptEmbedMessage(incoming({ data: "webpackHotUpdate" }), opts)).toBeNull();
    expect(acceptEmbedMessage(incoming({ data: null }), opts)).toBeNull();
    expect(acceptEmbedMessage(incoming({ data: [1, 2, 3] }), opts)).toBeNull();
  });

  it("accepts any origin only when the host explicitly asked for '*'", () => {
    const message = acceptEmbedMessage(incoming({ origin: "https://elsewhere.example" }), { expectedSource: FRAME, embedOrigin: "*" });
    expect(message).toEqual(READY);
    // The source check still applies: '*' loosens the origin, never the window.
    expect(acceptEmbedMessage(incoming({ source: {} }), { expectedSource: FRAME, embedOrigin: "*" })).toBeNull();
  });
});

describe("isEmbedMessage", () => {
  it("recognises every type the embed may send, and nothing else", () => {
    for (const type of EMBED_MESSAGE_TYPES) {
      expect(isEmbedMessage({ tvx: PROTOCOL_VERSION, type })).toBe(true);
    }
    // A host message coming back the other way is not an embed message.
    expect(isEmbedMessage({ tvx: PROTOCOL_VERSION, type: "load" })).toBe(false);
  });
});

describe("embedUrl", () => {
  it("names the host origin the embed must check against, percent-encoded", () => {
    expect(embedUrl(ORIGIN)).toBe(`${ORIGIN}/tetravox/index.html?embed=1&hostOrigin=http%3A%2F%2F127.0.0.1%3A8790`);
  });

  it("opts run panes into the viewport without changing the dedicated viewer", () => {
    const preview = new URL(embedUrl(ORIGIN, undefined, "viewport"));
    expect(preview.searchParams.get("presentation")).toBe("viewport");
    expect(preview.searchParams.get("hostOrigin")).toBe(ORIGIN);
    expect(new URL(embedUrl(ORIGIN)).searchParams.has("presentation")).toBe(false);
  });
});

describe("shape tolerance", () => {
  it("folds the fake embed's id-only `loaded` payload into the real shape", () => {
    expect(normalizeLoadedDatasets(["ds0", { id: "ds1", name: "T1.nii.gz", kind: "volume", bytes: 12 }])).toEqual([
      { id: "ds0", name: "ds0", kind: "volume" },
      { id: "ds1", name: "T1.nii.gz", kind: "volume", bytes: 12 },
    ]);
  });

  it("does the same for layers, defaulting a bare id to a visible, opaque layer", () => {
    expect(normalizeLayers(["L0", { id: "L1", name: "TI_max", visible: false, opacity: 0.7 }])).toEqual([
      { id: "L0", name: "L0", visible: true, opacity: 1 },
      { id: "L1", name: "TI_max", visible: false, opacity: 0.7 },
    ]);
  });
});
