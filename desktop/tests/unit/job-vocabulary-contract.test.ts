/**
 * The vocabularies the desktop app duplicates from the server agree with the server.
 *
 * What it pins: job kinds, job states and optional-panel ids are typed out by hand on both sides
 * (a TS string array cannot be generated from a schema). When they drift, nothing errors: a kind
 * missing from the Jobs filter is simply unfilterable, a state the main process reads as "still
 * running" blocks a quit forever, and a panel id the server rejects never reaches the nav. Before
 * 2026-10-22 `JOB_KIND_LABELS` still named `recip` and `report`, which are not job kinds.
 *
 * Where the expected values come from: never from the desktop code under test. Job kinds and
 * states are the `JobKind`/`JobState` enums of `contracts/openapi.yaml` (parsed with `yaml`) and
 * the tuples in `tit/jobs/spec.py`; terminal states are `tit/jobs/spec.py::TERMINAL_STATES`; the
 * config keys `jobTarget` reads must exist in `contracts/generated/config.schema.json` under the
 * class `x-kind-classes` names for that kind; panel ids are `_VALID_PANELS` in
 * `tit/server/routes/settings.py` and the `pages/panel-<id>/index.tsx` directories. Python sources
 * are read off disk as text. Every parser has a self-test that plants an extra element in a copy
 * of the source and must see it. The server's error-type taxonomy is checked from the Python side
 * (`tests/test_job_error_taxonomy_contract.py`). 2026-10-22.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { activeJobIds } from "../../src/shared/quitPlan";
import { JOB_KIND_LABELS, jobTarget, observeTransition } from "../../src/shared/jobNotifications";
import { JOB_KINDS, JOB_STATES, TERMINAL_STATES } from "../../src/renderer/app/jobs-rail/api";
import { RESULTS_KINDS } from "../../src/renderer/pages/overview/recentModel";

const REPO = resolve(__dirname, "../../..");
const DESKTOP = resolve(__dirname, "../..");
const read = (path: string) => readFileSync(resolve(REPO, path), "utf8");
const sorted = (values: Iterable<string>) => [...values].sort();

// ── parsers over source text (each self-tested below) ───────────────────────────────────────────

/** The string items of a Python `NAME: tuple[str, ...] = (...)` or `NAME = frozenset({...})` literal. */
function pythonStrings(source: string, name: string): string[] {
  const match = new RegExp(`^${name}\\b[^=\\n]*=\\s*(?:frozenset\\(\\s*)?[({]([\\s\\S]*?)[)}]`, "m").exec(source);
  if (!match) throw new Error(`${name} not found`);
  return [...match[1]!.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
}

/** The members of `export type PanelId = | "a" | "b";`. */
function panelIdUnion(source: string): string[] {
  const match = /export type PanelId =([^;]+);/.exec(source);
  if (!match) throw new Error("PanelId not found");
  return [...match[1]!.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
}

/** The keys of the `BY_KIND` object literal in `app/jobs/invalidation.ts`. */
function byKindKeys(source: string): string[] {
  const match = /const BY_KIND[^=]*=\s*\{([\s\S]*?)\n\};/.exec(source);
  if (!match) throw new Error("BY_KIND not found");
  return [...match[1]!.matchAll(/^\s+([a-z_]+):/gm)].map((m) => m[1]!);
}

const openapi = parse(read("contracts/openapi.yaml")) as { components: { schemas: Record<string, { enum?: string[] }> } };
const contractKinds = openapi.components.schemas.JobKind!.enum!;
const contractStates = openapi.components.schemas.JobState!.enum!;
const specPy = read("tit/jobs/spec.py");
const serverKinds = pythonStrings(specPy, "JOB_KINDS");
const serverStates = pythonStrings(specPy, "JOB_STATES");
const serverTerminal = pythonStrings(specPy, "TERMINAL_STATES");
const validPanels = pythonStrings(read("tit/server/routes/settings.py"), "_VALID_PANELS");

describe("the parsers read what they claim (planted-element self-tests)", () => {
  it("each sees an element planted in a copy of its source", () => {
    expect(pythonStrings(specPy.replace('JOB_KINDS: tuple[str, ...] = (\n', 'JOB_KINDS: tuple[str, ...] = (\n    "planted",\n'), "JOB_KINDS")).toContain("planted");
    const settingsPy = read("tit/server/routes/settings.py");
    expect(pythonStrings(settingsPy.replace('"source",', '"source",\n        "quick-notes",'), "_VALID_PANELS")).toContain("quick-notes");
    const shared = readFileSync(resolve(DESKTOP, "src/renderer/pages/panels/_shared.ts"), "utf8");
    expect(panelIdUnion(shared.replace('| "caps";', '| "caps"\n  | "planted";'))).toContain("planted");
    const invalidation = readFileSync(resolve(DESKTOP, "src/renderer/app/jobs/invalidation.ts"), "utf8");
    expect(byKindKeys(invalidation.replace("  tools: [],", "  tools: [],\n  planted: [],"))).toContain("planted");
  });

  it("finds a non-empty list in every real source", () => {
    for (const list of [contractKinds, contractStates, serverKinds, serverStates, serverTerminal, validPanels]) expect(list.length).toBeGreaterThan(0);
    expect(serverKinds).toContain("sim");
    expect(serverStates).toContain("queued");
  });
});

describe("job kinds", () => {
  it("the desktop's kind list equals the contract's JobKind enum and the server's JOB_KINDS", () => {
    expect(sorted(JOB_KINDS)).toEqual(sorted(contractKinds));
    expect(sorted(serverKinds)).toEqual(sorted(contractKinds));
  });

  it("every job kind has a notification label, and nothing that is not a kind has one", () => {
    expect(sorted(Object.keys(JOB_KIND_LABELS))).toEqual(sorted(contractKinds));
  });

  it("the kinds Overview sends to Results and the kinds job completion invalidates are real kinds", () => {
    for (const kind of RESULTS_KINDS) expect(contractKinds).toContain(kind);
    const keys = byKindKeys(readFileSync(resolve(DESKTOP, "src/renderer/app/jobs/invalidation.ts"), "utf8"));
    expect(keys.length).toBeGreaterThan(10);
    // `report` (removed 2026-09-28) and `recip` (never on main) are known leftovers in a file this
    // package does not own; any other key outside JobKind fails here.
    const KNOWN_STALE = ["recip", "report"];
    expect(keys.filter((k) => !contractKinds.includes(k) && !KNOWN_STALE.includes(k))).toEqual([]);
  });
});

describe("job states", () => {
  it("the desktop's state list equals the contract's JobState enum and the server's JOB_STATES", () => {
    expect(sorted(JOB_STATES)).toEqual(sorted(contractStates));
    expect(sorted(serverStates)).toEqual(sorted(contractStates));
  });

  it("the desktop's terminal states are the server's", () => {
    expect(sorted(TERMINAL_STATES)).toEqual(sorted(serverTerminal));
  });

  it("quitting asks about exactly the jobs in a non-terminal state", () => {
    const jobs = contractStates.map((state) => ({ id: `job-${state}`, state }));
    const nonTerminal = contractStates.filter((state) => !serverTerminal.includes(state));
    expect(nonTerminal.length).toBeGreaterThan(0);
    expect(sorted(activeJobIds(jobs))).toEqual(sorted(nonTerminal.map((state) => `job-${state}`)));
  });

  it("a banner fires on the move from a non-terminal state into each terminal state, and never otherwise", () => {
    for (const from of contractStates) {
      for (const to of contractStates) {
        const seen = new Map([["j", from]]);
        const fires = !serverTerminal.includes(from) && serverTerminal.includes(to);
        expect(observeTransition(seen, "j", to), `${from} -> ${to}`).toBe(fires);
      }
    }
  });
});

describe("the config keys a notification names exist in each kind's config class", () => {
  const schema = JSON.parse(read("contracts/generated/config.schema.json")) as {
    $defs: Record<string, { properties?: Record<string, { items?: { $ref?: string } }> }>;
    "x-kind-classes": Record<string, string>;
  };
  const props = (cls: string) => Object.keys(schema.$defs[cls]?.properties ?? {});
  const classOf = (kind: string) => schema["x-kind-classes"][kind]!;

  it("sim: montages[].display_name / name", () => {
    expect(props(classOf("sim"))).toContain("montages");
    const ref = schema.$defs[classOf("sim")]!.properties!.montages!.items!.$ref!;
    const montage = ref.replace("#/$defs/", "");
    expect(props(montage)).toEqual(expect.arrayContaining(["name", "display_name"]));
    // …and those are the keys `jobTarget` reads: display_name first.
    expect(jobTarget("sim", { montages: [{ name: "n", display_name: "Shown" }] })).toBe("montage Shown");
    expect(jobTarget("sim", { montages: [{ name: "n" }] })).toBe("montage n");
  });

  it("analyzer: region, then simulation", () => {
    expect(props(classOf("analyzer"))).toEqual(expect.arrayContaining(["region", "simulation"]));
    expect(jobTarget("analyzer", { region: ["L_Insula", "R_Insula"], simulation: "s" })).toBe("L_Insula+R_Insula");
    expect(jobTarget("analyzer", { simulation: "s" })).toBe("s");
  });

  it("ex and mex: run_name, then roi_name", () => {
    for (const kind of ["ex", "mex"]) {
      expect(props(classOf(kind))).toEqual(expect.arrayContaining(["run_name", "roi_name"]));
      expect(jobTarget(kind, { run_name: "R", roi_name: "x.csv" })).toBe("R");
      expect(jobTarget(kind, { roi_name: "Thalamus.csv" })).toBe("Thalamus");
    }
  });

  it("flex (all three kinds): the output folder's name", () => {
    for (const kind of ["flex", "flex_adaptive", "flex_pareto"]) {
      expect(props(classOf(kind))).toContain("output_folder");
      expect(jobTarget(kind, { output_folder: "/mnt/p/derivatives/SimNIBS/sub-1/flex-search/run1/" })).toBe("run1");
    }
  });
});

describe("optional panel ids", () => {
  const sharedTs = readFileSync(resolve(DESKTOP, "src/renderer/pages/panels/_shared.ts"), "utf8");
  const pageDirs = readdirSync(resolve(DESKTOP, "src/renderer/pages"))
    .filter((name) => name.startsWith("panel-") && existsSync(resolve(DESKTOP, "src/renderer/pages", name, "index.tsx")))
    .map((name) => name.replace(/^panel-/, ""));

  it("PanelId, the server's _VALID_PANELS and the panel page directories are one set", () => {
    expect(pageDirs.length).toBeGreaterThan(0);
    expect(sorted(panelIdUnion(sharedTs))).toEqual(sorted(validPanels));
    expect(sorted(pageDirs)).toEqual(sorted(validPanels));
  });

  it("the mock server's seeded panels are ids the real server accepts", () => {
    const seed = JSON.parse(readFileSync(resolve(DESKTOP, "tests/fixtures/settings_seed.json"), "utf8")) as { panels: string[] };
    expect(seed.panels.length).toBeGreaterThan(0);
    for (const id of seed.panels) expect(validPanels).toContain(id);
  });
});
