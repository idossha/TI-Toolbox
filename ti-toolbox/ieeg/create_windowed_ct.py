"""
Create properly windowed CT for better visualization
"""

import nibabel as nib
import numpy as np
from pathlib import Path

output_dir = Path(__file__).parent.parent / "output"
CT_aligned_path = output_dir / "CT_aligned_to_T1.nii.gz"

print("Creating windowed CT versions for easier viewing...")

# Load aligned CT
CT = nib.load(CT_aligned_path)
CT_data = np.asarray(CT.dataobj).astype(np.float32)

print(f"\nOriginal CT range: [{CT_data.min():.1f}, {CT_data.max():.1f}] HU")

# Create brain window version (soft tissue)
# Window: 100, Level: 40 (shows brain well)
brain_window = 100
brain_level = 40
CT_brain = np.clip(CT_data, brain_level - brain_window/2, brain_level + brain_window/2)
CT_brain = (CT_brain - CT_brain.min()) / (CT_brain.max() - CT_brain.min() + 1e-10)
CT_brain = (CT_brain * 4095).astype(np.int16)  # Scale to 12-bit range

brain_img = nib.Nifti1Image(CT_brain, CT.affine, CT.header)
brain_path = output_dir / "CT_aligned_brain_window.nii.gz"
nib.save(brain_img, brain_path)
print(f"✓ Brain window CT saved: {brain_path.name}")
print(f"  Range: [{CT_brain.min()}, {CT_brain.max()}]")

# Create bone window version (shows skull and electrodes)
# Window: 2000, Level: 500 (shows bone/metal well)
bone_window = 2000
bone_level = 500
CT_bone = np.clip(CT_data, bone_level - bone_window/2, bone_level + bone_window/2)
CT_bone = (CT_bone - CT_bone.min()) / (CT_bone.max() - CT_bone.min() + 1e-10)
CT_bone = (CT_bone * 4095).astype(np.int16)

bone_img = nib.Nifti1Image(CT_bone, CT.affine, CT.header)
bone_path = output_dir / "CT_aligned_bone_window.nii.gz"
nib.save(bone_img, bone_path)
print(f"✓ Bone window CT saved: {bone_path.name}")
print(f"  Range: [{CT_bone.min()}, {CT_bone.max()}]")

# Create electrode-optimized version
# Threshold to show only high-intensity (bone and electrodes)
electrode_threshold = 200  # Above this shows dense bone and metal
CT_electrodes = CT_data.copy()
CT_electrodes[CT_electrodes < electrode_threshold] = electrode_threshold
CT_electrodes = (CT_electrodes - electrode_threshold) / (CT_electrodes.max() - electrode_threshold + 1e-10)
CT_electrodes = (CT_electrodes * 4095).astype(np.int16)

elec_img = nib.Nifti1Image(CT_electrodes, CT.affine, CT.header)
elec_path = output_dir / "CT_aligned_electrodes_only.nii.gz"
nib.save(elec_img, elec_path)
print(f"✓ Electrode-focused CT saved: {elec_path.name}")
print(f"  Range: [{CT_electrodes.min()}, {CT_electrodes.max()}]")

print("\n" + "="*60)
print("DONE! Now you can view these in freeview:")
print("="*60)
print("\nFor brain visualization:")
print(f"  freeview data/pre_T1.nii.gz output/CT_aligned_brain_window.nii.gz:colormap=heat:opacity=0.5")
print("\nFor electrodes:")
print(f"  freeview data/pre_T1.nii.gz output/CT_aligned_electrodes_only.nii.gz:colormap=heat:opacity=0.7")
print("\nOr use the original with manual windowing:")
print(f"  freeview data/pre_T1.nii.gz output/CT_aligned_to_T1.nii.gz:colormap=heat:opacity=0.6")
print("  Then adjust Window/Level in the GUI")

