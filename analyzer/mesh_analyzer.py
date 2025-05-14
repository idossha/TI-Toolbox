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
        # If we already have a valid surface mesh, return it
        if self._surface_mesh_path is not None and os.path.exists(self._surface_mesh_path):
            return self._surface_mesh_path
            
        # Create a new temporary directory if needed
        if self._temp_dir is None:
            import tempfile
            self._temp_dir = tempfile.TemporaryDirectory()
            
        # Generate output directory name based on the input mesh
        input_name = os.path.basename(self.field_mesh_path)
        output_dir = os.path.join(self._temp_dir.name, f"cortex_{input_name}")
        
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
            
            # Store the path
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
        # Create a new field with field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(gm_surf.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add this as a new field to the original mesh
        gm_surf.add_node_field(masked_field, 'ROI_field')
        
        # Create the output filename in the region directory (not in a subdirectory)
        output_filename = os.path.join(output_dir, f"brain_with_{target_region}_ROI.msh")
        
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

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from a mesh.
        
        Args:
            center_coordinates: List of [x, y, z] coordinates for the center of the sphere
            radius: Radius of the sphere in mm
            
        Returns:
            Dictionary containing analysis results
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
        print(f"Field data type: {type(field_data)}")
        print(f"Field data shape: {field_data.value.shape}")
        
        # Get field values
        field_values = field_data.value
        
        # Create spherical ROI manually
        print(f"Creating spherical ROI at {center_coordinates} with radius {radius}mm...")
        node_coords = mesh.nodes.node_coord
        print(f"Node coordinates shape: {node_coords.shape}")
        
        # Calculate distance from each node to the center
        distances = np.sqrt(
            (node_coords[:, 0] - center_coordinates[0])**2 +
            (node_coords[:, 1] - center_coordinates[1])**2 + 
            (node_coords[:, 2] - center_coordinates[2])**2
        )
        
        # Create mask for nodes within radius
        roi_mask = distances <= radius
        print(f"ROI mask shape: {roi_mask.shape}")
        
        # Check if field_values and roi_mask have compatible shapes
        if len(field_values.shape) > 1 and field_values.shape[0] != len(roi_mask):
            print(f"WARNING: Shape mismatch! Field values shape: {field_values.shape}, ROI mask length: {len(roi_mask)}")
            
            # If field_values is a 2D array with first dimension matching roi_mask, extract first column
            if len(field_values.shape) == 2 and field_values.shape[0] == len(roi_mask):
                print("Using first column of 2D field values")
                field_values = field_values[:, 0]
            # If transposing would help, try that
            elif len(field_values.shape) == 2 and field_values.shape[1] == len(roi_mask):
                print("Transposing field values to match ROI mask")
                field_values = field_values.T
            else:
                print("Unable to reconcile shape differences, using simple reshape")
                # Try to reshape or flatten the array if needed
                field_values = field_values.flatten()
                if len(field_values) > len(roi_mask):
                    field_values = field_values[:len(roi_mask)]
                elif len(field_values) < len(roi_mask):
                    # Extend the mask instead
                    temp_mask = np.zeros(len(field_values), dtype=bool)
                    temp_mask[:len(roi_mask)] = roi_mask[:len(field_values)]
                    roi_mask = temp_mask
        elif len(field_values) != len(roi_mask):
            print(f"WARNING: Length mismatch! Field values length: {len(field_values)}, ROI mask length: {len(roi_mask)}")
            
            # Create a new mask or truncate field values for compatibility
            if len(field_values) > len(roi_mask):
                print("Field values are longer than mask. Truncating field values.")
                field_values = field_values[:len(roi_mask)]
            else:
                print("Mask is longer than field values. Truncating mask.")
                roi_mask = roi_mask[:len(field_values)]
        
        # Check if we have any nodes in the ROI
        roi_nodes_count = np.sum(roi_mask)
        if roi_nodes_count == 0:
            print(f"Warning: No nodes found in the specified spherical ROI")
            results = {
                'mean_value': None,
                'max_value': None,
                'min_value': None
            }
            
            # Save results to CSV even if empty
            region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
            self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'node')
            
            return results
        
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
            # Check if node_areas has the right shape
            if len(node_areas) == len(roi_mask):
                print("Calculating weighted average using node areas")
                mean_value = np.average(field_values_in_roi, weights=node_areas[roi_mask])
            else:
                print(f"Node areas shape mismatch - using simple average instead")
        except Exception as e:
            print(f"Could not calculate weighted average: {str(e)}")
        
        # Create results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value
        }
        
        # Save results to CSV
        region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
        self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'node')
        
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
                self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
                
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
            self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
            
            return results
                
        except Exception as e:
            print(f"Error in cortical analysis: {str(e)}")
            raise