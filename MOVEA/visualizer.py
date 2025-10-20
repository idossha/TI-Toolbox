"""
MOVEA Visualization Module
Includes field plotting, NIfTI generation, and brain visualization
"""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend to avoid threading issues
import matplotlib.pyplot as plt
from pathlib import Path


class MOVEAVisualizer:
    """Visualization tools for MOVEA optimization results"""
    
    def __init__(self, output_dir=None):
        """
        Initialize visualizer
        
        Args:
            output_dir: Directory for saving visualizations
        """
        self.output_dir = Path(output_dir) if output_dir else Path('.')
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_convergence(self, optimization_results, save_path=None):
        """
        Plot optimization convergence over generations
        
        Args:
            optimization_results: List of results from optimizer.optimization_results
            save_path: Path to save figure (optional)
        
        Returns:
            fig: Matplotlib figure
        """
        if not optimization_results:
            print("No optimization results to plot")
            return None
        
        # Extract data
        generations = []
        field_strengths = []
        costs = []
        
        for i, result in enumerate(optimization_results):
            generations.append(i + 1)
            field_strengths.append(result.get('field_strength', 0))
            costs.append(result.get('cost', 0))
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        
        # Plot field strength
        ax1.plot(generations, field_strengths, 'o-', linewidth=2, markersize=6)
        ax1.set_xlabel('Run Number', fontsize=12)
        ax1.set_ylabel('Field Strength (V/m)', fontsize=12)
        ax1.set_title('Target Field Strength', fontsize=14)
        ax1.grid(True, alpha=0.3)
        
        # Plot cost
        ax2.plot(generations, costs, 's-', color='orange', linewidth=2, markersize=6)
        ax2.set_xlabel('Run Number', fontsize=12)
        ax2.set_ylabel('Cost (1/Field)', fontsize=12)
        ax2.set_title('Optimization Cost', fontsize=14)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Convergence plot saved to: {save_path}")
        
        return fig
    
    def plot_pareto_front(self, pareto_solutions, save_path=None, target_name="ROI"):
        """
        Plot Pareto front for multi-objective optimization (like original MOVEA)
        Shows trade-off between intensity and focality
        
        Args:
            pareto_solutions: List of solution dictionaries with 'intensity_field' and 'focality'
            save_path: Path to save figure
        
        Returns:
            fig: Matplotlib figure
        """
        if not pareto_solutions:
            print("No Pareto solutions to plot")
            return None
        
        # Extract intensity and focality values
        intensity_values = np.array([s['intensity_field'] for s in pareto_solutions])
        focality_values = np.array([s['focality'] for s in pareto_solutions])
        
        print(f"DEBUG: Plotting Pareto with {len(pareto_solutions)} solutions")
        print(f"  Intensity range: {intensity_values.min():.6f} - {intensity_values.max():.6f} V/m")
        print(f"  Focality range: {focality_values.min():.6f} - {focality_values.max():.6f} V/m")
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Scatter plot like original MOVEA - use larger markers
        ax.scatter(intensity_values, focality_values, 
                  s=100, c='black', marker="o", alpha=0.8, label='MOVEA Solutions', edgecolors='red', linewidths=1.5)
        
        # Clear axis labels
        ax.set_xlabel(f'{target_name} Electric Field (V/m)', fontsize=16)
        ax.set_ylabel('Whole-Brain Electric Field (V/m)', fontsize=16)
        ax.set_title(f'Intensity vs Focality Trade-off: {target_name}', fontsize=18)
        ax.legend(loc='best', fontsize=16, markerscale=1.0)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Set reasonable axis limits
        x_margin = (intensity_values.max() - intensity_values.min()) * 0.1
        y_margin = (focality_values.max() - focality_values.min()) * 0.1
        ax.set_xlim([intensity_values.min() - x_margin, intensity_values.max() + x_margin])
        ax.set_ylim([focality_values.min() - y_margin, focality_values.max() + y_margin])
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Pareto front saved to: {save_path}")
            print(f"  Data points plotted: {len(intensity_values)}")
        
        plt.close(fig)  # Close to free memory
        
        return fig
    
    def create_field_nifti(self, field_values, voxel_positions, reference_nifti, 
                          output_path, interpolate=True):
        """
        Create NIfTI file from field values
        
        Args:
            field_values: Array of field magnitudes [n_voxels]
            voxel_positions: Voxel MNI coordinates [n_voxels, 3]
            reference_nifti: Path to reference NIfTI file
            output_path: Output path for NIfTI file
            interpolate: Whether to interpolate to full brain grid
        
        Returns:
            output_path: Path to created NIfTI file
        
        Note: This method is currently not used by the GUI but kept for future use.
        """
        try:
            import nibabel as nib
            from nibabel.affines import apply_affine
        except ImportError:
            print("nibabel not installed. Install with: pip install nibabel")
            return None
        
        # Load reference image
        ref_img = nib.load(reference_nifti)
        ref_data = ref_img.get_fdata()
        affine = ref_img.affine
        
        # Create empty output volume
        output_data = np.zeros_like(ref_data)
        
        # Convert MNI coordinates to voxel indices
        def mni_to_voxel(mni_coord):
            """Convert MNI coordinate to voxel index"""
            return np.dot(np.linalg.inv(affine), 
                         np.append(mni_coord, 1))[:3]
        
        # Fill in field values
        for idx, pos in enumerate(voxel_positions):
            voxel_idx = mni_to_voxel(pos)
            voxel_idx = np.round(voxel_idx).astype(int)
            
            # Check bounds
            if (0 <= voxel_idx[0] < ref_data.shape[0] and
                0 <= voxel_idx[1] < ref_data.shape[1] and
                0 <= voxel_idx[2] < ref_data.shape[2]):
                output_data[voxel_idx[0], voxel_idx[1], voxel_idx[2]] = field_values[idx]
        
        # Interpolate to brain tissue if requested
        if interpolate:
            try:
                from scipy.interpolate import griddata
                
                # Get coordinates where we have field values
                field_coords = []
                field_vals = []
                for idx, pos in enumerate(voxel_positions):
                    if field_values[idx] > 0:
                        voxel_idx = mni_to_voxel(pos)
                        field_coords.append(voxel_idx)
                        field_vals.append(field_values[idx])
                
                field_coords = np.array(field_coords)
                field_vals = np.array(field_vals)
                
                # Get brain tissue coordinates (GM=1, WM=2)
                brain_mask = (ref_data == 1) | (ref_data == 2)
                brain_coords = np.array(np.where(brain_mask)).T
                
                if len(field_coords) > 0 and len(brain_coords) > 0:
                    # Interpolate
                    interpolated_vals = griddata(
                        field_coords, field_vals, brain_coords, 
                        method='nearest', fill_value=0
                    )
                    
                    # Fill interpolated values
                    output_data = np.zeros_like(ref_data)
                    for i, coord in enumerate(brain_coords):
                        output_data[coord[0], coord[1], coord[2]] = interpolated_vals[i]
                    
                    print(f"Interpolated to {len(brain_coords)} brain voxels")
            
            except ImportError:
                print("scipy not available for interpolation")
        
        # Create and save NIfTI
        output_img = nib.Nifti1Image(output_data, affine)
        nib.save(output_img, output_path)
        
        print(f"NIfTI file saved to: {output_path}")
        return output_path
    
    def visualize_field_on_brain(self, nifti_path, reference_nifti, 
                                 target_coords=None, output_path=None):
        """
        Create brain slice visualization with field overlay
        
        Args:
            nifti_path: Path to field NIfTI file
            reference_nifti: Path to reference/background NIfTI
            target_coords: Target MNI coordinates [x, y, z] for cuts
            output_path: Path to save figure
        
        Returns:
            fig: Matplotlib figure (if nilearn available)
        
        Note: This method is currently not used by the GUI but kept for future use.
        """
        try:
            import nibabel as nib
            from nilearn import plotting, image
        except ImportError:
            print("nilearn/nibabel not installed. Install with: pip install nibabel nilearn")
            return None
        
        # Load images
        field_img = image.load_img(nifti_path)
        bg_img = image.load_img(reference_nifti)
        
        # Set cut coordinates
        if target_coords is None:
            cut_coords = None  # Auto
        else:
            cut_coords = target_coords
        
        # Create visualization
        display = plotting.plot_roi(
            field_img,
            bg_img=bg_img,
            cut_coords=cut_coords,
            black_bg=False,
            cmap=plt.get_cmap('hot'),
            alpha=0.7,
            output_file=output_path
        )
        
        if output_path:
            print(f"Brain visualization saved to: {output_path}")
        
        return display
    
    def visualize_montage(self, result, electrode_positions=None, 
                         electrode_names=None, save_path=None):
        """
        Visualize electrode montage on 2D head plot
        
        Args:
            result: Optimization result dictionary
            electrode_positions: Array of electrode 2D positions [n_electrodes, 2]
            electrode_names: List of electrode names
            save_path: Path to save figure
        
        Returns:
            fig: Matplotlib figure
        """
        electrodes = result['electrodes']
        e1, e2, e3, e4 = electrodes
        
        fig, ax = plt.subplots(figsize=(10, 10))
        
        if electrode_positions is not None:
            # Plot all electrodes
            ax.scatter(electrode_positions[:, 0], electrode_positions[:, 1],
                      s=50, c='lightgray', alpha=0.5, zorder=1)
            
            # Plot active electrodes
            pair1_anodes = [e1]
            pair1_cathodes = [e2]
            pair2_anodes = [e3]
            pair2_cathodes = [e4]
            
            # Plot pair 1
            ax.scatter(electrode_positions[pair1_anodes, 0], 
                      electrode_positions[pair1_anodes, 1],
                      s=200, c='red', marker='o', label='Pair 1 Anode', zorder=3)
            ax.scatter(electrode_positions[pair1_cathodes, 0], 
                      electrode_positions[pair1_cathodes, 1],
                      s=200, c='blue', marker='o', label='Pair 1 Cathode', zorder=3)
            
            # Plot pair 2
            ax.scatter(electrode_positions[pair2_anodes, 0], 
                      electrode_positions[pair2_anodes, 1],
                      s=200, c='orange', marker='s', label='Pair 2 Anode', zorder=3)
            ax.scatter(electrode_positions[pair2_cathodes, 0], 
                      electrode_positions[pair2_cathodes, 1],
                      s=200, c='cyan', marker='s', label='Pair 2 Cathode', zorder=3)
            
            # Draw lines between pairs
            ax.plot([electrode_positions[e1, 0], electrode_positions[e2, 0]],
                   [electrode_positions[e1, 1], electrode_positions[e2, 1]],
                   'r--', linewidth=2, alpha=0.5, zorder=2)
            ax.plot([electrode_positions[e3, 0], electrode_positions[e4, 0]],
                   [electrode_positions[e3, 1], electrode_positions[e4, 1]],
                   'orange', linestyle='--', linewidth=2, alpha=0.5, zorder=2)
            
            # Add labels if names provided
            if electrode_names is not None:
                for idx in [e1, e2, e3, e4]:
                    ax.annotate(electrode_names[idx],
                              (electrode_positions[idx, 0], electrode_positions[idx, 1]),
                              xytext=(5, 5), textcoords='offset points',
                              fontsize=10, fontweight='bold')
        else:
            # Simple representation without positions
            positions_2d = {
                e1: (0, 1), e2: (0, -1),
                e3: (1, 0), e4: (-1, 0)
            }
            
            for idx, pos in positions_2d.items():
                color = 'red' if idx == e1 else 'blue' if idx == e2 else 'orange' if idx == e3 else 'cyan'
                marker = 'o' if idx in [e1, e2] else 's'
                ax.scatter(pos[0], pos[1], s=300, c=color, marker=marker)
                ax.annotate(f"E{idx}", pos, ha='center', va='center', fontsize=12, fontweight='bold')
        
        ax.set_aspect('equal')
        ax.set_title(f"TI Montage - Field Strength: {result['field_strength']:.6f} V/m", 
                    fontsize=14)
        
        # Only show legend if we have labeled items
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc='best', fontsize=10)
        
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Montage visualization saved to: {save_path}")
        
        return fig


def visualize_complete_results(optimizer, result, output_dir='results'):
    """
    Create complete visualization suite for optimization results
    
    Args:
        optimizer: TIOptimizer or ScipyTIOptimizer instance
        result: Optimization result dictionary
        output_dir: Output directory for all visualizations
    
    Returns:
        dict: Paths to generated files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    visualizer = MOVEAVisualizer(output_dir)
    generated_files = {}
    
    # 1. Plot convergence if multiple runs (skip for single run)
    if len(optimizer.optimization_results) > 1:
        conv_path = output_dir / 'convergence.png'
        visualizer.plot_convergence(optimizer.optimization_results, save_path=conv_path)
        generated_files['convergence'] = str(conv_path)
    
    # 2. Create montage visualization
    montage_path = output_dir / 'montage.png'
    visualizer.visualize_montage(result, save_path=montage_path)
    generated_files['montage'] = str(montage_path)
    
    print(f"\n{'='*60}")
    print(f"Visualization Complete")
    print(f"{'='*60}")
    print(f"Output directory: {output_dir}")
    for name, path in generated_files.items():
        print(f"  {name}: {path}")
    print(f"{'='*60}\n")
    
    return generated_files

