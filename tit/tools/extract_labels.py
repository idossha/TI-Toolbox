#!/usr/bin/env python3
"""Extract specific labels from a NIfTI segmentation file.

Reads a NIfTI volume, masks all voxels whose integer label is not in
the requested set, and writes the result as a new NIfTI file.

Usage
-----
>>> from tit.tools.extract_labels import extract_labels
>>> out = extract_labels("seg.nii.gz", [10, 11, 12])

See Also
--------
tit.tools.field_extract : Extract tissue meshes from a SimNIBS head mesh.
"""

import nibabel as nib
import numpy as np
from pathlib import Path


def extract_labels(input_file, labels, output_file=None):
    """
    Extract specific labels from a NIfTI segmentation file.

    Parameters
    ----------
    input_file : str or Path
        Path to input NIfTI file
    labels : list of int
        List of label values to extract
    output_file : str or Path, optional
        Path to output NIfTI file. If None, defaults to input_file with '_extracted' suffix

    Returns
    -------
    str
        Path to the output file
    """
    input_path = Path(input_file)

    if output_file is None:
        output_file = (
            input_path.parent / f"{input_path.stem}_extracted{input_path.suffix}"
        )

    output_path = Path(output_file)

    img = nib.load(str(input_path))
    data = img.get_fdata()

    mask = np.isin(data, labels)
    output_data = np.where(mask, data, 0).astype(np.int16)

    out_img = nib.Nifti1Image(output_data, img.affine, img.header)
    nib.save(out_img, str(output_path))

    return str(output_path)
