import { describe, expect, it } from "vitest";
import {
  inspectTooltipText,
  labelFor,
  sharedPrefix,
  toCompletionResult,
} from "../../src/renderer/pages/notebooks/completion";
import {
  DEFAULT_PREFS,
  parsePrefs,
  FONT_SIZES,
  INDENT_SIZES,
} from "../../src/renderer/pages/notebooks/settings";

/**
 * The Jupyter `complete_reply` → CodeMirror mapping.
 *
 * These are the protocol's awkward parts, testable without a kernel: the
 * replacement range belongs to the kernel and often covers a whole dotted
 * expression, matches come back fully qualified, and IPython's type metadata
 * is an optional experimental key.
 */

describe("toCompletionResult", () => {
  it("uses the KERNEL's replacement range, not a guess from the text", () => {
    // The range is why this is a round trip at all: only the kernel knows
    // where the token it completed began.
    const doc = "from tit import get_p";
    const result = toCompletionResult(
      { matches: ["get_path_manager"], cursorStart: 16, cursorEnd: 21 },
      doc,
    )!;
    expect(doc.slice(result.from, result.to)).toBe("get_p");
    expect(result.options[0]).toMatchObject({ label: "get_path_manager", apply: "get_path_manager" });
  });

  it("moves the range past a shared dotted prefix instead of relabelling", () => {
    // THE defect this exists for. CodeMirror filters options by matching the
    // label against the text in the replaced range. A label of `subject_ids`
    // against a range covering `catalog.subj` matches nothing, so the popup
    // never appeared. Narrowing the RANGE keeps both halves right: the option
    // reads as the member, and the filter compares like with like.
    const doc = "catalog.subj";
    const result = toCompletionResult(
      { matches: ["catalog.subject_ids", "catalog.subject_detail"], cursorStart: 0, cursorEnd: 12 },
      doc,
    )!;
    expect(doc.slice(result.from, result.to)).toBe("subj");
    expect(result.options.map((o) => o.label)).toEqual(["subject_ids", "subject_detail"]);
    expect(result.options.map((o) => o.apply)).toEqual(["subject_ids", "subject_detail"]);
  });

  it("keeps the whole range when the matches do not share a prefix", () => {
    // A mixed answer (`catalog.x` and `other.y`) has no prefix to drop, and
    // dropping one match's would insert the wrong text for the other.
    const doc = "catalog.subj";
    const result = toCompletionResult(
      { matches: ["catalog.subject_ids", "other.thing"], cursorStart: 0, cursorEnd: 12 },
      doc,
    )!;
    expect(result.from).toBe(0);
    expect(result.options.map((o) => o.apply)).toEqual(["catalog.subject_ids", "other.thing"]);
  });

  it("maps IPython's experimental types onto CodeMirror's icons, and skips what it does not name", () => {
    const result = toCompletionResult(
      {
        matches: ["run_simulation", "SimulationConfig", "mystery"],
        cursorStart: 0,
        cursorEnd: 3,
        metadata: {
          _jupyter_types_experimental: [
            { text: "run_simulation", type: "function", signature: "(config)" },
            { text: "SimulationConfig", type: "class" },
            { text: "mystery", type: "something-new" },
          ],
        },
      },
      "run",
    )!;
    expect(result.options[0]).toMatchObject({ type: "function", detail: "(config)" });
    expect(result.options[1]).toMatchObject({ type: "class" });
    // An unknown kind gets no icon rather than a guessed one.
    expect(result.options[2]!.type).toBeUndefined();
  });

  it("sorts private names last without hiding them", () => {
    const result = toCompletionResult(
      { matches: ["__init__", "_private", "public"], cursorStart: 0, cursorEnd: 0 },
      "",
    )!;
    expect(result.options.map((o) => o.label)).toHaveLength(3);
    const boosts = Object.fromEntries(result.options.map((o) => [o.label, o.boost]));
    expect(boosts["public"]).toBeGreaterThan(boosts["_private"] as number);
    expect(boosts["_private"]).toBeGreaterThan(boosts["__init__"] as number);
  });

  it("drops duplicate matches", () => {
    const result = toCompletionResult(
      { matches: ["x", "x", "y"], cursorStart: 0, cursorEnd: 0 },
      "",
    )!;
    expect(result.options.map((o) => o.label)).toEqual(["x", "y"]);
  });

  it("reports nothing rather than an empty popup", () => {
    expect(toCompletionResult({ matches: [], cursorStart: 0, cursorEnd: 0 }, "")).toBeNull();
  });

  it("clamps a range the document cannot hold", () => {
    // A reply that raced an edit must not throw or produce a negative range.
    const result = toCompletionResult({ matches: ["x"], cursorStart: 50, cursorEnd: 99 }, "short")!;
    expect(result.from).toBe(5);
    expect(result.to).toBe(5);
  });

  it("re-queries on a dot instead of filtering the last answer", () => {
    const result = toCompletionResult({ matches: ["x"], cursorStart: 0, cursorEnd: 0 }, "")!;
    expect(result.validFor!.test("subj")).toBe(true);
    // `catalog.` is a NEW expression; reusing the old list would offer the
    // wrong object's members.
    expect(result.validFor!.test("subj.")).toBe(false);
  });
});

describe("labelFor and sharedPrefix", () => {
  it("finds the prefix only when every match has it", () => {
    expect(sharedPrefix(["catalog.a", "catalog.b"], "catalog.x")).toBe("catalog.");
    expect(sharedPrefix(["catalog.a", "other.b"], "catalog.x")).toBe("");
    expect(sharedPrefix(["get_path_manager"], "get_p")).toBe("");
  });

  it("keeps a match whole when there is no prefix to drop", () => {
    expect(labelFor("get_path_manager", "")).toBe("get_path_manager");
    expect(labelFor("other.thing", "catalog.")).toBe("other.thing");
    expect(labelFor("catalog.subject_ids", "catalog.")).toBe("subject_ids");
  });
});

describe("inspectTooltipText", () => {
  it("strips the kernel's ANSI colouring", () => {
    const coloured = `${String.fromCharCode(27)}[0;31mSignature:${String.fromCharCode(27)}[0m f(x)`;
    expect(inspectTooltipText(coloured)).toBe("Signature: f(x)");
  });

  it("truncates a long docstring rather than filling the screen with it", () => {
    const long = Array.from({ length: 60 }, (_, i) => `line ${i}`).join("\n");
    const text = inspectTooltipText(long, 5);
    expect(text.split("\n")).toHaveLength(6);
    expect(text.endsWith("…")).toBe(true);
  });
});

describe("editor preferences", () => {
  it("defaults to completion on, four-space indent, no line numbers", () => {
    expect(DEFAULT_PREFS.autocomplete).toBe(true);
    expect(DEFAULT_PREFS.indentSize).toBe(4);
    expect(DEFAULT_PREFS.lineNumbers).toBe(false);
  });

  it("falls back field by field, so a half-corrupt record still opens an editor", () => {
    expect(parsePrefs({ autocomplete: false, indentSize: 999, fontSize: "big" })).toEqual({
      ...DEFAULT_PREFS,
      autocomplete: false,
    });
    expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("nonsense")).toEqual(DEFAULT_PREFS);
  });

  it("accepts only the sizes the control offers", () => {
    for (const size of INDENT_SIZES) expect(parsePrefs({ indentSize: size }).indentSize).toBe(size);
    for (const size of FONT_SIZES) expect(parsePrefs({ fontSize: size }).fontSize).toBe(size);
    expect(parsePrefs({ indentSize: 3 }).indentSize).toBe(DEFAULT_PREFS.indentSize);
  });

  it("drops keys it does not know", () => {
    expect(parsePrefs({ ...DEFAULT_PREFS, injected: "x" })).toEqual(DEFAULT_PREFS);
  });
});
