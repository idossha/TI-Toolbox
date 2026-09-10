import { describe, expect, it } from "vitest";
import { failureReason } from "../../src/renderer/app/jobs-rail/format";

describe("failureReason", () => {
  it("picks the error line out of a Python traceback, not a frame", () => {
    const lines = [
      "Traceback (most recent call last):",
      '  File "/opt/tit/sim/__main__.py", line 42, in <module>',
      "    main()",
      '  File "/opt/tit/sim/runner.py", line 88, in main',
      "    cfg = SimulationConfig(**payload)",
      "          ^^^^^^^^^^^^^^^^^^^^^^^^^^^",
      "TypeError: SimulationConfig.__init__() missing 2 required positional arguments: 'subject_id' and 'montages'",
      "",
    ];
    expect(failureReason(lines, 1)).toBe(
      "TypeError: SimulationConfig.__init__() missing 2 required positional arguments: 'subject_id' and 'montages'",
    );
  });

  it("returns the last line of plain stderr", () => {
    expect(failureReason(["starting", "reading mesh", "fatal: mesh not found"], 1)).toBe("fatal: mesh not found");
  });

  it("falls back to the exit code when there is nothing meaningful", () => {
    expect(failureReason([], 137)).toBe("exited with code 137");
    expect(failureReason(undefined, 1)).toBe("exited with code 1");
    expect(failureReason(["", "   "], 2)).toBe("exited with code 2");
    // Only frames captured: still the exit code, never a `File "…"` line.
    expect(failureReason(['  File "/x.py", line 1, in <module>', "    boom()"], 1)).toBe("exited with code 1");
  });

  it("has a wording for a failure with no exit code at all", () => {
    expect(failureReason([], null)).toBe("the runner exited without a status");
  });
});
