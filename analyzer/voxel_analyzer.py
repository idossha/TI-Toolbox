import os
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt

class VoxelAnalyzer:
    """
    A class for analyzing voxel-based data from medical imaging.
    """
    
    def __init__(self, field_nifti: str, field_name: str, subject_dir: str, output_dir: str):
        """
        Initialize the VoxelAnalyzer class.
        
        Args:
            field_nifti (str): Path to the NIfTI file containing field data
            field_name (str): Name of the field to analyze
            subject_dir (str): Directory containing subject data
            output_dir (str): Directory where analysis results will be saved
        """
        self.field_nifti = field_nifti
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Validate that field_nifti exists
        if not os.path.exists(field_nifti):
            raise FileNotFoundError(f"Field file not found: {field_nifti}")

    def analyze_whole_head(self):
        """
        Analyze the entire head region from voxel data.
        
        Returns:
            dict: Analysis results for the whole head
        """
        print("Analyzing the entire head region from voxel data.")
        pass

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from voxel data.
        
        Args:
            center_coordinates (list or tuple): [x, y, z] coordinates of sphere center in mm
            radius (float): Radius of the sphere in mm
            
        Returns:
            dict: Analysis results for the spherical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of voxels in the ROI
        """
        print(f"Analyzing a spherical ROI (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the NIfTI data
        img = nib.load(self.field_nifti)
        field_data = img.get_fdata()
        
        # Get voxel dimensions (for proper distance calculation)
        voxel_size = np.array(img.header.get_zooms()[:3])
        
        # Get affine transformation matrix
        affine = img.affine
        
        # Convert world coordinates to voxel coordinates if needed
        # This assumes center_coordinates are in world space
        # inv_affine = np.linalg.inv(affine)
        # voxel_coords = np.dot(inv_affine, np.append(center_coordinates, 1))[:3]
        
        # For simplicity, assume coordinates are already in voxel space
        voxel_coords = np.array(center_coordinates)
        
        # Create coordinate grids for the entire volume
        x_size, y_size, z_size = field_data.shape
        x, y, z = np.ogrid[:x_size, :y_size, :z_size]
        
        # Calculate distance from center voxel (using voxel dimensions to account for anisotropy)
        dist_from_center = np.sqrt(
            ((x - voxel_coords[0])**2 * voxel_size[0]**2) +
            ((y - voxel_coords[1])**2 * voxel_size[1]**2) +
            ((z - voxel_coords[2])**2 * voxel_size[2]**2)
        )
        
        # Create the spherical mask
        roi_mask = dist_from_center <= radius
        
        # Count voxels in ROI
        roi_voxels_count = np.sum(roi_mask)
        
        # Check if we have any voxels in the ROI
        if roi_voxels_count == 0:
            print("Warning: No voxels found in the specified ROI!")
            return {
                'mean_value': None,
                'max_value': None,
                'min_value': None,
                'roi_mask': roi_mask
            }
        
        # Get the field values within the ROI
        roi_values = field_data[roi_mask]
        
        # Calculate statistics
        min_value = np.min(roi_values)
        max_value = np.max(roi_values)
        mean_value = np.mean(roi_values)
        
        print(f"ROI Analysis Results:")
        print(f" Number of voxels in ROI: {roi_voxels_count}")
        print(f" Mean {self.field_name}: {mean_value:.6f}")
        print(f" Min {self.field_name}: {min_value:.6f}")
        print(f" Max {self.field_name}: {max_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'voxels_in_roi': roi_voxels_count
        }

    def analyze_cortex(self):
        """
        Analyze the cortical region from voxel data.
        
        Returns:
            dict: Analysis results for the cortical region
        """
        print("Analyzing the cortical region from voxel data.")
        pass