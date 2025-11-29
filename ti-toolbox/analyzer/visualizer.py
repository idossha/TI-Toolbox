"""
Visualizer: A tool for generating visualizations of neuroimaging analysis results

This module provides visualization capabilities for both voxel-based and mesh-based
neuroimaging data analysis results. It can generate various types of plots and
visualizations to help interpret analysis results.

Inputs:
    - Analysis results (statistical measures, ROI masks)
    - Field data (voxel or mesh based)
    - Atlas information
    - Region specifications

Outputs:
    - Focality histograms (PDF)
    - ROI visualizations
    - Surface overlays
    - Statistical summaries (CSV)

Example Usage:
    ```python
    # Initialize visualizer
    visualizer = VoxelVisualizer(output_dir="/path/to/output")

    # Generate focality histogram
    visualizer.generate_focality_histogram(
        whole_head_field_data=whole_head_data,
        roi_field_data=roi_data,
        region_name="Left-Hippocampus"
    )
    ```

Dependencies:
    - numpy
    - matplotlib
    - nibabel (for VoxelVisualizer)
    - simnibs (for MeshVisualizer)
"""

# Standard library imports
import csv
import os
import sys
from pathlib import Path

# Third-party imports
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
import nibabel as nib
import numpy as np
import simnibs

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Local imports
from tools import logging_util


class BaseVisualizer:
    """
    Base class for visualization functionality.
    
    This class provides common visualization methods that can be used
    by both voxel-based and mesh-based visualizers.
    
    Attributes:
        output_dir (str): Directory where visualization files will be saved
    """
    
    def __init__(self, output_dir: str, logger=None):
        """
        Initialize the BaseVisualizer.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
            logger: Optional logger instance to use. If None, creates its own.
        """
        self.output_dir = output_dir
        
        # Set up logger - use provided logger or create a new one
        if logger is not None:
            # Create a child logger to distinguish visualizer logs
            self.logger = logger.getChild('visualizer')
        else:
            # Create our own logger if none provided
            import time
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Extract subject ID from output_dir path
            subject_id = os.path.basename(output_dir).split('_')[1] if '_' in os.path.basename(output_dir) else os.path.basename(output_dir)
            
            # Create derivatives/ti-toolbox/logs directory structure (using relative path)
            log_dir = os.path.join('derivatives', 'ti-toolbox', 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file in the new directory
            log_file = os.path.join(log_dir, f'visualizer_{time_stamp}.log')
            self.logger = logging_util.get_logger('visualizer', log_file, overwrite=True)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            self.logger.info(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir)

    def save_results_to_csv(self, results, analysis_type, region_name=None, data_type='node'):
        """
        Save analysis results to a CSV file.
        
        Args:
            results (dict): Analysis results to save
            analysis_type (str): Type of analysis ('cortical' or 'spherical')
            region_name (str, optional): Name of the region analyzed
            data_type (str): Type of data ('node' or 'voxel')
        
        Returns:
            str: Path to the created CSV file
        """
        
        # Create appropriate filename
        if region_name:
            filename = f"{analysis_type}_{region_name}.csv"
        else:
            filename = f"{analysis_type}_analysis.csv"
        
        # Save directly to the output directory
        output_path = os.path.join(self.output_dir, filename)
        
        # Write results to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header and data based on analysis type
            if analysis_type == 'spherical':
                writer.writerow(['Metric', 'Value'])
                for key, value in results.items():
                    if key not in ['roi_mask', 'elements_in_roi', 'voxels_in_roi', 'nodes_in_roi']:
                        writer.writerow([key, value])
                
                # Write count information
                if 'elements_in_roi' in results:
                    writer.writerow(['elements_in_roi', results['elements_in_roi']])
                if 'voxels_in_roi' in results:
                    writer.writerow(['voxels_in_roi', results['voxels_in_roi']])
                if 'nodes_in_roi' in results:
                    writer.writerow(['nodes_in_roi', results['nodes_in_roi']])
            
            elif analysis_type == 'cortical':
                writer.writerow(['Metric', 'Value'])
                for key, value in results.items():
                    if key not in ['roi_mask', 'elements_in_roi', 'voxels_in_roi', 'nodes_in_roi', 'visualization_file']:
                        writer.writerow([key, value])
                
                # Write count information
                if 'nodes_in_roi' in results:
                    writer.writerow(['nodes_in_roi', results['nodes_in_roi']])
                if 'voxels_in_roi' in results:
                    writer.writerow(['voxels_in_roi', results['voxels_in_roi']])
                
                # Write visualization file path if available
                if 'visualization_file' in results and results['visualization_file']:
                    writer.writerow(['visualization_file', results['visualization_file']])
            
        self.logger.info(f"Saved analysis results to: {output_path}")
        return output_path

    def save_extra_info_to_csv(self, focality_info, analysis_type, region_name=None, data_type='node'):
        """
        Save focality analysis extra information to a CSV file.
        
        Args:
            focality_info (dict): Focality metrics to save
            analysis_type (str): Type of analysis ('cortical' or 'spherical')
            region_name (str, optional): Name of the region analyzed
            data_type (str): Type of data ('node' or 'voxel')
        
        Returns:
            str: Path to the created CSV file
        """
        
        # Create appropriate filename
        if region_name:
            filename = f"{analysis_type}_{region_name}_extra_info.csv"
        else:
            filename = f"{analysis_type}_analysis_extra_info.csv"
        
        # Save directly to the output directory
        output_path = os.path.join(self.output_dir, filename)
        
        # Write focality info to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['Metric', 'Value'])
            
            # Write all focality metrics
            for key, value in focality_info.items():
                writer.writerow([key, value])
        
        self.logger.info(f"Saved focality extra info to: {output_path}")
        return output_path

    def save_whole_head_results_to_csv(self, results, atlas_type, data_type='voxel'):
        """Save a summary CSV of whole-head analysis results directly in the output directory."""
        # Create the CSV
        filename = f"whole_head_{atlas_type}_summary.csv"
        output_path = os.path.join(self.output_dir, filename)
        
        # Write results to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header row - include both TI_max and TI_normal columns
            header = ['Region', 'Mean Value', 'Max Value', 'Min Value', 'Focality', 
                     'Normal Mean Value', 'Normal Max Value', 'Normal Min Value', 'Normal Focality',
                     f'{data_type.capitalize()}s in ROI']
            writer.writerow(header)
            
            # Write data for each region
            for region_name, region_data in results.items():
                row = [
                    region_name,
                    region_data.get('mean_value', 'N/A'),
                    region_data.get('max_value', 'N/A'),
                    region_data.get('min_value', 'N/A'),
                    region_data.get('focality', 'N/A'),
                    region_data.get('normal_mean_value', 'N/A'),
                    region_data.get('normal_max_value', 'N/A'),
                    region_data.get('normal_min_value', 'N/A'),
                    region_data.get('normal_focality', 'N/A'),
                    region_data.get(f'{data_type}s_in_roi', 0)
                ]
                writer.writerow(row)
        
        self.logger.info(f"Saved whole-head analysis summary to: {output_path}")
        return output_path

    def generate_focality_histogram(self, whole_head_field_data, roi_field_data, 
                                    whole_head_element_sizes=None, roi_element_sizes=None,
                                    filename=None, region_name=None, roi_field_value=None, 
                                    data_type='element', voxel_dims=None):
        """
        Generate a whole-head histogram with ROI contribution color coding.
        
        This creates a histogram of field values across the entire brain volume,
        with bars color-coded to show how much of each bin's volume comes from the ROI.
        
        Args:
            whole_head_field_data (numpy.ndarray): Field strength values for entire head
            roi_field_data (numpy.ndarray): Field strength values for ROI only
            whole_head_element_sizes (numpy.ndarray, optional): Element sizes for entire head
            roi_element_sizes (numpy.ndarray, optional): Element sizes for ROI only
            filename (str, optional): Filename for the output image
            region_name (str, optional): Name of the analyzed region
            roi_field_value (float, optional): ROI field value to display as reference line
            data_type (str): Type of data elements ('element', 'voxel', 'node')
            voxel_dims (tuple, optional): Voxel dimensions (x,y,z) for voxel volume calculation
            
        Returns:
            str: Path to the generated histogram file
        """
        if plt is None:
            self.logger.warning("matplotlib not available. Cannot generate histogram.")
            return None
            
        self.logger.info(f"Generating whole-head ROI histogram for {len(whole_head_field_data)} {data_type}s")
        
        try:
            # Check for valid data
            if len(whole_head_field_data) == 0:
                self.logger.warning(f"No whole-head data to plot")
                return None
            
            if len(roi_field_data) == 0:
                self.logger.warning(f"No ROI data to plot")
                return None
            
            # Remove NaN values from both datasets
            whole_head_valid_mask = ~np.isnan(whole_head_field_data)
            roi_valid_mask = ~np.isnan(roi_field_data)
            
            whole_head_field_data = whole_head_field_data[whole_head_valid_mask]
            roi_field_data = roi_field_data[roi_valid_mask]
            
            # Handle element sizes for whole head
            if whole_head_element_sizes is not None:
                whole_head_element_sizes = whole_head_element_sizes[whole_head_valid_mask]
                if len(whole_head_element_sizes) != len(whole_head_field_data):
                    self.logger.warning("Whole head element sizes don't match data length, using frequency histogram")
                    whole_head_element_sizes = None
            elif data_type == 'voxel' and voxel_dims is not None:
                # Calculate voxel volumes from dimensions
                voxel_volume = np.prod(voxel_dims[:3])  # x * y * z
                whole_head_element_sizes = np.full(len(whole_head_field_data), voxel_volume)
                self.logger.info(f"Voxel dimensions: {voxel_dims[:3]} mm")
                self.logger.info(f"Using uniform voxel volume: {voxel_volume:.3f} mm³")
                self.logger.info(f"Number of whole head voxels: {len(whole_head_field_data):,}")
                self.logger.info(f"Total whole head volume: {np.sum(whole_head_element_sizes) / 1000.0:.1f} cm³")
            
            # Handle element sizes for ROI
            if roi_element_sizes is not None:
                roi_element_sizes = roi_element_sizes[roi_valid_mask]
                if len(roi_element_sizes) != len(roi_field_data):
                    self.logger.warning("ROI element sizes don't match data length")
                    roi_element_sizes = None
            
            # Set up focality parameters
            focality_cutoffs = [50, 75, 90, 95]  # Percentages of 99.9 percentile
            
            fig, ax = plt.subplots(figsize=(14, 10))
            
            # Determine if we're doing volume-weighted or frequency histogram
            use_volume_weighting = (whole_head_element_sizes is not None and 
                                  len(whole_head_element_sizes) == len(whole_head_field_data))
            
            # Use element/voxel counts instead of volume measurements
            weights = None
            unit = 'count'
            ax.set_ylabel(f'{data_type.capitalize()}s')
            
            # Create histogram bins based on whole head data
            n_bins = 100
            hist, bin_edges = np.histogram(whole_head_field_data, bins=n_bins, weights=weights)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            
            # Calculate ROI contribution to each bin
            roi_hist, _ = np.histogram(roi_field_data, bins=bin_edges, weights=roi_element_sizes if roi_element_sizes is not None else None)
            
            # Calculate ROI contribution percentage for each bin
            roi_contribution = np.zeros_like(hist, dtype=float)
            for i in range(len(hist)):
                if hist[i] > 0:
                    roi_contribution[i] = roi_hist[i] / hist[i]
                else:
                    roi_contribution[i] = 0.0
            
            # Calculate a more meaningful color scale based on the actual distribution
            # Use the 95th percentile of non-zero contributions as the upper bound
            non_zero_contributions = roi_contribution[roi_contribution > 0]
            if len(non_zero_contributions) > 0:
                max_contribution = np.percentile(non_zero_contributions, 95)
                # Ensure we have a reasonable range (at least 0.01)
                max_contribution = max(max_contribution, 0.01)
            else:
                max_contribution = 0.01
            
            # Normalize contributions to the new scale
            normalized_contributions = np.clip(roi_contribution / max_contribution, 0, 1)
            
            # Use a blue-green-red (rainbow) colormap
            rainbow_cmap = plt.cm.get_cmap('rainbow')
            # To get blue at 0, green at 0.5, red at 1, use the full range
            colors = rainbow_cmap(normalized_contributions)
            colors[:, 3] = 0.7  # Set alpha to 0.7 for transparency
            
            # Plot the histogram bars
            bars = ax.bar(bin_centers, hist, width=bin_edges[1]-bin_edges[0], 
                         color=colors, edgecolor='black', alpha=0.8)
            
            # Calculate focality cutoffs based on 99.9 percentile of whole head data
            percentile_99_9 = np.percentile(whole_head_field_data, 99.9)
            focality_thresholds = []
            focality_volumes = []
            
            for cutoff in focality_cutoffs:
                threshold = (cutoff / 100.0) * percentile_99_9
                focality_thresholds.append(threshold)
                
                # Calculate count above this threshold
                above_threshold = whole_head_field_data >= threshold
                if np.any(above_threshold):
                    count = np.sum(above_threshold)
                    focality_volumes.append(count)
                else:
                    focality_volumes.append(0)
            
            # Add vertical red lines for focality cutoffs
            colors_lines = ['red', 'darkred', 'crimson', 'maroon']
            lines_added = 0
            for i, (threshold, cutoff) in enumerate(zip(focality_thresholds, focality_cutoffs)):
                if threshold <= np.max(whole_head_field_data) and threshold >= np.min(whole_head_field_data):
                    color = colors_lines[i % len(colors_lines)]
                    ax.axvline(x=threshold, color=color, linestyle='--', linewidth=2, alpha=0.8,
                              label=f'{cutoff}% of 99.9%ile\n({threshold:.2f} V/m)\nCount: {focality_volumes[i]:,} {data_type}s')
                    lines_added += 1
            
            # Add mean ROI field value indicator line (if available)
            if roi_field_value is not None and np.min(whole_head_field_data) <= roi_field_value <= np.max(whole_head_field_data):
                ax.axvline(x=roi_field_value, color='green', linestyle='-', linewidth=3, alpha=0.9,
                          label=f'Mean ROI Field\n({roi_field_value:.2f} V/m)')
                lines_added += 1
            
            # Add legend for all lines (only if lines were added)
            if lines_added > 0:
                ax.legend(loc='upper left', bbox_to_anchor=(0.02, 0.98),
                          frameon=True, fancybox=True, shadow=True, fontsize=9)
            
            # Customize plot
            ax.set_xlabel('Field Strength (V/m)')
            
            # Create title
            title_parts = ['Whole-Head Field Distribution with ROI Contribution']
            if region_name:
                title_parts.append(f'ROI: {region_name}')
            if filename:
                title_parts.append(f'File: {filename}')
            
            ax.set_title('\n'.join(title_parts), fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Add colorbar for ROI contribution
            norm = plt.Normalize(0, 1)
            sm = plt.cm.ScalarMappable(cmap=rainbow_cmap, norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.7, pad=0.02, aspect=25)
            cbar.set_label(f'ROI Contribution Fraction\n(Blue→Green→Red, max={max_contribution:.3f})', fontsize=10, fontweight='bold')
            
            # Add statistics text box
            stats_text = f'Whole Head:\n'
            stats_text += f'Max: {np.max(whole_head_field_data):.2f} V/m\n'
            stats_text += f'Mean: {np.mean(whole_head_field_data):.2f} V/m\n'
            stats_text += f'99.9%ile: {np.percentile(whole_head_field_data, 99.9):.2f} V/m\n'
            stats_text += f'{data_type.capitalize()}s: {len(whole_head_field_data):,}\n'
            
            stats_text += f'\nROI:\n'
            stats_text += f'Mean: {np.mean(roi_field_data):.2f} V/m\n'
            stats_text += f'Max: {np.max(roi_field_data):.2f} V/m\n'
            stats_text += f'Nodes: {len(roi_field_data):,}'
            
            # Position stats box on the right side of the plot
            ax.text(0.98, 0.98, stats_text, transform=ax.transAxes, fontsize=9,
                   verticalalignment='top', horizontalalignment='right',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            # Generate output filename
            if filename:
                base_name = Path(filename).stem if hasattr(Path, 'stem') else os.path.splitext(os.path.basename(filename))[0]
            elif region_name:
                base_name = f"{region_name}_whole_head_roi"
            else:
                base_name = "whole_head_roi_histogram"
            
            # Save histogram with tight layout
            hist_file = os.path.join(self.output_dir, f'{base_name}_histogram.png')
            plt.tight_layout()
            plt.savefig(hist_file, dpi=300, bbox_inches='tight')
            plt.close(fig)
            
            self.logger.info(f"Generated whole-head ROI histogram: {hist_file}")
            return hist_file
            
        except Exception as e:
            self.logger.error(f"Failed to generate whole-head ROI histogram: {str(e)}")
            return None


class Visualizer(BaseVisualizer):
    """
    Base class for generating visualizations of analysis results.
    Contains common visualization methods used by both mesh and voxel analysis.
    """
    
    def __init__(self, output_dir: str, logger=None):
        """
        Initialize the Visualizer class.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
            logger: Optional logger instance to use. If None, creates its own.
        """
        super().__init__(output_dir, logger)
        
        # Only create directories if needed for individual analyses, not for whole-head
        # We'll create these directories on demand in the specific methods that need them
        # instead of creating them all at initialization
    




class MeshVisualizer(Visualizer):
    """Class for generating mesh-specific visualizations."""
    
    def __init__(self, output_dir: str, logger=None):
        """Initialize the MeshVisualizer class."""
        super().__init__(output_dir, logger)

    def visualize_cortex_roi(self, gm_surf, roi_mask, target_region, field_values, max_value, output_dir=None, surface_mesh_path=None, normal_mesh_path=None):
        """Generate 3D visualization for a region and save it directly to the specified directory."""
        if simnibs is None:
            self.logger.warning("simnibs not available. Cannot generate mesh visualization.")
            return None
            
        self.logger.info(f"Creating cortex ROI visualization for region: {target_region}")
        self.logger.info(f"ROI contains {np.sum(roi_mask)} nodes")
        
        # Load a fresh copy of the surface mesh to avoid accumulating ROI fields across regions
        if surface_mesh_path:
            region_mesh = simnibs.read_msh(surface_mesh_path)
        else:
            # Use the provided mesh if no path is given
            region_mesh = gm_surf
        
        # Create a new field with TI_max field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(region_mesh.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add TI_max field to the mesh
        region_mesh.add_node_field(masked_field, 'TI_max_ROI')
        
        # Try to add TI_normal field if normal mesh is available
        normal_max_value = max_value  # Default fallback
        try:
            # Construct normal mesh path if not provided
            if normal_mesh_path is None and surface_mesh_path:
                # Try to construct normal mesh path from surface mesh path
                # Surface mesh: /path/to/montage_TI_central.msh -> Normal mesh: /path/to/montage_normal.msh
                mesh_dir = os.path.dirname(surface_mesh_path)
                surface_filename = os.path.basename(surface_mesh_path)
                
                if '_TI_central.msh' in surface_filename:
                    normal_mesh_filename = surface_filename.replace('_TI_central.msh', '_normal.msh')
                elif '_mTI.msh' in surface_filename:
                    # For mTI simulations: _mTI.msh -> _mTI_normal.msh (if it exists)
                    normal_mesh_filename = surface_filename.replace('_mTI.msh', '_mTI_normal.msh')
                elif '_TI.msh' in surface_filename:
                    # For regular TI simulations: _TI.msh -> _normal.msh
                    normal_mesh_filename = surface_filename.replace('_TI.msh', '_normal.msh')
                else:
                    # General fallback: try to replace .msh with _normal.msh
                    base_name = os.path.splitext(surface_filename)[0]
                    normal_mesh_filename = f"{base_name}_normal.msh"
                
                normal_mesh_path = os.path.join(mesh_dir, normal_mesh_filename)
            
            # Load normal mesh and extract TI_normal values
            if normal_mesh_path and os.path.exists(normal_mesh_path):
                self.logger.info(f"Adding TI_normal field from: {normal_mesh_path}")
                normal_mesh = simnibs.read_msh(normal_mesh_path)
                
                if 'TI_normal' in normal_mesh.field:
                    normal_field_values = normal_mesh.field['TI_normal'].value
                    
                    # Create masked normal field (zeros everywhere except ROI)
                    masked_normal_field = np.zeros(region_mesh.nodes.nr)
                    masked_normal_field[roi_mask] = normal_field_values[roi_mask]
                    
                    # Add TI_normal field to the mesh
                    region_mesh.add_node_field(masked_normal_field, 'TI_normal_ROI')
                    
                    # Calculate max value for normal field for color scaling
                    normal_roi_values = normal_field_values[roi_mask]
                    if len(normal_roi_values[normal_roi_values > 0]) > 0:
                        normal_max_value = np.max(normal_roi_values[normal_roi_values > 0])
                        self.logger.info(f"TI_normal max value in ROI: {normal_max_value:.6f}")
                    
                    # Clean up
                    del normal_mesh
                    
                else:
                    self.logger.warning("TI_normal field not found in normal mesh")
            else:
                self.logger.warning(f"Normal mesh not found at: {normal_mesh_path}")
                
        except Exception as e:
            self.logger.warning(f"Could not add TI_normal field to visualization: {str(e)}")
        
        # Use provided output_dir or default to self.output_dir
        if output_dir is None:
            output_dir = self.output_dir
            
        # Create the output filename in the region directory
        output_filename = os.path.join(output_dir, f"{target_region}_ROI.msh")
        
        # Save the modified mesh
        region_mesh.write(output_filename)
        
        # Create the .msh.opt file with custom color map and alpha settings for both fields
        with open(f"{output_filename}.opt", 'w') as f:
            f.write(f"""
    // Hide 2D mesh element faces for cleaner field visualization
    Mesh.SurfaceFaces = 0;       // Hide surface faces
    Mesh.SurfaceEdges = 0;       // Hide surface edges
    Mesh.Points = 0;             // Hide mesh points
    Mesh.Lines = 0;              // Hide mesh lines

    // Make View[1] (TI_max_ROI) visible with custom colormap
    View[1].Visible = 1;
    View[1].ColormapNumber = 1;  // Use the first predefined colormap
    View[1].RangeType = 2;       // Custom range
    View[1].CustomMin = 0;       // Specific minimum value
    View[1].CustomMax = {max_value};  // Specific maximum value for TI_max
    View[1].ShowScale = 1;       // Show the color scale

    // Add alpha/transparency based on value
    View[1].ColormapAlpha = 1;
    View[1].ColormapAlphaPower = 0.08;

    // Make View[2] (TI_normal_ROI) visible with different colormap (if available)
    View[2].Visible = 0;         // Initially hidden - user can toggle
    View[2].ColormapNumber = 2;  // Use the second predefined colormap
    View[2].RangeType = 2;       // Custom range
    View[2].CustomMin = 0;       // Specific minimum value
    View[2].CustomMax = {normal_max_value};  // Specific maximum value for TI_normal
    View[2].ShowScale = 1;       // Show the color scale

    // Add alpha/transparency based on value
    View[2].ColormapAlpha = 1;
    View[2].ColormapAlphaPower = 0.08;
    
    // Field information as comments
    // View[1]: TI_max field (max value: {max_value:.6f})
    // View[2]: TI_normal field (max value: {normal_max_value:.6f})
    """)
        
        self.logger.info(f"Created visualization: {output_filename}")
        self.logger.info(f"Visualization settings saved to: {output_filename}.opt")
        
        return output_filename

    def visualize_spherical_roi(self, gm_surf, roi_mask, center_coords, radius, field_values, max_value, output_dir=None, surface_mesh_path=None):
        """Create visualization files for a spherical ROI in mesh data.
        
        Args:
            gm_surf: Gray matter surface mesh
            roi_mask: Boolean mask indicating which nodes are in the spherical ROI
            center_coords: Coordinates of the sphere center (x, y, z)
            radius: Radius of the sphere
            field_values: Field values for all nodes
            max_value: Maximum value for color scale
            output_dir: Optional output directory (if None, uses self.output_dir)
            surface_mesh_path: Optional path to surface mesh for TI_normal field extraction
            
        Returns:
            str: Path to the created visualization file
        """
        if simnibs is None:
            self.logger.warning("simnibs not available. Cannot generate mesh visualization.")
            return None
            
        self.logger.debug(f"Creating spherical ROI visualization at center {center_coords} with radius {radius}mm")
        self.logger.debug(f"ROI contains {np.sum(roi_mask)} surface nodes")
        
        # Create a new field with TI_max field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(gm_surf.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add TI_max field to the mesh
        gm_surf.add_node_field(masked_field, 'Spherical_ROI_field')
        
        # Try to add TI_normal field if normal mesh is available
        normal_max_value = max_value  # Default fallback
        try:
            # Construct normal mesh path if surface mesh path is provided
            normal_mesh_path = None
            if surface_mesh_path:
                # Try to construct normal mesh path from surface mesh path
                # Surface mesh: /path/to/montage_TI_central.msh -> Normal mesh: /path/to/montage_normal.msh
                mesh_dir = os.path.dirname(surface_mesh_path)
                surface_filename = os.path.basename(surface_mesh_path)
                
                if '_TI_central.msh' in surface_filename:
                    normal_mesh_filename = surface_filename.replace('_TI_central.msh', '_normal.msh')
                elif '_mTI.msh' in surface_filename:
                    # For mTI simulations: _mTI.msh -> _mTI_normal.msh (if it exists)
                    normal_mesh_filename = surface_filename.replace('_mTI.msh', '_mTI_normal.msh')
                elif '_TI.msh' in surface_filename:
                    # For regular TI simulations: _TI.msh -> _normal.msh
                    normal_mesh_filename = surface_filename.replace('_TI.msh', '_normal.msh')
                else:
                    # General fallback: try to replace .msh with _normal.msh
                    base_name = os.path.splitext(surface_filename)[0]
                    normal_mesh_filename = f"{base_name}_normal.msh"
                
                normal_mesh_path = os.path.join(mesh_dir, normal_mesh_filename)
            
            # Load normal mesh and extract TI_normal values
            if normal_mesh_path and os.path.exists(normal_mesh_path):
                self.logger.info(f"Adding TI_normal field from: {normal_mesh_path}")
                normal_mesh = simnibs.read_msh(normal_mesh_path)
                
                if 'TI_normal' in normal_mesh.field:
                    normal_field_values = normal_mesh.field['TI_normal'].value
                    
                    # Create masked normal field (zeros everywhere except ROI)
                    masked_normal_field = np.zeros(gm_surf.nodes.nr)
                    masked_normal_field[roi_mask] = normal_field_values[roi_mask]
                    
                    # Add TI_normal field to the mesh
                    gm_surf.add_node_field(masked_normal_field, 'TI_normal_ROI')
                    
                    # Calculate max value for normal field for color scaling
                    normal_roi_values = normal_field_values[roi_mask]
                    if len(normal_roi_values[normal_roi_values > 0]) > 0:
                        normal_max_value = np.max(normal_roi_values[normal_roi_values > 0])
                        self.logger.info(f"TI_normal max value in ROI: {normal_max_value:.6f}")
                    
                    # Clean up
                    del normal_mesh
                    
                else:
                    self.logger.warning("TI_normal field not found in normal mesh")
            else:
                self.logger.warning(f"Normal mesh not found at: {normal_mesh_path}")
                
        except Exception as e:
            self.logger.warning(f"Could not add TI_normal field to visualization: {str(e)}")
        
        # Use provided output_dir or default to self.output_dir
        if output_dir is None:
            output_dir = self.output_dir
            
        # Create sphere identifier for filename
        sphere_id = f"sphere_x{center_coords[0]:.2f}_y{center_coords[1]:.2f}_z{center_coords[2]:.2f}_r{radius:.2f}"
        output_filename = os.path.join(output_dir, f"{sphere_id}.msh")
        
        # Save the modified mesh
        gm_surf.write(output_filename)
        
        # Create the .msh.opt file with custom color map and alpha settings for both fields
        with open(f"{output_filename}.opt", 'w') as f:
            f.write(f"""
    // Hide 2D mesh element faces for cleaner field visualization
    Mesh.SurfaceFaces = 0;       // Hide surface faces
    Mesh.SurfaceEdges = 0;       // Hide surface edges
    Mesh.Points = 0;             // Hide mesh points
    Mesh.Lines = 0;              // Hide mesh lines

    // Make View[1] (Spherical_ROI_field) visible with custom colormap
    View[1].Visible = 1;
    View[1].ColormapNumber = 2;  // Use the second predefined colormap (different from cortical)
    View[1].RangeType = 2;       // Custom range
    View[1].CustomMin = 0;       // Specific minimum value
    View[1].CustomMax = {max_value};  // Specific maximum value for TI_max
    View[1].ShowScale = 1;       // Show the color scale

    // Add alpha/transparency based on value (slightly different for spherical ROIs)
    View[1].ColormapAlpha = 1;
    View[1].ColormapAlphaPower = 0.1;

    // Make View[2] (TI_normal_ROI) visible with different colormap (if available)
    View[2].Visible = 0;         // Initially hidden - user can toggle
    View[2].ColormapNumber = 3;  // Use the third predefined colormap
    View[2].RangeType = 2;       // Custom range
    View[2].CustomMin = 0;       // Specific minimum value
    View[2].CustomMax = {normal_max_value};  // Specific maximum value for TI_normal
    View[2].ShowScale = 1;       // Show the color scale

    // Add alpha/transparency based on value
    View[2].ColormapAlpha = 1;
    View[2].ColormapAlphaPower = 0.1;
    
    // Sphere information as comments
    // Sphere center: ({center_coords[0]:.2f}, {center_coords[1]:.2f}, {center_coords[2]:.2f})
    // Sphere radius: {radius:.2f} mm
    // View[1]: TI_max field (max value: {max_value:.6f})
    // View[2]: TI_normal field (max value: {normal_max_value:.6f})
    """)
        
        self.logger.info(f"Created spherical ROI visualization: {output_filename}")
        self.logger.info(f"Sphere center: ({center_coords[0]:.2f}, {center_coords[1]:.2f}, {center_coords[2]:.2f})")
        self.logger.info(f"Sphere radius: {radius:.2f} mm")
        self.logger.info(f"Visualization settings saved to: {output_filename}.opt")
        
        return output_filename

class VoxelVisualizer(Visualizer):
    """
    Class for generating voxel-specific visualizations.
    """
    
    def __init__(self, output_dir: str, logger=None):
        """
        Initialize the VoxelVisualizer class.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
            logger: Optional logger instance to use. If None, creates its own.
        """
        super().__init__(output_dir, logger)

    def create_cortex_nifti(self, atlas_img, atlas_arr, field_arr, region_id, region_name):
        """
        Create a NIfTI file visualization for a specific cortical region.
        
        Args:
            atlas_img (nibabel.Nifti1Image): Atlas image object
            atlas_arr (numpy.ndarray): Atlas data array
            field_arr (numpy.ndarray): Field data array
            region_id (int): ID of the target region
            region_name (str): Name of the target region
            
        Returns:
            str: Path to the created visualization file
        """
        if nib is None:
            self.logger.warning("nibabel not available. Cannot create NIfTI visualization.")
            return None
            
        self.logger.info(f"Creating NIfTI visualization for region: {region_name} (ID: {region_id})")
        # Create mask for this region
        region_mask = (atlas_arr == region_id)
        
        # Create visualization array (zeros everywhere except the region)
        vis_arr = np.zeros_like(atlas_arr)
        vis_arr[region_mask] = field_arr[region_mask]
        
        # Save overlay file directly in the output directory
        output_filename = os.path.join(self.output_dir, f"{region_name}_ROI.nii.gz")
        
        # Save as NIfTI
        vis_img = nib.Nifti1Image(vis_arr, atlas_img.affine)
        nib.save(vis_img, output_filename)
        
        self.logger.info(f"Created visualization: {output_filename}")
        return output_filename

    def _generate_region_visualization(self, atlas_img, atlas_arr, field_arr, region_id, region_name, output_dir):
        """Generate a NIfTI file visualization for a specific cortical region and save it directly to the specified directory."""
        if nib is None:
            self.logger.warning("nibabel not available. Cannot create NIfTI visualization.")
            return None
            
        # Create mask for this region
        region_mask = (atlas_arr == region_id)
        
        # Ensure field_arr is 3D for visualization
        if len(field_arr.shape) == 4:
            viz_field_arr = field_arr[:,:,:,0]  # Use the first volume
        else:
            viz_field_arr = field_arr
        
        # Create visualization array (zeros everywhere except the region)
        vis_arr = np.zeros_like(atlas_arr)
        vis_arr[region_mask] = viz_field_arr[region_mask]
        
        # Create output filename directly in the region directory
        output_filename = os.path.join(output_dir, f"{region_name}_ROI.nii.gz")
        
        # Save as NIfTI
        import nibabel as nib
        vis_img = nib.Nifti1Image(vis_arr, atlas_img.affine)
        nib.save(vis_img, output_filename)
        
        self.logger.info(f"Created visualization: {output_filename}")
        return output_filename

    def find_region(self, target_region, region_info):
        """Find region ID and name based on input.
        
        Args:
            target_region (str or int): Target region name or ID
            region_info (dict): Dictionary with region information
            
        Returns:
            tuple: (region_id, region_name)
        """
        # Check if target_region is an ID (int) or can be converted to one
        try:
            region_id = int(target_region)
            # If it's an ID, get the name from region_info if available
            if region_info and region_id in region_info:
                region_name = region_info[region_id]['name']
            else:
                region_name = f"Region {region_id}"
            return region_id, region_name
        except ValueError:
            # target_region is a string name, need to find the corresponding ID
            if not region_info:
                raise ValueError("Region labels are required to look up regions by name")
            
            # Search for the region name (case-insensitive)
            target_lower = target_region.lower()
            for region_id, info in region_info.items():
                if target_lower in info['name'].lower():
                    return region_id, info['name']
            
            # If we get here, region name was not found
            raise ValueError(f"Region name '{target_region}' not found in region labels")