/**
 * Signature help: what the kernel knows about the call you are inside.
 *
 * Jupyter's ⇧⇥. The kernel answers `inspect_request` for the name before the
 * open paren, and the reply's `text/plain` is IPython's own `?` output — the
 * same text `get_path_manager?` prints in a terminal. That is a whole page;
 * a tooltip is one line and a sentence, so this file's job is to find the call,
 * take the two parts worth showing, and know when to stop showing them.
 *
 * The two hard parts are pure functions with their own tests, because both are
 * wrong in ways a screenshot would not reveal: `parseInspect` against IPython's
 * field format, and `callTargetAt` against nested calls, strings and commas.
 */
import { StateEffect, StateField, type EditorState, type Extension } from "@codemirror/state";
import { EditorView, showTooltip, type Tooltip } from "@codemirror/view";

/** The two parts of an inspect reply worth putting in a tooltip. */
export interface SignatureInfo {
  /** `get_path_manager(project_dir=None)` — one line, however long. */
  signature: string;
  /** The docstring's first paragraph. Empty when there is none. */
  summary: string;
}

/**
 * IPython labels its `?` output with these, ANSI-coloured, at the start of a
 * line. They are also the only reliable end of the field before them: a
 * signature can wrap across lines and a docstring certainly does, so "up to the
 * next label" is the boundary, not "up to the next newline".
 */
const FIELDS = [
  "Signature",
  "Init signature",
  "Call signature",
  "Docstring",
  "Init docstring",
  "Class docstring",
  "Call docstring",
  "Source",
  "File",
  "Type",
  "Subclasses",
  "String form",
  "Length",
];

const FIELD_LINE = new RegExp(`^(${FIELDS.join("|")}):[ \\t]?(.*)$`);

/**
 * The ESC-based SGR escapes IPython colours its labels with. Built rather than
 * written as a literal: a raw ESC byte is invisible in a diff.
 */
const SGR = new RegExp(String.fromCharCode(27) + "\\[[0-9;]*m", "g");

/**
 * An `inspect_reply`'s `text/plain` as a signature and a one-paragraph summary,
 * or null when it carries neither.
 */
export function parseInspect(text: string): SignatureInfo | null {
  const plain = text.replace(SGR, "");
  if (plain.trim() === "") return null;

  const sections = new Map<string, string[]>();
  let current: string | null = null;
  for (const line of plain.split("\n")) {
    const field = FIELD_LINE.exec(line);
    if (field) {
      current = field[1] as string;
      sections.set(current, [(field[2] as string).trim()].filter((part) => part !== ""));
      continue;
    }
    if (current !== null) (sections.get(current) as string[]).push(line);
  }

  // A class shows `Init signature`; a callable object shows `Call signature`.
  // Whichever is present is the one the author is typing arguments into.
  const signatureLines =
    sections.get("Signature") ?? sections.get("Init signature") ?? sections.get("Call signature");
  const docLines =
    sections.get("Docstring") ?? sections.get("Init docstring") ?? sections.get("Class docstring");

  const signature = (signatureLines ?? []).join(" ").replace(/\s+/g, " ").trim();
  const summary = firstParagraph((docLines ?? []).join("\n"));
  if (signature === "" && summary === "") return null;
  return { signature, summary };
}

/**
 * The first paragraph of a docstring.
 *
 * A summary line, not a document: numpydoc bodies here run to forty lines with
 * `Parameters` and `Returns` sections, and a tooltip that tall covers the code
 * it is meant to describe. Blank line ends it, and so does a numpydoc section
 * underline (`-----`), which otherwise drags a heading in with no body.
 */
export function firstParagraph(text: string, maxChars = 320): string {
  const lines = text.replace(/\r/g, "").split("\n");
  const kept: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = (lines[i] as string).trim();
    if (line === "") {
      if (kept.length > 0) break;
      continue;
    }
    if (/^[-=~]{3,}$/.test(line)) {
      // A section underline: the line above it was a heading, not prose.
      kept.pop();
      break;
    }
    kept.push(line);
  }
  const paragraph = kept.join(" ").replace(/\s+/g, " ").trim();
  return paragraph.length > maxChars ? `${paragraph.slice(0, maxChars - 1).trimEnd()}…` : paragraph;
}

/** The call the cursor sits inside: what to inspect, and where to anchor. */
export interface CallTarget {
  /** Start of the callee expression (`catalog.subject_ids`). */
  from: number;
  /** End of it, which is also the position to send as the inspect cursor. */
  to: number;
  /** The `(` this call opened at. The tooltip hangs off it. */
  open: number;
  /** The callee, for deciding whether the tooltip still describes this call. */
  name: string;
}

/** Plain identifier characters. Subscripts are handled separately below. */
const IDENTIFIER = /[A-Za-z0-9_.]/;

/**
 * How far back to look for an unclosed `(`.
 *
 * A cell is not a file, but it can still be hundreds of lines, and this runs on
 * a keystroke. Beyond this the answer is "no call", which is also what a human
 * reading the code would say.
 */
const SCAN_LIMIT = 2000;

/**
 * The innermost unclosed call around `pos`, or null.
 *
 * Scanning backwards, skipping over balanced pairs and over string literals,
 * finds the `(` that is still open — which is precisely "the call the author is
 * typing arguments into". Two behaviours fall out of that rather than needing
 * their own rules: a nested call `f(g(|))` reports `g`, and typing past the
 * closing `)` reports null, which is how the tooltip dismisses itself.
 */
export function callTargetAt(doc: string, pos: number): CallTarget | null {
  let depth = 0;
  const cursor = Math.min(pos, doc.length) - 1;
  const floor = Math.max(0, cursor - SCAN_LIMIT);
  let i = cursor;
  while (i >= floor) {
    const ch = doc[i] as string;
    if (ch === '"' || ch === "'") {
      // Skip the literal wholesale: a paren or quote inside it is text.
      const quote = ch;
      i -= 1;
      while (i >= 0 && doc[i] !== quote) i -= 1;
      i -= 1;
      continue;
    }
    if (ch === ")" || ch === "]" || ch === "}") {
      depth += 1;
    } else if (ch === "(") {
      if (depth === 0) break; // the call the cursor is inside
      depth -= 1;
    } else if (ch === "[" || ch === "{") {
      // An unclosed `[` or `{` means the cursor is in a subscript or a
      // literal, not in an argument list — `d[key(` is a call, `f(x)[` is not.
      if (depth === 0) return null;
      depth -= 1;
    }
    i -= 1;
  }
  // Ran off the start (or the limit) with no unclosed `(`: no call. A newline
  // is deliberately NOT a boundary — arguments routinely span lines, and
  // treating one as the end reported no call for every `run_simulation(\n
  // config,` in this project.
  if (i < floor) return null;

  const open = i;
  let end = open;
  while (end > 0 && /\s/.test(doc[end - 1] as string)) end -= 1;

  // Walk left over the callee expression. A `]` is stepped over to its matching
  // `[`, so `rows[0].keys(` reads as `rows[0].keys` — but an UNMATCHED `[` is
  // where the expression began, so `d[f(` reads as `f` and not as `d[f`.
  // Getting this wrong is not cosmetic: `name` is what decides whether a
  // tooltip still describes the call in front of the cursor.
  let start = end;
  while (start > 0) {
    const ch = doc[start - 1] as string;
    if (IDENTIFIER.test(ch)) {
      start -= 1;
      continue;
    }
    if (ch === "]") {
      let inner = 0;
      let j = start - 1;
      for (; j >= 0; j -= 1) {
        const bracket = doc[j] as string;
        if (bracket === "]") inner += 1;
        else if (bracket === "[") {
          inner -= 1;
          if (inner === 0) break;
        }
      }
      if (j < 0) break; // unbalanced: not part of the callee
      start = j;
      continue;
    }
    break;
  }
  const name = doc.slice(start, end);
  // `(` with nothing callable in front of it is a grouping paren or a tuple.
  if (name === "" || !/^[A-Za-z_]/.test(name)) return null;
  return { from: start, to: end, open, name };
}

// ---------------------------------------------------------------------------
// the CodeMirror extension
// ---------------------------------------------------------------------------

interface ShownSignature extends SignatureInfo {
  /** Where the call opened, so the tooltip stays put while arguments grow. */
  open: number;
  /** Which callee this describes; a different one is a different tooltip. */
  name: string;
}

export const setSignature = StateEffect.define<ShownSignature | null>();

function tooltipFor(shown: ShownSignature): Tooltip {
  return {
    pos: shown.open,
    above: true,
    // Not arrow-anchored: the tooltip is wide and the arrow lands under the
    // paren, which is rarely where the eye is.
    create: () => {
      const dom = document.createElement("div");
      dom.className = "nb-signature";
      dom.setAttribute("data-testid", "nb-signature");
      const signature = document.createElement("div");
      signature.className = "nb-signature__sig";
      signature.textContent = shown.signature;
      dom.appendChild(signature);
      if (shown.summary !== "") {
        const summary = document.createElement("div");
        summary.className = "nb-signature__doc";
        summary.textContent = shown.summary;
        dom.appendChild(summary);
      }
      return { dom };
    },
  };
}

/**
 * The tooltip's state.
 *
 * It is cleared by the field itself whenever the document or the selection
 * moves out of the call it describes, so nothing has to remember to dismiss it:
 * pressing `)` past the end, or moving to another line, drops it because
 * `callTargetAt` no longer reports the same call.
 */
const signatureField = StateField.define<ShownSignature | null>({
  create: () => null,
  update(value, transaction) {
    let next = value;
    for (const effect of transaction.effects) {
      if (effect.is(setSignature)) next = effect.value;
    }
    if (next === null) return null;
    if (!transaction.docChanged && !transaction.selection && next === value) return next;
    const state = transaction.state;
    const target = callTargetAt(state.doc.toString(), state.selection.main.head);
    if (target === null || target.name !== next.name) return null;
    return target.open === next.open ? next : { ...next, open: target.open };
  },
  provide: (field) => showTooltip.from(field, (value) => (value === null ? null : tooltipFor(value))),
});

function signatureShown(state: EditorState): boolean {
  return state.field(signatureField, false) != null;
}

/** What the extension needs to ask the kernel. */
export interface SignatureSource {
  connected: boolean;
  inspect: (code: string, cursorPos: number) => Promise<string | null>;
}

/**
 * Ask the kernel about the call around the cursor and show what it says.
 *
 * Returns false when there is nothing to ask about, so a keymap can fall
 * through to whatever ⇧⇥ would otherwise do.
 */
export function requestSignature(view: EditorView, source: () => SignatureSource): boolean {
  const api = source();
  // A key press must never start a kernel: several seconds and a container
  // resource, taken without asking, because someone typed a bracket.
  if (!api.connected) return false;
  const doc = view.state.doc.toString();
  const target = callTargetAt(doc, view.state.selection.main.head);
  if (target === null) return false;

  void api
    .inspect(doc, target.to)
    .then((text) => {
      if (text === null) return;
      const info = parseInspect(text);
      if (info === null) return;
      // Re-check on arrival: the author kept typing while the kernel answered,
      // and a tooltip for a call they have already left is worse than none.
      const now = callTargetAt(
        view.state.doc.toString(),
        view.state.selection.main.head,
      );
      if (now === null || now.name !== target.name) return;
      view.dispatch({ effects: setSignature.of({ ...info, open: now.open, name: now.name }) });
    })
    .catch(() => {
      // A kernel that will not answer is not an error to report: the author
      // asked for a hint, not for a round trip they have to acknowledge.
    });
  return true;
}

export function dismissSignature(view: EditorView): boolean {
  if (!signatureShown(view.state)) return false;
  view.dispatch({ effects: setSignature.of(null) });
  return true;
}

/**
 * Signature help, on or off, as one reconfigurable bundle.
 *
 * `(` opens it automatically and ⇧⇥ asks for it explicitly — Jupyter's two
 * gestures. Escape is bound at the highest precedence *by the caller*, because
 * the notebook's own Escape leaves edit mode and dismissing a tooltip must come
 * first; see `dismissSignature`.
 */
export function signatureExtensions(
  enabled: boolean,
  source: () => SignatureSource,
): Extension {
  if (!enabled) return [];
  return [
    signatureField,
    EditorView.updateListener.of((update) => {
      if (!update.docChanged) return;
      // Only on the character that opens a call. Asking on every keystroke
      // would be a kernel round trip per key, and the field above already
      // keeps the tooltip alive while the arguments are typed.
      // `includes`, not `endsWith`: auto-close brackets is on by default, so
      // typing `(` inserts `()` in one change and the cursor lands between
      // them. Testing the last character of the insertion saw `)` and never
      // fired, which made signature help look like it did nothing at all for
      // anyone using the default settings.
      let opened = false;
      update.changes.iterChanges((_fa, _ta, _fb, _tb, inserted) => {
        if (inserted.toString().includes("(")) opened = true;
      });
      if (opened) requestSignature(update.view, source);
    }),
  ];
}
