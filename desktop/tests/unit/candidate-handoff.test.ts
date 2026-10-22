/**
 * "Use in Simulator" submits exactly what the server resolved for the candidate.
 *
 * The fixtures are the real `tit.opt.candidate_catalog.candidate_detail` output for a synthetic
 * project (`dev/make_contract_fixtures.py`; `tests/test_contract_fixtures_fresh.py` fails when
 * they go stale): a flex 2-channel run with recorded electrode poses and a head-mesh identity, an
 * ex net 2-pair run and an mEx 4-pair run. The spec is the identity: an unedited candidate row
 * builds the very `simulation_config` the server answered, so nothing the server resolved (the
 * `candidate_<sha16>` name, the poses, the provenance, the currents, the geometry) is lost or
 * re-defaulted on the way to `POST /api/plan/sim`.
 *
 * The frontier cases are hand-derived from Pareto dominance over (ROI mean, the background axis):
 * a non-ROI metric is better lower, the contrast ratio is better higher.
 *
 * Reproduce: `.venv/bin/python dev/make_contract_fixtures.py && cd desktop && npx vitest run
 * tests/unit/candidate-handoff.test.ts`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { frontierIds, type Candidate } from "../../src/renderer/pages/results/candidates/model";
import { buildSimulationConfig } from "../../src/renderer/pages/simulator/buildConfig";
import { candidateMetricsChanged, candidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import { defaultJobSettings } from "../../src/renderer/pages/simulator/types";

interface Fixture {
  request: { subject: string; kind: "flex" | "ex" | "mex"; run: string; candidate_id: string };
  response: { candidate: Candidate; simulation_config: Record<string, unknown> };
}
const load = (kind: string): Fixture =>
  JSON.parse(readFileSync(join(__dirname, "..", "fixtures", "contracts", `candidate_detail_${kind}.json`), "utf8")) as Fixture;

function handoff({ request, response }: Fixture) {
  return { id: request.candidate_id, subject: request.subject, kind: request.kind, run: request.run, config: structuredClone(response.simulation_config) };
}
const montageOf = (config: Record<string, unknown>) => (config.montages as Record<string, unknown>[])[0]!;

describe("the real candidate_detail output round-trips through the Simulator handoff", () => {
  for (const kind of ["flex", "ex", "mex"]) {
    it(`${kind}: an unedited candidate builds the server's simulation_config exactly`, () => {
      const fixture = load(kind);
      const row = candidateRow(handoff(fixture));
      const built = buildSimulationConfig(row, defaultJobSettings());
      // The one representational difference: the page leaves out `tissue_conductivities` when
      // there are no overrides, where the server wrote `null`. `SimulationConfig`'s default for
      // the field is `None`, so the two deserialize to the same config; anything else differing
      // fails below.
      const expected = structuredClone(fixture.response.simulation_config);
      expect(expected.tissue_conductivities).toBeNull();
      expect("tissue_conductivities" in built).toBe(false);
      delete expected.tissue_conductivities;
      expect(built).toStrictEqual(expected);
      expect(candidateMetricsChanged(row)).toBe(false);
    });
  }

  it("names the row after the server's montage, never candidate_<id>", () => {
    for (const kind of ["flex", "ex", "mex"]) {
      const fixture = load(kind);
      const row = candidateRow(handoff(fixture));
      const name = montageOf(fixture.response.simulation_config).name as string;
      expect(name).toMatch(/^candidate_[0-9a-f]{16}$/);
      expect(row.name).toBe(name);
      expect(row.name).not.toBe(`candidate_${fixture.request.candidate_id}`);
    }
  });

  it("reads each kind as its source: flex as placed coordinates, ex and mEx as cap labels", () => {
    const flex = candidateRow(handoff(load("flex")));
    expect(flex.source).toBe("flex");
    expect(flex.pairs).toBeUndefined();
    expect(flex.xyzPairs).toHaveLength(2); // two channels, the flex run's spec
    expect(flex.kind).toBe("uni_polar");
    // The recorded carriers are 0.7 and 1.3 mA (the generator's input).
    expect(flex.currents).toBe("0.7,1.3");

    const ex = candidateRow(handoff(load("ex")));
    expect(ex.source).toBe("montage");
    expect(ex.kind).toBe("uni_polar");
    expect(ex.pairs).toEqual([["E020", "E074"], ["E101", "E133"]]); // the CSV's best row
    expect(ex.eegNet).toBe("GSN-HydroCel-185.csv");
    expect(ex.currents).toBe("1.5,0.5");

    const mex = candidateRow(handoff(load("mex")));
    expect(mex.kind).toBe("multi_polar");
    expect(mex.pairs).toHaveLength(4);
    // mEx drives every pair at the one configured current (1 mA in run_config.json).
    expect(mex.currents).toBe("1,1,1,1");
  });

  it("an edited current is a changed candidate, and only the current moves", () => {
    const fixture = load("flex");
    const row = candidateRow(handoff(fixture));
    const edited = { ...row, currents: "0.7,1.1" };
    expect(candidateMetricsChanged(edited)).toBe(true);
    const built = buildSimulationConfig(edited, defaultJobSettings());
    expect(built.intensities).toEqual([0.7, 1.1]);
    expect(montageOf(built)).toStrictEqual(montageOf(fixture.response.simulation_config));
  });
});

const point = (id: string, roi: number, metric: "background_p95" | "contrast", value: number): Candidate => ({
  id, objective: null, objective_label: "", objective_direction: "minimize",
  metrics: { roi_mean: roi, [metric]: value }, metric_labels: {}, comparison_key: "k",
});

describe("frontierIds", () => {
  it("treats the contrast axis as higher-is-better", () => {
    // (roi, contrast): d (1.5, 3) is dominated by b (2, 4); a, b, c and e are not dominated.
    const points = [point("a", 1, "contrast", 5), point("b", 2, "contrast", 4), point("c", 3, "contrast", 1), point("d", 1.5, "contrast", 3), point("e", 0.5, "contrast", 6)];
    expect(new Set(frontierIds(points, "contrast"))).toEqual(new Set(["a", "b", "c", "e"]));
  });

  it("treats a background axis as lower-is-better", () => {
    // (roi, p95): b (2, 4) is dominated by a (3, 2); a and c (1, 1) are not.
    const points = [point("a", 3, "background_p95", 2), point("b", 2, "background_p95", 4), point("c", 1, "background_p95", 1)];
    expect(new Set(frontierIds(points, "background_p95"))).toEqual(new Set(["a", "c"]));
  });

  it("a single point is its own frontier", () => {
    expect([...frontierIds([point("only", 0.2, "contrast", 1.5)], "contrast")]).toEqual(["only"]);
  });

  it("points with no finite ROI mean or axis value have no frontier", () => {
    const points = [point("a", NaN, "contrast", 2), point("b", 1, "contrast", NaN), point("c", NaN, "contrast", NaN)];
    expect(frontierIds(points, "contrast").size).toBe(0);
  });
});
