// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** The last list rendered, so a test can play the scroll the real `VirtualList` would report. */
const lastList: { followTail?: boolean; onScrollAwayFromTail?: () => void } = {};
vi.mock("../../src/renderer/ui/VirtualList", () => ({
  VirtualList: <T,>({ items, renderRow, className, followTail, onScrollAwayFromTail }: { items: T[]; renderRow: (item: T, index: number) => React.ReactNode; className?: string; followTail?: boolean; onScrollAwayFromTail?: () => void }) => {
    lastList.followTail = followTail;
    lastList.onScrollAwayFromTail = onScrollAwayFromTail;
    return <div className={className}>{items.map((item, index) => <React.Fragment key={index}>{renderRow(item, index)}</React.Fragment>)}</div>;
  },
}));

import { JobConsole, type JobLogLine } from "../../src/renderer/ui/Jobs";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function render(sourceKey: string, lines: JobLogLine[]): Promise<void> {
  await act(async () => root.render(<JobConsole sourceKey={sourceKey} lines={lines} />));
}

async function click(selector: string): Promise<void> {
  await act(async () => (container.querySelector(selector) as HTMLElement).click());
}

function renderedLines(): string[] {
  return Array.from(container.querySelectorAll(".job-console-line"), (line) => line.textContent ?? "");
}

describe("JobConsole clear", () => {
  it("hides the current transcript without mutating it, then shows newer lines", async () => {
    // Frozen as well as compared: Clear must be a watermark over the caller's array, never a
    // splice of it (the plan's "leaves the input array byte-for-byte unchanged").
    const lines: JobLogLine[] = Object.freeze([
      Object.freeze({ seq: 1, level: "info", text: "one" }),
      Object.freeze({ seq: 2, level: "warning", text: "two" }),
    ]) as JobLogLine[];
    const before = structuredClone(lines);
    await render("job:first", lines);

    await click('[aria-label="Clear terminal"]');
    expect(renderedLines()).toEqual([]);
    expect(container.querySelector('[data-testid="job-console-cleared"]')?.textContent).toContain("Terminal cleared");
    expect(lines).toEqual(before);

    await render("job:first", [...lines, { seq: 3, level: "error", text: "three" }]);
    expect(renderedLines()).toEqual(["three"]);
  });

  it("resets the clear watermark and filter for a new source while retaining Follow", async () => {
    await render("job:first", [{ seq: 9, text: "first source" }]);
    const filter = container.querySelector('[aria-label="Filter log lines"]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(filter, "missing");
      filter.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await click('[aria-label="Follow tail"]');
    await click('[aria-label="Clear terminal"]');

    await render("job:second", [{ seq: 1, text: "second source" }]);
    expect((container.querySelector('[aria-label="Filter log lines"]') as HTMLInputElement).value).toBe("");
    expect(container.querySelector('[aria-label="Follow tail"]')?.getAttribute("aria-checked")).toBe("false");
    expect(renderedLines()).toEqual(["second source"]);
  });
});

describe("JobConsole follow", () => {
  it("turns Follow off when the reader scrolls back, and the switch turns it on again", async () => {
    await render("job:first", [{ seq: 1, text: "one" }]);
    expect(lastList.followTail).toBe(true);

    await act(async () => lastList.onScrollAwayFromTail!());
    expect(container.querySelector('[aria-label="Follow tail"]')?.getAttribute("aria-checked")).toBe("false");
    expect(lastList.followTail).toBe(false);

    // New output must not re-pin the tail behind the reader's back.
    await render("job:first", [{ seq: 1, text: "one" }, { seq: 2, text: "two" }]);
    expect(lastList.followTail).toBe(false);

    await click('[aria-label="Follow tail"]');
    expect(lastList.followTail).toBe(true);
  });
});
