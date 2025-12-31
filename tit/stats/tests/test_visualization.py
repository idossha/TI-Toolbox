#!/usr/bin/env python3
"""
Simple test script for visualization functions
"""

import numpy as np
import os

from tit.stats.visualization import (
    plot_permutation_null_distribution,
    plot_cluster_size_mass_correlation
)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def test_plot_permutation_null_distribution():
    """Test the permutation null distribution plotting function"""
    print("=" * 70)
    print("TEST 1: plot_permutation_null_distribution")
    print("=" * 70)
    
    # Generate synthetic null distribution
    np.random.seed(42)
    null_distribution = np.random.gamma(shape=5.0, scale=10.0, size=1000)
    
    # Calculate threshold (95th percentile)
    alpha = 0.05
    threshold = np.percentile(null_distribution, (1 - alpha) * 100)
    
    # Create observed clusters
    observed_clusters = [
        {'stat_value': threshold * 1.5, 'size': int(threshold * 1.5)},  # Significant
        {'stat_value': threshold * 0.8, 'size': int(threshold * 0.8)},  # Non-significant
        {'stat_value': threshold * 2.0, 'size': int(threshold * 2.0)},  # Significant
    ]
    
    print(f"\nNull distribution: n={len(null_distribution)}, mean={null_distribution.mean():.2f}, std={null_distribution.std():.2f}")
    print(f"Threshold (α={alpha}): {threshold:.2f}")
    print(f"Observed clusters:")
    for i, cluster in enumerate(observed_clusters):
        sig_status = "SIGNIFICANT" if cluster['stat_value'] > threshold else "non-significant"
        print(f"  Cluster {i+1}: stat_value={cluster['stat_value']:.2f} ({sig_status})")
    
    # Test with cluster size
    output_file_size = os.path.join(SCRIPT_DIR, 'test_null_distribution_size.pdf')
    plot_permutation_null_distribution(
        null_distribution=null_distribution,
        threshold=threshold,
        observed_clusters=observed_clusters,
        output_file=output_file_size,
        alpha=alpha,
        cluster_stat='size'
    )
    
    # Test with cluster mass
    output_file_mass = os.path.join(SCRIPT_DIR, 'test_null_distribution_mass.pdf')
    plot_permutation_null_distribution(
        null_distribution=null_distribution,
        threshold=threshold,
        observed_clusters=observed_clusters,
        output_file=output_file_mass,
        alpha=alpha,
        cluster_stat='mass'
    )
    
    print("✓ Test completed successfully!\n")


def test_plot_cluster_size_mass_correlation():
    """Test the cluster size-mass correlation plotting function"""
    print("=" * 70)
    print("TEST 2: plot_cluster_size_mass_correlation")
    print("=" * 70)
    
    # Generate synthetic correlated data
    np.random.seed(42)
    n_permutations = 500
    
    # Create correlated cluster sizes and masses
    cluster_sizes = np.random.gamma(shape=5.0, scale=10.0, size=n_permutations)
    noise = np.random.normal(0, 5, size=n_permutations)
    cluster_masses = 2.5 * cluster_sizes + 20 + noise
    
    # Add some zero values (permutations with no clusters)
    zero_indices = np.random.choice(n_permutations, size=50, replace=False)
    cluster_sizes[zero_indices] = 0
    cluster_masses[zero_indices] = 0
    
    print(f"\nTotal permutations: {n_permutations}")
    print(f"Permutations with clusters: {(cluster_sizes > 0).sum()}")
    print(f"Cluster sizes: mean={cluster_sizes[cluster_sizes > 0].mean():.2f}, std={cluster_sizes[cluster_sizes > 0].std():.2f}")
    print(f"Cluster masses: mean={cluster_masses[cluster_masses > 0].mean():.2f}, std={cluster_masses[cluster_masses > 0].std():.2f}")
    
    output_file = os.path.join(SCRIPT_DIR, 'test_cluster_correlation.pdf')
    plot_cluster_size_mass_correlation(
        cluster_sizes=cluster_sizes,
        cluster_masses=cluster_masses,
        output_file=output_file
    )
    
    print("✓ Test completed successfully!\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("TESTING VISUALIZATION FUNCTIONS")
    print("=" * 70 + "\n")
    
    test_plot_permutation_null_distribution()
    test_plot_cluster_size_mass_correlation()
    
    print("=" * 70)
    print("ALL TESTS COMPLETED!")
    print("=" * 70)
    print(f"\nOutput files saved in: {SCRIPT_DIR}/")
    print("  - test_null_distribution_size.pdf")
    print("  - test_null_distribution_mass.pdf")
    print("  - test_cluster_correlation.pdf")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
