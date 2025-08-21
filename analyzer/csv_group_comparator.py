#!/usr/bin/env python3

"""
CSV Group Comparator Script

This script compares multiple CSV files containing analysis results.
It can:
1. Compare the same subjects across different CSV files
2. Generate descriptive statistics for each CSV file
3. Compare group statistics between different CSV files

Expected CSV structure:
- Subject_ID: Subject identifier
- Montage: Montage type
- Analysis: Analysis type
- ROI_Mean, ROI_Max, ROI_Min, ROI_Focality: ROI metrics
- Grey_Mean, Grey_Max, Grey_Min: Grey matter metrics
- Normal_Mean, Normal_Max, Normal_Min, Normal_Focality: Normal metrics
"""


"""
python3 csv_group_comparator.py /Volumes/Ido/000_strength/derivatives/SimNIBS/group_analysis/cortical_maxTI/DK40_24_ernie_lh.precentral/enhanced_roi_comparison_summary_lh.precentral.csv /Volumes/Ido/000_strength/derivatives/SimNIBS/group_analysis/cortical_maxTI/flex_lh_DK40_24_mean_maxTI_..._lh.precentral/enhanced_roi_comparison_summary_lh.precentral.csv -o /Users/idohaber/Desktop/GA
"""

import os
import sys
import argparse
try:
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
except ImportError as e:
    print(f"Required packages not installed: {e}")
    print("Please install required packages with: pip install pandas numpy matplotlib seaborn")
    sys.exit(1)
from pathlib import Path
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util

def extract_subject_label(subject_id: str) -> str:
    """
    Extract meaningful subject label from subject ID.
    
    Args:
        subject_id: Full subject ID (e.g., 'sub-101', 'sub-ernie')
        
    Returns:
        Meaningful label (e.g., '101', 'ernie')
    """
    if subject_id.startswith('sub-'):
        return subject_id[4:]  # Remove 'sub-' prefix
    return subject_id

def setup_logger(output_dir: str) -> logging.Logger:
    """Set up logging for the CSV comparison."""
    log_dir = os.path.join(output_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"csv_comparison_{timestamp}.log")
    
    return logging_util.get_logger("csv_comparator", log_file, overwrite=False)

def load_csv_files(csv_paths: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Load CSV files and return a dictionary with subdirectory name as key and DataFrame as value.
    
    Args:
        csv_paths: List of paths to CSV files
        
    Returns:
        Dictionary mapping subdirectory names to DataFrames
    """
    csv_data = {}
    
    for csv_path in csv_paths:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
            
        # Use subdirectory name as the group name
        group_name = Path(csv_path).parent.name
        
        try:
            df = pd.read_csv(csv_path)
            csv_data[group_name] = df
            print(f"Loaded {group_name}: {len(df)} rows, {len(df.columns)} columns")
        except Exception as e:
            raise ValueError(f"Error loading {csv_path}: {str(e)}")
    
    return csv_data

def identify_common_subjects(csv_data: Dict[str, pd.DataFrame]) -> List[str]:
    """
    Identify subjects that appear in all CSV files.
    
    Args:
        csv_data: Dictionary of DataFrames
        
    Returns:
        List of common subject IDs
    """
    if not csv_data:
        return []
    
    # Get subject IDs from each DataFrame
    subject_sets = []
    for file_name, df in csv_data.items():
        if 'Subject_ID' in df.columns:
            subjects = set(df['Subject_ID'].unique())
            subject_sets.append(subjects)
            print(f"{file_name}: {len(subjects)} unique subjects")
        else:
            print(f"Warning: 'Subject_ID' column not found in {file_name}")
            return []
    
    # Find intersection of all subject sets
    common_subjects = set.intersection(*subject_sets) if subject_sets else set()
    print(f"Common subjects across all files: {len(common_subjects)}")
    
    return sorted(list(common_subjects))

def compare_subject_metrics(csv_data: Dict[str, pd.DataFrame], 
                          common_subjects: List[str], 
                          output_dir: str, 
                          logger: logging.Logger) -> pd.DataFrame:
    """
    Compare metrics for subjects that appear in ALL CSV files.
    Only includes subjects that have data in every CSV file.
    
    Args:
        csv_data: Dictionary of DataFrames
        common_subjects: List of common subject IDs
        output_dir: Output directory for results
        logger: Logger instance
        
    Returns:
        DataFrame with comparison results
    """
    if len(common_subjects) == 0:
        logger.warning("No common subjects found for comparison")
        return pd.DataFrame()
    
    # Define numeric columns to compare
    numeric_columns = [
        'ROI_Mean', 'ROI_Max', 'ROI_Min', 'ROI_Focality',
        'Grey_Mean', 'Grey_Max', 'Grey_Min',
        'Normal_Mean', 'Normal_Max', 'Normal_Min', 'Normal_Focality'
    ]
    
    comparison_results = []
    
    for subject_id in common_subjects:
        subject_data = {}
        
        # Extract data for this subject from each CSV
        # Only proceed if subject exists in ALL CSV files
        subject_found_in_all = True
        for file_name, df in csv_data.items():
            subject_rows = df[df['Subject_ID'] == subject_id]
            
            if len(subject_rows) > 0:
                # If multiple rows for same subject, take the first one
                subject_row = subject_rows.iloc[0]
                
                # Store relevant columns
                subject_data[file_name] = {
                    'Montage': subject_row.get('Montage', 'N/A'),
                    'Analysis': subject_row.get('Analysis', 'N/A')
                }
                
                # Add numeric metrics
                for col in numeric_columns:
                    if col in subject_row:
                        subject_data[file_name][col] = subject_row[col]
            else:
                subject_found_in_all = False
                break
        
        # Only create comparison if subject appears in ALL files
        if subject_found_in_all and len(subject_data) == len(csv_data):
            comparison_row = {'Subject_ID': subject_id}
            
            # Add metrics from each file
            for file_name, data in subject_data.items():
                for metric, value in data.items():
                    comparison_row[f"{file_name}_{metric}"] = value
            
            # Calculate differences for numeric metrics
            file_names = list(subject_data.keys())
            for col in numeric_columns:
                values = []
                for file_name in file_names:
                    if col in subject_data[file_name]:
                        values.append(subject_data[file_name][col])
                
                if len(values) == len(file_names):  # Only if all files have this metric
                    comparison_row[f"{col}_diff"] = float(max(values) - min(values))
                    comparison_row[f"{col}_mean"] = float(np.mean(values))
                    comparison_row[f"{col}_std"] = float(np.std(values))
            
            comparison_results.append(comparison_row)
    
    if comparison_results:
        comparison_df = pd.DataFrame(comparison_results)
        
        # Save comparison results
        comparison_file = os.path.join(output_dir, "subject_comparisons.csv")
        comparison_df.to_csv(comparison_file, index=False)
        logger.info(f"Subject comparison results saved to: {comparison_file}")
        logger.debug(f"Compared {len(comparison_results)} subjects that appear in all CSV files")
        
        return comparison_df
    else:
        logger.warning("No subjects found in all CSV files")
        return pd.DataFrame()

def generate_group_statistics(csv_data: Dict[str, pd.DataFrame], 
                            output_dir: str, 
                            logger: logging.Logger) -> Dict[str, pd.DataFrame]:
    """
    Generate descriptive statistics for each CSV file.
    
    Args:
        csv_data: Dictionary of DataFrames
        output_dir: Output directory for results
        logger: Logger instance
        
    Returns:
        Dictionary mapping file names to statistics DataFrames
    """
    numeric_columns = [
        'ROI_Mean', 'ROI_Max', 'ROI_Min', 'ROI_Focality',
        'Grey_Mean', 'Grey_Max', 'Grey_Min',
        'Normal_Mean', 'Normal_Max', 'Normal_Min', 'Normal_Focality'
    ]
    
    group_stats = {}
    
    for file_name, df in csv_data.items():
        # Select only numeric columns that exist in the DataFrame
        available_numeric_cols = [col for col in numeric_columns if col in df.columns]
        
        if available_numeric_cols:
            # Calculate descriptive statistics
            stats_df = df[available_numeric_cols].describe()
            
            # Add additional statistics
            stats_df.loc['median'] = df[available_numeric_cols].median()
            stats_df.loc['variance'] = df[available_numeric_cols].var()
            stats_df.loc['skewness'] = df[available_numeric_cols].skew()
            stats_df.loc['kurtosis'] = df[available_numeric_cols].kurtosis()
            
            group_stats[file_name] = stats_df
            
            # Save individual statistics
            stats_file = os.path.join(output_dir, f"{file_name}_statistics.csv")
            stats_df.to_csv(stats_file)
            logger.debug(f"Statistics for {file_name} saved to: {stats_file}")
        else:
            logger.warning(f"No numeric columns found in {file_name}")
    
    return group_stats

def compare_group_statistics(group_stats: Dict[str, pd.DataFrame], 
                           output_dir: str, 
                           logger: logging.Logger) -> pd.DataFrame:
    """
    Compare group statistics between different CSV files.
    
    Args:
        group_stats: Dictionary of statistics DataFrames
        output_dir: Output directory for results
        logger: Logger instance
        
    Returns:
        DataFrame with group comparison results
    """
    if len(group_stats) < 2:
        logger.warning("Need at least 2 files to compare group statistics")
        return pd.DataFrame()
    
    file_names = list(group_stats.keys())
    comparison_results = []
    
    # Get all available metrics
    all_metrics = set()
    for stats_df in group_stats.values():
        all_metrics.update(stats_df.columns)
    
    for metric in all_metrics:
        metric_comparison = {'Metric': metric}
        
        # Add mean values for each file
        for file_name in file_names:
            if metric in group_stats[file_name].columns:
                metric_comparison[f"{file_name}_mean"] = group_stats[file_name].loc['mean', metric]
                metric_comparison[f"{file_name}_std"] = group_stats[file_name].loc['std', metric]
                metric_comparison[f"{file_name}_median"] = group_stats[file_name].loc['median', metric]
        
        # Calculate differences between files (if exactly 2 files)
        if len(file_names) == 2:
            file1, file2 = file_names
            if (metric in group_stats[file1].columns and 
                metric in group_stats[file2].columns):
                mean_diff = (group_stats[file1].loc['mean', metric] - 
                           group_stats[file2].loc['mean', metric])
                metric_comparison['mean_difference'] = mean_diff
                
                # Calculate effect size (Cohen's d)
                pooled_std = np.sqrt((group_stats[file1].loc['std', metric]**2 + 
                                    group_stats[file2].loc['std', metric]**2) / 2)
                if pooled_std != 0:
                    metric_comparison['cohens_d'] = mean_diff / pooled_std
        
        comparison_results.append(metric_comparison)
    
    if comparison_results:
        comparison_df = pd.DataFrame(comparison_results)
        
        # Save group comparison results
        comparison_file = os.path.join(output_dir, "group_statistics_comparison.csv")
        comparison_df.to_csv(comparison_file, index=False)
        logger.info(f"Group statistics comparison saved to: {comparison_file}")
        
        return comparison_df
    else:
        return pd.DataFrame()

def create_visualization_plots(csv_data: Dict[str, pd.DataFrame], 
                             comparison_df: pd.DataFrame,
                             group_stats: Dict[str, pd.DataFrame],
                             output_dir: str, 
                             logger: logging.Logger):
    """
    Create visualization plots for the comparisons.
    
    Args:
        csv_data: Dictionary of DataFrames
        comparison_df: Subject comparison results
        group_stats: Group statistics
        output_dir: Output directory for plots
        logger: Logger instance
    """
    # Set up plotting style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create plots directory
    plots_dir = os.path.join(output_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    
    file_names = list(csv_data.keys())
    
    # Plot 1: Subject-by-subject comparison for specific metrics
    if not comparison_df.empty and len(file_names) == 2:
        target_metrics = ['ROI_Mean', 'ROI_Focality', 'Normal_Mean']
        
        for metric in target_metrics:
            # Check if we have data for this metric from both files
            col1 = f"{file_names[0]}_{metric}"
            col2 = f"{file_names[1]}_{metric}"
            
            if col1 in comparison_df.columns and col2 in comparison_df.columns:
                fig, ax = plt.subplots(figsize=(12, 8))
                
                # Get subjects that have data for both conditions
                valid_mask = comparison_df[col1].notna() & comparison_df[col2].notna()
                valid_data = comparison_df[valid_mask].copy()
                
                if len(valid_data) == 0:
                    logger.warning(f"No subjects with valid data for both conditions in {metric}")
                    plt.close()
                    continue
                
                # Get data for both conditions (same subjects, matched by Subject_ID)
                data1 = valid_data[col1].values
                data2 = valid_data[col2].values
                subject_ids = valid_data['Subject_ID'].values
                subject_labels = [extract_subject_label(sid) for sid in subject_ids]
                
                # Create scatter plot with lines connecting same subjects
                x_pos = range(len(data1))
                
                # Plot points for each condition
                ax.scatter([x - 0.1 for x in x_pos], data1, 
                          color='blue', alpha=0.7, s=60, label=file_names[0])
                ax.scatter([x + 0.1 for x in x_pos], data2, 
                          color='red', alpha=0.7, s=60, label=file_names[1])
                
                # Connect points for same subjects
                for i, (val1, val2) in enumerate(zip(data1, data2)):
                    ax.plot([i - 0.1, i + 0.1], [val1, val2], 
                           color='gray', alpha=0.5, linewidth=1)
                
                # Customize plot
                ax.set_xlabel('Subjects')
                ax.set_ylabel(f'{metric} Value')
                ax.set_title(f'{metric}: Subject-by-Subject Comparison')
                ax.set_xticks(x_pos)
                ax.set_xticklabels(subject_labels, rotation=45, ha='right')
                ax.legend()
                ax.grid(True, alpha=0.3)
                
                plt.tight_layout()
                plot_file = os.path.join(plots_dir, f"subject_comparison_{metric}.png")
                plt.savefig(plot_file, dpi=300, bbox_inches='tight')
                plt.close()
                logger.debug(f"Subject comparison plot for {metric} saved to: {plot_file} ({len(valid_data)} subjects)")
    
    # Plot 2: Group means comparison for the three target metrics
    if group_stats and len(file_names) == 2:
        target_metrics = ['ROI_Mean', 'ROI_Focality', 'Normal_Mean']
        
        # Check which metrics are available
        available_metrics = []
        for metric in target_metrics:
            if all(metric in stats_df.columns for stats_df in group_stats.values()):
                available_metrics.append(metric)
        
        if available_metrics:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Prepare data
            x_pos = np.arange(len(available_metrics))
            width = 0.35
            
            means1 = []
            means2 = []
            stds1 = []
            stds2 = []
            
            for metric in available_metrics:
                means1.append(group_stats[file_names[0]].loc['mean', metric])
                means2.append(group_stats[file_names[1]].loc['mean', metric])
                stds1.append(group_stats[file_names[0]].loc['std', metric])
                stds2.append(group_stats[file_names[1]].loc['std', metric])
            
            # Create bar plots
            bars1 = ax.bar(x_pos - width/2, means1, width, yerr=stds1, 
                          label=file_names[0], alpha=0.8, capsize=5)
            bars2 = ax.bar(x_pos + width/2, means2, width, yerr=stds2, 
                          label=file_names[1], alpha=0.8, capsize=5)
            
            # Customize plot
            ax.set_xlabel('Metrics')
            ax.set_ylabel('Mean Value')
            ax.set_title('Group Mean Comparison: Key Metrics')
            ax.set_xticks(x_pos)
            ax.set_xticklabels(available_metrics)
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')
            
            # Add value labels on bars
            for bars in [bars1, bars2]:
                for bar in bars:
                    height = bar.get_height()
                    ax.annotate(f'{height:.3f}',
                               xy=(bar.get_x() + bar.get_width() / 2, height),
                               xytext=(0, 3),  # 3 points vertical offset
                               textcoords="offset points",
                               ha='center', va='bottom',
                               fontsize=8)
            
            plt.tight_layout()
            plot_file = os.path.join(plots_dir, "group_means_key_metrics.png")
            plt.savefig(plot_file, dpi=300, bbox_inches='tight')
            plt.close()
            logger.debug(f"Group means comparison plot saved to: {plot_file}")
    
    # Plot 3: Combined overview plot (optional - shows both subject and group level)
    if not comparison_df.empty and group_stats and len(file_names) == 2:
        target_metrics = ['ROI_Mean', 'ROI_Focality', 'Normal_Mean']
        available_metrics = []
        
        for metric in target_metrics:
            col1 = f"{file_names[0]}_{metric}"
            col2 = f"{file_names[1]}_{metric}"
            if (col1 in comparison_df.columns and col2 in comparison_df.columns and
                all(metric in stats_df.columns for stats_df in group_stats.values())):
                available_metrics.append(metric)
        
        if available_metrics:
            fig, axes = plt.subplots(1, len(available_metrics), figsize=(5*len(available_metrics), 6))
            if len(available_metrics) == 1:
                axes = [axes]
            
            for i, metric in enumerate(available_metrics):
                ax = axes[i]
                
                # Get subject-level data - only subjects with data in both conditions
                col1 = f"{file_names[0]}_{metric}"
                col2 = f"{file_names[1]}_{metric}"
                valid_mask = comparison_df[col1].notna() & comparison_df[col2].notna()
                valid_data = comparison_df[valid_mask].copy()
                
                if len(valid_data) == 0:
                    ax.text(0.5, 0.5, f'No valid data\nfor {metric}', 
                           ha='center', va='center', transform=ax.transAxes)
                    ax.set_title(f'{metric}')
                    continue
                
                data1 = valid_data[col1].values
                data2 = valid_data[col2].values
                
                # Individual subject points
                ax.scatter([1]*len(data1), data1, alpha=0.6, color='lightblue', s=40)
                ax.scatter([2]*len(data2), data2, alpha=0.6, color='lightcoral', s=40)
                
                # Connect same subjects (now properly matched)
                for val1, val2 in zip(data1, data2):
                    ax.plot([1, 2], [val1, val2], color='gray', alpha=0.3, linewidth=0.5)
                
                # Group means as larger points
                mean1 = group_stats[file_names[0]].loc['mean', metric]
                mean2 = group_stats[file_names[1]].loc['mean', metric]
                std1 = group_stats[file_names[0]].loc['std', metric]
                std2 = group_stats[file_names[1]].loc['std', metric]
                
                ax.errorbar([1], [mean1], yerr=[std1], fmt='o', color='blue', 
                           markersize=8, capsize=5, linewidth=2, label='Group Mean ± SD')
                ax.errorbar([2], [mean2], yerr=[std2], fmt='o', color='red', 
                           markersize=8, capsize=5, linewidth=2)
                
                ax.set_xlim(0.5, 2.5)
                ax.set_xticks([1, 2])
                ax.set_xticklabels([file_names[0][:15] + '...' if len(file_names[0]) > 15 else file_names[0],
                                   file_names[1][:15] + '...' if len(file_names[1]) > 15 else file_names[1]], 
                                  rotation=45, ha='right')
                ax.set_ylabel(f'{metric} Value')
                ax.set_title(f'{metric}')
                ax.grid(True, alpha=0.3)
                
                if i == 0:
                    ax.legend()
            
            plt.suptitle('Subject-Level and Group-Level Comparison', fontsize=14)
            plt.tight_layout()
            plot_file = os.path.join(plots_dir, "combined_overview.png")
            plt.savefig(plot_file, dpi=300, bbox_inches='tight')
            plt.close()
            logger.debug(f"Combined overview plot saved to: {plot_file}")

def generate_summary_report(csv_data: Dict[str, pd.DataFrame], 
                          comparison_df: pd.DataFrame,
                          group_stats: Dict[str, pd.DataFrame],
                          group_comparison_df: pd.DataFrame,
                          output_dir: str, 
                          logger: logging.Logger):
    """
    Generate a comprehensive summary report.
    
    Args:
        csv_data: Dictionary of DataFrames
        comparison_df: Subject comparison results
        group_stats: Group statistics
        group_comparison_df: Group comparison results
        output_dir: Output directory for report
        logger: Logger instance
    """
    report_file = os.path.join(output_dir, "comparison_summary_report.txt")
    
    with open(report_file, 'w') as f:
        f.write("CSV GROUP COMPARISON REPORT\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Dataset overview
        f.write("DATASET OVERVIEW\n")
        f.write("-" * 20 + "\n")
        for file_name, df in csv_data.items():
            f.write(f"{file_name}:\n")
            f.write(f"  - Subjects: {len(df['Subject_ID'].unique()) if 'Subject_ID' in df.columns else 'N/A'}\n")
            f.write(f"  - Total rows: {len(df)}\n")
            f.write(f"  - Columns: {len(df.columns)}\n\n")
        
        # Common subjects analysis
        if not comparison_df.empty:
            f.write("SUBJECTS COMPARISON ANALYSIS\n")
            f.write("-" * 28 + "\n")
            f.write(f"Number of subjects found in ALL CSV files: {len(comparison_df)}\n")
            
            # Show subject IDs
            if len(comparison_df) > 0:
                subject_ids = comparison_df['Subject_ID'].tolist()
                subject_labels = [extract_subject_label(sid) for sid in subject_ids]
                f.write(f"Subject IDs: {', '.join(subject_labels)}\n\n")
            
            # Show largest differences
            diff_columns = [col for col in comparison_df.columns if col.endswith('_diff')]
            if diff_columns:
                f.write("Largest differences observed between groups:\n")
                for col in diff_columns:
                    max_diff = comparison_df[col].max()
                    mean_diff = comparison_df[col].mean()
                    f.write(f"  {col.replace('_diff', '')}: Max={max_diff:.4f}, Mean={mean_diff:.4f}\n")
                f.write("\n")
        else:
            f.write("SUBJECTS COMPARISON ANALYSIS\n")
            f.write("-" * 28 + "\n")
            f.write("No subjects found in ALL CSV files for comparison.\n\n")
        
        # Group statistics summary
        if group_stats:
            f.write("GROUP STATISTICS SUMMARY\n")
            f.write("-" * 25 + "\n")
            for file_name, stats_df in group_stats.items():
                f.write(f"{file_name}:\n")
                # Show mean values for key metrics
                key_metrics = ['ROI_Mean', 'Grey_Mean', 'Normal_Mean']
                for metric in key_metrics:
                    if metric in stats_df.columns:
                        mean_val = stats_df.loc['mean', metric]
                        std_val = stats_df.loc['std', metric]
                        f.write(f"  {metric}: {mean_val:.4f} ± {std_val:.4f}\n")
                f.write("\n")
        
        # Group comparison highlights
        if not group_comparison_df.empty:
            f.write("GROUP COMPARISON HIGHLIGHTS\n")
            f.write("-" * 28 + "\n")
            
            # Show metrics with largest differences
            if 'mean_difference' in group_comparison_df.columns:
                sorted_diffs = group_comparison_df.sort_values('mean_difference', key=abs, ascending=False)
                f.write("Metrics with largest mean differences:\n")
                for _, row in sorted_diffs.head(5).iterrows():
                    f.write(f"  {row['Metric']}: {row['mean_difference']:.4f}")
                    if 'cohens_d' in row:
                        f.write(f" (Cohen's d: {row['cohens_d']:.2f})")
                    f.write("\n")
        
        f.write("\nAnalysis completed successfully!\n")
        f.write("Check the generated CSV files and plots for detailed results.\n")
    
    logger.info(f"Summary report saved to: {report_file}")

def main():
    """Main function to run the CSV group comparison analysis."""
    parser = argparse.ArgumentParser(description="Compare multiple CSV files with analysis results")
    parser.add_argument("csv_files", nargs='+', help="Paths to CSV files to compare")
    parser.add_argument("-o", "--output", default="csv_comparison_results", 
                       help="Output directory for results (default: csv_comparison_results)")
    parser.add_argument("--no-plots", action="store_true", 
                       help="Skip generating visualization plots")
    parser.add_argument("--no-report", action="store_true", 
                       help="Skip generating summary report")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Setup logging
    logger = setup_logger(args.output)
    logger.info(f"Starting CSV group comparison analysis")
    logger.info(f"Input files: {args.csv_files}")
    logger.info(f"Output directory: {args.output}")
    
    try:
        # Load CSV files
        csv_data = load_csv_files(args.csv_files)
        
        # Identify common subjects
        common_subjects = identify_common_subjects(csv_data)
        
        # Compare subjects across files
        comparison_df = compare_subject_metrics(csv_data, common_subjects, args.output, logger)
        
        # Generate group statistics
        group_stats = generate_group_statistics(csv_data, args.output, logger)
        
        # Compare group statistics
        group_comparison_df = compare_group_statistics(group_stats, args.output, logger)
        
        # Generate visualizations
        if not args.no_plots:
            create_visualization_plots(csv_data, comparison_df, group_stats, args.output, logger)
        
        # Generate summary report
        if not args.no_report:
            generate_summary_report(csv_data, comparison_df, group_stats, 
                                  group_comparison_df, args.output, logger)
        
        logger.info("CSV group comparison analysis completed successfully!")
        print(f"\nAnalysis completed! Results saved to: {args.output}")
        
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        print(f"Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
