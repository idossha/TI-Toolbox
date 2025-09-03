#!/usr/bin/env python3
"""
Example script demonstrating the TI-Toolbox Classifier plotting functionality

This script shows how to use the plotting features based on Albizu et al. (2020)
methodology for visualizing classifier results.
"""

import numpy as np
import sys
from pathlib import Path

# Add the classifier directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from core.plotting import TIClassifierPlotter

def create_example_data():
    """Create synthetic example data for demonstration"""
    np.random.seed(42)
    
    # Simulate classifier results
    results = {
        'cv_accuracy': 86.4,
        'cv_std': 5.2,
        'roc_auc': 0.806,
        'confidence_interval': (81.2, 91.6),
        'method': 'Nested Cross-Validation (Example)',
        'fold_results': [
            {'fold': 1, 'accuracy': 0.857, 'auc': 0.823},
            {'fold': 2, 'accuracy': 0.900, 'auc': 0.850},
            {'fold': 3, 'accuracy': 0.833, 'auc': 0.780},
            {'fold': 4, 'accuracy': 0.875, 'auc': 0.810},
            {'fold': 5, 'accuracy': 0.889, 'auc': 0.825},
            {'fold': 6, 'accuracy': 0.846, 'auc': 0.795}
        ],
        'weights': np.random.randn(1000) * 0.1,  # Synthetic SVM weights
        'roi_importance': [
            {'roi_id': 1, 'roi_name': 'Left Superior Frontal Gyrus', 'weight': 0.245, 'abs_weight': 0.245},
            {'roi_id': 2, 'roi_name': 'Right Superior Frontal Gyrus', 'weight': 0.198, 'abs_weight': 0.198},
            {'roi_id': 3, 'roi_name': 'Right Middle Frontal Gyrus', 'weight': 0.176, 'abs_weight': 0.176},
            {'roi_id': 4, 'roi_name': 'Left Putamen', 'weight': -0.165, 'abs_weight': 0.165},
            {'roi_id': 5, 'roi_name': 'Right Frontal Pole', 'weight': 0.142, 'abs_weight': 0.142},
            {'roi_id': 6, 'roi_name': 'Right Precentral Gyrus', 'weight': 0.138, 'abs_weight': 0.138},
            {'roi_id': 7, 'roi_name': 'Left Frontal Pole', 'weight': 0.125, 'abs_weight': 0.125},
            {'roi_id': 8, 'roi_name': 'Right Pars Opercularis', 'weight': -0.118, 'abs_weight': 0.118},
            {'roi_id': 9, 'roi_name': 'Left Caudate', 'weight': 0.112, 'abs_weight': 0.112},
            {'roi_id': 10, 'roi_name': 'Right Supramarginal Gyrus', 'weight': 0.105, 'abs_weight': 0.105}
        ]
    }
    
    # Simulate training data
    n_responders = 7
    n_nonresponders = 7
    n_voxels = 1000
    
    # Responders have slightly higher current intensities
    resp_data = np.random.exponential(0.02, (n_responders, n_voxels)) + np.random.normal(0, 0.005, (n_responders, n_voxels))
    resp_data = np.maximum(resp_data, 0)  # Ensure non-negative
    
    # Non-responders have lower current intensities
    nonresp_data = np.random.exponential(0.015, (n_nonresponders, n_voxels)) + np.random.normal(0, 0.003, (n_nonresponders, n_voxels))
    nonresp_data = np.maximum(nonresp_data, 0)  # Ensure non-negative
    
    training_data = {
        'resp_data': resp_data,
        'nonresp_data': nonresp_data,
        'resolution_mm': 1,
        'use_roi_features': False
    }
    
    return results, training_data

def main():
    """Main demonstration function"""
    print("TI-Toolbox Classifier Plotting Demonstration")
    print("=" * 50)
    
    # Create output directory
    output_dir = Path("example_plots_output")
    output_dir.mkdir(exist_ok=True)
    
    # Initialize plotter
    plotter = TIClassifierPlotter(str(output_dir))
    
    # Generate example data
    print("Generating example data...")
    results, training_data = create_example_data()
    
    # Create all plots
    print("Creating visualization plots...")
    plotter.create_all_plots(results, training_data)
    
    # Create summary report
    print("Generating summary report...")
    plotter.create_summary_report(results, training_data)
    
    print("\n" + "=" * 50)
    print("DEMONSTRATION COMPLETE")
    print("=" * 50)
    print(f"Output directory: {output_dir.absolute()}")
    print("\nGenerated files:")
    print("• performance_metrics.png/pdf - ROC curves, accuracy, confusion matrix")
    print("• weight_interpretation.png/pdf - Current intensity analysis")
    print("• roi_ranking.png/pdf - Brain region importance ranking")
    print("• dosing_analysis.png/pdf - Group comparisons and PCA clustering")
    print("• classification_report.txt - Comprehensive analysis summary")
    print("\nThese plots demonstrate the visualization capabilities")
    print("based on Albizu et al. (2020) methodology.")
    print("=" * 50)

if __name__ == "__main__":
    main()
