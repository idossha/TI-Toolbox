# a quick and dirty script to convert a .annot file to a NIfTI volume without using Freesurfer

import nibabel as nib
import numpy as np
from nibabel.freesurfer.io import read_annot
import scipy.ndimage
from scipy.spatial import cKDTree
import os

# ---- Inputs ----
annot_path = 'segmentation/lh.101_DK40.annot'
surf_path = 'surfaces/lh.pial.gii'
t1_path = 'T1.nii.gz'
output_path = 'lh_labels_DK40.nii.gz'

# ---- Load .annot file ----
print("Loading .annot...")
labels, ctab, region_names = read_annot(annot_path)

# ---- Load GIFTI surface ----
print("Loading surface...")
gii = nib.load(surf_path)
vertices = gii.darrays[0].data  # Nx3 vertex coordinates

# ---- Load T1 image to get dimensions and affine ----
print("Loading T1 image...")
t1_img = nib.load(t1_path)
t1_affine = t1_img.affine
t1_shape = t1_img.shape

# ---- Convert surface coordinates to voxel indices ----
def world_to_vox(coords, affine):
    # Add homogeneous coordinate (1) to each point
    coords_homog = np.column_stack((coords, np.ones(coords.shape[0])))
    # Apply inverse affine transformation
    vox_coords = np.dot(np.linalg.inv(affine), coords_homog.T).T
    # Return integer coordinates
    return np.round(vox_coords[:, :3]).astype(int)

print("Mapping surface vertices to voxels...")
vox_coords = world_to_vox(vertices, t1_affine)

# ---- Create empty volume with background value ----
print("Building volume...")
background_value = -1  # Use -1 as background to distinguish from label 0
label_vol = np.full(t1_shape, background_value, dtype=np.int32)

# ---- Fill the volume with labels from the annotation file ----
valid_coords = []
for i, (x, y, z) in enumerate(vox_coords):
    if 0 <= x < t1_shape[0] and 0 <= y < t1_shape[1] and 0 <= z < t1_shape[2]:
        label_vol[x, y, z] = labels[i]
        valid_coords.append((x, y, z))

print(f"Initial voxels filled: {len(valid_coords)} out of {len(vox_coords)} vertices")

# ---- Expand labels using nearest neighbor interpolation ----
print("Expanding labels using nearest neighbor interpolation...")

# Create a KD-tree from the valid voxels
valid_coords = np.array(valid_coords)
valid_labels = np.array([labels[i] for i, (x, y, z) in enumerate(vox_coords) 
                        if 0 <= x < t1_shape[0] and 0 <= y < t1_shape[1] and 0 <= z < t1_shape[2]])

if len(valid_coords) > 0:  # Only proceed if we have valid coordinates
    tree = cKDTree(valid_coords)
    
    # Find regions near cortex
    # Create a mask of unlabeled voxels first by dilating the labeled region
    labeled_mask = (label_vol != background_value)
    dilated_mask = scipy.ndimage.binary_dilation(labeled_mask, iterations=3)
    unlabeled_near_cortex = np.logical_and(dilated_mask, label_vol == background_value)
    
    # Get indices of unlabeled voxels near cortex
    unlabeled_indices = np.where(unlabeled_near_cortex)
    unlabeled_coords = np.column_stack(unlabeled_indices)
    
    if len(unlabeled_coords) > 0:
        print(f"Filling {len(unlabeled_coords)} nearby unlabeled voxels...")
        
        # Find nearest labeled voxel for each unlabeled voxel
        distances, indices = tree.query(unlabeled_coords, k=1)
        
        # Assign each unlabeled voxel the label of its nearest labeled voxel
        for i, (x, y, z) in enumerate(unlabeled_coords):
            nearest_label_idx = indices[i]
            label_vol[x, y, z] = valid_labels[nearest_label_idx]
else:
    print("Warning: No valid coordinates found for KD-tree. Check if surface vertices map to volume space correctly.")

# ---- Optional: Fill holes in the volume using binary closing ----
print("Filling holes...")
# For each unique label, fill holes
unique_labels = np.unique(labels)
for label in unique_labels:
    if label == 0:  # Skip background label if present
        continue
    
    # Create binary mask for this label
    label_mask = (label_vol == label)
    
    # Apply binary closing to fill holes
    closed_mask = scipy.ndimage.binary_closing(label_mask, iterations=2)
    
    # Update label_vol with filled holes
    fill_indices = np.where(np.logical_and(closed_mask, label_vol == background_value))
    label_vol[fill_indices] = label

# ---- Set all remaining background values to 0 ----
label_vol[label_vol == background_value] = 0

# ---- Save NIfTI ----
print("Saving volume...")
out_img = nib.Nifti1Image(label_vol, affine=t1_affine)
nib.save(out_img, output_path)
print(f"Saved labeled volume: {output_path}")

# ---- Verify the output ----
print(f"Volume statistics:")
print(f"  Shape: {label_vol.shape}")
print(f"  Unique labels: {len(np.unique(label_vol))}")
print(f"  Non-zero voxels: {np.sum(label_vol > 0)}")
print(f"  Total voxels: {np.prod(label_vol.shape)}")
print(f"  Percentage filled: {np.sum(label_vol > 0) / np.prod(label_vol.shape) * 100:.2f}%")