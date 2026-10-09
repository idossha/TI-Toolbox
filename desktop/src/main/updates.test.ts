// TI-Toolbox's own release check (src/main/updates.ts): version order, when it runs, and that
// every failure comes back as `error` rather than a throw. Fetch is a fake; nothing touches GitHub.
import { describe, expect, it, vi } from "vitest";
import { compareVersions, createUpdateChecker, RELEASE_FEED, updateChecksEnabled } from "./updates";

function feed(body: unknown, status = 200) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
}
const RELEASE = { tag_name: "v3.1.0", html_url: "https://github.com/idossha/TI-Toolbox/releases/tag/v3.1.0", draft: false, prerelease: false };

describe("compareVersions", () => {
  it("orders numerically, not lexically, and treats missing parts as 0", () => {
    expect(compareVersions("3.0.10", "3.0.9")).toBeGreaterThan(0);
    expect(compareVersions("3.1.0", "3.0.99")).toBeGreaterThan(0);
    expect(compareVersions("2.9.9", "3.0.0")).toBeLessThan(0);
    expect(compareVersions("3.0.2", "3.0.2")).toBe(0);
    expect(compareVersions("3.1", "3.1.0")).toBe(0);
  });
});

describe("updateChecksEnabled", () => {
  it("checks packaged apps only, never automated runs, and obeys TIT_UPDATE_CHECK", () => {
    expect(updateChecksEnabled({}, true)).toBe(true);
    expect(updateChecksEnabled({}, false)).toBe(false);
    expect(updateChecksEnabled({ TIT_E2E_TOKEN: "mock-token" }, true)).toBe(false);
    expect(updateChecksEnabled({ TIT_E2E_OFFSCREEN: "1" }, true)).toBe(false);
    expect(updateChecksEnabled({ TIT_UPDATE_CHECK: "1", TIT_E2E_TOKEN: "mock-token" }, false)).toBe(true);
    expect(updateChecksEnabled({ TIT_UPDATE_CHECK: "0" }, true)).toBe(false);
  });
});

describe("createUpdateChecker", () => {
  it("reports a newer release with its page, asks GitHub with a User-Agent, and prompts once", async () => {
    const fetchImpl = feed(RELEASE);
    const check = createUpdateChecker({ current: "3.0.2", enabled: true, fetchImpl });
    expect(await check()).toEqual({ current: "3.0.2", latest: "3.1.0", available: true, url: RELEASE.html_url, error: null, prompt: true });
    expect(fetchImpl).toHaveBeenCalledWith(RELEASE_FEED, expect.objectContaining({ headers: expect.objectContaining({ "User-Agent": "TI-Toolbox" }) }));
    // The answer is kept for the process; the popup is not offered again, even after a forced check.
    expect(await check()).toMatchObject({ available: true, prompt: false });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(await check(true)).toMatchObject({ available: true, prompt: false });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("is up to date when the release is the same or older", async () => {
    expect(await createUpdateChecker({ current: "3.1.0", enabled: true, fetchImpl: feed(RELEASE) })()).toMatchObject({ latest: "3.1.0", available: false, error: null, prompt: false });
    expect(await createUpdateChecker({ current: "3.2.0", enabled: true, fetchImpl: feed(RELEASE) })()).toMatchObject({ available: false, error: null });
  });

  it("uses the overridden feed URL", async () => {
    const fetchImpl = feed(RELEASE);
    await createUpdateChecker({ current: "3.0.2", enabled: true, feedUrl: "http://127.0.0.1:9/latest", fetchImpl })();
    expect(fetchImpl).toHaveBeenCalledWith("http://127.0.0.1:9/latest", expect.anything());
  });

  it("returns an error, never throws, when offline, refused, unreadable or not a published version", async () => {
    const offline = vi.fn(async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch;
    const cases: [typeof fetch, RegExp][] = [
      [offline, /offline/],
      [feed({ message: "rate limited" }, 403), /HTTP 403/],
      [vi.fn(async () => new Response("<html>", { status: 200 })) as unknown as typeof fetch, /read the release feed/],
      [feed({ ...RELEASE, tag_name: "nightly" }), /published version/],
      [feed({ ...RELEASE, prerelease: true }), /published version/],
      [feed({ ...RELEASE, draft: true }), /published version/],
    ];
    for (const [fetchImpl, message] of cases) {
      const result = await createUpdateChecker({ current: "3.0.2", enabled: true, fetchImpl })();
      expect(result).toMatchObject({ current: "3.0.2", latest: null, available: false, url: null, prompt: false });
      expect(result.error).toMatch(message);
    }
  });

  it("asks nobody when checks are off", async () => {
    const fetchImpl = feed(RELEASE);
    const result = await createUpdateChecker({ current: "3.0.2", enabled: false, fetchImpl })(true);
    expect(result).toMatchObject({ available: false, latest: null, prompt: false, error: "Update checks are off in development builds." });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
