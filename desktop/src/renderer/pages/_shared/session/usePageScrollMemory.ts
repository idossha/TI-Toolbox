/**
 * Page-level scroll memory for non-run pages (lane Memory round 1).
 *
 * Run pages already get the same rule from `RunWork`: where the user scrolled is session state,
 * not component state. Settings, Results and optional panel pages do not render `RunWork`, so a
 * navigation away used to rebuild their work pane at the top. This hook attaches the existing
 * scroll-memory primitive to the page's `PageLayout` scrollport without touching `ui/Layout.tsx`:
 * layout remains a pure skeleton, and pages opt in only where the product says a draft should
 * survive navigation.
 *
 * The backing store is `app/pageSession.ts`, so it is memory-only and is cleared on an actual
 * project switch by `Shell`. It deliberately does not use localStorage; closing the app resets the
 * draft and scroll offset.
 */
import { useEffect } from "react";
import { usePageId, usePageSessionRef } from "../../../app/pageSession";
import { usePageActive } from "../../../app/pageActivity";
import { attachScrollMemory } from "../run/scrollMemory";

export function usePageScrollMemory(key = "workScroll"): void {
  const active = usePageActive();
  const pageId = usePageId();
  const bag = usePageSessionRef<number>(key);
  const scrollRead = bag.read;
  const scrollWrite = bag.write;

  useEffect(() => {
    if (!active) return;
    const page = pageId ? document.querySelector(`[data-page-panel="${pageId}"]`) : document;
    const scroller = page?.querySelector<HTMLElement>("[data-page-work-scroll]");
    if (!scroller) return;
    // Run pages own scroll memory in `RunWork`; attaching a second recorder to the same scrollport
    // would make two restore loops fight over the same key. Non-run pages have no `run-work`.
    if (scroller.querySelector('[data-testid="run-work"]')) return;
    const memory = attachScrollMemory(scroller, scrollRead, scrollWrite);
    if (typeof ResizeObserver === "undefined") return () => memory.dispose();
    const content = scroller.firstElementChild;
    const ro = new ResizeObserver(() => memory.retry());
    if (content) ro.observe(content);
    ro.observe(scroller);
    return () => {
      ro.disconnect();
      memory.dispose();
    };
  }, [active, pageId, scrollRead, scrollWrite]);
}
