---
name: troubleshoot-project
description: Diagnose a TI-Toolbox project directory — which subjects, head models, simulations, optimizations and reports exist, and what is missing for the user's goal.
argument-hint: [project-root] [subject-id]
---

# Troubleshoot a TI-Toolbox project

Arguments: `$ARGUMENTS` = `<project-root> [subject-id]`. If no project root is
given, ask for it (inside the container it is `/mnt/<project>`; on the host it is
the folder the desktop app was pointed at).

1. Call MCP `inspect_project(project_root, subject?)`.
2. For each subject, walk the pipeline and report the first missing stage:
   - `anat_files` empty → needs DICOM/NIfTI import (`pre-processing` wiki).
   - `has_m2m` false / `has_head_mesh` false → CHARM not run or failed; check
     `derivatives/SimNIBS/sub-<id>/m2m_<id>/charm_log.html`.
   - `freesurfer_recon` false → atlas/cortical ROI features unavailable.
   - `leadfields` empty → ex-search cannot run; make a leadfield first (wiki `ex-search`).
   - Simulation without `mesh_files`/`nifti_files` → run failed; ask for the log under
     `derivatives/ti-toolbox/logs/` or the simulation folder.
   - `qsirecon` false but user wants `vn|dir|mc` conductivity → needs diffusion processing.
3. If the user asks about a montage, call `read_project_config(project_root, "montage_list.json")`
   and confirm the name and EEG net exist.
4. Summarise as a short table: subject → stages present/missing → next action, each
   with the relevant wiki slug. Do not modify any files.
