#!/usr/bin/env simnibs_python
"""
Post-hoc atlas overlap analysis for existing significant voxel masks

This script allows you to test an existing significant voxel mask against
one or more atlases without re-running the full statistical analysis.

Usage:
    python posthoc_atlas_analysis.py --mask <mask_file> --atlases <atlas1> <atlas2> ...

Or edit the configuration section below and run:
    python posthoc_atlas_analysis.py
"""

import numpy as np
import pandas as pd
import nibabel as nib

import os
import sys
import argparse

from tit.atlas import atlas_overlap_analysis


def posthoc_atlas_overlap(mask_file, atlas_files, output_dir=None):
    """
    Perform atlas overlap analysis on an existing significant voxel mask

    Parameters:
    -----------
    mask_file : str
        Path to binary mask NIfTI file
    atlas_files : list of str
        Paths to atlas NIfTI files
    output_dir : str, optional
        Directory to save CSV outputs (defaults to mask file directory)
    """

    print("=" * 70)
    print("POST-HOC ATLAS OVERLAP ANALYSIS")
    print("=" * 70)

    # Load mask
    print(f"\nLoading mask: {mask_file}")
    mask_img = nib.load(mask_file)
    sig_mask = mask_img.get_fdata().astype(bool)

    total_sig_voxels = np.sum(sig_mask)
    print(f"Total significant voxels: {total_sig_voxels}")

    if total_sig_voxels == 0:
        print("Warning: No significant voxels in mask!")
        return

    # Set output directory
    if output_dir is None:
        output_dir = os.path.dirname(mask_file)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Delegate overlap calculation to atlas_overlap_analysis
    # Group atlas files by directory so we can call the shared function
    dir_to_files: dict = {}
    for atlas_file in atlas_files:
        data_dir = os.path.dirname(atlas_file)
        basename = os.path.basename(atlas_file)
        dir_to_files.setdefault(data_dir, []).append(basename)

    overlap_results: dict = {}
    for data_dir, basenames in dir_to_files.items():
        partial = atlas_overlap_analysis(
            sig_mask,
            basenames,
            data_dir,
            reference_img=mask_img,
        )
        overlap_results.update(partial)

    # Process each atlas
    all_results = {}

    for atlas_file in atlas_files:
        atlas_name = os.path.basename(atlas_file)
        region_counts = overlap_results.get(atlas_name, [])

        # Enrich with percentage fields
        results = []
        for r in region_counts:
            pct_of_region = 100 * r["overlap_voxels"] / r["region_size"]
            pct_of_significant = 100 * r["overlap_voxels"] / total_sig_voxels
            results.append(
                {
                    "region_id": r["region_id"],
                    "overlap_voxels": r["overlap_voxels"],
                    "region_total_voxels": r["region_size"],
                    "pct_of_region": round(pct_of_region, 2),
                    "pct_of_all_significant": round(pct_of_significant, 2),
                }
            )

        if not results:
            print(f"No overlapping regions found for {atlas_name}")
            continue

        # Convert to DataFrame and sort
        df = pd.DataFrame(results)
        df = df.sort_values("overlap_voxels", ascending=False)

        # Save to CSV
        atlas_basename = os.path.splitext(os.path.basename(atlas_file))[0]
        if atlas_basename.endswith(".nii"):
            atlas_basename = os.path.splitext(atlas_basename)[0]

        output_file = os.path.join(output_dir, f"posthoc_overlap_{atlas_basename}.csv")
        df.to_csv(output_file, index=False)

        print(f"\n✓ Saved {len(df)} regions to: {output_file}")
        print(f"\nTop 10 regions by overlap:")
        for i, (idx, row) in enumerate(df.head(10).iterrows(), 1):
            print(
                f"  {i:2d}. Region {int(row['region_id']):4d}: "
                f"{int(row['overlap_voxels']):5d} voxels "
                f"({row['pct_of_region']:5.1f}% of region, "
                f"{row['pct_of_all_significant']:5.1f}% of sig. voxels)"
            )

        all_results[atlas_name] = df

    # Generate summary report
    summary_file = os.path.join(output_dir, "posthoc_atlas_summary.txt")
    with open(summary_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("POST-HOC ATLAS OVERLAP ANALYSIS SUMMARY\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Mask file: {mask_file}\n")
        f.write(f"Total significant voxels: {total_sig_voxels}\n\n")

        for atlas_name, df in all_results.items():
            f.write(f"\n{atlas_name}\n")
            f.write("-" * 70 + "\n")
            f.write(f"Regions with overlap: {len(df)}\n\n")
            f.write("Top 20 regions:\n")
            for i, (idx, row) in enumerate(df.head(20).iterrows(), 1):
                f.write(
                    f"{i:2d}. Region {int(row['region_id']):4d}: "
                    f"{int(row['overlap_voxels']):5d} voxels "
                    f"({row['pct_of_region']:5.1f}% of region)\n"
                )
            f.write("\n")

    print(f"\n{'='*70}")
    print("POST-HOC ANALYSIS COMPLETE!")
    print(f"{'='*70}")
    print(f"Summary saved to: {summary_file}")
    print(f"\nCSV files saved to: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Post-hoc atlas overlap analysis for significant voxel masks"
    )
    parser.add_argument("--mask", type=str, help="Path to binary mask NIfTI file")
    parser.add_argument(
        "--atlases", nargs="+", type=str, help="Paths to atlas NIfTI files"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for results (default: same as mask)",
    )

    args = parser.parse_args()

    # If no arguments provided, use default configuration
    if args.mask is None and args.atlases is None:
        print("No arguments provided. Using default configuration...")
        print("(Edit this script or use --mask and --atlases arguments)\n")

        # DEFAULT CONFIGURATION - EDIT THESE
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, "output")
        assets_dir = os.path.join(project_root, "assets")

        mask_file = os.path.join(output_dir, "significant_voxels_mask.nii.gz")

        # List all atlases you want to test
        atlas_files = [
            os.path.join(assets_dir, "HarvardOxford-cort-maxprob-thr0-1mm.nii.gz"),
            os.path.join(assets_dir, "Talairach-labels-1mm.nii.gz"),
            os.path.join(assets_dir, "MNI_Glasser_HCP_v1.0.nii.gz"),
            # Add more atlases here as needed
            # os.path.join(assets_dir, "your_new_atlas.nii.gz"),
        ]

    else:
        # Use command line arguments
        mask_file = args.mask
        atlas_files = args.atlases
        output_dir = args.output

        if not os.path.exists(mask_file):
            print(f"Error: Mask file not found: {mask_file}")
            sys.exit(1)

    # Run analysis
    posthoc_atlas_overlap(mask_file, atlas_files, output_dir)


if __name__ == "__main__":
    main()
