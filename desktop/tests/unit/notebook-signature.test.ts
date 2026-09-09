import { describe, expect, it } from "vitest";
import {
  callTargetAt,
  firstParagraph,
  parseInspect,
} from "../../src/renderer/pages/notebooks/signature";

const ESC = String.fromCharCode(27);
/** IPython colours its field labels; every fixture here does too. */
const label = (name: string) => `${ESC}[31m${name}:${ESC}[39m`;

/**
 * Signature help.
 *
 * The fixtures are real: they were captured from the container's own kernel
 * (`sh.object_inspect_text(...)` under SimNIBS Python) rather than written from
 * memory of what IPython emits, because the field format — ANSI labels, wrapped
 * signatures, numpydoc bodies — is exactly what a hand-written fixture gets
 * subtly wrong.
 */

describe("parseInspect", () => {
  it("reads a signature and the docstring's first paragraph", () => {
    const reply = [
      `${label("Signature")} catalog.subject_ids(pm: 'PathManager') -> 'list[str]'`,
      `${label("Docstring")}`,
      "Union of raw-BIDS, FastSurfer, legacy-FreeSurfer and m2m subjects.",
      "",
      "Naturally sorted. ``derivatives/freesurfer`` is still unioned in.",
      `${label("File")}      /ti-toolbox/tit/catalog.py`,
      `${label("Type")}      function`,
    ].join("\n");
    expect(parseInspect(reply)).toEqual({
      signature: "catalog.subject_ids(pm: 'PathManager') -> 'list[str]'",
      summary: "Union of raw-BIDS, FastSurfer, legacy-FreeSurfer and m2m subjects.",
    });
  });

  it("stops the docstring at the next field, not at the next newline", () => {
    // The bug this guards: taking one line gives a summary that ends
    // mid-sentence; taking everything to the end drags `File:` and `Type:`
    // into the tooltip.
    const reply = [
      `${label("Signature")} f(x)`,
      `${label("Docstring")}`,
      "A summary that runs",
      "across two lines.",
      `${label("Type")}      function`,
    ].join("\n");
    const info = parseInspect(reply)!;
    expect(info.summary).toBe("A summary that runs across two lines.");
    expect(info.summary).not.toContain("function");
  });

  it("joins a signature that wrapped across lines", () => {
    const reply = [
      `${label("Signature")} run_simulation(`,
      "    config: SimulationConfig,",
      ") -> None",
      `${label("Type")}      function`,
    ].join("\n");
    expect(parseInspect(reply)!.signature).toBe(
      "run_simulation( config: SimulationConfig, ) -> None",
    );
  });

  it("takes a class's init signature and init docstring", () => {
    const reply = [
      `${label("Init signature")} Analyzer(config: AnalyzerConfig)`,
      `${label("Docstring")}`,
      "Field analysis over a simulation.",
      `${label("Init docstring")}`,
      "Build one from a config.",
    ].join("\n");
    expect(parseInspect(reply)).toEqual({
      signature: "Analyzer(config: AnalyzerConfig)",
      // `Docstring` wins where both exist: the class is what the author named.
      summary: "Field analysis over a simulation.",
    });
  });

  it("keeps a signature with no docstring, and a docstring with no signature", () => {
    expect(parseInspect(`${label("Signature")} f(x)`)).toEqual({ signature: "f(x)", summary: "" });
    expect(parseInspect(`${label("Docstring")}\nJust prose.`)).toEqual({
      signature: "",
      summary: "Just prose.",
    });
  });

  it("reports nothing rather than an empty tooltip", () => {
    expect(parseInspect("")).toBeNull();
    expect(parseInspect("   \n  ")).toBeNull();
    expect(parseInspect(`${label("Type")}      module`)).toBeNull();
  });
});

describe("firstParagraph", () => {
  it("drops a numpydoc section heading rather than showing it headless", () => {
    // Without this the tooltip reads "…the shared singleton instance. Parameters"
    // — a heading whose body was cut off by the paragraph rule.
    const doc = ["Return the singleton PathManager.", "Parameters", "----------", "x : int"].join(
      "\n",
    );
    expect(firstParagraph(doc)).toBe("Return the singleton PathManager.");
  });

  it("skips leading blank lines but stops at the first internal one", () => {
    expect(firstParagraph("\n\nOne line.\n\nSecond paragraph.")).toBe("One line.");
  });

  it("truncates a paragraph that would fill the screen", () => {
    const long = `${"word ".repeat(200)}end`;
    const text = firstParagraph(long, 40);
    expect(text.length).toBeLessThanOrEqual(40);
    expect(text.endsWith("…")).toBe(true);
  });
});

describe("callTargetAt", () => {
  const at = (doc: string) => {
    const cursor = doc.indexOf("|");
    expect(cursor).toBeGreaterThanOrEqual(0);
    expect(doc.indexOf("|", cursor + 1)).toBe(-1);
    return callTargetAt(doc.slice(0, cursor) + doc.slice(cursor + 1), cursor);
  };

  it("finds the callee of the call the cursor is inside", () => {
    const target = at("get_path_manager(|)")!;
    expect(target.name).toBe("get_path_manager");
    expect(target.open).toBe(16);
    expect(target.to).toBe(16);
  });

  it("keeps reporting the call while arguments are typed", () => {
    expect(at("f(1, 2, |")!.name).toBe("f");
    expect(at("catalog.subject_ids(pm, |)")!.name).toBe("catalog.subject_ids");
  });

  it("reports the INNER call when calls are nested", () => {
    // `print(len(|))` is `len`'s argument list, not `print`'s.
    expect(at("print(len(|))")!.name).toBe("len");
    expect(at("print(len(x), |)")!.name).toBe("print");
  });

  it("reports nothing once the cursor is past the closing paren", () => {
    // This IS the dismissal rule — no separate "hide on )" branch exists.
    expect(at("f(1)|")).toBeNull();
    expect(at("f(1)  |")).toBeNull();
  });

  it("does not read a paren inside a string as a call", () => {
    expect(at("print('a (b', |)")!.name).toBe("print");
    expect(at('f("(", |)')!.name).toBe("f");
    expect(at("x = '(|'")).toBeNull();
  });

  it("is not fooled by a subscript or a literal", () => {
    expect(at("d[|]")).toBeNull();
    expect(at("{'a': |}")).toBeNull();
    // …but a call inside a subscript is still a call.
    expect(at("d[f(|)]")!.name).toBe("f");
  });

  it("reports nothing for a grouping paren or a tuple", () => {
    expect(at("(1 + |")).toBeNull();
    expect(at("x = (|)")).toBeNull();
  });

  it("does not cross a line that opened nothing", () => {
    expect(at("f(1)\n|")).toBeNull();
    // …but a call left open at the end of a line still counts.
    expect(at("f(\n    |")!.name).toBe("f");
  });

  it("handles whitespace between the callee and its paren", () => {
    expect(at("f  (|")!.name).toBe("f");
  });

  it("reads a call on a chained expression", () => {
    expect(at("pm.list_simulations(|")!.name).toBe("pm.list_simulations");
    expect(at("rows[0].keys(|")!.name).toBe("rows[0].keys");
  });
});
