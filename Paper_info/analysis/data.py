"""
Data Loading Module for TI-Toolbox Research

This module provides standardized data loading functions for the TI-Toolbox research project.
It handles loading of processed CSV files, data validation, and basic preprocessing.

Author: TI-Toolbox Research Team
Date: July 2024
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')


class DataLoader:
    """
    A class to handle data loading operations for TI-Toolbox research.
    
    This class provides methods to load and validate data files for different
    research questions (Q1: Individualization, Q2: Mapping, Q3: Demographics).
    
    Attributes:
        data_dir (Path): Path to the processed data directory
        demographics_file (str): Name of demographics CSV file
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize the DataLoader.
        
        Args:
            data_dir (str): Path to the processed data directory
        """
        if data_dir is None:
            # Automatically find the data directory relative to the project root
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            self.data_dir = project_root / "case_studies" / "data" / "processed"
        else:
            self.data_dir = Path(data_dir)
        
        self.demographics_file = "demographics.csv"
        
        # Validate data directory exists
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
    
    def load_demographics(self) -> pd.DataFrame:
        """
        Load demographic data for participants.
        
        Returns:
            pd.DataFrame: Demographic data with columns:
                - Subject_ID: Participant identifier
                - age: Participant age
                - sex: Participant sex
                - cortical_bone_mass: Cortical bone mass measurements
                - volume: Bone volume measurements
                - mean: Mean bone thickness
        """
        file_path = self.data_dir / self.demographics_file
        if not file_path.exists():
            raise FileNotFoundError(f"Demographics file not found: {file_path}")
        
        df = pd.read_csv(file_path)
        print(f"Loaded demographics data: {len(df)} participants")
        return df
    
    def load_target_data(self, target: str, optimization_type: str, 
                        condition: str, file_path_override: Optional[str] = None) -> pd.DataFrame:
        """
        Load data for a specific target, optimization type, and condition.
        
        Args:
            target (str): Target region ('Left_Insula', 'Right_Hippocampus', 'sphere_x-36.1_y14.14_z0.33')
            optimization_type (str): Optimization type ('max', 'normal')
            condition (str): Condition type ('ernie', 'mapped', 'opt')
            
        Returns:
            pd.DataFrame: Target data with columns:
                - Subject_ID: Participant identifier
                - ROI_Mean: Mean electric field in ROI
                - ROI_Max: Maximum electric field in ROI
                - Normal_Mean: Mean electric field in normal tissue
                - Normal_Max: Maximum electric field in normal tissue
                - ROI_Focality: Focality measure (if available)
        """
        # Allow explicit file path override to bypass naming logic
        if file_path_override is not None:
            file_path = Path(file_path_override)
        else:
            # Map condition names to file naming scheme
            # Only normalize 'optimized' → 'opt'; allow custom conditions like 'mapped3'
            condition_map = {
                'optimized': 'opt',
                'opt': 'opt'
            }
            file_condition = condition_map.get(condition, condition)
            
            # Construct filename following the standard convention
            filename = f"{target}_{optimization_type}_{file_condition}.csv"
            file_path = self.data_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"Target data file not found: {file_path}")
        
        df = pd.read_csv(file_path)
        
        # Remove AVERAGE row if present
        df = df[df['Subject_ID'] != 'AVERAGE'].copy()
        
        # Extract focality from 4th column if it exists and not already present
        if len(df.columns) > 3 and 'focality' not in df.columns:
            df['focality'] = df.iloc[:, 3]
        
        # Select relevant columns (keep original names)
        columns = ['Subject_ID']
        
        # Add ROI_Mean if available
        if 'ROI_Mean' in df.columns:
            columns.append('ROI_Mean')
        elif 'mean' in df.columns:
            columns.append('mean')
            
        # Add ROI_Max if available
        if 'ROI_Max' in df.columns:
            columns.append('ROI_Max')
        elif 'max' in df.columns:
            columns.append('max')
            
        # Add Normal_Mean if available
        if 'Normal_Mean' in df.columns:
            columns.append('Normal_Mean')
            
        # Add Normal_Max if available
        if 'Normal_Max' in df.columns:
            columns.append('Normal_Max')
            
        # Add focality based on optimization type
        if optimization_type and 'normal' in optimization_type.lower():
            # For normal optimization, prefer Normal_Focality
            if 'Normal_Focality' in df.columns:
                columns.append('Normal_Focality')
            elif 'ROI_Focality' in df.columns:
                columns.append('ROI_Focality')
            elif 'focality' in df.columns:
                columns.append('focality')
        else:
            # For max optimization, prefer ROI_Focality
            if 'ROI_Focality' in df.columns:
                columns.append('ROI_Focality')
            elif 'Normal_Focality' in df.columns:
                columns.append('Normal_Focality')
            elif 'focality' in df.columns:
                columns.append('focality')
        
        # Select columns
        df = df[columns].copy()
        
        print(f"Loaded {target} data ({optimization_type}_{condition}): {len(df)} participants")
        return df
    
    def get_available_targets(self) -> List[str]:
        """
        Get list of available targets based on data files.
        
        Returns:
            List[str]: List of available target names
        """
        files = list(self.data_dir.glob("*.csv"))
        targets = set()
        
        for file in files:
            if file.name != self.demographics_file:
                parts = file.stem.split('_')
                if len(parts) >= 2:
                    # Handle different naming schemes
                    if parts[0] == 'sphere':
                        # Spherical target: sphere_x-36.1_y14.14_z0.33_max_ernie.csv
                        # Extract everything up to the optimization type
                        if len(parts) >= 4:  # sphere_x-36.1_y14.14_z0.33_max_ernie
                            target_name = '_'.join(parts[:-2])  # sphere_x-36.1_y14.14_z0.33
                            targets.add(target_name)
                    else:
                        # ROI target: Left_Insula_max_ernie.csv
                        if len(parts) >= 3:  # Left_Insula_max_ernie
                            target_name = '_'.join(parts[:-2])  # Left_Insula
                            targets.add(target_name)
        
        return sorted(list(targets))
    
    def get_available_conditions(self, target: str) -> Dict[str, List[str]]:
        """
        Get available optimization types and conditions for a target.
        
        Args:
            target (str): Target region name
            
        Returns:
            Dict[str, List[str]]: Dictionary with optimization types as keys and 
                                 lists of available conditions as values
        """
        files = list(self.data_dir.glob(f"{target}_*.csv"))
        conditions = {}
        
        for file in files:
            parts = file.stem.split('_')
            if len(parts) >= 3:
                # Handle different naming schemes
                if target.startswith('sphere_'):
                    # Spherical target: sphere_x-36.1_y14.14_z0.33_max_ernie.csv
                    # parts = ['sphere', 'x-36.1', 'y14.14', 'z0.33', 'max', 'ernie']
                    if len(parts) >= 6:  # Need at least 6 parts for spherical
                        opt_type = parts[-2]  # Second to last part (max/normal)
                        condition = parts[-1]  # Last part (ernie/mapped/opt)
                        
                        if opt_type not in conditions:
                            conditions[opt_type] = []
                        conditions[opt_type].append(condition)
                else:
                    # ROI target: Left_Insula_max_ernie.csv
                    # parts = ['Left', 'Insula', 'max', 'ernie']
                    opt_type = parts[-2]  # Second to last part
                    condition = parts[-1]  # Last part
                    
                    if opt_type not in conditions:
                        conditions[opt_type] = []
                    conditions[opt_type].append(condition)
        
        return conditions
    
    def create_comparison_dataset(self, target: str, optimization_type: str,
                                 condition_a: str, condition_b: str,
                                 file_path_a: Optional[str] = None,
                                 file_path_b: Optional[str] = None) -> pd.DataFrame:
        """
        Create a comparison dataset for two conditions.
        
        Args:
            target (str): Target region
            optimization_type (str): Optimization type
            condition_a (str): First condition name
            condition_b (str): Second condition name
            
        Returns:
            pd.DataFrame: Combined dataset with condition labels
        """
        # Load both conditions (optionally via explicit file paths)
        df_a = self.load_target_data(target, optimization_type, condition_a, file_path_override=file_path_a)
        df_b = self.load_target_data(target, optimization_type, condition_b, file_path_override=file_path_b)
        
        # Add condition labels
        df_a['condition'] = condition_a
        df_b['condition'] = condition_b
        
        # Combine datasets
        df_combined = pd.concat([df_a, df_b], ignore_index=True)
        
        print(f"Created comparison dataset: {condition_a} vs {condition_b} "
              f"({len(df_a)} participants each)")
        
        return df_combined
    
    def validate_data_quality(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Validate data quality and return summary statistics.
        
        Args:
            df (pd.DataFrame): Dataframe to validate
            
        Returns:
            Dict[str, any]: Quality metrics including missing values, outliers, etc.
        """
        quality_report = {
            'n_participants': len(df),
            'missing_values': df.isnull().sum().to_dict(),
            'duplicates': df.duplicated().sum(),
            'numeric_columns': []
        }
        
        # Check numeric columns
        for col in ['mean', 'max', 'focality']:
            if col in df.columns:
                quality_report['numeric_columns'].append(col)
                quality_report[f'{col}_range'] = (df[col].min(), df[col].max())
                quality_report[f'{col}_mean'] = df[col].mean()
                quality_report[f'{col}_std'] = df[col].std()
        
        return quality_report


def load_comparison_data(target: str, optimization_type: str, condition_a: str, condition_b: str,
                         file_path_a: Optional[str] = None,
                         file_path_b: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    Load data for any pairwise comparison between conditions.
    
    Args:
        target (str): Target region
        optimization_type (str): Optimization type ('max' or 'normal')
        condition_a (str): First condition ('ernie', 'optimized', 'mapped')
        condition_b (str): Second condition ('ernie', 'optimized', 'mapped')
        
    Returns:
        Tuple[pd.DataFrame, Dict[str, any]]: Comparison dataset and quality report
    """
    loader = DataLoader()
    
    # Create comparison dataset (with optional explicit file paths)
    df = loader.create_comparison_dataset(target, optimization_type, condition_a, condition_b,
                                          file_path_a=file_path_a, file_path_b=file_path_b)
    
    # Validate data quality
    quality_report = loader.validate_data_quality(df)
    
    return df, quality_report


def load_q1_data(target: str, optimization_type: str) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    Load data specifically for Q1 (Individualization) analysis.
    
    Args:
        target (str): Target region
        optimization_type (str): Optimization type ('max' or 'normal')
        
    Returns:
        Tuple[pd.DataFrame, Dict[str, any]]: Comparison dataset and quality report
    """
    return load_comparison_data(target, optimization_type, 'ernie', 'opt')


def load_q2_data(target: str, optimization_type: str) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    Load data specifically for Q2 (Mapping) analysis.
    
    Args:
        target (str): Target region
        optimization_type (str): Optimization type ('max' or 'normal')
        
    Returns:
        Tuple[pd.DataFrame, Dict[str, any]]: Comparison dataset and quality report
    """
    return load_comparison_data(target, optimization_type, 'opt', 'mapped')


def load_q3_data(target: str, optimization_type: str) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    Load data specifically for Q3 (Demographics) analysis.
    
    Args:
        target (str): Target region
        optimization_type (str): Optimization type ('max' or 'normal')
        
    Returns:
        Tuple[pd.DataFrame, Dict[str, any]]: Combined dataset with demographics and quality report
    """
    loader = DataLoader()
    
    # Load target data (use optimized condition for Q3)
    target_data = loader.load_target_data(target, optimization_type, 'opt')
    
    # Load demographics
    demographics = loader.load_demographics()
    
    # Merge datasets
    df = target_data.merge(demographics, on='Subject_ID', how='inner')
    
    # Validate data quality
    quality_report = loader.validate_data_quality(df)
    
    print(f"Q3 dataset: {len(df)} participants with complete data")
    
    return df, quality_report


def load_q3_data_enhanced(target: str, optimization_type: str) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    Load data for enhanced Q3 (Demographics) analysis with all three conditions.
    
    This function loads data from ernie, mapped, and optimized conditions
    and combines them with demographics for enhanced correlation analysis.
    
    Args:
        target (str): Target region
        optimization_type (str): Optimization type ('max' or 'normal')
        
    Returns:
        Tuple[pd.DataFrame, Dict[str, any]]: Combined dataset with all conditions and demographics
    """
    loader = DataLoader()
    
    # Load data from all three conditions
    ernie_data = loader.load_target_data(target, optimization_type, 'ernie')
    mapped_data = loader.load_target_data(target, optimization_type, 'mapped')
    optimized_data = loader.load_target_data(target, optimization_type, 'opt')
    
    # Load demographics
    demographics = loader.load_demographics()
    
    # Add condition identifier to each dataset
    ernie_data['condition'] = 'ernie'
    mapped_data['condition'] = 'mapped'
    optimized_data['condition'] = 'optimized'
    
    # Combine all conditions
    all_data = pd.concat([ernie_data, mapped_data, optimized_data], ignore_index=True)
    
    # Merge with demographics
    df = all_data.merge(demographics, on='Subject_ID', how='inner')
    
    # Validate data quality
    quality_report = loader.validate_data_quality(df)
    
    print(f"Enhanced Q3 dataset: {len(df)} participants with all conditions")
    print(f"  - Ernie: {len(df[df['condition'] == 'ernie'])} participants")
    print(f"  - Mapped: {len(df[df['condition'] == 'mapped'])} participants")
    print(f"  - Optimized: {len(df[df['condition'] == 'optimized'])} participants")
    
    return df, quality_report


if __name__ == "__main__":
    # Example usage and testing
    loader = DataLoader()
    
    print("Available targets:", loader.get_available_targets())
    
    for target in loader.get_available_targets():
        conditions = loader.get_available_conditions(target)
        print(f"\n{target}: {conditions}") 