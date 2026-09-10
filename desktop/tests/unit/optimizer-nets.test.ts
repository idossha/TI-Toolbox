import { describe, expect, it } from "vitest";
import {
  defaultNet,
  electrodesForNet,
  leadfieldFor,
  leadfieldPathFor,
  netKey,
  netOptions,
} from "../../src/renderer/pages/optimizer/nets";
import type { EegNet, Leadfield } from "../../src/renderer/pages/optimizer/api";

/**
 * The exact shapes the REAL server answers with for Dataset 000's `sub-ernie`, copied from
 * `GET /api/catalog/leadfields?subject=ernie` and `GET /api/catalog/eeg-nets?subject=ernie`
 * against the dev container (lane FX1, 2026-09-03). The two endpoints spell the same net two
 * different ways, and that is the whole point of these tests: before `nets.ts` the page joined
 * them with `===`, so every electrode bucket in Ex/mEx was empty against real data and neither
 * search could be started from the UI (`real/ex.spec.ts` timed out waiting for the option "Fp1").
 *
 * The mock server (`tests/mock-server/server.mjs`) spells BOTH sides bare, which is why the mock
 * `optimizer.spec.ts` passed throughout — both spellings are therefore covered here.
 */
const REAL_LEADFIELDS: Leadfield[] = [
  {
    net: "EEG10-10_UI_Jurak_2007",
    path: "/mnt/000/derivatives/SimNIBS/sub-ernie/leadfields/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
    exists: true,
    size_bytes: 3239314641,
  },
];
const REAL_NETS: EegNet[] = [
  { name: "EEG10-10_Cutini_2011.csv", electrodes: ["Fp1", "Fp2", "Fz"], n: 3 },
  { name: "EEG10-10_UI_Jurak_2007.csv", electrodes: ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"], n: 8 },
];

/** The mock server's shape: `subject_details.eeg_nets` are bare and so are its leadfields. */
const MOCK_LEADFIELDS: Leadfield[] = [
  { net: "GSN-HydroCel-185", path: "/mnt/example/n.hdf5", exists: true, size_bytes: 2147483648 },
  { net: "EGI_template", path: "/mnt/example/e.hdf5", exists: false, size_bytes: 0 },
];
const MOCK_NETS: EegNet[] = [
  { name: "GSN-HydroCel-185", electrodes: ["E1", "E2", "E3", "E4"], n: 4 },
  { name: "EGI_template", electrodes: ["E1", "E2"], n: 2 },
];

describe("netKey", () => {
  it("treats the leadfield's bare name and the catalog's filename as one net", () => {
    expect(netKey("EEG10-10_UI_Jurak_2007.csv")).toBe("EEG10-10_UI_Jurak_2007");
    expect(netKey("EEG10-10_UI_Jurak_2007")).toBe("EEG10-10_UI_Jurak_2007");
    // Only a trailing suffix, and only that one: a net whose name contains ".csv" mid-string keeps it.
    expect(netKey("net.csv.backup")).toBe("net.csv.backup");
  });
});

describe("the electrode list behind every Ex/mEx bucket", () => {
  it("finds the real project's electrodes for the net its leadfield names (the FX1 bug)", () => {
    const net = REAL_LEADFIELDS[0]!.net; // "EEG10-10_UI_Jurak_2007", no extension
    expect(electrodesForNet(REAL_NETS, net)).toEqual(["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"]);
    // The pre-fix expression, kept as the regression witness: an equality join finds nothing.
    expect(REAL_NETS.find((n) => n.name === net)?.electrodes ?? []).toEqual([]);
  });

  it("still finds them when both sides are bare (the mock server's shape)", () => {
    expect(electrodesForNet(MOCK_NETS, "GSN-HydroCel-185")).toEqual(["E1", "E2", "E3", "E4"]);
  });

  it("is empty, not undefined, for no net and for an unknown net", () => {
    expect(electrodesForNet(REAL_NETS, null)).toEqual([]);
    expect(electrodesForNet(REAL_NETS, "NoSuchNet")).toEqual([]);
    expect(electrodesForNet(undefined, "EEG10-10_UI_Jurak_2007")).toEqual([]);
  });
});

describe("the leadfield gate", () => {
  it("resolves the HDF5 path across the spelling difference", () => {
    expect(leadfieldPathFor(REAL_LEADFIELDS, "EEG10-10_UI_Jurak_2007.csv")).toBe(REAL_LEADFIELDS[0]!.path);
    expect(leadfieldPathFor(REAL_LEADFIELDS, "EEG10-10_UI_Jurak_2007")).toBe(REAL_LEADFIELDS[0]!.path);
  });

  it("reports null for a net whose leadfield row exists but was never computed", () => {
    expect(leadfieldFor(MOCK_LEADFIELDS, "EGI_template")?.exists).toBe(false);
    expect(leadfieldPathFor(MOCK_LEADFIELDS, "EGI_template")).toBeNull();
    expect(leadfieldPathFor(MOCK_LEADFIELDS, "NoSuchNet")).toBeNull();
  });

  it("defaults to the net that already has a leadfield, as a bare name", () => {
    expect(defaultNet(REAL_LEADFIELDS, REAL_NETS)).toBe("EEG10-10_UI_Jurak_2007");
    expect(defaultNet(MOCK_LEADFIELDS, MOCK_NETS)).toBe("GSN-HydroCel-185");
    // No leadfields at all: the first net of the subject's own cap list, still bare — the value
    // The strip's "Generate" button submits as `eeg_net`, which LeadfieldGenerator suffixes with ".csv".
    expect(defaultNet([], REAL_NETS)).toBe("EEG10-10_Cutini_2011");
    expect(defaultNet([], [])).toBeNull();
  });

  it("offers every net once, bare, leadfield-backed first", () => {
    expect(netOptions(REAL_LEADFIELDS, REAL_NETS)).toEqual([
      { value: "EEG10-10_UI_Jurak_2007", label: "EEG10-10_UI_Jurak_2007" },
      { value: "EEG10-10_Cutini_2011", label: "EEG10-10_Cutini_2011" },
    ]);
    expect(netOptions(MOCK_LEADFIELDS, MOCK_NETS).map((o) => o.value)).toEqual(["GSN-HydroCel-185", "EGI_template"]);
  });
});
