"""
MOVEA Visualization Module
Includes field plotting, NIfTI generation, and brain visualization
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend to avoid threading issues
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set seaborn style for professional plots with white background
sns.set_style("white")
sns.set_context("paper", font_scale=1.1)
sns.set_palette("colorblind")

# Configure matplotlib for high-quality output
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Helvetica', 'Arial'],
    'font.size': 11,
    'axes.linewidth': 1.5,
    'axes.edgecolor': '#333333',
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
    'grid.linewidth': 0.5,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
})


class MOVEAVisualizer:
    """Visualization tools for MOVEA optimization results"""

    def __init__(self, output_dir=None, progress_callback=None):
        """
        Initialize visualizer

        Args:
            output_dir: Directory for saving visualizations
            progress_callback: Optional callback function(message, type) for progress updates
        """
        self.output_dir = Path(output_dir) if output_dir else Path('.')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._progress_callback = progress_callback

    def _log(self, message, msg_type='info'):
        """Send log message through callback or fallback to print"""
        if self._progress_callback:
            self._progress_callback(message, msg_type)
        else:
            print(message)
    
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
            self._log("No optimization results to plot", 'warning')
            return None

        # Extract data - use generation number if available, otherwise use index
        generations = []
        field_strengths = []
        costs = []

        for i, result in enumerate(optimization_results):
            # Use generation number if available, otherwise use sequential numbering
            gen_num = result.get('generation', i + 1)
            generations.append(gen_num)
            field_strengths.append(result.get('field_strength', 0))
            costs.append(result.get('cost', 0))

        # Prepare data for seaborn plotting
        df_field = pd.DataFrame({
            'Generation': generations,
            'Value': field_strengths,
            'Type': 'Field Strength (V/m)'
        })
        df_cost = pd.DataFrame({
            'Generation': generations,
            'Value': costs,
            'Type': 'Cost (1/Field)'
        })

        # Create figure with professional styling
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6), facecolor='white')

        # Professional color palette
        colors = sns.color_palette("colorblind", 2)
        field_color = colors[0]  # Blue
        cost_color = colors[1]   # Orange

        # Plot field strength with professional styling
        sns.lineplot(data=df_field, x='Generation', y='Value', ax=ax1,
                    marker='o', markersize=6, linewidth=2.0,
                    color=field_color, markerfacecolor=field_color,
                    markeredgecolor='white', markeredgewidth=1.5,
                    alpha=0.9)
        ax1.set_xlabel('Generation', fontsize=12, fontweight='normal', labelpad=10)
        ax1.set_ylabel('Field Strength (V/m)', fontsize=12, fontweight='normal', labelpad=10)
        ax1.set_title('Field Strength Convergence', fontsize=14, fontweight='bold', pad=20)
        ax1.grid(True, alpha=0.4, linestyle='-', linewidth=0.5, color='#E0E0E0')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # Add best value annotation with professional styling
        best_idx = np.argmax(field_strengths)
        ax1.annotate(f'Peak: {field_strengths[best_idx]:.4f} V/m',
                    xy=(generations[best_idx], field_strengths[best_idx]),
                    xytext=(15, 15), textcoords='offset points',
                    fontsize=10, ha='left', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                             edgecolor=field_color, linewidth=1.5, alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color=field_color,
                                   connectionstyle='arc3,rad=0.1', alpha=0.8, linewidth=1.5))

        # Plot cost with professional styling
        sns.lineplot(data=df_cost, x='Generation', y='Value', ax=ax2,
                    marker='s', markersize=6, linewidth=2.0,
                    color=cost_color, markerfacecolor=cost_color,
                    markeredgecolor='white', markeredgewidth=1.5,
                    alpha=0.9)
        ax2.set_xlabel('Generation', fontsize=12, fontweight='normal', labelpad=10)
        ax2.set_ylabel('Cost (1/Field)', fontsize=12, fontweight='normal', labelpad=10)
        ax2.set_title('Cost Reduction', fontsize=14, fontweight='bold', pad=20)
        ax2.grid(True, alpha=0.4, linestyle='-', linewidth=0.5, color='#E0E0E0')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        # Add best value annotation with professional styling
        best_idx = np.argmin(costs)
        ax2.annotate(f'Minimum: {costs[best_idx]:.4f}',
                    xy=(generations[best_idx], costs[best_idx]),
                    xytext=(15, -15), textcoords='offset points',
                    fontsize=10, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                             edgecolor=cost_color, linewidth=1.5, alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color=cost_color,
                                   connectionstyle='arc3,rad=-0.1', alpha=0.8, linewidth=1.5))

        # Improve overall layout
        plt.tight_layout(pad=2.0)
        fig.patch.set_facecolor('white')

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            self._log(f"Convergence plot saved to: {save_path}", 'success')

        return fig
    
    def plot_pareto_front(self, pareto_solutions, save_path=None, target_name="ROI"):
        """
        Plot Pareto front for multi-objective optimization with enhanced visualization
        Shows trade-off between intensity and focality, highlighting top solutions
        
        Args:
            pareto_solutions: List of solution dictionaries with 'intensity_field' and 'focality'
            save_path: Path to save figure
            target_name: Name of the target region for labeling
        
        Returns:
            fig: Matplotlib figure
        """
        if not pareto_solutions:
            self._log("No Pareto solutions to plot", 'warning')
            return None
        
        # Extract values and calculate focality ratio
        intensity_values = np.array([s['intensity_field'] for s in pareto_solutions])
        focality_values = np.array([s['focality'] for s in pareto_solutions])
        focality_ratios = intensity_values / (focality_values + 1e-10)  # Avoid division by zero
        
        # Find top 5 solutions by focality ratio
        top_indices = np.argsort(focality_ratios)[-5:]
        
        self._log(f"Plotting Pareto front with {len(pareto_solutions)} solutions", 'info')
        self._log(f"  Intensity range: {intensity_values.min():.6f} - {intensity_values.max():.6f} V/m", 'info')
        self._log(f"  Focality range: {focality_values.min():.6f} - {focality_values.max():.6f} V/m", 'info')
        self._log(f"  Best focality ratio: {focality_ratios.max():.4f}", 'info')
        
        # Create figure with seaborn styling
        fig, ax = plt.subplots(figsize=(12, 9))
        
        # Plot all solutions
        scatter = ax.scatter(intensity_values, focality_values, 
                           s=120, c=focality_ratios, cmap='viridis', 
                           alpha=0.7, edgecolors='black', linewidths=1)
        
        # Highlight top 5 solutions with larger red markers
        ax.scatter(intensity_values[top_indices], focality_values[top_indices],
                  s=300, c='red', marker='*', 
                  edgecolors='darkred', linewidths=2,
                  label='Top 5 Focality Ratio', zorder=5)
        
        # Add text labels for top solutions
        for i, idx in enumerate(top_indices):
            ax.annotate(f'#{i+1}', 
                       (intensity_values[idx], focality_values[idx]),
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=10, fontweight='bold')
        
        # Add colorbar for focality ratio
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Focality Ratio (Intensity/Whole Brain)', fontsize=14)
        
        # Enhanced labels and title
        ax.set_xlabel(f'{target_name} Electric Field (V/m)', fontsize=16, fontweight='bold')
        ax.set_ylabel('Whole-Brain Electric Field (V/m)', fontsize=16, fontweight='bold')
        ax.set_title(f'Multi-Objective Optimization Results: {target_name}\n'
                    f'Pareto Front Analysis (n={len(pareto_solutions)})', 
                    fontsize=18, fontweight='bold', pad=20)
        
        # Add grid with custom style
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        
        # Set reasonable axis limits with padding
        x_margin = (intensity_values.max() - intensity_values.min()) * 0.12
        y_margin = (focality_values.max() - focality_values.min()) * 0.12
        ax.set_xlim([intensity_values.min() - x_margin, intensity_values.max() + x_margin])
        ax.set_ylim([focality_values.min() - y_margin, focality_values.max() + y_margin])
        
        # Add legend with custom styling
        legend = ax.legend(loc='upper right', fontsize=14, 
                          frameon=True, fancybox=True, shadow=True)
        legend.get_frame().set_alpha(0.9)
        
        # Add ideal point annotation
        ax.annotate('Ideal Point →', 
                   xy=(intensity_values.max(), focality_values.min()),
                   xytext=(intensity_values.max() - x_margin*0.5, focality_values.min() + y_margin*0.5),
                   arrowprops=dict(arrowstyle='->', lw=2, color='gray', alpha=0.5),
                   fontsize=12, color='gray', style='italic')
        
        # Improve layout
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
            self._log(f"Enhanced Pareto front saved to: {save_path}", 'success')
            self._log(f"  Total solutions: {len(intensity_values)}", 'info')
            self._log(f"  Top 5 focality ratios: {', '.join([f'{r:.3f}' for r in sorted(focality_ratios)[-5:]])}", 'info')
        
        plt.close(fig)  # Close to free memory

        return fig



def visualize_complete_results(optimizer, result, output_dir='results', electrode_names=None):
    """
    Create complete visualization suite for optimization results

    Args:
        optimizer: TIOptimizer or ScipyTIOptimizer instance
        result: Optimization result dictionary
        output_dir: Output directory for all visualizations
        electrode_names: List of electrode names for plotting (optional)

    Returns:
        dict: Paths to generated files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    visualizer = MOVEAVisualizer(output_dir)
    generated_files = {}

    # 1. Plot convergence for optimization results
    if len(optimizer.optimization_results) > 0:
        conv_path = output_dir / 'convergence.png'
        visualizer.plot_convergence(optimizer.optimization_results, save_path=conv_path)
        generated_files['convergence'] = str(conv_path)

    visualizer._log(f"\n{'='*60}", 'default')
    visualizer._log(f"Visualization Complete", 'success')
    visualizer._log(f"{'='*60}", 'default')
    visualizer._log(f"Output directory: {output_dir}", 'info')
    for name, path in generated_files.items():
        visualizer._log(f"  {name}: {path}", 'default')
    visualizer._log(f"{'='*60}\n", 'default')

    return generated_files

