# This script compares two analysis outputs and returns the results

import os
import sys
import argparse
import pandas as pd

def collect_arguments() -> tuple[list[str], str]:
    """
    Collect absolute paths to analysis directories and output directory using command line arguments.
    
    Returns:
        tuple[list[str], str]: List of absolute paths to analysis directories and output directory path
    """
    parser = argparse.ArgumentParser(description='Compare multiple SimNIBS analysis outputs')
    parser.add_argument('-analyses', nargs='+', required=True, help='Absolute paths to analysis directories (minimum 2)')
    parser.add_argument('--output', required=True, help='Path to output directory')
    
    args = parser.parse_args()
    
    if len(args.analyses) < 2:
        parser.error("At least 2 analysis paths must be provided")
    
    # Verify all analysis paths exist
    for path in args.analyses:
        if not os.path.isdir(path):
            parser.error(f"Analysis path does not exist or is not a directory: {path}")
    
    return args.analyses, args.output

def setup_output_dir(output_path: str) -> str:
    """
    Create and setup the output directory if it doesn't exist.
    
    Args:
        output_path (str): Path to desired output directory
    
    Returns:
        str: Path to the created/existing output directory
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)
    return output_path

def compare_analyses(analyses: list[str], output_dir: str):
    """
    Compare multiple analyses and write their names to a file.
    Extracts mean, max, and min values from each analysis CSV and computes percent differences.
    
    Args:
        analyses (list[str]): List of absolute paths to analysis directories
        output_dir (str): Path to the output directory
    """
    # Dictionary to store results for each analysis
    analysis_results = {}
    
    # Process each analysis directory
    for analysis_path in analyses:
        # Create a unique identifier that includes more path info to avoid collisions
        # Instead of just using the last directory name, use a more descriptive identifier
        path_parts = analysis_path.split('/')
        
        # Try to find subject and montage info in the path
        subject_id = "unknown"
        montage_name = "unknown"
        analysis_name = os.path.basename(os.path.normpath(analysis_path))
        
        for i, part in enumerate(path_parts):
            if part.startswith('sub-'):
                subject_id = part
            elif 'Simulations' in path_parts and i < len(path_parts) - 1:
                # Look for the directory after 'Simulations'
                sim_idx = path_parts.index('Simulations')
                if i == sim_idx + 1:
                    montage_name = part
        
        # Create unique identifier: subject_montage_analysis
        unique_name = f"{subject_id}_{montage_name}_{analysis_name}"
        
        # Find the CSV file in the analysis directory
        csv_files = [f for f in os.listdir(analysis_path) if f.endswith('.csv')]
        if not csv_files:
            print(f"Warning: No CSV file found in {analysis_path}")
            continue
        
        csv_path = os.path.join(analysis_path, csv_files[0])
        print(f"Reading CSV from: {csv_path}")
        
        # Read specific rows from the CSV
        try:
            df = pd.read_csv(csv_path, header=None)
            metrics = {
                'mean_value': float(df.iloc[1, 1]),  # Row 2, Column 2
                'max_value': float(df.iloc[2, 1]),   # Row 3, Column 2
                'min_value': float(df.iloc[3, 1]),   # Row 4, Column 2
            }
            analysis_results[unique_name] = metrics
            print(f"Extracted metrics from {unique_name}:")
            for key, value in metrics.items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(f"Error reading CSV for {unique_name}: {str(e)}")
            continue
    
    print(f"Debug: Found {len(analysis_results)} valid analyses")
    print(f"Debug: Analysis keys: {list(analysis_results.keys())}")
    
    # Calculate and write percent differences
    if len(analysis_results) < 2:
        print("Error: Need at least 2 valid analyses to compare")
        return
    
    # Write results to file
    with open(os.path.join(output_dir, 'comparison_results.txt'), 'w') as f:
        f.write("Analysis Comparison Results\n")
        f.write("=========================\n\n")
        
        # Write the analysis names
        f.write("Analyses compared:\n")
        for i, name in enumerate(analysis_results.keys(), 1):
            f.write(f"{i}. {name}\n")
        f.write("\n")
        
        # Calculate percent differences between each pair
        analysis_names = list(analysis_results.keys())
        for i in range(len(analysis_names)):
            for j in range(i + 1, len(analysis_names)):
                name1, name2 = analysis_names[i], analysis_names[j]
                results1, results2 = analysis_results[name1], analysis_results[name2]
                
                f.write(f"\nComparison between {name1} and {name2}:\n")
                f.write("-" * 40 + "\n")
                
                for metric in ['mean_value', 'max_value', 'min_value']:
                    val1, val2 = results1[metric], results2[metric]
                    # Calculate percent difference
                    avg = (val1 + val2) / 2
                    if avg != 0:
                        pct_diff = abs(val1 - val2) / avg * 100
                        f.write(f"{metric}:\n")
                        f.write(f"  {name1}: {val1:.6f}\n")
                        f.write(f"  {name2}: {val2:.6f}\n")
                        f.write(f"  Percent difference: {pct_diff:.2f}%\n\n")
                    else:
                        f.write(f"{metric}: Both values are 0\n\n")
        
        print(f"\nResults have been written to {os.path.join(output_dir, 'comparison_results.txt')}")

if __name__ == "__main__":
    analyses, output_path = collect_arguments()
    output_dir = setup_output_dir(output_path)
    compare_analyses(analyses, output_dir)