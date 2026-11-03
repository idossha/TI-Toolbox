// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createContext, runInContext } from "node:vm";
import { beforeEach, expect, it } from "vitest";

beforeEach(() => {
  document.body.replaceChildren();
  Object.defineProperty(document, "readyState", { value: "complete", configurable: true });
});

function load(path: string, location = { origin: "https://docs.example", href: "https://docs.example/", hash: "" }) {
  const context = createContext({ document, window: { location }, location, URL, URLSearchParams, console });
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
  // The markup and data shape of docs/wiki/atlases.md and docs/_data/atlases.json, trimmed to one atlas.
  document.body.innerHTML = `<script type="application/json" id="atlas-data"></script>
    <div class="atlas-viewer"><div class="atlas-left">
      <div class="atlas-controls"><select id="atlas-select" class="atlas-select"><option value="mni:cit168">CIT168</option></select></div>
      <div class="atlas-canvas-wrap"><canvas id="atlas-canvas"></canvas></div><p class="atlas-hint"></p>
    </div><div class="atlas-right"><div class="atlas-right-inner"><div id="atlas-desc"></div>
      <div class="atlas-table-tools"><input type="text" id="atlas-filter" class="atlas-filter"><span class="atlas-count" id="atlas-count"></span></div>
      <div class="atlas-table-scroll"><table id="atlas-table"><thead></thead><tbody></tbody></table></div>
    </div></div></div>
    <div class="atlas-no-webgl" style="display:none;"><p></p></div>`;
  const name = '<img src=x onerror="alert(1)"> Thalamus';
  const row = { id: 1, index: 1, name, r: 242, g: 84, b: 84, voxels: 9136, volume_mm3: 9136, centroid_mni: [-26, 0.7, 0.4] };
  document.getElementById("atlas-data")!.textContent = JSON.stringify({
    mni: { template: { filename: "mni152_t1_1mm.nii.gz" }, atlases: { cit168: { display_name: "CIT168", filename: "cit168.nii.gz", rows: [row] } } },
  });
  load("atlas-browser.js");
  const cell = document.querySelector("#atlas-table .atlas-name")!;
  expect(cell.textContent).toBe(name);
  expect(cell.children.length).toBe(0);
  const input = document.getElementById("atlas-filter") as HTMLInputElement;
  // A query outside the tag: "img" would split it ("<<mark>img</mark> src=…"), which even innerHTML leaves as text.
  input.value = "thal";
  input.dispatchEvent(new Event("input"));
  expect(cell.textContent).toBe(name);
  expect(cell.querySelector("mark")?.textContent).toBe("Thal");
  expect(cell.querySelector("img")).toBeNull();
  input.value = "";
  input.dispatchEvent(new Event("input"));
  expect(cell.textContent).toBe(name);
  expect(cell.children.length).toBe(0);
});
