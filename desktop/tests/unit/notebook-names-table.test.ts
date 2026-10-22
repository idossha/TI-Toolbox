// @vitest-environment jsdom
/**
 * The Notebooks page names an imported `.ipynb` by the server's rule (`proposeName`, checked
 * against `tit/server/notebooks.py::normalise_name` through one shared table).
 *
 * Where the expected values come from: `tests/fixtures/notebook_names.json`, verdicts written by
 * hand from the rule in its `_about`; `tests/test_notebook_names_table.py` checks the server
 * against the same rows. The `client` column is what this page must return. 2026-10-22.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// jsdom ships no `matchMedia`; the Notebooks page reaches modules that call it at import.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({ matches: false, media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }),
});

const { proposeName } = await import("../../src/renderer/pages/notebooks/index");

interface Row {
  why: string;
  name: string;
  length?: number;
  client: string | null;
  server: string | null;
}

const rows = (JSON.parse(readFileSync(resolve(__dirname, "../../../tests/fixtures/notebook_names.json"), "utf8")) as { rows: Row[] }).rows;

describe("proposeName over the shared notebook-name table", () => {
  it("covers accepted and refused names and the 128/129 boundary", () => {
    expect(rows.some((row) => row.client === null)).toBe(true);
    expect(rows.some((row) => row.client !== null)).toBe(true);
    for (const row of rows.filter((r) => r.length !== undefined)) expect(row.name).toHaveLength(row.length!);
    expect(rows.map((row) => row.length).filter(Boolean).sort()).toEqual([128, 129]);
  });

  it.each(rows.map((row) => [row.why, row] as const))("%s", (_why, row) => {
    expect(proposeName(row.name)).toBe(row.client);
  });
});
