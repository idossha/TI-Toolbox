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
import csv
from datetime import datetime
import matplotlib.pyplot as plt
from utils.logging_utils import get_logger

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
        _temp_dir (tempfile.TemporaryDirectory): Temporary directory for surface mesh
        _surface_mesh_path (str): Path to the generated surface mesh
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
        
        # Get logger instance
        self.logger = get_logger("analyzer")
        if not self.logger:
            raise RuntimeError("Logger not initialized. Please call setup_logging before creating MeshAnalyzer.")
        
        # Initialize temporary directory and surface mesh path
        self._temp_dir = None
        self._surface_mesh_path = None
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            self.logger.debug(f"Created output directory: {output_dir}")
        
        # Validate that field mesh exists
        if not os.path.exists(field_mesh_path):
            self.logger.error(f"Field mesh file not found: {field_mesh_path}")
            raise FileNotFoundError(f"Field mesh file not found: {field_mesh_path}")
        
        self.logger.info(f"Initialized MeshAnalyzer with field: {field_mesh_path}")
        self.logger.debug(f"Field name: {field_name}")
        self.logger.debug(f"Subject directory: {subject_dir}")

    def _generate_surface_mesh(self):
        """
        Generate a surface mesh from the field mesh using msh2cortex if not already generated.
        This is used for cortical analysis.
        
        Returns:
            str: Path to the generated surface mesh file
        """
        # Get the base name of the input mesh
        input_name = os.path.basename(self.field_mesh_path)
        base_name = os.path.splitext(input_name)[0]
        
        self.logger.info("Generating surface mesh...")
        
        # Get the simulation name and subject ID from the field mesh path
        field_path_parts = self.field_mesh_path.split(os.sep)
        try:
            sim_idx = field_path_parts.index('Simulations')
            simulation_name = field_path_parts[sim_idx + 1]
            
            # Get the subject ID from the m2m directory path
            m2m_name = os.path.basename(self.subject_dir)
            subject_id = m2m_name.split('_')[1]
            
            self.logger.debug(f"Simulation name: {simulation_name}")
            self.logger.debug(f"Subject ID: {subject_id}")
            
            # Get the SimNIBS directory
            simnibs_dir = os.path.dirname(os.path.dirname(self.subject_dir))
            
            # Construct the path where the surface mesh should be stored
            surface_mesh_dir = os.path.join(simnibs_dir, f'sub-{subject_id}', 'Simulations', simulation_name, 'TI', 'mesh')
            os.makedirs(surface_mesh_dir, exist_ok=True)
            
            # The surface mesh file path
            surface_mesh_path = os.path.join(surface_mesh_dir, f"{base_name}_central.msh")
            
            # If we already have a valid surface mesh, return it
            if os.path.exists(surface_mesh_path):
                self.logger.info(f"Using existing surface mesh: {surface_mesh_path}")
                self._surface_mesh_path = surface_mesh_path
                return surface_mesh_path
            
            self.logger.info("Running msh2cortex to generate surface mesh...")
            
            try:
                # Run msh2cortex command
                cmd = [
                    'msh2cortex',
                    '-i', self.field_mesh_path,
                    '-m', self.subject_dir,
                    '-o', surface_mesh_dir
                ]
                
                self.logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(cmd, check=True, capture_output=True)
                self.logger.debug(f"msh2cortex stdout: {result.stdout.decode()}")
                
                if not os.path.exists(surface_mesh_path):
                    self.logger.error(f"Expected surface mesh file not found at: {surface_mesh_path}")
                    raise FileNotFoundError(f"Expected surface mesh file not found at: {surface_mesh_path}")
                
                # Store the path
                self._surface_mesh_path = surface_mesh_path
                self.logger.info(f"Surface mesh generated successfully: {surface_mesh_path}")
                
                return surface_mesh_path
                
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error running msh2cortex: {str(e)}")
                self.logger.error(f"Command output: {e.stdout.decode() if e.stdout else ''}")
                self.logger.error(f"Command error: {e.stderr.decode() if e.stderr else ''}")
                raise RuntimeError("Failed to generate surface mesh using msh2cortex")
            except FileNotFoundError as e:
                self.logger.error(f"Error: {str(e)}")
                self.logger.error("msh2cortex completed but did not generate the expected file")
                self.logger.debug(f"Contents of output directory {surface_mesh_dir}:")
                try:
                    files = os.listdir(surface_mesh_dir)
                    for f in files:
                        self.logger.debug(f"  {f}")
                except Exception as list_err:
                    self.logger.error(f"Could not list directory contents: {str(list_err)}")
                raise
                
        except (ValueError, IndexError) as e:
            self.logger.error("Could not determine simulation name from field mesh path")
            self.logger.error("Expected path structure: .../sub-<n>/Simulations/simulation_name/TI/mesh/field.msh")
            raise ValueError("Could not determine simulation name from field mesh path")

    def __del__(self):
        """Cleanup temporary directory when the analyzer is destroyed."""
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
                self.logger.debug("Cleaned up temporary directory")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temporary directory: {str(e)}")

    def analyze_whole_head(self, atlas_type='HCP_MMP1', visualize=False):
        """
        Analyze all regions in the specified atlas.
        """
        start_time = time.time()
        self.logger.info(f"Starting whole head analysis using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            self.logger.info("Generating surface mesh...")
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            self.logger.info("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            self.logger.debug(f"Surface mesh loaded with {gm_surf.nodes.nr} nodes")
            
            # Load the atlas
            self.logger.info(f"Loading {atlas_type} atlas...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            self.logger.debug(f"Atlas loaded with {len(atlas.keys())} regions")
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            total_regions = len(atlas.keys())
            for idx, region_name in enumerate(atlas.keys(), 1):
                try:
                    self.logger.info(f"Processing region {idx}/{total_regions}: {region_name}")
                    
                    # Create a directory for this region in the main output directory
                    region_dir = os.path.join(self.output_dir, region_name)
                    os.makedirs(region_dir, exist_ok=True)
                    
                    # Get ROI mask for this region
                    roi_mask = atlas[region_name]
                    
                    # Check if we have any nodes in the ROI
                    roi_nodes_count = np.sum(roi_mask)
                    self.logger.debug(f"Found {roi_nodes_count} nodes in region '{region_name}'")
                    
                    if roi_nodes_count == 0:
                        self.logger.warning(f"No nodes found in region '{region_name}'")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None,
                            'nodes_in_roi': 0
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        continue
                    
                    # Get the field values within the ROI
                    field_values = gm_surf.field[self.field_name].value
                    field_values_in_roi = field_values[roi_mask]
                    
                    # Calculate statistics
                    min_value = np.min(field_values_in_roi)
                    max_value = np.max(field_values_in_roi)
                    
                    # Calculate mean value using node areas for proper averaging
                    node_areas = gm_surf.nodes_areas()
                    mean_value = np.average(field_values_in_roi, weights=node_areas[roi_mask])
                    
                    # Create result dictionary for this region
                    region_results = {
                        'mean_value': mean_value,
                        'max_value': max_value,
                        'min_value': min_value,
                        'nodes_in_roi': roi_nodes_count
                    }
                    
                    self.logger.debug(f"Region '{region_name}' Results:")
                    self.logger.debug(f"- Mean Value: {mean_value:.6f}")
                    self.logger.debug(f"- Max Value: {max_value:.6f}")
                    self.logger.debug(f"- Min Value: {min_value:.6f}")
                    self.logger.debug(f"- Nodes in ROI: {roi_nodes_count}")
                    
                    # Store in the overall results
                    results[region_name] = region_results
                    
                    # Generate visualizations if requested
                    if visualize:
                        self.logger.debug(f"Generating visualizations for region '{region_name}'...")
                        # Generate 3D visualization and save directly to the region directory
                        viz_file = self._generate_region_visualization(
                            gm_surf=gm_surf,
                            roi_mask=roi_mask,
                            target_region=region_name,
                            field_values=field_values,
                            max_value=max_value,
                            output_dir=region_dir
                        )
                        
                        # Generate region-specific value distribution plot
                        if len(field_values_in_roi) > 0:
                            # Create a custom visualizer just for this region with the region directory as output
                            region_visualizer = MeshVisualizer(region_dir)
                            
                            # Generate value distribution plot for this region
                            region_visualizer.generate_value_distribution_plot(
                                field_values_in_roi,
                                region_name,
                                atlas_type,
                                mean_value,
                                max_value,
                                min_value,
                                data_type='node'
                            )
                    
                except Exception as e:
                    self.logger.error(f"Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
                        'nodes_in_roi': 0
                    }
            
            # Generate global scatter plot and save whole-head results to CSV directly in the main output directory
            if visualize and results:
                self.logger.info("Generating global visualization plots...")
                # Generate scatter plots in the main output directory
                self._generate_whole_head_plots(results, atlas_type, 'node')
                
                # Generate and save summary CSV
                self._save_whole_head_summary_csv(results, atlas_type, 'node')
            
            analysis_time = time.time() - start_time
            self.logger.info(f"Whole head analysis completed in {analysis_time:.2f} seconds")
            self.logger.info(f"Analyzed {len(results)} regions")
            
            return results
            
        finally:
            # Clean up
            try:
                del gm_surf
                del atlas
            except:
                pass

    def _generate_region_visualization(self, gm_surf, roi_mask, target_region, field_values, max_value, output_dir):
        """Generate 3D visualization for a region and save it directly to the specified directory."""
        # Create a new field with field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(gm_surf.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add this as a new field to the original mesh
        gm_surf.add_node_field(masked_field, 'ROI_field')
        
        # Create timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create the output filename in the region directory
        output_filename = os.path.join(output_dir, f"region_overlay_{target_region}_{timestamp}.msh")
        
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
    
    def _generate_whole_head_plots(self, results, atlas_type, data_type='node'):
        """Generate scatter plots for whole head analysis directly in the main output directory."""
        # Filter out regions with None values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        
        if not valid_results:
            print("Warning: No valid results to plot")
            return
        
        # Prepare data for plotting
        regions = list(valid_results.keys())
        mean_values = [res['mean_value'] for res in valid_results.values()]
        
        # Create figure with larger size for all regions
        fig, ax = plt.subplots(figsize=(15, 10))
        
        # Create scatter plot with enhanced styling (without color coding by count)
        scatter = ax.scatter(regions, mean_values, 
                          c='royalblue',
                          s=100,
                          alpha=0.6,
                          edgecolors='black',
                          linewidths=1)
        
        # Customize plot
        ax.set_title(f'Cortical Region Analysis - {atlas_type}', 
                   pad=20, 
                   fontsize=14, 
                   fontweight='bold')
        ax.set_xlabel('Region Name', fontsize=12, fontweight='bold')
        ax.set_ylabel('Mean Field Value', fontsize=12, fontweight='bold')
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        
        # Add grid
        ax.grid(True, linestyle='--', alpha=0.3)
        
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        
        # Save plot directly in the main output directory
        output_file = os.path.join(self.output_dir, f'cortex_analysis_{atlas_type}.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated scatter plot: {output_file}")
        
        # Generate additional plot with sorted values
        fig, ax = plt.subplots(figsize=(15, 10))
        
        # Sort regions by mean value
        sorted_indices = np.argsort(mean_values)
        sorted_regions = [regions[i] for i in sorted_indices]
        sorted_values = [mean_values[i] for i in sorted_indices]
        
        # Create sorted scatter plot with enhanced styling
        scatter = ax.scatter(range(len(sorted_regions)), sorted_values,
                          c='royalblue',
                          s=100,
                          alpha=0.6,
                          edgecolors='black',
                          linewidths=1)
        
        # Customize plot
        ax.set_title(f'Sorted Cortical Region Analysis - {atlas_type}', 
                   pad=20, 
                   fontsize=14, 
                   fontweight='bold')
        ax.set_xlabel('Region Index (sorted by mean value)', 
                    fontsize=12, 
                    fontweight='bold')
        ax.set_ylabel('Mean Field Value', 
                    fontsize=12, 
                    fontweight='bold')
        
        # Add grid
        ax.grid(True, linestyle='--', alpha=0.3)
        
        # Set x-ticks to show region names at the bottom
        ax.set_xticks(range(len(sorted_regions)))
        ax.set_xticklabels(sorted_regions, rotation=45, ha='right', fontsize=8)
        
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        
        # Save sorted plot directly in the main output directory
        sorted_output_file = os.path.join(self.output_dir, f'cortex_analysis_sorted_{atlas_type}.png')
        plt.savefig(sorted_output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated sorted scatter plot: {sorted_output_file}")

    def _save_whole_head_summary_csv(self, results, atlas_type, data_type='node'):
        """Save a summary CSV of whole-head analysis results directly in the output directory."""
        # Create the CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"whole_head_{atlas_type}_summary_{timestamp}.csv"
        output_path = os.path.join(self.output_dir, filename)
        
        # Write results to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header row
            header = ['Region', 'Mean Value', 'Max Value', 'Min Value']
            writer.writerow(header)
            
            # Write data for each region
            for region_name, region_data in results.items():
                row = [
                    region_name,
                    region_data.get('mean_value', 'N/A'),
                    region_data.get('max_value', 'N/A'),
                    region_data.get('min_value', 'N/A')
                ]
                writer.writerow(row)
        
        print(f"Saved whole-head analysis summary to: {output_path}")
        return output_path

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from a mesh.
        
        Args:
            center_coordinates: List of [x, y, z] coordinates for the center of the sphere
            radius: Radius of the sphere in mm
            
        Returns:
            Dictionary containing analysis results or None if no elements found
        """
        self.logger.info(f"Starting spherical ROI analysis at coordinates {center_coordinates} with radius {radius}mm")
        
        # Load the mesh
        self.logger.info("Loading mesh data...")
        mesh = simnibs.read_msh(self.field_mesh_path)
        
        # Check if field exists before any processing
        if self.field_name not in mesh.field:
            available_fields = list(mesh.field.keys())
            self.logger.error(f"Field '{self.field_name}' not found in mesh")
            self.logger.error(f"Available fields: {available_fields}")
            raise ValueError(f"Field '{self.field_name}' not found in mesh. Available fields: {available_fields}")
        
        # Get the field data
        field_data = mesh.field[self.field_name]
        self.logger.debug(f"Field data type: {type(field_data)}")
        
        # Get the centers of all elements (tetrahedra)
        self.logger.info("Getting element centers...")
        element_centers = mesh.elements_baricenters().value  # Use .value to get the ndarray
        self.logger.debug(f"Element centers shape: {element_centers.shape}")
        
        # Calculate distance from each element center to the sphere center
        self.logger.info(f"Creating spherical ROI mask...")
        distances = np.sqrt(
            (element_centers[:, 0] - center_coordinates[0])**2 +
            (element_centers[:, 1] - center_coordinates[1])**2 + 
            (element_centers[:, 2] - center_coordinates[2])**2
        )
        
        # Create mask for elements within radius
        roi_mask = distances <= radius
        
        # Check if we have any elements in the ROI
        roi_elements_count = np.sum(roi_mask)
        self.logger.info(f"Found {roi_elements_count} elements in the ROI")
        
        if roi_elements_count == 0:
            # Determine the tissue type from the field mesh name
            field_mesh_name = os.path.basename(self.field_mesh_path).lower()
            tissue_type = "grey matter" if "grey" in field_mesh_name else "white matter" if "white" in field_mesh_name else "brain tissue"
            
            self.logger.warning(f"No elements found in ROI at {center_coordinates}, r={radius}mm")
            self.logger.warning(f"ROI is not capturing any {tissue_type}")
            self.logger.warning("Adjust coordinates/radius or verify using freeview")
            
            return None
        
        # Get the field values
        self.logger.info("Extracting field values...")
        field_values = field_data.value  # Use .value to get the ndarray
        self.logger.debug(f"Field values shape: {field_values.shape}")
        self.logger.debug(f"ROI mask shape: {roi_mask.shape}")
        self.logger.debug(f"Field dimensions per point: {field_data.nr_comp}")
        
        # Get element volumes for proper weighted averaging
        self.logger.info("Calculating element volumes for weighted averaging...")
        element_vols = mesh.elements_volumes_and_areas().value  # Use .value to get the ndarray
        
        # Check for shape compatibility
        if len(field_values.shape) > 1 and field_values.shape[0] != roi_mask.shape[0]:
            self.logger.warning(f"Field values shape ({field_values.shape}) doesn't match ROI mask shape ({roi_mask.shape})")
            
            # If dimensions don't match, check if it's a vector field (3 components per element)
            if field_data.nr_comp == 3 and field_values.shape[1] == 3:
                self.logger.info("Detected vector field, calculating magnitude...")
                # Calculate magnitude for vector fields
                field_magnitudes = np.sqrt(np.sum(field_values**2, axis=1))
                field_values = field_magnitudes
                self.logger.debug(f"Calculated field magnitude, new shape: {field_values.shape}")
        
        # Get the field values within the ROI
        self.logger.info("Calculating statistics...")
        try:
            field_values_in_roi = field_values[roi_mask]
            element_vols_in_roi = element_vols[roi_mask]
            
            # Calculate statistics
            min_value = np.min(field_values_in_roi)
            max_value = np.max(field_values_in_roi)
            
            # Calculate volume-weighted mean
            self.logger.info("Calculating volume-weighted mean...")
            mean_value = np.average(field_values_in_roi, weights=element_vols_in_roi)
            
            # Create results dictionary
            results = {
                'mean_value': mean_value,
                'max_value': max_value,
                'min_value': min_value,
                'elements_in_roi': roi_elements_count
            }
            
            self.logger.info("Analysis Results:")
            self.logger.info(f"- Mean Value: {mean_value:.6f}")
            self.logger.info(f"- Max Value: {max_value:.6f}")
            self.logger.info(f"- Min Value: {min_value:.6f}")
            self.logger.info(f"- Elements in ROI: {roi_elements_count}")
            
            # Save results to CSV
            region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
            self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'element')
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to calculate statistics: {str(e)}")
            self.logger.error(f"Field values shape: {field_values.shape}, ROI mask shape: {roi_mask.shape}")
            raise

    def analyze_cortex(self, atlas_type, target_region, visualize=False):
        """
        Analyze a cortical region defined by an atlas.
        
        Args:
            atlas_type: Type of atlas to use (e.g., 'DK40', 'HCP_MMP1')
            target_region: Name of the region to analyze
            visualize: Whether to generate visualization files
            
        Returns:
            Dictionary containing analysis results
        """
        self.logger.info(f"Starting cortical analysis for region '{target_region}' using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            self.logger.info("Generating surface mesh...")
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            self.logger.info("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            self.logger.debug(f"Surface mesh loaded with {gm_surf.nodes.nr} nodes")
            
            # Load the atlas
            self.logger.info(f"Loading {atlas_type} atlas...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            self.logger.debug(f"Atlas loaded with {len(atlas.keys())} regions")
            
            # Verify region exists in atlas
            if target_region not in atlas:
                available_regions = sorted(atlas.keys())
                self.logger.error(f"Region '{target_region}' not found in {atlas_type} atlas")
                self.logger.error(f"Available regions: {available_regions}")
                raise ValueError(f"Region '{target_region}' not found in {atlas_type} atlas")
            
            # Get ROI mask for this region
            roi_mask = atlas[target_region]
            
            # Check if we have any nodes in the ROI
            roi_nodes_count = np.sum(roi_mask)
            self.logger.info(f"Found {roi_nodes_count} nodes in region '{target_region}'")
            
            if roi_nodes_count == 0:
                self.logger.warning(f"No nodes found in region '{target_region}'")
                results = {
                    'mean_value': None,
                    'max_value': None,
                    'min_value': None,
                    'nodes_in_roi': 0
                }
                
                # Save results to CSV even if empty
                self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
                
                return results
            
            # Get the field values within the ROI
            self.logger.info("Extracting field values...")
            field_values = gm_surf.field[self.field_name].value
            field_values_in_roi = field_values[roi_mask]
            
            self.logger.debug(f"Field values shape: {field_values.shape}")
            self.logger.debug(f"Number of field values in ROI: {len(field_values_in_roi)}")
            
            # Calculate statistics
            min_value = np.min(field_values_in_roi)
            max_value = np.max(field_values_in_roi)
            
            # Calculate mean value using node areas for proper averaging
            self.logger.info("Calculating weighted average using node areas...")
            node_areas = gm_surf.nodes_areas()
            mean_value = np.average(field_values_in_roi, weights=node_areas[roi_mask])
            
            # Prepare the results
            results = {
                'mean_value': mean_value,
                'max_value': max_value,
                'min_value': min_value,
                'nodes_in_roi': roi_nodes_count
            }
            
            self.logger.info("Analysis Results:")
            self.logger.info(f"- Mean Value: {mean_value:.6f}")
            self.logger.info(f"- Max Value: {max_value:.6f}")
            self.logger.info(f"- Min Value: {min_value:.6f}")
            self.logger.info(f"- Nodes in ROI: {roi_nodes_count}")
            
            # Generate visualization if requested
            if visualize:
                self.logger.info("Generating visualizations...")
                # Generate distribution plot
                self.visualizer.generate_value_distribution_plot(
                    field_values_in_roi,
                    target_region,
                    atlas_type,
                    mean_value,
                    max_value,
                    min_value,
                    data_type='node'
                )
                
                # Create region mesh visualization
                region_mesh_file = self._generate_region_visualization(
                    gm_surf=gm_surf,
                    roi_mask=roi_mask,
                    target_region=target_region,
                    field_values=field_values,
                    max_value=max_value,
                    output_dir=self.output_dir
                )
                self.logger.info(f"Generated region visualization: {region_mesh_file}")
            
            # Save results to CSV
            self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
            
            return results
                
        except Exception as e:
            self.logger.error(f"Error in cortical analysis: {str(e)}")
            raise