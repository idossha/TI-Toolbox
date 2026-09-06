// @vitest-environment jsdom
/**
 * Ground rows belong to the table that owns the rows (cleanup round, lane CL2, item 3 — lane
 * FIX-D's cross-lane request 3).
 *
 * Two pages needed the shape of a list under a short one, and neither could ask for it: `ui/
 * DataTable` renders its own `<tr>`s, so `pages/jobs/jobs-page.css` and `pages/panels/panels.css`
 * each painted the same repeating gradient BEHIND the table — one rule, written twice, in two
 * files that do not know about each other, at a pitch that only happened to match the table's own
 * rows. The rows are the table's now (`fill`/`minRows`), and this file keeps the copies deleted.
 *
 * `tests/e2e/table-room.spec.ts` measures the result on the real pages (22 ground rows on Jobs,
 * 20 on Subject info, the painted divs gone, both inside L5a); what is asserted here is the row
 * contract and the absence of the duplicate rule, which no screenshot can show.
 */
import React, { act } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DataTable, type DataTableColumn } from "../../src/renderer/ui/DataTable";
import { SubjectsField } from "../../src/renderer/pages/_shared/subjects/SubjectsField";
import { clearPageSession } from "../../src/renderer/app/pageSession";
import { ElectrodePairsEditor } from "../../src/renderer/ui/ElectrodePairsEditor";
import type { Coordinate } from "../../src/renderer/ui/CoordinateInput";

const CSS = (path: string): string => readFileSync(resolve(__dirname, "../../src/renderer", path), "utf8");

interface Row {
  id: string;
  name: string;
}
const COLUMNS: DataTableColumn<Row>[] = [
  { id: "name", header: "Name", accessorKey: "name" },
  { id: "id", header: "Id", accessorKey: "id" },
];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
function render(el: React.ReactElement) {
  act(() => root.render(el));
}

describe("ui/DataTable draws its own ground rows", () => {
  it("pads a short list to `minRows`, and the pad rows are hidden from the accessibility tree", () => {
    render(<DataTable data={[{ id: "a", name: "Alpha" }]} columns={COLUMNS} getRowId={(r) => r.id} minRows={6} />);
    const body = container.querySelector("tbody")!;
    expect(body.querySelectorAll("tr")).toHaveLength(6);
    const ground = body.querySelectorAll("tr.data-table-filler");
    expect(ground).toHaveLength(5);
    // A ground row is scenery: it must not be read out as a row of the list, and it spans the
    // whole table so it lines up with the rows above it.
    expect(ground[0]!.getAttribute("aria-hidden")).toBe("true");
    expect(ground[0]!.querySelector("td")!.getAttribute("colspan")).toBe("2");
  });

  it("keeps the empty state's message row and pads below it", () => {
    render(<DataTable data={[]} columns={COLUMNS} emptyMessage="Nothing has run yet." minRows={4} />);
    const rows = container.querySelectorAll("tbody tr");
    expect(rows[0]!.textContent).toBe("Nothing has run yet.");
    expect(container.querySelectorAll("tbody tr.data-table-filler")).toHaveLength(3);
  });

  it("draws nothing extra when the page asks for nothing", () => {
    render(<DataTable data={[{ id: "a", name: "Alpha" }]} columns={COLUMNS} getRowId={(r) => r.id} />);
    expect(container.querySelectorAll("tbody tr.data-table-filler")).toHaveLength(0);
    expect(container.querySelector(".data-table-container")!.getAttribute("data-fill")).toBeNull();
  });
});

describe("the duplicate ground-row rule stays deleted", () => {
  it("neither page paints ground rows behind a table any more", () => {
    for (const path of ["pages/jobs/jobs-page.css", "pages/panels/panels.css"]) {
      const css = CSS(path);
      expect(css, `${path} still paints ground rows`).not.toMatch(/repeating-linear-gradient/);
      expect(css, `${path} still carries a filler element`).not.toMatch(/\.(jobs-page|panel-table)-filler\s*\{/);
    }
  });

  it("the rule exists once, in the stylesheet of the component that renders the rows", () => {
    const components = CSS("ui/components.css");
    const matches = components.match(/\.data-table tbody tr\.data-table-filler td\s*\{/g) ?? [];
    expect(matches).toHaveLength(1);
    // The pitch and the surface are the row's own — that is the whole reason the rows moved here.
    const block = components.slice(components.indexOf(matches[0]!));
    expect(block.slice(0, block.indexOf("}"))).toMatch(/height:\s*var\(--row-h\)/);
  });

  it("`.run-subject-scroll`'s cap is a default a page can lift, not a ceiling", () => {
    const run = CSS("pages/_shared/run/run.css");
    expect(run).toMatch(/\.run-subject-scroll\s*\{[^}]*max-height:\s*176px/);
    expect(run).toMatch(/\.run-subject-scroll\[data-fill="true"\]\s*\{[^}]*max-height:\s*none/);
    // And the page that needed it lifted no longer reaches into `pages/_shared` to do it.
    expect(CSS("pages/panels/panels.css")).not.toMatch(/\.run-subject-scroll[^*\n]*\{/);
  });
});

describe("SubjectsField says which shape it is", () => {
  const subjects = [{ id: "ernie" }, { id: "101" }, { id: "MNI152" }];

  it("marks the control and its scroll box when the page asks for the room", () => {
    render(<SubjectsField subjects={subjects} value={[]} onChange={() => {}} defaultOpen fill />);
    expect(container.querySelector(".subjects-field")!.getAttribute("data-fill")).toBe("true");
    expect(container.querySelector(".run-subject-scroll")!.getAttribute("data-fill")).toBe("true");
  });

  it("leaves both unmarked otherwise, so every other page keeps the 176px default", () => {
    render(<SubjectsField subjects={subjects} value={[]} onChange={() => {}} defaultOpen />);
    expect(container.querySelector(".subjects-field")!.getAttribute("data-fill")).toBeNull();
    expect(container.querySelector(".run-subject-scroll")!.getAttribute("data-fill")).toBeNull();
  });

  // The subject list ends after the last subject: the maintainer's "just a simple list of
  // subjects". `fill` still decides how much ROOM the box may take; it never pads the list out.
  it("draws no ground rows, in either shape", () => {
    render(<SubjectsField subjects={subjects} value={[]} onChange={() => {}} defaultOpen fill />);
    expect(container.querySelectorAll("tbody tr.run-table-filler")).toHaveLength(0);
    expect(container.querySelectorAll("tbody tr.selection-row")).toHaveLength(3);
  });
});

describe("a control is drawn only when it can act", () => {
  it("ElectrodePairsEditor hides the source switcher when the caller offers one mode", () => {
    const base = {
      mode: "net" as const,
      electrodes: ["E1", "E2"],
      pairs: [["E1", "E2"]] as [string, string][],
      onPairsChange: () => {},
      freehandPairs: [] as [Coordinate, Coordinate][],
      onFreehandPairsChange: () => {},
    };
    // `pages/simulator/MontageManager.tsx` used to pass `onModeChange={() => {}}` here: the
    // control moved when clicked and snapped straight back, because a montage built on an EEG net
    // has no free-hand mode to switch to.
    render(<ElectrodePairsEditor {...base} />);
    expect(container.querySelectorAll(".segmented")).toHaveLength(0);

    render(<ElectrodePairsEditor {...base} onModeChange={() => {}} />);
    const segment = container.querySelector(".segmented")!;
    expect(segment.getAttribute("aria-label")).toBe("Electrode source");
  });
});
