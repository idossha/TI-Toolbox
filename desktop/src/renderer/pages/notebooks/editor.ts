/**
 * The cell editor: CodeMirror 6, Python, and completion from the live kernel.
 *
 * SUNA puts a CodeMirror in every cell for the same reason Jupyter does — a
 * `<textarea>` cannot colour Python, cannot indent a block, and cannot show a
 * completion popup. The first version of this page shipped a textarea to avoid
 * a dependency; the maintainer's answer was that the cost was worth paying, so
 * this is the editor that replaces it.
 *
 * Two things here are not the default CodeMirror recipe:
 *
 * 1. **The theme is built from the app's CSS variables, not from a colour
 *    list.** `EditorView.theme` cannot read a variable that changes later, so
 *    every rule below resolves to `var(--…)`: the editor then follows the
 *    light/dark switch with the rest of the app, with no second palette to keep
 *    in sync and no re-created editor on a theme change.
 * 2. **Completion is a kernel round trip, not a static analysis.** See
 *    `completion.ts` — the interpreter holding the objects is a better
 *    completer than any parser, and it is already running.
 */
import { acceptCompletion, autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap, completionStatus, startCompletion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, placeholder } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { toCompletionResult } from "./completion";
import type { NotebookPrefs } from "./settings";

/**
 * Python's syntax, in the app's semantic tokens.
 *
 * Deliberately few colours. A notebook cell is read next to prose and output,
 * and a nine-colour theme in that context is noise — keyword, string, number,
 * comment, definition and builtin are the distinctions that carry meaning when
 * scanning a cell, and each maps to a token that already exists (DESIGN §3)
 * rather than to a hex value this file would then own.
 */
export const pythonHighlighting = HighlightStyle.define([
  { tag: [tags.keyword, tags.modifier, tags.controlKeyword], color: "var(--lost)", fontWeight: "600" },
  { tag: [tags.definitionKeyword, tags.moduleKeyword], color: "var(--lost)", fontWeight: "600" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--success)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--field)" },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: "var(--ink-3)", fontStyle: "italic" },
  { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: "var(--accent)" },
  { tag: [tags.definition(tags.variableName), tags.definition(tags.propertyName)], color: "var(--ink)", fontWeight: "600" },
  { tag: [tags.className, tags.typeName], color: "var(--warning)", fontWeight: "600" },
  { tag: [tags.operator, tags.punctuation, tags.bracket], color: "var(--ink-2)" },
  { tag: [tags.propertyName, tags.attributeName], color: "var(--ink)" },
  { tag: tags.self, color: "var(--lost)", fontStyle: "italic" },
  { tag: tags.invalid, color: "var(--danger)" },
]);

/** Chrome and layout. Colours are variables so the theme switch is free. */
export const editorTheme = EditorView.theme({
  "&": {
    color: "var(--ink)",
    backgroundColor: "var(--surface)",
    border: "1px solid var(--line)",
    borderRadius: "var(--radius-control)",
  },
  "&.cm-focused": {
    outline: "2px solid var(--focus)",
    outlineOffset: "-1px",
    borderColor: "transparent",
  },
  ".cm-content": {
    fontFamily: "var(--font-mono)",
    padding: "var(--space-1) 0",
    caretColor: "var(--ink)",
  },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.5" },
  ".cm-gutters": {
    backgroundColor: "var(--surface-2)",
    color: "var(--ink-3)",
    border: "none",
    borderRight: "1px solid var(--line)",
  },
  ".cm-activeLine": { backgroundColor: "transparent" },
  ".cm-activeLineGutter": { backgroundColor: "transparent" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection": {
    backgroundColor: "var(--accent-soft)",
  },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--ink)" },
  ".cm-tooltip": {
    backgroundColor: "var(--surface)",
    border: "1px solid var(--line-strong)",
    borderRadius: "var(--radius-control)",
    boxShadow: "var(--shadow-2)",
    color: "var(--ink)",
    fontFamily: "var(--font-mono)",
    fontSize: "11px",
  },
  ".cm-tooltip.cm-tooltip-autocomplete > ul": { fontFamily: "var(--font-mono)", maxHeight: "16em" },
  ".cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "var(--accent-soft)",
    color: "var(--ink)",
  },
  ".cm-completionIcon": { color: "var(--ink-3)" },
  ".cm-completionDetail": { color: "var(--ink-3)", fontStyle: "normal" },
  ".cm-tooltip.cm-tooltip-signature": { padding: "var(--space-1) var(--space-2)", whiteSpace: "pre-wrap", maxWidth: "42em" },
});

/** What the editor needs from the notebook to answer a completion. */
export interface CompletionSource {
  /** Is a kernel up? A key press must not start one. */
  connected: boolean;
  complete: (code: string, cursorPos: number) => Promise<{
    matches: string[];
    cursorStart: number;
    cursorEnd: number;
    metadata?: Record<string, unknown>;
  } | null>;
  inspect: (code: string, cursorPos: number) => Promise<string | null>;
}

/**
 * The completion source CodeMirror calls.
 *
 * `explicit` matters: on ⌃Space or ⇥ the author asked, so the kernel is asked
 * whatever the cursor sits on. Otherwise a query only goes out after a word
 * character or a dot, so typing prose in a comment does not produce a round
 * trip per keystroke.
 */
export function kernelCompletions(source: () => CompletionSource) {
  return async (context: CompletionContext): Promise<CompletionResult | null> => {
    const api = source();
    if (!api.connected) return null;
    const before = context.matchBefore(/[\w.]+$/);
    if (!context.explicit && before === null) return null;
    // A bare dot is a real completion request (`catalog.` → its members) even
    // though `matchBefore` above already covers it; what is refused is an
    // implicit query with nothing at all before the cursor.
    const code = context.state.doc.toString();
    const reply = await api.complete(code, context.pos);
    if (reply === null || context.aborted) return null;
    return toCompletionResult(reply, code) as CompletionResult | null;
  };
}

/** The extensions that depend on a preference, as one reconfigurable bundle. */
export function prefExtensions(prefs: NotebookPrefs): Extension {
  const extensions: Extension[] = [
    indentUnit.of(" ".repeat(prefs.indentSize)),
    EditorState.tabSize.of(prefs.indentSize),
    EditorView.theme({
      ".cm-content, .cm-scroller, .cm-gutters": { fontSize: `${prefs.fontSize}px` },
    }),
  ];
  if (prefs.lineNumbers) extensions.push(lineNumbers());
  if (prefs.wordWrap) extensions.push(EditorView.lineWrapping);
  if (prefs.closeBrackets) extensions.push(closeBrackets(), keymap.of(closeBracketsKeymap));
  return extensions;
}

/** Autocompletion, on or off, as one reconfigurable bundle. */
export function completionExtensions(
  enabled: boolean,
  source: () => CompletionSource,
): Extension {
  if (!enabled) return [];
  return [
    autocompletion({
      override: [kernelCompletions(source)],
      // The kernel decides what matches; filtering its answer again
      // client-side would hide `_private` names it deliberately offered.
      filterStrict: false,
      activateOnTyping: true,
      icons: true,
      defaultKeymap: false,
    }),
    keymap.of(completionKeymap),
    keymap.of([
      // Tab, in the order Jupyter resolves it — and the order matters.
      //
      // Typing already opens the popup (`activateOnTyping`), so by the time
      // Tab arrives there is usually one on screen. The first version only
      // called `startCompletion`, which returns false when a completion is
      // already open; Tab then fell through to `indentWithTab`, which inserted
      // an indent AND closed the popup. Pressing Tab to complete made the
      // completion disappear, which is exactly the opposite of the gesture.
      {
        key: "Tab",
        run: (view) => {
          // 1. A visible popup: take the selected option.
          if (acceptCompletion(view)) return true;
          // 2. An answer still in flight: swallow the key rather than indent
          //    into the middle of the word the kernel is completing.
          if (completionStatus(view.state) === "pending") return true;
          // 3. A token under the cursor: ask.
          const before = view.state.sliceDoc(
            Math.max(0, view.state.selection.main.head - 1),
            view.state.selection.main.head,
          );
          if (/[\w.]/.test(before)) return startCompletion(view);
          // 4. Otherwise Tab is indentation, which `indentWithTab` handles.
          return false;
        },
      },
      { key: "Ctrl-Space", run: startCompletion },
      { key: "Mod-i", run: startCompletion },
    ]),
  ];
}

/** The extensions every cell editor has, whatever the preferences say. */
export function baseExtensions(): Extension {
  return [
    python(),
    syntaxHighlighting(pythonHighlighting),
    editorTheme,
    history(),
    keymap.of(historyKeymap),
    // `defaultKeymap` last: the notebook's own keys are installed ahead of it
    // by the component, so ⇧↵ runs the cell rather than inserting a newline.
    keymap.of(defaultKeymap.filter((binding) => binding.key !== "Mod-Enter")),
    keymap.of([indentWithTab]),
    placeholder(""),
    EditorView.contentAttributes.of({ "data-testid": "nb-editor" }),
  ];
}

export { EditorState, EditorView, keymap, Compartment };
