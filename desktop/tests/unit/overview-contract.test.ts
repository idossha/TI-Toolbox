/**
 * The Overview page model reads a `build_overview` response the real server produced.
 *
 * `tests/fixtures/contracts/overview.json` is `tit.server.routes.overview.build_overview` over a
 * synthetic project with one subject of each kind (`dev/make_contract_fixtures.py`, kept fresh by
 * `tests/test_contract_fixtures_fresh.py`), so a server-side rename of a stage, a reason or a
 * presence field breaks this file, where the hand-written `fixtures/overview.json` (the mock's)
 * cannot. Every expectation below is derived by hand from the fixture's own `subjects` spec and
 * the documented rules -- not read back from the response:
 *
 * - preprocess needs raw MRI or staged sourcedata ("no raw MRI");
 * - simulator needs a head model ("no head model");
 * - optimizer needs a head model and a leadfield ("no leadfield", or "no head model" first);
 * - analyzer needs a simulation ("no simulations");
 * - the Ready filter is simulator-ready AND raw present (`isReady`);
 * - a queued job of the producing kind shows its column `pending` (pulsing), a failed newest job
 *   shows it `failed` (danger), staged-not-converted raw is `partial` (`notConverted`).
 *
 * Reproduce: `.venv/bin/python dev/make_contract_fixtures.py && cd desktop && npx vitest run
 * tests/unit/overview-contract.test.ts`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Overview, OverviewSubject } from "../../src/renderer/pages/overview/api";
import { blockedReason, isReady, notConverted, presenceCells, readyFor } from "../../src/renderer/pages/overview/model";
import { subjectRows } from "../../src/renderer/pages/results/useOutputs";

interface Fixture {
  subjects: Record<string, string>;
  jobs: { id: string; kind: string; state: string; subject_ids: string[] }[];
  catalog_subjects: string[];
  response: Overview;
}
const fixture = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "contracts", "overview.json"), "utf8"),
) as Fixture;
const row = (id: string): OverviewSubject => {
  const found = fixture.response.subjects.find((s) => s.id === id);
  if (!found) throw new Error(`the server did not list subject ${id}`);
  return found;
};
const cell = (id: string, key: string) => presenceCells(row(id)).find((c) => c.key === key)!;

type Stage = "preprocess" | "simulator" | "optimizer" | "analyzer";
/** subject -> stage -> the reason it is blocked (undefined = ready), from the spec and the rules. */
const EXPECTED: Record<string, Record<Stage, string | undefined>> = {
  full: { preprocess: undefined, simulator: undefined, optimizer: undefined, analyzer: undefined },
  m2monly: { preprocess: "no raw MRI", simulator: undefined, optimizer: "no leadfield", analyzer: "no simulations" },
  rawonly: { preprocess: undefined, simulator: "no head model", optimizer: "no head model", analyzer: "no simulations" },
  staged: { preprocess: undefined, simulator: "no head model", optimizer: "no head model", analyzer: "no simulations" },
  queued: { preprocess: undefined, simulator: "no head model", optimizer: "no head model", analyzer: "no simulations" },
  lffailed: { preprocess: "no raw MRI", simulator: undefined, optimizer: "no leadfield", analyzer: "no simulations" },
};

describe("Overview model over the real build_overview response", () => {
  it("lists exactly the subjects the project holds", () => {
    expect(Object.keys(fixture.subjects).sort()).toEqual(Object.keys(EXPECTED).sort());
    expect(fixture.response.subjects.map((s) => s.id).sort()).toEqual(Object.keys(EXPECTED).sort());
    expect(fixture.response.totals.subjects).toBe(6);
  });

  for (const [id, stages] of Object.entries(EXPECTED)) {
    it(`${id}: readyFor and blockedReason follow the stage rules`, () => {
      for (const [stage, reason] of Object.entries(stages)) {
        expect(readyFor(row(id), stage), `${id} ${stage}`).toBe(reason === undefined);
        expect(blockedReason(row(id), stage), `${id} ${stage}`).toBe(reason);
      }
    });
  }

  it("the Ready filter is simulator-ready AND raw present", () => {
    // full has both; m2monly and lffailed have a head model but no raw MRI; the rest no head model.
    const ready = fixture.response.subjects.filter(isReady).map((s) => s.id);
    expect(ready).toEqual(["full"]);
  });

  it("staged sourcedata is partial raw, not converted, and still pre-processable", () => {
    expect(row("staged").raw).toBe("partial");
    expect(notConverted(row("staged"))).toBe(true);
    expect(cell("staged", "raw").kind).toBe("warning");
    for (const id of ["full", "m2monly", "rawonly", "queued", "lffailed"]) expect(notConverted(row(id)), id).toBe(false);
  });

  it("a queued pre job makes the absent head model pending, and only pending cells pulse", () => {
    const m2m = cell("queued", "m2m");
    expect(m2m.state).toBe("pending");
    expect(m2m.pulse).toBe(true);
    expect(m2m.kind).toBe("accent");
    // Present raw MRI stays present while the job runs: on disk wins over a job.
    expect(cell("queued", "raw").state).toBe("present");
    for (const subject of fixture.response.subjects) {
      for (const c of presenceCells(subject)) expect(c.pulse, `${subject.id} ${c.key}`).toBe(c.state === "pending");
    }
  });

  it("a failed newest leadfield job shows the leadfield as failed (danger)", () => {
    const leadfield = cell("lffailed", "leadfield");
    expect(leadfield.state).toBe("failed");
    expect(leadfield.kind).toBe("danger");
    expect(leadfield.pulse).toBe(false);
    // The subject with a leadfield for its only net is present; no job touched it.
    expect(cell("full", "leadfield").state).toBe("present");
    expect(cell("m2monly", "leadfield").state).toBe("absent");
  });

  it("every Overview subject is one the Results page lists, so Open in Results lands on it", () => {
    const listed = subjectRows(fixture.catalog_subjects);
    for (const subject of fixture.response.subjects) expect(listed, subject.id).toContain(subject.id);
  });
});
