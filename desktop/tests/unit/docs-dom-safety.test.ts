// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createContext, runInContext } from "node:vm";
import { beforeEach, expect, it } from "vitest";

beforeEach(() => {
  document.body.replaceChildren();
  Object.defineProperty(document, "readyState", { value: "complete", configurable: true });
});

function load(path: string, location = { origin: "https://docs.example", href: "https://docs.example/" }) {
  const context = createContext({ document, window: { location }, URL, URLSearchParams, console });
  runInContext(readFileSync(resolve(__dirname, "../../../docs/assets/js", path), "utf8"), context);
  return location;
}

it.each(["search/header.js", "search/results.js"])("%s keeps navigation on origin with hostile base attributes", path => {
  const isHeader = path.includes("header");
  document.body.innerHTML = `<input id="${isHeader ? "search-input" : "search-query"}"><button id="${isHeader ? "search-button" : "search-submit-button"}"></button>`;
  document.documentElement.setAttribute("data-baseurl", "javascript:alert(1)//");
  // Results-page initialization also fetches its index; retain its navigation function
  // and invoke that directly so no network request is needed.
  if (!isHeader) document.getElementById("search-submit-button")!.remove();
  const location = { origin: "https://docs.example", href: "https://docs.example/" };
  const context = createContext({ document, window: { location }, URL, URLSearchParams, console });
  runInContext(readFileSync(resolve(__dirname, "../../../docs/assets/js", path), "utf8"), context);
  const query = '<img onerror="alert(1)">&next=evil';
  if (isHeader) {
    (document.querySelector("input") as HTMLInputElement).value = query;
    (document.querySelector("button") as HTMLButtonElement).click();
  } else {
    context.query = query;
    runInContext("navigateToSearch(query)", context);
  }
  const destination = new URL(location.href);
  expect(destination.origin).toBe("https://docs.example");
  expect(destination.searchParams.get("q")).toBe(query);
});

it("lightbox displays hostile alt captions literally", () => {
  document.body.innerHTML = '<div class="wiki-content-inner"><img src="/safe.png"></div>';
  const image = document.querySelector("img")!;
  const caption = '<img src=x onerror="alert(1)">';
  image.alt = caption;
  load("wiki-lightbox.js");
  image.click();
  const rendered = document.querySelector(".wiki-lightbox-caption")!;
  expect(rendered.textContent).toBe(caption);
  expect(rendered.children.length).toBe(0);
});

it("atlas filters highlight literal names without interpreting markup", () => {
  document.body.innerHTML = '<script id="atlas-data" type="application/json">{"mni":{}}</script><div class="atlas-viewer" data-space="mni"><canvas></canvas></div><input class="atlas-filter" data-target="regions"><table id="regions"><tbody><tr data-id="1"><td class="atlas-name"></td></tr></tbody></table>';
  const name = '<img src=x onerror="alert(1)"> Thalamus';
  const cell = document.querySelector(".atlas-name")!;
  cell.textContent = name;
  load("atlas-browser.js");
  const input = document.querySelector("input")!;
  input.value = "img";
  input.dispatchEvent(new Event("input"));
  expect(cell.textContent).toBe(name);
  expect(cell.querySelector("mark")?.textContent).toBe("img");
  expect(cell.querySelector("img")).toBeNull();
  input.value = "";
  input.dispatchEvent(new Event("input"));
  expect(cell.textContent).toBe(name);
  expect(cell.children.length).toBe(0);
});
