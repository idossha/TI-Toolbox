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
    - Distribution plots
    - Scatter plots
    - ROI visualizations
    - Surface overlays
    - Statistical summaries

Example Usage:
    ```python
    # Initialize visualizer
    visualizer = VoxelVisualizer(output_dir="/path/to/output")
    
    # Generate distribution plot
    visualizer.generate_value_distribution_plot(
        values=field_values,
        region_name="Left-Hippocampus",
        atlas_type="DK40",
        mean_value=0.5,
        max_value=1.0,
        min_value=0.1,
        data_type='voxel'
    )
    
    # Generate scatter plot
    visualizer.generate_cortex_scatter_plot(
        results=analysis_results,
        atlas_type="DK40",
        data_type='voxel'
    )
    ```

Dependencies:
    - numpy
    - matplotlib
    - nibabel (for VoxelVisualizer)
    - simnibs (for MeshVisualizer)
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
import simnibs
from pathlib import Path
import csv
from datetime import datetime


class BaseVisualizer:
    """
    Base class for visualization functionality.
    
    This class provides common visualization methods that can be used
    by both voxel-based and mesh-based visualizers.
    
    Attributes:
        output_dir (str): Directory where visualization files will be saved
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize the BaseVisualizer.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
        """
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
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
        # Generate timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create appropriate filename
        if region_name:
            filename = f"{analysis_type}_{region_name}_{timestamp}.csv"
        else:
            filename = f"{analysis_type}_analysis_{timestamp}.csv"
        
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
            
        print(f"Saved analysis results to: {output_path}")
        return output_path

    def save_whole_head_results_to_csv(self, results, atlas_type, data_type='node'):
        """
        Save whole-head analysis results to a CSV file.
        
        Args:
            results (dict): Whole-head analysis results to save
            atlas_type (str): Type of atlas used
            data_type (str): Type of data ('node' or 'voxel')
        
        Returns:
            str: Path to the created CSV file
        """
        # Create CSV directory if it doesn't exist
        csv_dir = os.path.join(self.output_dir, 'csv_results')
        os.makedirs(csv_dir, exist_ok=True)
        
        # Generate timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"whole_head_{atlas_type}_{timestamp}.csv"
        output_path = os.path.join(csv_dir, filename)
        
        # Write results to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header row
            header = ['Region', 'Mean Value', 'Max Value', 'Min Value', f'{data_type.capitalize()}s in ROI']
            writer.writerow(header)
            
            # Write data for each region
            for region_name, region_data in results.items():
                row = [
                    region_name,
                    region_data.get('mean_value', 'N/A'),
                    region_data.get('max_value', 'N/A'),
                    region_data.get('min_value', 'N/A'),
                    region_data.get(f'{data_type}s_in_roi', 0)
                ]
                writer.writerow(row)
        
        print(f"Saved whole-head analysis results to: {output_path}")
        return output_path


class Visualizer(BaseVisualizer):
    """
    Base class for generating visualizations of analysis results.
    Contains common visualization methods used by both mesh and voxel analysis.
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize the Visualizer class.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
        """
        super().__init__(output_dir)
        
        # Only create directories if needed for individual analyses, not for whole-head
        # We'll create these directories on demand in the specific methods that need them
        # instead of creating them all at initialization
    
    def generate_cortex_scatter_plot(self, results, atlas_type, data_type='voxel'):
        """Generate a scatter plot of median values for all cortical regions."""
        # Filter out regions with None values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        
        if not valid_results:
            print("Warning: No valid results to plot")
            return
        
        # Save results to CSV
        self.save_whole_head_results_to_csv(results, atlas_type, data_type)
        
        # Prepare data for plotting
        regions = list(valid_results.keys())
        mean_values = [res['mean_value'] for res in valid_results.values()]
        counts = [res[f'{data_type}s_in_roi'] for res in valid_results.values()]
        
        # Create figure with larger size
        fig, ax = plt.subplots(figsize=(15, 10))
        
        # Create scatter plot with enhanced styling
        scatter = ax.scatter(regions, mean_values, 
                           c=counts,
                           cmap='viridis',
                           s=100,
                           alpha=0.6,
                           edgecolors='black',
                           linewidths=1)
        
        # Add colorbar with enhanced styling
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label(f'Number of {data_type.capitalize()}s', fontsize=12, fontweight='bold')
        
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
        
        # Save plot directly in the output directory (not in a subdirectory)
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
        sorted_counts = [counts[i] for i in sorted_indices]
        
        # Create sorted scatter plot with enhanced styling
        scatter = ax.scatter(range(len(sorted_regions)), sorted_values,
                           c=sorted_counts,
                           cmap='viridis',
                           s=100,
                           alpha=0.6,
                           edgecolors='black',
                           linewidths=1)
        
        # Add colorbar with enhanced styling
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label(f'Number of {data_type.capitalize()}s', fontsize=12, fontweight='bold')
        
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
        
        # Save sorted plot directly in the output directory (not in a subdirectory)
        sorted_output_file = os.path.join(self.output_dir, f'cortex_analysis_sorted_{atlas_type}.png')
        plt.savefig(sorted_output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated sorted scatter plot: {sorted_output_file}")

    def generate_value_distribution_plot(self, field_values, region_name, atlas_type, mean_value, max_value, min_value, data_type='voxel'):
        """Generate a raincloud plot showing the distribution of individual values within a region."""
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), 
                                      gridspec_kw={'height_ratios': [3, 1]})
        
        # Calculate adaptive jitter based on local density
        n_bins = 50
        hist, bin_edges = np.histogram(field_values, bins=n_bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        
        # Calculate density for each point
        point_densities = np.zeros_like(field_values)
        for i, value in enumerate(field_values):
            bin_idx = np.digitize(value, bin_edges) - 1
            if bin_idx >= 0 and bin_idx < len(hist):
                point_densities[i] = hist[bin_idx]
        
        # Normalize densities to get jitter scale
        max_density = np.max(point_densities)
        jitter_scales = 0.4 * (point_densities / max_density)
        
        # Create the raincloud plot in the top subplot
        violin = ax1.violinplot(field_values, vert=True, showextrema=True, 
                              positions=[0], widths=0.8)
        
        # Customize violin plot
        violin['bodies'][0].set_facecolor('skyblue')
        violin['bodies'][0].set_alpha(0.3)
        violin['cmaxes'].set_color('black')
        violin['cmins'].set_color('black')
        violin['cbars'].set_color('black')
        
        # Add scatter plot with adaptive jitter
        jitter = np.random.normal(0, jitter_scales, len(field_values))
        scatter = ax1.scatter(jitter, 
                            field_values,
                            c=field_values,
                            cmap='viridis',
                            s=20,
                            alpha=0.6,
                            edgecolors='black',
                            linewidths=0.5)
        
        # Add mean, max, and min lines
        ax1.axhline(y=mean_value, color='r', linestyle='--', alpha=0.7, label=f'Mean: {mean_value:.6f}')
        ax1.axhline(y=max_value, color='g', linestyle='--', alpha=0.7, label=f'Max: {max_value:.6f}')
        ax1.axhline(y=min_value, color='b', linestyle='--', alpha=0.7, label=f'Min: {min_value:.6f}')
        
        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax1)
        cbar.set_label('Field Value', fontsize=10, fontweight='bold')
        
        # Customize main plot
        ax1.set_title(f'{data_type.capitalize()} Value Distribution - {region_name}\n({atlas_type} Atlas)', 
                     pad=20, 
                     fontsize=12, 
                     fontweight='bold')
        ax1.set_ylabel('Field Value', fontsize=10, fontweight='bold')
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.legend(loc='upper left')
        ax1.set_xlim(-0.5, 0.5)
        ax1.set_xticks([])
        
        # Histogram in the bottom subplot
        ax2.hist(field_values, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
        ax2.axvline(x=mean_value, color='r', linestyle='--', alpha=0.7, label=f'Mean: {mean_value:.6f}')
        ax2.axvline(x=max_value, color='g', linestyle='--', alpha=0.7, label=f'Max: {max_value:.6f}')
        ax2.axvline(x=min_value, color='b', linestyle='--', alpha=0.7, label=f'Min: {min_value:.6f}')
        
        # Customize histogram
        ax2.set_title('Value Distribution Histogram', fontsize=10, fontweight='bold')
        ax2.set_xlabel('Field Value', fontsize=10, fontweight='bold')
        ax2.set_ylabel(f'Number of {data_type.capitalize()}s', fontsize=10, fontweight='bold')
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.legend(loc='upper right')
        
        # Adjust layout
        plt.tight_layout()
        
        # Create timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save plot directly to the output directory
        output_file = os.path.join(self.output_dir, f'{data_type}_distribution_{region_name}_{timestamp}.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated {data_type} value distribution plot: {output_file}")
        
        return output_file

    def _generate_whole_head_plots(self, results, atlas_type, data_type='voxel'):
        """Generate scatter plots for whole head analysis directly in the main output directory."""
        # Filter out regions with None values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        
        if not valid_results:
            print("Warning: No valid results to plot")
            return
        
        try:
            # Prepare data for plotting
            regions = list(valid_results.keys())
            mean_values = [res['mean_value'] for res in valid_results.values()]
            
            # Check if voxel count data is available, and use it if possible
            try:
                # Attempt to get voxel counts if they're in the data
                counts = [res.get(f'{data_type}s_in_roi', 1) for res in valid_results.values()]
                use_counts_for_color = True
            except (KeyError, AttributeError):
                # If not available, use a default color
                print(f"Note: '{data_type}s_in_roi' not found in results, using default coloring")
                counts = [1 for _ in valid_results.values()]
                use_counts_for_color = False
            
            # Create timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Dynamically calculate figure width based on number of regions
            num_regions = len(regions)
            
            # Base width for a plot with 30 regions
            base_width = 15
            
            # Calculate width scaling factor (more regions = wider plot)
            # This adds extra width as the number of regions increases
            width_scaling = max(1.0, num_regions / 30)
            
            # Calculate height scaling factor (taller for many regions to maintain proportion)
            height_scaling = min(1.2, max(1.0, num_regions / 60))
            
            # Calculate final dimensions with minimum width
            fig_width = max(base_width, base_width * width_scaling)
            fig_height = 10 * height_scaling
            
            # Adjust font size for region labels based on number of regions
            if num_regions <= 30:
                label_fontsize = 8
            elif num_regions <= 50:
                label_fontsize = 7
            elif num_regions <= 100:
                label_fontsize = 6
            else:
                label_fontsize = 5
            
            # Create figure for the sorted plot with dynamic size
            plt.figure(figsize=(fig_width, fig_height))
            fig, ax = plt.subplots(figsize=(fig_width, fig_height))
            
            # Sort regions by mean value
            sorted_indices = np.argsort(mean_values)
            sorted_regions = [regions[i] for i in sorted_indices]
            sorted_values = [mean_values[i] for i in sorted_indices]
            
            # Use the coloring approach based on availability of count data
            if use_counts_for_color:
                sorted_counts = [counts[i] for i in sorted_indices]
                scatter = ax.scatter(range(len(sorted_regions)), sorted_values,
                                c=sorted_counts,
                                cmap='viridis',
                                s=100,
                                alpha=0.6,
                                edgecolors='black',
                                linewidths=1)
                
                # Add colorbar with enhanced styling
                cbar = plt.colorbar(scatter, ax=ax)
                cbar.set_label(f'Number of {data_type.capitalize()}s', fontsize=12, fontweight='bold')
            else:
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
            ax.set_xlabel('Region Index', 
                        fontsize=12, 
                        fontweight='bold')
            ax.set_ylabel('Mean Field Value', 
                        fontsize=12, 
                        fontweight='bold')
            
            # Add grid
            ax.grid(True, linestyle='--', alpha=0.3)
            
            # If there are too many regions, we need to limit the displayed labels
            if num_regions > 200:
                # For very large region counts, only show every Nth label
                step = max(1, num_regions // 100)  # Show approximately 100 labels max
                xticks_pos = range(0, len(sorted_regions), step)
                xticks_labels = [sorted_regions[i] for i in xticks_pos]
                ax.set_xticks(xticks_pos)
                ax.set_xticklabels(xticks_labels, rotation=45, ha='right', fontsize=label_fontsize)
            else:
                # Otherwise show all labels
                ax.set_xticks(range(len(sorted_regions)))
                ax.set_xticklabels(sorted_regions, rotation=45, ha='right', fontsize=label_fontsize)
            
            # Adjust layout to prevent label cutoff
            plt.tight_layout()
            
            # Save plot directly in the main output directory (without "sorted" in the name)
            output_file = os.path.join(self.output_dir, f'cortex_analysis_{atlas_type}_{timestamp}.png')
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"Generated cortical region plot: {output_file}")
            
            return output_file
            
        except Exception as e:
            # If there's any error during plotting, log it but don't stop the overall analysis
            import traceback
            print(f"Warning: Failed to generate plot: {str(e)}")
            print(f"Error details: {traceback.format_exc()}")
            print("Continuing with analysis without visualizations.")
            return None


class MeshVisualizer(Visualizer):
    """Class for generating mesh-specific visualizations."""
    
    def __init__(self, output_dir: str):
        """Initialize the MeshVisualizer class."""
        super().__init__(output_dir)

    def visualize_cortex_roi(self, gm_surf, roi_mask, target_region, field_values, max_value, output_dir=None):
        """Create visualization files for a specific cortical ROI in mesh data."""
        # Create a new field with field values only in ROI (zeros elsewhere)
        masked_field = np.zeros(gm_surf.nodes.nr)
        masked_field[roi_mask] = field_values[roi_mask]
        
        # Add this as a new field to the original mesh
        gm_surf.add_node_field(masked_field, 'ROI_field')
        
        # Create the output directory if it doesn't exist
        if output_dir:
            # Use the specified output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # For individual region analysis, create the cortex_visuals directory
            if not os.path.basename(output_dir).startswith('whole_head'):
                vis_dir = os.path.join(output_dir, 'cortex_visuals')
                os.makedirs(vis_dir, exist_ok=True)
                output_filename = os.path.join(vis_dir, f"brain_with_{target_region}_ROI.msh")
            else:
                # For whole-head analysis, save directly in the region directory
                output_filename = os.path.join(output_dir, f"brain_with_{target_region}_ROI.msh")
        else:
            # Use the class's output directory and create the cortex_visuals directory
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


class VoxelVisualizer(Visualizer):
    """
    Class for generating voxel-specific visualizations.
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize the VoxelVisualizer class.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
        """
        super().__init__(output_dir)

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
        # Create mask for this region
        region_mask = (atlas_arr == region_id)
        
        # Create visualization array (zeros everywhere except the region)
        vis_arr = np.zeros_like(atlas_arr)
        vis_arr[region_mask] = field_arr[region_mask]
        
        # Create cortex_visuals directory for individual region analysis
        # If the output directory contains 'whole_head', assume it's a whole-head analysis
        if 'whole_head' not in self.output_dir:
            vis_dir = os.path.join(self.output_dir, 'cortex_visuals')
            os.makedirs(vis_dir, exist_ok=True)
            output_filename = os.path.join(vis_dir, f"brain_with_{region_name}_ROI.nii.gz")
        else:
            # For whole-head analysis, save directly in the output directory
            output_filename = os.path.join(self.output_dir, f"brain_with_{region_name}_ROI.nii.gz")
        
        # Save as NIfTI
        import nibabel as nib
        vis_img = nib.Nifti1Image(vis_arr, atlas_img.affine)
        nib.save(vis_img, output_filename)
        
        print(f"Created visualization: {output_filename}")
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