#!/usr/bin/env python3
"""
TI-Toolbox Classifier v2.0 - Production CLI

Clean, modular command-line interface for the TI field classifier.
"""

import sys
import argparse
from pathlib import Path

# Import the new modular classifier
from classifier_v2 import TIClassifier


def main():
    """Production-ready CLI for TI classifier."""
    parser = argparse.ArgumentParser(
        description='TI-Toolbox Classifier v2.0 - Production Ready',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic training:
    %(prog)s train --project-dir /path/to/project --response-file responses.csv
  
  ROI-based training (recommended for small samples):
    %(prog)s train --project-dir /path/to/project --response-file responses.csv --roi-features
  
  High-resolution analysis:
    %(prog)s train --project-dir /path/to/project --response-file responses.csv \\
      --resolution 1 --p-threshold 0.001
  
  Fast analysis with downsampling:
    %(prog)s train --project-dir /path/to/project --response-file responses.csv \\
      --resolution 4 --roi-features
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Train command
    train_parser = subparsers.add_parser('train', help='Train classifier')
    train_parser.add_argument('--project-dir', required=True,
                            help='Path to TI-Toolbox project directory')
    train_parser.add_argument('--response-file', required=True,
                            help='Path to CSV file with response data')
    train_parser.add_argument('--output-dir',
                            help='Output directory (default: project/derivatives/ti-toolbox/classifier/results)')
    
    # Analysis settings
    train_parser.add_argument('--resolution', type=int, default=1, choices=[1, 2, 3, 4],
                            help='Resolution in mm (1=original, 2-4=downsampled, default: 1)')
    train_parser.add_argument('--p-threshold', type=float, default=0.01,
                            help='P-value threshold for voxel-wise feature selection (default: 0.01)')
    train_parser.add_argument('--cores', type=int, default=-1,
                            help='Number of CPU cores (-1=all, default: -1)')
    train_parser.add_argument('--roi-features', action='store_true',
                            help='Use ROI-averaged features instead of voxel-wise (recommended for <50 subjects)')
    
    # Quality assurance command
    qa_parser = subparsers.add_parser('qa', help='Generate QA report only')
    qa_parser.add_argument('--project-dir', required=True,
                         help='Path to TI-Toolbox project directory')
    qa_parser.add_argument('--response-file', required=True,
                         help='Path to CSV file with response data')
    qa_parser.add_argument('--resolution', type=int, default=1, choices=[1, 2, 3, 4],
                         help='Resolution in mm for QA analysis')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == 'train':
        return train_command(args)
    elif args.command == 'qa':
        return qa_command(args)
    
    return 0


def train_command(args):
    """Handle training command."""
    print("="*80)
    print("TI-TOOLBOX CLASSIFIER v2.0 - PRODUCTION READY")
    print("="*80)
    
    # Display settings
    print(f"\nSettings:")
    print(f"• Project: {args.project_dir}")
    print(f"• Response file: {Path(args.response_file).name}")
    print(f"• Resolution: {args.resolution}mm")
    print(f"• Feature type: {'ROI-averaged' if args.roi_features else 'Voxel-wise'}")
    if not args.roi_features:
        print(f"• P-value threshold: {args.p_threshold}")
    print(f"• CPU cores: {args.cores}")
    
    try:
        # Initialize classifier
        classifier = TIClassifier(
            project_dir=args.project_dir,
            output_dir=args.output_dir,
            resolution_mm=args.resolution,
            p_value_threshold=args.p_threshold,
            n_jobs=args.cores,
            use_roi_features=args.roi_features
        )
        
        # Train
        results = classifier.train(args.response_file)
        
        # Display results
        print("\n" + "="*80)
        print("TRAINING COMPLETED SUCCESSFULLY")
        print("="*80)
        print(f"Method: {results['method']}")
        print(f"Accuracy: {results['cv_accuracy']:.1f}% ± {results['cv_std']:.1f}%")
        
        if 'confidence_interval' in results:
            ci = results['confidence_interval']
            print(f"95% CI: [{ci[0]:.1f}%, {ci[1]:.1f}%]")
        
        print(f"ROC-AUC: {results['roc_auc']:.3f}")
        
        if args.roi_features and 'n_roi_features' in results:
            print(f"Features: {results['n_roi_features']} ROIs")
        
        print(f"\n✓ Results saved to: {classifier.output_dir}")
        print("\nGenerated files:")
        print("  • ti_classifier_model.pkl - Trained model")
        print("  • performance_metrics.csv - Performance summary")
        print("  • results_summary.json - Results summary")
        print("  • QA/ - Quality assurance reports")
        print("    ├── QA.log - File inventory")
        print("    ├── atlas_info.txt - Atlas details")
        print("    ├── overlap_metrics.csv - Alignment analysis")
        print("    └── overlap_summary.txt - Summary interpretation")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Training failed: {e}")
        return 1


def qa_command(args):
    """Handle QA-only command."""
    print("="*80)
    print("TI-TOOLBOX CLASSIFIER - QA REPORT ONLY")
    print("="*80)
    
    try:
        # Initialize classifier for QA only
        classifier = TIClassifier(
            project_dir=args.project_dir,
            resolution_mm=args.resolution,
            use_roi_features=False  # QA works for both modes
        )
        
        # Load data
        responder_paths, nonresponder_paths, metadata = classifier.data_loader.load_response_data(args.response_file)
        
        # Load and process one subject for QA
        template_img = nib.load(str(responder_paths[0]))
        if args.resolution > 1:
            template_img = classifier._downsample_nifti(template_img, args.resolution)
        
        template_shape = template_img.shape
        
        # Resample atlas
        classifier.atlas_manager.resample_atlas_to_match(template_shape, template_img.affine)
        
        # Generate QA report
        classifier.qa_reporter.create_comprehensive_report(
            responder_paths, nonresponder_paths, template_shape, args.resolution
        )
        
        print(f"\n✓ QA report generated: {classifier.qa_dir}")
        return 0
        
    except Exception as e:
        print(f"\n❌ QA generation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
