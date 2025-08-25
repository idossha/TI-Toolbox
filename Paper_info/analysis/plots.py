"""
Visualization Module for TI-Toolbox Research

This module provides publication-ready plotting functions following best practices
from top academic journals (Cell, Science, Nature) for the three main research questions:
- Q1: Individualization effects (Individual vs Generalized models)
- Q2: Mapping effects (Free vs Mapped optimization)  
- Q3: Demographic factors and individual variability

Author: TI-Toolbox Research Team
Date: July 2024
"""

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Set publication-quality style following Cell/Science/Nature standards
plt.style.use('default')

# Define professional color palette (accessible and publication-ready)
PROFESSIONAL_COLORS = {
    'primary': '#2E3440',      # Dark gray (main text)
    'secondary': '#5E81AC',    # Blue (primary data)
    'accent': '#BF616A',       # Red (secondary data)
    'tertiary': '#88C0D0',     # Light blue (tertiary data)
    'quaternary': '#8FBCBB',   # Teal (quaternary data)
    'success': '#A3BE8C',      # Green (positive effects)
    'warning': '#EBCB8B',      # Yellow (cautions)
    'error': '#BF616A',        # Red (errors/significance)
    'neutral': '#D8DEE9',      # Light gray (backgrounds)
    'white': '#FFFFFF',        # White
    'black': '#2E3440'         # Black
}

# Define condition-specific colors
CONDITION_COLORS = {
    'ernie': PROFESSIONAL_COLORS['secondary'],
    'mapped': PROFESSIONAL_COLORS['accent'],
    'optimized': PROFESSIONAL_COLORS['tertiary'],
    'individual': PROFESSIONAL_COLORS['secondary'],
    'generalized': PROFESSIONAL_COLORS['accent'],
    'free': PROFESSIONAL_COLORS['tertiary'],
    'mapped_opt': PROFESSIONAL_COLORS['quaternary']
}


class PublicationPlotter:
    """
    A class to create publication-ready plots following Cell/Science/Nature standards.
    
    This class provides methods for creating consistent, high-quality
    visualizations for all research questions with professional styling.
    """
    
    def __init__(self, figsize: Tuple[int, int] = (12, 8), dpi: int = 300):
        """
        Initialize the PublicationPlotter.
        
        Args:
            figsize (Tuple[int, int]): Default figure size (width, height)
            dpi (int): Figure resolution (300 for publication quality)
        """
        self.figsize = figsize
        self.dpi = dpi
        self.colors = PROFESSIONAL_COLORS
        self.condition_colors = CONDITION_COLORS
    
    def setup_publication_style(self):
        """Set up Cell/Science/Nature publication-quality plotting style."""
        plt.rcParams.update({
            # Typography - following journal standards
            'font.size': 8,
            'axes.titlesize': 9,
            'axes.labelsize': 8,
            'xtick.labelsize': 7,
            'ytick.labelsize': 7,
            'legend.fontsize': 7,
            'figure.titlesize': 10,
            'font.family': 'Arial',
            'font.sans-serif': ['Arial', 'DejaVu Sans', 'Liberation Sans'],
            'mathtext.fontset': 'custom',
            'mathtext.rm': 'Arial',
            'mathtext.it': 'Arial:italic',
            'mathtext.bf': 'Arial:bold',
            
            # Line and marker properties
            'lines.linewidth': 1.0,
            'lines.markersize': 4,
            'axes.linewidth': 0.8,
            
            # Spines and grid
            'axes.spines.top': False,
            'axes.spines.right': False,
            'axes.spines.left': True,
            'axes.spines.bottom': True,
            'axes.grid': False,
            
            # Figure properties
            'figure.facecolor': 'white',
            'axes.facecolor': 'white',
            'savefig.facecolor': 'white',
            'savefig.bbox': 'tight',
            'savefig.dpi': 300,
            
            # Tick properties
            'xtick.major.size': 3,
            'xtick.major.width': 0.8,
            'xtick.minor.size': 1.5,
            'xtick.minor.width': 0.5,
            'ytick.major.size': 3,
            'ytick.major.width': 0.8,
            'ytick.minor.size': 1.5,
            'ytick.minor.width': 0.5,
            
            # Legend properties
            'legend.frameon': False,
            'legend.fancybox': False,
            'legend.shadow': False,
            'legend.borderpad': 0.5,
            'legend.labelspacing': 0.3,
            'legend.handlelength': 1.5,
            'legend.handleheight': 0.7,
            'legend.handletextpad': 0.5,
            'legend.columnspacing': 1.0,
        })
    
    def create_paired_comparison_plot(self, df: pd.DataFrame, 
                                    variables: List[str] = None,
                                    title: str = "Paired Comparison Results",
                                    stats_results: Dict = None,
                                    optimization_type: str = None) -> plt.Figure:
        """
        Create publication-ready paired comparison plots following journal standards.
        
        Args:
            df (pd.DataFrame): Dataframe with 'condition' column and variables
            variables (List[str]): Variables to plot (default: ['ROI_Mean', 'ROI_Max', 'ROI_Focality'])
            title (str): Plot title
            stats_results (Dict): Statistical results from paired_comparison_analysis
            
        Returns:
            plt.Figure: Publication-ready figure
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
        
        self.setup_publication_style()
        
        # Calculate optimal figure size based on number of variables
        n_vars = len(variables)
        fig_width = max(5 * n_vars, 15)  # Increased width for better spacing
        fig_height = 6  # Increased height for better spacing
        
        fig, axes = plt.subplots(1, n_vars, figsize=(fig_width, fig_height), dpi=self.dpi)
        
        if n_vars == 1:
            axes = [axes]
        
        for i, var in enumerate(variables):
            ax = axes[i]
            
            # Get paired data for each participant
            pivot_df = df.pivot(index='Subject_ID', columns='condition', values=var).dropna()
            
            # Calculate means and standard errors
            condition_names = pivot_df.columns
            means = pivot_df.mean()
            sems = pivot_df.sem()
            
            # Create box plot with professional styling
            # Prepare data for box plot
            plot_data = []
            plot_labels = []
            plot_colors = []
            
            for condition in condition_names:
                plot_data.append(pivot_df[condition])
                plot_labels.append(condition)
                
                # Use condition-specific colors
                if 'ernie' in condition.lower():
                    plot_colors.append(self.condition_colors['ernie'])
                elif 'mapped' in condition.lower():
                    plot_colors.append(self.condition_colors['mapped'])
                elif 'opt' in condition.lower():
                    plot_colors.append(self.condition_colors['optimized'])
                elif 'individual' in condition.lower():
                    plot_colors.append(self.condition_colors['individual'])
                elif 'generalized' in condition.lower():
                    plot_colors.append(self.condition_colors['generalized'])
                else:
                    plot_colors.append(self.colors['secondary'])
            
            # Create box plot with improved styling
            bp = ax.boxplot(plot_data, patch_artist=True, 
                          medianprops={'color': self.colors['primary'], 'linewidth': 2},
                          flierprops={'marker': 'o', 'markerfacecolor': self.colors['primary'], 
                                    'markeredgecolor': self.colors['primary'], 'markersize': 3, 'alpha': 0.6},
                          whiskerprops={'color': self.colors['primary'], 'linewidth': 1.5},
                          capprops={'color': self.colors['primary'], 'linewidth': 1.5},
                          boxprops={'linewidth': 1.5},
                          widths=0.6)
            
            # Color the boxes with better alpha
            for patch, color in zip(bp['boxes'], plot_colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.6)
                patch.set_edgecolor(self.colors['primary'])
            
            # Add individual data points with better jitter and styling
            np.random.seed(42)  # For reproducible jitter
            for i, (data, color) in enumerate(zip(plot_data, plot_colors)):
                x = np.random.normal(i + 1, 0.03, size=len(data))
                ax.scatter(x, data, alpha=0.5, s=15, c=color, zorder=3, 
                          edgecolors='white', linewidths=0.3)
                
            # Set x-axis labels with better positioning
            ax.set_xticks(range(1, len(plot_labels) + 1))
            ax.set_xticklabels(plot_labels, rotation=0, ha='center')
            
            # Add connecting lines for paired data (only if exactly 2 conditions)
            if len(condition_names) == 2:
                for idx, (subject_id, row) in enumerate(pivot_df.iterrows()):
                    # Darken the connective lines (made darker as requested)
                    ax.plot([1, 2], [row.iloc[0], row.iloc[1]], 
                           color=self.colors['neutral'], alpha=0.8, linewidth=1.2,
                           zorder=1)
                    
                    # Add subject IDs next to the dots
                    # Position text slightly offset from the dots
                    offset_x = 0.08
                    offset_y = (row.iloc[1] - row.iloc[0]) * 0.02  # Small y offset based on difference
                    
                    # Add subject ID near the second dot (right side)
                    ax.text(2 + offset_x, row.iloc[1] + offset_y, str(subject_id), 
                           fontsize=7, alpha=0.7, color=self.colors['primary'],
                           ha='left', va='center', zorder=4)
            
            # Add statistical information if available
            if stats_results and var in stats_results:
                stats = stats_results[var]
                p_val = stats['p_value']
                effect_size = stats['effect_size']
                effect_size_name = stats['effect_size_name']
                test_used = stats['test_used']
                percent_change = stats['percent_change']
                
                # Significance indicator with professional styling
                if p_val < 0.001:
                    sig_text = "***"
                    sig_color = self.colors['error']
                elif p_val < 0.01:
                    sig_text = "**"
                    sig_color = self.colors['error']
                elif p_val < 0.05:
                    sig_text = "*"
                    sig_color = self.colors['error']
                else:
                    sig_text = "n.s."
                    sig_color = self.colors['primary']
                
                # Add statistical annotation above boxes with proper spacing
                y_max = max([max(data) for data in plot_data])
                y_min = min([min(data) for data in plot_data])
                y_range = y_max - y_min
                y_text = y_max + y_range * 0.1
                
                # Position text in center of the plot
                x_center = (len(plot_data) + 1) / 2
                
                # Add statistical text with improved spacing
                ax.text(x_center, y_text + y_range * 0.03, sig_text, ha='center', va='bottom', 
                       fontsize=12, fontweight='bold', color=sig_color)
                ax.text(x_center, y_text + y_range * 0.08, f'p = {p_val:.3f} ({test_used})', ha='center', va='bottom', 
                       fontsize=9, color=self.colors['primary'])
                ax.text(x_center, y_text + y_range * 0.13, f'{effect_size_name} = {effect_size:.2f}', ha='center', va='bottom', 
                       fontsize=9, color=self.colors['primary'])
                ax.text(x_center, y_text + y_range * 0.18, f'{percent_change:+.1f}%', ha='center', va='bottom', 
                       fontsize=9, fontweight='bold', color=self.colors['primary'])
                
                # Add normality test results if available
                if 'normality' in stats:
                    norm_info = stats['normality']
                    norm_text = "Normal" if norm_info['is_normal'] else "Non-normal"
                    norm_color = self.colors['success'] if norm_info['is_normal'] else self.colors['warning']
                    ax.text(x_center, y_text + y_range * 0.23, f'Data: {norm_text}', ha='center', va='bottom', 
                           fontsize=8, color=norm_color, style='italic')
            
            # Customize plot with professional styling
            ax.set_xlim(0.5, len(condition_names) + 0.5)
            ax.set_xlabel('Condition', fontsize=12, fontweight='bold', color=self.colors['primary'])
            ax.set_ylabel(f'{var} (V/m)', fontsize=12, fontweight='bold', color=self.colors['primary'])
            # Set title above the values - moderately reduced padding
            ax.set_title(f'{var}', fontsize=13, fontweight='bold', 
                        color=self.colors['primary'], pad=30)
            ax.set_xticks(range(1, len(plot_labels) + 1))
            ax.set_xticklabels(plot_labels, fontsize=10, fontweight='bold', color=self.colors['primary'])
            
            # Set y-axis ticks and labels
            ax.tick_params(axis='y', labelsize=10, color=self.colors['primary'])
            ax.tick_params(axis='x', labelsize=10, color=self.colors['primary'])
            
            # Add grid for better readability
            ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
            ax.set_axisbelow(True)
            
            # Remove top and right spines for cleaner look
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_linewidth(1.2)
            ax.spines['bottom'].set_linewidth(1.2)
            
            # Set axis limits with some padding
            y_min, y_max = ax.get_ylim()
            y_range = y_max - y_min
            ax.set_ylim(y_min - 0.05 * y_range, y_max + 0.25 * y_range)  # More space for annotations
        
        # Add overall title with professional styling - moderately reduced padding
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=1.02)
        
        # Adjust layout for professional appearance - moderately reduced padding
        plt.tight_layout()
        plt.subplots_adjust(top=0.88)  # Make room for title only
        
        return fig
    
    def create_scatter_comparison_plot(self, df: pd.DataFrame, 
                                      condition_a: str, condition_b: str,
                                      variables: List[str] = None,
                                      title: str = "Scatter Comparison",
                                      stats_results: Dict = None,
                                      optimization_type: str = None) -> plt.Figure:
        """
        Create scatter plot comparison with X=condition_a, Y=condition_b, unity line.
        
        Args:
            df (pd.DataFrame): Dataframe with 'condition' column and variables
            condition_a (str): Name of first condition (X-axis)
            condition_b (str): Name of second condition (Y-axis)
            variables (List[str]): Variables to plot
            title (str): Plot title
            stats_results (Dict): Statistical results from paired_comparison_analysis
            optimization_type (str): Type of optimization for variable selection
            
        Returns:
            plt.Figure: Scatter comparison figure
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
        
        self.setup_publication_style()
        
        # Calculate optimal figure size based on number of variables
        n_vars = len(variables)
        fig_width = max(5 * n_vars, 15)
        fig_height = 6
        
        fig, axes = plt.subplots(1, n_vars, figsize=(fig_width, fig_height), dpi=self.dpi)
        
        if n_vars == 1:
            axes = [axes]
        
        for i, var in enumerate(variables):
            ax = axes[i]
            
            # Get paired data for each participant
            pivot_df = df.pivot(index='Subject_ID', columns='condition', values=var).dropna()
            
            # Check if both conditions exist
            if condition_a not in pivot_df.columns or condition_b not in pivot_df.columns:
                continue
                
            x_data = pivot_df[condition_a]
            y_data = pivot_df[condition_b]
            
            # Create scatter plot
            ax.scatter(x_data, y_data, alpha=0.7, s=50, 
                      c=self.colors['secondary'], edgecolors=self.colors['primary'], 
                      linewidths=0.5, zorder=3)
            
            # Add subject IDs next to dots
            for subject_id, (x_val, y_val) in zip(pivot_df.index, zip(x_data, y_data)):
                ax.text(x_val + (max(x_data) - min(x_data)) * 0.02, 
                       y_val + (max(y_data) - min(y_data)) * 0.02, 
                       str(subject_id), fontsize=8, alpha=0.7, 
                       color=self.colors['primary'], ha='left', va='bottom', zorder=4)
            
            # Calculate range for unity line
            all_data = list(x_data) + list(y_data)
            data_min = min(all_data)
            data_max = max(all_data)
            data_range = data_max - data_min
            line_min = data_min - data_range * 0.05
            line_max = data_max + data_range * 0.05
            
            # Add unity line (diagonal)
            ax.plot([line_min, line_max], [line_min, line_max], 
                   color=self.colors['neutral'], linestyle='--', alpha=0.6, 
                   linewidth=1.5, zorder=1, label='Unity line')
            
            # Add statistical information if available
            if stats_results and var in stats_results:
                stats = stats_results[var]
                p_val = stats['p_value']
                test_used = stats['test_used']
                
                # Add correlation information
                from scipy.stats import pearsonr
                correlation, _ = pearsonr(x_data, y_data)
                
                # Position statistics text in upper left
                ax.text(0.05, 0.95, f'r = {correlation:.3f}', transform=ax.transAxes,
                       fontsize=10, fontweight='bold', color=self.colors['primary'],
                       ha='left', va='top', bbox=dict(boxstyle='round,pad=0.3', 
                       facecolor='white', alpha=0.8))
                
                ax.text(0.05, 0.85, f'p = {p_val:.3f}', transform=ax.transAxes,
                       fontsize=9, color=self.colors['primary'],
                       ha='left', va='top', bbox=dict(boxstyle='round,pad=0.3', 
                       facecolor='white', alpha=0.8))
            
            # Customize plot with professional styling
            ax.set_xlabel(f'{condition_a} {var} (V/m)', fontsize=12, fontweight='bold', 
                         color=self.colors['primary'])
            ax.set_ylabel(f'{condition_b} {var} (V/m)', fontsize=12, fontweight='bold', 
                         color=self.colors['primary'])
            ax.set_title(f'{var}', fontsize=13, fontweight='bold', 
                        color=self.colors['primary'], pad=20)
            
            # Set equal aspect ratio and limits
            ax.set_xlim(line_min, line_max)
            ax.set_ylim(line_min, line_max)
            ax.set_aspect('equal')
            
            # Add grid for better readability
            ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
            ax.set_axisbelow(True)
            
            # Style tick labels
            ax.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
            
            # Remove top and right spines for cleaner look
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_linewidth(1.2)
            ax.spines['bottom'].set_linewidth(1.2)
        
        # Add overall title with professional styling
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=1.02)
        
        # Adjust layout for professional appearance
        plt.tight_layout()
        plt.subplots_adjust(top=0.88)
        
        return fig
    
    def create_normality_check_plot(self, df: pd.DataFrame, 
                                   variables: List[str] = None,
                                   title: str = "Normality Check",
                                   stats_results: Dict = None,
                                   optimization_type: str = None) -> plt.Figure:
        """
        Create normality check plots with Q-Q plots and histograms.
        
        Args:
            df (pd.DataFrame): Dataframe with 'condition' column and variables
            variables (List[str]): Variables to check (default: ['ROI_Mean', 'ROI_Max', 'ROI_Focality'])
            title (str): Plot title
            stats_results (Dict): Statistical results containing normality tests
            
        Returns:
            plt.Figure: Normality check figure
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
        
        self.setup_publication_style()
        
        # Calculate figure size
        n_vars = len(variables)
        fig_width = max(4 * n_vars, 12)
        fig_height = 8
        
        fig, axes = plt.subplots(2, n_vars, figsize=(fig_width, fig_height), dpi=self.dpi)
        
        if n_vars == 1:
            axes = axes.reshape(-1, 1)
        
        for i, var in enumerate(variables):
            # Get paired data for each participant
            pivot_df = df.pivot(index='Subject_ID', columns='condition', values=var).dropna()
            condition_names = pivot_df.columns
            
            # Calculate differences for paired data
            if len(condition_names) == 2:
                differences = pivot_df.iloc[:, 1] - pivot_df.iloc[:, 0]
                
                # Top plot: Q-Q plot for differences
                ax_qq = axes[0, i]
                from scipy import stats as scipy_stats
                scipy_stats.probplot(differences, dist="norm", plot=ax_qq)
                ax_qq.set_title(f'{var} - Q-Q Plot (Differences)', fontsize=10, fontweight='bold')
                ax_qq.get_lines()[0].set_markerfacecolor(self.colors['secondary'])
                ax_qq.get_lines()[0].set_markeredgecolor(self.colors['primary'])
                ax_qq.get_lines()[0].set_markersize(4)
                ax_qq.get_lines()[1].set_color(self.colors['error'])
                
                # Bottom plot: Histogram of differences
                ax_hist = axes[1, i]
                ax_hist.hist(differences, bins=10, alpha=0.7, color=self.colors['secondary'],
                           edgecolor=self.colors['primary'], density=True)
                
                # Overlay normal curve
                x = np.linspace(differences.min(), differences.max(), 100)
                y = scipy_stats.norm.pdf(x, differences.mean(), differences.std())
                ax_hist.plot(x, y, color=self.colors['error'], linewidth=2, label='Normal fit')
                
                ax_hist.set_title(f'{var} - Distribution (Differences)', fontsize=10, fontweight='bold')
                ax_hist.set_xlabel('Difference', fontsize=9)
                ax_hist.set_ylabel('Density', fontsize=9)
                ax_hist.legend()
                
                # Add normality test results if available
                if stats_results and var in stats_results and 'normality' in stats_results[var]:
                    norm_info = stats_results[var]['normality']
                    p_diff = norm_info['shapiro_p_diff']
                    
                    # Add text annotation
                    text = f"Shapiro-Wilk p = {p_diff:.3f}"
                    color = self.colors['success'] if p_diff > 0.05 else self.colors['error']
                    ax_hist.text(0.05, 0.95, text, transform=ax_hist.transAxes,
                               fontsize=8, verticalalignment='top', color=color,
                               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.suptitle(title, fontsize=14, fontweight='bold', y=0.96)
        plt.tight_layout()
        plt.subplots_adjust(top=0.90)  # Add more padding between title and subplots
        
        return fig
    
    def create_correlation_plot(self, df: pd.DataFrame, 
                              target_vars: List[str], 
                              predictor_vars: List[str],
                              title: str = "Correlation Analysis") -> plt.Figure:
        """
        Create publication-ready correlation plots following journal standards.
        
        Args:
            df (pd.DataFrame): Dataframe with target and predictor variables
            target_vars (List[str]): Target variables
            predictor_vars (List[str]): Predictor variables
            title (str): Plot title
            
        Returns:
            plt.Figure: Publication-ready figure
        """
        self.setup_publication_style()
        
        # Calculate number of subplots needed
        n_targets = len([var for var in target_vars if var in df.columns])
        n_predictors = len([var for var in predictor_vars if var in df.columns])
        
        if n_targets == 0 or n_predictors == 0:
            raise ValueError("No valid target or predictor variables found")
        
        # Calculate optimal figure size with better spacing
        fig_width = max(4.5 * n_predictors, 12)
        fig_height = max(4.5 * n_targets, 10)
        
        fig, axes = plt.subplots(n_targets, n_predictors, 
                                figsize=(fig_width, fig_height), dpi=self.dpi)
        
        if n_targets == 1 and n_predictors == 1:
            axes = np.array([[axes]])
        elif n_targets == 1:
            axes = axes.reshape(1, -1)
        elif n_predictors == 1:
            axes = axes.reshape(-1, 1)
        
        plot_count = 0
        
        for i, target in enumerate(target_vars):
            if target not in df.columns:
                continue
                
            for j, predictor in enumerate(predictor_vars):
                if predictor not in df.columns:
                    continue
                
                ax = axes[i, j]
                
                # Remove missing values
                valid_data = df[[target, predictor]].dropna()
                
                if len(valid_data) < 3:
                    ax.text(0.5, 0.5, 'Insufficient data', 
                           ha='center', va='center', transform=ax.transAxes,
                           fontsize=12, color=self.colors['primary'], fontweight='bold')
                    continue
                
                # Create scatter plot with professional styling
                ax.scatter(valid_data[predictor], valid_data[target], 
                          alpha=0.7, s=60, color=self.colors['secondary'],
                          edgecolors='white', linewidth=0.5, zorder=2)
                
                # Add trend line with professional styling
                z = np.polyfit(valid_data[predictor], valid_data[target], 1)
                p = np.poly1d(z)
                ax.plot(valid_data[predictor], p(valid_data[predictor]), 
                       color=self.colors['accent'], alpha=0.8, linewidth=2,
                       linestyle='--', zorder=1)
                
                # Calculate and display correlation
                correlation, p_value = np.corrcoef(valid_data[predictor], valid_data[target])[0, 1], 0
                try:
                    from scipy.stats import pearsonr
                    correlation, p_value = pearsonr(valid_data[predictor], valid_data[target])
                except:
                    pass
                
                # Add correlation text with professional styling
                sig_text = "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                sig_color = self.colors['error'] if p_value < 0.05 else self.colors['primary']
                
                corr_text = f'r = {correlation:.3f}{sig_text}\np = {p_value:.3f}'
                ax.text(0.05, 0.95, corr_text, transform=ax.transAxes, 
                       verticalalignment='top', fontsize=10, color=sig_color, fontweight='bold',
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='white', 
                                alpha=0.95, edgecolor=self.colors['neutral'], 
                                linewidth=1))
                
                # Customize plot with professional styling
                ax.set_xlabel(predictor.replace('_', ' ').title(), 
                            fontsize=12, fontweight='bold', color=self.colors['primary'])
                ax.set_ylabel(target.replace('_', ' ').title(), 
                            fontsize=12, fontweight='bold', color=self.colors['primary'])
                
                # Set tick parameters
                ax.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
                
                # Add grid for better readability
                ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
                ax.set_axisbelow(True)
                
                # Remove top and right spines for cleaner look
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_linewidth(1.2)
                ax.spines['bottom'].set_linewidth(1.2)
                
                plot_count += 1
        
        # Add overall title with professional styling
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=0.95)
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.88)
        
        return fig
    
    def create_enhanced_correlation_plot(self, df: pd.DataFrame, 
                                       target_vars: List[str], 
                                       predictor_vars: List[str],
                                       title: str = "Enhanced Correlation Analysis") -> plt.Figure:
        """
        Create comprehensive correlation plots showing all three conditions on the same subplot.
        
        This function creates correlation plots where each subplot shows the relationship
        between a target variable and predictor variable for all three conditions
        (ernie, mapped, optimized) with different colors and markers, including
        correlation coefficients and p-values in the legend.
        
        Args:
            df (pd.DataFrame): Dataframe with target, predictor variables, and 'condition' column
            target_vars (List[str]): Target variables
            predictor_vars (List[str]): Predictor variables
            title (str): Plot title
            
        Returns:
            plt.Figure: Publication-ready figure with enhanced correlation plots
        """
        self.setup_publication_style()
        
        # Check if condition column exists
        if 'condition' not in df.columns:
            raise ValueError("Dataframe must contain 'condition' column for enhanced correlation plot")
        
        # Calculate number of subplots needed
        n_targets = len([var for var in target_vars if var in df.columns])
        n_predictors = len([var for var in predictor_vars if var in df.columns])
        
        if n_targets == 0 or n_predictors == 0:
            raise ValueError("No valid target or predictor variables found")
        
        # Calculate optimal figure size with better spacing
        fig_width = max(4 * n_predictors, 12)
        fig_height = max(4 * n_targets, 10)
        
        fig, axes = plt.subplots(n_targets, n_predictors, 
                                figsize=(fig_width, fig_height), dpi=self.dpi)
        
        if n_targets == 1 and n_predictors == 1:
            axes = np.array([[axes]])
        elif n_targets == 1:
            axes = axes.reshape(1, -1)
        elif n_predictors == 1:
            axes = axes.reshape(-1, 1)
        
        # Colors for different mapping types
        mapping_colors = {
            'ernie': self.condition_colors['ernie'],
            'mapped': self.condition_colors['mapped'],
            'optimized': self.condition_colors['optimized']
        }
        
        for i, target in enumerate(target_vars):
            if target not in df.columns:
                continue
                
            for j, predictor in enumerate(predictor_vars):
                if predictor not in df.columns:
                    continue
                
                ax = axes[i, j]
                
                # Plot correlations for each mapping type
                for condition in ['ernie', 'mapped', 'optimized']:
                    condition_data = df[df['condition'] == condition]
                    valid_data = condition_data[[target, predictor]].dropna()
                    
                    if len(valid_data) >= 3:
                        # Calculate correlation
                        try:
                            from scipy.stats import pearsonr
                            correlation, p_value = pearsonr(valid_data[predictor], valid_data[target])
                            
                            # Create legend label with r and p-value
                            sig_text = "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                            legend_label = f'{condition.upper()} (r={correlation:.3f}{sig_text}, p={p_value:.3f})'
                            
                            # Create scatter plot
                            ax.scatter(valid_data[predictor], valid_data[target], 
                                     alpha=0.7, s=40, color=mapping_colors[condition],
                                     edgecolors='white', linewidth=0.5, zorder=2,
                                     label=legend_label)
                            
                            # Add trend line
                            z = np.polyfit(valid_data[predictor], valid_data[target], 1)
                            p = np.poly1d(z)
                            ax.plot(valid_data[predictor], p(valid_data[predictor]), 
                                   color=mapping_colors[condition], alpha=0.8, 
                                   linewidth=1.5, linestyle='--', zorder=1)
                        except:
                            # Fallback if pearsonr fails
                            ax.scatter(valid_data[predictor], valid_data[target], 
                                     alpha=0.7, s=40, color=mapping_colors[condition],
                                     edgecolors='white', linewidth=0.5, zorder=2,
                                     label=f'{condition.upper()}')
                            
                            # Add trend line
                            z = np.polyfit(valid_data[predictor], valid_data[target], 1)
                            p = np.poly1d(z)
                            ax.plot(valid_data[predictor], p(valid_data[predictor]), 
                                   color=mapping_colors[condition], alpha=0.8, 
                                   linewidth=1.5, linestyle='--', zorder=1)
                
                # Customize plot
                ax.set_xlabel(predictor.replace('_', ' ').title(), 
                            fontsize=12, fontweight='bold', color=self.colors['primary'])
                ax.set_ylabel(target.replace('_', ' ').title(), 
                            fontsize=12, fontweight='bold', color=self.colors['primary'])
                
                # Add grid and styling
                ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
                ax.set_axisbelow(True)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_linewidth(1.2)
                ax.spines['bottom'].set_linewidth(1.2)
                
                ax.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
                
                # Add legend to all plots
                ax.legend(fontsize=8, frameon=False, loc='upper left', bbox_to_anchor=(0, 1.02))
        
        # Add overall title
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=1.05)
        
        # Adjust layout to make room for legends
        plt.tight_layout()
        plt.subplots_adjust(top=0.93, hspace=0.4, wspace=0.3)
        
        return fig
    
    def create_regression_plot(self, df: pd.DataFrame, 
                             target_var: str, 
                             predictor_vars: List[str],
                             title: str = "Multiple Regression Analysis") -> plt.Figure:
        """
        Create publication-ready regression plots following journal standards.
        
        Args:
            df (pd.DataFrame): Dataframe with target and predictor variables
            target_var (str): Target variable
            predictor_vars (List[str]): Predictor variables
            title (str): Plot title
            
        Returns:
            plt.Figure: Publication-ready figure
        """
        self.setup_publication_style()
        
        # Prepare data
        valid_predictors = [var for var in predictor_vars if var in df.columns]
        
        if target_var not in df.columns or not valid_predictors:
            raise ValueError("Invalid target or predictor variables")
        
        # Remove missing values
        analysis_data = df[[target_var] + valid_predictors].dropna()
        
        if len(analysis_data) < len(valid_predictors) + 2:
            raise ValueError("Insufficient data for regression analysis")
        
        # Create figure with subplots using professional layout
        fig = plt.figure(figsize=(16, 12), dpi=self.dpi)
        gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1],
                             hspace=0.4, wspace=0.4)
        
        # Panel A: Actual vs Predicted
        ax0 = fig.add_subplot(gs[0, 0])
        
        # Fit regression model
        from statsmodels.api import OLS, add_constant
        X = add_constant(analysis_data[valid_predictors])
        y = analysis_data[target_var]
        model = OLS(y, X).fit()
        y_pred = model.predict(X)
        
        # Plot actual vs predicted with professional styling
        ax0.scatter(y, y_pred, alpha=0.7, s=40, color=self.colors['secondary'],
                   edgecolors='white', linewidth=0.5, zorder=2)
        ax0.plot([y.min(), y.max()], [y.min(), y.max()], 
                color=self.colors['accent'], alpha=0.8, linewidth=2,
                linestyle='--', zorder=1)
        ax0.set_xlabel('Actual Values (V/m)', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax0.set_ylabel('Predicted Values (V/m)', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax0.set_title(f'A. Actual vs Predicted\nR² = {model.rsquared:.3f}', 
                     fontsize=13, fontweight='bold', color=self.colors['primary'])
        ax0.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
        ax0.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax0.set_axisbelow(True)
        ax0.spines['top'].set_visible(False)
        ax0.spines['right'].set_visible(False)
        ax0.spines['left'].set_linewidth(1.2)
        ax0.spines['bottom'].set_linewidth(1.2)
        
        # Panel B: Residuals vs Predicted
        ax1 = fig.add_subplot(gs[0, 1])
        residuals = y - y_pred
        ax1.scatter(y_pred, residuals, alpha=0.7, s=40, color=self.colors['tertiary'],
                   edgecolors='white', linewidth=0.5, zorder=2)
        ax1.axhline(y=0, color=self.colors['accent'], linestyle='--', 
                   alpha=0.8, linewidth=2, zorder=1)
        ax1.set_xlabel('Predicted Values (V/m)', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax1.set_ylabel('Residuals (V/m)', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax1.set_title('B. Residuals vs Predicted', fontsize=13, fontweight='bold',
                     color=self.colors['primary'])
        ax1.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
        ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax1.set_axisbelow(True)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.spines['left'].set_linewidth(1.2)
        ax1.spines['bottom'].set_linewidth(1.2)
        
        # Panel C: Coefficient plot
        ax2 = fig.add_subplot(gs[1, :])
        
        # Extract coefficients and p-values
        coefs = model.params[1:]  # Exclude intercept
        p_vals = model.pvalues[1:]
        
        # Create coefficient plot with professional styling
        y_pos = np.arange(len(coefs))
        colors = [self.colors['error'] if p < 0.05 else self.colors['neutral'] for p in p_vals]
        
        bars = ax2.barh(y_pos, coefs, color=colors, alpha=0.8, height=0.6,
                       edgecolor=self.colors['primary'], linewidth=0.5)
        
        # Add significance indicators and values with professional styling
        for i, (coef, p_val) in enumerate(zip(coefs, p_vals)):
            sig_text = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
            p_text = f"p = {p_val:.3f}"
            text_color = self.colors['error'] if p_val < 0.05 else self.colors['primary']
            
            # Position text based on coefficient sign
            if coef >= 0:
                ax2.text(coef + 0.0001, i, f"{sig_text}\n{p_text}", 
                        va='center', ha='left', fontsize=7, color=text_color)
            else:
                ax2.text(coef - 0.0001, i, f"{sig_text}\n{p_text}", 
                        va='center', ha='right', fontsize=7, color=text_color)
        
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels([var.replace('_', ' ').title() for var in valid_predictors],
                           fontsize=10, fontweight='bold', color=self.colors['primary'])
        ax2.set_xlabel('Coefficient Value', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax2.set_title('C. Regression Coefficients', fontsize=13, fontweight='bold',
                     color=self.colors['primary'])
        ax2.axvline(x=0, color=self.colors['primary'], linestyle='-', 
                   alpha=0.5, linewidth=1)
        ax2.tick_params(axis='x', labelsize=10, color=self.colors['primary'])
        ax2.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax2.set_axisbelow(True)
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_linewidth(1.2)
        ax2.spines['bottom'].set_linewidth(1.2)
        
        # Add model summary text with professional styling
        model_text = f"Model: R² = {model.rsquared:.3f}, F = {model.fvalue:.2f}, p = {model.f_pvalue:.3f}"
        fig.text(0.5, 0.02, model_text, ha='center', fontsize=10, 
                color=self.colors['primary'], style='italic', fontweight='bold')
        
        # Add overall title - positioned higher
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=1.08)
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.1, top=0.9)
        
        return fig
    
    def create_comprehensive_regression_plot(self, df: pd.DataFrame, 
                                           target_var: str,
                                           predictor_vars: List[str],
                                           title: str = "Comprehensive Regression Analysis") -> plt.Figure:
        """
        Create comprehensive regression comparison plot across all three conditions.
        
        This function creates a two-panel plot showing:
        - Panel A: R² comparison across all mapping types
        - Panel B: Regression coefficient comparison across all mapping types
        
        Args:
            df (pd.DataFrame): Dataframe with target, predictor variables, and 'condition' column
            target_var (str): Target variable for regression
            predictor_vars (List[str]): Predictor variables
            title (str): Plot title
            
        Returns:
            plt.Figure: Publication-ready figure with comprehensive regression analysis
        """
        self.setup_publication_style()
        
        # Check if condition column exists
        if 'condition' not in df.columns:
            raise ValueError("Dataframe must contain 'condition' column for comprehensive regression plot")
        
        # Colors for different mapping types
        mapping_colors = {
            'ernie': self.condition_colors['ernie'],
            'mapped': self.condition_colors['mapped'],
            'optimized': self.condition_colors['optimized']
        }
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6), dpi=self.dpi)
        
        # Panel A: R² comparison
        r_squared_values = []
        mapping_labels = []
        
        for condition in ['ernie', 'mapped', 'optimized']:
            condition_data = df[df['condition'] == condition]
            valid_data = condition_data[[target_var] + predictor_vars].dropna()
            
            if len(valid_data) >= len(predictor_vars) + 2:
                # Fit regression model
                try:
                    from statsmodels.api import OLS, add_constant
                    X = add_constant(valid_data[predictor_vars])
                    y = valid_data[target_var]
                    model = OLS(y, X).fit()
                    
                    r_squared_values.append(model.rsquared)
                    mapping_labels.append(condition.upper())
                except:
                    # Fallback if regression fails
                    r_squared_values.append(0.0)
                    mapping_labels.append(condition.upper())
        
        # Plot R² comparison
        if r_squared_values:
            bars = ax1.bar(mapping_labels, r_squared_values, 
                          color=[mapping_colors[m.lower()] for m in mapping_labels],
                          alpha=0.8, edgecolor=self.colors['primary'], linewidth=1.2)
            
            # Add R² values on bars
            for bar, r2 in zip(bars, r_squared_values):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                        f'{r2:.3f}', ha='center', va='bottom', fontsize=12, fontweight='bold')
        
        ax1.set_ylabel('R²', fontsize=12, fontweight='bold', color=self.colors['primary'])
        ax1.set_title('A. Model Fit Comparison', fontsize=13, fontweight='bold',
                      color=self.colors['primary'])
        ax1.tick_params(axis='both', labelsize=10, color=self.colors['primary'])
        ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax1.set_axisbelow(True)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.spines['left'].set_linewidth(1.2)
        ax1.spines['bottom'].set_linewidth(1.2)
        
        # Panel B: Coefficient comparison
        all_coefficients = []
        all_predictors = []
        all_mapping_types = []
        
        for condition in ['ernie', 'mapped', 'optimized']:
            condition_data = df[df['condition'] == condition]
            valid_data = condition_data[[target_var] + predictor_vars].dropna()
            
            if len(valid_data) >= len(predictor_vars) + 2:
                # Fit regression model
                try:
                    from statsmodels.api import OLS, add_constant
                    X = add_constant(valid_data[predictor_vars])
                    y = valid_data[target_var]
                    model = OLS(y, X).fit()
                    
                    # Extract coefficients (excluding intercept)
                    coefs = model.params[1:]
                    p_vals = model.pvalues[1:]
                    
                    for pred, coef, p_val in zip(predictor_vars, coefs, p_vals):
                        all_coefficients.append(coef)
                        all_predictors.append(pred.replace('_', ' ').title())
                        all_mapping_types.append(condition.upper())
                except:
                    # Fallback if regression fails
                    for pred in predictor_vars:
                        all_coefficients.append(0.0)
                        all_predictors.append(pred.replace('_', ' ').title())
                        all_mapping_types.append(condition.upper())
        
        # Create coefficient comparison plot
        if all_coefficients:
            x_pos = np.arange(len(all_coefficients))
            colors = [mapping_colors[m.lower()] for m in all_mapping_types]
            
            bars = ax2.bar(x_pos, all_coefficients, color=colors, alpha=0.8,
                          edgecolor=self.colors['primary'], linewidth=1.2)
            
            # Add coefficient values
            for bar, coef in zip(bars, all_coefficients):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height + (0.001 if height >= 0 else -0.001),
                        f'{coef:.4f}', ha='center', va='bottom' if height >= 0 else 'top', 
                        fontsize=8, fontweight='bold')
            
            ax2.set_xticks(x_pos)
            ax2.set_xticklabels([f'{pred}\n({m})' for pred, m in zip(all_predictors, all_mapping_types)],
                               rotation=45, fontsize=9, color=self.colors['primary'])
        
        ax2.set_ylabel('Coefficient Value', fontsize=12, fontweight='bold', 
                      color=self.colors['primary'])
        ax2.set_title('B. Regression Coefficients', fontsize=13, fontweight='bold',
                      color=self.colors['primary'])
        ax2.axhline(y=0, color=self.colors['primary'], linestyle='-', 
                   alpha=0.5, linewidth=1)
        ax2.tick_params(axis='y', labelsize=10, color=self.colors['primary'])
        ax2.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax2.set_axisbelow(True)
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_linewidth(1.2)
        ax2.spines['bottom'].set_linewidth(1.2)
        
        # Add overall title
        fig.suptitle(title, fontsize=16, fontweight='bold', 
                    color=self.colors['primary'], y=1.02)
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.89)
        
        return fig
    
    def create_summary_plot(self, results: Dict, analysis_type: str,
                          target: str, optimization_type: str) -> plt.Figure:
        """
        Create a summary plot showing key results for any analysis type.
        
        Args:
            results (Dict): Analysis results
            analysis_type (str): Type of analysis ('Q1', 'Q2', or 'Q3')
            target (str): Target region
            optimization_type (str): Optimization type
            
        Returns:
            plt.Figure: Summary figure
        """
        self.setup_publication_style()
        
        if analysis_type in ['Q1', 'Q2']:
            return self._create_comparison_summary_plot(results, analysis_type, target, optimization_type)
        elif analysis_type == 'Q3':
            return self._create_demographics_summary_plot(results, target, optimization_type)
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
    
    def _create_comparison_summary_plot(self, results: Dict, analysis_type: str,
                                      target: str, optimization_type: str) -> plt.Figure:
        """Create summary plot for Q1 and Q2 analyses with professional styling."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), dpi=self.dpi)
        
        # Extract data
        variables = list(results['comparison_results'].keys())
        p_values = [results['comparison_results'][var]['p_value'] for var in variables]
        effect_sizes = [results['comparison_results'][var]['cohens_d'] for var in variables]
        significant = [results['comparison_results'][var]['significant'] for var in variables]
        
        # Plot 1: P-values with professional styling
        colors = [self.colors['error'] if sig else self.colors['neutral'] for sig in significant]
        bars1 = ax1.bar(variables, p_values, color=colors, alpha=0.8,
                       edgecolor=self.colors['primary'], linewidth=0.5)
        ax1.axhline(y=0.05, color=self.colors['error'], linestyle='--', 
                   alpha=0.8, linewidth=2, label='α = 0.05')
        ax1.set_ylabel('P-value', fontsize=8, color=self.colors['primary'])
        ax1.set_title('Statistical Significance', fontsize=9, fontweight='bold',
                     color=self.colors['primary'])
        ax1.set_ylim(0, 1)
        ax1.legend(fontsize=7, frameon=False)
        ax1.tick_params(axis='both', labelsize=7, color=self.colors['primary'])
        ax1.grid(False)
        
        # Plot 2: Effect sizes with professional styling
        colors = [self.colors['error'] if sig else self.colors['neutral'] for sig in significant]
        bars2 = ax2.bar(variables, effect_sizes, color=colors, alpha=0.8,
                       edgecolor=self.colors['primary'], linewidth=0.5)
        ax2.set_ylabel("Cohen's d", fontsize=8, color=self.colors['primary'])
        ax2.set_title('Effect Sizes', fontsize=9, fontweight='bold',
                     color=self.colors['primary'])
        ax2.axhline(y=0, color=self.colors['primary'], linestyle='-', 
                   alpha=0.5, linewidth=1)
        ax2.tick_params(axis='both', labelsize=7, color=self.colors['primary'])
        ax2.grid(False)
        
        # Add significance indicators with professional styling
        for i, sig in enumerate(significant):
            if sig:
                ax1.text(i, p_values[i] + 0.02, '*', ha='center', va='bottom', 
                        fontsize=14, color=self.colors['error'], fontweight='bold')
                ax2.text(i, effect_sizes[i] + (0.02 if effect_sizes[i] >= 0 else -0.02), '*', 
                        ha='center', va='bottom' if effect_sizes[i] >= 0 else 'top', 
                        fontsize=14, color=self.colors['error'], fontweight='bold')
        
        # Add overall title
        fig.suptitle(f'{analysis_type} Analysis: {target} ({optimization_type})', 
                    fontsize=10, fontweight='bold', color=self.colors['primary'])
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.9)
        
        return fig
    
    def _create_demographics_summary_plot(self, results: Dict, 
                                        target: str, optimization_type: str) -> plt.Figure:
        """Create summary plot for Q3 analysis with professional styling."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), dpi=self.dpi)
        
        # Extract correlation data
        if 'correlation_results' in results:
            corr_data = results['correlation_results']
            
            # Prepare data for heatmap
            target_vars = list(corr_data.keys())
            predictor_vars = list(corr_data[target_vars[0]].keys()) if target_vars else []
            
            corr_matrix = np.zeros((len(target_vars), len(predictor_vars)))
            p_matrix = np.zeros((len(target_vars), len(predictor_vars)))
            
            for i, target_var in enumerate(target_vars):
                for j, predictor in enumerate(predictor_vars):
                    if predictor in corr_data[target_var]:
                        corr_matrix[i, j] = corr_data[target_var][predictor]['correlation']
                        p_matrix[i, j] = corr_data[target_var][predictor]['p_value']
            
            # Plot 1: Correlation heatmap with professional styling
            im1 = ax1.imshow(corr_matrix, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
            ax1.set_xticks(range(len(predictor_vars)))
            ax1.set_yticks(range(len(target_vars)))
            ax1.set_xticklabels([var.replace('_', ' ').title() for var in predictor_vars], 
                               rotation=45, fontsize=7, color=self.colors['primary'])
            ax1.set_yticklabels([var.replace('_', ' ').title() for var in target_vars],
                               fontsize=7, color=self.colors['primary'])
            ax1.set_title('Correlation Matrix', fontsize=9, fontweight='bold',
                         color=self.colors['primary'])
            
            # Add correlation values with professional styling
            for i in range(len(target_vars)):
                for j in range(len(predictor_vars)):
                    text_color = 'white' if abs(corr_matrix[i, j]) > 0.5 else 'black'
                    ax1.text(j, i, f'{corr_matrix[i, j]:.2f}',
                            ha="center", va="center", color=text_color, 
                            fontweight='bold', fontsize=7)
            
            # Add colorbar with professional styling
            cbar = plt.colorbar(im1, ax=ax1)
            cbar.ax.tick_params(labelsize=7, color=self.colors['primary'])
        
        # Plot 2: Regression results with professional styling
        if 'regression_results' in results and results['regression_results']:
            reg_results = results['regression_results']
            
            # Extract coefficients and p-values
            coefs = list(reg_results['coefficients'].values())[1:]  # Exclude intercept
            p_vals = list(reg_results['p_values'].values())[1:]
            var_names = list(reg_results['coefficients'].keys())[1:]
            
            colors = [self.colors['error'] if p < 0.05 else self.colors['neutral'] for p in p_vals]
            bars = ax2.bar(range(len(coefs)), coefs, color=colors, alpha=0.8,
                          edgecolor=self.colors['primary'], linewidth=0.5)
            
            ax2.set_xticks(range(len(coefs)))
            ax2.set_xticklabels([var.replace('_', ' ').title() for var in var_names], 
                               rotation=45, fontsize=7, color=self.colors['primary'])
            ax2.set_ylabel('Coefficient Value', fontsize=8, color=self.colors['primary'])
            ax2.set_title(f'Regression Coefficients\nR² = {reg_results["r_squared"]:.3f}', 
                         fontsize=9, fontweight='bold', color=self.colors['primary'])
            ax2.axhline(y=0, color=self.colors['primary'], linestyle='-', 
                       alpha=0.5, linewidth=1)
            ax2.tick_params(axis='y', labelsize=7, color=self.colors['primary'])
            ax2.grid(False)
        
        # Add overall title
        fig.suptitle(f'Q3 Analysis: {target} ({optimization_type})', 
                    fontsize=10, fontweight='bold', color=self.colors['primary'])
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.9)
        
        return fig


def create_q1_plots(df: pd.DataFrame, target: str, optimization_type: str,
                   save_path: str = None, stats_results: Dict = None) -> List[plt.Figure]:
    """
    Create all plots for Q1 (Individualization) analysis with professional styling.
    
    Args:
        df (pd.DataFrame): Comparison dataset
        target (str): Target region
        optimization_type (str): Optimization type
        save_path (str): Path to save figures (optional)
        stats_results (Dict): Statistical results from analysis
        
    Returns:
        List[plt.Figure]: List of created figures
    """
    plotter = PublicationPlotter()
    figures = []
    
    # Create paired comparison plot
    fig1 = plotter.create_paired_comparison_plot(
        df, title=f"Q1: Individualization Effects - {target} ({optimization_type})",
        stats_results=stats_results
    )
    figures.append(fig1)
    
    if save_path:
        fig1.savefig(f"{save_path}/q1_paired_comparison_{target}_{optimization_type}.png", 
                    dpi=300, bbox_inches='tight', facecolor='white')
    
    return figures


def create_q2_plots(df: pd.DataFrame, target: str, optimization_type: str,
                   save_path: str = None, stats_results: Dict = None) -> List[plt.Figure]:
    """
    Create all plots for Q2 (Mapping) analysis with professional styling.
    
    Args:
        df (pd.DataFrame): Comparison dataset
        target (str): Target region
        optimization_type (str): Optimization type
        save_path (str): Path to save figures (optional)
        stats_results (Dict): Statistical results from analysis
        
    Returns:
        List[plt.Figure]: List of created figures
    """
    plotter = PublicationPlotter()
    figures = []
    
    # Create paired comparison plot
    fig1 = plotter.create_paired_comparison_plot(
        df, title=f"Q2: Mapping Effects - {target} ({optimization_type})",
        stats_results=stats_results
    )
    figures.append(fig1)
    
    if save_path:
        fig1.savefig(f"{save_path}/q2_paired_comparison_{target}_{optimization_type}.png", 
                    dpi=300, bbox_inches='tight', facecolor='white')
    
    return figures


def create_q3_plots(df: pd.DataFrame, target: str, optimization_type: str,
                   save_path: str = None) -> List[plt.Figure]:
    """
    Create all plots for Q3 (Demographics) analysis with professional styling.
    
    Args:
        df (pd.DataFrame): Dataset with demographics
        target (str): Target region
        optimization_type (str): Optimization type
        save_path (str): Path to save figures (optional)
        
    Returns:
        List[plt.Figure]: List of created figures
    """
    plotter = PublicationPlotter()
    figures = []
    
    # Define variables
    target_vars = ['ROI_Mean', 'ROI_Max', 'Normal_Mean', 'Normal_Max']
    predictor_vars = ['age', 'bone_volume', 'bone_mean_thick']  # Demographics columns
    
    # Create correlation plot
    fig1 = plotter.create_correlation_plot(
        df, target_vars, predictor_vars,
        title=f"Q3: Demographic Correlations - {target} ({optimization_type})"
    )
    figures.append(fig1)
    
    # Create regression plot (only if we have sufficient data)
    try:
        if len(df.dropna(subset=predictor_vars)) >= len(predictor_vars) + 2:
            fig2 = plotter.create_regression_plot(
                df, 'ROI_Mean', predictor_vars,
                title=f"Q3: Multiple Regression - {target} ({optimization_type})"
            )
            figures.append(fig2)
            
            if save_path:
                fig2.savefig(f"{save_path}/q3_regression_{target}_{optimization_type}.png", 
                            dpi=300, bbox_inches='tight', facecolor='white')
    except Exception as e:
        print(f"   Note: Regression plot not created due to insufficient data: {e}")
    
    if save_path:
        fig1.savefig(f"{save_path}/q3_correlations_{target}_{optimization_type}.png", 
                    dpi=300, bbox_inches='tight', facecolor='white')
    
    return figures


def create_q3_plots_enhanced(df: pd.DataFrame, target: str, optimization_type: str,
                           save_path: str = None) -> List[plt.Figure]:
    """
    Create enhanced plots for Q3 (Demographics) analysis with all three conditions.
    
    This function creates correlation plots showing the relationship between
    demographic factors and electric field measures for all three conditions
    (ernie, mapped, optimized) on the same subplot for better comparison.
    
    Args:
        df (pd.DataFrame): Dataset with demographics and 'condition' column
        target (str): Target region
        optimization_type (str): Optimization type
        save_path (str): Path to save figures (optional)
        
    Returns:
        List[plt.Figure]: List of created figures
    """
    plotter = PublicationPlotter()
    figures = []
    
    # Define variables
    target_vars = ['ROI_Mean', 'ROI_Max', 'Normal_Mean', 'Normal_Max']
    predictor_vars = ['age', 'bone_volume', 'bone_mean_thick']  # Demographics columns
    
    # Create enhanced correlation plot
    fig1 = plotter.create_enhanced_correlation_plot(
        df, target_vars, predictor_vars,
        title=f"Q3: Enhanced Demographic Correlations - {target} ({optimization_type})"
    )
    figures.append(fig1)
    
    # Create comprehensive regression plot (only if we have sufficient data)
    try:
        if len(df.dropna(subset=predictor_vars)) >= len(predictor_vars) + 2:
            fig2 = plotter.create_comprehensive_regression_plot(
                df, 'ROI_Mean', predictor_vars,
                title=f"Q3: Comprehensive Regression Analysis - {target} ({optimization_type})"
            )
            figures.append(fig2)
            
            if save_path:
                fig2.savefig(f"{save_path}/q3_comprehensive_regression_{target}_{optimization_type}.png", 
                            dpi=300, bbox_inches='tight', facecolor='white')
    except Exception as e:
        print(f"   Note: Comprehensive regression plot not created due to insufficient data: {e}")
    
    if save_path:
        fig1.savefig(f"{save_path}/q3_enhanced_correlations_{target}_{optimization_type}.png", 
                    dpi=300, bbox_inches='tight', facecolor='white')
    
    return figures


if __name__ == "__main__":
    # Example usage and testing
    print("Visualization Module for TI-Toolbox Research")
    print("Updated with Cell/Science/Nature publication standards")
    print("Available functions:")
    print("- create_q1_plots()")
    print("- create_q2_plots()")
    print("- create_q3_plots()")
    print("- PublicationPlotter class") 