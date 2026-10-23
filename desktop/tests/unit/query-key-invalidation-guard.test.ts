/**
 * Every catalog query the outputs pages read is refreshed when a job finishes (p32,
 * `app/jobs/invalidation.ts`).
 *
 * Catalog reads never poll: `queriesAffectedBy(kind)` is the one place that says which query-key
 * prefixes a finished job may have changed. A key that is in no list keeps its first answer for
 * the session. That is how a re-run with Replace left the Results header on the old Intensity and
 * Created values (`results-file-text`), an analysis on its old key numbers
 * (`results-analysis-summary`), and a stats run opened while running on "This run produced no
 * results" after it succeeded (`results-group-stats`).
 *
 * The guard reads the pages' source off disk, so a new query on these pages has to be added to an
 * invalidation list, or to `STATIC_KEYS` below with the reason no job changes it.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { QueryClient, QueryObserver, type QueryKey } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { BY_KIND, invalidateForJobs, queriesAffectedBy } from "../../src/renderer/app/jobs/invalidation";
import { JOB_KINDS } from "../../src/renderer/app/jobs-rail/api";
import type { JobStatus } from "../../src/renderer/app/jobs/types";

const RENDERER = join(__dirname, "../../src/renderer");
const GUARDED_DIRS = ["pages/results", "pages/viewer", "pages/overview", "pages/jobs", "app/jobs-rail"];

/** Query-key prefixes on the guarded pages that no finished job changes, each with its reason. */
const STATIC_KEYS: Record<string, string> = {
  jobs: "the job list itself: the /ws/jobs stream and the pages' own submit/cancel/delete keep it fresh",
  job: "one job's record: same source as `jobs`, removed when the job is deleted",
  "job-log": "a job's log: its key carries live/final and it polls every 3 s while the job runs",
  "job-outputs": "a job's folder listing: its key carries the job's state and artifact count, so a finished job is a new key",
  "job-output-dir": "the folder a job's results live in: its key carries the job's state and artifact count, and it polls every 5 s while the job runs",
  "viewer-saved-scenes": "scenes the user saves in the Viewer, which invalidates it on every save and delete; no job writes them",
};

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

/**
 * The first element of every `queryKey:` in *text*: a literal array (`["x", …]`, possibly spread
 * over lines) or a call to a key factory declared in the same file (`function f(…) { return ["x", …] }`).
 * Any other form is returned in `unread` so the guard fails instead of skipping it.
 */
function queryKeyPrefixes(text: string): { prefixes: string[]; unread: string[] } {
  const prefixes: string[] = [];
  const unread: string[] = [];
  for (const m of text.matchAll(/queryKey:\s*([^,}\n]*)/g)) {
    const rest = text.slice((m.index ?? 0) + "queryKey:".length);
    const literal = /^\s*\[\s*"([^"]+)"/.exec(rest);
    if (literal) {
      prefixes.push(literal[1]!);
      continue;
    }
    const call = /^\s*([A-Za-z_$][\w$]*)\s*\(/.exec(rest);
    const body = call ? new RegExp(`function ${call[1]}\\b[^{]*\\{[^}]*?return \\[\\s*"([^"]+)"`).exec(text) : null;
    if (body) prefixes.push(body[1]!);
    else unread.push(m[0]);
  }
  return { prefixes, unread };
}

function scan(): { used: Map<string, string[]>; unread: string[] } {
  const used = new Map<string, string[]>();
  const unread: string[] = [];
  for (const dir of GUARDED_DIRS) {
    for (const file of sourceFiles(join(RENDERER, dir))) {
      const found = queryKeyPrefixes(readFileSync(file, "utf8"));
      const where = relative(RENDERER, file);
      for (const p of found.prefixes) used.set(p, [...(used.get(p) ?? []), where]);
      for (const u of found.unread) unread.push(`${where}: ${u}`);
    }
  }
  return { used, unread };
}

/** Prefixes some finished job invalidates, as whole one-element keys (`["x"]` matches `["x", …]`). */
function invalidatedPrefixes(): Set<string> {
  const out = new Set<string>();
  for (const kind of JOB_KINDS) {
    for (const key of queriesAffectedBy(kind)) if (key.length === 1 && typeof key[0] === "string") out.add(key[0]);
  }
  return out;
}

describe("query-key invalidation guard", () => {
  const { used, unread } = scan();

  it("reads every queryKey on the guarded pages", () => {
    expect(unread).toEqual([]);
    // The scan found the pages' own reads, so a broken regex cannot pass on an empty set.
    for (const key of ["results-simulations", "results-file-text", "results-analysis-summary", "results-group-stats", "viewer-tree", "job-log"]) {
      expect(used.has(key), key).toBe(true);
    }
  });

  it("every catalog query on Results, Viewer, Overview, Jobs and the jobs rail is refreshed by some finished job", () => {
    const invalidated = invalidatedPrefixes();
    const orphans = [...used.keys()].filter((k) => !invalidated.has(k) && !(k in STATIC_KEYS)).sort();
    expect(orphans, `query keys no job invalidates: ${orphans.map((k) => `${k} (${used.get(k)!.join(", ")})`).join("; ")}`).toEqual([]);
  });

  it("STATIC_KEYS names only keys the pages use and no job invalidates", () => {
    const invalidated = invalidatedPrefixes();
    for (const key of Object.keys(STATIC_KEYS)) {
      expect(used.has(key), `${key} is allowlisted but unused`).toBe(true);
      expect(invalidated.has(key), `${key} is allowlisted but also invalidated`).toBe(false);
    }
  });

  it("every invalidation entry is a job kind the server runs, and every job kind has its own entry", () => {
    expect(Object.keys(BY_KIND).filter((k) => !(JOB_KINDS as string[]).includes(k))).toEqual([]);
    expect((JOB_KINDS as string[]).filter((k) => !(k in BY_KIND))).toEqual([]);
  });
});

function finished(kind: string): JobStatus {
  return { id: `${kind}-1`, kind, state: "succeeded" } as unknown as JobStatus;
}

/**
 * A query observed the way the Results preview observes it, answering "v1" and then "v2". After
 * the job finishes, the observer must hold "v2": the query was refetched, not left on its cached
 * first answer.
 */
async function refreshedBy(kind: string, queryKey: QueryKey, staleTime: number): Promise<string | undefined> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let version = 1;
  const observer = new QueryObserver<string>(client, { queryKey, queryFn: async () => `v${version}`, staleTime });
  const unsubscribe = observer.subscribe(() => {});
  try {
    await expect.poll(() => observer.getCurrentResult().data).toBe("v1");
    version = 2;
    invalidateForJobs(client, [finished(kind)]);
    await expect.poll(() => observer.getCurrentResult().isFetching).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, 0));
    return observer.getCurrentResult().data;
  } finally {
    unsubscribe();
    client.clear();
  }
}

describe("a re-run with Replace refreshes what the Results preview shows", () => {
  // The key shapes are the ones `pages/results/index.tsx` builds; staleTime Infinity is what the
  // manifest reads use, 60 s is the app default (`main.tsx`).
  const SIM_CONFIG = ["results-file-text", "/mnt/p/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/documentation/config.json"];

  it("a simulation's recorded settings (documentation/config.json)", async () => {
    expect(await refreshedBy("sim", SIM_CONFIG, Infinity)).toBe("v2");
  });

  it("a flex run's summary.txt and an ex/mEx run's run_config.json", async () => {
    const flexSummary = ["results-file-text", "/mnt/p/derivatives/SimNIBS/sub-ernie/flex-search/run_a/summary.txt"];
    const exConfig = ["results-file-text", "/mnt/p/derivatives/SimNIBS/sub-ernie/ex-search/run_b/run_config.json"];
    expect(await refreshedBy("flex", flexSummary, Infinity)).toBe("v2");
    expect(await refreshedBy("ex", exConfig, Infinity)).toBe("v2");
    expect(await refreshedBy("mex", exConfig, Infinity)).toBe("v2");
  });

  it("an analysis's key numbers and its text files", async () => {
    expect(await refreshedBy("analyzer", ["results-analysis-summary", "ernie", "Thalamus", "sphere_roi"], 60_000)).toBe("v2");
    const csv = ["results-file-text", "/mnt/p/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Mesh/sphere_roi/results.csv"];
    expect(await refreshedBy("analyzer", csv, Infinity)).toBe("v2");
  });

  it("a group-statistics run opened while it was still running, and its log", async () => {
    expect(await refreshedBy("stats", ["results-group-stats", "group_comparison", "cmp_1"], 60_000)).toBe("v2");
    const log = ["results-file-text", "/mnt/p/derivatives/ti-toolbox/stats/group_comparison/cmp_1/permutation.log"];
    expect(await refreshedBy("stats", log, Infinity)).toBe("v2");
  });

  it("the Viewer resolves a re-run's files afresh", async () => {
    // `pages/viewer/index.tsx` keys a draft's resolution `["viewer-resolution", draftKey]`.
    for (const kind of ["sim", "flex", "ex", "analyzer"]) {
      expect(await refreshedBy(kind, ["viewer-resolution", "simulation|ernie|Thalamus"], Infinity), kind).toBe("v2");
    }
  });

  it("a job of an unrelated kind leaves a run's settings cached", async () => {
    // The lists are per kind: a finished leadfield must not refetch every open preview.
    expect(await refreshedBy("leadfield", SIM_CONFIG, Infinity)).toBe("v1");
  });
});
