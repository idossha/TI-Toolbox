#!/usr/bin/env python3

# Standard library imports
import glob
import logging
import os
import re
import sys
from pathlib import Path

# Third-party imports
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend before importing pyplot
import matplotlib.pyplot as plt
import meshio
import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Local imports
from tools import logging_util


class MeshFieldAnalyzer:
    def __init__(self, mesh_dir):
        # Convert to absolute path and ensure it exists
        self.mesh_dir = Path(mesh_dir).resolve()
        if not self.mesh_dir.exists():
            raise ValueError(f"Mesh directory does not exist: {self.mesh_dir}")
        
        # Initialize logger following ex-search pattern
        self.logger = self._setup_logger()
        self.logger.info(f"Initializing mesh field analyzer for: {self.mesh_dir}")
        
        # Standard parameters (matching MATLAB defaults)
        self.percentiles = [95, 99, 99.9]
        self.focality_cutoffs = [50, 75, 90, 95]
        self.field_name = 'TImax'  # Default field to analyze (from your TI simulations)
        self.region_idx = 2  # Gray matter tetrahedra
        
        # Get environment variables
        self.project_dir = os.getenv('PROJECT_DIR')
        self.subject_name = os.getenv('SUBJECT_NAME')
        self.selected_net = os.getenv('SELECTED_EEG_NET')
        self.roi_name = os.getenv('ROI_NAME')
        
        # Log configuration
        self.logger.info(f"Project directory: {self.project_dir}")
        self.logger.info(f"Subject: {self.subject_name}")
        self.logger.info(f"Selected EEG net: {self.selected_net}")
        self.logger.info(f"ROI name: {self.roi_name}")
        
        # Create output directory
        self.analysis_dir = self.mesh_dir / 'analysis'
        self.analysis_dir.mkdir(exist_ok=True)
        self.logger.info(f"Analysis directory: {self.analysis_dir}")
    
    def _setup_logger(self):
        """Setup logger following ex-search pattern (same as simulator components)"""
        import time
        
        # Check if log file path is provided through environment variable (from GUI)
        shared_log_file = os.environ.get('TI_LOG_FILE')
        
        if shared_log_file:
            # Use shared log file for unified logging
            # When running from GUI as subprocess, we want both file AND stdout (GUI captures stdout)
            log_file = shared_log_file
            logger = logging_util.get_logger('mesh_field_analyzer', log_file, overwrite=False)
        else:
            # CLI usage: create individual log file with both console and file output
            logger_name = 'MeshFieldAnalyzer'
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            log_file = f'mesh_field_analyzer_{time_stamp}.log'
            logger = logging_util.get_logger(logger_name, log_file, overwrite=False)

        # Configure external loggers to use our logging setup (same as simulator)
        try:
            logging_util.configure_external_loggers(['simnibs', 'mesh_io'], logger)
        except Exception:
            pass  # Silently handle external logger configuration failures
        
        return logger
        
    def process_all_meshes(self):
        """Process all .msh files in the directory
        
        Workflow:
        1. Load ROI data from final_output.csv (created by roi-analyzer.py)
        2. Process each mesh file to extract field metrics
        3. Generate individual histograms with ROI contribution coloring
        4. Merge ROI data with mesh analysis results
        5. Save final summary.csv with complete data
        6. Clean up intermediate files (only after successful merge)
        """
        mesh_files = list(self.mesh_dir.glob('*.msh'))
        
        if not mesh_files:
            self.logger.warning(f"No mesh files found in directory: {self.mesh_dir}")
            return
            
        self.logger.info(f"Found {len(mesh_files)} mesh files to process")
        
        # Initialize results storage
        csv_data = []
        
        # Load ROI data from roi-analyzer output (required for merging)
        roi_data = self.load_roi_data()
        if roi_data is None:
            self.logger.warning("ROI data not available - field values at ROI will be missing in summary")
        
        for mesh_file in mesh_files:
            self.logger.info(f"Processing mesh file: {mesh_file.name}")
            try:
                results = self.analyze_mesh(mesh_file, roi_data)
                if results:
                    csv_data.append(results)
            except Exception as e:
                self.logger.error(f"Failed to process {mesh_file.name}: {str(e)}")
                continue
        
        # Save results with merged ROI data
        if csv_data:
            # Generate final summary CSV with merged ROI and mesh analysis data
            # This is the critical step where ROI values from roi-analyzer.py are merged
            # with mesh field metrics from this script
            self.save_final_summary(csv_data, roi_data)
            
            # Verify final output exists before declaring success
            summary_path = self.analysis_dir / 'summary.csv'
            if summary_path.exists():
                self.logger.info("========================================")
                self.logger.info("Ex-Search Analysis Complete")
                self.logger.info("========================================")
                self.logger.info(f"Output directory: {self.mesh_dir}")
                self.logger.info("Generated outputs:")
                self.logger.info("  In root directory:")
                self.logger.info("    - Per-mesh histograms (*_histogram.png)")
                self.logger.info("    - Mesh files (*.msh)")
                self.logger.info("  In analysis/ subdirectory:")
                self.logger.info("    - summary.csv - Comprehensive field metrics")
                self.logger.info("========================================")
            else:
                self.logger.error("Summary.csv was not created - check logs for errors")
        else:
            self.logger.warning("No results to save - all mesh processing failed")
    
    def analyze_mesh(self, mesh_file, roi_data=None):
        """Analyze a single mesh file and extract field metrics"""
        try:
            # Load mesh using meshio
            mesh = meshio.read(mesh_file)
            self.logger.info(f"Loaded mesh using meshio: {mesh_file.name}")
            
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
            
            # Generate individual histogram for this mesh file with ROI coloring
            self.generate_mesh_histogram(mesh_file.name, filtered_data, element_sizes, positions, roi_data)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to analyze mesh {mesh_file.name}: {str(e)}")
            return None
    
    def get_field_idx(self, mesh, field_name):
        """Find field index in mesh following meshio pattern"""
        self.logger.info(f"Looking for field data in mesh with name: {field_name}")
        
        # Look in cell_data first (element data - tetrahedra)
        if hasattr(mesh, 'cell_data') and mesh.cell_data:
            if field_name in mesh.cell_data:
                self.logger.info(f"Found exact field match in cell_data: {field_name}")
                field_data = mesh.cell_data[field_name]
                return field_data, 'element'
            
            # Log available fields for debugging
            available_fields = list(mesh.cell_data.keys())
            self.logger.info(f"Available fields in cell_data: {available_fields}")
        
        # Look in point_data (node data)
        if hasattr(mesh, 'point_data') and mesh.point_data:
            if isinstance(mesh.point_data, dict) and field_name in mesh.point_data:
                self.logger.info(f"Found field in point_data: {field_name}")
                return mesh.point_data[field_name], 'node'
        
        # Try common field name variations
        field_variations = ['TImax', 'magnE', 'E.normal', 'TI_max', 'E_magn', 'TI_field']
        for variant in field_variations:
            if hasattr(mesh, 'cell_data') and mesh.cell_data:
                if variant in mesh.cell_data:
                    self.logger.info(f"Found field under variant name in cell_data: {variant}")
                    self.field_name = variant
                    return mesh.cell_data[variant], 'element'
            
            if hasattr(mesh, 'point_data') and mesh.point_data:
                if isinstance(mesh.point_data, dict) and variant in mesh.point_data:
                    self.logger.info(f"Found field under variant name in point_data: {variant}")
                    self.field_name = variant
                    return mesh.point_data[variant], 'node'
        
        self.logger.warning("No field data found in any expected location")
        return None, None
    
    def extract_field_data(self, mesh):
        """Extract field data from mesh following meshio patterns"""
        self.logger.info("Attempting to extract field data from mesh...")
        
        field_data, data_type = self.get_field_idx(mesh, self.field_name)
        if field_data is not None:
            # Convert to numpy array for easier processing
            field_data = np.asarray(field_data)
            # Flatten if needed (handle shape like (1, N) -> (N,))
            if field_data.ndim > 1:
                field_data = field_data.flatten()
                self.logger.info(f"Flattened field data shape: {field_data.shape}")
            
            # Log some statistics
            self.logger.info(f"Field data statistics:")
            self.logger.info(f"  Min: {np.min(field_data):.6f}")
            self.logger.info(f"  Max: {np.max(field_data):.6f}")
            self.logger.info(f"  Mean: {np.mean(field_data):.6f}")
            self.logger.info(f"  Elements: {len(field_data)}")
                
        return field_data
    
    def filter_by_region(self, mesh, field_data):
        """Filter data by region following meshio pattern (mesh_extract_regions equivalent)"""
        self.logger.info("Starting region filtering...")
        
        # Validate input field data
        if field_data is None:
            self.logger.error("No field data provided for filtering")
            return np.array([]), np.array([]).reshape(0,3), np.array([])
            
        # Find tetrahedra and their region tags
        tet_cells = None
        tet_regions = None
        
        # Handle meshio mesh format - iterate through cells to find tetrahedra
        for i, cell_block in enumerate(mesh.cells):
            if cell_block.type == 'tetra':
                tet_cells = cell_block.data
                self.logger.info(f"Found {len(tet_cells)} tetrahedra")
                
                # Look for region information (gmsh:physical tags)
                if hasattr(mesh, 'cell_data') and mesh.cell_data:
                    # Look for physical region tags - they're stored as lists in cell_data
                    if 'gmsh:physical' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['gmsh:physical'])
                        # Flatten if needed (handle shape like (1, N) -> (N,))
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                        self.logger.info(f"Found {len(tet_regions)} region tags in gmsh:physical")
                    elif 'Physical Names' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['Physical Names'])
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                        self.logger.info(f"Found {len(tet_regions)} region tags in Physical Names")
                    elif 'region' in mesh.cell_data:
                        tet_regions = np.asarray(mesh.cell_data['region'])
                        if tet_regions.ndim > 1:
                            tet_regions = tet_regions.flatten()
                        self.logger.info(f"Found {len(tet_regions)} region tags in region")
                    else:
                        self.logger.warning("No region tags found in mesh")
                break
        
        if tet_cells is None:
            self.logger.warning("No tetrahedra found in mesh")
            return np.array([]), np.array([]).reshape(0,3), np.array([])
        
        # Filter by gray matter region (region_idx = 2)
        if tet_regions is not None:
            # Create mask for gray matter elements
            gray_matter_mask = tet_regions == self.region_idx
            gray_matter_count = np.sum(gray_matter_mask)
            self.logger.info(f"Found {gray_matter_count} gray matter elements (region {self.region_idx})")
            
            gray_matter_tets = tet_cells[gray_matter_mask]
            if len(gray_matter_tets) == 0:
                self.logger.warning(f"No elements found for region {self.region_idx}")
                return np.array([]), np.array([]).reshape(0,3), np.array([])
            
            # Get field data for gray matter tetrahedra only
            if isinstance(field_data, np.ndarray):
                self.logger.info(f"Field data shape: {field_data.shape}")
                self.logger.info(f"Tetrahedra count: {len(tet_cells)}")
                
                # Try to match dimensions
                if len(field_data) == len(tet_cells):
                    filtered_data = field_data[gray_matter_mask]
                    self.logger.info(f"Filtered field data shape: {filtered_data.shape}")
                else:
                    self.logger.error(f"Field data length ({len(field_data)}) does not match tetrahedra count ({len(tet_cells)})")
                    return np.array([]), np.array([]).reshape(0,3), np.array([])
            else:
                self.logger.error(f"Field data is not a numpy array: {type(field_data)}")
                return np.array([]), np.array([]).reshape(0,3), np.array([])
            
            # Get mesh points - meshio stores them in mesh.points
            if hasattr(mesh, 'points'):
                mesh_points = mesh.points
                self.logger.info(f"Found {len(mesh_points)} mesh points")
                
                # Calculate element centers and sizes
                try:
                    # meshio uses 0-based indexing by default
                    element_centers = np.mean(mesh_points[gray_matter_tets], axis=1)
                    element_sizes = self.calculate_tetrahedron_volumes(mesh_points, gray_matter_tets)
                    
                    self.logger.info(f"Calculated {len(element_centers)} element centers")
                    self.logger.info(f"Calculated {len(element_sizes)} element volumes")
                    
                except Exception as e:
                    self.logger.error(f"Error calculating element properties: {str(e)}")
                    return np.array([]), np.array([]).reshape(0,3), np.array([])
            else:
                self.logger.error("Mesh does not have node coordinates")
                return np.array([]), np.array([]).reshape(0,3), np.array([])
        else:
            self.logger.warning("No region information found, using all tetrahedra")
            filtered_data = field_data
            
            # Calculate properties for all tetrahedra
            mesh_points = mesh.points
            # meshio uses 0-based indexing by default
            element_centers = np.mean(mesh_points[tet_cells], axis=1)
            element_sizes = self.calculate_tetrahedron_volumes(mesh_points, tet_cells)
        
        # Ensure we return proper numpy arrays
        filtered_data = np.asarray(filtered_data).flatten()
        element_centers = np.asarray(element_centers)
        element_sizes = np.asarray(element_sizes)
        
        # Log final statistics
        self.logger.info("Region filtering complete:")
        self.logger.info(f"  Field data elements: {len(filtered_data)}")
        self.logger.info(f"  Element centers: {len(element_centers)}")
        self.logger.info(f"  Element volumes: {len(element_sizes)}")
        
        if len(filtered_data) > 0:
            self.logger.info("Field statistics:")
            self.logger.info(f"  Min: {np.min(filtered_data):.6f}")
            self.logger.info(f"  Max: {np.max(filtered_data):.6f}")
            self.logger.info(f"  Mean: {np.mean(filtered_data):.6f}")
        
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
    
    # End of class methods
    
    def load_roi_data(self):
        """Load ROI data from the analysis directory."""
        try:
            roi_csv_path = self.analysis_dir / 'final_output.csv'
            if roi_csv_path.exists():
                self.logger.info(f"Loading ROI data from: {roi_csv_path}")
                roi_df = pd.read_csv(roi_csv_path)
                return roi_df
            else:
                self.logger.warning("No ROI data file found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to load ROI data: {str(e)}")
            return None
    
    def save_final_summary(self, results_list, roi_data):
        """Save comprehensive final summary CSV with merged ROI and mesh analysis data.
        
        This method merges:
        - Mesh field analysis results (from this script)
        - ROI field values (from roi-analyzer.py via final_output.csv)
        
        The merge is done by matching electrode configurations between datasets.
        """
        try:
            if not results_list:
                self.logger.warning("No results to save in summary")
                return
                
            # Create summary rows
            summary_rows = []
            
            for results in results_list:
                # Extract electrode configuration from filename
                # TI_field_O1_Fp1_and_T7_F7.msh -> O1_Fp1 <> T7_F7
                mesh_name = results['filename']
                config = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
                
                row = {
                    'Electrode Configuration': config,
                    'Peak Field': f"{results['max_value']:.3f}" if results['max_value'] is not None else '',
                    '95th %': f"{results['percentile_values'][0]:.3f}" if len(results['percentile_values']) > 0 else '',
                    '99th %': f"{results['percentile_values'][1]:.3f}" if len(results['percentile_values']) > 1 else '',
                    '99.9th %': f"{results['percentile_values'][2]:.3f}" if len(results['percentile_values']) > 2 else '',
                }
                
                # Add focality values (convert cm³ to mm³)
                if len(results['focality_values']) >= 4:
                    row['Focality 50%'] = f"{results['focality_values'][0]*1000:.1f}"  # cm³ to mm³
                    row['Focality 75%'] = f"{results['focality_values'][1]*1000:.1f}"
                    row['Focality 90%'] = f"{results['focality_values'][2]*1000:.1f}"
                    row['Focality 95%'] = f"{results['focality_values'][3]*1000:.1f}"
                else:
                    row['Focality 50%'] = ''
                    row['Focality 75%'] = ''
                    row['Focality 90%'] = ''
                    row['Focality 95%'] = ''
                
                # Add peak location (as separate columns)
                if results['xyz_max']:
                    xyz = results['xyz_max']
                    row['Peak Location'] = f"{xyz[0]:.2f}, {xyz[1]:.2f}, {xyz[2]:.2f}"
                else:
                    row['Peak Location'] = ''
                
                # Add ROI data if available
                if roi_data is not None and 'Mesh' in roi_data.columns:
                    # Find matching ROI data
                    roi_match = roi_data[roi_data['Mesh'] == config]
                    if not roi_match.empty:
                        if 'TImax_ROI' in roi_match.columns:
                            roi_val = roi_match.iloc[0]['TImax_ROI']
                            row['TImax ROI'] = f"{roi_val:.3f}" if not pd.isna(roi_val) else ''
                        else:
                            row['TImax ROI'] = ''
                        if 'TImean_ROI' in roi_match.columns:
                            roi_val = roi_match.iloc[0]['TImean_ROI']
                            row['TImean ROI'] = f"{roi_val:.3f}" if not pd.isna(roi_val) else ''
                        else:
                            row['TImean ROI'] = ''
                    else:
                        row['TImax ROI'] = ''
                        row['TImean ROI'] = ''
                else:
                    row['TImax ROI'] = ''
                    row['TImean ROI'] = ''
                
                # Reorder columns to match requested format
                ordered_row = {
                    'Electrode Configuration': row['Electrode Configuration'],
                    'TImax ROI': row['TImax ROI'],
                    'TImean ROI': row['TImean ROI'],
                    'Peak Field': row['Peak Field'],
                    '95th %': row['95th %'],
                    '99th %': row['99th %'],
                    '99.9th %': row['99.9th %'],
                    'Focality 50%': row['Focality 50%'],
                    'Focality 75%': row['Focality 75%'],
                    'Focality 90%': row['Focality 90%'],
                    'Focality 95%': row['Focality 95%'],
                    'Peak Location': row['Peak Location']
                }
                
                summary_rows.append(ordered_row)
            
            # Save to CSV
            summary_df = pd.DataFrame(summary_rows)
            
            # Save only in analysis directory
            analysis_output = self.analysis_dir / 'summary.csv'
            summary_df.to_csv(analysis_output, index=False)
            
            self.logger.info(f"Summary CSV saved to: {analysis_output}")
            self.logger.info(f"Successfully merged {len(summary_rows)} electrode configurations")
            
            # Verify ROI data was successfully merged
            if roi_data is not None:
                merged_count = sum(1 for row in summary_rows if row.get('TImax ROI', '') != '')
                self.logger.info(f"ROI values merged for {merged_count}/{len(summary_rows)} configurations")
            
            # Clean up intermediate files - only after successful merge
            # This preserves data integrity by ensuring all merging is complete
            self.cleanup_analysis_directory()
            
        except Exception as e:
            self.logger.error(f"Failed to save final summary: {str(e)}")
            self.logger.info("Preserving intermediate files due to summary creation failure")
    
    def cleanup_analysis_directory(self):
        """Remove intermediate files from analysis directory, keeping only summary.csv
        
        This cleanup happens AFTER all data has been successfully merged into summary.csv.
        The files being removed are intermediate processing files that are no longer needed.
        """
        try:
            # Only clean up if summary.csv exists (ensuring merge was successful)
            summary_path = self.analysis_dir / 'summary.csv'
            if not summary_path.exists():
                self.logger.warning("Summary.csv not found - skipping cleanup to preserve data")
                return
            
            # Verify summary.csv has content before cleaning up
            summary_df = pd.read_csv(summary_path)
            if summary_df.empty:
                self.logger.warning("Summary.csv is empty - skipping cleanup to preserve source data")
                return
            
            # List of intermediate files to remove after successful merge
            files_to_remove = ['final_output.csv', 'mesh_data.json']
            
            for filename in files_to_remove:
                file_path = self.analysis_dir / filename
                if file_path.exists():
                    file_path.unlink()
                    self.logger.info(f"Cleaned up intermediate file: {filename}")
            
            # Remove any other temporary files (except summary.csv)
            for file_path in self.analysis_dir.glob('*'):
                if file_path.is_file() and file_path.name != 'summary.csv':
                    file_path.unlink()
                    self.logger.info(f"Cleaned up: {file_path.name}")
                    
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")
            self.logger.info("Preserving all files due to cleanup error")
    
    def generate_mesh_histogram(self, mesh_name, field_data, element_sizes, positions, roi_data=None):
        """Generate histogram for a single mesh file showing field distribution in gray matter with ROI contribution coloring."""
        try:
            self.logger.info(f"Generating histogram for {mesh_name}...")
            
            # Convert to numpy arrays if needed
            field_data = np.asarray(field_data)
            element_sizes = np.asarray(element_sizes)
            
            # Remove NaN values
            valid_mask = ~np.isnan(field_data)
            field_data = field_data[valid_mask]
            element_sizes = element_sizes[valid_mask]
            positions = positions[valid_mask] if positions is not None else None
            
            if len(field_data) == 0:
                self.logger.warning(f"No valid field data for histogram in {mesh_name}")
                return
            
            # Create figure
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Create histogram with volume weighting
            weights = element_sizes / 1000.0  # Convert mm³ to cm³
            n_bins = 100
            
            # Create histogram bins
            hist, bin_edges = np.histogram(field_data, bins=n_bins, weights=weights)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            bin_width = bin_edges[1] - bin_edges[0]
            
            # Calculate ROI contribution for rainbow coloring if ROI data is available
            if roi_data is not None and 'TImax_ROI' in roi_data.columns and len(roi_data) > 0:
                # Get ROI field value for this mesh
                # Match mesh name with roi_data
                mesh_base = mesh_name.replace('.msh', '').replace('TI_field_', '')
                mesh_formatted = mesh_base.replace('_and_', ' <> ')
                
                roi_value = None
                if 'Mesh' in roi_data.columns:
                    roi_row = roi_data[roi_data['Mesh'] == mesh_formatted]
                    if not roi_row.empty:
                        roi_value = roi_row['TImax_ROI'].values[0]
                
                if roi_value is not None and not np.isnan(roi_value):
                    # Calculate contribution of ROI region to each bin
                    # Higher field values closer to ROI value indicate better focality
                    distances = np.abs(bin_centers - roi_value)
                    
                    # Apply a gaussian-like decay from ROI value
                    # Sigma controls how rapidly the contribution decreases with distance
                    field_range = np.max(field_data) - np.min(field_data)
                    sigma = field_range / 15  # Adjust width of influence
                    contributions = np.exp(-(distances**2) / (2 * sigma**2))
                    
                    # Normalize contributions to [0, 1]
                    contributions = (contributions - np.min(contributions)) / (np.max(contributions) - np.min(contributions) + 1e-10)
                    
                    # Use rainbow colormap (blue=low, green=medium, red=high contribution)
                    rainbow_cmap = plt.colormaps['rainbow']
                    colors = rainbow_cmap(contributions)
                    colors[:, 3] = 0.8  # Set alpha
                    
                    # Create bar plot with colors
                    bars = ax.bar(bin_centers, hist, width=bin_width, edgecolor='black', linewidth=0.5)
                    for bar, color in zip(bars, colors):
                        bar.set_facecolor(color)
                    
                    # Add colorbar to show contribution scale
                    sm = plt.cm.ScalarMappable(cmap=plt.colormaps['rainbow'], norm=plt.Normalize(vmin=0, vmax=1))
                    sm.set_array([])
                    cbar = plt.colorbar(sm, ax=ax, pad=0.02, aspect=30)
                    cbar.set_label('ROI Contribution', rotation=270, labelpad=20)
                    
                    # Add ROI value line
                    ax.axvline(x=roi_value, color='red', linestyle='-', linewidth=3, alpha=0.9,
                              label=f'ROI Field: {roi_value:.2f} V/m')
                else:
                    # No ROI data for this mesh, use default color
                    ax.bar(bin_centers, hist, width=bin_width, alpha=0.8, edgecolor='black', color='skyblue')
            else:
                # No ROI data available, use default color
                ax.bar(bin_centers, hist, width=bin_width, alpha=0.8, edgecolor='black', color='skyblue')
            
            # Calculate percentiles and focality metrics
            percentile_95 = np.percentile(field_data, 95)
            percentile_99 = np.percentile(field_data, 99)
            percentile_99_9 = np.percentile(field_data, 99.9)
            max_value = np.max(field_data)
            
            # Add percentile lines
            ax.axvline(x=percentile_95, color='blue', linestyle='--', linewidth=2, alpha=0.7,
                      label=f'95th percentile: {percentile_95:.2f} V/m')
            ax.axvline(x=percentile_99, color='orange', linestyle='--', linewidth=2, alpha=0.7,
                      label=f'99th percentile: {percentile_99:.2f} V/m')
            ax.axvline(x=percentile_99_9, color='red', linestyle='--', linewidth=2, alpha=0.7,
                      label=f'99.9th percentile: {percentile_99_9:.2f} V/m')
            ax.axvline(x=max_value, color='darkred', linestyle='-', linewidth=2, alpha=0.9,
                      label=f'Max: {max_value:.2f} V/m')
            
            # Labels and formatting
            ax.set_xlabel('Field Strength (V/m)', fontsize=12)
            ax.set_ylabel('Volume (cm³)', fontsize=12)
            
            # Clean up mesh name for title (remove .msh extension if present)
            clean_name = mesh_name.replace('.msh', '').replace('_', ' ')
            # Add note about ROI contribution if it's being shown
            if roi_data is not None and 'TImax_ROI' in roi_data.columns:
                ax.set_title(f'Field Distribution with ROI Contribution: {clean_name}', fontsize=14, fontweight='bold')
            else:
                ax.set_title(f'Field Distribution: {clean_name}', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Add statistics box
            stats_text = f'Statistics:\n'
            stats_text += f'Max: {max_value:.2f} V/m\n'
            stats_text += f'Mean: {np.mean(field_data):.2f} V/m\n'
            stats_text += f'Median: {np.median(field_data):.2f} V/m\n'
            stats_text += f'Total Volume: {np.sum(element_sizes)/1000.0:.1f} cm³'
            
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            # Add legend
            ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True)
            
            # Save histogram in root directory with mesh file name
            histogram_name = mesh_name.replace('.msh', '_histogram.png')
            histogram_path = self.mesh_dir / histogram_name
            
            plt.tight_layout()
            plt.savefig(histogram_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            
            self.logger.info(f"Histogram saved to: {histogram_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to generate histogram for {mesh_name}: {str(e)}")
            import traceback
            self.logger.error(f"Traceback:\n{traceback.format_exc()}")

# End of MeshFieldAnalyzer class

def main():
    # Set up logger for main function
    try:
        from tools import logging_util
        
        # Check if running from GUI (TI_LOG_FILE environment variable set)
        shared_log_file = os.environ.get('TI_LOG_FILE')
        
        if shared_log_file:
            # When running from GUI as subprocess, we want both file AND stdout (GUI captures stdout)
            main_logger = logging_util.get_logger('mesh_field_analyzer_main', shared_log_file, overwrite=False)
        else:
            # CLI usage: use standard logging utility
            main_logger = logging_util.get_logger('MeshFieldAnalyzer-Main')
    except ImportError:
        # Fallback: create a simple logger (use module-level logging)
        logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
        main_logger = logging.getLogger('MeshFieldAnalyzer-Main')
    
    # Process command line arguments
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