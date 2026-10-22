/**
 * Dataset 000's real catalog through the real desktop builders: what the Simulator, the Analyzer
 * field list and the Ex/mEx leadfield join would build from every real montage, flex run,
 * free-hand placement, simulation and leadfield is physically and contractually right.
 *
 * Input: `desktop/tests/fixtures/realdata/dataset000_catalog.json`, written from a read-only
 * Dataset 000 copy by `dev/regen_desktop_realdata_fixture.py` and checked current by
 * `tests/test_desktop_realdata_snapshot.py` (which skips with a reason when the dataset is absent).
 *
 * Expected values come from outside the builders: the server's rules (`SimulationConfig`'s pair
 * count and `required` currents, typed out below), physics (a current is > 0; two pads are distinct
 * points on a scalp whose radius is 50–130 mm — the flex audit measured 75–114 mm, montage
 * electrodes 17–127 mm apart), the flex convention (the two channels share 2 × current_mA, or
 * ratio_total_mA) and the analyzer's field registry.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { OPTIMIZED, flexCurrents, placementsFor } from "../../src/renderer/pages/simulator/FlexTab";
import type { FlexRun } from "../../src/renderer/pages/simulator/api";
import { defaultCurrents, defaultCurrentsFor, defaultJobSettings, isRunnableRow, type MontageKind, type SelectedRow } from "../../src/renderer/pages/simulator/types";
import { FIELD_REGISTRY, fieldSpecForName } from "../../src/renderer/pages/analyzer/fields";
import { electrodesForNet, leadfieldPathFor, netKey } from "../../src/renderer/pages/optimizer/nets";
import type { EegNet, Leadfield } from "../../src/renderer/pages/optimizer/api";

type Xyz = [number, number, number];
interface Snapshot {
  electrodes: Record<string, string[]>;
  montages: Record<string, Record<"uni_polar" | "multi_polar", Record<string, [string, string][]>>>;
  subjects: Record<
    string,
    {
      eeg_nets: string[];
      montage_electrode_positions: Record<string, Record<string, Xyz>>;
      flex_runs: { name: string; manifest: { current_mA?: number; current_split?: number[] | null; ratio_total_mA?: number | null }; mappings: { eeg_net: string; pairs: [string, string][] }[]; optimized: [Xyz, Xyz][] | null }[];
      freehand: { name: string; electrode_positions: { label?: string; x: number; y: number; z: number }[] }[];
      leadfields: Leadfield[];
      simulations: { name: string; fields: string[] }[];
    }
  >;
}

const SNAPSHOT = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "realdata", "dataset000_catalog.json"), "utf8"),
) as Snapshot;
const params = defaultJobSettings() as GlobalParams;
const SUBJECTS = Object.entries(SNAPSHOT.subjects);

/** SimulationConfig: 2 pairs (TI) or an even count from 4 (mTI); TI takes 2 currents, mTI one per pair. */
const serverAcceptsPairs = (n: number) => n === 2 || (n >= 4 && n % 2 === 0);
const serverRequired = (n: number) => (n === 2 ? 2 : n);
const dist = (a: Xyz, b: Xyz) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
function minDistance(points: Xyz[]): number {
  let min = Infinity;
  for (let i = 0; i < points.length; i += 1) for (let j = i + 1; j < points.length; j += 1) min = Math.min(min, dist(points[i]!, points[j]!));
  return min;
}

/** The job a row builds, with the invariants every real job must meet. */
function expectRealJob(row: SelectedRow, pairs: number, where: string) {
  expect(serverAcceptsPairs(pairs), `${where}: pair count ${pairs}`).toBe(true);
  expect(isRunnableRow(row), where).toBe(true);
  const config = buildSimulationConfig(row, params);
  const intensities = config.intensities as number[];
  expect(intensities, where).toHaveLength(serverRequired(pairs));
  for (const v of intensities) expect(v, where).toBeGreaterThan(0);
  const montage = (config.montages as { electrode_pairs: unknown[]; eeg_net: string | null; mode: string }[])[0]!;
  expect(montage.electrode_pairs, where).toHaveLength(pairs);
  return { config, montage, intensities };
}

describe("Dataset 000 snapshot", () => {
  it("is not empty: montages, flex runs, a free-hand set, simulations and leadfields to check", () => {
    const montages = Object.values(SNAPSHOT.montages).flatMap((b) => [...Object.values(b.uni_polar), ...Object.values(b.multi_polar)]);
    expect(montages.length).toBeGreaterThanOrEqual(20);
    expect(SUBJECTS.flatMap(([, s]) => s.flex_runs).length).toBeGreaterThanOrEqual(3);
    expect(SUBJECTS.flatMap(([, s]) => s.freehand).length).toBeGreaterThanOrEqual(1);
    expect(SUBJECTS.flatMap(([, s]) => s.simulations).length).toBeGreaterThanOrEqual(5);
    expect(SUBJECTS.flatMap(([, s]) => s.leadfields).length).toBeGreaterThanOrEqual(1);
  });
});

/**
 * Caps on disk whose electrodes collapsed onto each other when they were warped before the
 * cap-transform fix (sub-CHN and sub-LA, dated Sep 2026; testmap audit_caps-electrodes §3: 61 of
 * BioSemi-128-A1's electrodes have a neighbour < 2 mm away). A label montage carries labels only,
 * so the Simulator cannot see this; refusing a job on a collapsed cap is the caps package's (p07).
 * Their montages are checked for everything but separation, and the finding itself is pinned
 * below so this list cannot outlive it.
 */
const STALE_CAPS = new Set(["CHN/BioSemi-128-A1.csv", "LA/BioSemi-128-A1.csv"]);

describe("every saved montage, on every subject that has its net, builds a job the server takes", () => {
  const cases = SUBJECTS.flatMap(([sid, s]) =>
    s.eeg_nets.flatMap((net) =>
      (["uni_polar", "multi_polar"] as MontageKind[]).flatMap((kind) =>
        Object.entries(SNAPSHOT.montages[net]?.[kind] ?? {}).map(([name, pairs]) => ({ sid, net, kind, name, pairs })),
      ),
    ),
  );

  it("there are real (subject, net, montage) rows to check", () => {
    expect(cases.length).toBeGreaterThanOrEqual(50);
  });

  it.each(cases.map((c) => [`sub-${c.sid} ${c.net} ${c.kind} ${c.name}`, c] as const))("%s", (where, { sid, net, kind, name, pairs }) => {
    // The row MontageManager.setRowMontage makes when this montage is picked.
    const row: SelectedRow = { id: "r", subjectId: sid, source: "montage", eegNet: net, kind, name, pairs, currents: defaultCurrentsFor(kind, pairs.length) };
    const labels = new Set(SNAPSHOT.electrodes[net]);
    for (const label of pairs.flat()) expect(labels.has(label), `${where}: ${label} on ${net}`).toBe(true);
    expect(new Set(pairs.flat()).size, `${where}: distinct electrodes`).toBe(pairs.length * 2);
    const { montage } = expectRealJob(row, pairs.length, where);
    expect(montage).toMatchObject({ mode: "net", eeg_net: net, electrode_pairs: pairs });
    // Two pads at least 5 mm apart on this subject's own cap.
    const xyz = SNAPSHOT.subjects[sid]!.montage_electrode_positions[net]!;
    for (const label of pairs.flat()) expect(xyz[label], `${where}: ${label} has a position`).toBeDefined();
    if (!STALE_CAPS.has(`${sid}/${net}`)) expect(minDistance(pairs.flat().map((l) => xyz[l]!)), where).toBeGreaterThanOrEqual(5);
  });

  it("the stale caps really are collapsed (a montage's two pads on one point), and only they are", () => {
    const collapsed = new Set(
      cases.filter((c) => minDistance(c.pairs.flat().map((l) => SNAPSHOT.subjects[c.sid]!.montage_electrode_positions[c.net]![l]!)) < 5).map((c) => `${c.sid}/${c.net}`),
    );
    expect(collapsed).toEqual(STALE_CAPS);
  });
});

describe("every flex run builds a job at its own XYZ and at every mapped cap", () => {
  const runs = SUBJECTS.flatMap(([sid, s]) => s.flex_runs.map((run) => ({ sid, run })));

  it.each(runs.map((c) => [`sub-${c.sid} ${c.run.name}`, c] as const))("%s", (where, { sid, run }) => {
    const flexRun = run as unknown as FlexRun;
    const placements = placementsFor(flexRun);
    // Every run writes electrode_positions.json, so the optimised placement is always offered.
    expect(placements.some((p) => p.value === OPTIMIZED), where).toBe(true);
    expect(placements).toHaveLength(run.mappings.length + 1);
    for (const p of run.optimized!.flat()) {
      expect(p.every(Number.isFinite), where).toBe(true);
      const r = Math.hypot(...p);
      expect(r, `${where}: |p| = ${r.toFixed(1)} mm`).toBeGreaterThanOrEqual(50);
      expect(r, `${where}: |p| = ${r.toFixed(1)} mm`).toBeLessThanOrEqual(130);
    }
    expect(minDistance(run.optimized!.flat()), where).toBeGreaterThanOrEqual(5);

    for (const placement of placements) {
      const pairs = placement.pairs?.length ?? placement.xyzPairs?.length ?? 0;
      const currents = flexCurrents(flexRun, pairs);
      // MontageManager.setRowFlexRun / applyFlexPlacement.
      const row: SelectedRow = {
        id: "r", subjectId: sid, source: "flex", name: run.name,
        eegNet: placement.value === OPTIMIZED ? undefined : placement.value,
        pairs: placement.pairs, xyzPairs: placement.xyzPairs, currents,
      };
      const { montage, intensities } = expectRealJob(row, pairs, `${where} ${placement.label}`);
      expect(montage.mode).toBe(placement.value === OPTIMIZED ? "flex_free" : "flex_mapped");
      // The run's own split is what runs, and the channels share the run's total.
      expect(intensities).toEqual(currents.split(",").map(Number));
      const total = run.manifest.ratio_total_mA ?? 2 * run.manifest.current_mA!;
      expect(intensities.reduce((a, b) => a + b, 0)).toBeCloseTo(total, 9);
    }
  });
});

describe("every free-hand placement builds the job it was saved as", () => {
  const sets = SUBJECTS.flatMap(([sid, s]) => s.freehand.map((set) => ({ sid, set })));

  it.each(sets.map((c) => [`sub-${c.sid} ${c.set.name}`, c] as const))("%s", (where, { sid, set }) => {
    const points = set.electrode_positions.map((p) => [p.x, p.y, p.z] as Xyz);
    // MontageManager.setRowFreehand: consecutive positions are a pair.
    const xyzPairs = Array.from({ length: points.length / 2 }, (_, i) => [points[2 * i]!, points[2 * i + 1]!] as [Xyz, Xyz]);
    const row: SelectedRow = { id: "r", subjectId: sid, source: "freehand", name: set.name, xyzPairs, currents: defaultCurrents(xyzPairs.length) };
    const { montage } = expectRealJob(row, xyzPairs.length, where);
    expect(montage.mode).toBe("freehand");
    expect(montage.electrode_pairs).toEqual(xyzPairs);
    for (const p of points) expect(Math.hypot(...p), where).toBeGreaterThanOrEqual(50);
    expect(minDistance(points), where).toBeGreaterThanOrEqual(5);
  });
});

describe("analyzer field options for every real simulation", () => {
  const sims = SUBJECTS.flatMap(([sid, s]) => s.simulations.map((sim) => ({ sid, sim })));
  const analysable = new Set([...FIELD_REGISTRY.map((f) => f.name), "mTI_max"]);

  it.each(sims.map((c) => [`sub-${c.sid} ${c.sim.name}`, c] as const))("%s", (where, { sim }) => {
    // AnalysisFieldSelect offers the catalog fields the registry knows. Every field the catalog
    // reports is one of those, or the carrier magnitude magnE — never a mangled token ("peak",
    // "sar", "avg") that would silently drop a computed field from the list.
    const offered = sim.fields.filter((f) => fieldSpecForName(f) !== undefined);
    for (const f of offered) expect(analysable.has(f), where).toBe(true);
    expect(sim.fields.filter((f) => !offered.includes(f) && f !== "magnE"), where).toEqual([]);
    expect(offered.length, `${where}: something to analyse`).toBeGreaterThan(0);
  });
});

describe("every computed leadfield joins its subject's cap", () => {
  const leadfields = SUBJECTS.flatMap(([sid, s]) => s.leadfields.map((lf) => ({ sid, s, lf })));

  it.each(leadfields.map((c) => [`sub-${c.sid} ${c.lf.net}`, c] as const))("%s", (where, { s, lf }) => {
    const nets: EegNet[] = s.eeg_nets.map((name) => ({ name, electrodes: SNAPSHOT.electrodes[name]!, n: SNAPSHOT.electrodes[name]!.length }) as EegNet);
    // The leadfield strip selects the bare name; the path and the electrode list must both resolve.
    expect(leadfieldPathFor(s.leadfields, netKey(lf.net)), where).toBe(lf.exists ? lf.path : null);
    expect(leadfieldPathFor(s.leadfields, `${netKey(lf.net)}.csv`), where).toBe(lf.exists ? lf.path : null);
    expect(electrodesForNet(nets, netKey(lf.net)).length, `${where}: cap electrodes`).toBeGreaterThan(0);
  });
});
