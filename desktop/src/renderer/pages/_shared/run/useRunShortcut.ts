import { useEffect } from "react";
import { usePageActive } from "../../../app/pageActivity";

/**
 * `⌘⏎` / `Ctrl+⏎` fires the run page's primary action from anywhere on the page (DESIGN.md v3
 * §2.3, checklist item 8). Bound per page rather than in `app/keyboard.ts` because the shell has
 * no idea what "the primary" is — only the page that built the action bar does.
 *
 * Ignored while a modal/overlay owns the document (`[role="dialog"]` present), so ⌘⏎ inside the
 * QSIPrep dialog belongs to the dialog, not to the page behind it.
 */
export function useRunShortcut(onRun: () => void, enabled = true): void {
  const active = usePageActive();
  useEffect(() => {
    if (!enabled || !active) return;
    function onKeyDown(e: KeyboardEvent): void {
      if (e.key !== "Enter" || !(e.metaKey || e.ctrlKey) || e.altKey) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      e.preventDefault();
      onRun();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onRun, enabled, active]);
}
