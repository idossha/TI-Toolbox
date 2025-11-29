"""
MeshAnalyzer: A tool for analyzing mesh-based neuroimaging data

This module provides functionality for analyzing field data in specific regions of interest,
including spherical ROIs and cortical regions defined by an atlas. It works with
SimNIBS mesh files and can generate surface meshes for cortical analysis.

Inputs:
    - SimNIBS mesh files (.msh) containing field data
    - Subject directory containing m2m files for atlas mapping
    - ROI specifications (coordinates, regions)

Outputs:
    - Statistical measures (mean, min, max)
    - ROI masks
    - Surface meshes for visualization
    - Visualization files (optional)

Example Usage:
    ```python
    # Initialize analyzer
    analyzer = MeshAnalyzer(
        field_mesh_path="/path/to/field.msh",
        field_name="normE",
        subject_dir="/path/to/m2m_subject",
        output_dir="/path/to/output"
    )

    # Analyze a spherical ROI
    sphere_results = analyzer.analyze_sphere(
        center_coordinates=[0, 0, 0],
        radius=10
    )

    # Analyze a cortical region
    cortex_results = analyzer.analyze_cortex(
        atlas_type="DK40",
        target_region="superiorfrontal",
        visualize=True
    )

    # Analyze whole head
    whole_head_results = analyzer.analyze_whole_head(
        atlas_type="DK40",
        visualize=True
    )
    ```

Dependencies:
    - numpy
    - simnibs
    - subprocess (for msh2cortex operations)
"""

# Standard library imports
import csv
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Third-party imports
import matplotlib.pyplot as plt
import numpy as np
import simnibs

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports
from tools import logging_util
from analyzer.visualizer import MeshVisualizer

class MeshAnalyzer:
    """
    A class for analyzing mesh-based data from 3D models.
    
   This class provides methods for analyzing field data in specific regions of interest,
    including spherical ROIs and cortical regions defined by an atlas. It works with
    SimNIBS mesh files and can generate surface meshes for cortical analysis.
    
    Attributes:
        field_mesh_path (str): Path to the mesh file containing field data
        field_name (str): Name of the field to analyze in the mesh
        subject_dir (str): Directory containing subject data (m2m folder)
        output_dir (str): Directory where analysis results will be saved
        visualizer (MeshVisualizer): Instance of visualizer for generating plots
        _temp_dir (tempfile.TemporaryDirectory): Temporary directory for surface mesh
        _surface_mesh_path (str): Path to the generated surface mesh
    """
    
    def __init__(self, field_mesh_path: str, field_name: str, subject_dir: str, output_dir: str, logger=None):
        """
        Initialize the MeshAnalyzer class.

        Args:
            field_mesh_path (str): Path to the mesh file containing the field data
            field_name (str): Name of the field to analyze
            subject_dir (str): Directory containing subject data (m2m folder)
            output_dir (str): Directory where analysis results will be saved
            logger: Optional logger instance to use. If None, creates its own.
        """
        self.field_mesh_path = field_mesh_path
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        
        # Set up logger - use provided logger or create a new one
        if logger is not None:
            # Create a child logger to distinguish mesh analyzer logs
            self.logger = logger.getChild('mesh_analyzer')
        else:
            # Create our own logger if none provided
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Extract subject ID from subject_dir (e.g., m2m_subject -> subject)
            subject_id = os.path.basename(self.subject_dir).split('_')[1] if '_' in os.path.basename(self.subject_dir) else os.path.basename(self.subject_dir)
            
            # Create derivatives/ti-toolbox/logs/sub-* directory structure (using relative path like voxel analyzer)
            log_dir = os.path.join('derivatives', 'ti-toolbox', 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file in the new directory
            log_file = os.path.join(log_dir, f'mesh_analyzer_{time_stamp}.log')
            self.logger = logging_util.get_logger('mesh_analyzer', log_file, overwrite=True)
        
        # Initialize visualizer with logger
        self.visualizer = MeshVisualizer(output_dir, self.logger)
        
        # Initialize temporary directory and surface mesh path
        self._temp_dir = None
        self._surface_mesh_path = None
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            self.logger.debug(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir)
        
        # Validate that field mesh exists
        if not os.path.exists(field_mesh_path):
            self.logger.error(f"Field mesh file not found: {field_mesh_path}")
            raise FileNotFoundError(f"Field mesh file not found: {field_mesh_path}")
        
        self.logger.debug(f"Mesh analyzer initialized successfully")
        self.logger.debug(f"Field mesh path: {field_mesh_path}")
        self.logger.debug(f"Field name: {field_name}")
        self.logger.debug(f"Subject directory: {subject_dir}")
        self.logger.debug(f"Output directory: {output_dir}")

    def _generate_surface_mesh(self):
        """
        Generate a surface mesh from the field mesh using msh2cortex if not already generated.
        This is used for cortical analysis.
        
        Returns:
            str: Path to the generated surface mesh file
        """
        # Get the base name of the input mesh
        input_name = os.path.basename(self.field_mesh_path)
        base_name = os.path.splitext(input_name)[0]
        
        # Get the simulation name and subject ID from the field mesh path
        # Field path structure can be:
        # 1. .../sub-<n>/Simulations/simulation_name/TI/mesh/field.msh (regular simulations)
        # 2. .../sub-<n>/ex-search/roi_leadfield/field.msh (ex-search)
        # 3. .../sub-<n>/flex-search/roi_leadfield/field.msh (flex-search)
        field_path_parts = self.field_mesh_path.split(os.sep)
        
        # Check if this is an ex-search or flex-search path
        is_ex_search = 'ex-search' in field_path_parts
        is_flex_search = 'flex-search' in field_path_parts
        
        try:
            if is_ex_search or is_flex_search:
                # For optimization searches, use the output_dir directly for surface meshes
                if self.output_dir:
                    surface_mesh_dir = self.output_dir
                else:
                    # Fallback: use the same directory as the field mesh
                    surface_mesh_dir = os.path.dirname(self.field_mesh_path)
                os.makedirs(surface_mesh_dir, exist_ok=True)
                
                # For ex-search/flex-search, use the first generated surface mesh
                # msh2cortex names output based on input, so we'll use base_name
                # but we'll look for any existing *_central.msh file first
                existing_central = [f for f in os.listdir(surface_mesh_dir) if f.endswith('_central.msh')]
                if existing_central:
                    # Reuse existing surface mesh
                    surface_mesh_path = os.path.join(surface_mesh_dir, existing_central[0])
                    self.logger.debug(f"Found existing surface mesh to reuse: {surface_mesh_path}")
                else:
                    # Generate new one with current field's name
                    surface_mesh_path = os.path.join(surface_mesh_dir, f"{base_name}_central.msh")
            else:
                # Standard simulation path structure
                sim_idx = field_path_parts.index('Simulations')
                simulation_name = field_path_parts[sim_idx + 1]
                
                # Get the subject ID from the m2m directory path
                # m2m path structure: .../sub-<n>/m2m_<n>
                m2m_name = os.path.basename(self.subject_dir)  # e.g., 'm2m_ido'
                subject_id = m2m_name.split('_')[1]  # e.g., 'ido'
                
                # Get the SimNIBS directory (parent of sub-*)
                simnibs_dir = os.path.dirname(os.path.dirname(self.subject_dir))
                
                # Detect if this is an mTI simulation by checking the field mesh path
                is_mti = 'mTI' in self.field_mesh_path
                
                # Construct the path where the surface mesh should be stored
                if is_mti:
                    surface_mesh_dir = os.path.join(simnibs_dir, f'sub-{subject_id}', 'Simulations', simulation_name, 'mTI', 'mesh')
                else:
                    surface_mesh_dir = os.path.join(simnibs_dir, f'sub-{subject_id}', 'Simulations', simulation_name, 'TI', 'mesh')
                os.makedirs(surface_mesh_dir, exist_ok=True)
                
                # The surface mesh file path - specific to this field mesh only
                surface_mesh_path = os.path.join(surface_mesh_dir, f"{base_name}_central.msh")
            
            # If we already have a valid surface mesh, return it
            if os.path.exists(surface_mesh_path):
                self.logger.debug(f"Using existing surface mesh at: {surface_mesh_path}")
                self._surface_mesh_path = surface_mesh_path
                return surface_mesh_path
                
            self.logger.info(f"Generating surface mesh for specific field: {input_name} using msh2cortex...")
            
            try:
                # Run msh2cortex command only for this specific field mesh
                cmd = [
                    'msh2cortex',
                    '-i', self.field_mesh_path,
                    '-m', self.subject_dir,
                    '-o', surface_mesh_dir
                ]
                
                self.logger.debug(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True)
                
                if not os.path.exists(surface_mesh_path):
                    self.logger.error(f"Expected surface mesh file not found at: {surface_mesh_path}")
                    raise FileNotFoundError(f"Expected surface mesh file not found at: {surface_mesh_path}")
                
                # Store the path
                self._surface_mesh_path = surface_mesh_path
                self.logger.debug(f"Surface mesh generated successfully for {input_name} at: {surface_mesh_path}")
                
                return surface_mesh_path
                
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error running msh2cortex: {str(e)}")
                self.logger.error(f"Command output: {e.stdout.decode() if e.stdout else ''}")
                self.logger.error(f"Command error: {e.stderr.decode() if e.stderr else ''}")
                raise RuntimeError("Failed to generate surface mesh using msh2cortex")
            except FileNotFoundError as e:
                self.logger.error(f"Error: {str(e)}")
                self.logger.error("msh2cortex completed but did not generate the expected file.")
                self.logger.error(f"Contents of output directory {surface_mesh_dir}:")
                try:
                    files = os.listdir(surface_mesh_dir)
                    for f in files:
                        self.logger.error(f"  {f}")
                except:
                    self.logger.error("  Could not list directory contents")
                raise
                
        except (ValueError, IndexError) as e:
            self.logger.error(f"Could not determine simulation name from field mesh path. Expected path structure: .../sub-<n>/Simulations/simulation_name/(TI|mTI)/mesh/field.msh")
            raise ValueError("Could not determine simulation name from field mesh path. Expected path structure: .../sub-<n>/Simulations/simulation_name/(TI|mTI)/mesh/field.msh")

    def __del__(self):
        """Cleanup temporary directory when the analyzer is destroyed."""
        if self._temp_dir is not None:
            try:
                self.logger.info("Cleaning up temporary directory...")
                self._temp_dir.cleanup()
            except:
                pass

    def _construct_normal_mesh_path(self):
        """
        Construct the path to the normal mesh file based on the main field mesh path.
        Expected pattern: 
        - <montage>_TI.msh -> <montage>_normal.msh (for TI simulations)
        - <montage>_mTI.msh -> <montage>_mTI_normal.msh (for mTI simulations, if available)
        
        Returns:
            str: Path to the normal mesh file
        """
        # Get the directory and filename from the main field mesh path
        mesh_dir = os.path.dirname(self.field_mesh_path)
        mesh_filename = os.path.basename(self.field_mesh_path)
        
        # Handle mTI simulations
        if mesh_filename.endswith('_mTI.msh'):
            # For mTI, the normal file would be _mTI_normal.msh (if it exists)
            # Note: mTI pipeline currently doesn't generate normal meshes, so this may not exist
            normal_filename = mesh_filename.replace('_mTI.msh', '_mTI_normal.msh')
        # Handle regular TI simulations
        elif mesh_filename.endswith('_TI.msh'):
            normal_filename = mesh_filename.replace('_TI.msh', '_normal.msh')
        else:
            # Fallback: just replace .msh with _normal.msh
            base_name = os.path.splitext(mesh_filename)[0]
            normal_filename = f"{base_name}_normal.msh"
        
        normal_mesh_path = os.path.join(mesh_dir, normal_filename)
        return normal_mesh_path

    def _extract_normal_field_values(self, roi_mask):
        """
        Extract TI_normal field values from the normal mesh file for a given ROI mask.
        
        Args:
            roi_mask: Boolean array indicating which nodes are in the ROI
            
        Returns:
            tuple: (normal_field_values_positive, normal_statistics)
                normal_field_values_positive: Array of positive TI_normal values in ROI
                normal_statistics: Dict with mean, max, min values, or None if no values found
        """
        try:
            # Construct path to normal mesh file
            normal_mesh_path = self._construct_normal_mesh_path()
            
            # Check if normal mesh file exists
            if not os.path.exists(normal_mesh_path):
                self.logger.warning(f"Normal mesh file not found: {normal_mesh_path}")
                return None, None
            
            self.logger.info(f"Loading normal mesh: {normal_mesh_path}")
            
            # Load the normal mesh
            normal_mesh = simnibs.read_msh(normal_mesh_path)
            
            # Check if TI_normal field exists
            if 'TI_normal' not in normal_mesh.field:
                available_fields = list(normal_mesh.field.keys())
                self.logger.warning(f"TI_normal field not found in normal mesh. Available fields: {available_fields}")
                return None, None
            
            # Get TI_normal field values
            normal_field_values = normal_mesh.field['TI_normal'].value
            
            # Apply ROI mask to get values in the region of interest
            normal_field_values_in_roi = normal_field_values[roi_mask]
            
            # Filter for positive values
            positive_mask = normal_field_values_in_roi > 0
            normal_field_values_positive = normal_field_values_in_roi[positive_mask]
            
            # Check if we have any positive values
            if len(normal_field_values_positive) == 0:
                self.logger.warning("No positive TI_normal values found in ROI")
                return None, None
            
            # Calculate statistics on positive values only
            normal_min_value = np.min(normal_field_values_positive)
            normal_max_value = np.max(normal_field_values_positive)
            
            # Calculate mean value using node areas for proper averaging (only positive values)
            # Note: We assume the normal mesh has the same node structure as the surface mesh
            # so we can use the same ROI mask
            node_areas = normal_mesh.nodes_areas()
            positive_node_areas = node_areas[roi_mask][positive_mask]
            normal_mean_value = np.average(normal_field_values_positive, weights=positive_node_areas)
            
            # Calculate focality for TI_normal
            whole_brain_positive_mask = normal_field_values > 0
            whole_brain_node_areas = node_areas[whole_brain_positive_mask]
            whole_brain_normal_average = np.average(normal_field_values[whole_brain_positive_mask], weights=whole_brain_node_areas)
            normal_focality = normal_mean_value / whole_brain_normal_average
            
            normal_statistics = {
                'normal_mean_value': normal_mean_value,
                'normal_max_value': normal_max_value,
                'normal_min_value': normal_min_value,
                'normal_focality': normal_focality
            }
            
            self.logger.debug(f"TI_normal statistics calculated successfully")
            
            # Clean up
            del normal_mesh
            
            return normal_field_values_positive, normal_statistics
            
        except Exception as e:
            self.logger.warning(f"Failed to extract TI_normal values: {str(e)}")
            return None, None

    def analyze_whole_head(self, atlas_type='HCP_MMP1', visualize=False):
        """
        Analyze all regions in the specified atlas.
        """
        start_time = time.time()
        self.logger.info(f"Starting whole head analysis using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            surface_mesh_path = self._generate_surface_mesh()
      
            # Load the surface mesh
            self.logger.info("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Load the atlas
            self.logger.info(f"Loading atlas {atlas_type}...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_name in atlas.keys():
                try:
                    self.logger.info(f"Processing region: {region_name}")
                    
                    # Create a directory for this region in the main output directory
                    region_dir = os.path.join(self.output_dir, region_name)
                    os.makedirs(region_dir, exist_ok=True)
                    
                    # Get ROI mask for this region
                    try:
                        roi_mask = atlas[region_name]
                        # Check if roi_mask is actually a mask array
                        if callable(roi_mask):
                            self.logger.error(f"Region {region_name}: atlas[region_name] returned a callable object, not a mask")
                            raise TypeError(f"Region {region_name}: Expected mask array, got callable object")
                        elif not hasattr(roi_mask, '__len__'):
                            self.logger.error(f"Region {region_name}: atlas[region_name] returned non-array object: {type(roi_mask)}")
                            raise TypeError(f"Region {region_name}: Expected mask array, got {type(roi_mask)}")
                    except Exception as e:
                        self.logger.error(f"Failed to get ROI mask for region {region_name}: {str(e)}")
                        raise
                    
                    # Check if we have any nodes in the ROI
                    roi_nodes_count = np.sum(roi_mask)
                    if roi_nodes_count == 0:
                        self.logger.warning(f"Warning: No nodes found in the specified region '{region_name}'")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None,
                            'focality': None,
                            'nodes_in_roi': 0,
                            'normal_mean_value': None,
                            'normal_max_value': None,
                            'normal_min_value': None,
                            'normal_focality': None
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        
                        continue
                    
                    self.logger.info(f"Getting field values within the ROI...")
                    # Get the field values within the ROI
                    try:
                        field_values = gm_surf.field[self.field_name].value
                        if callable(field_values):
                            self.logger.error(f"Region {region_name}: field values returned a callable object")
                            raise TypeError(f"Region {region_name}: Expected field values array, got callable object")
                        field_values_in_roi = field_values[roi_mask]
                    except Exception as e:
                        self.logger.error(f"Failed to get field values for region {region_name}: {str(e)}")
                        self.logger.error(f"Field values type: {type(field_values) if 'field_values' in locals() else 'undefined'}")
                        self.logger.error(f"ROI mask type: {type(roi_mask)}")
                        raise
                    
                    # Filter for positive values in ROI (matching voxel analyzer behavior)
                    positive_mask = field_values_in_roi > 0
                    field_values_positive = field_values_in_roi[positive_mask]
                    
                    # Check if we have any positive values in the ROI
                    positive_count = len(field_values_positive)
                    if positive_count == 0:
                        self.logger.warning(f"Warning: Region {region_name} has no positive values")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None,
                            'focality': None,
                            'nodes_in_roi': 0,
                            'normal_mean_value': None,
                            'normal_max_value': None,
                            'normal_min_value': None,
                            'normal_focality': None
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        
                        continue
                    
                    # Calculate statistics on positive values only
                    min_value = np.min(field_values_positive)
                    max_value = np.max(field_values_positive)
                    
                    # Calculate mean value using node areas for proper averaging (only positive values)
                    try:
                        node_areas = gm_surf.nodes_areas()
                        if callable(node_areas):
                            self.logger.error(f"Region {region_name}: nodes_areas() returned a callable object")
                            raise TypeError(f"Region {region_name}: Expected node areas array, got callable object")
                        positive_node_areas = node_areas[roi_mask][positive_mask]
                    except Exception as e:
                        self.logger.error(f"Failed to get node areas for region {region_name}: {str(e)}")
                        self.logger.error(f"Node areas type: {type(node_areas) if 'node_areas' in locals() else 'undefined'}")
                        raise
                    mean_value = np.average(field_values_positive, weights=positive_node_areas)
                    
                    # Calculate focality (roi_average / whole_brain_average)
                    # Only include positive values in the whole brain average
                    # Use area-weighted averaging for consistency with other mesh analyses
                    whole_brain_positive_mask = field_values > 0
                    whole_brain_node_areas = node_areas[whole_brain_positive_mask]
                    whole_brain_average = np.average(field_values[whole_brain_positive_mask], weights=whole_brain_node_areas)
                    focality = mean_value / whole_brain_average
                    
                    # Log the whole brain average for debugging
                    self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")
                    
                    # Create result dictionary for this region with TI_max values
                    region_results = {
                        'mean_value': mean_value,
                        'max_value': max_value,
                        'min_value': min_value,
                        'focality': focality,
                        'nodes_in_roi': positive_count
                    }
                    
                    # Extract TI_normal values from normal mesh for this region
                    self.logger.debug(f"Extracting TI_normal values for region: {region_name}")
                    normal_field_values_positive, normal_statistics = self._extract_normal_field_values(roi_mask)
                    
                    # Add TI_normal statistics to region results if available
                    if normal_statistics is not None:
                        region_results.update(normal_statistics)
                        self.logger.debug(f"TI_normal values successfully added for region: {region_name}")
                    else:
                        self.logger.warning(f"TI_normal values not available for region: {region_name}")
                    
                    # Store in the overall results
                    results[region_name] = region_results
                    
                    # Generate visualizations if requested
                    if visualize:
                        self.logger.info(f"Generating 3D visualization for region: {region_name}")
                        # Generate 3D visualization and save directly to the region directory
                        self.visualizer.visualize_cortex_roi(
                            gm_surf=gm_surf,
                            roi_mask=roi_mask,
                            target_region=region_name,
                            field_values=field_values,
                            max_value=max_value,
                            output_dir=region_dir,
                            surface_mesh_path=self._surface_mesh_path
                        )

                        # Generate focality histogram for this region
                        if len(field_values_positive) > 0:
                            try:
                                self.logger.info(f"Generating focality histogram for region: {region_name}")
                                # Get node areas for volume weighting
                                node_areas = gm_surf.nodes_areas()
                                positive_node_areas = node_areas[roi_mask][positive_mask]

                                # Create a custom visualizer just for this region with the region directory as output
                                # Pass the main logger to avoid creating derivatives folder in region directory
                                region_visualizer = MeshVisualizer(region_dir, self.logger)

                                region_visualizer.generate_focality_histogram(
                                    whole_head_field_data=field_values,
                                    roi_field_data=field_values_positive,
                                    whole_head_element_sizes=node_areas,
                                    roi_element_sizes=positive_node_areas,
                                    region_name=region_name,
                                    roi_field_value=mean_value,
                                    data_type='node'
                                )
                            except Exception as e:
                                self.logger.warning(f"Could not generate focality histogram for {region_name}: {str(e)}")
                    
                except Exception as e:
                    self.logger.warning(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
                        'focality': None,
                        'nodes_in_roi': 0,
                        'normal_mean_value': None,
                        'normal_max_value': None,
                        'normal_min_value': None,
                        'normal_focality': None
                    }
            
            # Generate global visualization plots are disabled - only histograms are generated per region
            
            # Always generate and save summary CSV after all regions are processed
            self.logger.info("Saving whole-head analysis summary to CSV...")
            self.visualizer.save_whole_head_results_to_csv(results, atlas_type, 'node')
            
            return results
            
        finally:
            # Clean up
            try:
                del gm_surf
                del atlas
            except:
                pass


    def analyze_sphere(self, center_coordinates, radius, visualize=False, save_results=True):
        """
        Analyze a spherical region of interest from a mesh.
        
        Args:
            center_coordinates: List of [x, y, z] coordinates for the center of the sphere
            radius: Radius of the sphere in mm
            visualize: Whether to generate visualization files
            save_results: Whether to save individual CSV files (default: True, set False for batch processing)
            
        Returns:
            Dictionary containing analysis results or None if no nodes found
        """
        self.logger.info(f"Starting spherical ROI analysis (radius={radius}mm) at coordinates {center_coordinates}")
        
        try:
            # Generate surface mesh if needed and load it (for consistency with cortical analysis)
            surface_mesh_path = self._generate_surface_mesh()
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Check if field exists
            if self.field_name not in gm_surf.field:
                available_fields = list(gm_surf.field.keys())
                raise ValueError(f"Field '{self.field_name}' not found in surface mesh. Available fields: {available_fields}")
            
            # Get field values from surface mesh
            field_values = gm_surf.field[self.field_name].value
            
            # Create spherical ROI on surface mesh
            self.logger.info(f"Creating spherical ROI at {center_coordinates} with radius {radius}mm...")
            node_coords = gm_surf.nodes.node_coord
            
            # Calculate distance from each node to the center
            distances = np.sqrt(
                (node_coords[:, 0] - center_coordinates[0])**2 +
                (node_coords[:, 1] - center_coordinates[1])**2 + 
                (node_coords[:, 2] - center_coordinates[2])**2
            )
            
            # Create mask for nodes within radius
            roi_mask = distances <= radius
            
            # Check if we have any nodes in the ROI
            roi_nodes_count = np.sum(roi_mask)
            if roi_nodes_count == 0:
                self.logger.error(f"Analysis Failed: No nodes found in ROI at [{center_coordinates[0]}, {center_coordinates[1]}, {center_coordinates[2]}], r={radius}mm")
                self.logger.error("ROI is not capturing any grey matter surface nodes")
                self.logger.error("Suggestion: Adjust coordinates/radius or verify using freeview")
                return None
            
            self.logger.info(f"Found {roi_nodes_count} nodes in the ROI")
            self.logger.info("Calculating statistics...")
            
            # Get the field values within the ROI
            field_values_in_roi = field_values[roi_mask]
            
            # Filter for positive values in ROI (matching voxel analyzer behavior)
            positive_mask = field_values_in_roi > 0
            field_values_positive = field_values_in_roi[positive_mask]
            
            # Check if we have any positive values in the ROI
            positive_count = len(field_values_positive)
            if positive_count == 0:
                self.logger.warning(f"Warning: No positive values found in spherical ROI")
                return None
            
            self.logger.info(f"Found {positive_count} nodes with positive values in the ROI")
            self.logger.info("Calculating statistics...")
            
            # Calculate statistics on positive values only
            min_value = np.min(field_values_positive)
            max_value = np.max(field_values_positive)
            
            # Calculate mean value using node areas for proper averaging (only positive values)
            node_areas = gm_surf.nodes_areas()
            positive_node_areas = node_areas[roi_mask][positive_mask]
            mean_value = np.average(field_values_positive, weights=positive_node_areas)

            # Calculate focality (roi_average / whole_brain_average)
            # Only include positive values in the whole brain average
            # Use area-weighted averaging for consistency with ROI calculations
            whole_brain_positive_mask = field_values > 0
            whole_brain_node_areas = node_areas[whole_brain_positive_mask]
            whole_brain_average = np.average(field_values[whole_brain_positive_mask], weights=whole_brain_node_areas)
            focality = mean_value / whole_brain_average

            # Log the whole brain average for debugging
            self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")

            # Create results dictionary with TI_max values
            results = {
                'mean_value': mean_value,
                'max_value': max_value,
                'min_value': min_value,
                'nodes_in_roi': roi_nodes_count,
                'focality': focality
            }
            
            # Extract TI_normal values from normal mesh
            self.logger.info("Extracting TI_normal values from normal mesh...")
            normal_field_values_positive, normal_statistics = self._extract_normal_field_values(roi_mask)
            
            # Add TI_normal statistics to results if available
            if normal_statistics is not None:
                results.update(normal_statistics)
                self.logger.debug("TI_normal values successfully added to results")
            else:
                self.logger.warning("TI_normal values not available - results will only contain TI_max values")
            
            # Generate visualizations if requested
            if visualize:
                if self.visualizer is not None:
                    self.logger.info("Generating visualizations...")

                    # Generate focality histogram
                    try:
                        self.logger.info("Generating focality histogram for spherical ROI...")
                        self.visualizer.generate_focality_histogram(
                            whole_head_field_data=field_values,
                            roi_field_data=field_values_positive,
                            whole_head_element_sizes=node_areas,
                            roi_element_sizes=positive_node_areas,
                            region_name=f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}",
                            roi_field_value=mean_value,
                            data_type='node'
                        )
                    except Exception as e:
                        self.logger.warning(f"Could not generate focality histogram for spherical ROI: {str(e)}")
                    
                    # Create spherical ROI overlay visualization
                    # This creates a mesh file with the ROI highlighted
                    self.logger.info("Creating spherical ROI overlay visualization...")
                    viz_file = self.visualizer.visualize_spherical_roi(
                        gm_surf=gm_surf,
                        roi_mask=roi_mask,
                        center_coords=center_coordinates,
                        radius=radius,
                        field_values=field_values,
                        max_value=max_value,
                        output_dir=self.output_dir,
                        surface_mesh_path=surface_mesh_path
                    )
                    results['visualization_file'] = viz_file
                else:
                    self.logger.warning("Visualization requested but MeshVisualizer not available")
            
            # Calculate and save extra focality information for entire grey matter
            self.logger.info("Calculating focality metrics for entire grey matter...")
            focality_info = self._calculate_focality_metrics(
                field_values,  # Use entire surface data, not just ROI
                node_areas,    # Use all node areas, not just ROI
                f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}"
            )

            # Save results to CSV (only if save_results=True)
            if save_results and self.visualizer is not None:
                region_name = f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}"
                self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'node')
                
                # Save extra info CSV with focality data
                if focality_info:
                    self.visualizer.save_extra_info_to_csv(focality_info, 'spherical', region_name, 'node')
            elif save_results:
                self.logger.warning("Cannot save results to CSV - MeshVisualizer not available")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in spherical analysis: {str(e)}")
            raise

    def analyze_cortex(self, atlas_type, target_region, visualize=False):
        """
        Analyze a cortical region defined by an atlas.
        
        Args:
            atlas_type: Type of atlas to use (e.g., 'DK40', 'HCP_MMP1')
            target_region: Name of the region to analyze
            visualize: Whether to generate visualization files
            
        Returns:
            Dictionary containing analysis results
        """
        self.logger.info(f"Starting cortical analysis for region '{target_region}' using {atlas_type} atlas")
        
        try:
            # Generate surface mesh if needed
            surface_mesh_path = self._generate_surface_mesh()
            
            # Load the surface mesh
            self.logger.info("Loading surface mesh...")
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Load the atlas
            self.logger.info(f"Loading atlas {atlas_type}...")
            atlas = simnibs.subject_atlas(atlas_type, self.subject_dir)
            
            # Verify region exists in atlas
            if target_region not in atlas:
                available_regions = sorted(atlas.keys())
                raise ValueError(f"Region '{target_region}' not found in {atlas_type} atlas. Available regions: {available_regions}")
            
            # Get ROI mask for this region
            roi_mask = atlas[target_region]
            
            # Check if we have any nodes in the ROI
            roi_nodes_count = np.sum(roi_mask)
            if roi_nodes_count == 0:
                self.logger.warning(f"No nodes found in the specified region '{target_region}'")
                results = {
                    'mean_value': None,
                    'max_value': None,
                    'min_value': None,
                    'focality': None,
                    'normal_mean_value': None,
                    'normal_max_value': None,
                    'normal_min_value': None,
                    'normal_focality': None
                }
                
                # Save results to CSV even if empty
                self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
                
                return results
            
            # Get the field values within the ROI
            field_values = gm_surf.field[self.field_name].value
            field_values_in_roi = field_values[roi_mask]
            
            # Filter for positive values in ROI (matching voxel analyzer behavior)
            positive_mask = field_values_in_roi > 0
            field_values_positive = field_values_in_roi[positive_mask]
            
            # Check if we have any positive values in the ROI
            positive_count = len(field_values_positive)
            if positive_count == 0:
                self.logger.warning(f"Warning: Region {target_region} has no positive values")
                results = {
                    'mean_value': None,
                    'max_value': None,
                    'min_value': None,
                    'focality': None,
                    'normal_mean_value': None,
                    'normal_max_value': None,
                    'normal_min_value': None,
                    'normal_focality': None
                }
                
                # Save results to CSV even if empty
                self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
                
                return results
            
            # Calculate statistics on positive values only
            min_value = np.min(field_values_positive)
            max_value = np.max(field_values_positive)

            # Calculate mean value using node areas for proper averaging (only positive values)
            node_areas = gm_surf.nodes_areas()
            positive_node_areas = node_areas[roi_mask][positive_mask]
            mean_value = np.average(field_values_positive, weights=positive_node_areas)

            # Calculate focality (roi_average / whole_brain_average)
            # Only include positive values in the whole brain average
            # Use area-weighted averaging for consistency with ROI calculations
            whole_brain_positive_mask = field_values > 0
            whole_brain_node_areas = node_areas[whole_brain_positive_mask]
            whole_brain_average = np.average(field_values[whole_brain_positive_mask], weights=whole_brain_node_areas)
            focality = mean_value / whole_brain_average
            
            # Log the whole brain average for debugging
            self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")
            
            # Prepare the results with TI_max values
            results = {
                'mean_value': mean_value,
                'max_value': max_value,
                'min_value': min_value,
                'focality': focality
            }
            
            # Extract TI_normal values from normal mesh
            self.logger.info("Extracting TI_normal values from normal mesh...")
            normal_field_values_positive, normal_statistics = self._extract_normal_field_values(roi_mask)
            
            # Add TI_normal statistics to results if available
            if normal_statistics is not None:
                results.update(normal_statistics)
                self.logger.debug("TI_normal values successfully added to results")
            else:
                self.logger.warning("TI_normal values not available - results will only contain TI_max values")
            
            # Generate visualization if requested
            if visualize:
                self.logger.info("Generating visualizations...")
                # Generate focality histogram
                try:
                    self.logger.info(f"Generating focality histogram for region: {target_region}")
                    # Get node areas for volume weighting
                    node_areas = gm_surf.nodes_areas()
                    positive_node_areas = node_areas[roi_mask][positive_mask]

                    self.visualizer.generate_focality_histogram(
                        whole_head_field_data=field_values,
                        roi_field_data=field_values_positive,
                        whole_head_element_sizes=node_areas,
                        roi_element_sizes=positive_node_areas,
                        region_name=target_region,
                        roi_field_value=mean_value,
                        data_type='node'
                    )
                except Exception as e:
                    self.logger.warning(f"Could not generate focality histogram for {target_region}: {str(e)}")
                
                # Create region mesh visualization
                # This creates a mesh file with the ROI highlighted
                region_mesh_file = self.visualizer.visualize_cortex_roi(
                    gm_surf=gm_surf,
                    roi_mask=roi_mask,
                    target_region=target_region,
                    field_values=field_values,
                    max_value=max_value,
                    output_dir=self.output_dir,
                    surface_mesh_path=self._surface_mesh_path
                )
            
            # Calculate and save extra focality information for entire grey matter
            self.logger.info("Calculating focality metrics for entire grey matter...")
            focality_info = self._calculate_focality_metrics(
                field_values,  # Use entire surface data, not just ROI
                node_areas,    # Use all node areas, not just ROI
                target_region
            )
            
            # Save results to CSV
            self.visualizer.save_results_to_csv(results, 'cortical', target_region, 'node')
            
            # Save extra info CSV with focality data
            if focality_info:
                self.visualizer.save_extra_info_to_csv(focality_info, 'cortical', target_region, 'node')
            
            return results
                
        except Exception as e:
            self.logger.error(f"Error in cortical analysis: {str(e)}")
            raise

    def _calculate_focality_metrics(self, field_data, element_sizes, region_name):
        """
        Calculate focality metrics similar to ex-search mesh_field_analyzer.
        
        Args:
            field_data: Field values for entire grey matter surface (positive values only)
            element_sizes: Corresponding element sizes (node areas) for entire surface
            region_name: Name of the region being analyzed (for labeling purposes)
            
        Returns:
            dict: Dictionary containing focality metrics
        """
        try:
            # Standard parameters matching ex-search
            percentiles = [95, 99, 99.9]
            focality_cutoffs = [50, 75, 90, 95]
            
            if len(field_data) == 0:
                self.logger.warning(f"No field data available for focality calculation in {region_name}")
                return None
            
            # Remove NaN values
            valid_mask = ~np.isnan(field_data)
            data = field_data[valid_mask]
            sizes = element_sizes[valid_mask]
            
            if len(data) == 0:
                self.logger.warning(f"No valid field data after NaN removal for {region_name}")
                return None
            
            # Sort data and corresponding sizes
            sort_idx = np.argsort(data)
            data_sorted = data[sort_idx]
            sizes_sorted = sizes[sort_idx]
            
            # Calculate cumulative volumes (element sizes)
            cumulative_sizes = np.cumsum(sizes_sorted)
            total_size = cumulative_sizes[-1]
            normalized_cumulative = cumulative_sizes / total_size
            
            # Calculate percentiles and their values
            percentile_values = []
            for percentile in percentiles:
                # Find index where cumulative size exceeds percentile
                threshold_idx = np.searchsorted(normalized_cumulative, percentile/100.0)
                if threshold_idx >= len(data_sorted):
                    threshold_idx = len(data_sorted) - 1
                
                percentile_value = data_sorted[threshold_idx]
                percentile_values.append(float(percentile_value))
            
            # Calculate focality (area above thresholds)
            # Use 99.9 percentile as reference (index 2)
            focality_values = []
            if len(percentile_values) > 2:
                reference_value = percentile_values[2]  # 99.9 percentile
                
                for cutoff in focality_cutoffs:
                    threshold = (cutoff / 100.0) * reference_value
                    above_threshold = data >= threshold
                    area = np.sum(sizes[above_threshold]) if np.any(above_threshold) else 0.0
                    # Convert from mm² to cm² for consistency with ex-search
                    focality_values.append(float(area / 100.0))
            else:
                focality_values = [0.0] * len(focality_cutoffs)
            
            # Prepare results
            results = {
                'region_name': region_name,
                'field_name': self.field_name,
                'max_value': float(np.max(data)),
                'min_value': float(np.min(data)),
                'percentile_95': percentile_values[0] if len(percentile_values) > 0 else 0.0,
                'percentile_99': percentile_values[1] if len(percentile_values) > 1 else 0.0,
                'percentile_99_9': percentile_values[2] if len(percentile_values) > 2 else 0.0,
                'focality_50': focality_values[0] if len(focality_values) > 0 else 0.0,
                'focality_75': focality_values[1] if len(focality_values) > 1 else 0.0,
                'focality_90': focality_values[2] if len(focality_values) > 2 else 0.0,
                'focality_95': focality_values[3] if len(focality_values) > 3 else 0.0,
                'total_area_cm2': float(total_size / 100.0),  # Convert mm² to cm²
                'num_elements': len(data)
            }
            
            self.logger.info(f"Focality metrics calculated for {region_name}: 99.9%={percentile_values[2]:.4f}, focality_95={focality_values[3]:.4f} cm²")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error calculating focality metrics for {region_name}: {str(e)}")
            return None

    def get_grey_matter_statistics(self):
        """
        Calculate grey matter field statistics from the GM surface (central layer).
        
        For mesh analysis, tries to use the same GM surface as other analyses for consistency.
        Falls back to original mesh if surface generation fails to ensure robustness.
        
        Returns:
            dict: Dictionary containing grey matter statistics (mean, max, min)
        """
        self.logger.info("Calculating grey matter field statistics from GM surface (central layer)...")
        
        try:
            # Try to generate and load GM surface mesh (same as other mesh analyses)
            surface_mesh_path = self._generate_surface_mesh()
            gm_surf = simnibs.read_msh(surface_mesh_path)
            
            # Check if field exists
            if self.field_name not in gm_surf.field:
                available_fields = list(gm_surf.field.keys())
                raise ValueError(f"Field '{self.field_name}' not found in GM surface. Available fields: {available_fields}")
            
            # Get field values from GM surface (same source as other mesh analyses)
            field_values = gm_surf.field[self.field_name].value
            
            # Filter for positive values only (matching ROI analysis behavior)
            positive_mask = field_values > 0
            field_values_positive = field_values[positive_mask]
            
            # Check if we have any positive values
            if len(field_values_positive) == 0:
                self.logger.warning("No positive values found in GM surface")
                return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
            
            # Calculate statistics using area-weighted averaging (consistent with other mesh analyses)
            node_areas = gm_surf.nodes_areas()
            positive_node_areas = node_areas[positive_mask]
            grey_mean = np.average(field_values_positive, weights=positive_node_areas)
            grey_max = np.max(field_values_positive)
            grey_min = np.min(field_values_positive)
            
            self.logger.info(f"Grey matter statistics from GM surface for field '{self.field_name}' (positive values only): "
                           f"mean={grey_mean:.6f}, max={grey_max:.6f}, min={grey_min:.6f}")
            self.logger.info(f"Total nodes with positive values: {len(field_values_positive)}")
            
            return {
                'grey_mean': float(grey_mean),
                'grey_max': float(grey_max),
                'grey_min': float(grey_min)
            }
            
        except Exception as e:
            self.logger.warning(f"GM surface generation failed: {str(e)}")
            self.logger.info("Falling back to original mesh for grey matter statistics...")
            
            # Fallback: Use original mesh if surface generation fails
            try:
                field_mesh = simnibs.read_msh(self.field_mesh_path)
                
                if self.field_name not in field_mesh.field:
                    available_fields = list(field_mesh.field.keys())
                    raise ValueError(f"Field '{self.field_name}' not found in original mesh. Available fields: {available_fields}")
                
                field_values = field_mesh.field[self.field_name].value
                positive_mask = field_values > 0
                field_values_positive = field_values[positive_mask]
                
                if len(field_values_positive) == 0:
                    self.logger.warning("No positive values found in original mesh")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
                
                # Use simple averaging for volume mesh fallback
                grey_mean = np.mean(field_values_positive)
                grey_max = np.max(field_values_positive)
                grey_min = np.min(field_values_positive)
                
                self.logger.info(f"Grey matter statistics from original mesh (fallback) for field '{self.field_name}': "
                               f"mean={grey_mean:.6f}, max={grey_max:.6f}, min={grey_min:.6f}")
                
                return {
                    'grey_mean': float(grey_mean),
                    'grey_max': float(grey_max),
                    'grey_min': float(grey_min)
                }
                
            except Exception as fallback_error:
                self.logger.error(f"Fallback to original mesh also failed: {str(fallback_error)}")
                return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
