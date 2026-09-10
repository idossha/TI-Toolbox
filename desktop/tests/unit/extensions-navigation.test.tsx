// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavRail } from "../../src/renderer/app/NavRail";

const state = vi.hoisted(() => ({
  panels: ["source", "cluster-permutation"],
  labelled: true,
}));
vi.mock("../../src/renderer/app/registry", () => ({
  useNavSections: () => [
    {
      id: "workflow",
      pinned: false,
      pages: [
        { id: "jobs", title: "Jobs", icon: () => null },
        ...state.panels.map((id) => ({
          id: `panel-${id}`,
          title: id,
          icon: () => null,
          navGroup: "panels",
        })),
      ],
    },
  ],
  pageById: () => undefined,
  pagePath: ({ id }: { id: string }) => `/${id}`,
}));
vi.mock("../../src/renderer/ui/Overlay", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
}));

describe("Extensions navigation", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    state.panels = ["source", "cluster-permutation"];
    state.labelled = true;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: () => null, setItem: vi.fn() },
    });
    window.matchMedia = vi
      .fn()
      .mockImplementation(() => ({
        matches: state.labelled,
        addEventListener() {},
        removeEventListener() {},
      }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });
  function render() {
    act(() =>
      root.render(
        <MemoryRouter initialEntries={["/panel-source"]}>
          <NavRail />
        </MemoryRouter>,
      ),
    );
  }
  it("groups enabled tools after Jobs while preserving their routes and active child", () => {
    render();
    const group = container.querySelector<HTMLButtonElement>(
      '[aria-label="Extensions"]',
    )!;
    const children = container.querySelector<HTMLElement>(
      "#nav-subitems-extensions",
    )!;
    expect(group.dataset.containsActive).toBe("true");
    expect(group.getAttribute("aria-current")).toBeNull();
    expect(
      [...children.querySelectorAll("a")].map((item) =>
        item.getAttribute("href"),
      ),
    ).toEqual(["/panel-source", "/panel-cluster-permutation"]);
    expect(children.querySelector('[aria-current="page"]')?.textContent).toBe(
      "source",
    );
    expect(
      container
        .querySelector('[data-testid="nav-item-jobs"]')!
        .compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    act(() => group.click());
    expect(children.hidden).toBe(true);
    expect(group.getAttribute("aria-expanded")).toBe("false");
    act(() => group.click());
    expect(children.hidden).toBe(false);
  });
  it("keeps each extension reachable from the compact icon rail", () => {
    state.labelled = false;
    render();
    expect(container.querySelector('[data-rail-mode="icons"]')).not.toBeNull();
    expect(container.querySelectorAll(".nav-extension-icon")).toHaveLength(2);
    expect(
      container.querySelector('[aria-label="source"]')?.getAttribute("href"),
    ).toBe("/panel-source");
  });
  it("removes disabled tools and hides the group when none are enabled", () => {
    state.panels = ["source"];
    render();
    expect(
      container.querySelector('[aria-label="cluster-permutation"]'),
    ).toBeNull();
    state.panels = [];
    render();
    expect(container.querySelector('[aria-label="Extensions"]')).toBeNull();
  });
});
