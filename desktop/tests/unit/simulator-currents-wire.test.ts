/**
 * The Simulator sends exactly the currents its table shows.
 *
 * Spec ("what the user sees is what runs"): a row's channel inputs show one value per channel, a
 * blank cell reading 1.0 mA (`currentValues`, the display), and `buildSimulationConfig` sends that
 * list as `intensities`. The count the server needs is `SimulationConfig`'s `required` —
 * tit/sim/config.py: 2 for a 2-pair (TI) montage, `num_pairs` for mTI — typed out below as
 * `serverRequired`, independently of the desktop's `currentsCount`. A row the table calls runnable
 * must be one the server takes: no 0 mA channel (a 0 mA channel makes the TI envelope 0
 * everywhere), no negative typed current, a pair count of 2 or an even count from 4, and as many
 * currents as the pair count needs.
 *
 * Before the fix `parseIntensities` read "" as [0, 0] (the row showed 1.0 / 1.0), passed a short
 * list through (a 4-pair row showing four inputs sent two, a 422), and a 1-pair "2.0" became
 * [2, 2] while the row showed 2.0 / 1.0.
 */
import { describe, expect, it } from "vitest";
import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { currentValues, rowCurrentsCount } from "../../src/renderer/pages/simulator/MontageManager";
import { simStepEdit, simStepRows } from "../../src/renderer/pages/simulator/planStep";
import { candidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import { defaultJobSettings, isRunnableRow, rowProblem, type SelectedRow } from "../../src/renderer/pages/simulator/types";

const params = defaultJobSettings() as GlobalParams;
const NET = "GSN-HydroCel-185.csv";
type Xyz = [number, number, number];

/** n label pairs with 2n distinct labels. */
const labels = (n: number): [string, string][] => Array.from({ length: n }, (_, i) => [`E${2 * i + 1}`, `E${2 * i + 2}`]);
/** n XYZ pairs on a 75 mm sphere, every electrode at least 20 mm from every other. */
const xyz = (n: number): [Xyz, Xyz][] =>
  Array.from({ length: n }, (_, i) => {
    const t = (2 * Math.PI * i) / Math.max(1, n);
    return [
      [75 * Math.cos(t), 75 * Math.sin(t), 20],
      [75 * Math.cos(t + Math.PI / n), 75 * Math.sin(t + Math.PI / n), -20],
    ];
  });

/** tit/sim/config.py `required`: TI (2 pairs) takes 2 currents, mTI one per pair. */
const serverRequired = (pairs: number) => (pairs === 2 ? 2 : pairs);
const sent = (row: SelectedRow) => buildSimulationConfig(row, params).intensities as number[];
const shown = (row: SelectedRow) => currentValues(row.currents, rowCurrentsCount(row));
const base = { id: "r", subjectId: "ernie", name: "M" };

/** Every row shape the table can hold, with the pair count the montage carries. */
const SHAPES: { label: string; pairs: number; row: (currents: string) => SelectedRow }[] = [
  { label: "TI net montage", pairs: 2, row: (currents) => ({ ...base, source: "montage", kind: "uni_polar", eegNet: NET, pairs: labels(2), currents }) },
  { label: "mTI net montage, 4 pairs", pairs: 4, row: (currents) => ({ ...base, source: "montage", kind: "multi_polar", eegNet: NET, pairs: labels(4), currents }) },
  { label: "mTI net montage, 6 pairs", pairs: 6, row: (currents) => ({ ...base, source: "montage", kind: "multi_polar", eegNet: NET, pairs: labels(6), currents }) },
  { label: "flex result mapped onto a cap", pairs: 2, row: (currents) => ({ ...base, source: "flex", eegNet: NET, pairs: labels(2), currents }) },
  { label: "flex result at its own XYZ", pairs: 2, row: (currents) => ({ ...base, source: "flex", xyzPairs: xyz(2), currents }) },
  { label: "free-hand, 4 positions", pairs: 2, row: (currents) => ({ ...base, source: "freehand", xyzPairs: xyz(2), currents }) },
  { label: "free-hand, 8 positions", pairs: 4, row: (currents) => ({ ...base, source: "freehand", xyzPairs: xyz(4), currents }) },
];
const CURRENTS = ["", "2.0", "1,1", "1,2,3,4", "0.5,1.5,2.5,3.5,4.5,5.5", " 1.5 , ,2"];

describe("buildSimulationConfig sends the currents the row shows", () => {
  for (const shape of SHAPES) {
    for (const currents of CURRENTS) {
      it(`${shape.label}, currents ${JSON.stringify(currents)}`, () => {
        const row = shape.row(currents);
        expect(sent(row)).toEqual(shown(row));
        expect(sent(row)).toHaveLength(serverRequired(shape.pairs));
        // Every one of those is a usable current, so the row runs.
        expect(isRunnableRow(row)).toBe(true);
      });
    }
  }

  it("a blank currents cell is 1 mA per channel, never 0", () => {
    // planStep.ts sets currents "" for a step whose config names no intensities.
    expect(sent(SHAPES[0]!.row(""))).toEqual([1, 1]);
    expect(sent(SHAPES[1]!.row(""))).toEqual([1, 1, 1, 1]);
  });

  it("a short list is padded to one value per channel, a long one cut to the channel count", () => {
    expect(sent(SHAPES[1]!.row("1,1"))).toEqual([1, 1, 1, 1]);
    expect(sent(SHAPES[0]!.row("1,2,3,4"))).toEqual([1, 2]);
    expect(sent(SHAPES[0]!.row("2.0"))).toEqual([2, 1]);
    expect(sent(SHAPES[2]!.row(" 1.5 , ,2"))).toEqual([1.5, 1, 2, 1, 1, 1]);
  });

  it("a plan step that names no intensities shows and sends 1 mA per channel, and runs", () => {
    const [row] = simStepRows({
      proposalId: "p", stepId: "s", number: 1, title: "Simulate", kind: "sim", subjectIds: ["ernie"], overwrite: false,
      config: { montages: [{ name: "M1", mode: "net", eeg_net: NET, electrode_pairs: labels(2) }] },
    });
    expect(row!.currents).toBe("");
    expect(sent(row!)).toEqual([1, 1]);
    expect(isRunnableRow(row!)).toBe(true);
    // "Save to plan" writes what the row shows, and refuses a row the server would, saying why.
    const target = { proposalId: "p", stepId: "s", number: 1, title: "Simulate", kind: "sim", subjectIds: ["ernie"], overwrite: false, config: {} };
    expect(simStepEdit(target, [row!], params).config?.intensities).toEqual([1, 1]);
    expect(() => simStepEdit(target, [{ ...row!, currents: "0,1" }], params)).toThrow("Channel 1 needs a current above 0 mA.");
  });

  it("a plan's pending flex run with blank currents keeps the run's own; typed currents are sent", () => {
    const step = {
      proposalId: "p", stepId: "s2", number: 2, title: "Simulate the flex result", kind: "sim_from_flex" as const,
      subjectIds: ["ernie"], overwrite: false, flexRun: "flexrun", config: { flex_step: "s1" },
    };
    const [row] = simStepRows(step);
    expect(row!.currents).toBe("");
    expect(simStepEdit(step, [row!], params).config).not.toHaveProperty("intensities");
    expect(simStepEdit(step, [{ ...row!, currents: "1.5,0.5" }], params).config?.intensities).toEqual([1.5, 0.5]);
  });
});

describe("a row the server would refuse is not runnable, and says why", () => {
  const ti = SHAPES[0]!.row;

  it("refuses a 0 mA or negative channel", () => {
    for (const currents of ["0,1", "1,0", "-1,1", "1,-0.5"]) {
      const row = ti(currents);
      expect(isRunnableRow(row), currents).toBe(false);
      expect(rowProblem(row), currents).toMatch(/^Channel [12] needs a current above 0 mA\.$/);
    }
    expect(rowProblem(ti("0,1"))).toBe("Channel 1 needs a current above 0 mA.");
    expect(rowProblem(ti("1,-0.5"))).toBe("Channel 2 needs a current above 0 mA.");
  });

  it("refuses a current that is not a finite number", () => {
    expect(isRunnableRow(ti("Infinity,1"))).toBe(false);
    expect(rowProblem(ti("1,-Infinity"))).toBe("Channel 2 needs a current above 0 mA.");
  });

  it("refuses a pair count the server cannot classify (1, 3, 5 pairs)", () => {
    for (const n of [1, 3, 5]) {
      const label: SelectedRow = { ...base, source: "montage", kind: n > 2 ? "multi_polar" : "uni_polar", eegNet: NET, pairs: labels(n), currents: "" };
      const free: SelectedRow = { ...base, source: "freehand", xyzPairs: xyz(n), currents: "" };
      for (const row of [label, free]) {
        expect(isRunnableRow(row), `${row.source} ${n}`).toBe(false);
        expect(rowProblem(row)).toContain(`${n} electrode pair`);
      }
    }
  });

  it("refuses a 4-pair montage stored as TI: it shows 2 currents, the server needs 4", () => {
    const row: SelectedRow = { ...base, source: "montage", kind: "uni_polar", eegNet: NET, pairs: labels(4), currents: "1.0,1.0" };
    expect(shown(row)).toHaveLength(2);
    expect(serverRequired(4)).toBe(4);
    expect(isRunnableRow(row)).toBe(false);
    expect(rowProblem(row)).toBe("Saved as TI with 4 pairs, which run with 4 currents, not 2: open it in the montage editor and save it again.");
    // The same pairs in the mTI bucket are a job.
    expect(isRunnableRow({ ...row, kind: "multi_polar", currents: "" })).toBe(true);
  });

  it("an optimiser candidate keeps a signed current but never a zero one", () => {
    const pairs = xyz(2);
    const config = { subject_id: "ernie", montages: [{ _type: "Montage", name: "candidate_8", mode: "flex_free", eeg_net: null, electrode_pairs: pairs }], intensities: [0.7, 1.3] };
    const row = candidateRow({ id: "8", subject: "ernie", run: "flexrun", config });
    expect(sent(row)).toEqual([0.7, 1.3]);
    expect(isRunnableRow({ ...row, currents: "0.7,-1.1" })).toBe(true);
    expect(sent({ ...row, currents: "0.7,-1.1" })).toEqual([0.7, -1.1]);
    expect(isRunnableRow({ ...row, currents: "0.7,0" })).toBe(false);
    expect(rowProblem({ ...row, currents: "0,1" })).toBe("Channel 1 needs a current other than 0 mA.");
  });

  it("a row still being filled in has no problem to report, and is not runnable", () => {
    const blank: SelectedRow = { ...base, source: "montage", eegNet: NET, name: "", currents: "0,0" };
    expect(rowProblem(blank)).toBeNull();
    expect(isRunnableRow(blank)).toBe(false);
    expect(isRunnableRow({ ...ti(""), subjectId: "" })).toBe(false);
    expect(isRunnableRow({ ...ti(""), mappingPending: true })).toBe(false);
  });
});
