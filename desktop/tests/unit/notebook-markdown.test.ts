import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../../src/renderer/pages/notebooks/markdown";

/**
 * The renderer for notebook prose cells.
 *
 * The maintainer's report was that a markdown cell "shows as a flat paragraph",
 * so every feature named in that report has an assertion here — headings,
 * lists, bold/italic, links, code blocks in the mono face, tables and maths —
 * plus the escaping rules the whole file rests on.
 */

describe("blocks", () => {
  it("renders headings at their level rather than as paragraph text", () => {
    expect(renderMarkdown("# One")).toBe("<h1>One</h1>");
    expect(renderMarkdown("### Three")).toBe("<h3>Three</h3>");
    expect(renderMarkdown("####### seven hashes is not a heading")).toContain("<p>");
  });

  it("renders both kinds of list, and closes one before starting the other", () => {
    expect(renderMarkdown("- a\n- b")).toBe("<ul>\n<li>a</li>\n<li>b</li>\n</ul>");
    expect(renderMarkdown("1. a\n2. b")).toBe("<ol>\n<li>a</li>\n<li>b</li>\n</ol>");
    const mixed = renderMarkdown("- a\n\n1. b");
    expect(mixed).toContain("</ul>");
    expect(mixed).toContain("<ol>");
  });

  it("renders a fenced block in the mono class, keeping its language", () => {
    const html = renderMarkdown("```python\nx = 1\nprint(x)\n```");
    expect(html).toContain('<pre class="nb-code">');
    expect(html).toContain('<code class="language-python">');
    expect(html).toContain("x = 1\nprint(x)");
    // A fence is a block: it must not end up inside a paragraph.
    expect(html).not.toMatch(/<p>[^<]*<pre/);
  });

  it("renders a GFM table with its alignments", () => {
    const html = renderMarkdown("| a | b |\n| --- | ---: |\n| 1 | 2 |");
    expect(html).toContain("<table>");
    expect(html).toContain("<th>a</th>");
    expect(html).toContain('<th style="text-align:right">b</th>');
    expect(html).toContain("<td>1</td>");
    expect(html).toContain('<td style="text-align:right">2</td>');
  });

  it("does not turn a paragraph that merely contains pipes into a table", () => {
    // Without the delimiter row it is prose, and treating it as a table is how
    // a sentence about `a | b` becomes an empty grid.
    expect(renderMarkdown("run a | b to pipe them")).toBe("<p>run a | b to pipe them</p>");
  });

  it("renders blockquotes and rules", () => {
    expect(renderMarkdown("> quoted")).toBe("<blockquote><p>quoted</p></blockquote>");
    expect(renderMarkdown("---")).toBe("<hr />");
  });

  it("joins the lines of one paragraph and separates two", () => {
    expect(renderMarkdown("one\ntwo")).toBe("<p>one two</p>");
    expect(renderMarkdown("one\n\ntwo")).toBe("<p>one</p>\n<p>two</p>");
  });
});

describe("inline", () => {
  it("renders emphasis, code, strikethrough and links", () => {
    expect(renderMarkdown("**b** and *i* and `c`")).toBe(
      "<p><strong>b</strong> and <em>i</em> and <code>c</code></p>",
    );
    expect(renderMarkdown("__b__ and _i_")).toBe("<p><strong>b</strong> and <em>i</em></p>");
    expect(renderMarkdown("~~gone~~")).toBe("<p><del>gone</del></p>");
    expect(renderMarkdown("[wiki](https://example.org)")).toContain(
      '<a href="https://example.org" target="_blank" rel="noreferrer">wiki</a>',
    );
  });

  it("leaves markdown inside a code span alone", () => {
    // The bug this guards: `**` inside `code` becoming a <strong> that then
    // spans out of the code element.
    expect(renderMarkdown("`a ** b`")).toBe("<p><code>a ** b</code></p>");
  });
});

describe("maths", () => {
  it("renders inline TeX with KaTeX", () => {
    const html = renderMarkdown("the field $E_1$ is a carrier");
    expect(html).toContain('class="katex"');
    expect(html).not.toContain("$E_1$");
  });

  it("renders a display equation as its own block", () => {
    const html = renderMarkdown("before\n\n$$\n\\frac{a}{b}\n$$\n\nafter");
    expect(html).toContain('<div class="nb-math-block">');
    expect(html).toContain("katex-display");
    // A block element inside a <p> would be closed early by the browser.
    expect(html).not.toMatch(/<p>[^<]*<div class="nb-math-block"/);
    expect(html).toContain("<p>before</p>");
    expect(html).toContain("<p>after</p>");
  });

  it("does not read a dollar inside code as maths", () => {
    expect(renderMarkdown("`$PATH` and `$HOME`")).toBe(
      "<p><code>$PATH</code> and <code>$HOME</code></p>",
    );
    expect(renderMarkdown("```sh\necho $PATH\n```")).toContain("echo $PATH");
  });

  it("marks TeX that does not parse instead of drawing KaTeX's red source", () => {
    const html = renderMarkdown("$\\frac{1$");
    expect(html).toContain("nb-math-error");
  });

  it("does not eat a lone dollar sign", () => {
    expect(renderMarkdown("it costs $5")).toBe("<p>it costs $5</p>");
  });
});

describe("escaping — the rule the file rests on", () => {
  it("shows HTML in a cell as text rather than running it", () => {
    const html = renderMarkdown('<img src=x onerror="steal()">');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("escapes inside code blocks and table cells too", () => {
    expect(renderMarkdown("```\n<script>go()</script>\n```")).toContain("&lt;script&gt;");
    expect(renderMarkdown("| a |\n| --- |\n| <b>x</b> |")).toContain("&lt;b&gt;");
  });

  it("refuses a link or image scheme that is not http or mailto", () => {
    expect(renderMarkdown("[x](javascript:alert(1))")).not.toContain("<a ");
    expect(renderMarkdown("![x](javascript:alert(1))")).not.toContain("<img");
    expect(renderMarkdown("[m](mailto:a@b.c)")).toContain('href="mailto:a@b.c"');
  });

  it("gives KaTeX no way to inject markup from a cell", () => {
    // `trust: false` is what makes \href and \includegraphics inert.
    const html = renderMarkdown("$\\href{javascript:alert(1)}{click}$");
    expect(html).not.toContain("javascript:alert(1)");
  });
});

describe("the example notebook's own prose", () => {
  // The cell the maintainer saw flat. Every feature it uses, in one render.
  const prose = [
    "# Getting started",
    "",
    "Runs on the container's **SimNIBS Python**, with *nothing to install*.",
    "",
    "## What it shows",
    "",
    "1. The environment and `tit`.",
    "2. A `pandas` table.",
    "",
    "$$",
    "|\\vec{E}| = 2|\\vec{E}_2|",
    "$$",
    "",
    "and $2|\\vec{E}_1|$ otherwise.",
    "",
    "| step | cost |",
    "| --- | --- |",
    "| environment | instant |",
    "",
    "See the [wiki](https://idossha.github.io/TI-Toolbox/).",
  ].join("\n");
  const html = renderMarkdown(prose);

  it("is not one flat paragraph", () => {
    expect(html).toContain("<h1>Getting started</h1>");
    expect(html).toContain("<h2>What it shows</h2>");
    expect(html).toContain("<ol>");
    expect(html).toContain("<strong>SimNIBS Python</strong>");
    expect(html).toContain("<em>nothing to install</em>");
    expect(html).toContain("<code>tit</code>");
    expect(html).toContain("<table>");
    expect(html).toContain('<a href="https://idossha.github.io/TI-Toolbox/"');
    expect(html).toContain("katex-display");
    expect(html).toContain('class="katex"');
  });
});
