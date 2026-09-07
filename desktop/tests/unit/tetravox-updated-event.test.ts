/**
 * `/ws/tetravox`'s one message, and the narrowing that keeps everything else off the screen.
 *
 * The toast is the only thing a user sees of the automatic update (A3), so what reaches it must
 * be the server's own sentence and nothing else: a message of another type, a payload without a
 * version, or a string that is not JSON must all produce no toast rather than a blank one.
 */
import { describe, expect, it } from "vitest";
import { asTetravoxUpdated } from "../../src/renderer/app/useTetravoxUpdated";

describe("asTetravoxUpdated", () => {
  it("accepts the server's event verbatim", () => {
    expect(
      asTetravoxUpdated({
        type: "tetravox.updated",
        version: "0.3.12",
        protocol: 2,
        message: "Tetravox 0.3.12 installed and active — reload the viewer to use it",
      }),
    ).toEqual({
      type: "tetravox.updated",
      version: "0.3.12",
      protocol: 2,
      message: "Tetravox 0.3.12 installed and active — reload the viewer to use it",
    });
  });

  it("falls back to a sentence rather than showing an empty toast", () => {
    expect(asTetravoxUpdated({ type: "tetravox.updated", version: "0.4.0" })).toEqual({
      type: "tetravox.updated",
      version: "0.4.0",
      protocol: null,
      message: "Tetravox 0.4.0 installed",
    });
  });

  it("ignores anything that is not this event", () => {
    expect(asTetravoxUpdated(null)).toBeNull();
    expect(asTetravoxUpdated("tetravox.updated")).toBeNull();
    expect(asTetravoxUpdated({ type: "job", job: { id: "x" } })).toBeNull();
    expect(asTetravoxUpdated({ type: "tetravox.updated" })).toBeNull();
    expect(asTetravoxUpdated({ type: "tetravox.updated", version: 3 })).toBeNull();
  });
});
