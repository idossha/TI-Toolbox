import { describe, expect, it } from "vitest";
import { keepElectrodesOnNet } from "../../src/renderer/pages/optimizer/nets";
import { rowFormReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow, type OptimizerRow } from "../../src/renderer/pages/optimizer/rows";

/**
 * An Ex/mEx row switched to another net keeps only the electrodes that net has (package c1_4,
 * 2026-10-22). Found by `tests/e2e/optimizer-ex-edges.spec.ts`: an Ex row filled on EGI_template
 * with E1+ = E200 and switched to GSN-HydroCel-185 kept E200 and let the job run, though the
 * GSN-HydroCel-185 leadfield has no field for it (the server then failed after loading the
 * leadfield). The rule: a label the new net's electrode list lacks is dropped (and named), and the
 * row gate's existing sentence refuses what is left incomplete.
 *
 * The nets are hand-written lists in the shape `GET /api/catalog/eeg-nets` serves (`electrodes`
 * = the CSV's Electrode rows, `tit/catalog.py::_read_cap_electrode_labels`); the two GSN-like nets
 * mirror the mock server's (E1..E256 and E1..E185).
 */
const range = (n: number) => Array.from({ length: n }, (_, i) => `E${i + 1}`);
const EGI_256 = range(256);
const GSN_185 = range(185);
/** EEG10-10_UI_Jurak_2007 as the catalog lists it: Electrode rows only, so not its reference Cz. */
const JURAK_LISTED = ["Fp1", "Fz", "F3", "F4", "C3", "C4", "P3", "P4"];
/** A net where Cz is an ordinary Electrode row (EEG10-20_extended_SPM12 has one). */
const SPM12_LIKE = ["Cz", "Fp1", "F3", "F4", "C3", "C4"];

function exRow(buckets: Record<string, string[]>, net = "EGI_template"): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "ernie", method: "ex", net });
  return { ...row, ex: { ...row.ex, electrodeMode: "bucketed", buckets } };
}

function poolRow(pool: string[]): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "ernie", method: "ex", net: "EGI_template" });
  return { ...row, ex: { ...row.ex, electrodeMode: "all", pool } };
}

function mexRow(buckets: Record<string, string[]>): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "ernie", method: "ex", net: "EGI_template", exPairs: 4 });
  return { ...row, mex: { ...row.mex, buckets } };
}

const FILLED_MEX = {
  e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"],
  e3_plus: ["E5"], e3_minus: ["E6"], e4_plus: ["E7"], e4_minus: ["E8"],
};

describe("switching an Ex row's net", () => {
  it("drops an electrode the new net lacks, and the emptied bucket refuses the run", () => {
    const row = exRow({ e1_plus: ["E200"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] });
    expect(rowFormReason(row)).toBeNull(); // complete on EGI_template
    const { row: next, dropped } = keepElectrodesOnNet(row, GSN_185);
    expect(dropped).toEqual(["E200"]);
    expect(next.ex.buckets).toEqual({ e1_plus: [], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] });
    expect(rowFormReason(next)).toBe("Fill in every electrode bucket.");
    // Pure: the row the table still holds is not edited in place.
    expect(row.ex.buckets.e1_plus).toEqual(["E200"]);
    // Nothing but the electrodes changes.
    expect(next.net).toBe(row.net);
    expect({ ...next.ex, buckets: null, pool: null }).toEqual({ ...row.ex, buckets: null, pool: null });
  });

  it("keeps a label both nets share and takes out only the missing ones from a mixed bucket", () => {
    const row = exRow({ e1_plus: ["E2", "E200", "E185"], e1_minus: ["E186"], e2_plus: ["E3"], e2_minus: ["E4", "E256"] });
    const { row: next, dropped } = keepElectrodesOnNet(row, GSN_185);
    expect(next.ex.buckets.e1_plus).toEqual(["E2", "E185"]); // E185 is the new net's last electrode
    expect(next.ex.buckets.e2_minus).toEqual(["E4"]);
    expect(dropped).toEqual(["E200", "E186", "E256"]); // first-seen order, bucket by bucket
  });

  it("returns the same row when every label is on the new net", () => {
    const row = exRow({ e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E185"] });
    const result = keepElectrodesOnNet(row, GSN_185);
    expect(result.dropped).toEqual([]);
    expect(result.row).toBe(row);
    // And switching back to the larger net keeps everything too.
    expect(keepElectrodesOnNet(row, EGI_256).row).toBe(row);
  });

  it("names a label once even when several buckets and the pool hold it", () => {
    const row = exRow({ e1_plus: ["E200"], e1_minus: ["E200"], e2_plus: ["E3"], e2_minus: ["E4"] });
    const withPool = { ...row, ex: { ...row.ex, pool: ["E1", "E200", "E201"] } };
    const { row: next, dropped } = keepElectrodesOnNet(withPool, GSN_185);
    expect(dropped).toEqual(["E200", "E201"]);
    expect(next.ex.pool).toEqual(["E1"]);
  });

  it("drops pool electrodes the new net lacks; a pool left under four refuses the run", () => {
    const row = poolRow(["E1", "E2", "E3", "E200", "E250"]);
    expect(rowFormReason(row)).toBeNull();
    const { row: next, dropped } = keepElectrodesOnNet(row, GSN_185);
    expect(next.ex.pool).toEqual(["E1", "E2", "E3"]);
    expect(dropped).toEqual(["E200", "E250"]);
    expect(rowFormReason(next)).toBe("Add at least four electrodes to the pool.");
  });

  it("leaves a pool of four on-net electrodes runnable", () => {
    const row = poolRow(["E1", "E2", "E3", "E4", "E200"]);
    const { row: next } = keepElectrodesOnNet(row, GSN_185);
    expect(next.ex.pool).toEqual(["E1", "E2", "E3", "E4"]);
    expect(rowFormReason(next)).toBeNull();
  });
});

describe("switching an mEx row's net", () => {
  it("drops from the eight buckets, and one emptied bucket refuses the run", () => {
    const row = mexRow({ ...FILLED_MEX, e4_minus: ["E201"] });
    expect(rowFormReason(row)).toBeNull();
    const { row: next, dropped } = keepElectrodesOnNet(row, GSN_185);
    expect(dropped).toEqual(["E201"]);
    expect(next.mex.buckets).toEqual({ ...FILLED_MEX, e4_minus: [] });
    expect(rowFormReason(next)).toBe("Fill in all eight electrode buckets.");
  });

  it("also reconciles the Ex form the mEx row carries, so going back to two pairs is safe", () => {
    const row = mexRow(FILLED_MEX);
    const carried = { ...row, ex: { ...row.ex, buckets: { e1_plus: ["E220"], e1_minus: ["E1"], e2_plus: ["E2"], e2_minus: ["E3"] } } };
    const { row: next, dropped } = keepElectrodesOnNet(carried, GSN_185);
    expect(dropped).toEqual(["E220"]);
    expect(next.ex.buckets.e1_plus).toEqual([]);
    expect(next.mex.buckets).toEqual(FILLED_MEX);
  });
});

describe("the reference electrode", () => {
  it("is kept exactly when the net's listing names it", () => {
    // Cz picked on a net where it is an Electrode row, then the row switches to Jurak, whose Cz is
    // the ReferenceElectrode row. The catalog lists Electrode rows only, so the bucket picker never
    // offers Cz on Jurak and the switch drops it -- although SimNIBS's leadfield holds the
    // reference and the server and runner accept it (tests/test_ex_electrodes_on_net.py). The page
    // follows the listing; were the catalog to list the reference, it would be kept.
    const row = exRow({ e1_plus: ["Cz"], e1_minus: ["F3"], e2_plus: ["C3"], e2_minus: ["C4"] }, "EEG10-20_extended_SPM12");
    expect(keepElectrodesOnNet(row, SPM12_LIKE).row).toBe(row);
    const { row: next, dropped } = keepElectrodesOnNet(row, JURAK_LISTED);
    expect(dropped).toEqual(["Cz"]);
    expect(next.ex.buckets.e1_plus).toEqual([]);
    expect(keepElectrodesOnNet(row, [...JURAK_LISTED, "Cz"]).dropped).toEqual([]);
  });
});

describe("when the page cannot judge", () => {
  it("keeps every label while the new net's electrode list is unknown", () => {
    const row = exRow({ e1_plus: ["E200"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] });
    const result = keepElectrodesOnNet(row, []);
    expect(result.row).toBe(row);
    expect(result.dropped).toEqual([]);
  });

  it("leaves a Flex row alone: its net is a mapping net, not a leadfield", () => {
    const ex = exRow({ e1_plus: ["E200"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] });
    const flex: OptimizerRow = { ...ex, method: "flex" };
    const result = keepElectrodesOnNet(flex, GSN_185);
    expect(result.row).toBe(flex);
    expect(result.dropped).toEqual([]);
  });
});
