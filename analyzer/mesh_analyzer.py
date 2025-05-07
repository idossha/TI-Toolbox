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
            field_name (str): Name of the field to analyze
            subject_dir (str): Directory containing subject data
            output_dir (str): Directory where analysis results will be saved
        """
        self.mesh_path = mesh_path
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Validate that mesh_path exists
        if not os.path.exists(mesh_path):
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

    def analyze_whole_head(self):
        """
        Analyze the entire head region from mesh data.
        
        Returns:
            dict: Analysis results for the whole head including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of elements in the ROI
                - elements_in_roi: Number of elements in the ROI
        """
        print("Analyzing the entire head region from mesh data.")
        pass

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from mesh data.
        
        Args:
            center_coordinates (list or tuple): [x, y, z] coordinates of sphere center in mm
            radius (float): Radius of the sphere in mm
            
        Returns:
            dict: Analysis results for the spherical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of elements in the ROI
                - elements_in_roi: Number of elements in the ROI
        """
        print(f"Analyzing a spherical ROI (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the mesh
        mesh = simnibs.read_msh(self.mesh_path)
        
        # Get element centers
        elm_centers = mesh.elements_baricenters()[:]
        
        # Create ROI mask for elements within the sphere
        roi_mask = np.linalg.norm(elm_centers - center_coordinates, axis=1) < radius
        
        # Check if we have any elements in the ROI
        roi_elements_count = np.sum(roi_mask)
        if roi_elements_count == 0:
            print("Warning: No elements found in the specified ROI!")
            return {
                'mean_value': None,
                'max_value': None, 
                'min_value': None,
                'roi_mask': roi_mask,
                'elements_in_roi': 0
            }
        
        # Get element volumes for proper weighted averaging
        elm_vols = mesh.elements_volumes_and_areas()[:]
        
        # Get the field values for the specified field
        field_values = mesh.field[self.field_name][:]
        
        # Calculate statistics
        min_value = np.min(field_values[roi_mask])
        max_value = np.max(field_values[roi_mask])
        mean_value = np.average(field_values[roi_mask], weights=elm_vols[roi_mask])
        
        print(f"ROI Analysis Results:")
        print(f"  Number of elements in ROI: {roi_elements_count}")
        print(f"  Mean {self.field_name}: {mean_value:.6f}")
        print(f"  Min {self.field_name}: {min_value:.6f}")
        print(f"  Max {self.field_name}: {max_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'elements_in_roi': roi_elements_count
        }

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
                - roi_mask: Boolean mask of nodes in the ROI
                - nodes_in_roi: Number of nodes in the ROI
        """
        print(f"Analyzing the cortical region '{target_region}' using {atlas_type} atlas.")
        
        # 1. Load the original mesh
        gm_surf = simnibs.read_msh(self.mesh_path)
        
        # 2. Load the atlas and map it to the mesh
        atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
        
        # 3. Select the target region
        if target_region not in atlas:
            raise ValueError(f"Region '{target_region}' not found in atlas {atlas_type}. "
                            f"Available regions: {list(atlas.keys())}")
        
        # Get the ROI mask for the target region
        roi_mask = atlas[target_region]
        
        # Check if we have any nodes in the ROI
        roi_nodes_count = np.sum(roi_mask)
        if roi_nodes_count == 0:
            print(f"Warning: No nodes found in the specified region '{target_region}'!")
            return {
                'mean_value': None,
                'max_value': None, 
                'min_value': None,
                'roi_mask': roi_mask,
                'nodes_in_roi': 0
            }
        
        # Get the field values within the ROI
        field_values_in_roi = gm_surf.field[self.field_name].value[roi_mask]
        
        # Calculate statistics
        min_value = np.min(field_values_in_roi)
        max_value = np.max(field_values_in_roi)
        
        # Calculate mean value using node areas for proper averaging
        node_areas = gm_surf.nodes_areas()
        mean_value = np.average(gm_surf.field[self.field_name].value[roi_mask], weights=node_areas[roi_mask])
        
        # Print summary of results
        print(f"Analysis Results for {target_region} (Atlas: {atlas_type}):")
        print(f"  Total nodes in region: {roi_nodes_count}")
        print(f"  Mean field value: {mean_value:.6f}")
        print(f"  Max field value: {max_value:.6f}")
        print(f"  Min field value: {min_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'nodes_in_roi': roi_nodes_count
        }