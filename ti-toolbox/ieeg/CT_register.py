"""
Automatic co-registration of CT to T1 MRI
Uses rigid body transformation (rotation + translation only)
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

import nibabel as nib
import numpy as np
from pathlib import Path
from dipy.align import resample, affine_registration
from dipy.align.imaffine import AffineMap

print("="*60)
print("CT to T1 Co-registration Script")
print("="*60)

# Define paths
data_dir = Path(__file__).parent.parent / "data"
output_dir = Path(__file__).parent.parent / "output"
output_dir.mkdir(exist_ok=True)

T1_path = data_dir / "pre_T1.nii.gz"
CT_path = data_dir / "post_CT.nii.gz"

print(f"\nLoading data...")
print(f"  T1: {T1_path.name}")
print(f"  CT: {CT_path.name}")

# Load images
T1 = nib.load(T1_path)
CT_orig = nib.load(CT_path)

print(f"\nT1 shape: {T1.shape}")
print(f"CT shape: {CT_orig.shape}")


# Helper function to visualize overlay
def plot_overlay(image, compare, title, thresh=None, filename=None):
    """Plot overlay of two images."""
    image = nib.orientations.apply_orientation(
        np.asarray(image.dataobj),
        nib.orientations.axcodes2ornt(nib.orientations.aff2axcodes(image.affine)),
    ).astype(np.float32)
    compare = nib.orientations.apply_orientation(
        np.asarray(compare.dataobj),
        nib.orientations.axcodes2ornt(nib.orientations.aff2axcodes(compare.affine)),
    ).astype(np.float32)
    if thresh is not None:
        compare[compare < np.quantile(compare, thresh)] = np.nan
    
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    fig.suptitle(title)
    for i, ax in enumerate(axes):
        ax.imshow(
            np.take(image, [image.shape[i] // 2], axis=i).squeeze().T, cmap="gray"
        )
        ax.imshow(
            np.take(compare, [compare.shape[i] // 2], axis=i).squeeze().T,
            cmap="gist_heat",
            alpha=0.5,
        )
        ax.invert_yaxis()
        ax.axis("off")
    fig.tight_layout()
    
    if filename:
        fig.savefig(output_dir / filename, dpi=150, bbox_inches='tight')
        print(f"  Saved: {filename}")
    
    return fig


print("\n" + "="*60)
print("Step 1: Initial Resampling")
print("="*60)
print("Resampling CT to T1's coordinate space...")
print("(This just interpolates to match voxel grid, no alignment yet)")

# Resample CT to T1's definition of world coordinates
CT_resampled = resample(
    moving=np.asarray(CT_orig.dataobj),
    static=np.asarray(T1.dataobj),
    moving_affine=CT_orig.affine,
    static_affine=T1.affine,
)

print("Done! Creating visualization...")
plot_overlay(T1, CT_resampled, "BEFORE Alignment: CT Overlaid on T1", 
             thresh=0.95, filename="01_before_alignment.png")


print("\n" + "="*60)
print("Step 2: Computing Rigid Registration")
print("="*60)
print("This will compute the optimal rotation + translation...")
print("NOTE: This typically takes ~5-10 minutes. Please be patient!")
print("Progress updates will appear below:\n")

# Prepare data for registration
CT_data = np.asarray(CT_orig.dataobj).astype(np.float32)
T1_data = np.asarray(T1.dataobj).astype(np.float32)

# Use Dipy's high-level affine_registration function
# Pipeline: center_of_mass -> translation -> rigid -> affine
# Using full pipeline for better convergence
print("Running registration pipeline: center_of_mass -> translation -> rigid -> affine")
print("(Using Mutual Information metric for CT-MRI alignment)")
print("This will take several minutes...")

transformed, reg_affine = affine_registration(
    moving=CT_data,
    static=T1_data,
    moving_affine=CT_orig.affine,
    static_affine=T1.affine,
    pipeline=['center_of_mass', 'translation', 'rigid', 'affine'],
    level_iters=[10000, 1000, 100],  # More iterations for better convergence
    sigmas=[3.0, 1.0, 0.0],  # Smoothing at each scale
    factors=[4, 2, 1],  # Downsampling factors
    metric='MI',
)

print("\n✓ Registration complete!")
print("\nComputed transformation matrix:")
print(reg_affine)

# Save the transformation matrix
np.save(output_dir / "ct_to_t1_transform.npy", reg_affine)
print(f"\nTransform saved to: ct_to_t1_transform.npy")


print("\n" + "="*60)
print("Step 3: Applying Transformation")
print("="*60)
print("Applying the computed transformation to align CT to T1...")

# The affine_registration already returned the transformed data
# We just need to create a proper NIfTI image from it
CT_aligned = nib.Nifti1Image(transformed, T1.affine)

print("Done! Creating visualization...")
plot_overlay(T1, CT_aligned, "AFTER Alignment: CT Overlaid on T1",
             thresh=0.95, filename="02_after_alignment.png")


print("\n" + "="*60)
print("Step 4: Saving Results")
print("="*60)

# Save the aligned CT
aligned_ct_path = output_dir / "CT_aligned_to_T1.nii.gz"
nib.save(CT_aligned, aligned_ct_path)
print(f"Aligned CT saved to: {aligned_ct_path.name}")

# Create a detailed comparison figure
print("\nCreating detailed comparison...")
CT_data = CT_aligned.get_fdata().copy()
CT_data[CT_data < np.quantile(CT_data, 0.95)] = np.nan
T1_data = np.asarray(T1.dataobj)

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax in axes:
    ax.axis('off')
    
axes[0].imshow(T1_data[T1.shape[0] // 2], cmap='gray')
axes[0].set_title('T1 MRI', fontsize=14)

axes[1].imshow(np.asarray(CT_aligned.dataobj)[CT_aligned.shape[0] // 2], cmap='gray')
axes[1].set_title('Aligned CT', fontsize=14)

axes[2].imshow(T1_data[T1.shape[0] // 2], cmap='gray')
axes[2].imshow(CT_data[CT_aligned.shape[0] // 2], cmap='gist_heat', alpha=0.5)
axes[2].set_title('CT Overlay on T1', fontsize=14)

fig.suptitle('CT-to-T1 Registration Result', fontsize=16)
fig.tight_layout()
fig.savefig(output_dir / "03_alignment_comparison.png", dpi=150, bbox_inches='tight')
print(f"  Saved: 03_alignment_comparison.png")


print("\n" + "="*60)
print("COMPLETE!")
print("="*60)
print(f"\nAll outputs saved to: {output_dir}/")
print("\nFiles created:")
print("  1. 01_before_alignment.png - Shows initial misalignment")
print("  2. 02_after_alignment.png - Shows result after registration")
print("  3. 03_alignment_comparison.png - Detailed comparison")
print("  4. CT_aligned_to_T1.nii.gz - Aligned CT image (can load in any viewer)")
print("  5. ct_to_t1_transform.npy - 4x4 transformation matrix")
print("\nThe aligned CT is now in the same space as your T1 MRI!")
print("Next step: Use MNE GUI to mark electrode locations")

