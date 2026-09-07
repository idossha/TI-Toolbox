/**
 * What each pre-processing stage does, what it eats, and what it leaves behind.
 *
 * One module, because three places want the same answer: the checkbox rows on this page, the two
 * section headers, and (TODO) the pipeline canvas node inspector — `pages/pipeline/NodeInspector`
 * has no per-node help affordance yet; when it grows one it should read `STEP_INFO` by stage id
 * rather than restating any of this.
 *
 * The picture is a **node flow**, not a directory listing: every input, every process and every
 * output is a box with a human label (`T1w DICOM series`), the concrete path underneath it in
 * small muted type, and arrows between the columns. Laid out with CSS grid rather than SVG so the
 * paths stay selectable and the whole thing follows the theme tokens.
 *
 * Every path below is copied from the code that writes it, not guessed:
 *
 *  - `tit/paths.py` — `sourcedata_dicom`, `bids_anat`, `bids_dwi`, `m2m`, `segmentation`,
 *    `tissue_labeling`, `fastsurfer_mri`, `tissue_analysis_output`, `qsiprep_subject`,
 *    `qsirecon_subject`
 *  - `tit/pre/dicom2nifti.py` (`MODALITIES`), `tit/pre/charm.py`, `tit/pre/fastsurfer.py`,
 *    `tit/pre/tissue_analyzer.py`, `tit/pre/qsi/*`
 *  - `docs/wiki/pre-processing.md` §"Output Directory Structure"
 *
 * Durations come from `PRE_STAGE_MIN` in `tit/jobs/eta.py`, whose constants are stated there as
 * the emulated wall clocks divided by `EMULATION_FACTOR` (3.0). Both numbers are shown, because a
 * reader on Apple Silicon gets the emulated one.
 */
import type { ReactNode } from "react";
import { Cog, ExternalLink, FileInput, FileOutput } from "lucide-react";
import { isElectron } from "../../env";
import { HelpIcon } from "../../ui/HelpPopover";
import "./preprocess.css";

const DOCS_SITE = "https://idossha.github.io/TI-Toolbox/";
const PRE_DOCS = `${DOCS_SITE}wiki/pre-processing/`;
const DWI_DOCS = `${DOCS_SITE}wiki/diffusion-processing/`;

/** How much slower the amd64 image is under Rosetta/QEMU — `EMULATION_FACTOR` in `tit/jobs/eta.py`. */
export const EMULATION_FACTOR = 3;

export type NodeKind = "input" | "process" | "output";

/** One box in the flow. `path` is the concrete file or directory the box stands for. */
export interface StepNode {
  id: string;
  label: string;
  path?: string;
  kind: NodeKind;
}

/** A `from` → `to` arrow, by node id. */
export type StepEdge = [from: string, to: string];

/** What an author writes: a label, and the path it stands for. */
interface NodeSpec {
  label: string;
  path?: string;
}

export interface StepInfo {
  /** The `PreprocessConfig` flag this row toggles, or the section id for a header. */
  id: string;
  /** The `G1`-`G6` tag `tit/jobs/plans.py` emits. Absent on the two section headers. */
  stage?: "G1" | "G2a" | "G2b" | "G3" | "G4" | "G5" | "G6";
  title: string;
  /** Mini-markdown (see `ui/HelpPopover`): one or two sentences on what the step does. */
  text: string;
  inputs: NodeSpec[];
  /** One box, or a chain of them for a multi-stage step (QSIPrep → QSIRecon → extract). */
  process: NodeSpec[];
  outputs: NodeSpec[];
  /** Native minutes, i.e. `PRE_STAGE_MIN[stage]`. Absent on the section headers. */
  nativeMinutes?: number;
  docsHref: string;
}

/** `PRE_STAGE_MIN` in `tit/jobs/eta.py`, as the emulated figures it divides by EMULATION_FACTOR. */
const MEASURED_EMULATED_MIN: Record<string, number> = {
  G1: 2,
  G2a: 45,
  G2b: 90,
  G3: 3,
  G4: 120,
  G5: 60,
  G6: 6,
};

const native = (stage: keyof typeof MEASURED_EMULATED_MIN) => (MEASURED_EMULATED_MIN[stage] ?? 0) / EMULATION_FACTOR;

/** Keyed by the `PreprocessConfig` flag the checkbox writes, plus the two section headers. */
export const STEP_INFO: Record<string, StepInfo> = {
  structural: {
    id: "structural",
    title: "Structural",
    text:
      "Builds the head model every simulation and optimization runs on.\n\n" +
      "Steps run in this order, except **charm** and **FastSurfer** which run in parallel — FastSurfer " +
      "reads the raw BIDS T1w, so it needs nothing from charm. An HTML report is written at the end of " +
      "each subject's run.",
    inputs: [{ label: "Source images", path: "sourcedata/sub-<id>/" }],
    process: [
      { label: "dcm2niix" },
      { label: "charm + FastSurfer" },
    ],
    outputs: [
      { label: "Head model", path: "derivatives/SimNIBS/sub-<id>/m2m_<id>/" },
      { label: "DKT parcellation", path: "derivatives/fastsurfer/sub-<id>/" },
    ],
    docsHref: `${PRE_DOCS}#processing-stages`,
  },
  dwi: {
    id: "dwi",
    title: "DWI (docker)",
    text:
      "Optional. Turns diffusion-weighted images into the anisotropic conductivity tensor SimNIBS can " +
      "use instead of the isotropic default.\n\n" +
      "Both QSIPrep and QSIRecon run in **their own containers** and need Docker socket access. " +
      "QSIRecon needs QSIPrep output; the tensor extraction needs QSIRecon output and `charm`.",
    inputs: [{ label: "Raw diffusion series", path: "sub-<id>/dwi/" }],
    process: [{ label: "QSIPrep" }, { label: "QSIRecon" }, { label: "extract tensor" }],
    outputs: [{ label: "DTI conductivity tensor", path: "m2m_<id>/DTI_coregT1_tensor.nii.gz" }],
    docsHref: DWI_DOCS,
  },

  convert_dicom: {
    id: "convert_dicom",
    stage: "G1",
    title: "Convert DICOM to NIfTI",
    text:
      "Ingests every modality found under the subject's `sourcedata/` folder and writes it out under a " +
      "BIDS name. DICOM series go through `dcm2niix`; a folder that already holds a NIfTI is copied " +
      "into place instead.",
    inputs: [
      { label: "T1w DICOM series", path: "sourcedata/sub-<id>/T1w/dicom/" },
      { label: "T2w DICOM series", path: "sourcedata/sub-<id>/T2w/dicom/" },
      { label: "DWI DICOM series", path: "sourcedata/sub-<id>/dwi/dicom/" },
    ],
    process: [{ label: "dcm2niix" }],
    outputs: [
      { label: "T1w NIfTI + JSON", path: "sub-<id>/anat/sub-<id>_T1w.nii.gz" },
      { label: "T2w NIfTI + JSON", path: "sub-<id>/anat/sub-<id>_T2w.nii.gz" },
      { label: "DWI NIfTI + bval/bvec", path: "sub-<id>/dwi/sub-<id>_dwi.nii.gz" },
    ],
    nativeMinutes: native("G1"),
    docsHref: `${PRE_DOCS}#stage-1-dicom-to-nifti-conversion`,
  },
  create_m2m: {
    id: "create_m2m",
    stage: "G2a",
    title: "SimNIBS charm (m2m + subject atlas)",
    text:
      "Segments the head and meshes it: `charm` produces the tetrahedral head model every FEM solve " +
      "uses, and `subject_atlas` projects the surface atlases into this subject's anatomy. A T2w image " +
      "is used when one is present — it sharpens the skull/CSF boundary, where the field is most " +
      "sensitive to segmentation error.",
    inputs: [
      { label: "T1w image", path: "sub-<id>/anat/sub-<id>_T1w.nii.gz" },
      { label: "T2w image (optional)", path: "sub-<id>/anat/sub-<id>_T2w.nii.gz" },
    ],
    process: [{ label: "charm" }, { label: "subject_atlas" }],
    outputs: [
      { label: "Head mesh", path: "m2m_<id>/<id>.msh" },
      { label: "Tissue labels", path: "m2m_<id>/segmentation/labeling.nii.gz" },
      { label: "EEG net positions", path: "m2m_<id>/eeg_positions/" },
      { label: "Subject atlases", path: "m2m_<id>/segmentation/" },
    ],
    nativeMinutes: native("G2a"),
    docsHref: `${PRE_DOCS}#stage-2-simnibs-charm-head-model-creation`,
  },
  run_fastsurfer: {
    id: "run_fastsurfer",
    stage: "G2b",
    title: "FastSurfer segmentation",
    text:
      "Optional. A FreeSurfer-style **DKT** cortical/subcortical parcellation, without the multi-hour " +
      "`recon-all` it replaces. Runs `--seg_only`: segmentation only, no surface reconstruction. It " +
      "reads the raw BIDS T1w, so it does not wait for charm — the two run in parallel.",
    inputs: [{ label: "T1w image", path: "sub-<id>/anat/sub-<id>_T1w.nii.gz" }],
    process: [{ label: "FastSurfer --seg_only" }],
    outputs: [
      { label: "DKT parcellation", path: "derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep.mgz" },
      { label: "NIfTI copy", path: "derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep.nii.gz" },
      { label: "Label sidecar", path: "derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep_labels.txt" },
    ],
    nativeMinutes: native("G2b"),
    docsHref: `${PRE_DOCS}#stage-3-fastsurfer-segmentation-optional`,
  },
  run_tissue_analysis: {
    id: "run_tissue_analysis",
    stage: "G3",
    title: "Tissue analyzer",
    text:
      "Measures **CSF**, **bone** and **skin** from charm's labelling: per-tissue volume and thickness, " +
      "plus a thickness map and a methodology figure. Needs charm's segmentation, so it runs after it.",
    inputs: [{ label: "Tissue labels", path: "m2m_<id>/segmentation/labeling.nii.gz" }],
    process: [{ label: "tissue analyzer" }],
    outputs: [
      { label: "Volumes report", path: "derivatives/ti-toolbox/tissue_analysis/sub-<id>/<tissue>_analysis.txt" },
      { label: "Thickness map", path: "derivatives/ti-toolbox/tissue_analysis/sub-<id>/<tissue>_thickness.png" },
    ],
    nativeMinutes: native("G3"),
    docsHref: `${PRE_DOCS}#processing-stages`,
  },
  run_qsiprep: {
    id: "run_qsiprep",
    stage: "G4",
    title: "QSIPrep",
    text:
      "Preprocesses the raw diffusion series — denoising, Gibbs unringing, distortion and motion " +
      "correction, and resampling to an ACPC-aligned grid. Runs in the **QSIPrep container**, so the " +
      "toolbox needs Docker socket access. The longest step in pre-processing by a wide margin.",
    inputs: [
      { label: "Raw DWI + bval/bvec", path: "sub-<id>/dwi/" },
      { label: "T1w image", path: "sub-<id>/anat/sub-<id>_T1w.nii.gz" },
    ],
    process: [{ label: "QSIPrep (docker)" }],
    outputs: [
      { label: "Preprocessed DWI", path: "derivatives/qsiprep/sub-<id>/" },
      { label: "Work dir (kept for reruns)", path: "derivatives/.qsiprep_work/" },
    ],
    nativeMinutes: native("G4"),
    docsHref: DWI_DOCS,
  },
  run_qsirecon: {
    id: "run_qsirecon",
    stage: "G5",
    title: "QSIRecon",
    text:
      "Reconstructs the preprocessed DWI into model maps. The tensor extraction below expects the " +
      "`dsi_studio_gqi` pipeline, so leave it selected unless you only want the other maps. Runs in " +
      "the **QSIRecon container** and needs QSIPrep output.",
    inputs: [{ label: "Preprocessed DWI", path: "derivatives/qsiprep/sub-<id>/" }],
    process: [{ label: "QSIRecon (docker)" }],
    outputs: [{ label: "DTI / recon maps", path: "derivatives/qsirecon/sub-<id>/" }],
    nativeMinutes: native("G5"),
    docsHref: DWI_DOCS,
  },
  extract_dti: {
    id: "extract_dti",
    stage: "G6",
    title: "Extract DTI tensor",
    text:
      "Takes QSIRecon's tensor, registers it from ACPC space into the SimNIBS T1 space and writes it " +
      "where SimNIBS looks for it. This file is what makes an **anisotropic** conductivity simulation " +
      "possible. Needs both QSIRecon output and `charm`.",
    inputs: [
      { label: "DSI Studio tensor", path: "derivatives/qsirecon/sub-<id>/" },
      { label: "SimNIBS T1", path: "m2m_<id>/T1.nii.gz" },
    ],
    process: [{ label: "extract tensor" }, { label: "register to T1" }],
    outputs: [
      { label: "DTI conductivity tensor", path: "m2m_<id>/DTI_coregT1_tensor.nii.gz" },
      { label: "ACPC tensor (intermediate)", path: "m2m_<id>/DTI_ACPC_tensor.nii.gz" },
    ],
    nativeMinutes: native("G6"),
    docsHref: DWI_DOCS,
  },
};

/**
 * The flow as columns of nodes plus the arrows between them: inputs fan in to the first process
 * box, process boxes chain, and the last one fans out to the outputs.
 *
 * Returned rather than stored so an author only writes the three lists; the ids and the edges are
 * derived, which is what stops a hand-written edge from pointing at a node that no longer exists.
 */
export function stepGraph(info: StepInfo): { columns: StepNode[][]; edges: StepEdge[] } {
  const inputs: StepNode[] = info.inputs.map((n, i) => ({ ...n, id: `in-${i}`, kind: "input" }));
  const process: StepNode[] = info.process.map((n, i) => ({ ...n, id: `proc-${i}`, kind: "process" }));
  const outputs: StepNode[] = info.outputs.map((n, i) => ({ ...n, id: `out-${i}`, kind: "output" }));

  const edges: StepEdge[] = [];
  const first = process[0]!;
  const last = process[process.length - 1]!;
  for (const node of inputs) edges.push([node.id, first.id]);
  for (let i = 1; i < process.length; i++) edges.push([process[i - 1]!.id, process[i]!.id]);
  for (const node of outputs) edges.push([last.id, node.id]);

  return { columns: [inputs, ...process.map((p) => [p]), outputs], edges };
}

/** Every concrete path the step names, inputs then outputs. */
export function stepPaths(info: StepInfo): string[] {
  return [...info.inputs, ...info.outputs].map((n) => n.path).filter((p): p is string => !!p);
}

/** "≈15 min (≈45 min emulated)" — both, because the emulated one is what many readers will see. */
export function durationLabel(nativeMinutes: number): string {
  const round = (m: number) => (m < 1 ? "<1" : String(Math.round(m)));
  return `≈${round(nativeMinutes)} min (≈${round(nativeMinutes * EMULATION_FACTOR)} min emulated)`;
}

const COLUMN_CAPTION: Record<NodeKind, string> = { input: "inputs", process: "process", output: "outputs" };

function NodeGlyph({ kind }: { kind: NodeKind }) {
  const Icon = kind === "input" ? FileInput : kind === "output" ? FileOutput : Cog;
  return <Icon size={13} className="flow-node-glyph" aria-hidden />;
}

function FlowArrow() {
  // Decorative: the reading order already says which way it goes, and every node is real text.
  return (
    <div className="flow-arrow" aria-hidden>
      <svg viewBox="0 0 24 10" preserveAspectRatio="none" focusable="false">
        <path d="M0 5 H18" />
        <path d="M24 5 l-7 -4 v8 z" className="flow-arrow-head" />
      </svg>
    </div>
  );
}

/**
 * `inputs → [process] → outputs` as connected boxes.
 *
 * CSS grid rather than SVG: the labels and paths stay real, selectable text (so they are also what
 * a test and a screen reader see), they wrap and ellipsise on their own, and the colours come from
 * `preprocess.css`'s tokens in both themes.
 */
export function StepFlow({ info }: { info: StepInfo }) {
  const { columns } = stepGraph(info);
  return (
    <div
      className="step-flow"
      data-testid="step-diagram"
      role="group"
      aria-label={`${info.inputs.map((n) => n.label).join(", ")} to ${info.process
        .map((n) => n.label)
        .join(" then ")} to ${info.outputs.map((n) => n.label).join(", ")}`}
    >
      {columns.map((column, ci) => (
        <div className="step-flow-group" key={ci}>
          {ci > 0 && <FlowArrow />}
          <div className={`flow-col flow-col-${column[0]!.kind}`}>
            {/* One caption per role, not per column — a chained process is still "process". */}
            {(ci === 0 || ci === columns.length - 1 || ci === 1) && (
              <div className="flow-caption">{COLUMN_CAPTION[column[0]!.kind]}</div>
            )}
            {column.map((node) => (
              <div className={`flow-node flow-node-${node.kind}`} key={node.id} data-node-id={node.id}>
                <div className="flow-node-head">
                  <NodeGlyph kind={node.kind} />
                  <span className="flow-node-label">{node.label}</span>
                </div>
                {node.path && (
                  // Full path in `title`: the box is sized to the popover, and a BIDS derivative
                  // path is longer than any box that fits next to two others.
                  <span className="flow-node-path" title={node.path}>
                    {node.path}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReadMore({ href }: { href: string }) {
  if (isElectron) {
    return (
      <button type="button" className="help-more" onClick={() => void window.tit?.openExternal(href)}>
        Read more <ExternalLink size={10} aria-hidden />
      </button>
    );
  }
  return (
    <a className="help-more" href={href} target="_blank" rel="noreferrer">
      Read more <ExternalLink size={10} aria-hidden />
    </a>
  );
}

/**
 * The (i) next to a stage row or a section header: click opens the explainer, the flow, the
 * duration and a link into the wiki. Nothing here happens on hover.
 */
export function StepHelpIcon({ id, size = 13 }: { id: string; size?: number }): ReactNode {
  const info = STEP_INFO[id];
  if (!info) return null;
  return (
    <HelpIcon
      title={info.title}
      text={info.text}
      label={`About ${info.title}`}
      size={size}
      testId={`step-help-${id}`}
    >
      <StepFlow info={info} />
      <div className="help-footer">
        {info.nativeMinutes !== undefined && (
          <span className="help-duration" data-testid="step-duration">
            {durationLabel(info.nativeMinutes)}
          </span>
        )}
        <ReadMore href={info.docsHref} />
      </div>
    </HelpIcon>
  );
}
