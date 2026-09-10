// @vitest-environment jsdom
/**
 * `pages/preprocess/stepInfo` is the single source of the stage explainers, so it is the thing
 * that has to be true: every stage has prose, at least one input, at least one output, and every
 * path it names looks like a path this project actually writes — not a plausible-looking invention.
 *
 * The path regex is deliberately a shape check against the real roots (`tit/paths.py`), not a
 * filesystem probe: these strings carry `<id>` placeholders and describe a subject that may not
 * exist on the machine running the tests.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  EMULATION_FACTOR,
  STEP_INFO,
  StepFlow,
  durationLabel,
  stepGraph,
  stepPaths,
} from "../../src/renderer/pages/preprocess/stepInfo";

/** The seven `G1`-`G6` stage rows, keyed by their `PreprocessConfig` flag. */
const STAGE_IDS = [
  "convert_dicom",
  "create_m2m",
  "run_fastsurfer",
  "run_freesurfer",
  "run_tissue_analysis",
  "run_qsiprep",
  "run_qsirecon",
  "extract_dti",
] as const;

/** The two `FormSection` headers on the page. */
const SECTION_IDS = ["structural", "dwi"] as const;

/**
 * A path this project really writes. Roots come from `tit/paths.py`:
 * `sourcedata/`, `sub-<id>/`, `derivatives/{SimNIBS,fastsurfer,qsiprep,qsirecon,ti-toolbox}/`,
 * `m2m_<id>/`. A leading `…` or `<tissue>` continues the entry above it.
 */
const REAL_PATH =
  /^(sourcedata\/sub-<id>\/|sub-<id>\/(anat|dwi)\/|derivatives\/(SimNIBS|fastsurfer|freesurfer|qsiprep|qsirecon|ti-toolbox|\.qsiprep_work)|m2m_<id>\/|…|<tissue>_)/;

describe("STEP_INFO", () => {
  it("covers every stage row and both section headers, and nothing else", () => {
    expect(Object.keys(STEP_INFO).sort()).toEqual([...STAGE_IDS, ...SECTION_IDS].sort());
  });

  it.each([...STAGE_IDS, ...SECTION_IDS])("%s: has prose, ≥1 input, ≥1 output and a docs link", (id) => {
    const info = STEP_INFO[id]!;
    expect(info.id).toBe(id);
    expect(info.title.length).toBeGreaterThan(2);
    // One or two sentences — long enough to say something, short enough to read in a popover.
    expect(info.text.length).toBeGreaterThan(60);
    expect(info.text.length).toBeLessThan(600);
    expect(info.inputs.length).toBeGreaterThanOrEqual(1);
    expect(info.process.length).toBeGreaterThanOrEqual(1);
    expect(info.outputs.length).toBeGreaterThanOrEqual(1);
    // Every box says what it IS in words; the path is the small print under it, never the label.
    for (const node of [...info.inputs, ...info.process, ...info.outputs]) {
      expect(node.label.length).toBeGreaterThan(2);
      // "bval/bvec" and "DTI / recon maps" are fine; a project path as the label is not.
      expect(node.label, `${id}: label is a path`).not.toMatch(REAL_PATH);
      expect(node.label, `${id}: label is a filename`).not.toMatch(/\.nii\.gz|\.mgz|\.msh/);
    }
    expect(info.docsHref).toMatch(/^https:\/\/idossha\.github\.io\/TI-Toolbox\/wiki\//);
  });

  it.each([...STAGE_IDS, ...SECTION_IDS])("%s: every input and output is a path this project writes", (id) => {
    const info = STEP_INFO[id]!;
    const paths = stepPaths(info);
    expect(paths.length).toBeGreaterThanOrEqual(2);
    for (const path of paths) {
      expect(path, `${id}: ${path}`).toMatch(REAL_PATH);
    }
  });

  it.each(STAGE_IDS.filter((id) => id !== "run_freesurfer"))("%s: carries its G-stage tag and a duration from tit/jobs/eta.py", (id) => {
    const info = STEP_INFO[id]!;
    expect(info.stage).toMatch(/^G[1-6][ab]?$/);
    expect(info.nativeMinutes).toBeGreaterThan(0);
    // PRE_STAGE_MIN's constants are the emulated figures divided by EMULATION_FACTOR, so every
    // stored value has to be an exact 1/3 of a whole number of measured minutes.
    expect(info.nativeMinutes! * EMULATION_FACTOR).toBeCloseTo(
      Math.round(info.nativeMinutes! * EMULATION_FACTOR),
      6,
    );
  });

  it("FreeSurfer has no unmeasured duration estimate", () => {
    expect(STEP_INFO.run_freesurfer!.stage).toBe("G2c");
    expect(STEP_INFO.run_freesurfer!.nativeMinutes).toBeUndefined();
  });

  it("section headers have no duration — they are not jobs", () => {
    for (const id of SECTION_IDS) {
      expect(STEP_INFO[id]!.nativeMinutes).toBeUndefined();
      expect(STEP_INFO[id]!.stage).toBeUndefined();
    }
  });

  it("the DTI tensor path is the one SimNIBS reads", () => {
    expect(STEP_INFO.extract_dti!.outputs[0]!.path).toBe("m2m_<id>/DTI_coregT1_tensor.nii.gz");
  });

  it("QSIRecon's input is QSIPrep's output — the dependency the plan enforces", () => {
    expect(STEP_INFO.run_qsirecon!.inputs[0]!.path).toBe("derivatives/qsiprep/sub-<id>/");
    expect(STEP_INFO.run_qsiprep!.outputs[0]!.path).toMatch(/^derivatives\/qsiprep\/sub-<id>\//);
  });
});

describe("durationLabel", () => {
  it("states both the native and the emulated wall clock", () => {
    expect(durationLabel(15)).toBe("≈15 min (≈45 min emulated)");
  });

  it("a sub-minute stage says '<1' rather than '0'", () => {
    expect(durationLabel(2 / 3)).toBe("≈<1 min (≈2 min emulated)");
  });
});

describe("stepGraph", () => {
  it("lays the flow out as inputs | process… | outputs", () => {
    const { columns } = stepGraph(STEP_INFO.convert_dicom!);
    expect(columns.map((c) => c[0]!.kind)).toEqual(["input", "process", "output"]);
    expect(columns[0]).toHaveLength(3);
    expect(columns[2]).toHaveLength(3);
  });

  it("a multi-stage step gets one column per process box", () => {
    const { columns } = stepGraph(STEP_INFO.dwi!);
    // QSIPrep → QSIRecon → extract, between the input and the output columns.
    expect(columns).toHaveLength(5);
    expect(columns.slice(1, 4).map((c) => c[0]!.label)).toEqual(["QSIPrep", "QSIRecon", "extract"]);
  });

  it("every input fans into the first process box, and the last fans out to every output", () => {
    const info = STEP_INFO.create_m2m!;
    const { edges } = stepGraph(info);
    const froms = edges.filter(([, to]) => to === "proc-0").map(([from]) => from);
    expect(froms).toEqual(info.inputs.map((_, i) => `in-${i}`));
    const tos = edges.filter(([from]) => from === `proc-${info.process.length - 1}`).map(([, to]) => to);
    expect(tos).toEqual(info.outputs.map((_, i) => `out-${i}`));
    // Chained process boxes are wired to each other, so no node is left dangling.
    for (const node of stepGraph(info).columns.flat()) {
      expect(edges.some(([from, to]) => from === node.id || to === node.id), node.id).toBe(true);
    }
  });

  it("ids are unique across the whole graph", () => {
    for (const info of Object.values(STEP_INFO)) {
      const ids = stepGraph(info).columns.flat().map((n) => n.id);
      expect(new Set(ids).size, info.id).toBe(ids.length);
    }
  });
});

describe("StepFlow", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("draws every node as a box with a human label, its path under it, and arrows between", () => {
    const info = STEP_INFO.convert_dicom!;
    act(() => root.render(<StepFlow info={info} />));

    const nodes = container.querySelectorAll(".flow-node");
    expect(nodes).toHaveLength(info.inputs.length + info.process.length + info.outputs.length);
    expect(container.querySelectorAll(".flow-node-process")).toHaveLength(1);
    // One arrow between each pair of columns: inputs → process → outputs.
    expect(container.querySelectorAll(".flow-arrow")).toHaveLength(2);

    const labels = Array.from(container.querySelectorAll(".flow-node-label")).map((n) => n.textContent);
    expect(labels).toContain("T1w DICOM series");
    expect(labels).toContain("dcm2niix");
    expect(labels).toContain("T1w NIfTI + JSON");

    // The path is small print under the label, and carries the full string in `title` because the
    // box ellipsises it.
    const path = container.querySelector(".flow-node-path") as HTMLElement;
    expect(path.textContent).toBe("sourcedata/sub-<id>/T1w/dicom/");
    expect(path.getAttribute("title")).toBe(path.textContent);

    // Colours come from preprocess.css's tokens, never from inline styles.
    expect(container.querySelector("[style]")).toBeNull();
    // The captions name the three roles.
    const captions = Array.from(container.querySelectorAll(".flow-caption")).map((n) => n.textContent);
    expect(captions).toEqual(["inputs", "process", "outputs"]);
  });

  it("names the whole flow for assistive tech", () => {
    act(() => root.render(<StepFlow info={STEP_INFO.create_m2m!} />));
    const flow = container.querySelector(".step-flow")!;
    expect(flow.getAttribute("role")).toBe("group");
    expect(flow.getAttribute("aria-label")).toBe(
      "T1w image, T2w image (optional) to charm then subject_atlas to Head mesh, Tissue labels, EEG net positions, Subject atlases",
    );
  });

  it("every stage renders every one of its labels and paths as real text", () => {
    for (const id of STAGE_IDS) {
      const info = STEP_INFO[id]!;
      act(() => root.render(<StepFlow info={info} />));
      const text = container.textContent ?? "";
      for (const node of [...info.inputs, ...info.process, ...info.outputs]) {
        expect(text, `${id}: ${node.label}`).toContain(node.label);
        if (node.path) expect(text, `${id}: ${node.path}`).toContain(node.path);
      }
    }
  });
});
