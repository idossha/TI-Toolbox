"""Sub-cortical mesh export -- STL + MSH geometry, and a field-coloured PLY.

The v2.5.0 GUI ran this inline on the Qt main thread
(``tit/gui/extensions/visual_exporter.py``'s ``_run`` sub-cortical branch), so a
long export froze the window and left no trace in any job list.  The code below
is that branch, unchanged in every step that touches the filesystem -- the same
``extract_labels`` / ``nifti_to_mesh`` / ``nifti_to_field_ply`` calls in the same
order, the same ``subcortical_<suffix>.{stl,msh,ply,nii.gz}`` names, the same
``clean_threshold=0.1`` -- lifted into a function a ``blender`` job can run.

See Also
--------
tit.blender.config.SubcorticalConfig : The configuration it consumes.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil

from tit import constants as const
from tit.blender.config import SubcorticalConfig

logger = logging.getLogger(__name__)


def _visual_exports_dir(project_dir: str, subject_id: str) -> str:
    """``derivatives/ti-toolbox/visual_exports/sub-<id>/sub-cortical``, created."""
    out_base = os.path.join(
        project_dir,
        const.DIR_DERIVATIVES,
        const.DIR_TI_TOOLBOX,
        "visual_exports",
        f"{const.PREFIX_SUBJECT}{subject_id}",
        "sub-cortical",
    )
    os.makedirs(out_base, exist_ok=True)
    return out_base


def find_field_nifti(sim_dir: str | None, field_name: str) -> str | None:
    """First ``*_subject_<field>.nii.gz`` under *sim_dir*, or ``None``.

    Same glob the Qt widget's ``_find_field_nifti`` used, including the sort
    that makes "first match" deterministic.
    """
    if not sim_dir or not os.path.isdir(sim_dir):
        return None
    pattern = os.path.join(sim_dir, "**", f"*_subject_{field_name}.nii.gz")
    matches = sorted(glob.glob(pattern, recursive=True))
    return matches[0] if matches else None


def output_suffix(labels: list[int], clean_components: bool) -> str:
    """``labels_10_49_clean`` / ``full_raw`` -- the 2.5.0 filename suffix rule."""
    if labels:
        parts = ["labels_" + "_".join(str(v) for v in sorted(labels))]
    else:
        parts = ["full"]
    parts.append("clean" if clean_components else "raw")
    return "_".join(parts)


def run_subcortical(
    config: SubcorticalConfig, logger_override: logging.Logger | None = None
) -> str:
    """Export sub-cortical geometry for one subject; return the output directory."""
    log = logger_override or logger
    from tit.paths import get_path_manager
    from tit.tools.extract_labels import extract_labels
    from tit.tools.nifti_to_mesh import nifti_to_mesh, nifti_to_field_ply

    pm = get_path_manager()

    nifti_path = (config.nifti_path or "").strip()
    if not nifti_path:
        m2m_dir = pm.m2m(config.subject_id)
        if not m2m_dir or not os.path.isdir(m2m_dir):
            raise ValueError(
                "Could not determine default NIfTI path. Please specify manually."
            )
        nifti_path = os.path.join(m2m_dir, "segmentation", "labeling.nii.gz")
    if not os.path.exists(nifti_path):
        raise ValueError(f"NIfTI file not found: {nifti_path}")
    log.info(f"NIfTI file: {nifti_path}")

    output_dir = config.output_dir or _visual_exports_dir(
        pm.project_dir, config.subject_id
    )
    os.makedirs(output_dir, exist_ok=True)
    config.output_dir = output_dir
    log.info(f"Output directory: {output_dir}")

    labels = list(config.labels)
    clean_components = config.clean_components
    if labels:
        log.info(f"Extracting labels: {labels}")
    if clean_components:
        log.info("Will remove small disconnected components")

    temp_nifti = os.path.join(output_dir, "temp_extracted.nii.gz")
    try:
        if labels:
            input_file = extract_labels(nifti_path, labels, temp_nifti)
            log.info(f"Extracted labels to: {input_file}")
        else:
            input_file = nifti_path

        suffix = output_suffix(labels, clean_components)

        stl_output = os.path.join(output_dir, f"subcortical_{suffix}.stl")
        log.info("Generating STL mesh...")
        stl_result = nifti_to_mesh(
            input_file, stl_output, clean_components=clean_components, clean_threshold=0.1
        )
        log.info(
            f"STL created: {stl_result['output_file']} "
            f"({stl_result['vertices']} vertices, {stl_result['faces']} faces)"
        )
        if stl_result["removed_components"] > 0:
            log.info(f"Removed {stl_result['removed_components']} small components")

        msh_output = os.path.join(output_dir, f"subcortical_{suffix}.msh")
        log.info("Generating MSH mesh...")
        msh_result = nifti_to_mesh(
            input_file, msh_output, clean_components=clean_components, clean_threshold=0.1
        )
        log.info(
            f"MSH created: {msh_result['output_file']} "
            f"({msh_result['vertices']} vertices, {msh_result['faces']} faces)"
        )
        if msh_result["removed_components"] > 0:
            log.info(f"Removed {msh_result['removed_components']} small components")

        field_name = config.field_name or "TI_max"
        field_nifti = None
        if config.simulation_name:
            field_nifti = find_field_nifti(
                pm.simulation(config.subject_id, config.simulation_name), field_name
            )
        if field_nifti:
            ply_output = os.path.join(output_dir, f"subcortical_{suffix}.ply")
            log.info(f"Generating field-coloured PLY from {field_name}...")
            ply_result = nifti_to_field_ply(
                input_file,
                field_nifti,
                ply_output,
                field_name=field_name,
                clean_components=clean_components,
                clean_threshold=0.1,
            )
            log.info(
                f"PLY created: {ply_result['output_file']} "
                f"({ply_result['vertices']} vertices, "
                f"{ply_result['faces']} faces; "
                f"{field_name} range "
                f"{ply_result['field_min']:.3f}-{ply_result['field_max']:.3f})"
            )
        elif config.simulation_name:
            log.warning(
                f"No '{field_name}' subject-space field volume found "
                f"for simulation '{config.simulation_name}'; skipping PLY export."
            )
        else:
            log.info("No simulation selected; skipping field-coloured PLY export.")

        nifti_copy_path = os.path.join(output_dir, f"subcortical_{suffix}.nii.gz")
        shutil.copy2(input_file, nifti_copy_path)
        log.info(f"Saved NIfTI file: {nifti_copy_path}")
    finally:
        # The temp extraction is scratch, on success and on failure alike -- 2.5.0
        # removed it in both paths, and leaving it behind would make the next run's
        # artifact listing report a file no user asked for.
        if labels and os.path.exists(temp_nifti):
            try:
                os.remove(temp_nifti)
            except OSError:
                pass

    return output_dir
