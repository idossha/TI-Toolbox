import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
import simnibs

class Visualizer:
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
        self.output_dir = output_dir
        
        # Create output directories if they don't exist
        self.cortex_plot_dir = os.path.join(output_dir, 'cortex_plots')
        self.node_plot_dir = os.path.join(output_dir, 'node_plots')
        self.voxel_plot_dir = os.path.join(output_dir, 'voxel_plots')
        
        for directory in [self.cortex_plot_dir, self.node_plot_dir, self.voxel_plot_dir]:
            os.makedirs(directory, exist_ok=True)

    def generate_cortex_scatter_plot(self, results, atlas_type, data_type='voxel'):
        """
        Generate a scatter plot of median values for all cortical regions.
        
        Args:
            results (dict): Dictionary of analysis results from analyze_whole_head
            atlas_type (str): Type of atlas used for analysis
            data_type (str): Type of data being visualized ('voxel' or 'node')
        """
        # Filter out regions with None values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        
        if not valid_results:
            print("Warning: No valid results to plot")
            return
        
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
        
        # Save plot
        output_file = os.path.join(self.cortex_plot_dir, f'cortex_analysis_{atlas_type}.png')
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
        
        # Save sorted plot
        sorted_output_file = os.path.join(self.cortex_plot_dir, f'cortex_analysis_sorted_{atlas_type}.png')
        plt.savefig(sorted_output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated sorted scatter plot: {sorted_output_file}")

    def generate_value_distribution_plot(self, field_values, region_name, atlas_type, mean_value, max_value, min_value, data_type='voxel'):
        """
        Generate a raincloud plot showing the distribution of individual values within a region.
        
        Args:
            field_values (numpy.ndarray): Array of field values for elements in the ROI
            region_name (str): Name of the region being analyzed
            atlas_type (str): Type of atlas used
            mean_value (float): Mean field value for the region
            max_value (float): Maximum field value for the region
            min_value (float): Minimum field value for the region
            data_type (str): Type of data being visualized ('voxel' or 'node')
        """
        # Select appropriate plot directory
        plot_dir = self.voxel_plot_dir if data_type == 'voxel' else self.node_plot_dir
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), 
                                      gridspec_kw={'height_ratios': [3, 1]})
        
        # Calculate adaptive jitter based on local density
        # First, create bins to estimate local density
        n_bins = 50
        hist, bin_edges = np.histogram(field_values, bins=n_bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        
        # Calculate density for each point
        point_densities = np.zeros_like(field_values)
        for i, value in enumerate(field_values):
            # Find the bin this point belongs to
            bin_idx = np.digitize(value, bin_edges) - 1
            if bin_idx >= 0 and bin_idx < len(hist):
                point_densities[i] = hist[bin_idx]
        
        # Normalize densities to get jitter scale
        max_density = np.max(point_densities)
        jitter_scales = 0.4 * (point_densities / max_density)  # Scale proportionally with density
        
        # Create the raincloud plot in the top subplot
        # First, create the half-violin plot
        violin = ax1.violinplot(field_values, vert=True, showextrema=True, 
                              positions=[0], widths=0.8)
        
        # Customize violin plot
        violin['bodies'][0].set_facecolor('skyblue')
        violin['bodies'][0].set_alpha(0.3)
        violin['cmaxes'].set_color('black')
        violin['cmins'].set_color('black')
        violin['cbars'].set_color('black')
        
        # Add the scatter plot with adaptive jitter
        jitter = np.random.normal(0, jitter_scales, len(field_values))
        scatter = ax1.scatter(jitter, 
                            field_values,
                            c=field_values,  # Color by value
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
        ax1.set_xlim(-0.5, 0.5)  # Limit x-axis to show only the violin and scatter
        ax1.set_xticks([])  # Remove x-axis ticks
        
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
        
        # Save plot
        output_file = os.path.join(plot_dir, f'{data_type}_values_{region_name}_{atlas_type}.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated {data_type} value distribution plot: {output_file}")


class MeshVisualizer(Visualizer):
    """
    Class for generating mesh-specific visualizations.
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize the MeshVisualizer class.
        
        Args:
            output_dir (str): Directory where visualization files will be saved
        """
        super().__init__(output_dir)
        self.mesh_vis_dir = os.path.join(output_dir, 'cortex_visuals')
        os.makedirs(self.mesh_vis_dir, exist_ok=True)

    def visualize_cortex_roi(self, gm_surf, roi_mask, target_region, field_values, max_value, output_dir=None):
        """
        Create visualization files for a specific cortical ROI in mesh data.
        
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
            output_filename = os.path.join(self.mesh_vis_dir, f"brain_with_{target_region}_ROI.msh")
        
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
        self.voxel_vis_dir = os.path.join(output_dir, 'voxel_visuals')
        os.makedirs(self.voxel_vis_dir, exist_ok=True)

    # Add voxel-specific visualization methods here
    # For example, methods for 3D volume rendering, slice views, etc. 