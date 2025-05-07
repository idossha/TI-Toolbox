import simnibs
import numpy as np
import os
import time

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

    def analyze_whole_head(self, atlas_type='HCP_MMP1', visualize=False):
        """
        Analyze all regions in the specified atlas.
        
        Args:
            atlas_type (str): Type of atlas to use (e.g., 'HCP_MMP1', 'DK40', 'a2009s')
            
        Returns:
            dict: Dictionary mapping region names to their analysis results, where each result includes:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of nodes in the ROI
                - nodes_in_roi: Number of nodes in the ROI
        """
        start_time = time.time()
        print(f"Starting whole head analysis of {atlas_type} atlas.")
        
        # Load the original mesh
        gm_surf = simnibs.read_msh(self.mesh_path)
        
        # Load the atlas
        atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
        
        # Dictionary to store results for each region
        results = {}
        
        # Analyze each region in the atlas
        for region_name in atlas.keys():
            print(f"\nAnalyzing region: {region_name}")
            try:
                region_results = self.analyze_cortex(atlas_type, region_name, visualize)
                results[region_name] = region_results
            except Exception as e:
                print(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                results[region_name] = {
                    'mean_value': None,
                    'max_value': None,
                    'min_value': None,
                    'roi_mask': None,
                    'nodes_in_roi': 0
                }
        
        # Print summary of results
        print("\nSummary of whole head analysis:")
        print(f"Total regions analyzed: {len(results)}")
        
        # Count regions with valid results
        valid_regions = sum(1 for r in results.values() if r['mean_value'] is not None)
        print(f"Regions with valid results: {valid_regions}")
        
        # Find regions with highest and lowest mean values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        if valid_results:
            max_region = max(valid_results.items(), key=lambda x: x[1]['mean_value'])
            min_region = min(valid_results.items(), key=lambda x: x[1]['mean_value'])
            print(f"Region with highest mean value: {max_region[0]} ({max_region[1]['mean_value']:.6f})")
            print(f"Region with lowest mean value: {min_region[0]} ({min_region[1]['mean_value']:.6f})")
        
        # Calculate and print timing information
        end_time = time.time()
        total_time = end_time - start_time
        print(f"\nTiming Information:")
        print(f"Total analysis time: {total_time:.2f} seconds")
        print(f"Average time per region: {total_time/len(results):.2f} seconds")
        
        # Clear any temporary data
        del gm_surf
        del atlas
        
        return results

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

    def analyze_cortex(self, atlas_type, target_region, visualize=False):
        """
        Analyze a specific cortical region from mesh data using an atlas.
        
        Args:
            atlas_type (str): Type of atlas to use (e.g., 'HCP_MMP1', 'DK40', 'a2009s')
            target_region (str): Name of the target region in the atlas
            visualize (bool, optional): Whether to generate visualization files (default: False)
                
        Returns:
            dict: Analysis results for the cortical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of nodes in the ROI
                - nodes_in_roi: Number of nodes in the ROI
                - visualization_file: Path to visualization file (if visualize=True)
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
            result = {
                'mean_value': None,
                'max_value': None, 
                'min_value': None,
                'roi_mask': roi_mask,
                'nodes_in_roi': 0
            }
            if visualize:
                result['visualization_file'] = None
            return result
        
        # Get the field values within the ROI
        field_values = gm_surf.field[self.field_name].value
        field_values_in_roi = field_values[roi_mask]
        
        # Calculate statistics
        min_value = np.min(field_values_in_roi)
        max_value = np.max(field_values_in_roi)
        
        # Calculate mean value using node areas for proper averaging
        node_areas = gm_surf.nodes_areas()
        mean_value = np.average(field_values[roi_mask], weights=node_areas[roi_mask])
        
        # Print summary of results
        print(f"Analysis Results for {target_region} (Atlas: {atlas_type}):")
        print(f"  Total nodes in region: {roi_nodes_count}")
        print(f"  Mean field value: {mean_value:.6f}")
        print(f"  Max field value: {max_value:.6f}")
        print(f"  Min field value: {min_value:.6f}")
        
        # Create the return dictionary
        result = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'nodes_in_roi': roi_nodes_count
        }
        
        # Generate visualization if requested
        if visualize:
            viz_file = self.visualize_cortex_roi(
                gm_surf=gm_surf,
                roi_mask=roi_mask,
                target_region=target_region,
                field_values=field_values,
                max_value=max_value
            )
            result['visualization_file'] = viz_file
        
        return result
    
    def visualize_cortex_roi(self, gm_surf, roi_mask, target_region, field_values, max_value, output_dir=None):
        """
        Create visualization files for a specific cortical ROI.
        
        Args:
            gm_surf (simnibs.msh.mesh_io.Msh): The mesh object
            roi_mask (numpy.ndarray): Boolean mask of nodes in the ROI
            target_region (str): Name of the target region
            field_values (numpy.ndarray): Field values
            max_value (float): Maximum field value for scaling
            output_dir (str, optional): Directory where visualization files will be saved
            
        Returns:
            str: Path to the created visualization file
        """
        # Create a new field with field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(gm_surf.nodes.nr)
        # Copy the field values for nodes in our ROI
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add this as a new field to the original mesh
        gm_surf.add_node_field(masked_field, 'ROI_field')
        
        # Create the output directory if it doesn't exist
        if output_dir:
            # Use the specified output directory
            os.makedirs(output_dir, exist_ok=True)
            vis_dir = os.path.join(output_dir, 'cortex_visuals')
            os.makedirs(vis_dir, exist_ok=True)
            output_filename = os.path.join(vis_dir, f"brain_with_{target_region}_ROI.msh")
        else:
            # Use the class's output directory
            vis_dir = os.path.join(self.output_dir, 'cortex_visuals')
            os.makedirs(vis_dir, exist_ok=True)
            output_filename = os.path.join(vis_dir, f"brain_with_{target_region}_ROI.msh")
        
        # Save the modified original mesh
        gm_surf.write(output_filename)
        
        # Create the .msh.opt file with custom color map and alpha settings
        with open(f"{output_filename}.opt", 'w') as f:
            f.write(f"""
    // Make View[1] (ROI_field) visible with custom colormap
    View[1].Visible = 1;
    View[1].ColormapNumber = 1;  // Use the first predefined colormap
    View[1].RangeType = 2;       // Custom range
    View[1].CustomMin = 0;       // Specific minimum value
    View[1].CustomMax = {max_value};  // Specific maximum value for this cortex
    View[1].ShowScale = 1;       // Show the color scale

    // Add alpha/transparency based on value
    View[1].ColormapAlpha = 1;
    View[1].ColormapAlphaPower = 0.08;
    """)
        
        print(f"Created visualization: {output_filename}")
        print(f"Visualization settings saved to: {output_filename}.opt")
        
        return output_filename