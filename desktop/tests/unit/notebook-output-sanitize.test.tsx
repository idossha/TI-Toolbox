// @vitest-environment jsdom
/**
 * Rich notebook outputs cannot reach the app around them (audit UI-03).
 *
 * The reproduction the audit gave: a stored output carrying a `<style>` block hid an element
 * OUTSIDE the output. A notebook is a shared file, so its outputs are attacker-controllable text
 * this app renders — they get an allowlist, and an SVG figure gets image context.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { OutputView } from "../../src/renderer/pages/notebooks/Outputs";
import { sanitizeOutputHtml, svgImageSource } from "../../src/renderer/pages/notebooks/sanitize";
import type { Output } from "../../src/renderer/pages/notebooks/notebook";

let container: HTMLDivElement;
let root: Root;
let chrome: HTMLDivElement;

beforeEach(() => {
  chrome = document.createElement("div");
  chrome.id = "app-chrome";
  chrome.textContent = "sidebar";
  document.body.appendChild(chrome);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  chrome.remove();
});

function render(output: Output): void {
  act(() => root.render(<OutputView output={output} />));
}

function display(data: Record<string, unknown>): Output {
  return { output_type: "display_data", data, metadata: {} } as unknown as Output;
}

describe("adversarial output", () => {
  it("a <style> block in an HTML output cannot restyle anything outside it", () => {
    render(display({ "text/html": "<style>#app-chrome{display:none}</style><table><tr><td>1</td></tr></table>" }));
    expect(document.querySelector("#app-chrome")).not.toBeNull();
    expect(container.querySelector("style")).toBeNull();
    expect(document.head.querySelector("style#none")).toBeNull();
    // The table itself still rendered.
    expect(container.querySelector("td")?.textContent).toBe("1");
  });

  it("strips event handlers, scripts and javascript: URLs", () => {
    render(
      display({
        "text/html":
          '<img src="x" onerror="window.__pwned = true"><script>window.__pwned = true</script>' +
          '<a href="javascript:alert(1)">click</a>',
      }),
    );
    const img = container.querySelector("img");
    expect(img?.getAttribute("onerror")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("a")?.getAttribute("href")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("an SVG output renders as an image, so its own script/style never apply", () => {
    render(display({ "image/svg+xml": '<svg xmlns="http://www.w3.org/2000/svg"><style>#app-chrome{display:none}</style><rect/></svg>' }));
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img!.getAttribute("src")!.startsWith("data:image/svg+xml")).toBe(true);
    expect(container.querySelector("svg")).toBeNull();
    expect(document.querySelector("#app-chrome")).not.toBeNull();
  });
});

describe("ordinary output still displays", () => {
  it("a DataFrame table keeps its structure, classes and per-cell styling", () => {
    render(
      display({
        "text/html":
          '<div class="dataframe"><table class="tbl"><thead><tr><th>a</th></tr></thead>' +
          '<tbody><tr><td style="color: red" colspan="2">3.14</td></tr></tbody></table></div>',
      }),
    );
    expect(container.querySelector("table.tbl")).not.toBeNull();
    expect(container.querySelector("th")?.textContent).toBe("a");
    const td = container.querySelector("td")!;
    expect(td.getAttribute("colspan")).toBe("2");
    expect(td.getAttribute("style")).toContain("red");
  });

  it("a plot's static HTML snippet keeps its image", () => {
    render(display({ "text/html": '<div><img src="data:image/png;base64,AAA" alt="fig"></div>' }));
    expect(container.querySelector("img")?.getAttribute("src")).toBe("data:image/png;base64,AAA");
  });

  it("plain text and images are untouched by any of this", () => {
    render(display({ "image/png": "AAA" }));
    expect(container.querySelector("img")?.getAttribute("src")).toContain("data:image/png;base64,AAA");
  });
});

describe("sanitizeOutputHtml", () => {
  it("unwraps unknown elements rather than dropping their text", () => {
    expect(sanitizeOutputHtml("<custom-thing>kept</custom-thing>")).toBe("kept");
  });

  it("drops <base>, <link>, <iframe> and comments outright", () => {
    const out = sanitizeOutputHtml('<base href="http://evil"><link rel="stylesheet" href="x"><iframe src="x"></iframe><!-- c -->ok');
    expect(out).toBe("ok");
  });

  it("keeps external links but never with a handle on this window", () => {
    const out = sanitizeOutputHtml('<a href="https://example.org">x</a>');
    expect(out).toContain('rel="noopener noreferrer"');
    expect(out).toContain('target="_blank"');
  });

  it("refuses a style attribute that smuggles a url() or an expression", () => {
    expect(sanitizeOutputHtml('<div style="background:url(javascript:alert(1))">x</div>')).not.toContain("style");
    expect(sanitizeOutputHtml('<div style="width:expression(alert(1))">x</div>')).not.toContain("style");
  });
});

describe("svgImageSource", () => {
  it("encodes the document so it cannot break out of the attribute", () => {
    expect(svgImageSource('<svg a="b">')).toBe("data:image/svg+xml;charset=utf-8,%3Csvg%20a%3D%22b%22%3E");
  });
});
