// TI-Toolbox's own "is there a newer release?" check (ARCHITECTURE §5, decision 2026-10-09).
// One GitHub request per app process; the renderer never sees a throw.
import type { TitAppUpdate } from "../shared/tit-bridge";

export const RELEASE_FEED = "https://api.github.com/repos/idossha/TI-Toolbox/releases/latest";

/** SemVer §11.4: numeric identifiers numerically and below alphanumeric ones, which compare in ASCII. */
function compareIdentifiers(a: string, b: string): number {
  const numeric = /^\d+$/;
  if (numeric.test(a) && numeric.test(b)) return Number(a) - Number(b);
  if (numeric.test(a) !== numeric.test(b)) return numeric.test(a) ? -1 : 1;
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * SemVer 2.0.0 precedence of `x.y.z[-pre.release][+build]` (§11): positive when `a` is newer.
 * Missing core parts count as 0; a release outranks its own pre-releases ("3.1.2" > "3.1.2-rc.1"
 * > "3.1.2-dev.1" > "3.1.1"); build metadata is ignored (§10).
 */
export function compareVersions(a: string, b: string): number {
  const [leftCore = "", leftPre] = a.split("+", 1)[0]!.split(/-(.*)/s);
  const [rightCore = "", rightPre] = b.split("+", 1)[0]!.split(/-(.*)/s);
  const left = leftCore.split(".").map(Number);
  const right = rightCore.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference) return difference;
  }
  if (leftPre === undefined || rightPre === undefined) return (leftPre === undefined ? 1 : 0) - (rightPre === undefined ? 1 : 0);
  const leftIds = leftPre.split(".");
  const rightIds = rightPre.split(".");
  for (let index = 0; index < Math.min(leftIds.length, rightIds.length); index += 1) {
    const difference = compareIdentifiers(leftIds[index]!, rightIds[index]!);
    if (difference) return difference;
  }
  return leftIds.length - rightIds.length;
}

const DEVELOPMENT_BUILD = "Update checks are off in development builds.";

/**
 * Why the release check is off, or `null` when it runs. Packaged apps check; dev runs and
 * automated tests do not. `TIT_UPDATE_CHECK=1` forces it on (an e2e spec pointing
 * `TIT_UPDATE_FEED_URL` at a fixture), `=0` off.
 */
export function updateCheckOffReason(env: NodeJS.ProcessEnv, packaged: boolean): string | null {
  if (env.TIT_UPDATE_CHECK === "1") return null;
  if (env.TIT_UPDATE_CHECK === "0") return "Update checks are turned off (TIT_UPDATE_CHECK=0).";
  if (!packaged) return DEVELOPMENT_BUILD;
  if (env.TIT_E2E_TOKEN || env.TIT_E2E_OFFSCREEN) return "Update checks are off during automated tests.";
  return null;
}

/** Whether the release check runs: {@link updateCheckOffReason} found no reason to skip it. */
export function updateChecksEnabled(env: NodeJS.ProcessEnv, packaged: boolean): boolean {
  return updateCheckOffReason(env, packaged) === null;
}

type Lookup = Omit<TitAppUpdate, "prompt">;

async function lookupLatest(current: string, feedUrl: string, fetchImpl: typeof fetch): Promise<Lookup> {
  const none = { current, latest: null, available: false, url: null };
  let response: Response;
  try {
    response = await fetchImpl(feedUrl, {
      headers: { Accept: "application/vnd.github+json", "User-Agent": "TI-Toolbox" },
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return { ...none, error: "Couldn't reach GitHub to check for updates (offline?)." };
  }
  if (!response.ok) return { ...none, error: `Couldn't check for updates (GitHub answered HTTP ${response.status}).` };
  let body: { tag_name?: unknown; html_url?: unknown; draft?: unknown; prerelease?: unknown };
  try {
    body = (await response.json()) as typeof body;
  } catch {
    return { ...none, error: "Couldn't read the release feed." };
  }
  const latest = typeof body.tag_name === "string" ? /^v?(\d+\.\d+\.\d+)$/.exec(body.tag_name)?.[1] : undefined;
  // `/releases/latest` already skips drafts and prereleases; a fixture or proxy might not.
  if (!latest || body.draft === true || body.prerelease === true) return { ...none, error: "The release feed did not name a published version." };
  const url = typeof body.html_url === "string" && /^https?:\/\//.test(body.html_url) ? body.html_url : null;
  return { current, latest, available: compareVersions(latest, current) > 0, url, error: null };
}

/**
 * The bridge's `checkAppUpdate`. The first lookup is kept for the process lifetime; `force`
 * (Settings ▸ Check again) replaces it. `prompt` is true on exactly one answer per process —
 * the first that finds an update — so the load popup appears once per session, not once per
 * page load (the window reloads on every project switch).
 */
export function createUpdateChecker(options: { current: string; enabled: boolean; offReason?: string | null; feedUrl?: string; fetchImpl?: typeof fetch }) {
  const { current, enabled, offReason, feedUrl = RELEASE_FEED, fetchImpl = fetch } = options;
  let pending: Promise<Lookup> | undefined;
  let prompted = false;
  return async (force = false): Promise<TitAppUpdate> => {
    if (!enabled) return { current, latest: null, available: false, url: null, error: offReason || DEVELOPMENT_BUILD, prompt: false };
    if (force || !pending) pending = lookupLatest(current, feedUrl, fetchImpl);
    const result = await pending;
    const prompt = result.available && !prompted;
    if (prompt) prompted = true;
    return { ...result, prompt };
  };
}
