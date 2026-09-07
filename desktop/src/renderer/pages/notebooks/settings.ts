/**
 * Notebook editor preferences, per machine.
 *
 * Same shape and same storage as `app/executionPrefs.ts`: a small typed record
 * in `localStorage`, read through a `zustand` store so a change reaches every
 * open cell without a prop drilled through the page. These are *preferences*,
 * not project state — they follow the person, not the notebook — which is why
 * they are not in the `.ipynb` and not on the server.
 */
import { create } from "zustand";

export interface NotebookPrefs {
  /** Kernel-backed completion on Tab / ⌃Space. */
  autocomplete: boolean;
  /** Type `(`, get `()`, with the same for quotes and brackets. */
  closeBrackets: boolean;
  lineNumbers: boolean;
  /** Spaces per indent level. Python's own answer is 4. */
  indentSize: number;
  /** Editor and output font size in px. */
  fontSize: number;
  /** Wrap long lines instead of scrolling the cell sideways. */
  wordWrap: boolean;
  /** Show a signature/docstring tooltip while typing arguments. */
  signatureHelp: boolean;
}

export const DEFAULT_PREFS: NotebookPrefs = {
  autocomplete: true,
  closeBrackets: true,
  lineNumbers: false,
  indentSize: 4,
  fontSize: 12,
  wordWrap: true,
  signatureHelp: true,
};

const STORAGE_KEY = "tit.notebooks.prefs";

/** Indent sizes and font sizes offered; anything else is refused, not clamped. */
export const INDENT_SIZES = [2, 4, 8] as const;
export const FONT_SIZES = [11, 12, 13, 14, 16] as const;

/**
 * Stored JSON as prefs. Unknown keys are dropped and a bad value falls back to
 * its default one field at a time, so a half-corrupt record still yields a
 * usable editor rather than a blank one.
 */
export function parsePrefs(raw: unknown): NotebookPrefs {
  if (typeof raw !== "object" || raw === null) return { ...DEFAULT_PREFS };
  const stored = raw as Record<string, unknown>;
  const boolean = (key: keyof NotebookPrefs): boolean =>
    typeof stored[key] === "boolean" ? (stored[key] as boolean) : (DEFAULT_PREFS[key] as boolean);
  const oneOf = (key: keyof NotebookPrefs, allowed: readonly number[]): number =>
    allowed.includes(stored[key] as number) ? (stored[key] as number) : (DEFAULT_PREFS[key] as number);
  return {
    autocomplete: boolean("autocomplete"),
    closeBrackets: boolean("closeBrackets"),
    lineNumbers: boolean("lineNumbers"),
    indentSize: oneOf("indentSize", INDENT_SIZES),
    fontSize: oneOf("fontSize", FONT_SIZES),
    wordWrap: boolean("wordWrap"),
    signatureHelp: boolean("signatureHelp"),
  };
}

function load(): NotebookPrefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === null ? { ...DEFAULT_PREFS } : parsePrefs(JSON.parse(raw));
  } catch {
    // A private window, cleared site data, or storage the browser refuses.
    return { ...DEFAULT_PREFS };
  }
}

interface PrefsState {
  prefs: NotebookPrefs;
  set: <K extends keyof NotebookPrefs>(key: K, value: NotebookPrefs[K]) => void;
  reset: () => void;
}

export const useNotebookPrefs = create<PrefsState>((setState, getState) => ({
  prefs: typeof window === "undefined" ? { ...DEFAULT_PREFS } : load(),
  set: (key, value) => {
    const prefs = { ...getState().prefs, [key]: value };
    setState({ prefs });
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Preferences are a convenience; failing to persist one is not an error
      // worth interrupting the author for.
    }
  },
  reset: () => {
    setState({ prefs: { ...DEFAULT_PREFS } });
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* see above */
    }
  },
}));
