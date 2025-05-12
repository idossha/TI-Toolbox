"""
MeshAnalyzer: A tool for analyzing mesh-based neuroimaging data

This module provides functionality for analyzing mesh-based data from medical imaging,
particularly focusing on field analysis in specific regions of interest (ROIs) using
SimNIBS mesh files.

Inputs:
    - SimNIBS mesh files (.msh) containing field data
    - Subject directory containing m2m files for atlas mapping
    - ROI specifications (coordinates, regions)

Outputs:
    - Statistical measures (mean, min, max)
    - ROI masks
    - Surface meshes for visualization
    - Visualization files (optional)

Example Usage:
    ```python
    # Initialize analyzer
    analyzer = MeshAnalyzer(
        field_mesh_path="/path/to/field.msh",
        field_name="normE",
        subject_dir="/path/to/m2m_subject",
        output_dir="/path/to/output"
    )

    # Analyze a spherical ROI
    sphere_results = analyzer.analyze_sphere(
        center_coordinates=[0, 0, 0],
        radius=10
    )

    # Analyze a cortical region
    cortex_results = analyzer.analyze_cortex(
        atlas_type="DK40",
        target_region="superiorfrontal",
        visualize=True
    )

    # Analyze whole head
    whole_head_results = analyzer.analyze_whole_head(
        atlas_type="DK40",
        visualize=True
    )
    ```

Dependencies:
    - numpy
    - simnibs
    - subprocess (for msh2cortex operations)
"""

import simnibs
import numpy as np
import os
import time
import subprocess
import tempfile
from pathlib import Path
from visualizer import MeshVisualizer

class MeshAnalyzer:
    """
    A class for analyzing mesh-based data from 3D models.
    
    This class provides methods for analyzing field data in specific regions of interest,
    including spherical ROIs and cortical regions defined by an atlas. It works with
    SimNIBS mesh files and can generate surface meshes for cortical analysis.
    
    Attributes:
        field_mesh_path (str): Path to the mesh file containing field data
        field_name (str): Name of the field to analyze in the mesh
        subject_dir (str): Directory containing subject data (m2m folder)
        output_dir (str): Directory where analysis results will be saved
        visualizer (MeshVisualizer): Instance of visualizer for generating plots
        _surface_mesh_path (str): Cached path to generated surface mesh
    """
    
    def __init__(self, field_mesh_path: str, field_name: str, subject_dir: str, output_dir: str):
        """
        Initialize the MeshAnalyzer class.

        Args:
            field_mesh_path (str): Path to the mesh file containing the field data
            field_name (str): Name of the field to analyze
            subject_dir (str): Directory containing subject data (m2m folder)
            output_dir (str): Directory where analysis results will be saved
        """
        self.field_mesh_path = field_mesh_path
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        self.visualizer = MeshVisualizer(output_dir)
        
        # Cache for the surface mesh path
        self._surface_mesh_path = None
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Validate that field mesh exists
        if not os.path.exists(field_mesh_path):
            raise FileNotFoundError(f"Field mesh file not found: {field_mesh_path}")

    def _generate_surface_mesh(self):
        """
        Generate a surface mesh from the field mesh using msh2cortex if not already generated.
        This is used for cortical analysis.
        
        Returns:
            str: Path to the generated surface mesh file
        """
        if self._surface_mesh_path is not None and os.path.exists(self._surface_mesh_path):
            return self._surface_mesh_path
            
        # Create a directory for the surface mesh if it doesn't exist
        surface_dir = os.path.join(self.output_dir, 'surface_mesh')
        os.makedirs(surface_dir, exist_ok=True)
        
        # Generate output directory name based on the input mesh
        input_name = os.path.basename(self.field_mesh_path)
        output_dir = os.path.join(surface_dir, f"cortex_{input_name}")
        
        print(f"Generating surface mesh using msh2cortex...")
        print(f"This may take a few moments...")
        
        try:
            # Run msh2cortex command
            cmd = [
                'msh2cortex',
                '-i', self.field_mesh_path,
                '-m', self.subject_dir,
                '-o', output_dir
            ]
            
            print(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True)
            
            # The actual mesh file will be named *_central.msh inside the output directory
            base_name = os.path.splitext(input_name)[0]
            central_mesh = os.path.join(output_dir, f"{base_name}_central.msh")
            
            if not os.path.exists(central_mesh):
                raise FileNotFoundError(f"Expected surface mesh file not found at: {central_mesh}")
            
            # Store the path in cache
            self._surface_mesh_path = central_mesh
            print(f"Surface mesh generated successfully at: {central_mesh}")
            
            return central_mesh
            
        except subprocess.CalledProcessError as e:
            print(f"Error running msh2cortex: {str(e)}")
            print(f"Command output: {e.stdout.decode() if e.stdout else ''}")
            print(f"Command error: {e.stderr.decode() if e.stderr else ''}")
            raise RuntimeError("Failed to generate surface mesh using msh2cortex")
        except FileNotFoundError as e:
            print(f"Error: {str(e)}")
            print("msh2cortex completed but did not generate the expected file.")
            print(f"Contents of output directory {output_dir}:")
            try:
                files = os.listdir(output_dir)
                for f in files:
                    print(f"  {f}")
            except:
                print("  Could not list directory contents")
            raise

    def analyze_whole_head(self, atlas_type='HCP_MMP1', visualize=False):
        """
        Analyze all regions in the specified atlas.
        
        Args:
            atlas_type (str): Type of atlas to use (e.g., 'HCP_MMP1', 'DK40', 'a2009s')
            visualize (bool): Whether to generate visualizations
            
        Returns:
            dict: Dictionary mapping region names to their analysis results
        """
        start_time = time.time()
        print(f"Starting whole head analysis of {atlas_type} atlas.")
        
        try:
            # Generate surface mesh if needed
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Load the atlas
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_name in atlas.keys():
                try:
                    region_results = self.analyze_cortex(atlas_type, region_name, visualize)
                    # Only store essential results, not the masks
                    results[region_name] = {
                        'mean_value': region_results['mean_value'],
                        'max_value': region_results['max_value'],
                        'min_value': region_results['min_value'],
                        'nodes_in_roi': region_results['nodes_in_roi']
                    }
                except Exception as e:
                    print(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
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
            
            # Generate scatter plot if visualization is requested
            if visualize:
                self.visualizer.generate_cortex_scatter_plot(results, atlas_type, data_type='node')
            
            # Calculate and print timing information
            end_time = time.time()
            total_time = end_time - start_time
            print(f"\nTiming Information:")
            print(f"Total analysis time: {total_time:.2f} seconds")
            print(f"Average time per region: {total_time/len(results):.2f} seconds")
            
            return results
            
        finally:
            # Clean up
            try:
                del gm_surf
                del atlas
            except:
                pass

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from the field mesh data.
        Only includes elements with non-zero field values.
        
        Args:
            center_coordinates (list or tuple): [x, y, z] coordinates of sphere center in mm
            radius (float): Radius of the sphere in mm
            
        Returns:
            dict: Analysis results for the spherical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of elements in the ROI
                - elements_in_roi: Number of elements in the ROI (excluding zero values)
        """
        print(f"Analyzing a spherical ROI (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the field mesh
        mesh = simnibs.read_msh(self.field_mesh_path)
        
        # Get element centers
        elm_centers = mesh.elements_baricenters()[:]
        
        # Create ROI mask for elements within the sphere
        roi_mask = np.linalg.norm(elm_centers - center_coordinates, axis=1) < radius
        
        # Get the field values for the specified field
        field_values = mesh.field[self.field_name][:]
        
        # Create mask for non-zero values
        nonzero_mask = field_values > 0
        
        # Combine masks to get only non-zero values within ROI
        combined_mask = roi_mask & nonzero_mask
        
        # Check if we have any elements in the ROI
        roi_elements_count = np.sum(combined_mask)
        if roi_elements_count == 0:
            print("Warning: No elements with non-zero values found in the specified ROI!")
            return {
                'mean_value': None,
                'max_value': None, 
                'min_value': None,
                'roi_mask': combined_mask,
                'elements_in_roi': 0
            }
        
        # Get element volumes for proper weighted averaging
        elm_vols = mesh.elements_volumes_and_areas()[:]
        
        # Calculate statistics using only non-zero values in ROI
        min_value = np.min(field_values[combined_mask])
        max_value = np.max(field_values[combined_mask])
        mean_value = np.average(field_values[combined_mask], weights=elm_vols[combined_mask])
        
        # Get counts for reporting
        total_elements_in_roi = np.sum(roi_mask)
        zero_elements_in_roi = total_elements_in_roi - roi_elements_count
        
        print(f"ROI Analysis Results:")
        print(f"  Total elements in ROI: {total_elements_in_roi}")
        print(f"  Elements with non-zero values: {roi_elements_count}")
        print(f"  Elements with zero values (excluded): {zero_elements_in_roi}")
        print(f"  Mean {self.field_name}: {mean_value:.6f}")
        print(f"  Min {self.field_name}: {min_value:.6f}")
        print(f"  Max {self.field_name}: {max_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': combined_mask,
            'elements_in_roi': roi_elements_count
        }

    def analyze_cortex(self, atlas_type, target_region, visualize=False):
        """
        Analyze a specific cortical region using an atlas.
        Generates a surface mesh if not already generated.
        
        Args:
            atlas_type (str): Type of atlas to use (e.g., 'HCP_MMP1', 'DK40', 'a2009s')
            target_region (str): Name of the target region in the atlas
            visualize (bool, optional): Whether to generate visualization files (default: False)
                
        Returns:
            dict: Analysis results for the cortical region
        """
        print(f"Analyzing the cortical region '{target_region}' using {atlas_type} atlas.")
        
        # Generate surface mesh if needed
        surface_mesh_path = self._generate_surface_mesh()
        
        # Load the surface mesh
        gm_surf = simnibs.read_msh(surface_mesh_path)
        
        # Load the atlas and map it to the mesh
        atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
        
        # Select the target region
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
        
        # Generate visualizations if requested
        if visualize:
            # Generate 3D visualization
            viz_file = self.visualizer.visualize_cortex_roi(
                gm_surf=gm_surf,
                roi_mask=roi_mask,
                target_region=target_region,
                field_values=field_values,
                max_value=max_value
            )
            result['visualization_file'] = viz_file
            
            # Generate scatter plot of individual node values
            self.visualizer.generate_value_distribution_plot(
                field_values_in_roi,
                target_region,
                atlas_type,
                mean_value,
                max_value,
                min_value,
                data_type='node'
            )
        
        return result