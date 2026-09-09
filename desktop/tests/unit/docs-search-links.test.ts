// @vitest-environment jsdom
// Search-index links stay on the docs origin; hostile text remains text. No browser is launched.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createContext, runInContext } from "node:vm";
import { beforeEach, expect, it } from "vitest";

const source = readFileSync(resolve(__dirname, "../../../docs/assets/js/search/results.js"), "utf8");

beforeEach(() => {
  document.documentElement.setAttribute("data-baseurl", "/TI-Toolbox");
  document.body.innerHTML = '<div id="search-stats"></div><div id="search-results-list"></div><div id="no-results"></div>';
});

function render(url: string, base = "/TI-Toolbox") {
  document.documentElement.setAttribute("data-baseurl", base);
  const context = createContext({
    document,
    window: { location: new URL("https://docs.example/TI-Toolbox/search/") },
    URL, URLSearchParams,
    console: { error: () => {} },
    fixture: [{ url, title: '<img src=x onerror="alert(1)">', content: "safe content" }],
  });
  runInContext(source, context);
  runInContext('displayResults(fixture, "img")', context);
  return document.querySelector("a")!;
}

it.each([
  ["/wiki/guide/", "/TI-Toolbox", "https://docs.example/TI-Toolbox/wiki/guide/"],
  ["/TI-Toolbox/wiki/guide/?q=a#part", "/TI-Toolbox", "https://docs.example/TI-Toolbox/wiki/guide/?q=a#part"],
  ["/wiki/guide/", "", "https://docs.example/wiki/guide/"],
])("keeps valid indexed path %s", (url, base, expected) => {
  expect(render(url, base).getAttribute("href")).toBe(expected);
  expect(document.querySelector("img")).toBeNull();
  expect(document.querySelector("mark")?.textContent).toBe("img");
});

it.each([
  ["javascript:alert(1)", ""],
  ["data:text/html,<script>alert(1)</script>", ""],
  ["//evil.example/wiki/", ""],
  ["https://evil.example/wiki/", "/TI-Toolbox"],
  ["/wiki/guide/", "https://evil.example"],
])("leaves unsafe or foreign indexed URL %s unlinked", (url, base) => {
  expect(render(url, base).hasAttribute("href")).toBe(false);
});
