#!/usr/bin/env python3
"""
Simple script to plot MNI 3 slices with atlas contours and thresholded field values.
Creates a single figure with sagittal, coronal, and axial views.
"""

import os
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from nilearn import datasets, plotting
from nilearn.image import threshold_img
import warnings
warnings.filterwarnings('ignore')

# Configuration - set these variables to customize the visualization
DATA_DIR = '/Users/idohaber/Desktop/visual_publication'
FIELD_FILE = os.path.join(DATA_DIR, 'grey_Nav_3_TI_MNI_MNI_TI_max.nii.gz')

# Choose atlas: 'harvard_oxford', 'harvard_oxford_sub', 'aal', 'schaefer_2018'
ATLAS_NAME = 'harvard_oxford_sub'

# Choose regions: None for all regions, or list of indices (1-based, e.g., [1, 2, 3, 10, 15])
# For Harvard Oxford cortical: common regions include 1-48 for cortical areas
# For Harvard Oxford subcortical: common regions include 1-21 for subcortical structures
# For AAL: common regions include 1-116 for brain regions
# For Schaefer: 1-100 for parcels
SELECTED_REGIONS = None  # None = use all regions

def load_atlas(atlas_name, selected_regions=None):
    """Load the specified atlas and optionally filter to specific regions."""
    atlas_configs = {
        'harvard_oxford': {
            'name': 'Harvard Oxford Cortical Atlas',
            'function': lambda: datasets.fetch_atlas_harvard_oxford("cort-maxprob-thr25-2mm"),
            'atlas_key': 'filename',
            'labels_key': 'labels'
        },
        'harvard_oxford_sub': {
            'name': 'Harvard Oxford Subcortical Atlas',
            'function': lambda: datasets.fetch_atlas_harvard_oxford("sub-maxprob-thr25-2mm"),
            'atlas_key': 'filename',
            'labels_key': 'labels'
        },
        'aal': {
            'name': 'AAL Atlas',
            'function': lambda: datasets.fetch_atlas_aal(),
            'atlas_key': 'maps',
            'labels_key': 'labels'
        },
        'schaefer_2018': {
            'name': 'Schaefer 2018 Atlas (100 regions)',
            'function': lambda: datasets.fetch_atlas_schaefer_2018(n_rois=100),
            'atlas_key': 'maps',
            'labels_key': 'labels'
        }
    }

    if atlas_name not in atlas_configs:
        print(f"Error: Unknown atlas '{atlas_name}'. Available: {list(atlas_configs.keys())}")
        return None, None

    config = atlas_configs[atlas_name]

    try:
        print(f"Loading {config['name']}...")
        atlas_data = config['function']()
        atlas_img = atlas_data[config['atlas_key']]

        if selected_regions and 'labels' in atlas_data:
            # Create a filtered atlas with only selected regions
            atlas_nii = nib.load(atlas_img)
            atlas_array = atlas_nii.get_fdata()

            # Create mask for selected regions (regions are 1-indexed in the data)
            mask = np.zeros_like(atlas_array, dtype=bool)
            for region_idx in selected_regions:
                mask = mask | (atlas_array == region_idx)

            # Create new atlas with only selected regions
            filtered_array = np.zeros_like(atlas_array)
            filtered_array[mask] = atlas_array[mask]

            # Create new nifti image
            atlas_img = nib.Nifti1Image(filtered_array, atlas_nii.affine, atlas_nii.header)

            atlas_name_display = f"{config['name']} (Selected regions: {len(selected_regions)})"
        else:
            atlas_name_display = config['name']

        return atlas_img, atlas_name_display

    except Exception as e:
        print(f"Error loading atlas: {e}")
        return None, None

def create_mni_multi_slices_with_atlas_contours(atlas_img, atlas_name, field_file):
    """
    Create MNI multi-slice plot with atlas contours and thresholded field overlay.
    Shows 8 slices each for sagittal, coronal, and axial views (24 total slices).
    """
    print("Creating MNI multi-slices with atlas contours and field overlay...")

    # Load field data
    if not os.path.exists(field_file):
        print(f"Error: Field file not found: {field_file}")
        return

    # Load and threshold field data based on percentiles
    field_img_raw = nib.load(field_file)
    field_data = field_img_raw.get_fdata()

    # Calculate percentile-based thresholds
    field_data_nonzero = field_data[field_data > 0]
    if len(field_data_nonzero) == 0:
        print("Warning: No non-zero field values found")
        return

    percentile_95 = np.percentile(field_data_nonzero, 95)
    percentile_999 = np.percentile(field_data_nonzero, 99.9)
    max_value = np.max(field_data)

    # Threshold at 95th percentile as minimum
    field_img = threshold_img(field_file, threshold=percentile_95)

    print(f"Field statistics:")
    print(f"  Maximum value: {max_value:.3f} V/m")
    print(f"  95th percentile (min threshold): {percentile_95:.3f} V/m")
    print(f"  99.9th percentile (max): {percentile_999:.3f} V/m")
    print(f"  Visualization range: {percentile_95:.3f} - {percentile_999:.3f} V/m")

    # Create figure with 8 rows (slices) x 3 columns (views) = 24 subplots
    fig, axes = plt.subplots(8, 3, figsize=(12, 32))

    # Coordinates for multiple slices - 8 per view
    sagittal_coords = [-30, -20, -10, 0, 10, 20, 30, 40]   # x coordinates
    coronal_coords = [-40, -30, -20, -10, 0, 10, 20, 30]   # y coordinates
    axial_coords = [10, 20, 30, 40, 50, 60, 70, 80]       # z coordinates

    all_coords = [sagittal_coords, coronal_coords, axial_coords]
    view_names = ['Sagittal', 'Coronal', 'Axial']
    coord_labels = ['x', 'y', 'z']

    for col, (coords, view_name, coord_label) in enumerate(zip(all_coords, view_names, coord_labels)):
        for row, cut_coord in enumerate(coords):
            ax = axes[row, col]

            # Plot the field data as the base layer
            display = plotting.plot_stat_map(
                field_img,
                cut_coords=[cut_coord],
                display_mode=coord_label.lower(),  # 'x', 'y', or 'z'
                axes=ax,
                annotate=False,
                black_bg=False,
                cmap='hot',
                alpha=0.8,
                vmin=percentile_95,
                vmax=percentile_999,
                colorbar=False
            )

            # Add atlas contours on top
            display.add_contours(
                atlas_img,
                colors=['red', 'blue', 'green', 'yellow', 'purple', 'orange'] * 20,
                alpha=0.4,
                linewidths=0.5,
                levels=list(range(1, 200))  # Many levels for different regions
            )

            # Set view names only on first row for cleaner layout
            if row == 0:
                ax.set_title(f'{view_name}', fontsize=10, fontweight='bold')

    # Add a horizontal colorbar at the bottom
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    # Create a ScalarMappable for the colorbar
    norm = mcolors.Normalize(vmin=percentile_95, vmax=percentile_999)
    sm = cm.ScalarMappable(cmap='hot', norm=norm)
    sm.set_array([])

    # Add horizontal colorbar at the bottom
    cbar_ax = fig.add_axes([0.15, 0.02, 0.7, 0.02])  # [left, bottom, width, height]
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation='horizontal', label='Electric Field (V/m)')
    cbar.set_ticks([percentile_95, percentile_999])
    cbar.set_ticklabels([f'{percentile_95:.2f}', f'{percentile_999:.2f}'])

    # Main title
    fig.suptitle(f'MNI Template Multi-Slices with {atlas_name} Contours and Electric Field Overlay\n95th-99.9th Percentile Range', fontsize=14, fontweight='bold')

    plt.tight_layout(rect=[0, 0.05, 1, 0.95])  # Leave space for colorbar at bottom and title

    # Save the figure
    output_file = os.path.join(DATA_DIR, 'mni_multi_slices_atlas_contours_field.png')
    fig.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")

    # Also save as PDF for publication quality
    pdf_file = os.path.join(DATA_DIR, 'mni_multi_slices_atlas_contours_field.pdf')
    fig.savefig(pdf_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {pdf_file}")

    plt.close(fig)

def main():
    """Main function to run the visualization."""
    print("MNI Multi-Slices with Atlas Contours and Field Overlay")
    print("=" * 60)

    # Check field file
    if not os.path.exists(FIELD_FILE):
        print(f"✗ Field file not found: {FIELD_FILE}")
        return

    print(f"✓ Field file: {FIELD_FILE}")
    print(f"✓ Atlas: {ATLAS_NAME}")
    if SELECTED_REGIONS:
        print(f"✓ Selected regions: {SELECTED_REGIONS}")
    else:
        print("✓ Using all regions")

    # Load the configured atlas
    atlas_img, atlas_name = load_atlas(ATLAS_NAME, SELECTED_REGIONS)
    if atlas_img is None:
        print("Failed to load atlas")
        return

    # Create the visualization
    try:
        create_mni_multi_slices_with_atlas_contours(atlas_img, atlas_name, FIELD_FILE)
        print("\n✓ Visualization complete!")
        print(f"Check the output files in: {DATA_DIR}")
        print("Output files:")
        print("  - mni_multi_slices_atlas_contours_field.png")
        print("  - mni_multi_slices_atlas_contours_field.pdf")
    except Exception as e:
        print(f"Error creating visualization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
