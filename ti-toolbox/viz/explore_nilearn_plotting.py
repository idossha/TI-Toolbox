#!/usr/bin/env python3
"""
Simplified script for visualizing electric field distributions from TES simulations.
Focuses on two key visualization approaches:
1. Multiple surface views (lateral, medial, left/right hemispheres) saved as high-res PDF with minimum cutoff
2. Interactive 3D visualization saved as HTML using plotly

Based on: https://nilearn.github.io/dev/auto_examples/01_plotting/plot_3d_map_to_surface_projection.html
"""

import os
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from nilearn import plotting
from nilearn.plotting import plot_img_on_surf, view_img_on_surf
import warnings
warnings.filterwarnings('ignore')

# Set up paths to your data
DATA_DIR = '/Users/idohaber/Desktop/visual_publication'
ATLAS_FILE = os.path.join(DATA_DIR, 'MNI_Glasser_HCP_v1.0.nii.gz')

# Electric field simulation files
EF_FILES = {
    'ernie_hippo': os.path.join(DATA_DIR, 'grey_Nav_3_TI_MNI_MNI_TI_max.nii.gz')
}

def load_electric_field_data(filename):
    """Load electric field NIfTI data."""
    if os.path.exists(filename):
        return nib.load(filename)
    else:
        print(f"Warning: {filename} not found")
        return None

def visualize_multiple_views(min_cutoff=0.3):
    """Multiple surface views (lateral, medial, left/right hemispheres) saved as PDF."""
    print("=== Multiple Surface Views (PDF) ===")

    ef_img = load_electric_field_data(EF_FILES['ernie_hippo'])
    if ef_img is None:
        return

    # Load data and show statistics
    data = ef_img.get_fdata()
    max_value = np.max(data)
    percentile_999 = np.percentile(data, 99.9)  # 99.9th percentile as top threshold
    min_value = np.min(data[data > 0])  # Minimum non-zero value
    print(f"Electric field statistics:")
    print(f"  Absolute maximum: {max_value:.2f} V/m")
    print(f"  99.9th percentile: {percentile_999:.2f} V/m")
    print(f"  Minimum (non-zero): {min_value:.2f} V/m")
    print(f"  Visualization cutoff: {min_cutoff:.2f} V/m")

    # Save as high-resolution PDF directly using nilearn's output_file parameter
    pdf_file = os.path.join(DATA_DIR, "electric_field_multiple_views.pdf")
    plot_img_on_surf(
        stat_map=ef_img,
        views=["lateral", "medial"],
        hemispheres=["left", "right"],
        title=f"Electric Field - Multiple Views (Cutoff: {min_cutoff} V/m)",
        bg_on_data=True,
        symmetric_cmap=False,
        cmap="hot",
        threshold=min_cutoff,  # Minimum cutoff for visualization
        vmin=min_cutoff,  # Explicitly set minimum for colorbar
        vmax=percentile_999,  # Use 99.9th percentile as top threshold
        colorbar=True,  # Ensure colorbar is shown
        cbar_tick_format="%.2f",  # Format colorbar ticks to 2 decimal places
        output_file=pdf_file,  # Save directly as PDF
    )
    print(f"✓ Saved: {pdf_file}")
    print(f"  Colorbar range: {min_cutoff:.2f} - {percentile_999:.2f} V/m")

def create_interactive_html():
    """3. Interactive 3D visualization saved as HTML using plotly."""
    print("=== 3. Interactive 3D HTML Visualization ===")

    ef_img = load_electric_field_data(EF_FILES['ernie_hippo'])
    if ef_img is None:
        return

    # Create interactive view with both electric fields
    print("Creating interactive visualization for Ernie Hippo...")
    view1 = view_img_on_surf(
        ef_img,
        threshold="90%",  # Auto threshold at 90th percentile
        cmap="hot",
        symmetric_cmap=False,
        title="Electric Field: Ernie Hippo"
    )

    # Save as HTML
    html_file1 = os.path.join(DATA_DIR, "electric_field_ernie_hippo.html")
    view1.save_as_html(html_file1)
    print(f"✓ Saved: {html_file1}")

    # Create second interactive view
    ef2_img = load_electric_field_data(EF_FILES['nav_3'])
    if ef2_img is not None:
        print("Creating interactive visualization for Nav 3...")
        view2 = view_img_on_surf(
            ef2_img,
            threshold="90%",
            cmap="plasma",
            symmetric_cmap=False,
            title="Electric Field: Nav 3"
        )

        html_file2 = os.path.join(DATA_DIR, "electric_field_nav_3.html")
        view2.save_as_html(html_file2)
        print(f"✓ Saved: {html_file2}")

        print("\nOpen these HTML files in your browser for interactive 3D exploration!")
        print("- Rotate, zoom, and pan the brain")
        print("- Click on different brain regions")
        print("- Adjust threshold and colormap settings")

def main():
    """Run the two key visualizations."""
    print("Electric Field Visualization Script")
    print("=" * 50)
    print(f"Data directory: {DATA_DIR}")

    # Check if files exist
    for name, path in EF_FILES.items():
        exists = os.path.exists(path)
        print(f"  {name}: {'✓' if exists else '✗'}")

    # Visualization parameters
    MIN_CUTOFF = 0  # V/m - minimum cutoff for visualization
    print(f"\nVisualization cutoff: {MIN_CUTOFF} V/m")

    print("\n" + "="*60)

    # Run the main visualizations
    try:
        visualize_multiple_views(min_cutoff=MIN_CUTOFF)
    except Exception as e:
        print(f"Error in Multiple Views: {e}")

    try:
        create_interactive_html()
    except Exception as e:
        print(f"Error in Interactive HTML: {e}")

    print("\n" + "="*60)
    print("Visualization complete!")
    print("\nGenerated outputs:")
    print("1. Multiple surface views (high-res PDF with minimum cutoff)")
    print("2. Interactive HTML files for 3D exploration")

if __name__ == "__main__":
    main()