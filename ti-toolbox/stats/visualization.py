"""
Visualization utilities for neuroimaging analysis

This module contains functions for:
- Plotting permutation null distributions
- Creating correlation plots
"""

import numpy as np
import matplotlib
# CRITICAL: Set backend BEFORE importing pyplot for Docker compatibility
matplotlib.use('Agg')  # Use non-interactive backend for headless environments
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configure matplotlib for Docker/headless environments
os.environ['MPLBACKEND'] = 'Agg'

# Set seaborn style for consistent appearance
sns.set_style("whitegrid")
sns.set_context("notebook", font_scale=1.0)


def plot_permutation_null_distribution(null_distribution, threshold, observed_clusters, 
                                       output_file, alpha=0.05, cluster_stat='size'):
    """
    Plot permutation null distribution with threshold and observed clusters
    
    Parameters:
    -----------
    null_distribution : ndarray
        Maximum cluster statistics from permutation null distribution
    threshold : float
        Cluster statistic threshold at given alpha level
    observed_clusters : list of dict
        List of observed cluster information (with 'stat_value' and 'size' keys)
    output_file : str
        Path to save PDF file
    alpha : float
        Significance level used
    cluster_stat : {'size', 'mass'}, optional
        Cluster statistic used (default: 'size')
    """
    # Explicitly create new figure (Docker-safe)
    fig, ax = plt.subplots(figsize=(10, 6))
    
    try:
        # Set labels based on cluster statistic
        if cluster_stat == 'size':
            x_label = 'Maximum Cluster Size (voxels)'
            title = 'Permutation Null Distribution of Maximum Cluster Sizes'
            threshold_label = f'Threshold (α={alpha}): {threshold:.1f} voxels'
        else:  # cluster_stat == 'mass'
            x_label = 'Maximum Cluster Mass (sum of t-statistics)'
            title = 'Permutation Null Distribution of Maximum Cluster Mass'
            threshold_label = f'Threshold (α={alpha}): {threshold:.2f}'
        
        # Plot histogram of null distribution with seaborn
        sns.histplot(null_distribution, bins=200, alpha=0.7, color='gray', 
                    edgecolor='black', label='Null Distribution', ax=ax)
        
        # Plot threshold line
        ax.axvline(threshold, color='red', linestyle='--', linewidth=2, 
                   label=threshold_label)
        
        # Plot observed cluster statistics
        for i, cluster in enumerate(observed_clusters):
            stat_value = cluster['stat_value']
            is_significant = stat_value > threshold
            color = 'green' if is_significant else 'orange'
            label = 'Significant Cluster' if i == 0 and is_significant else None
            if i == 0 and not is_significant:
                label = 'Non-significant Cluster'
            
            ax.axvline(stat_value, color=color, linestyle='-', linewidth=1.5, 
                      alpha=0.8, label=label)
        
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='upper right', fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save as high-quality PDF
        plt.savefig(output_file, format='pdf', dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        print(f"Saved permutation null distribution plot: {output_file}")
        
    except Exception as e:
        print(f"Error creating permutation null distribution plot: {e}")
        raise
    finally:
        # Ensure figure is closed to free memory (critical in Docker)
        plt.close(fig)


def plot_cluster_size_mass_correlation(cluster_sizes, cluster_masses, output_file):
    """
    Plot correlation between cluster size and cluster mass from permutation null distribution
    
    Parameters:
    -----------
    cluster_sizes : ndarray
        Maximum cluster sizes from each permutation
    cluster_masses : ndarray
        Maximum cluster masses from each permutation
    output_file : str
        Path to save PDF file
    """
    from scipy.stats import pearsonr
    
    # Remove any zero values (permutations with no clusters)
    mask = (cluster_sizes > 0) & (cluster_masses > 0)
    sizes_nonzero = cluster_sizes[mask]
    masses_nonzero = cluster_masses[mask]
    
    if len(sizes_nonzero) < 2:
        print("Warning: Not enough non-zero clusters to compute correlation")
        return
    
    # Calculate Pearson correlation
    r_value, p_value = pearsonr(sizes_nonzero, masses_nonzero)
    
    # Explicitly create new figure (Docker-safe)
    fig, ax = plt.subplots(figsize=(10, 8))
    
    try:
        # Scatter plot with regression line using seaborn
        sns.regplot(x=sizes_nonzero, y=masses_nonzero, ax=ax,
                   scatter_kws={'alpha': 0.6, 's': 50, 'color': 'steelblue', 
                               'edgecolors': 'black', 'linewidths': 0.5},
                   line_kws={'color': 'red', 'linewidth': 2})
        
        # Calculate linear fit parameters for label
        z = np.polyfit(sizes_nonzero, masses_nonzero, 1)
        
        # Labels and title
        ax.set_xlabel('Maximum Cluster Size (voxels)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Maximum Cluster Mass (sum of t-statistics)', fontsize=12, fontweight='bold')
        ax.set_title(f'Cluster Size vs Cluster Mass Correlation\nPearson r = {r_value:.3f} (p = {p_value:.2e})', 
                    fontsize=14, fontweight='bold')
        
        # Add text box with statistics
        textstr = f'n = {len(sizes_nonzero)} permutations\nr = {r_value:.3f}\np = {p_value:.2e}\nLinear fit: y = {z[0]:.2f}x + {z[1]:.2f}'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=11,
               verticalalignment='top', bbox=props)
        
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save as high-quality PDF
        plt.savefig(output_file, format='pdf', dpi=300, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        print(f"Saved cluster size-mass correlation plot: {output_file}")
        print(f"Pearson correlation: r = {r_value:.3f}, p = {p_value:.2e}")
        
    except Exception as e:
        print(f"Error creating cluster size-mass correlation plot: {e}")
        raise
    finally:
        # Ensure figure is closed to free memory (critical in Docker)
        plt.close(fig)

