/**
 * The small slice of markdown a notebook's prose cells actually use.
 *
 * SUNA renders markdown cells through `@suna/markdown`, a full SciMark parser
 * with citations, cross-references and math. None of that exists here, and
 * pulling a markdown library in for cell prose would be a dependency the rest
 * of this app has no other use for. So this is deliberately small: headings,
 * emphasis, inline and fenced code, links, lists, rules, paragraphs — the
 * things people write in a notebook heading cell.
 *
 * Everything is escaped first and markup is only ever *added* to escaped text,
 * so a cell that contains HTML shows that HTML as text rather than running it.
 * That is the security property this file rests on; do not "improve" it by
 * passing source through unescaped.
 */

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

function inline(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (whole, label: string, href: string) => {
    const safe = safeHref(href);
    return safe === null ? whole : `<a href="${safe}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  return html;
}

/** Markdown source as HTML. Never returns anything the source did not escape. */
export function renderMarkdown(source: string): string {
  const lines = source.split("\n");
  const out: string[] = [];
  let listKind: "ul" | "ol" | null = null;
  let paragraph: string[] = [];
  let fence: string[] | null = null;

  const closeList = (): void => {
    if (listKind !== null) {
      out.push(`</${listKind}>`);
      listKind = null;
    }
  };
  const closeParagraph = (): void => {
    if (paragraph.length > 0) {
      out.push(`<p>${inline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };

  for (const line of lines) {
    if (fence !== null) {
      if (line.trimEnd().startsWith("```")) {
        out.push(`<pre><code>${escapeHtml(fence.join("\n"))}</code></pre>`);
        fence = null;
      } else {
        fence.push(line);
      }
      continue;
    }
    if (line.trimStart().startsWith("```")) {
      closeParagraph();
      closeList();
      fence = [];
      continue;
    }
    if (line.trim() === "") {
      closeParagraph();
      closeList();
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeParagraph();
      closeList();
      const level = heading[1]!.length;
      out.push(`<h${level}>${inline(heading[2]!)}</h${level}>`);
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      closeParagraph();
      closeList();
      out.push("<hr />");
      continue;
    }
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
      out.push(`<li>${inline((bullet ?? numbered)![1]!)}</li>`);
      continue;
    }
    paragraph.push(line.trim());
  }
  if (fence !== null) out.push(`<pre><code>${escapeHtml(fence.join("\n"))}</code></pre>`);
  closeParagraph();
  closeList();
  return out.join("\n");
}
