/**
 * E1's renderer half: a pane asks for a **named feature**, never for a version number.
 *
 * Its Python twin (`tit/tetravox/protocol.py`) is compared against this file's declarations by
 * `tests/test_tetravox_protocol.py`; what is tested here is the behaviour a caller depends on.
 */
import { describe, expect, it } from "vitest";
import {
  EMBED_FEATURE_MIN_PROTOCOL,
  SUPPORTED_EMBED_PROTOCOL,
  embedCan,
  embedIsCompatible,
  embedShortfall,
  featuresForProtocol,
  isSupportedProtocol,
  type EmbedCapability,
} from "../../src/renderer/viewer/embedProtocol";

const P1: EmbedCapability = { available: true, version: "0.3.4", protocol: 1, source: "baked", features: [], compatible: true };
const P2: EmbedCapability = { available: true, version: "0.4.0", protocol: 2, source: "installed", features: [], compatible: true };

describe("isSupportedProtocol", () => {
  it("accepts the declared range and nothing else", () => {
    expect(isSupportedProtocol(SUPPORTED_EMBED_PROTOCOL.min)).toBe(true);
    expect(isSupportedProtocol(SUPPORTED_EMBED_PROTOCOL.max)).toBe(true);
    expect(isSupportedProtocol(SUPPORTED_EMBED_PROTOCOL.max + 1)).toBe(false);
    expect(isSupportedProtocol(SUPPORTED_EMBED_PROTOCOL.min - 1)).toBe(false);
  });

  it("refuses anything that is not an integer — a manifest that cannot say is not supported", () => {
    for (const value of [null, undefined, "1", 1.5, NaN, {}]) expect(isSupportedProtocol(value)).toBe(false);
  });
});

describe("embedCan", () => {
  it("gates protocol-2 features on a protocol-1 embed, and allows the protocol-1 ones", () => {
    expect(embedCan(P1, "cursor")).toBe(true);
    expect(embedCan(P1, "markers")).toBe(false);
    expect(embedCan(P1, "pick")).toBe(false);
    expect(embedCan(P1, "camera")).toBe(false);
    for (const feature of Object.keys(EMBED_FEATURE_MIN_PROTOCOL)) expect(embedCan(P2, feature)).toBe(true);
  });

  it("takes the server's feature list as authoritative when it has one", () => {
    // This is what makes an *additive* Tetravox release usable with no change to this repo: the
    // manifest names a feature this build has never heard of, and a pane asking for it works.
    const future: EmbedCapability = { available: true, protocol: 2, features: ["markers", "clipping"], compatible: true };
    expect(embedCan(future, "clipping")).toBe(true);
    expect(embedCan(future, "markers")).toBe(true);
    expect(embedCan(future, "camera")).toBe(false); // declared list is the whole list
  });

  it("says no to everything when no bundle is available or the protocol is out of range", () => {
    expect(embedCan({ available: false }, "cursor")).toBe(false);
    expect(embedCan(null, "cursor")).toBe(false);
    expect(embedCan({ available: true, protocol: 99, features: [], compatible: false }, "cursor")).toBe(false);
  });

  it("falls back to the protocol map when the server never sent `features`", () => {
    // An older server (pre-E1) reports only `{available, version, protocol}`.
    const legacy: EmbedCapability = { available: true, version: "0.3.4", protocol: 1 };
    expect(embedCan(legacy, "cursor")).toBe(true);
    expect(embedCan(legacy, "markers")).toBe(false);
  });
});

describe("featuresForProtocol", () => {
  it("grows monotonically with the protocol level", () => {
    const one = featuresForProtocol(1);
    const two = featuresForProtocol(2);
    expect(one.every((f) => two.includes(f))).toBe(true);
    expect(two.length).toBeGreaterThan(one.length);
    expect(featuresForProtocol("2")).toEqual([]);
  });
});

describe("embedShortfall — the one line a page shows instead of a broken control", () => {
  it("is null when the feature is there", () => {
    expect(embedShortfall(P2, "markers")).toBeNull();
  });

  it("names the missing feature and where to fix it", () => {
    const message = embedShortfall(P1, "markers");
    expect(message).toContain("markers");
    expect(message).toContain("Settings");
  });

  it("distinguishes 'nothing installed' from 'too new to drive'", () => {
    expect(embedShortfall({ available: false }, "markers")).toContain("No viewer bundle is installed");
    const tooNew = embedShortfall({ available: true, protocol: 99, compatible: false }, "markers");
    expect(tooNew).toContain("protocol 99");
    expect(embedIsCompatible({ available: true, protocol: 99, compatible: false })).toBe(false);
  });
});
