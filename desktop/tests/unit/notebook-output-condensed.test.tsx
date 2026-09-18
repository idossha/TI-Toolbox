// @vitest-environment jsdom
/**
 * A long text output is condensed by default: one scrolling box, the whole
 * text still there, a toggle to show it all. A FEM run or a flex-search writes
 * tens of thousands of SimNIBS log lines into the cell, one stream message per
 * line, and unconstrained they pushed every later cell off the page.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  CONDENSED_AFTER_LINES,
  OutputList,
  coalesceStreams,
  textLineCount,
} from "../../src/renderer/pages/notebooks/Outputs";
import type { Output } from "../../src/renderer/pages/notebooks/notebook";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function stream(name: "stdout" | "stderr", text: string | string[]): Output {
  return { output_type: "stream", name, text } as Output;
}

function textOf(output: Output | undefined): string | string[] {
  return (output as unknown as { text: string | string[] }).text;
}

function render(outputs: Output[]): void {
  act(() => root.render(<OutputList outputs={outputs} />));
}

describe("coalesceStreams", () => {
  it("merges consecutive writes to the same stream and keeps the rest apart", () => {
    const merged = coalesceStreams([
      stream("stdout", "a\n"),
      stream("stdout", "b\n"),
      stream("stderr", "warn\n"),
      stream("stdout", "c\n"),
    ]);
    expect(merged.map(textOf)).toEqual(["a\nb\n", "warn\n", "c\n"]);
  });

  it("does not touch the outputs it was given", () => {
    const outputs = [stream("stdout", "a\n"), stream("stdout", "b\n")];
    coalesceStreams(outputs);
    expect(textOf(outputs[0])).toBe("a\n");
    expect(outputs).toHaveLength(2);
  });
});

describe("textLineCount", () => {
  it("counts rows, not newline characters", () => {
    expect(textLineCount([stream("stdout", "a\nb\n")])).toBe(2);
    expect(textLineCount([stream("stdout", "a\nb")])).toBe(2);
    expect(textLineCount([stream("stdout", ["x\n", "y\n"])])).toBe(2);
    expect(textLineCount([])).toBe(0);
  });
});

describe("OutputList", () => {
  it("a short output is shown whole, with no toggle", () => {
    render([stream("stdout", "done\n")]);
    expect(
      container.querySelector('[data-testid="nb-output-toggle"]'),
    ).toBeNull();
    expect(container.querySelector(".nb-output__body--condensed")).toBeNull();
    expect(container.textContent).toContain("done");
  });

  it("a long log is condensed by default, every line still present, and expands on Show all", () => {
    const lines = CONDENSED_AFTER_LINES * 10;
    const outputs: Output[] = [];
    for (let i = 0; i < lines; i += 1)
      outputs.push(stream("stderr", `[ simnibs ] INFO: Goal: ${i}\n`));
    render(outputs);

    const body = container.querySelector('[data-testid="nb-output-body"]');
    expect(body?.classList.contains("nb-output__body--condensed")).toBe(true);
    // One block of text, not one <pre> per kernel message.
    expect(container.querySelectorAll("pre")).toHaveLength(1);
    expect(container.textContent).toContain(`Goal: ${lines - 1}`);
    expect(container.textContent).toContain("Goal: 0");
    expect(container.querySelector(".nb-output__count")?.textContent).toBe(
      `${lines.toLocaleString()} lines`,
    );

    const toggle = container.querySelector<HTMLButtonElement>(
      '[data-testid="nb-output-toggle"]',
    );
    expect(toggle?.textContent).toBe("Show all");
    act(() => toggle?.click());
    expect(body?.classList.contains("nb-output__body--condensed")).toBe(false);
    expect(
      container.querySelector('[data-testid="nb-output-toggle"]')?.textContent,
    ).toBe("Condense");
  });
});
