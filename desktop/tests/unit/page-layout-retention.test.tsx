// @vitest-environment jsdom
import React, { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PageActivityContext, usePageActive } from "../../src/renderer/app/pageActivity";
import { PageLayout, usePaneController, type PaneController } from "../../src/renderer/ui/Layout";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("PageLayout retains hidden pane sessions", () => {
  let container: HTMLDivElement;
  let root: Root;
  let controller: PaneController;
  let sequence = 0;
  let pageId: string;
  const mounts: string[] = [];
  const disposals: string[] = [];

  beforeEach(() => {
    pageId = `retained-layout-${++sequence}`;
    mounts.length = 0;
    disposals.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function Probe({ name }: { name: string }) {
    const active = usePageActive();
    useEffect(() => {
      mounts.push(name);
      return () => { disposals.push(name); };
    }, [name]);
    return <output data-probe={name} data-active={String(active)} />;
  }

  function Harness({ legacy }: { legacy: boolean }) {
    controller = usePaneController({ pageId, name: "run" });
    return (
      <PageLayout
        paneController={controller}
        resizableInspector={legacy}
        rightPane={<><Probe name="scene" /><iframe title="live scene" src="about:blank" /></>}
      >
        <Probe name="work" />
        <input aria-label="unsaved draft" defaultValue="" />
      </PageLayout>
    );
  }

  function render(legacy: boolean, active = true) {
    act(() => root.render(
      <PageActivityContext.Provider value={active}><Harness legacy={legacy} /></PageActivityContext.Provider>,
    ));
  }

  for (const legacy of [false, true]) {
    const shape = legacy ? "legacy split" : "run layout";

    it(`${shape}: collapse retains the iframe and disables only the hidden pane`, () => {
      render(legacy);
      const pane = container.querySelector<HTMLElement>('[data-testid="page-right-pane"]')!;
      const frame = pane.querySelector("iframe")!;
      const frameWindow = frame.contentWindow;
      pane.scrollTop = 29;

      act(() => controller.toggleCollapse());
      expect(container.querySelector('[data-testid="page-right-pane"]')).toBe(pane);
      expect(pane.hidden).toBe(true);
      expect(pane.getAttribute("aria-hidden")).toBe("true");
      expect(pane.hasAttribute("inert")).toBe(true);
      expect(frame.isConnected).toBe(true);
      expect(frame.contentWindow).toBe(frameWindow);
      expect(container.querySelector('[data-probe="scene"]')?.getAttribute("data-active")).toBe("false");
      expect(container.querySelector('[data-probe="work"]')?.getAttribute("data-active")).toBe("true");
      if (legacy) expect(container.querySelector<HTMLButtonElement>(".resizable-handle")?.hidden).toBe(true);

      // The parent controller must remain active while its children are hidden, so the normal
      // restore chord still works. A provider around the entire page would swallow this shortcut.
      act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "i", ctrlKey: true, shiftKey: true })));
      expect(pane.hidden).toBe(false);
      expect(pane.hasAttribute("inert")).toBe(false);
      expect(pane.scrollTop).toBe(29);
      expect(pane.querySelector("iframe")).toBe(frame);
      expect(frame.contentWindow).toBe(frameWindow);
      expect(mounts).toEqual(["work", "scene"]);
      expect(disposals).toEqual([]);
    });

    it(`${shape}: expansion retains work DOM, drafts and scroll; Escape restores it`, () => {
      render(legacy);
      const work = container.querySelector<HTMLElement>('[data-testid="page-work"]')!;
      const scroller = work.querySelector<HTMLElement>("[data-page-work-scroll]")!;
      const input = work.querySelector("input")!;
      const frame = container.querySelector("iframe")!;
      input.value = "incomplete placement";
      scroller.scrollTop = 137;

      act(() => controller.toggleExpand());
      expect(container.querySelector('[data-testid="page-work"]')).toBe(work);
      expect(work.hidden).toBe(true);
      expect(work.getAttribute("aria-hidden")).toBe("true");
      expect(work.hasAttribute("inert")).toBe(true);
      expect(container.querySelector('[data-probe="work"]')?.getAttribute("data-active")).toBe("false");
      expect(container.querySelector('[data-probe="scene"]')?.getAttribute("data-active")).toBe("true");
      expect(container.querySelector("iframe")).toBe(frame);

      act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
      expect(work.hidden).toBe(false);
      expect(work.hasAttribute("inert")).toBe(false);
      expect(work.querySelector("input")).toBe(input);
      expect(input.value).toBe("incomplete placement");
      expect(work.querySelector("[data-page-work-scroll]")).toBe(scroller);
      expect(scroller.scrollTop).toBe(137);
      expect(mounts).toEqual(["work", "scene"]);
      expect(disposals).toEqual([]);

      render(legacy, false);
      act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "i", ctrlKey: true, shiftKey: true })));
      expect(controller.mode).toBe("normal");
      expect(Array.from(container.querySelectorAll("[data-probe]"), (probe) => probe.getAttribute("data-active"))).toEqual(["false", "false"]);
    });
  }
});
