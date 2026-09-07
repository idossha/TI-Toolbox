/**
 * Turning Jupyter's `complete_reply` into CodeMirror's completion result.
 *
 * There is no language server here and there deliberately is not one. The
 * kernel that would have to be kept in sync with an LSP is the same process
 * that *holds the objects*: after a notebook has run `from tit import catalog`,
 * only that interpreter knows what `catalog.` contains, because it is the
 * thing containing it. IPython answers `complete_request` from that live
 * namespace using `jedi`, which ships inside `ipykernel` — so completion here
 * costs one round trip and nothing to install.
 *
 * This module is the mapping and nothing else: it is pure, so the protocol's
 * awkward parts — a kernel-owned replacement range, dotted matches, `__dunder`
 * ordering — are unit-testable without a kernel or an editor.
 */

/** The parts of a `complete_reply` this mapping uses. */
export interface CompleteReply {
  matches: string[];
  cursorStart: number;
  cursorEnd: number;
  metadata?: Record<string, unknown>;
}

/** One CodeMirror completion option. */
export interface CompletionOption {
  label: string;
  /** What actually gets inserted; differs from the label for a dotted match. */
  apply: string;
  type?: string;
  boost?: number;
  detail?: string;
}

/** A CodeMirror `CompletionResult`, in the shape this app builds it. */
export interface CompletionResult {
  from: number;
  to: number;
  options: CompletionOption[];
  /** Re-query the kernel rather than filtering the last answer client-side. */
  validFor?: RegExp;
}

/**
 * IPython's `metadata._jupyter_types_experimental` names each match's kind.
 * These are its spellings mapped onto CodeMirror's icon set; anything it does
 * not name gets no icon rather than a guessed one.
 */
const TYPE_MAP: Record<string, string> = {
  function: "function",
  method: "method",
  class: "class",
  module: "namespace",
  instance: "variable",
  statement: "variable",
  keyword: "keyword",
  param: "variable",
  path: "text",
  magic: "keyword",
};

interface ExperimentalType {
  text?: unknown;
  type?: unknown;
  signature?: unknown;
}

function typesFromMetadata(metadata: Record<string, unknown> | undefined): Map<string, ExperimentalType> {
  const raw = metadata?.["_jupyter_types_experimental"];
  const out = new Map<string, ExperimentalType>();
  if (!Array.isArray(raw)) return out;
  for (const entry of raw as ExperimentalType[]) {
    if (entry && typeof entry.text === "string") out.set(entry.text, entry);
  }
  return out;
}

/**
 * The common `a.b.` prefix of the replaced range, when every match shares it.
 *
 * The kernel replaces `[cursorStart, cursorEnd)`, and for a dotted expression
 * that range covers the WHOLE expression — so completing `catalog.subj` comes
 * back as `catalog.subject_ids` replacing all sixteen characters.
 *
 * That cannot be handed to CodeMirror as-is. It filters options by matching the
 * label against the text in the replaced range, so a label of `subject_ids`
 * against a range of `catalog.subject_` matches nothing and the popup never
 * appears — which is exactly what it did. Keeping the label as the full dotted
 * path fixes the filter and breaks the reading: every option then reads
 * `catalog.…` and they are indistinguishable at a glance.
 *
 * So the RANGE moves instead. When the replaced text has a dot and every match
 * begins with the same `a.b.` prefix, the range starts after that prefix and
 * both label and insertion are the tail. The filter then compares
 * `subject_ids` against `subject_`, which is what the author is typing.
 */
export function sharedPrefix(matches: string[], replaced: string): string {
  const dot = replaced.lastIndexOf(".");
  if (dot === -1) return "";
  const prefix = replaced.slice(0, dot + 1);
  return matches.every((match) => match.startsWith(prefix)) ? prefix : "";
}

/**
 * A match as it is shown, given the prefix the range no longer covers.
 *
 * Exported for its own test: this and `sharedPrefix` are the two halves of the
 * dotted-completion rule, and each is wrong in a different way.
 */
export function labelFor(match: string, prefix: string): string {
  return prefix !== "" && match.startsWith(prefix) ? match.slice(prefix.length) : match;
}

/**
 * Private names sort last. Python's `_x` and `__x__` are answers to a question
 * nobody asked at the top of a list; they are still offered, just not first.
 */
function boostOf(label: string): number {
  if (label.startsWith("__")) return -99;
  if (label.startsWith("_")) return -50;
  return 0;
}

/**
 * A `complete_reply` and the document it answers, as a CodeMirror result.
 *
 * `doc` is the cell's whole source; the reply's offsets index into it.
 */
export function toCompletionResult(reply: CompleteReply, doc: string): CompletionResult | null {
  if (reply.matches.length === 0) return null;
  const start = Math.max(0, Math.min(reply.cursorStart, doc.length));
  const to = Math.max(start, Math.min(reply.cursorEnd, doc.length));
  const replaced = doc.slice(start, to);
  const prefix = sharedPrefix(reply.matches, replaced);
  const from = start + prefix.length;
  const types = typesFromMetadata(reply.metadata);

  const seen = new Set<string>();
  const options: CompletionOption[] = [];
  for (const match of reply.matches) {
    if (seen.has(match)) continue;
    seen.add(match);
    const label = labelFor(match, prefix);
    const info = types.get(match);
    const kind = typeof info?.type === "string" ? TYPE_MAP[info.type] : undefined;
    // `apply` equals the label now that the range starts after the prefix —
    // it is kept explicit because the two were different before this rule and
    // a reader should not have to re-derive that they no longer are.
    const option: CompletionOption = { label, apply: label, boost: boostOf(label) };
    if (kind !== undefined) option.type = kind;
    if (typeof info?.signature === "string" && info.signature !== "") option.detail = info.signature;
    options.push(option);
  }

  return {
    from,
    to,
    options,
    // The kernel's answer is only valid while the token grows by word
    // characters. A dot means a new expression and a new round trip — filtering
    // the old list would offer `catalog.`'s members after the user typed `.`
    // on something else entirely.
    validFor: /^[\w]*$/,
  };
}

/**
 * IPython colours an inspect reply and a tooltip is plain text, so the SGR
 * escapes are stripped here rather than parsed. The pattern is BUILT rather
 * than written as a literal: a raw ESC byte is invisible in a diff and trivial
 * to delete by accident -- which is how this first shipped matching a bare
 * `[0m` and leaving every real escape in place.
 */
const SGR = new RegExp(String.fromCharCode(27) + "\\[[0-9;]*m", "g");

/** The `text/plain` of an `inspect_reply`, trimmed for a tooltip. */
export function inspectTooltipText(text: string, maxLines = 24): string {
  const lines = text.replace(SGR, "").split("\n");
  const kept = lines.slice(0, maxLines);
  if (lines.length > maxLines) kept.push("\u2026");
  return kept.join("\n").trimEnd();
}
