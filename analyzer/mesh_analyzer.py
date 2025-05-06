import simnibs
import numpy as np
import os

class MeshAnalyzer:
    """
    A class for analyzing mesh-based data from 3D models.
    """
    
    def __init__(self, mesh_path: str, field_name: str, subject_dir: str, output_dir: str):
        """
        Initialize the MeshAnalyzer class.

        Args:
            mesh_path (str): Path to the field mesh file 
            subject_dir (str): Directory containing subject data
            field_name (str): Name of the field to analyze
            output_dir (str): Directory where analysis results will be saved
        """
        self.mesh_path = mesh_path
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir

    def analyze_cortex(self, atlas_type, target_region):
        """
        Analyze a specific cortical region from mesh data using an atlas.
        
        Args:
            atlas_type (str): Type of atlas to use (e.g., 'HCP_MMP1', 'DK40', 'a2009s')
            target_region (str): Name of the target region in the atlas
            
        Returns:
            dict: Analysis results for the cortical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - nodes_in_roi: Number of nodes in the ROI
        """
        print(f"Analyzing the cortical region '{target_region}' using {atlas_type} atlas.")
        
        # 1. Load the original mesh
        gm_surf = simnibs.read_msh(self.mesh_path)
        
        # 2. Load the atlas
        atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
        
        # 3. Select the target region
        if target_region not in atlas:
            raise ValueError(f"Region '{target_region}' not found in atlas {atlas_type}. "
                            f"Available regions: {list(atlas.keys())}")
        
        roi_mask = atlas[target_region]
        
        # 4. Calculate the min and max values in the specific cortex region
        field_values_in_roi = gm_surf.field[self.field_name].value[roi_mask]
        
        # Check if we have any nodes in the ROI
        roi_nodes_count = np.sum(roi_mask)
        if roi_nodes_count == 0:
            print(f"Warning: No nodes found in the specified region '{target_region}'!")
            return {
                'mean_value': None,
                'max_value': None, 
                'min_value': None,
                'nodes_in_roi': 0
            }
        
        min_value = np.min(field_values_in_roi)
        max_value = np.max(field_values_in_roi)
        
        # Calculate mean value using node areas for proper averaging
        node_areas = gm_surf.nodes_areas()
        mean_value = np.average(gm_surf.field[self.field_name].value[roi_mask], weights=node_areas[roi_mask])
        
        print(f"Cortical ROI Analysis Results:")
        print(f"  Region: {target_region} (Atlas: {atlas_type})")
        print(f"  Number of nodes in ROI: {roi_nodes_count}")
        print(f"  Mean {self.field_name}: {mean_value:.6f}")
        print(f"  Min {self.field_name}: {min_value:.6f}")
        print(f"  Max {self.field_name}: {max_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'nodes_in_roi': roi_nodes_count
        }