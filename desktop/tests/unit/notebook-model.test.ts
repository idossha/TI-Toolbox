import { describe, expect, it } from "vitest";
import {
  cellKey,
  cellText,
  convertCell,
  isCodeCell,
  newCell,
  retireCellKey,
  type Cell,
  type CodeCell,
  type Notebook,
} from "../../src/renderer/pages/notebooks/notebook";
import { renderMarkdown } from "../../src/renderer/pages/notebooks/markdown";

function notebook(minor = 5): Notebook {
  return { cells: [], metadata: {}, nbformat: 4, nbformat_minor: minor };
}

describe("the notebook model", () => {
  it("reads a source stored as a list of lines exactly as one stored as a string", () => {
    // nbformat stores multi-line strings as lists; a renderer that only handles
    // one of the two shows half the notebooks in a project as empty.
    const asList: Cell = { cell_type: "code", source: ["a = 1\n", "b = 2"], metadata: {} };
    expect(cellText(asList)).toBe("a = 1\nb = 2");
    expect(cellText({ cell_type: "code", source: "a = 1", metadata: {} })).toBe("a = 1");
  });

  it("mints a cell id only where the format version has one", () => {
    // A v4.4 file that gained ids on save is a file every other tool re-diffs.
    expect(newCell("code", notebook(5)).id).toBeTypeOf("string");
    expect(newCell("code", notebook(4)).id).toBeUndefined();
  });

  it("gives a new code cell the keys nbformat requires of one", () => {
    const cell = newCell("code", notebook()) as CodeCell;
    expect(cell.outputs).toEqual([]);
    expect(cell.execution_count).toBeNull();
    expect(newCell("markdown", notebook())).not.toHaveProperty("outputs");
  });

  it("adds and removes the code-only keys when a cell changes type", () => {
    const cell = newCell("code", notebook()) as Cell;
    (cell as CodeCell).outputs.push({ output_type: "stream", name: "stdout", text: "x" });
    convertCell(cell, "markdown");
    expect(cell.cell_type).toBe("markdown");
    // A markdown cell with an `outputs` key is not a valid notebook.
    expect(cell).not.toHaveProperty("outputs");
    expect(cell).not.toHaveProperty("execution_count");
    convertCell(cell, "code");
    expect((cell as CodeCell).outputs).toEqual([]);
    expect(isCodeCell(cell)).toBe(true);
  });

  it("keys a cell by identity, and re-keys it on demand", () => {
    // The key must survive a mutation (the notebook is edited in place) and
    // must NOT survive a type change (the editor cannot be re-pointed).
    const cell = newCell("code", notebook());
    const first = cellKey(cell);
    cell.source = "changed";
    expect(cellKey(cell)).toBe(first);
    retireCellKey(cell);
    expect(cellKey(cell)).not.toBe(first);
  });

  it("keys two cells that carry no id apart", () => {
    const a: Cell = { cell_type: "code", source: "", metadata: {} };
    const b: Cell = { cell_type: "code", source: "", metadata: {} };
    expect(cellKey(a)).not.toBe(cellKey(b));
  });
});

describe("markdown cells", () => {
  it("renders the shapes a notebook heading cell actually uses", () => {
    expect(renderMarkdown("# Title")).toBe("<h1>Title</h1>");
    expect(renderMarkdown("- one\n- two")).toBe("<ul>\n<li>one</li>\n<li>two</li>\n</ul>");
    expect(renderMarkdown("a **bold** and `code`")).toBe(
      "<p>a <strong>bold</strong> and <code>code</code></p>",
    );
    expect(renderMarkdown("```\nx = 1\n```")).toBe("<pre><code>x = 1</code></pre>");
  });

  it("shows HTML in a cell as text rather than running it", () => {
    // The security property this file rests on: source is escaped first, and
    // markup is only ever added to escaped text.
    const html = renderMarkdown('<img src=x onerror="steal()">');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("refuses a link scheme that is not http or mailto", () => {
    expect(renderMarkdown("[x](javascript:alert(1))")).not.toContain("<a ");
    expect(renderMarkdown("[x](https://example.org)")).toContain('href="https://example.org"');
  });
});
