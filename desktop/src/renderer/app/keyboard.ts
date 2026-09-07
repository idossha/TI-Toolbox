import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { SHORTCUT_ALIASES, enabledPages } from "./registry";

/**
 * "Unmodified keys belong to whatever has focus" (plan §3, DESIGN.md §6.5). That is the rule the
 * Tetravox canvas needs — its own keys are bare letters and arrows — and it is the same rule a
 * text input has always needed. Anything that claims its unmodified keys says so with
 * `data-keyboard-owner`; a focused `<canvas>` claims them implicitly, since a canvas is only ever
 * focusable because something wants its keystrokes.
 */
export function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT") return true;
  if (el.isContentEditable) return true;
  if (el.tagName === "CANVAS") return true;
  return el.closest("[data-keyboard-owner]") !== null;
}

/**
 * Synchronous best-effort platform check for the shortcut glyph (⌘ vs Ctrl) shown in the palette
 * and the keyboard sheet. `window.tit.platform()` is the authoritative source in Electron but is
 * async and only exists inside the shell; `navigator.platform` (deprecated but still populated by
 * every engine we ship on) is good enough for a label and works in browser mode too.
 */
export const isMac =
  typeof navigator !== "undefined" && (/mac/i.test(navigator.platform ?? "") || /mac/i.test(navigator.userAgent));

/** The modifier glyph/word for a shortcut label, e.g. "⌘1" or "Ctrl+1". */
export function modKey(digitOrLetter: string): string {
  return isMac ? `⌘${digitOrLetter}` : `Ctrl+${digitOrLetter}`;
}

/** With Shift, e.g. "⌘⇧N" or "Ctrl+Shift+N". */
export function modShiftKey(letter: string): string {
  return isMac ? `⌘⇧${letter}` : `Ctrl+Shift+${letter}`;
}

export interface ShellShortcuts {
  /** ⌘J — the jobs panel. */
  toggleJobs: () => void;
  /** ⌘K — the command palette. */
  openPalette: () => void;
  /** ⌘P — the subject switcher. */
  openSubjectSwitcher: () => void;
  /** ⌘⇧N — the quick-notes drawer. */
  toggleQuickNotes: () => void;
  /** ? — the keyboard sheet. The one shortcut without a modifier, and only when nothing is focused. */
  openKeyboardSheet: () => void;
  /** ⌘⇧V — move focus to the viewer canvas, so its own keys start working. */
  focusViewer: () => void;
}

/**
 * Every app shortcut carries ⌘/Ctrl, with `?` as the single documented exception. `Esc` closing
 * overlays and `Enter` submitting from a primary button are Radix's and each form's job, not this
 * hook's.
 */
export function useGlobalShortcuts(handlers: ShellShortcuts): void {
  const navigate = useNavigate();
  // The handler object is rebuilt on every Shell render; keeping it in a ref means the listener is
  // attached once instead of on every keystroke-driven state change.
  const ref = useRef(handlers);
  useEffect(() => {
    ref.current = handlers;
  });

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const typing = isTypingTarget(e.target);

      // The one unmodified shortcut. A real keystroke reports `e.key === "?"`, but a synthesised
      // Shift+"/" (CDP, and therefore Playwright's `press("Shift+/")`) reports the unshifted `"/"`
      // with `shiftKey` set. Accept both so the binding does not depend on who produced the event.
      const isQuestionMark = e.key === "?" || (e.shiftKey && e.key === "/");
      if (isQuestionMark && !e.metaKey && !e.ctrlKey && !e.altKey && !typing) {
        e.preventDefault();
        ref.current.openKeyboardSheet();
        return;
      }

      if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
      const key = e.key.toLowerCase();

      // ⌘-prefixed shortcuts work while typing too: they are how you leave a form, and a person
      // half-way through a field still expects ⌘K to open the palette.
      if (e.shiftKey) {
        if (key === "n") {
          e.preventDefault();
          ref.current.toggleQuickNotes();
        } else if (key === "v") {
          e.preventDefault();
          ref.current.focusViewer();
        }
        return;
      }

      if (key === "k") {
        e.preventDefault();
        ref.current.openPalette();
        return;
      }
      if (key === "p") {
        e.preventDefault();
        ref.current.openSubjectSwitcher();
        return;
      }
      if (key === "j") {
        e.preventDefault();
        ref.current.toggleJobs();
        return;
      }

      // ⌘1..⌘N are the rail in order, the next free digit is Settings (⌘0 now that the rail is
      // nine rows deep), and ⌘, is Settings' alias (DESIGN.md §9).
      // The number comes from `registry.ts`'s NAV_ORDER, so the rail, the palette and the `?`
      // sheet cannot disagree about which key goes where.
      if (/^[0-9,]$/.test(e.key)) {
        const aliasId = SHORTCUT_ALIASES[e.key];
        const page = aliasId
          ? enabledPages.find((p) => p.id === aliasId)
          : enabledPages.find((p) => p.shortcut === e.key);
        if (page) {
          e.preventDefault();
          navigate(`/${page.id}`);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);
}
