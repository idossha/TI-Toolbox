#!/usr/bin/env python3
"""
Python replacement for MATLAB field-analysis scripts
Extracts field peaks, percentiles, and focality metrics from .msh files

Author: TI-toolbox Python Conversion
Replaces: process_mesh_files.m and process_mesh_files_new.m
"""

import os
import sys
import glob
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import meshio

matplotlib.use('Agg')  # Use non-interactive backend
from pathlib import Path

# Add utils directory to path for logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.logging_util import get_logger

class MeshFieldAnalyzer:
    def __init__(self, mesh_dir):
        self.mesh_dir = Path(mesh_dir)
        self.analysis_dir = self.mesh_dir / 'analysis'
        self.analysis_dir.mkdir(exist_ok=True)
        
        # Initialize logger following ex-search pattern
        self.logger = self._setup_logger()
        
        # Standard parameters (matching MATLAB defaults)
        self.percentiles = [95, 99, 99.9]
        self.focality_cutoffs = [50, 75, 90, 95]
        self.field_name = 'TImax'  # Default field to analyze (from your TI simulations)
        self.region_idx = 2  # Gray matter tetrahedra
    
    def _setup_logger(self):
        """Setup logger following ex-search pattern (same as simulator components)"""
        import time
        
        # Check if log file path is provided through environment variable (from GUI)
        shared_log_file = os.environ.get('TI_LOG_FILE')
        
        if shared_log_file:
            # Use shared log file and shared logger name for unified logging
            logger_name = 'Ex-Search'
            log_file = shared_log_file
            logger = get_logger(logger_name, log_file, overwrite=False)
        else:
            # CLI usage: create individual log file
            logger_name = 'MeshFieldAnalyzer'
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            log_file = f'mesh_field_analyzer_{time_stamp}.log'
            logger = get_logger(logger_name, log_file, overwrite=False)

        # Configure external loggers to use our logging setup (same as simulator)
        from logging_util import configure_external_loggers
        configure_external_loggers(['simnibs', 'mesh_io'], logger)
        
        return logger
        
    def process_all_meshes(self):
        """Process all .msh files in the directory"""
        mesh_files = list(self.mesh_dir.glob('*.msh'))
        
        if not mesh_files:
            self.logger.warning(f"No mesh files found in directory: {self.mesh_dir}")
            return
            
        self.logger.info(f"Found {len(mesh_files)} mesh files to process")
        
        # Initialize results storage
        csv_data = []
        summary_text = []
        
        for mesh_file in mesh_files:
            self.logger.info(f"Processing mesh file: {mesh_file.name}")
            try:
                results = self.analyze_mesh(mesh_file)
                if results:
                    csv_data.append(results)
                    summary_text.append(self.format_summary_text(mesh_file.name, results))
            except Exception as e:
                self.logger.error(f"Failed to process {mesh_file.name}: {str(e)}")
                continue
        
        # Save results
        if csv_data:
            self.save_summary_csv(csv_data)
            self.save_final_output_csv(csv_data)  # Create final output directly
            self.save_summary_txt(summary_text)
            self.logger.info(f"Analysis results saved to: {self.analysis_dir}")
        else:
            self.logger.warning("No results to save - all mesh processing failed")
    
    def analyze_mesh(self, mesh_file):
        """Analyze a single mesh file and extract field metrics"""
        try:
            # Load mesh using meshio
            mesh = meshio.read(mesh_file)
            # Find the field data
            field_data = self.extract_field_data(mesh)
            if field_data is None or (hasattr(field_data, '__len__') and len(field_data) == 0):
                self.logger.warning(f"No field data found in mesh file: {mesh_file.name}")
                return None
            
            # Extract regions (tetrahedra with specified region index)
            filtered_data, positions, element_sizes = self.filter_by_region(mesh, field_data)
            if len(filtered_data) == 0:
                self.logger.warning(f"No gray matter region data found in: {mesh_file.name}")
                return None
            
            # Calculate metrics
            results = self.calculate_field_metrics(filtered_data, positions, element_sizes)
            if results is None:
                self.logger.error(f"Failed to calculate field metrics for: {mesh_file.name}")
                return None
                
            results['filename'] = mesh_file.name
            
            # Generate visualization with volume weighting
            self.generate_histogram(mesh_file.name, filtered_data, element_sizes, positions)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to analyze mesh {mesh_file.name}: {str(e)}")
            return None
    
    def get_field_idx(self, mesh, field_name):
        """Find field index in mesh following SimNIBS pattern"""
        # Look in cell_data first (element data - tetrahedra)
        if hasattr(mesh, 'cell_data') and mesh.cell_data:
            # cell_data structure: {field_name: [data_list], ...}
            if field_name in mesh.cell_data:
                field_data = mesh.cell_data[field_name]
                return field_data, 'element'
        
        # Look in point_data (node data)
        if hasattr(mesh, 'point_data') and mesh.point_data:
            if isinstance(mesh.point_data, dict) and field_name in mesh.point_data:
                return mesh.point_data[field_name], 'node'
        
        # Try common field name variations
        field_variations = ['TImax', 'magnE', 'E.normal', 'TI_max', 'E_magn']
        for variant in field_variations:
            if hasattr(mesh, 'cell_data') and mesh.cell_data:
                if variant in mesh.cell_data:
                    self.field_name = variant
                    return mesh.cell_data[variant], 'element'
            
            if hasattr(mesh, 'point_data') and mesh.point_data:
                if isinstance(mesh.point_data, dict) and variant in mesh.point_data:
                    self.field_name = variant
                    return mesh.point_data[variant], 'node'
        
        return None, None
    
    def extract_field_data(self, mesh):
        """Extract field data from mesh following SimNIBS patterns"""
        field_data, data_type = self.get_field_idx(mesh, self.field_name)
        if field_data is not None:
            # Convert to numpy array for easier processing
            field_data = np.asarray(field_data)
            # Flatten if needed (handle shape like (1, N) -> (N,))
            if field_data.ndim > 1:
                field_data = field_data.flatten()
                
        return field_data
    
    def filter_by_region(self, mesh, field_data):
        """Filter data by region following SimNIBS pattern (mesh_extract_regions equivalent)"""
        # Find tetrahedra and their region tags
        tet_cells = None
        tet_regions = None
        
        for i, cell_block in enumerate(mesh.cells):
            if cell_block.type == 'tetra':
                tet_cells = cell_block.data
                
                # Look for region information (gmsh:physical tags)
                if hasattr(mesh, 'cell_data') and mesh.cell_data:
                    # Look for physical region tags - they're stored as lists in cell_data
                    if 'gmsh:physical' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['gmsh:physical'])
                        # Flatten if needed (handle shape like (1, N) -> (N,))
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                    elif 'Physical Names' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['Physical Names'])
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                    elif 'region' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['region'])
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                break
        
        if tet_cells is None:
            self.logger.warning("No tetrahedra found in mesh")
            return np.array([]), np.array([]).reshape(0,3), np.array([])
        
        # Filter by gray matter region (region_idx = 2)
        if tet_regions is not None:
            # Create mask for gray matter elements
            gray_matter_mask = tet_regions == self.region_idx
            gray_matter_tets = tet_cells[gray_matter_mask]
            
            if len(gray_matter_tets) == 0:
                self.logger.warning(f"No elements found for region {self.region_idx}")
                return np.array([]), np.array([]).reshape(0,3), np.array([])
            
            # Get field data for gray matter tetrahedra only
            if isinstance(field_data, np.ndarray) and len(field_data) == len(tet_cells):
                # Check that mask dimensions match field data dimensions
                if len(gray_matter_mask) != len(field_data):
                    self.logger.error(f"Mask length ({len(gray_matter_mask)}) does not match field data length ({len(field_data)})")
                    return np.array([]), np.array([]).reshape(0,3), np.array([])
                
                filtered_data = field_data[gray_matter_mask]
            else:
                self.logger.error(f"Field data length ({len(field_data)}) does not match tetrahedra count ({len(tet_cells)})")
                return np.array([]), np.array([]).reshape(0,3), np.array([])
            
            # Calculate tetrahedron centers (equivalent to mesh_get_tetrahedron_centers)
            element_centers = np.mean(mesh.points[gray_matter_tets], axis=1)
            
            # Calculate tetrahedron volumes (equivalent to mesh_get_tetrahedron_sizes)
            element_sizes = self.calculate_tetrahedron_volumes(mesh.points, gray_matter_tets)
            
        else:
            self.logger.warning("No region information found, using all tetrahedra")
            # Use all tetrahedra if no region information
            filtered_data = field_data
            element_centers = np.mean(mesh.points[tet_cells], axis=1)
            element_sizes = self.calculate_tetrahedron_volumes(mesh.points, tet_cells)
        
        # Ensure we return proper numpy arrays
        filtered_data = np.asarray(filtered_data).flatten()
        element_centers = np.asarray(element_centers)
        element_sizes = np.asarray(element_sizes)
        
        return filtered_data, element_centers, element_sizes
    
    def calculate_tetrahedron_volumes(self, points, tetrahedra):
        """Calculate volumes of tetrahedra"""
        if len(tetrahedra) == 0:
            return np.array([])
        
        # Get vertices of each tetrahedron
        v0 = points[tetrahedra[:, 0]]
        v1 = points[tetrahedra[:, 1]]
        v2 = points[tetrahedra[:, 2]]  
        v3 = points[tetrahedra[:, 3]]
        
        # Calculate volume using determinant formula
        # V = |det(v1-v0, v2-v0, v3-v0)| / 6
        a = v1 - v0
        b = v2 - v0
        c = v3 - v0
        
        volumes = np.abs(np.linalg.det(np.stack([a, b, c], axis=1))) / 6.0
        return volumes
    
    def calculate_field_metrics(self, data, positions, element_sizes):
        """Calculate field metrics matching MATLAB output"""
        # Remove NaN values
        valid_mask = ~np.isnan(data)
        data = data[valid_mask]
        positions = positions[valid_mask]
        element_sizes = element_sizes[valid_mask]
        
        if len(data) == 0:
            return None
        
        # Sort data and corresponding arrays
        sort_idx = np.argsort(data)
        data_sorted = data[sort_idx]
        positions_sorted = positions[sort_idx]
        element_sizes_sorted = element_sizes[sort_idx]
        
        # Calculate cumulative volumes (element sizes)
        cumulative_sizes = np.cumsum(element_sizes_sorted)
        total_size = cumulative_sizes[-1]
        normalized_cumulative = cumulative_sizes / total_size
        
        results = {
            'field_name': self.field_name,
            'region_idx': self.region_idx,
            'max_value': float(np.max(data)),
            'min_value': float(np.min(data)) if np.min(data) < 0 else None,
        }
        
        # Find maximum position
        max_idx = np.argmax(data)
        results['xyz_max'] = positions[max_idx].tolist()
        
        # Calculate percentiles and their positions
        percentile_values = []
        xyz_percentiles = []
        xyz_std_percentiles = []
        
        for percentile in self.percentiles:
            # Find index where cumulative size exceeds percentile
            threshold_idx = np.searchsorted(normalized_cumulative, percentile/100.0)
            if threshold_idx >= len(data_sorted):
                threshold_idx = len(data_sorted) - 1
            
            percentile_value = data_sorted[threshold_idx]
            percentile_values.append(float(percentile_value))
            
            # Calculate mean and std of positions for elements above this percentile
            above_threshold = data_sorted >= percentile_value
            if np.any(above_threshold):
                above_positions = positions_sorted[above_threshold]
                above_sizes = element_sizes_sorted[above_threshold]
                
                # Weighted mean position
                weighted_mean = np.average(above_positions, axis=0, weights=above_sizes)
                xyz_percentiles.append(weighted_mean.tolist())
                
                # Weighted standard deviation
                weighted_var = np.average((above_positions - weighted_mean)**2, axis=0, weights=above_sizes)
                xyz_std_percentiles.append(np.sqrt(weighted_var).tolist())
            else:
                xyz_percentiles.append([0, 0, 0])
                xyz_std_percentiles.append([0, 0, 0])
        
        results['percentile_values'] = percentile_values
        results['xyz_percentiles'] = xyz_percentiles
        results['xyz_std_percentiles'] = xyz_std_percentiles
        
        # Calculate focality (volume above thresholds)
        # Use 99.9 percentile as reference (index 2)
        if len(percentile_values) > 2:
            reference_value = percentile_values[2]  # 99.9 percentile
            focality_values = []
            
            for cutoff in self.focality_cutoffs:
                threshold = (cutoff / 100.0) * reference_value
                above_threshold = data >= threshold
                volume = np.sum(element_sizes[above_threshold]) if np.any(above_threshold) else 0.0
                # Convert from mm³ to cm³
                focality_values.append(float(volume / 1000.0))
            
            results['focality_values'] = focality_values
        else:
            results['focality_values'] = [0.0] * len(self.focality_cutoffs)
        
        return results
    
    def generate_histogram(self, filename, data, element_sizes=None, positions=None):
        """Generate enhanced histogram visualization with focality cutoffs and volume weighting"""
        try:
            # Check for valid data
            if len(data) == 0:
                self.logger.warning(f"No data to plot for histogram: {filename}")
                return
                
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Try to get ROI field value for indicator line
            roi_field_value = self.get_roi_field_value(filename)
            
            # Create volume-weighted histogram if element sizes are provided
            if element_sizes is not None and len(element_sizes) == len(data):
                # Create histogram with volume weighting (convert mm³ to cm³)
                weights = element_sizes / 1000.0  # Convert mm³ to cm³
                n, bins, patches = ax.hist(data, bins=100, weights=weights, alpha=0.7, 
                                         edgecolor='black', color='lightblue')
                ax.set_ylabel('Volume (cm³)')
                
                # Calculate focality cutoffs based on 99.9 percentile
                percentile_99_9 = np.percentile(data, 99.9)
                focality_thresholds = []
                focality_volumes = []
                
                for cutoff in self.focality_cutoffs:
                    threshold = (cutoff / 100.0) * percentile_99_9
                    focality_thresholds.append(threshold)
                    
                    # Calculate volume above this threshold (in cm³)
                    above_threshold = data >= threshold
                    volume = np.sum(element_sizes[above_threshold]) / 1000.0 if np.any(above_threshold) else 0.0  # Convert to cm³
                    focality_volumes.append(volume)
                
                # Add vertical red lines for focality cutoffs
                colors = ['red', 'darkred', 'crimson', 'maroon']
                lines_added = 0
                for i, (threshold, cutoff) in enumerate(zip(focality_thresholds, self.focality_cutoffs)):
                    if threshold <= np.max(data) and threshold >= np.min(data):  # Only draw line if it's within data range
                        color = colors[i % len(colors)]  # Cycle through colors if more cutoffs than colors
                        ax.axvline(x=threshold, color=color, linestyle='--', linewidth=2, alpha=0.8,
                                  label=f'{cutoff}% of 99.9%ile\n({threshold:.2f} V/m)\nVol: {focality_volumes[i]:.1f} cm³')
                        lines_added += 1
                
                # Add mean ROI field value indicator line (if available)
                if roi_field_value is not None and np.min(data) <= roi_field_value <= np.max(data):
                    ax.axvline(x=roi_field_value, color='green', linestyle='-', linewidth=3, alpha=0.9,
                              label=f'Mean ROI Field\n({roi_field_value:.2f} V/m)')
                    lines_added += 1
                
                # Add legend for all lines (only if lines were added)
                if lines_added > 0:
                    ax.legend(loc='upper right', bbox_to_anchor=(1.25, 1), 
                             frameon=True, fancybox=True, shadow=True)
                
            else:
                # Frequency histogram if no element sizes available
                ax.hist(data, bins=500, alpha=0.7, edgecolor='black', color='lightblue')
                ax.set_ylabel('Frequency')
                
                # Add ROI indicator for frequency plots
                if roi_field_value is not None and np.min(data) <= roi_field_value <= np.max(data):
                    ax.axvline(x=roi_field_value, color='green', linestyle='-', linewidth=3, alpha=0.9,
                              label=f'Mean ROI Field\n({roi_field_value:.2f} V/m)')
                    ax.legend(loc='upper right')
            
            ax.set_xlabel('Field Strength (V/m)')
            ax.set_title(f'Field Distribution with Focality Cutoffs\n{filename}', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Add statistics text box
            stats_text = f'Max: {np.max(data):.2f} V/m\n'
            stats_text += f'Mean: {np.mean(data):.2f} V/m\n'
            stats_text += f'99.9%ile: {np.percentile(data, 99.9):.2f} V/m\n'
            stats_text += f'Elements: {len(data):,}'
            
            if element_sizes is not None:
                total_volume = np.sum(element_sizes) / 1000.0  # Convert to cm³
                stats_text += f'\nTotal Vol: {total_volume:.1f} cm³'
            
            if roi_field_value is not None:
                stats_text += f'\nROI Field: {roi_field_value:.2f} V/m'
            
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            # Save histogram with tight layout
            base_name = Path(filename).stem
            hist_file = self.analysis_dir / f'{base_name}_histogram.png'
            plt.tight_layout()
            plt.savefig(hist_file, dpi=150, bbox_inches='tight')
            plt.close(fig)
            
        except Exception as e:
            self.logger.error(f"Failed to generate histogram for {filename}: {str(e)}")
    
    def get_roi_field_value(self, filename):
        """Get the ROI field value from the ROI analysis CSV file"""
        try:
            # Look for ROI CSV files in the parent directory structure
            # Pattern: /path/to/subject/m2m_XXX/ROIs/*_TImax.csv
            current_path = self.mesh_dir
            
            # Navigate up to find the subject directory
            while current_path.name != 'ex-search' and current_path.parent != current_path:
                current_path = current_path.parent
            
            if current_path.name == 'ex-search':
                subject_dir = current_path.parent
                m2m_dirs = list(subject_dir.glob('m2m_*'))
                
                if m2m_dirs:
                    roi_dir = m2m_dirs[0] / 'ROIs'
                    roi_csv_files = list(roi_dir.glob('*_TImax.csv'))
                    
                    if roi_csv_files:
                        # Read the first ROI CSV file
                        import pandas as pd
                        roi_df = pd.read_csv(roi_csv_files[0])
                        
                        # Get the mean field value (assuming TImax column exists)
                        if 'TImax' in roi_df.columns:
                            mean_roi_value = roi_df['TImax'].mean()
                            return mean_roi_value
                        else:
                            # Try other possible column names
                            for col in roi_df.columns:
                                if 'TI' in col.upper() or 'FIELD' in col.upper():
                                    mean_roi_value = roi_df[col].mean()
                                    return mean_roi_value
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Could not read ROI field value: {str(e)}")
            return None
    
    def save_summary_csv(self, results_list):
        """Save results to CSV matching MATLAB format"""
        csv_rows = []
        
        for results in results_list:
            row = {
                'FileName': results['filename'],
                'FieldName': results['field_name'],
                'RegionIndices': str(results['region_idx']),
                'MaxValue': results['max_value'],
            }
            
            # Add percentile values
            if len(results['percentile_values']) >= 3:
                row['PercentileValue_95'] = results['percentile_values'][0]
                row['PercentileValue_99'] = results['percentile_values'][1] 
                row['PercentileValue_99.9'] = results['percentile_values'][2]
            
            # Add focality values
            if len(results['focality_values']) >= 4:
                row['FocalityValue_50'] = results['focality_values'][0]
                row['FocalityValue_75'] = results['focality_values'][1]
                row['FocalityValue_90'] = results['focality_values'][2]
                row['FocalityValue_95'] = results['focality_values'][3]
            
            # Add XYZ coordinates
            row['XYZ_Max'] = str(results['xyz_max'])
            
            if len(results['xyz_percentiles']) >= 3:
                row['XYZ_Percentiles_95'] = str(results['xyz_percentiles'][0])
                row['XYZ_Percentiles_99'] = str(results['xyz_percentiles'][1])
                row['XYZ_Percentiles_99.9'] = str(results['xyz_percentiles'][2])
            
            if len(results['xyz_std_percentiles']) >= 3:
                row['XYZ_Std_Percentiles_95'] = str(results['xyz_std_percentiles'][0])
                row['XYZ_Std_Percentiles_99'] = str(results['xyz_std_percentiles'][1])
                row['XYZ_Std_Percentiles_99.9'] = str(results['xyz_std_percentiles'][2])
            
            csv_rows.append(row)
        
        # Create DataFrame and save
        df = pd.DataFrame(csv_rows)
        csv_file = self.analysis_dir / 'summary.csv'
        df.to_csv(csv_file, index=False)
        self.logger.info(f"Summary CSV saved to: {csv_file}")
    
    def save_final_output_csv(self, results_list):
        """Merge mesh analysis results with existing ROI data in final output CSV"""
        final_csv_file = self.analysis_dir / 'final_output.csv'
        
        # Check if ROI analyzer already created a CSV with ROI field data
        if final_csv_file.exists():
            self.logger.info("Loading existing final_output.csv from ROI analyzer")
            existing_df = pd.read_csv(final_csv_file)
            self.logger.info(f"Existing CSV has {len(existing_df)} rows with columns: {list(existing_df.columns)}")
        else:
            self.logger.warning("No existing final_output.csv found - creating new one")
            existing_df = pd.DataFrame()
        
        # Create mesh analysis data
        mesh_rows = []
        for results in results_list:
            # Convert mesh filename to user-friendly format
            # TI_field_O1_Fp1_and_T7_F7.msh -> O1_Fp1 <> T7_F7
            mesh_name = results['filename']
            mesh_clean = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
            
            row = {
                'Mesh': mesh_clean,
                'TImax': results['max_value'],
            }
            
            # Add percentile values
            if len(results['percentile_values']) >= 3:
                row['PercentileValue_95'] = results['percentile_values'][0]
                row['PercentileValue_99'] = results['percentile_values'][1] 
                row['PercentileValue_99.9'] = results['percentile_values'][2]
            
            # Add focality values
            if len(results['focality_values']) >= 4:
                row['FocalityValue_50'] = results['focality_values'][0]
                row['FocalityValue_75'] = results['focality_values'][1]
                row['FocalityValue_90'] = results['focality_values'][2]
                row['FocalityValue_95'] = results['focality_values'][3]
            
            # Add XYZ coordinates (formatted as comma-separated string)
            if results['xyz_max']:
                xyz_coords = results['xyz_max']
                row['XYZ_Max'] = f"{xyz_coords[0]:.2f},{xyz_coords[1]:.2f},{xyz_coords[2]:.2f}"
            
            mesh_rows.append(row)
        
        mesh_df = pd.DataFrame(mesh_rows)
        
        # Debug: Show what data we're working with
        self.logger.info(f"Mesh analysis data mesh names: {mesh_df['Mesh'].tolist()}")
        if not existing_df.empty:
            self.logger.info(f"Existing ROI data mesh names: {existing_df['Mesh'].tolist() if 'Mesh' in existing_df.columns else 'No Mesh column'}")
        
        # Merge with existing ROI data if available
        if not existing_df.empty and 'Mesh' in existing_df.columns:
            # Merge on 'Mesh' column to preserve ROI field data
            final_df = pd.merge(existing_df, mesh_df, on='Mesh', how='outer', suffixes=('_roi', '_mesh'))
            
            # Handle duplicate TImax columns (prefer mesh analysis values, but keep ROI TImax as separate column)
            if 'TImax_mesh' in final_df.columns:
                final_df['TImax_Brain'] = final_df['TImax_mesh']  # Rename to clarify this is brain-wide max
                final_df.drop(columns=['TImax_mesh'], inplace=True)
            
            # Handle ROI TImax columns
            if 'TImax_roi' in final_df.columns:
                final_df.drop(columns=['TImax_roi'], inplace=True)  # Remove duplicate, keep original TImax_ROI
            elif 'TImax' in existing_df.columns and 'TImax_ROI' not in final_df.columns:
                # Handle case where there's no suffix conflict and old naming
                final_df.rename(columns={'TImax': 'TImax_ROI'}, inplace=True)
            
            # Handle ROI TImean columns (should not have duplicates since mesh analyzer doesn't create TImean)
            if 'TImean_ROI_roi' in final_df.columns:
                final_df.rename(columns={'TImean_ROI_roi': 'TImean_ROI'}, inplace=True)
            
            self.logger.info(f"Successfully merged data - final shape: {final_df.shape}")
            self.logger.info(f"Final columns: {list(final_df.columns)}")
        else:
            # No existing data or no proper structure - use mesh data only
            final_df = mesh_df
            self.logger.info("Using mesh analysis data only (no valid ROI data found)")
        
        # Save merged data
        final_df.to_csv(final_csv_file, index=False)
        self.logger.info(f"Final output CSV saved to: {final_csv_file}")
        self.logger.info(f"Final output contains {len(final_df)} rows with columns: {list(final_df.columns)}")
    
    def save_summary_txt(self, summary_list):
        """Save text summary matching MATLAB format"""
        summary_file = self.analysis_dir / 'summary.txt'
        with open(summary_file, 'w') as f:
            for summary in summary_list:
                f.write(summary + '\n')
        self.logger.info(f"Summary text saved to: {summary_file}")
    
    def format_summary_text(self, filename, results):
        """Format summary text matching MATLAB output"""
        text = f"Summary for {filename}\n"
        text += f"Field Name: {results['field_name']}\n"
        text += f"Region Indices: {results['region_idx']}\n"
        text += f"Max Value: {results['max_value']:.6f} V/m\n"
        text += f"Percentiles: {self.percentiles}\n"
        text += f"Percentile Values: {results['percentile_values']} V/m\n"
        text += f"Focality Cutoffs: {self.focality_cutoffs}\n"
        text += f"Focality Values: {results['focality_values']} (in cubic cm)\n"
        text += f"XYZ Max: {results['xyz_max']}\n"
        text += f"XYZ Percentiles: {results['xyz_percentiles']}\n"
        text += f"XYZ Std Percentiles: {results['xyz_std_percentiles']}\n"
        text += "---------------------------------------------\n"
        return text

def main():
    # Create a basic logger for the main function
    main_logger = get_logger('MeshFieldAnalyzer-Main')
    
    if len(sys.argv) != 2:
        main_logger.error("Usage: python mesh_field_analyzer.py <mesh_directory>")
        sys.exit(1)
    
    mesh_dir = sys.argv[1]
    
    if not os.path.exists(mesh_dir):
        main_logger.error(f"Directory does not exist: {mesh_dir}")
        sys.exit(1)
    
    main_logger.info(f"Starting mesh field analysis in: {mesh_dir}")
    analyzer = MeshFieldAnalyzer(mesh_dir)
    analyzer.process_all_meshes()
    main_logger.info("Analysis complete!")

if __name__ == "__main__":
    main() 