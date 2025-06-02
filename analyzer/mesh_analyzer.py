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
        
        # Initialize temporary directory and surface mesh path
        self._temp_dir = None
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
        # Get the base name of the input mesh
        input_name = os.path.basename(self.field_mesh_path)
        base_name = os.path.splitext(input_name)[0]
        
        # Get the simulation name and subject ID from the field mesh path
        # Field path structure: .../sub-<name>/Simulations/simulation_name/TI/mesh/field.msh
        field_path_parts = self.field_mesh_path.split(os.sep)
        try:
            sim_idx = field_path_parts.index('Simulations')
            simulation_name = field_path_parts[sim_idx + 1]
            
            # Get the subject ID from the m2m directory path
            # m2m path structure: .../sub-<name>/m2m_<name>
            m2m_name = os.path.basename(self.subject_dir)  # e.g., 'm2m_ido'
            subject_id = m2m_name.split('_')[1]  # e.g., 'ido'
            
            # Get the SimNIBS directory (parent of sub-*)
            simnibs_dir = os.path.dirname(os.path.dirname(self.subject_dir))
            
            # Construct the path where the surface mesh should be stored
            surface_mesh_dir = os.path.join(simnibs_dir, f'sub-{subject_id}', 'Simulations', simulation_name, 'TI', 'mesh')
            os.makedirs(surface_mesh_dir, exist_ok=True)
            
            # The surface mesh file path
            surface_mesh_path = os.path.join(surface_mesh_dir, f"{base_name}_central.msh")
            
            # If we already have a valid surface mesh, return it
            if os.path.exists(surface_mesh_path):
                print(f"Using existing surface mesh at: {surface_mesh_path}")
                self._surface_mesh_path = surface_mesh_path
                return surface_mesh_path
                
            print(f"Generating surface mesh using msh2cortex...")
            print(f"This may take a few moments...")
            
            try:
                # Run msh2cortex command
                cmd = [
                    'msh2cortex',
                    '-i', self.field_mesh_path,
                    '-m', self.subject_dir,
                    '-o', surface_mesh_dir
                ]
                
                print(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True)
                
                if not os.path.exists(surface_mesh_path):
                    raise FileNotFoundError(f"Expected surface mesh file not found at: {surface_mesh_path}")
                
                # Store the path
                self._surface_mesh_path = surface_mesh_path
                print(f"Surface mesh generated successfully at: {surface_mesh_path}")
                
                return surface_mesh_path
                
            except subprocess.CalledProcessError as e:
                print(f"Error running msh2cortex: {str(e)}")
                print(f"Command output: {e.stdout.decode() if e.stdout else ''}")
                print(f"Command error: {e.stderr.decode() if e.stderr else ''}")
                raise RuntimeError("Failed to generate surface mesh using msh2cortex")
            except FileNotFoundError as e:
                print(f"Error: {str(e)}")
                print("msh2cortex completed but did not generate the expected file.")
                print(f"Contents of output directory {surface_mesh_dir}:")
                try:
                    files = os.listdir(surface_mesh_dir)
                    for f in files:
                        print(f"  {f}")
                except:
                    print("  Could not list directory contents")
                raise
                
        except (ValueError, IndexError) as e:
            raise ValueError("Could not determine simulation name from field mesh path. Expected path structure: .../sub-<name>/Simulations/simulation_name/TI/mesh/field.msh")

    def __del__(self):
        """Cleanup temporary directory when the analyzer is destroyed."""
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except:
                pass

    def analyze_whole_head(self, atlas_type='HCP_MMP1', visualize=False):
        """
        Analyze all regions in the specified atlas.
        """
        start_time = time.time()
        print(f"Starting whole head analysis using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            print("Generating surface mesh...")
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            print("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Load the atlas
            print("Loading atlas...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_name in atlas.keys():
                try:
                    print(f"Processing region: {region_name}")
                    
                    # Create a directory for this region in the main output directory
                    region_dir = os.path.join(self.output_dir, region_name)
                    os.makedirs(region_dir, exist_ok=True)
                    
                    # Get ROI mask for this region
                    roi_mask = atlas[region_name]
                    
                    # Check if we have any nodes in the ROI
                    roi_nodes_count = np.sum(roi_mask)
                    if roi_nodes_count == 0:
                        print(f"Warning: No nodes found in the specified region '{region_name}'")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None
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
                    mean_value = np.average(field_values[roi_mask], weights=node_areas[roi_mask])
                    
                    # Create result dictionary for this region
                    region_results = {
                        'mean_value': mean_value,
                        'max_value': max_value,
                        'min_value': min_value
                    }
                    
                    # Store in the overall results
                    results[region_name] = region_results
                    
                    # Generate visualizations if requested
                    if visualize:
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
                    print(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None
                    }
            
            # Generate global scatter plot and save whole-head results to CSV directly in the main output directory
            if visualize and results:
                print("Generating global visualization plots...")
                # Generate scatter plots in the main output directory
                self._generate_whole_head_plots(results, atlas_type, 'node')
                
                # Generate and save summary CSV
                self._save_whole_head_summary_csv(results, atlas_type, 'node')
            
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
        # Load a fresh copy of the surface mesh to avoid accumulating ROI fields across regions
        region_mesh = simnibs.read_msh(self._surface_mesh_path)
        
        # Create a new field with field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(region_mesh.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add this as a new field to the fresh mesh
        region_mesh.add_node_field(masked_field, 'ROI_field')
        
        # Create the output filename in the region directory
        output_filename = os.path.join(output_dir, f"{target_region}_ROI.msh")
        
        # Save the modified mesh
        region_mesh.write(output_filename)
        
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
        """Generate a sorted scatter plot for whole head analysis directly in the main output directory."""
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
        ax.set_title(f'Cortical Region Analysis - {atlas_type}', 
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
        
        # Save plot directly in the main output directory
        output_file = os.path.join(self.output_dir, f'cortex_analysis_{atlas_type}.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated sorted scatter plot: {output_file}")

    def _save_whole_head_summary_csv(self, results, atlas_type, data_type='node'):
        """Save a summary CSV of whole-head analysis results directly in the output directory."""
        # Create the CSV
        filename = f"whole_head_{atlas_type}_summary.csv"
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

    def analyze_sphere(self, center_coordinates, radius, visualize=False):
        """
        Analyze a spherical region of interest from a mesh.
        
        Args:
            center_coordinates: List of [x, y, z] coordinates for the center of the sphere
            radius: Radius of the sphere in mm
            visualize: Whether to generate visualization files
            
        Returns:
            Dictionary containing analysis results or None if no nodes found
        """
        print(f"Starting spherical ROI analysis (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the mesh
        print("Loading mesh data...")
        mesh = simnibs.read_msh(self.field_mesh_path)
        
        # Check if field exists before any cropping
        if self.field_name not in mesh.field:
            available_fields = list(mesh.field.keys())
            raise ValueError(f"Field '{self.field_name}' not found in mesh. Available fields: {available_fields}")
        
        # Get field directly from the mesh
        field_data = mesh.field[self.field_name]
        
        # Get field values
        field_values = field_data.value
        
        # Create spherical ROI manually
        print(f"Creating spherical ROI at {center_coordinates} with radius {radius}mm...")
        node_coords = mesh.nodes.node_coord
        
        # Calculate distance from each node to the center
        distances = np.sqrt(
            (node_coords[:, 0] - center_coordinates[0])**2 +
            (node_coords[:, 1] - center_coordinates[1])**2 + 
            (node_coords[:, 2] - center_coordinates[2])**2
        )
        
        # Create mask for nodes within radius
        roi_mask = distances <= radius
        
        # Check if field_values and roi_mask have compatible shapes
        if len(field_values.shape) > 1 and field_values.shape[0] != len(roi_mask):
            if len(field_values.shape) == 2 and field_values.shape[0] == len(roi_mask):
                field_values = field_values[:, 0]
            elif len(field_values.shape) == 2 and field_values.shape[1] == len(roi_mask):
                field_values = field_values.T
            else:
                field_values = field_values.flatten()
                if len(field_values) > len(roi_mask):
                    field_values = field_values[:len(roi_mask)]
                elif len(field_values) < len(roi_mask):
                    temp_mask = np.zeros(len(field_values), dtype=bool)
                    temp_mask[:len(roi_mask)] = roi_mask[:len(field_values)]
                    roi_mask = temp_mask
        elif len(field_values) != len(roi_mask):
            if len(field_values) > len(roi_mask):
                field_values = field_values[:len(roi_mask)]
            else:
                roi_mask = roi_mask[:len(field_values)]
        
        # Check if we have any nodes in the ROI
        roi_nodes_count = np.sum(roi_mask)
        if roi_nodes_count == 0:
            # Determine the tissue type from the field mesh name
            field_mesh_name = os.path.basename(self.field_mesh_path).lower()
            tissue_type = "grey matter" if "grey" in field_mesh_name else "white matter" if "white" in field_mesh_name else "brain tissue"
            
            warning_msg = f"""
\033[93m⚠️  WARNING: Analysis Failed ⚠️
• No nodes found in ROI at [{center_coordinates[0]}, {center_coordinates[1]}, {center_coordinates[2]}], r={radius}mm
• ROI is not capturing any {tissue_type}
• Adjust coordinates/radius or verify using freeview\033[0m"""
            print(warning_msg)
            
            return None
        
        print(f"Found {roi_nodes_count} nodes in the ROI")
        print("Calculating statistics...")
        
        # Get the field values within the ROI
        field_values_in_roi = field_values[roi_mask]
        
        # Calculate statistics
        min_value = np.min(field_values_in_roi)
        max_value = np.max(field_values_in_roi)
        mean_value = np.mean(field_values_in_roi)
        
        # Try to calculate weighted mean if possible
        try:
            # Try to get node areas for weighted average
            node_areas = mesh.nodes_areas()
            
            # Check if we have node areas data for the ROI mask nodes
            # NodeData objects don't support len(), so we need to check if the values
            # attribute exists and has the right shape
            if hasattr(node_areas, 'value') and node_areas.value.shape[0] >= len(roi_mask):
                # Get the actual values from the NodeData object
                node_area_values = node_areas.value
                
                # Make sure we're only using values up to the length of roi_mask
                if node_area_values.shape[0] > len(roi_mask):
                    node_area_values = node_area_values[:len(roi_mask)]
                
                print("Calculating weighted average using node areas")
                # Use the actual values for weighting
                mean_value = np.average(field_values_in_roi, weights=node_area_values[roi_mask])
            else:
                print("Node areas shape incompatible - using simple average instead")
        except Exception as e:
            print(f"Could not calculate weighted average: {str(e)}")
        
        # Create results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'nodes_in_roi': roi_nodes_count
        }
        
        # Generate visualizations if requested
        if visualize:
            print("Generating visualizations...")
            
            # Generate distribution plot
            self.visualizer.generate_value_distribution_plot(
                field_values_in_roi,
                f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}",
                "Spherical",
                mean_value,
                max_value,
                min_value,
                data_type='node'
            )
            
            # For 3D mesh visualization, we need to generate a surface mesh
            try:
                print("Generating surface mesh for visualization...")
                surface_mesh_path = self._generate_surface_mesh()
                
                # Load the surface mesh
                gm_surf = simnibs.read_msh(surface_mesh_path)
                
                # We need to create the spherical ROI on the surface mesh
                # since the surface mesh may have different node coordinates/indices
                print("Creating spherical ROI on surface mesh...")
                surface_node_coords = gm_surf.nodes.node_coord
                
                # Calculate distances on the surface mesh
                surface_distances = np.sqrt(
                    (surface_node_coords[:, 0] - center_coordinates[0])**2 +
                    (surface_node_coords[:, 1] - center_coordinates[1])**2 + 
                    (surface_node_coords[:, 2] - center_coordinates[2])**2
                )
                
                # Create ROI mask for surface mesh
                surface_roi_mask = surface_distances <= radius
                
                # Get field values from surface mesh
                surface_field_values = gm_surf.field[self.field_name].value
                
                # Check surface ROI has nodes
                surface_roi_count = np.sum(surface_roi_mask)
                if surface_roi_count > 0:
                    print(f"Found {surface_roi_count} surface nodes in the ROI")
                    
                    # Get max value from surface field for proper color scaling
                    surface_field_values_in_roi = surface_field_values[surface_roi_mask]
                    surface_max_value = np.max(surface_field_values_in_roi)
                    
                    # Create spherical ROI overlay visualization
                    print("Creating spherical ROI overlay visualization...")
                    viz_file = self.visualizer.visualize_spherical_roi(
                        gm_surf=gm_surf,
                        roi_mask=surface_roi_mask,
                        center_coords=center_coordinates,
                        radius=radius,
                        field_values=surface_field_values,
                        max_value=surface_max_value,
                        output_dir=self.output_dir
                    )
                    results['visualization_file'] = viz_file
                else:
                    print("Warning: No surface nodes found in spherical ROI")
                    print("This may happen if the sphere is in deep brain regions not represented on the cortical surface")
                    
            except Exception as viz_error:
                print(f"Warning: Could not generate 3D visualization: {str(viz_error)}")
                print("This may happen if surface mesh generation fails or sphere is outside cortical surface")
                # Continue without 3D visualization but still save other results
        
        # Save results to CSV
        region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
        self.visualizer.save_results_to_csv(results, region_name, 'node')
        
        return results

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
        print(f"Starting cortical analysis for region '{target_region}' using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            print("Generating surface mesh...")
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            print("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Load the atlas
            print("Loading atlas...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            
            # Verify region exists in atlas
            if target_region not in atlas:
                available_regions = sorted(atlas.keys())
                raise ValueError(f"Region '{target_region}' not found in {atlas_type} atlas. Available regions: {available_regions}")
            
            # Get ROI mask for this region
            roi_mask = atlas[target_region]
            
            # Check if we have any nodes in the ROI
            roi_nodes_count = np.sum(roi_mask)
            if roi_nodes_count == 0:
                print(f"Warning: No nodes found in the specified region '{target_region}'")
                results = {
                    'mean_value': None,
                    'max_value': None,
                    'min_value': None
                }
                
                # Save results to CSV even if empty
                self.visualizer.save_results_to_csv(results, target_region, 'node')
                
                return results
            
            # Get the field values within the ROI
            field_values = gm_surf.field[self.field_name].value
            field_values_in_roi = field_values[roi_mask]
            
            # Calculate statistics
            min_value = np.min(field_values_in_roi)
            max_value = np.max(field_values_in_roi)
            
            # Calculate mean value using node areas for proper averaging
            node_areas = gm_surf.nodes_areas()
            mean_value = np.average(field_values_in_roi, weights=node_areas[roi_mask])
            
            # Prepare the results
            results = {
                'mean_value': mean_value,
                'max_value': max_value,
                'min_value': min_value
            }
            
            # Generate visualization if requested
            if visualize:
                print("Generating visualizations...")
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
                # This creates a mesh file with the ROI highlighted
                region_mesh_file = self._generate_region_visualization(
                    gm_surf=gm_surf,
                    roi_mask=roi_mask,
                    target_region=target_region,
                    field_values=field_values,
                    max_value=max_value,
                    output_dir=self.output_dir
                )
            
            # Save results to CSV
            self.visualizer.save_results_to_csv(results, target_region, 'node')
            
            return results
                
        except Exception as e:
            print(f"Error in cortical analysis: {str(e)}")
            raise