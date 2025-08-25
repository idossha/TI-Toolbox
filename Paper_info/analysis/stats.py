"""
Statistical Analysis Module for TI-Toolbox Research

This module provides statistical analysis functions for the three main research questions:
- Q1: Individualization effects (Individual vs Generalized models)
- Q2: Mapping effects (Free vs Mapped optimization)
- Q3: Demographic factors and individual variability

Author: TI-Toolbox Research Team
Date: July 2024
"""

import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.api import OLS, add_constant
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')


class StatisticalAnalyzer:
    """
    A class to perform statistical analyses for TI-Toolbox research questions.
    
    This class provides methods for paired t-tests, correlation analyses,
    and multiple regression analyses used across the three research questions.
    """
    
    def __init__(self):
        """Initialize the StatisticalAnalyzer."""
        self.results = {}
    
    def paired_comparison_analysis(self, df: pd.DataFrame, 
                                 variables: List[str] = None,
                                 optimization_type: str = None) -> Dict[str, Dict]:
        """
        Perform paired comparison analysis between two conditions.
        
        This is used for Q1 (Individualization) and Q2 (Mapping) analyses
        where we compare two conditions within subjects.
        
        Args:
            df (pd.DataFrame): Dataframe with 'condition' column and variables
            variables (List[str]): List of variables to analyze (default: ['ROI_Mean', 'ROI_Max', 'ROI_Focality'])
            
        Returns:
            Dict[str, Dict]: Results for each variable including:
                - diff: Mean difference (B - A)
                - percent_change: Percentage change
                - z_score: Standardized effect size
                - p_value: Statistical significance
                - cohens_d: Cohen's d effect size
                - significant: Boolean significance indicator
        """
        if variables is None:
            # Select variables based on optimization type
            if optimization_type and 'max' in optimization_type.lower():
                variables = ['ROI_Mean', 'ROI_Max', 'ROI_Focality']
            elif optimization_type and 'normal' in optimization_type.lower():
                variables = ['Normal_Mean', 'Normal_Max', 'Normal_Focality']
            else:
                # Fallback to all available variables
                variables = ['ROI_Mean', 'ROI_Max', 'ROI_Focality', 'Normal_Mean', 'Normal_Max']
        
        # Filter to only include variables that exist in the dataframe
        variables = [var for var in variables if var in df.columns]
        
        results = {}
        
        for var in variables:
            # Get data for each condition
            condition_a_data = df[df['condition'] == df['condition'].unique()[0]][var].values
            condition_b_data = df[df['condition'] == df['condition'].unique()[1]][var].values
            
            # Basic statistics
            mean_a, mean_b = np.mean(condition_a_data), np.mean(condition_b_data)
            std_a, std_b = np.std(condition_a_data, ddof=1), np.std(condition_b_data, ddof=1)
            diff = mean_b - mean_a
            
            # Calculate effect sizes
            percent_change = (diff / mean_a) * 100 if mean_a != 0 else 0
            pooled_std = np.sqrt((std_a**2 + std_b**2) / 2)
            z_score = diff / pooled_std if pooled_std != 0 else 0
            
            # Test for normality using Shapiro-Wilk test
            _, norm_p_a = stats.shapiro(condition_a_data)
            _, norm_p_b = stats.shapiro(condition_b_data)
            _, norm_p_diff = stats.shapiro(condition_b_data - condition_a_data)
            is_normal = all(p > 0.05 for p in [norm_p_a, norm_p_b, norm_p_diff])
            
            # Statistical tests - both parametric and non-parametric
            # Paired t-test (parametric)
            t_stat, t_p_value = stats.ttest_rel(condition_b_data, condition_a_data)
            cohens_d = np.mean(condition_b_data - condition_a_data) / np.std(condition_b_data - condition_a_data, ddof=1)
            
            # Wilcoxon signed-rank test (non-parametric)
            try:
                w_stat, w_p_value = stats.wilcoxon(condition_b_data, condition_a_data, alternative='two-sided')
                # Calculate effect size for Wilcoxon (r = Z / sqrt(N))
                z_score_wilcoxon = (w_stat - len(condition_a_data) * (len(condition_a_data) + 1) / 4) / np.sqrt(len(condition_a_data) * (len(condition_a_data) + 1) * (2 * len(condition_a_data) + 1) / 24)
                r_effect_size = abs(z_score_wilcoxon) / np.sqrt(len(condition_a_data))
            except ValueError:
                # Handle case where all differences are zero
                w_stat, w_p_value = np.nan, 1.0
                r_effect_size = 0.0
            
            # Choose appropriate test based on normality
            if is_normal:
                primary_p_value = t_p_value
                primary_test = "t-test"
                primary_effect_size = cohens_d
                primary_effect_name = "Cohen's d"
            else:
                primary_p_value = w_p_value
                primary_test = "Wilcoxon"
                primary_effect_size = r_effect_size
                primary_effect_name = "r"
            
            # Store results
            results[var] = {
                'diff': diff,
                'percent_change': percent_change,
                'z_score': z_score,
                'mean_a': mean_a,
                'mean_b': mean_b,
                'std_a': std_a,
                'std_b': std_b,
                'n': len(condition_a_data),
                # Primary test results (chosen based on normality)
                'p_value': primary_p_value,
                'effect_size': primary_effect_size,
                'effect_size_name': primary_effect_name,
                'test_used': primary_test,
                'significant': primary_p_value < 0.05,
                # Parametric test results
                'parametric': {
                    'test_name': 't-test',
                    'statistic': t_stat,
                    'p_value': t_p_value,
                    'cohens_d': cohens_d,
                    'significant': t_p_value < 0.05
                },
                # Non-parametric test results
                'nonparametric': {
                    'test_name': 'Wilcoxon signed-rank',
                    'statistic': w_stat,
                    'p_value': w_p_value,
                    'r_effect_size': r_effect_size,
                    'significant': w_p_value < 0.05
                },
                # Normality testing
                'normality': {
                    'is_normal': is_normal,
                    'shapiro_p_a': norm_p_a,
                    'shapiro_p_b': norm_p_b,
                    'shapiro_p_diff': norm_p_diff,
                    'recommended_test': primary_test
                }
            }
        
        return results
    
    def correlation_analysis(self, df: pd.DataFrame, 
                           target_vars: List[str], 
                           predictor_vars: List[str]) -> Dict[str, Dict]:
        """
        Perform correlation analysis between target and predictor variables.
        
        This is used for Q3 (Demographics) analysis to examine relationships
        between electric field measures and demographic factors.
        
        Args:
            df (pd.DataFrame): Dataframe with target and predictor variables
            target_vars (List[str]): Target variables (e.g., ['mean', 'max'])
            predictor_vars (List[str]): Predictor variables (e.g., ['age', 'volume', 'mean_thickness'])
            
        Returns:
            Dict[str, Dict]: Correlation results for each target-predictor pair
        """
        results = {}
        
        for target in target_vars:
            if target not in df.columns:
                continue
                
            results[target] = {}
            
            for predictor in predictor_vars:
                if predictor not in df.columns:
                    continue
                
                # Remove missing values
                valid_data = df[[target, predictor]].dropna()
                
                if len(valid_data) < 3:  # Need at least 3 points for correlation
                    continue
                
                # Calculate correlation
                correlation, p_value = stats.pearsonr(valid_data[target], valid_data[predictor])
                
                results[target][predictor] = {
                    'correlation': correlation,
                    'p_value': p_value,
                    'significant': p_value < 0.05,
                    'n': len(valid_data)
                }
        
        return results
    
    def multiple_regression_analysis(self, df: pd.DataFrame, 
                                   target_var: str, 
                                   predictor_vars: List[str]) -> Dict[str, any]:
        """
        Perform multiple linear regression analysis.
        
        This is used for Q3 (Demographics) analysis to predict electric field
        measures from multiple demographic factors.
        
        Args:
            df (pd.DataFrame): Dataframe with target and predictor variables
            target_var (str): Target variable (e.g., 'mean')
            predictor_vars (List[str]): Predictor variables
            
        Returns:
            Dict[str, any]: Regression results including:
                - r_squared: Model R-squared
                - coefficients: Regression coefficients
                - p_values: P-values for each coefficient
                - model_summary: Full model summary
        """
        # Prepare data
        valid_predictors = [var for var in predictor_vars if var in df.columns]
        
        if target_var not in df.columns or not valid_predictors:
            return None
        
        # Remove missing values
        analysis_data = df[[target_var] + valid_predictors].dropna()
        
        if len(analysis_data) < len(valid_predictors) + 2:  # Need enough data points
            return None
        
        # Prepare variables
        X = add_constant(analysis_data[valid_predictors])
        y = analysis_data[target_var]
        
        # Fit model
        model = OLS(y, X).fit()
        
        # Extract results
        results = {
            'r_squared': model.rsquared,
            'adjusted_r_squared': model.rsquared_adj,
            'f_statistic': model.fvalue,
            'f_p_value': model.f_pvalue,
            'coefficients': model.params.to_dict(),
            'p_values': model.pvalues.to_dict(),
            'standard_errors': model.bse.to_dict(),
            'n': len(y),
            'model_summary': model.summary()
        }
        
        return results
    
    def generate_summary_report(self, analysis_type: str, results: Dict, 
                              target: str, optimization_type: str) -> str:
        """
        Generate a human-readable summary report of statistical results.
        
        Args:
            analysis_type (str): Type of analysis ('Q1', 'Q2', or 'Q3')
            results (Dict): Statistical results
            target (str): Target region
            optimization_type (str): Optimization type
            
        Returns:
            str: Formatted summary report
        """
        report = f"STATISTICAL ANALYSIS REPORT\n"
        report += f"=" * 50 + "\n\n"
        report += f"Analysis Type: {analysis_type}\n"
        report += f"Target: {target}\n"
        report += f"Optimization: {optimization_type}\n\n"
        
        if analysis_type in ['Q1', 'Q2']:
            # Paired comparison results
            report += f"Study Design: Within-subjects comparison\n"
            report += f"Variables Analyzed: {', '.join(results.keys())}\n\n"
            
            report += "RESULTS:\n"
            report += "-" * 30 + "\n"
            
            for var, result in results.items():
                direction = "higher" if result['diff'] > 0 else "lower"
                sig_text = "**SIGNIFICANT**" if result['significant'] else "Not significant"
                
                report += f"{var.upper()}: {direction} in condition B "
                report += f"({result['diff']:.3f} = {result['percent_change']:+.1f}% = {result['z_score']:+.2f} SD)\n"
                report += f"  p = {result['p_value']:.3f}, Cohen's d = {result['cohens_d']:.2f} - {sig_text}\n\n"
        
        elif analysis_type == 'Q3':
            # Correlation and regression results
            if 'correlations' in results:
                report += "CORRELATION RESULTS:\n"
                report += "-" * 20 + "\n"
                for target_var, corr_results in results['correlations'].items():
                    for predictor, corr_data in corr_results.items():
                        sig_text = "**SIGNIFICANT**" if corr_data['significant'] else "Not significant"
                        report += f"{target_var} vs {predictor}: r = {corr_data['correlation']:.3f}, "
                        report += f"p = {corr_data['p_value']:.3f} - {sig_text}\n"
                report += "\n"
            
            if 'regression' in results and results['regression']:
                reg_results = results['regression']
                report += "MULTIPLE REGRESSION RESULTS:\n"
                report += "-" * 25 + "\n"
                report += f"R² = {reg_results['r_squared']:.3f} (n = {reg_results['n']})\n"
                report += f"F-statistic = {reg_results['f_statistic']:.2f}, p = {reg_results['f_p_value']:.3f}\n\n"
                
                report += "Coefficients:\n"
                for var, coef in reg_results['coefficients'].items():
                    p_val = reg_results['p_values'][var]
                    sig_text = "**SIGNIFICANT**" if p_val < 0.05 else "Not significant"
                    report += f"  {var}: {coef:.3f} (p = {p_val:.3f}) - {sig_text}\n"
        
        return report


def analyze_q1_individualization(df: pd.DataFrame, target: str, 
                                optimization_type: str) -> Dict[str, any]:
    """
    Analyze Q1: Individualization effects (Individual vs Generalized models).
    
    Args:
        df (pd.DataFrame): Comparison dataset with 'condition' column
        target (str): Target region
        optimization_type (str): Optimization type
        
    Returns:
        Dict[str, any]: Complete analysis results
    """
    analyzer = StatisticalAnalyzer()
    
    # Perform paired comparison analysis
    comparison_results = analyzer.paired_comparison_analysis(df)
    
    # Generate summary report
    summary_report = analyzer.generate_summary_report('Q1', comparison_results, 
                                                    target, optimization_type)
    
    return {
        'analysis_type': 'Q1_individualization',
        'target': target,
        'optimization_type': optimization_type,
        'comparison_results': comparison_results,
        'summary_report': summary_report
    }


def analyze_q2_mapping(df: pd.DataFrame, target: str, 
                      optimization_type: str) -> Dict[str, any]:
    """
    Analyze Q2: Mapping effects (Free vs Mapped optimization).
    
    Args:
        df (pd.DataFrame): Comparison dataset with 'condition' column
        target (str): Target region
        optimization_type (str): Optimization type
        
    Returns:
        Dict[str, any]: Complete analysis results
    """
    analyzer = StatisticalAnalyzer()
    
    # Perform paired comparison analysis
    comparison_results = analyzer.paired_comparison_analysis(df)
    
    # Generate summary report
    summary_report = analyzer.generate_summary_report('Q2', comparison_results, 
                                                    target, optimization_type)
    
    return {
        'analysis_type': 'Q2_mapping',
        'target': target,
        'optimization_type': optimization_type,
        'comparison_results': comparison_results,
        'summary_report': summary_report
    }


def analyze_q3_demographics(df: pd.DataFrame, target: str, 
                           optimization_type: str) -> Dict[str, any]:
    """
    Analyze Q3: Demographic factors and individual variability.
    
    Args:
        df (pd.DataFrame): Dataset with target variables and demographics
        target (str): Target region
        optimization_type (str): Optimization type
        
    Returns:
        Dict[str, any]: Complete analysis results
    """
    analyzer = StatisticalAnalyzer()
    
    # Define target and predictor variables
    target_vars = ['ROI_Mean', 'ROI_Max', 'Normal_Mean', 'Normal_Max']
    predictor_vars = ['age', 'bone_volume', 'bone_mean_thick']  # Demographics columns
    
    # Perform correlation analysis
    correlation_results = analyzer.correlation_analysis(df, target_vars, predictor_vars)
    
    # Perform multiple regression analysis (only if we have sufficient data)
    regression_results = None
    if len(df.dropna(subset=predictor_vars)) >= len(predictor_vars) + 2:
        regression_results = analyzer.multiple_regression_analysis(df, 'ROI_Mean', predictor_vars)
    
    # Combine results
    combined_results = {
        'correlations': correlation_results,
        'regression': regression_results
    }
    
    # Generate summary report
    summary_report = analyzer.generate_summary_report('Q3', combined_results, 
                                                    target, optimization_type)
    
    return {
        'analysis_type': 'Q3_demographics',
        'target': target,
        'optimization_type': optimization_type,
        'correlation_results': correlation_results,
        'regression_results': regression_results,
        'summary_report': summary_report
    }


def analyze_pairwise_comparisons(df: pd.DataFrame, target: str, 
                               optimization_type: str, condition_a: str, condition_b: str) -> Dict[str, any]:
    """
    Analyze pairwise comparisons between two conditions.
    
    This function performs comprehensive pairwise comparison analysis between
    any two conditions (ernie vs mapped, ernie vs optimized, mapped vs optimized).
    
    Args:
        df (pd.DataFrame): Comparison dataset with 'condition' column
        target (str): Target region
        optimization_type (str): Optimization type
        condition_a (str): First condition
        condition_b (str): Second condition
        
    Returns:
        Dict[str, any]: Complete analysis results
    """
    analyzer = StatisticalAnalyzer()
    
    # Perform paired comparison analysis
    comparison_results = analyzer.paired_comparison_analysis(df, optimization_type=optimization_type)
    
    # Generate summary report
    summary_report = analyzer.generate_summary_report('pairwise', comparison_results, 
                                                    target, optimization_type)
    
    return {
        'analysis_type': 'pairwise_comparisons',
        'target': target,
        'optimization_type': optimization_type,
        'condition_a': condition_a,
        'condition_b': condition_b,
        'comparison_results': comparison_results,
        'summary_report': summary_report
    }


if __name__ == "__main__":
    # Example usage and testing
    print("Statistical Analysis Module for TI-Toolbox Research")
    print("Available functions:")
    print("- analyze_q1_individualization()")
    print("- analyze_q2_mapping()")
    print("- analyze_q3_demographics()") 