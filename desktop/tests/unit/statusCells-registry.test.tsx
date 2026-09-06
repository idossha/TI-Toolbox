// @vitest-environment jsdom
/**
 * The status-bar registry (DESIGN.md §11, program U8). The v2 bar printed `RAS — Space —
 * Renderer —` on the Jobs page; these tests are the mechanism that makes that unwritable.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  hasValue,
  sortStatusCells,
  useStatusCellStore,
  useRegisteredStatusCells,
  useStatusCells,
  type StatusCellSpec,
} from "../../src/renderer/app/statusCells";

function Page({ cells }: { cells: StatusCellSpec[] }) {
  useStatusCells(cells);
  return null;
}

/** Renders the registry the way `AppStatusBar` does, so the test reads what the bar would show. */
function Bar() {
  const cells = useRegisteredStatusCells();
  return <span data-testid="bar">{cells.map((c) => c.id).join(",")}</span>;
}

describe("useStatusCells", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    useStatusCellStore.setState({ byOwner: {} });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });
  const render = (el: React.ReactElement) => act(() => root.render(el));
  const bar = () => container.querySelector("[data-testid=bar]")!.textContent;

  it("renders the registered cells in priority order, ties broken by registration", () => {
    render(
      <>
        <Page
          cells={[
            { id: "planCost", value: "2 jobs", priority: 20 },
            { id: "lastJob", value: "pre · running", priority: 10 },
          ]}
        />
        <Bar />
      </>,
    );
    expect(bar()).toBe("lastJob,planCost");
  });

  it("does NOT register a cell with no value — there is no dash in the status bar", () => {
    render(
      <>
        <Page
          cells={[
            { id: "ras", value: null, priority: 10 },
            { id: "space", value: undefined, priority: 20 },
            { id: "renderer", value: "", priority: 30 },
            { id: "counts", value: "3 subjects", priority: 10 },
          ]}
        />
        <Bar />
      </>,
    );
    expect(bar()).toBe("counts");
  });

  it("unregisters on unmount, so a cell from the page you left cannot survive", () => {
    render(
      <>
        <Page cells={[{ id: "ras", value: "12.0 −18.0 9.0", priority: 10 }]} />
        <Bar />
      </>,
    );
    expect(bar()).toBe("ras");
    // Leaving the Viewer for Jobs: the Viewer's component unmounts, the Jobs page registers its own.
    render(
      <>
        <Page cells={[{ id: "jobCounts", value: "1 running", priority: 10 }]} />
        <Bar />
      </>,
    );
    expect(bar()).toBe("jobCounts");
  });

  it("two pages cannot clobber each other: registration is per component instance", () => {
    render(
      <>
        <Page cells={[{ id: "a", value: "1", priority: 10 }]} />
        <Page cells={[{ id: "b", value: "2", priority: 20 }]} />
        <Bar />
      </>,
    );
    expect(bar()).toBe("a,b");
  });

  it("an inline array literal does not write the store on every render", () => {
    let writes = 0;
    const unsubscribe = useStatusCellStore.subscribe(() => {
      writes++;
    });
    function Counter({ n }: { n: number }) {
      // The array is a fresh literal each render; only the VALUE changes on the second render.
      useStatusCells([{ id: "lastJob", value: `pre · ${n}s`, priority: 10 }]);
      return null;
    }
    render(<Counter n={1} />);
    const afterFirst = writes;
    render(<Counter n={1} />);
    expect(writes).toBe(afterFirst); // same value: no write
    render(<Counter n={2} />);
    expect(writes).toBeGreaterThan(afterFirst); // changed value: one write
    unsubscribe();
  });
});

describe("the pure helpers", () => {
  it("hasValue treats null, undefined and empty string as nothing to say", () => {
    expect(hasValue({ id: "a", value: null, priority: 10 })).toBe(false);
    expect(hasValue({ id: "a", value: undefined, priority: 10 })).toBe(false);
    expect(hasValue({ id: "a", value: "", priority: 10 })).toBe(false);
    expect(hasValue({ id: "a", value: 0, priority: 10 })).toBe(true); // 0 is a number, not "nothing"
  });

  it("sortStatusCells is stable across owners and drops the empty ones", () => {
    const sorted = sortStatusCells({
      viewer: [
        { id: "renderer", value: "Apple M2 Pro", priority: 30 },
        { id: "ras", value: "12.0", priority: 10 },
      ],
      page: [
        { id: "space", value: "subject", priority: 20 },
        { id: "gone", value: "", priority: 5 },
      ],
    });
    expect(sorted.map((c) => c.id)).toEqual(["ras", "space", "renderer"]);
  });
});
