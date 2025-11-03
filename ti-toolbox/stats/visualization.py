"""
Visualization utilities for neuroimaging analysis

This module contains functions for:
- Plotting permutation null distributions
- Creating correlation plots
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for PDF generation

# Set white background explicitly for consistency across environments
matplotlib.rcParams['figure.facecolor'] = 'white'
matplotlib.rcParams['axes.facecolor'] = 'white'
matplotlib.rcParams['savefig.facecolor'] = 'white'


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
    plt.figure(figsize=(10, 6))
    
    # Plot histogram of null distribution with higher bin resolution
    # Use more bins for better resolution (200 instead of 50)
    plt.hist(null_distribution, bins=200, alpha=0.7, color='gray', 
             edgecolor='black', label='Null Distribution')
    
    # Set labels based on cluster statistic
    if cluster_stat == 'size':
        x_label = 'Maximum Cluster Size (voxels)'
        title = 'Permutation Null Distribution of Maximum Cluster Sizes'
        threshold_label = f'Threshold (α={alpha}): {threshold:.1f} voxels'
    else:  # cluster_stat == 'mass'
        x_label = 'Maximum Cluster Mass (sum of t-statistics)'
        title = 'Permutation Null Distribution of Maximum Cluster Mass'
        threshold_label = f'Threshold (α={alpha}): {threshold:.2f}'
    
    # Plot threshold line
    plt.axvline(threshold, color='red', linestyle='--', linewidth=2, 
                label=threshold_label)
    
    # Plot observed cluster statistics
    for i, cluster in enumerate(observed_clusters):
        stat_value = cluster['stat_value']
        is_significant = stat_value > threshold
        color = 'green' if is_significant else 'orange'
        label = 'Significant Cluster' if i == 0 and is_significant else None
        if i == 0 and not is_significant:
            label = 'Non-significant Cluster'
        
        plt.axvline(stat_value, color=color, linestyle='-', linewidth=1.5, 
                   alpha=0.8, label=label)
    
    plt.xlabel(x_label, fontsize=12)
    plt.ylabel('Frequency', fontsize=12)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.legend(loc='upper right', fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save as PDF
    plt.savefig(output_file, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved permutation null distribution plot: {output_file}")


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
    
    # Create figure
    plt.figure(figsize=(10, 8))
    
    # Scatter plot
    plt.scatter(sizes_nonzero, masses_nonzero, alpha=0.6, s=50, 
               color='steelblue', edgecolors='black', linewidth=0.5)
    
    # Linear regression line
    z = np.polyfit(sizes_nonzero, masses_nonzero, 1)
    p = np.poly1d(z)
    x_line = np.linspace(sizes_nonzero.min(), sizes_nonzero.max(), 100)
    plt.plot(x_line, p(x_line), 'r-', linewidth=2, label=f'Linear fit: y = {z[0]:.2f}x + {z[1]:.2f}')
    
    # Labels and title
    plt.xlabel('Maximum Cluster Size (voxels)', fontsize=12, fontweight='bold')
    plt.ylabel('Maximum Cluster Mass (sum of t-statistics)', fontsize=12, fontweight='bold')
    plt.title(f'Cluster Size vs Cluster Mass Correlation\nPearson r = {r_value:.3f} (p = {p_value:.2e})', 
             fontsize=14, fontweight='bold')
    
    # Add text box with statistics
    textstr = f'n = {len(sizes_nonzero)} permutations\nr = {r_value:.3f}\np = {p_value:.2e}'
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    plt.text(0.05, 0.95, textstr, transform=plt.gca().transAxes, fontsize=11,
            verticalalignment='top', bbox=props)
    
    plt.legend(loc='lower right', fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save as PDF
    plt.savefig(output_file, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved cluster size-mass correlation plot: {output_file}")
    print(f"Pearson correlation: r = {r_value:.3f}, p = {p_value:.2e}")

