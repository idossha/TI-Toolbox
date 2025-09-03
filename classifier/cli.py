#!/usr/bin/env python3
"""
TI-Toolbox Classifier v2.0 - Production CLI

Clean, modular command-line interface for the TI field classifier.
"""

import sys
import argparse
from pathlib import Path

# Import the production classifier
from ti_classifier import TIClassifier


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
  
  Use pre-computed MNI files (skip FSL normalization):
    %(prog)s train --project-dir /path/to/project --response-file responses.csv \\
      --no-fsl-normalize
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
                            help='Use FSL ROI-averaged features (recommended for <50 subjects)')
    train_parser.add_argument('--atlas', default='HarvardOxford-cort-maxprob-thr0-1mm',
                            choices=['HarvardOxford-cort-maxprob-thr0-1mm', 'MNI_Glasser_HCP_v1.0'],
                            help='Brain atlas for analysis (default: Harvard-Oxford)')
    
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
    atlas_display = "Harvard-Oxford (48 ROIs)" if "HarvardOxford" in args.atlas else "Glasser HCP (360 ROIs)"
    print(f"• Feature type: {'FSL ROI-averaged (1mm)' if args.roi_features else 'Voxel-wise'}")
    print(f"• Atlas: {atlas_display}")
    print(f"• Files: Pre-computed MNI from SimNIBS")
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
            use_roi_features=args.roi_features,
            atlas_name=args.atlas
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
        print("  • niftis/ - Reference files")
        print("    ├── MNI152_T1_1mm_template.nii.gz - MNI template")
        print("    ├── HarvardOxford-cort-maxprob-thr0-1mm.nii.gz - Harvard-Oxford atlas")
        print("    └── HarvardOxford-cort-maxprob-thr0-1mm.txt - Atlas labels")
        
        if args.roi_features:
            print("  • roi_features/ - FSL ROI-averaged files (cached for reuse)")
            print("    ├── HarvardOxford-cort-maxprob-thr0-1mm/")
            print("    │   └── sub-*_ROI_averaged_intensities.nii.gz")
            print("    └── MNI_Glasser_HCP_v1.0/")
            print("        └── sub-*_ROI_averaged_intensities.nii.gz")
            print("  • group_averages/ - Group-averaged ROI maps")
            print("    ├── responders_ROI_averaged_{atlas}_MNI.nii.gz")
            print("    ├── nonresponders_ROI_averaged_{atlas}_MNI.nii.gz")
            print("    └── difference_responders_vs_nonresponders_ROI_averaged_{atlas}_MNI.nii.gz")
            print("  • roi_importance.csv - ROI rankings by SVM importance")
        
        print("  • QA/ - Quality assurance reports")
        print("    ├── QA.log - File inventory")
        print("    ├── atlas_info.txt - Atlas details")
        print("    ├── overlap_metrics.csv - Alignment analysis")
        print("    ├── overlap_summary.txt - Summary interpretation")
        print("    ├── overlay_before_resampling.png - Original resolution overlay")
        if args.resolution > 1:
            print("    ├── overlay_after_resampling.png - Downsampled resolution overlay")
            print("    └── before_after_resampling_comparison.png - Side-by-side comparison")
        else:
            print("    └── (no after-resampling overlay - native resolution used)")
        
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
