import type { PreprocessConfig } from "./api";

export function defaultConfig(): PreprocessConfig {
  return {
    subject_ids: [],
    // These match `pre_process_tab.py`'s Qt defaults (checked out of the box), not the bare
    // schema default (false) — see PARITY.md.
    convert_dicom: true,
    run_fastsurfer: true,
    run_freesurfer: false,
    freesurfer_recon_all: true,
    freesurfer_subregions: ["thalamus", "hippo-amygdala"],
    freesurfer_threads: null,
    charm_options: null,
    charm_threads: null,
    fastsurfer_threads: null,
    create_m2m: true,
    run_tissue_analysis: false,
    run_qsiprep: false,
    run_qsirecon: false,
    qsiprep_config: null,
    qsi_recon_config: null,
    extract_dti: false,
    skip_existing_outputs: true,
    replace_existing_outputs: false,
  };
}

