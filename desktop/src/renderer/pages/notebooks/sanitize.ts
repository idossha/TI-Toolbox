/**
 * Making a kernel's HTML output safe to put in this document (audit UI-03).
 *
 * A notebook output is not the app's own markup: it is whatever the kernel produced, and a
 * notebook is a file people SHARE, so it is attacker-controllable text that this app stores and
 * later renders. It used to go in verbatim via `dangerouslySetInnerHTML`, which meant an output
 * shared the app's document — a `<style>` block inside a DataFrame repr restyled the app chrome
 * (a probe hid an element outside the output entirely), `<img onerror>` ran script in the app's
 * origin, and a `<link>`/`<base>` could reach further still. Scripts inserted by `innerHTML`
 * never execute, but that was the only thing standing in the way.
 *
 * Why an allowlist and not a sandboxed iframe: the app is served under
 * `script-src 'self'; frame-src 'self'` (tit/server/app.py), and a `srcdoc` frame INHERITS its
 * parent's CSP — the inline height-reporting script such a frame needs to size itself would be
 * blocked, and so would any plotting library's inline script, so a frame would buy isolation at
 * the price of every rich output rendering as a blank box of the wrong height. An allowlist keeps
 * DataFrame tables and static plot HTML looking exactly as they do today while removing the
 * capabilities that made them dangerous.
 *
 * What survives: structural and inline markup, tables, images (`data:` and same-origin only), and
 * per-element `style` attributes (pandas' Styler is unusable without them — and a style ATTRIBUTE
 * cannot reach outside the element it is on, unlike a `<style>` RULE, which can).
 * What does not: `<script>`, `<style>`, `<link>`, `<base>`, `<meta>`, `<iframe>`, `<object>`,
 * `<embed>`, `<form>` and friends, every `on*` handler, and any `javascript:` URL.
 */

const ALLOWED_TAGS = new Set([
  "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup", "dd", "details",
  "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i",
  "img", "kbd", "li", "mark", "ol", "p", "pre", "q", "s", "samp", "small", "span", "strong", "sub",
  "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "time", "tr", "u", "ul", "var",
]);

/** Dropped with everything inside them; unlisted tags are unwrapped, keeping their text. */
const DROPPED_TAGS = new Set([
  "script", "style", "link", "base", "meta", "iframe", "frame", "frameset", "object", "embed",
  "applet", "form", "input", "button", "select", "textarea", "option", "template", "noscript",
  "audio", "video", "source", "track", "canvas", "math",
]);

const ALLOWED_ATTRS = new Set([
  "align", "alt", "class", "colspan", "dir", "headers", "height", "href", "id", "lang", "rowspan",
  "scope", "span", "src", "style", "title", "valign", "width",
]);

const SAFE_HREF = /^(https?:|mailto:|#)/i;
const SAFE_IMG_SRC = /^(data:image\/(png|jpeg|gif|webp|svg\+xml);|https?:)/i;

/** A `style` attribute is per-element, but it must not smuggle a URL or an old IE expression. */
function safeStyle(value: string): string | null {
  const lowered = value.toLowerCase();
  if (lowered.includes("expression(") || lowered.includes("javascript:") || lowered.includes("url(")) return null;
  if (lowered.includes("position:fixed") || lowered.includes("position: fixed")) return null;
  return value;
}

function scrubElement(element: Element): void {
  for (const attr of [...element.attributes]) {
    const name = attr.name.toLowerCase();
    const value = attr.value;
    if (name.startsWith("on") || !ALLOWED_ATTRS.has(name)) {
      element.removeAttribute(attr.name);
      continue;
    }
    if (name === "href" && !SAFE_HREF.test(value.trim())) element.removeAttribute(attr.name);
    else if (name === "src" && !SAFE_IMG_SRC.test(value.trim())) element.removeAttribute(attr.name);
    else if (name === "style") {
      const safe = safeStyle(value);
      if (safe === null) element.removeAttribute(attr.name);
    }
  }
  // A link that leaves the app opens in the user's browser, never with a handle back on this window.
  if (element.tagName.toLowerCase() === "a" && element.hasAttribute("href")) {
    element.setAttribute("rel", "noopener noreferrer");
    element.setAttribute("target", "_blank");
  }
}

function walk(node: Node): void {
  for (const child of [...node.childNodes]) {
    if (child.nodeType === 3 /* text */ || child.nodeType === 4 /* cdata */) continue;
    if (child.nodeType !== 1 /* element */) {
      child.parentNode?.removeChild(child); // comments, processing instructions
      continue;
    }
    const element = child as Element;
    const tag = element.tagName.toLowerCase();
    if (DROPPED_TAGS.has(tag)) {
      element.parentNode?.removeChild(element);
      continue;
    }
    if (!ALLOWED_TAGS.has(tag)) {
      // Unknown but not dangerous: keep the text it wrapped, drop the element itself.
      const parent = element.parentNode;
      walk(element);
      while (element.firstChild) parent?.insertBefore(element.firstChild, element);
      parent?.removeChild(element);
      continue;
    }
    scrubElement(element);
    walk(element);
  }
}

/**
 * The kernel's HTML with everything that could reach outside its own output removed.
 *
 * Parsing happens in a detached `DOMParser` document: nothing there loads, fetches or runs, so
 * the markup is neutralised before it is ever near the live page.
 */
export function sanitizeOutputHtml(html: string): string {
  if (typeof DOMParser === "undefined") return ""; // no parser (SSR/node): render nothing rather than raw markup
  const doc = new DOMParser().parseFromString(html, "text/html");
  walk(doc.body);
  return doc.body.innerHTML;
}

/**
 * An SVG figure as an inert image.
 *
 * SVG is a document format: inline, it can carry `<script>`, `<style>` (which leaks into the app
 * exactly as an HTML `<style>` does) and event handlers. Loaded through `<img src="data:...">`
 * the browser refuses to run any of it — scripting is disabled in image context — and it still
 * renders as the vector figure it is, which is the whole point of preferring SVG over the PNG.
 */
export function svgImageSource(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
