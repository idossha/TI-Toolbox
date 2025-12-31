#!/usr/bin/env python3
"""Extract specific labels from a NIfTI segmentation file."""

import argparse
import nibabel as nib
import numpy as np
from pathlib import Path


def extract_labels_from_nifti(input_file, labels, output_file=None):
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
        output_file = input_path.parent / f"{input_path.stem}_extracted{input_path.suffix}"

    output_path = Path(output_file)

    # Load NIfTI
    img = nib.load(str(input_path))
    data = img.get_fdata()

    # Create mask for selected labels
    mask = np.isin(data, labels)
    output_data = np.where(mask, data, 0).astype(np.int16)

    # Save
    out_img = nib.Nifti1Image(output_data, img.affine, img.header)
    nib.save(out_img, str(output_path))

    return str(output_path)


def main():
    """Command-line interface for extracting labels from NIfTI files."""
    parser = argparse.ArgumentParser(
        description="Extract specific labels from a NIfTI segmentation file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s segmentation.nii.gz "10,49" -o thalamus_striatum.nii.gz
  %(prog)s labeling.nii.gz "1,2,3,4"  # outputs labeling_extracted.nii.gz
        """
    )
    parser.add_argument("input", help="Input NIfTI segmentation file")
    parser.add_argument("labels", help="Comma-separated list of labels to extract (e.g., '10,49')")
    parser.add_argument("-o", "--output", help="Output NIfTI file (default: <input>_extracted.nii.gz)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose output")

    args = parser.parse_args()

    # Parse and validate labels
    try:
        labels = [int(l.strip()) for l in args.labels.split(",")]
        if not labels:
            parser.error("At least one label must be specified")
    except ValueError as e:
        parser.error(f"Invalid label format: {e}")

    # Extract labels
    try:
        output_file = extract_labels_from_nifti(args.input, labels, args.output)

        if args.verbose:
            print(f"Input file: {args.input}")
            print(f"Extracted labels: {labels}")
            print(f"Output file: {output_file}")
        else:
            print(f"Extracted labels {labels} -> {output_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
