/**
 * Release-check version order follows SemVer 2.0.0 §11, and a disabled check says why
 * (desktop/src/main/updates.ts). Expected orders are the spec's own example chains
 * (https://semver.org/spec/v2.0.0.html §11, §10 for build metadata), not this module's output.
 *
 * The defect: "3.1.2-rc.1".split(".") made Number("2-rc") NaN, the NaN difference was falsy and
 * the compare returned 0, so an rc/dev build (dev/update/update_version.py writes X.Y.Z-dev.N) was
 * never told its final release was out. And TIT_UPDATE_CHECK=0 on a packaged app answered "off in
 * development builds". Run: cd desktop && npx vitest run src/main/update-version-compare.test.ts
 */
import { describe, expect, it, vi } from "vitest";
import { compareVersions, createAppUpdateChecker, createUpdateChecker, updateCheckOffReason, updateChecksEnabled } from "./updates";

/** SemVer §11.4's example, lowest first. */
const SPEC_PRERELEASE_CHAIN = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"];
/** SemVer §11.2's example, lowest first. */
const SPEC_CORE_CHAIN = ["1.0.0", "2.0.0", "2.1.0", "2.1.1"];

function feed(tag: string) {
  const body = { tag_name: tag, html_url: `https://github.com/idossha/TI-Toolbox/releases/tag/${tag}`, draft: false, prerelease: false };
  return vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })) as unknown as typeof fetch;
}

describe("compareVersions follows SemVer precedence", () => {
  it.each([["pre-release chain", SPEC_PRERELEASE_CHAIN], ["core chain", SPEC_CORE_CHAIN]])("orders every pair of the spec's %s", (_name, chain) => {
    for (const [i, lower] of chain.entries()) {
      expect(compareVersions(lower, lower)).toBe(0);
      for (const higher of chain.slice(i + 1)) {
        expect(compareVersions(higher, lower), `${higher} > ${lower}`).toBeGreaterThan(0);
        expect(compareVersions(lower, higher), `${lower} < ${higher}`).toBeLessThan(0);
      }
    }
  });

  it("ranks a final release above its own pre-releases and a pre-release above the previous patch", () => {
    expect(compareVersions("3.1.2", "3.1.2-rc.1")).toBeGreaterThan(0);
    expect(compareVersions("3.1.2-rc.2", "3.1.2-rc.1")).toBeGreaterThan(0);
    expect(compareVersions("3.1.2-dev", "3.1.1")).toBeGreaterThan(0);
    expect(compareVersions("3.1.2-dev.1", "3.1.1")).toBeGreaterThan(0);
    // update_version.py's development stamp sorts below the release candidate it precedes.
    expect(compareVersions("3.1.2-dev.9", "3.1.2-rc.1")).toBeLessThan(0);
  });

  it("ignores build metadata (§10) and still treats a missing part as 0", () => {
    expect(compareVersions("3.1.2+build.7", "3.1.2")).toBe(0);
    expect(compareVersions("3.1.2-rc.1+exp.sha.5114f85", "3.1.2-rc.1")).toBe(0);
    expect(compareVersions("3.1", "3.1.0")).toBe(0);
  });
});

describe("the release checker on a pre-release build", () => {
  it("offers the final release to its release candidate and dev builds", async () => {
    for (const current of ["3.1.2-rc.1", "3.1.2-dev.1"]) {
      const answer = await createUpdateChecker({ current, enabled: true, fetchImpl: feed("v3.1.2") })();
      expect(answer).toMatchObject({ current, latest: "3.1.2", available: true, error: null, prompt: true });
    }
  });

  it("does not offer an older release to a newer pre-release", async () => {
    const answer = await createUpdateChecker({ current: "3.1.2-dev.1", enabled: true, fetchImpl: feed("v3.1.1") })();
    expect(answer).toMatchObject({ latest: "3.1.1", available: false, error: null });
  });

  it("never offers a pre-release tag from the feed", async () => {
    const answer = await createUpdateChecker({ current: "3.1.2", enabled: true, fetchImpl: feed("v3.1.3-rc.1") })();
    expect(answer).toMatchObject({ latest: null, available: false, prompt: false });
    expect(answer.error).toMatch(/did not name a published version/);
  });
});

describe("a disabled check names its real reason", () => {
  it("TIT_UPDATE_CHECK=0 on a packaged app is not called a development build", async () => {
    const env = { TIT_UPDATE_CHECK: "0" };
    expect(updateChecksEnabled(env, true)).toBe(false);
    const reason = updateCheckOffReason(env, true);
    expect(reason).toMatch(/TIT_UPDATE_CHECK=0/);
    expect(reason).not.toMatch(/development/);
    const fetchImpl = feed("v9.9.9");
    const answer = await createUpdateChecker({ current: "3.1.1", enabled: false, offReason: reason, fetchImpl })(true);
    expect(answer).toEqual({ current: "3.1.1", latest: null, available: false, url: null, error: reason, prompt: false });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("an unpackaged run is a development build; a packaged automated run says so", () => {
    expect(updateCheckOffReason({}, false)).toBe("Update checks are off in development builds.");
    expect(updateCheckOffReason({ TIT_E2E_TOKEN: "mock-token" }, true)).toMatch(/automated/);
    expect(updateCheckOffReason({ TIT_E2E_OFFSCREEN: "1" }, true)).toMatch(/automated/);
  });

  it("has no reason on a packaged app, or when TIT_UPDATE_CHECK=1 forces the check on", () => {
    expect(updateCheckOffReason({}, true)).toBeNull();
    expect(updateCheckOffReason({ TIT_UPDATE_CHECK: "1" }, false)).toBeNull();
    // Forced on outranks the automated-run rule: the app-update e2e spec points the feed at a fixture.
    expect(updateCheckOffReason({ TIT_UPDATE_CHECK: "1", TIT_E2E_TOKEN: "t" }, true)).toBeNull();
  });
});

describe("the app's own checker (what main/index.ts builds)", () => {
  /** The GitHub REST endpoint for a repository's latest published release. */
  const GITHUB_LATEST = "https://api.github.com/repos/idossha/TI-Toolbox/releases/latest";

  it("answers TIT_UPDATE_CHECK=0 on a packaged app with that reason, without a request", async () => {
    const fetchImpl = feed("v9.9.9");
    const answer = await createAppUpdateChecker({ TIT_UPDATE_CHECK: "0" }, true, "3.1.1", fetchImpl)(true);
    expect(answer).toMatchObject({ current: "3.1.1", latest: null, available: false, prompt: false });
    expect(answer.error).toMatch(/TIT_UPDATE_CHECK=0/);
    expect(answer.error).not.toMatch(/development/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("calls an unpackaged run a development build, without a request", async () => {
    const fetchImpl = feed("v9.9.9");
    const answer = await createAppUpdateChecker({}, false, "3.1.1", fetchImpl)(true);
    expect(answer.error).toBe("Update checks are off in development builds.");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("asks GitHub's latest-release endpoint on a packaged app, or TIT_UPDATE_FEED_URL when set", async () => {
    const fromGithub = feed("v3.1.2");
    expect(await createAppUpdateChecker({}, true, "3.1.2-rc.1", fromGithub)()).toMatchObject({ latest: "3.1.2", available: true, error: null });
    expect(vi.mocked(fromGithub).mock.calls.map(([url]) => url)).toEqual([GITHUB_LATEST]);

    const fixture = "http://127.0.0.1:9/latest.json";
    const fromFixture = feed("v3.1.2");
    await createAppUpdateChecker({ TIT_UPDATE_FEED_URL: fixture }, true, "3.1.1", fromFixture)();
    expect(vi.mocked(fromFixture).mock.calls.map(([url]) => url)).toEqual([fixture]);
  });
});
