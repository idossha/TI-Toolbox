/**
 * Markdown for notebook prose cells.
 *
 * SUNA renders markdown cells through `@suna/markdown`, a full SciMark parser
 * with citations, cross-references, figures and journal semantics. None of that
 * exists here and none of it belongs in a notebook cell, so this is its own
 * small renderer — but it covers what a notebook heading cell actually uses:
 * headings, lists, emphasis, links, inline and fenced code, blockquotes, rules,
 * GFM pipe tables, and TeX.
 *
 * **Maths is KaTeX**, the same library SUNA depends on (`katex`, and the only
 * dependency this feature adds). It is a real npm package rendered at build
 * time into the bundle, not a CDN script: the renderer's CSP forbids remote
 * scripts, and a `srcdoc` frame inherits that CSP, so a CDN would have drawn
 * nothing and said nothing about it.
 *
 * ## The one rule this file rests on
 *
 * Source is **escaped first**, and markup is only ever *added* to escaped text.
 * Code spans and maths are lifted out into placeholders before anything else
 * runs, so a `$` in a code block is not maths and an `*` in an equation is not
 * emphasis, and their replacements are the only HTML that did not come from
 * escaping. A markdown cell is author-supplied *and* kernel-adjacent content;
 * do not "improve" this by passing source through unescaped.
 */
import katex from "katex";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Only http(s) and mailto links become anchors; anything else stays text. */
function safeHref(href: string): string | null {
  return /^(https?:|mailto:)/i.test(href.trim()) ? escapeHtml(href.trim()) : null;
}

/**
 * TeX as HTML, or the source in a marked span when it does not parse.
 *
 * `throwOnError: false` is not enough on its own: KaTeX's own error rendering
 * is a red copy of the source, which in a notebook is indistinguishable from a
 * deliberate red equation. The class says "this did not parse" instead.
 */
function renderMath(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: true,
      // `trust: false` is KaTeX's default and is the reason `\href` and
      // `\includegraphics` cannot inject anything from a cell.
      trust: false,
      strict: false,
      output: "html",
    });
  } catch {
    return `<code class="nb-math-error" title="This is not valid TeX">${escapeHtml(tex)}</code>`;
  }
}

/**
 * A slot table for content that must survive escaping and inline parsing
 * untouched.
 *
 * The delimiter is **NUL**, written as an escape so it is visible in a diff: it
 * cannot occur in markdown anyone writes, no rule below can see inside it, and
 * `escapeHtml` leaves it alone. A whitespace delimiter was tried first and is
 * wrong — `String.trim()` eats it, so a line that is nothing but one slot stops
 * being recognisable as the block it stands for.
 */
const MARK = "\u0000";

class Slots {
  private readonly values: string[] = [];
  /** Slots that stand for a BLOCK rather than for inline content. */
  private readonly blocks = new Set<number>();

  put(html: string): string {
    this.values.push(html);
    return `${MARK}slot${this.values.length - 1}${MARK}`;
  }

  /** A slot whose content is a block element — a fence, a display equation. */
  putBlock(html: string): string {
    const marker = this.put(html);
    this.blocks.add(this.values.length - 1);
    return marker;
  }

  /**
   * True when this whole line is one BLOCK slot.
   *
   * The distinction matters: a line that is nothing but a code *span* is still
   * a paragraph (`` `a ** b` `` on its own renders as `<p><code>…</code></p>`),
   * while a line that is a fence or a display equation is not — putting a
   * `<pre>` inside a `<p>` makes the browser close the paragraph early.
   */
  isWholeBlock(line: string): boolean {
    const match = new RegExp(`^${MARK}slot(\\d+)${MARK}$`).exec(line);
    return match !== null && this.blocks.has(Number(match[1]));
  }

  restore(text: string): string {
    return text.replace(
      new RegExp(`${MARK}slot(\\d+)${MARK}`, "g"),
      (_whole, index: string) => this.values[Number(index)] ?? "",
    );
  }
}

/** Inline markdown, on already-slotted text. Escapes, then adds markup. */
function inline(text: string, slots: Slots): string {
  let html = escapeHtml(text);
  html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  html = html.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
  html = html.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (whole, alt: string, src: string) => {
    const safe = safeHref(src);
    return safe === null ? whole : `<img src="${safe}" alt="${alt}" />`;
  });
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (whole, label: string, href: string) => {
    const safe = safeHref(href);
    return safe === null ? whole : `<a href="${safe}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  return slots.restore(html);
}

/** One GFM pipe row into its cells, tolerating the optional outer pipes. */
function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

const ALIGNMENT = /^:?-{2,}:?$/;

function isDelimiterRow(line: string | undefined): boolean {
  if (line === undefined) return false;
  const cells = splitRow(line);
  return cells.length > 0 && cells.every((cell) => ALIGNMENT.test(cell));
}

function alignmentOf(cell: string): string {
  const left = cell.startsWith(":");
  const right = cell.endsWith(":");
  if (left && right) return ' style="text-align:center"';
  if (right) return ' style="text-align:right"';
  if (left) return ' style="text-align:left"';
  return "";
}

/** Markdown source as HTML. Never returns markup the source was not escaped into. */
export function renderMarkdown(source: string): string {
  const slots = new Slots();

  // ---- lift out what must not be parsed as markdown ----------------------
  // The order is load-bearing. Fenced code first (a fence may legally contain
  // `$$` and backticks). Then CODE SPANS, before either maths pass: `$PATH`
  // and `$HOME` in two adjacent spans would otherwise be read as one inline
  // equation spanning the prose between them. Then block maths, then inline.
  let text = source.replace(
    /```([A-Za-z0-9_+-]*)\n([\s\S]*?)```/g,
    (_whole, language: string, body: string) => {
      const cls = language === "" ? "" : ` class="language-${escapeHtml(language)}"`;
      const block = `<pre class="nb-code"><code${cls}>${escapeHtml(body.replace(/\n$/, ""))}</code></pre>`;
      return `\n\n${slots.putBlock(block)}\n\n`;
    },
  );
  text = text.replace(/`([^`\n]+)`/g, (_whole, code: string) =>
    slots.put(`<code>${escapeHtml(code)}</code>`),
  );
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_whole, tex: string) => {
    // A display equation is its own block, separated from whatever sat on the
    // same line — inside a paragraph the browser closes the <p> early.
    const block = `<div class="nb-math-block">${renderMath(tex.trim(), true)}</div>`;
    return `\n\n${slots.putBlock(block)}\n\n`;
  });
  text = text.replace(
    /(^|[^\\$])\$([^$\n]+?)\$/g,
    (_whole, before: string, tex: string) => before + slots.put(renderMath(tex.trim(), false)),
  );

  // ---- blocks -------------------------------------------------------------
  const lines = text.split("\n");
  const out: string[] = [];
  let listKind: "ul" | "ol" | null = null;
  let paragraph: string[] = [];
  let quote: string[] = [];

  const closeList = (): void => {
    if (listKind !== null) {
      out.push(`</${listKind}>`);
      listKind = null;
    }
  };
  const closeParagraph = (): void => {
    if (paragraph.length > 0) {
      out.push(`<p>${inline(paragraph.join(" "), slots)}</p>`);
      paragraph = [];
    }
  };
  const closeQuote = (): void => {
    if (quote.length > 0) {
      out.push(`<blockquote><p>${inline(quote.join(" "), slots)}</p></blockquote>`);
      quote = [];
    }
  };
  const closeAll = (): void => {
    closeParagraph();
    closeList();
    closeQuote();
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] as string;

    if (line.trim() === "") {
      closeAll();
      continue;
    }

    // A slot that is a whole line is a block someone already rendered.
    if (slots.isWholeBlock(line.trim())) {
      closeAll();
      out.push(slots.restore(line.trim()));
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeAll();
      const level = (heading[1] as string).length;
      out.push(`<h${level}>${inline(heading[2] as string, slots)}</h${level}>`);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      closeAll();
      out.push("<hr />");
      continue;
    }

    // A GFM table is a header row plus a delimiter row; without the second
    // it is an ordinary paragraph that happens to contain pipes.
    if (line.includes("|") && isDelimiterRow(lines[i + 1])) {
      closeAll();
      const header = splitRow(line);
      const alignments = splitRow(lines[i + 1] as string).map(alignmentOf);
      const body: string[][] = [];
      let j = i + 2;
      while (j < lines.length && (lines[j] as string).includes("|") && (lines[j] as string).trim() !== "") {
        body.push(splitRow(lines[j] as string));
        j += 1;
      }
      i = j - 1;
      const head = header
        .map((cell, index) => `<th${alignments[index] ?? ""}>${inline(cell, slots)}</th>`)
        .join("");
      const rows = body
        .map(
          (cells) =>
            `<tr>${cells.map((cell, index) => `<td${alignments[index] ?? ""}>${inline(cell, slots)}</td>`).join("")}</tr>`,
        )
        .join("");
      out.push(`<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`);
      continue;
    }

    const quoted = /^\s*>\s?(.*)$/.exec(line);
    if (quoted) {
      closeParagraph();
      closeList();
      quote.push(quoted[1] as string);
      continue;
    }
    closeQuote();

    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      closeParagraph();
      const kind = bullet ? "ul" : "ol";
      if (listKind !== kind) {
        closeList();
        out.push(`<${kind}>`);
        listKind = kind;
      }
      out.push(`<li>${inline(((bullet ?? numbered) as RegExpExecArray)[1] as string, slots)}</li>`);
      continue;
    }

    // An indented block inside a list item continues that item's text rather
    // than starting a paragraph the list would have to be closed for.
    if (listKind !== null && /^\s{2,}\S/.test(line) && out.length > 0) {
      const last = out.pop() as string;
      out.push(last.replace(/<\/li>$/, ` ${inline(line.trim(), slots)}</li>`));
      continue;
    }

    closeList();
    paragraph.push(line.trim());
  }
  closeAll();
  return out.join("\n");
}
