/**
 * QSIPrep/QSIRecon dialog data and defaults, ported from
 * `tit/gui/components/qsi_config_dialogs.py` (categorised spec/atlas lists, tooltips, defaults).
 *
 * `PreprocessConfig.qsiprep_config`/`qsi_recon_config` hold the settings-only `QSIPrepSettings`/
 * `QSIReconSettings` shapes (B4, landed mid-build): no `subject_id`, resource fields flat
 * (`cpus`/`memory_gb`/`omp_threads` directly on the object, not nested under `resources`).
 */
import type { SurferSettings } from "../settings/api";
import type { QsiPrepSettings, QsiReconSettings } from "./api";

export interface CategoryItem {
  value: string;
  label: string;
  tooltip: string;
}

export interface Category {
  title: string;
  hint: string;
  items: CategoryItem[];
}

export const DEFAULT_RECON_SPEC = "dsi_studio_gqi";
export const DEFAULT_QSIPREP_IMAGE_TAG = "26.0.0";
export const DEFAULT_QSIRECON_IMAGE_TAG = "26.0.0";

export const SPEC_CATEGORIES: Category[] = [
  {
    title: "DTI / scalar extraction",
    hint: "Produces tensor components for SimNIBS anisotropic modeling.",
    items: [
      {
        value: "dsi_studio_gqi",
        label: "dsi_studio_gqi",
        tooltip:
          "GQI + deterministic tractography. Outputs tensor components (txx-tzz), QA, GFA, ISO.",
      },
    ],
  },
  {
    title: "Tractography — MRtrix3",
    hint: "CSD-based probabilistic tractography (iFOD2, 10M streamlines, SIFT2).",
    items: [
      {
        value: "mrtrix_multishell_msmt_ACT-hsvs",
        label: "mrtrix_multishell_msmt_ACT-hsvs",
        tooltip:
          "Multi-shell MSMT CSD, ACT with hybrid surface-volume segmentation. Requires FreeSurfer.",
      },
      {
        value: "mrtrix_multishell_msmt_ACT-fast",
        label: "mrtrix_multishell_msmt_ACT-fast",
        tooltip:
          "Multi-shell MSMT CSD, ACT with FSL FAST segmentation. Requires FreeSurfer.",
      },
      {
        value: "mrtrix_multishell_msmt_noACT",
        label: "mrtrix_multishell_msmt_noACT",
        tooltip: "Multi-shell MSMT CSD, no anatomical constraints.",
      },
      {
        value: "mrtrix_singleshell_ss3t_ACT-hsvs",
        label: "mrtrix_singleshell_ss3t_ACT-hsvs",
        tooltip:
          "Single-shell SS3T CSD, ACT with HSVS segmentation. Requires FreeSurfer.",
      },
      {
        value: "mrtrix_singleshell_ss3t_ACT-fast",
        label: "mrtrix_singleshell_ss3t_ACT-fast",
        tooltip:
          "Single-shell SS3T CSD, ACT with FSL FAST segmentation. Requires FreeSurfer.",
      },
      {
        value: "mrtrix_singleshell_ss3t_noACT",
        label: "mrtrix_singleshell_ss3t_noACT",
        tooltip: "Single-shell SS3T CSD, no anatomical constraints.",
      },
    ],
  },
  {
    title: "Tractography — bundle identification",
    hint: "Automated white-matter tract recognition.",
    items: [
      {
        value: "dsi_studio_autotrack",
        label: "dsi_studio_autotrack",
        tooltip:
          "QSDR + AutoTrack: identifies 56 white-matter bundles in MNI space.",
      },
      {
        value: "pyafq_tractometry",
        label: "pyafq_tractometry",
        tooltip:
          "Automated Fiber Quantification (PyAFQ): recognizes major WM pathways.",
      },
      {
        value: "mrtrix_multishell_msmt_pyafq_tractometry",
        label: "mrtrix_multishell_msmt_pyafq_tractometry",
        tooltip:
          "MRtrix3 CSD tractography combined with PyAFQ bundle analysis.",
      },
      {
        value: "ss3t_fod_autotrack",
        label: "ss3t_fod_autotrack",
        tooltip: "Single-shell FOD variant of DSI Studio AutoTrack.",
      },
    ],
  },
  {
    title: "Microstructural models",
    hint: "Voxel-wise diffusion model fitting (no tractography).",
    items: [
      {
        value: "dipy_dki",
        label: "dipy_dki",
        tooltip:
          "Diffusion Kurtosis Imaging: AK, RK, MK, KFA, plus all DTI scalars (FA, MD, AD, RD).",
      },
      {
        value: "dipy_mapmri",
        label: "dipy_mapmri",
        tooltip:
          "MAP-MRI: ensemble average propagator estimation. Outputs RTOP, RTAP, QIV, MSD + ODFs.",
      },
      {
        value: "dipy_3dshore",
        label: "dipy_3dshore",
        tooltip: "3dSHORE (BrainSuite): anisotropy scalars + ODFs.",
      },
      {
        value: "amico_noddi",
        label: "amico_noddi",
        tooltip: "NODDI via AMICO framework: ICVF, ISOVF, OD scalars.",
      },
      {
        value: "TORTOISE",
        label: "TORTOISE",
        tooltip: "TORTOISE tensor fitting + MAPMRI: NG, PA, RTOP, RTAP.",
      },
    ],
  },
  {
    title: "Composite pipelines",
    hint: "Run multiple models in one pass. These subsume individual specs above.",
    items: [
      {
        value: "multishell_scalarfest",
        label: "multishell_scalarfest",
        tooltip:
          "DKI + TORTOISE + GQI + NODDI, no tractography. Subsumes: dipy_dki, TORTOISE, dsi_studio_gqi, amico_noddi.",
      },
      {
        value: "hbcd_scalar_maps",
        label: "hbcd_scalar_maps",
        tooltip:
          "DKI + TORTOISE + GQI + DSI AutoTrack. Subsumes: dipy_dki, TORTOISE, dsi_studio_gqi, dsi_studio_autotrack.",
      },
      {
        value: "abcd_recon",
        label: "abcd_recon",
        tooltip: "ABCD study-specific composite reconstruction.",
      },
    ],
  },
  {
    title: "Utility / experimental",
    hint: "",
    items: [
      {
        value: "reorient_fslstd",
        label: "reorient_fslstd",
        tooltip:
          "Reorient preprocessed DWI to FSL standard orientation (no model fitting).",
      },
      {
        value: "csdsi_3dshore",
        label: "csdsi_3dshore",
        tooltip:
          "Experimental: for DSI/CS-DSI data. Imputes a multi-shell HCP sampling scheme.",
      },
    ],
  },
];

export const ATLAS_CATEGORIES: Category[] = [
  {
    title: "4S series — Schaefer cortical + 56 subcortical ROIs",
    hint: "Resolution variants of the same parcellation. The 56 subcortical regions come from CIT168, HCP Thalamus, HCP Amygdala/Hippocampus, and MDTB Cerebellum.",
    items: [
      {
        value: "4S156Parcels",
        label: "4S156Parcels",
        tooltip: "Schaefer 100 cortical + 56 subcortical",
      },
      {
        value: "4S256Parcels",
        label: "4S256Parcels",
        tooltip: "Schaefer 200 + 56 subcortical",
      },
      {
        value: "4S356Parcels",
        label: "4S356Parcels",
        tooltip: "Schaefer 300 + 56 subcortical",
      },
      {
        value: "4S456Parcels",
        label: "4S456Parcels",
        tooltip: "Schaefer 400 + 56 subcortical",
      },
      {
        value: "4S556Parcels",
        label: "4S556Parcels",
        tooltip: "Schaefer 500 + 56 subcortical",
      },
      {
        value: "4S656Parcels",
        label: "4S656Parcels",
        tooltip: "Schaefer 600 + 56 subcortical",
      },
      {
        value: "4S756Parcels",
        label: "4S756Parcels",
        tooltip: "Schaefer 700 + 56 subcortical",
      },
      {
        value: "4S856Parcels",
        label: "4S856Parcels",
        tooltip: "Schaefer 800 + 56 subcortical",
      },
      {
        value: "4S956Parcels",
        label: "4S956Parcels",
        tooltip: "Schaefer 900 + 56 subcortical",
      },
      {
        value: "4S1056Parcels",
        label: "4S1056Parcels",
        tooltip: "Schaefer 1000 + 56 subcortical",
      },
    ],
  },
  {
    title: "Classic atlases (extended with subcortical regions)",
    hint: "",
    items: [
      {
        value: "AAL116",
        label: "AAL116",
        tooltip:
          "Automated Anatomical Labeling: 116 macro-anatomical regions (Tzourio-Mazoyer et al. 2002).",
      },
      {
        value: "Brainnetome246Ext",
        label: "Brainnetome246Ext",
        tooltip:
          "Connectivity-based parcellation: 246 regions (Fan et al. 2016).",
      },
      {
        value: "AICHA384Ext",
        label: "AICHA384Ext",
        tooltip:
          "Homotopic connectivity atlas: 384 regions (Joliot et al. 2015).",
      },
      {
        value: "Gordon333Ext",
        label: "Gordon333Ext",
        tooltip:
          "Resting-state fMRI boundary mapping: 333 regions (Gordon et al. 2016).",
      },
    ],
  },
];

/**
 * Qt pre-fills CPUs/Memory from `get_inherited_dood_resources()` (current container limits); no
 * v1 endpoint exposes that to the renderer (PARITY.md gap #2), so both default to "auto" (`null`)
 * — the settings' own schema default, which the backend resolves at run time.
 */
export function defaultQsiPrepConfig(): QsiPrepSettings {
  return {
    output_resolution: 2.0,
    cpus: null,
    memory_gb: null,
    omp_threads: 8,
    image_tag: DEFAULT_QSIPREP_IMAGE_TAG,
    skip_bids_validation: true,
    denoise_method: "dwidenoise",
    unringing_method: "mrdegibbs",
  };
}

export function defaultQsiReconConfig(): QsiReconSettings {
  return {
    recon_specs: [DEFAULT_RECON_SPEC],
    atlases: null,
    use_gpu: false,
    cpus: null,
    memory_gb: null,
    omp_threads: 8,
    image_tag: DEFAULT_QSIRECON_IMAGE_TAG,
    skip_odf_reports: true,
  };
}

export const DENOISE_METHODS = ["dwidenoise", "patch2self", "none"];
export const UNRINGING_METHODS = ["mrdegibbs", "rpg", "none"];

export function qsiPrepPreferences(config: QsiPrepSettings): SurferSettings["qsiprep_config"] {
  const { output_resolution, image_tag, skip_bids_validation, denoise_method, unringing_method } = config;
  if (denoise_method !== "dwidenoise" && denoise_method !== "patch2self" && denoise_method !== "none") throw new Error("Unsupported denoise method");
  if (unringing_method !== "mrdegibbs" && unringing_method !== "rpg" && unringing_method !== "none") throw new Error("Unsupported unringing method");
  return { output_resolution, image_tag, skip_bids_validation, denoise_method, unringing_method };
}
export function qsiReconPreferences(config: QsiReconSettings): SurferSettings["qsi_recon_config"] {
  const { recon_specs, atlases, use_gpu, image_tag, skip_odf_reports } = config;
  return { recon_specs: recon_specs ?? [DEFAULT_RECON_SPEC], atlases, use_gpu, image_tag, skip_odf_reports };
}
