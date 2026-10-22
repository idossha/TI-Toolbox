/**
 * The Results flex/ex preview parsers read what the Python producers write (2026-10-22, p12).
 *
 * Flex: every file in `tests/fixtures/flex_meta_contract/` is written by the real
 * `tit/opt/flex/manifest.py::write_manifest` from a synthetic `FlexConfig`
 * (`dev/regen_flex_manifest_fixtures.py`; `tests/test_flex_manifest_contract.py` fails when the
 * committed copy drifts from the writer). The writer stores ROI fields as the desktop sends them —
 * lists, also for one region — which the old scalar-only parser dropped ("subcortical · GM").
 * Each expected row below is derived by hand from the generator's inputs (the CASES table), not
 * from the parser.
 *
 * Ex: a pool-mode `run_config.json` in the shape `tit/opt/ex/results.py::save_run_config` writes
 * (`electrodes: {electrodes: [...]}`, copied from Dataset 000 sub-101/ex-search/20260914_112857),
 * and the mEx run_config the desktop→runner chain wrote (`desktop/tests/fixtures/ex_chain/mex/`,
 * eight buckets).
 *
 * Run: `cd desktop && npx vitest run tests/unit/results-preview-producers.test.ts`.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseExRunConfig } from "../../src/renderer/pages/results/preview/ex";
import { flexManifestSummary, flexRoiLabel, parseFlexPositions } from "../../src/renderer/pages/results/preview/flex";

const contract = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(__dirname, "../../../tests/fixtures/flex_meta_contract", `${name}.json`), "utf8"));

const rows = (name: string): Record<string, string> =>
  Object.fromEntries(flexManifestSummary(contract(name)).rows.map((r) => [r.label, r.value]));

describe("flexManifestSummary on manifests the writer produced", () => {
  it("a single sphere sent as one-element lists names its centre and radius", () => {
    const r = rows("sphere_desktop");
    expect(r.ROI).toBe("spherical · (-30, 10, 5) r 10 mm");
    expect(r.Goal).toBe("mean · max_TI");
    expect(r.Current).toBe("1 mA");
    expect(r.Channels).toBe("2 · 1 multistart");
    expect(r["Best value"]).toBe("-0.21");
    expect(r.Runs).toBe("1");
    // No net was mapped, no threshold set, no background observed: no row says otherwise.
    expect(r["EEG net"]).toBeUndefined();
    expect(r.Thresholds).toBeUndefined();
    expect(r["Non-ROI"]).toBeUndefined();
  });

  it("a net named without mapping is not recorded, so no EEG net row claims a mapping", () => {
    const r = rows("sphere_net_unmapped");
    expect(r["EEG net"]).toBeUndefined();
    expect(r.ROI).toBe("spherical · (-30, 10, 5) r 10 mm");
  });

  it("a two-sphere union names both centres with their own radii, and the tissue", () => {
    expect(rows("sphere_union").ROI).toBe("spherical · (-30, 10, 5) r 10 mm + (30, 12, 6) r 8 mm · GM");
    expect(rows("sphere_union").Runs).toBe("2");
  });

  it("a cortical atlas region names its annotation, label and hemisphere", () => {
    expect(rows("atlas_chn").ROI).toBe("atlas · lh.CHN_DK40.annot label 35 · lh");
  });

  it("a subcortical union in one atlas lists both labels, and a mapped run names its net", () => {
    const r = rows("subcortical_union_mapped");
    expect(r.ROI).toBe("subcortical · massp2021-parcellation_decade-18to40.nii.gz labels 13+14 · GM");
    expect(r["EEG net"]).toBe("GSN-HydroCel-185");
    expect(r.Goal).toBe("focality_tf · max_TI");
    expect(r["Non-ROI"]).toBe("everything else");
    expect(r.Channels).toBe("2 · 2 multistart");
  });

  it("a ROC focality run states its thresholds", () => {
    const r = rows("subcortical_focality");
    expect(r.ROI).toBe("subcortical · labeling.nii.gz label 17 · GM");
    expect(r.Thresholds).toBe("0.1,0.2");
    expect(r["Best value"]).toBe("-91.5567");
  });

  it("a specific non-ROI is named like the ROI, and a failed restart (null) still counts as a run", () => {
    const r = rows("focality_tf_specific_nonroi");
    expect(r["Non-ROI"]).toBe("spherical · (30, -20, 40) r 15 mm");
    expect(r.Runs).toBe("2");
    expect(r["Best value"]).toBe("-1.59");
  });
});

describe("flexRoiLabel pairs parallel lists by index (tit/opt/roi_spec.py)", () => {
  it("regions in different atlas files keep each file with its own label", () => {
    expect(
      flexRoiLabel({ type: "subcortical", atlas_path: ["/a/A.nii.gz", "/b/B.nii.gz"], label: [1, 2], tissues: "GM" }),
    ).toBe("subcortical · A.nii.gz label 1 + B.nii.gz label 2 · GM");
  });

  it("one atlas path with several labels applies to every label", () => {
    expect(flexRoiLabel({ type: "subcortical", atlas_path: ["/x/L.nii.gz"], label: [3, 4] })).toBe(
      "subcortical · L.nii.gz labels 3+4",
    );
  });

  it("the Dataset 000 ernie DKT region", () => {
    expect(
      flexRoiLabel({
        type: "subcortical",
        atlas_path: ["/mnt/000/derivatives/fastsurfer/sub-ernie/mri/aparc.DKTatlas+aseg.deep.nii.gz"],
        label: [1025],
        tissues: "GM",
      }),
    ).toBe("subcortical · aparc.DKTatlas+aseg.deep.nii.gz label 1025 · GM");
  });

  it("an atlas union across hemispheres names both", () => {
    expect(
      flexRoiLabel({
        type: "atlas",
        atlas_path: ["/s/lh.aparc.DKTatlas.annot", "/s/rh.aparc.DKTatlas.annot"],
        label: [35, 35],
        hemisphere: ["lh", "rh"],
      }),
    ).toBe("atlas · lh.aparc.DKTatlas.annot label 35 + rh.aparc.DKTatlas.annot label 35 · lh+rh");
  });

  it("the scalar shape older manifests wrote still reads", () => {
    expect(flexRoiLabel({ type: "subcortical", atlas_path: "/m/labeling.nii.gz", label: 17, tissues: "GM" })).toBe(
      "subcortical · labeling.nii.gz label 17 · GM",
    );
  });
});

describe("parseFlexPositions without channel_array_indices", () => {
  it("derives channel floor(i/2) and array i%2, the order SimNIBS writes", () => {
    const text = JSON.stringify({
      optimized_positions: [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
        [10, 11, 12],
      ],
    });
    expect(parseFlexPositions(text).map((e) => [e.channel, e.array])).toEqual([
      [0, 0],
      [0, 1],
      [1, 0],
      [1, 1],
    ]);
  });
});

describe("parseExRunConfig on what save_run_config writes", () => {
  it("a pool run lists its pool", () => {
    const pool = ["AF7", "AFz", "CP6", "P10", "POz"];
    const summary = parseExRunConfig(
      JSON.stringify({
        subject_id: "101",
        roi_name: "labeling.nii.gz_1region.csv",
        roi_radius: 3,
        leadfield_hdf: "/mnt/000/derivatives/SimNIBS/sub-101/leadfields/101_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
        electrode_mode: "pool",
        electrodes: { electrodes: pool },
        n_combinations: 480,
        total_current_mA: 2,
        current_step_mA: 0.4,
        channel_limit_mA: 1.6,
        symmetric_bucket: false,
      }),
    )!;
    expect(summary.buckets).toEqual([{ label: "Pool", electrodes: pool }]);
  });

  it("an mEx run lists all eight channel poles", () => {
    const text = readFileSync(resolve(__dirname, "../fixtures/ex_chain/mex/run_config.json"), "utf8");
    const written = JSON.parse(text).electrodes as Record<string, string[]>;
    const summary = parseExRunConfig(text)!;
    const poles = [1, 2, 3, 4].flatMap((ch) => [
      [`Channel ${ch} +`, `e${ch}_plus`],
      [`Channel ${ch} −`, `e${ch}_minus`],
    ]);
    expect(summary.buckets).toEqual(poles.map(([label, key]) => ({ label, electrodes: written[key!] })));
  });
});
