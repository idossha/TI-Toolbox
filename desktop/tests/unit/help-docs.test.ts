/**
 * Help ▸ Docs points at the published documentation website, never at the app's own origin.
 *
 * The bug this pins: the tab used to probe and frame the same-origin path `/docs/`. `tit.server`'s
 * static route is an SPA catch-all (only `api`/`ws`/`auth`/`tetravox` are reserved), so `/docs/`
 * answers 200 with the app's own `index.html` — the presence check always passed and the iframe
 * rendered TI-Toolbox inside TI-Toolbox.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DOCS_SITE, docsSiteReachable } from "../../src/renderer/pages/help/api";

const REPO_ROOT = resolve(__dirname, "../../..");

afterEach(() => vi.unstubAllGlobals());

describe("DOCS_SITE", () => {
  it("is the site docs/_config.yml publishes (url + baseurl), not a same-origin path", () => {
    const cfg = readFileSync(resolve(REPO_ROOT, "docs/_config.yml"), "utf8");
    const url = /^url:\s*"([^"]+)"/m.exec(cfg)![1];
    const baseurl = /^baseurl:\s*"([^"]+)"/m.exec(cfg)![1];
    expect(DOCS_SITE).toBe(`${url}${baseurl}/`);
    expect(new URL(DOCS_SITE).origin).not.toBe("http://localhost");
    expect(DOCS_SITE.startsWith("https://")).toBe(true);
  });

  it("is framed by DocsTab, and no same-origin /docs path is fetched any more", () => {
    const dir = resolve(__dirname, "../../src/renderer/pages/help");
    const tab = readFileSync(resolve(dir, "DocsTab.tsx"), "utf8");
    const api = readFileSync(resolve(dir, "api.ts"), "utf8");
    expect(tab).toMatch(/src=\{DOCS_SITE\}/);
    expect(tab).not.toMatch(/src="\/docs/);
    expect(api).not.toMatch(/fetch\("\/docs/);
  });
});

describe("docsSiteReachable", () => {
  it("is true when the site answers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(docsSiteReachable()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(DOCS_SITE, expect.objectContaining({ mode: "no-cors" }));
  });

  it("is false when the machine is offline (fetch rejects)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(docsSiteReachable()).resolves.toBe(false);
  });

  it("is false when the probe outlives its timeout rather than hanging the tab", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    await expect(docsSiteReachable(5)).resolves.toBe(false);
  });
});
