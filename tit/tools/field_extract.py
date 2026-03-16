"""
Field extraction utilities for TI-Toolbox.

Extracts grey and white matter meshes from a full SimNIBS head mesh.
"""

import logging
import os

from simnibs import mesh_io

logger = logging.getLogger(__name__)


def main(
    input_file,
    project_dir=None,
    subject_id=None,
    gm_output_file=None,
    wm_output_file=None,
):
    """
    Load the original mesh, crop to grey matter (tag #2) and white matter
    (tag #1), and save to separate files.

    Directory structure (BIDS-compliant):
    project_dir/
    ├── sub-{subject_id}/
    └── derivatives/
        └── SimNIBS/
            └── sub-{subject_id}/
                ├── m2m_{subject_id}/
                └── Simulations/

    Parameters
    ----------
    input_file : str
        Path to the input mesh file.
    project_dir : str, optional
        Path to the project directory (BIDS structure).
    subject_id : str, optional
        Subject ID (without "sub-" prefix).
    gm_output_file : str, optional
        Path to the output grey matter mesh file.
    wm_output_file : str, optional
        Path to the output white matter mesh file.
    """
    full_mesh = mesh_io.read_msh(input_file)
    gm_mesh = full_mesh.crop_mesh(tags=[2])
    wm_mesh = full_mesh.crop_mesh(tags=[1])

    if project_dir and subject_id:
        derivatives_dir = os.path.join(project_dir, "derivatives")
        simnibs_dir = os.path.join(derivatives_dir, "SimNIBS", f"sub-{subject_id}")
        output_base = os.path.join(simnibs_dir, "Simulations")
        os.makedirs(output_base, exist_ok=True)
        input_filename = os.path.basename(input_file)

        if gm_output_file is None:
            gm_output_file = os.path.join(
                output_base, f"sub-{subject_id}_space-MNI305_desc-grey_{input_filename}"
            )
        if wm_output_file is None:
            wm_output_file = os.path.join(
                output_base,
                f"sub-{subject_id}_space-MNI305_desc-white_{input_filename}",
            )
    else:
        # Use original directory structure
        input_dir = os.path.dirname(input_file)
        input_filename = os.path.basename(input_file)

        if gm_output_file is None:
            gm_output_file = os.path.join(input_dir, "grey_" + input_filename)
        if wm_output_file is None:
            wm_output_file = os.path.join(input_dir, "white_" + input_filename)

    # Save grey matter mesh
    mesh_io.write_msh(gm_mesh, gm_output_file)
    logger.info("Grey matter mesh saved to %s", gm_output_file)

    # Save white matter mesh
    mesh_io.write_msh(wm_mesh, wm_output_file)
    logger.info("White matter mesh saved to %s", wm_output_file)
