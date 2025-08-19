#!/usr/bin/env python3
"""
Average all NIfTI files in a directory (if they share the same dimensions).

Usage:
  python utils/average_nifti_dir.py /path/to/dir --output average.nii.gz

Requires: nibabel, numpy
"""

import argparse
import glob
import os
from typing import List

import nibabel as nib
import numpy as np


def find_nifti_files(directory: str, pattern: str = "*.nii*") -> List[str]:
    search_pattern = os.path.join(directory, pattern)
    files = sorted(glob.glob(search_pattern))
    return [f for f in files if f.lower().endswith((".nii", ".nii.gz"))]


def average_niftis(nifti_paths: List[str], output_path: str) -> str:
    if len(nifti_paths) < 2:
        raise ValueError("Need at least 2 NIfTI files to average")

    first_img = nib.load(nifti_paths[0])
    reference_shape = first_img.shape
    reference_affine = first_img.affine
    reference_header = first_img.header

    # Verify shapes (and affines for typical MNI consistency)
    valid_paths = []
    for p in nifti_paths:
        img = nib.load(p)
        if img.shape != reference_shape:
            raise ValueError(f"Shape mismatch: {os.path.basename(p)} has shape {img.shape}, expected {reference_shape}")
        # Affine check with small tolerance
        if not np.allclose(img.affine, reference_affine, atol=1e-6):
            raise ValueError(f"Affine mismatch: {os.path.basename(p)} has different affine than reference")
        valid_paths.append(p)

    # Stack and compute mean
    data_stack = []
    for p in valid_paths:
        data = nib.load(p).get_fdata(dtype=np.float64)
        data_stack.append(data)
    mean_data = np.mean(np.stack(data_stack, axis=0), axis=0)

    out_img = nib.Nifti1Image(mean_data, reference_affine, header=reference_header)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    nib.save(out_img, output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Average all NIfTI files in a directory if they share the same dimensions")
    parser.add_argument("directory", help="Directory containing .nii/.nii.gz files")
    parser.add_argument("--output", "-o", default=None, help="Path for the averaged output (.nii or .nii.gz)")
    parser.add_argument("--pattern", default="*.nii*", help="Glob pattern to match NIfTI files (default: *.nii*)")
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        raise FileNotFoundError(f"Directory not found: {args.directory}")

    nifti_paths = find_nifti_files(args.directory, args.pattern)
    if not nifti_paths:
        raise FileNotFoundError(f"No NIfTI files found in: {args.directory}")

    output_path = args.output
    if output_path is None:
        # default inside the input directory
        output_path = os.path.join(args.directory, "average.nii.gz")

    result_path = average_niftis(nifti_paths, output_path)
    print(f"Saved averaged NIfTI: {result_path}")


if __name__ == "__main__":
    main()


