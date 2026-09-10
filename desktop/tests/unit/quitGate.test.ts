import { describe, expect, it } from "vitest";
import { createQuitGate } from "../../src/shared/quitGate";

describe("createQuitGate", () => {
  it("starts unapproved", () => {
    const gate = createQuitGate();
    expect(gate.isApproved()).toBe(false);
  });

  it("reports approved after approve()", () => {
    const gate = createQuitGate();
    gate.approve();
    expect(gate.isApproved()).toBe(true);
  });

  it("reverts to unapproved after reset()", () => {
    const gate = createQuitGate();
    gate.approve();
    gate.reset();
    expect(gate.isApproved()).toBe(false);
  });

  it("models the macOS reopen bug this replaces: a fresh window generation must not inherit an earlier generation's approval", () => {
    const gate = createQuitGate();

    // First window: user quits, the running-jobs prompt runs, then the app approves the close.
    expect(gate.isApproved()).toBe(false);
    gate.approve();
    expect(gate.isApproved()).toBe(true);

    // macOS: the app stays alive with no windows; `activate` opens a new one. `index.ts` must
    // reset the gate here — without this line the bug reproduces (second generation "approved").
    gate.reset();

    // Second window generation: its own close must run the prompt again, not skip it.
    expect(gate.isApproved()).toBe(false);
  });

  it("two independent gates do not share state", () => {
    const a = createQuitGate();
    const b = createQuitGate();
    a.approve();
    expect(a.isApproved()).toBe(true);
    expect(b.isApproved()).toBe(false);
  });
});
