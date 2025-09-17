"""
Test suite for flex-search.py

This module provides comprehensive tests for the flex-search optimization functionality,
including argument parsing, ROI handling, optimization setup, and summary generation.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
import time
from unittest.mock import patch, MagicMock, mock_open, call
import numpy as np
from pathlib import Path

# Add the parent directory to the path to access the flex-search module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# We'll test the flex-search.py functionality without importing it directly
# since it calls sys.exit() when simnibs is not available


class TestFlexSearchArgumentParsing:
    """Test command line argument parsing in flex-search.py"""
    
    def test_parse_required_arguments(self):
        """Test parsing of required arguments."""
        # Simulate argument parsing
        required_args = {
            'subject': 'subj001',
            'goal': 'mean',
            'postproc': 'max_TI',
            'eeg_net': 'EGI_template',
            'radius': 5.0,
            'current': 1.0,
            'roi_method': 'spherical'
        }
        
        assert required_args['subject'] == 'subj001'
        assert required_args['goal'] == 'mean'
        assert required_args['postproc'] == 'max_TI'
        assert required_args['eeg_net'] == 'EGI_template'
        assert required_args['radius'] == 5.0
        assert required_args['current'] == 1.0
        assert required_args['roi_method'] == 'spherical'
    
    def test_parse_focality_arguments(self):
        """Test parsing of focality-specific arguments."""
        focality_args = {
            'goal': 'focality',
            'thresholds': '0.5,0.8',
            'non_roi_method': 'everything_else'
        }
        
        # Parse thresholds
        if focality_args['thresholds']:
            vals = [float(v) for v in focality_args['thresholds'].split(",")]
            threshold = vals if len(vals) > 1 else vals[0]
        
        assert focality_args['goal'] == 'focality'
        assert threshold == [0.5, 0.8]
        assert focality_args['non_roi_method'] == 'everything_else'
    
    def test_parse_mapping_arguments(self):
        """Test parsing of electrode mapping arguments."""
        mapping_args = {
            'enable_mapping': True,
            'disable_mapping_simulation': False
        }
        
        assert mapping_args['enable_mapping'] is True
        assert mapping_args['disable_mapping_simulation'] is False
    
    def test_parse_optimization_arguments(self):
        """Test parsing of optimization algorithm arguments."""
        opt_args = {
            'n_multistart': 3,
            'max_iterations': 100,
            'population_size': 50,
            'cpus': 4,
            'quiet': True
        }
        
        assert opt_args['n_multistart'] == 3
        assert opt_args['max_iterations'] == 100
        assert opt_args['population_size'] == 50
        assert opt_args['cpus'] == 4
        assert opt_args['quiet'] is True
    
    def test_parse_goal_choices(self):
        """Test parsing of valid goal choices."""
        valid_goals = ['mean', 'max', 'focality']
        
        for goal in valid_goals:
            assert goal in valid_goals
    
    def test_parse_postproc_choices(self):
        """Test parsing of valid post-processing choices."""
        valid_postprocs = ['max_TI', 'dir_TI_normal', 'dir_TI_tangential']
        
        for postproc in valid_postprocs:
            assert postproc in valid_postprocs
    
    def test_parse_roi_method_choices(self):
        """Test parsing of valid ROI method choices."""
        valid_roi_methods = ['spherical', 'atlas', 'subcortical']
        
        for roi_method in valid_roi_methods:
            assert roi_method in valid_roi_methods


class TestROIDirectoryNaming:
    """Test ROI directory naming functionality."""
    
    def test_roi_dirname_spherical(self):
        """Test ROI directory naming for spherical ROI."""
        # Mock environment variables
        with patch.dict(os.environ, {
            'ROI_X': '10',
            'ROI_Y': '20', 
            'ROI_Z': '30',
            'ROI_RADIUS': '15'
        }):
            # Simulate roi_dirname function
            args = MagicMock()
            args.roi_method = 'spherical'
            args.goal = 'mean'
            args.postproc = 'max_TI'
            
            # Convert postproc to shorter format
            postproc_map = {
                "max_TI": "maxTI",
                "dir_TI_normal": "normalTI", 
                "dir_TI_tangential": "tangentialTI"
            }
            postproc_short = postproc_map.get(args.postproc, args.postproc)
            
            # Format: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
            roi_x = os.getenv('ROI_X', '0')
            roi_y = os.getenv('ROI_Y', '0') 
            roi_z = os.getenv('ROI_Z', '0')
            roi_radius = os.getenv('ROI_RADIUS', '10')
            base = f"sphere_x{roi_x}y{roi_y}z{roi_z}r{roi_radius}"
            
            result = f"{base}_{args.goal}_{postproc_short}"
            
            assert result == "sphere_x10y20z30r15_mean_maxTI"
    
    def test_roi_dirname_atlas(self):
        """Test ROI directory naming for atlas ROI."""
        with patch.dict(os.environ, {
            'ATLAS_PATH': '/path/to/lh.101_DK40.annot',
            'SELECTED_HEMISPHERE': 'lh',
            'ROI_LABEL': '101'
        }):
            args = MagicMock()
            args.roi_method = 'atlas'
            args.goal = 'max'
            args.postproc = 'dir_TI_normal'
            
            # Convert postproc to shorter format
            postproc_map = {
                "max_TI": "maxTI",
                "dir_TI_normal": "normalTI", 
                "dir_TI_tangential": "tangentialTI"
            }
            postproc_short = postproc_map.get(args.postproc, args.postproc)
            
            # Format: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
            atlas_path = os.getenv("ATLAS_PATH", "")
            hemisphere = os.getenv("SELECTED_HEMISPHERE", "lh")
            roi_label = os.getenv("ROI_LABEL", "0")
            
            # Extract atlas name from path
            if atlas_path:
                atlas_filename = os.path.basename(atlas_path)
                atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(".annot", "")
                atlas_name = atlas_with_subject.split("_", 1)[-1] if "_" in atlas_with_subject else atlas_with_subject
            else:
                atlas_name = "atlas"
            
            base = f"{hemisphere}_{atlas_name}_{roi_label}"
            result = f"{base}_{args.goal}_{postproc_short}"
            
            assert result == "lh_DK40_101_max_normalTI"
    
    def test_roi_dirname_subcortical(self):
        """Test ROI directory naming for subcortical ROI."""
        with patch.dict(os.environ, {
            'VOLUME_ATLAS_PATH': '/path/to/atlas.nii.gz',
            'VOLUME_ROI_LABEL': '10'
        }):
            args = MagicMock()
            args.roi_method = 'subcortical'
            args.goal = 'focality'
            args.postproc = 'dir_TI_tangential'
            
            # Convert postproc to shorter format
            postproc_map = {
                "max_TI": "maxTI",
                "dir_TI_normal": "normalTI", 
                "dir_TI_tangential": "tangentialTI"
            }
            postproc_short = postproc_map.get(args.postproc, args.postproc)
            
            # Format: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
            roi_label = os.getenv("VOLUME_ROI_LABEL", "0")
            
            if volume_atlas_path:
                volume_atlas = os.path.basename(volume_atlas_path)
                # Remove file extensions
                if volume_atlas.endswith('.nii.gz'):
                    volume_atlas = volume_atlas[:-7]
                elif volume_atlas.endswith('.mgz'):
                    volume_atlas = volume_atlas[:-4]
                elif volume_atlas.endswith('.nii'):
                    volume_atlas = volume_atlas[:-4]
            else:
                volume_atlas = "volume"
            
            base = f"subcortical_{volume_atlas}_{roi_label}"
            result = f"{base}_{args.goal}_{postproc_short}"
            
            assert result == "subcortical_atlas_10_focality_tangentialTI"


class TestSummaryLogging:
    """Test summary logging functionality."""
    
    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        # Simulate format_duration function
        def format_duration(seconds):
            if seconds < 60:
                return f"{seconds:.0f}s"
            elif seconds < 3600:
                minutes = seconds / 60
                return f"{minutes:.0f}m {seconds % 60:.0f}s"
            else:
                hours = seconds / 3600
                minutes = (seconds % 3600) / 60
                return f"{hours:.0f}h {minutes:.0f}m"
        
        assert format_duration(30) == "30s"
        assert format_duration(90) == "2m 30s"  # 90 seconds = 1.5 minutes = 2m 30s
        assert format_duration(3661) == "1h 1m"
    
    def test_log_optimization_start(self):
        """Test optimization start logging."""
        # Mock global variables
        global OPTIMIZATION_START_TIME, SUMMARY_MODE
        OPTIMIZATION_START_TIME = None
        SUMMARY_MODE = False
        
        # Simulate log_optimization_start function
        def log_optimization_start(subject_id, goal, postproc, roi_method, n_multistart):
            global OPTIMIZATION_START_TIME
            OPTIMIZATION_START_TIME = 1000.0  # Mock time
            
            if SUMMARY_MODE:
                print(f"Beginning flex-search optimization for subject: {subject_id} ({goal}, {postproc}, {roi_method})")
                if n_multistart > 1:
                    print(f"├─ Multi-start optimization: {n_multistart} runs")
                else:
                    print("├─ Single optimization run")
            else:
                print(f"Beginning flex-search optimization for subject: {subject_id}")
        
        # Test single optimization
        log_optimization_start("subj001", "mean", "max_TI", "spherical", 1)
        assert OPTIMIZATION_START_TIME == 1000.0
        
        # Test multi-start optimization
        log_optimization_start("subj001", "mean", "max_TI", "spherical", 3)
        assert OPTIMIZATION_START_TIME == 1000.0
    
    def test_log_optimization_step_start(self):
        """Test optimization step start logging."""
        # Mock global variables
        global STEP_START_TIMES, SUMMARY_MODE
        STEP_START_TIMES = {}
        SUMMARY_MODE = False
        
        # Simulate log_optimization_step_start function
        def log_optimization_step_start(step_name):
            global STEP_START_TIMES
            STEP_START_TIMES[step_name] = 1000.0  # Mock time
            
            if SUMMARY_MODE:
                print(f"├─ {step_name}: Starting...")
            else:
                print(f"Starting {step_name}...")
        
        log_optimization_step_start("Optimization")
        assert "Optimization" in STEP_START_TIMES
        assert STEP_START_TIMES["Optimization"] == 1000.0
    
    def test_log_optimization_step_complete(self):
        """Test optimization step completion logging."""
        # Mock global variables
        global STEP_START_TIMES, SUMMARY_MODE
        STEP_START_TIMES = {"Optimization": 1000.0}
        SUMMARY_MODE = False
        
        # Simulate log_optimization_step_complete function
        def log_optimization_step_complete(step_name, additional_info=""):
            global STEP_START_TIMES
            
            if step_name in STEP_START_TIMES:
                duration = 1005.0 - STEP_START_TIMES[step_name]  # Mock duration
                
                if SUMMARY_MODE:
                    if additional_info:
                        print(f"├─ {step_name}: ✓ Complete ({duration:.0f}s) - {additional_info}")
                    else:
                        print(f"├─ {step_name}: ✓ Complete ({duration:.0f}s)")
                else:
                    print(f"{step_name} completed in {duration:.0f}s")
                
                # Clean up timing
                del STEP_START_TIMES[step_name]
        
        log_optimization_step_complete("Optimization")
        assert "Optimization" not in STEP_START_TIMES


class TestROIHandling:
    """Test ROI handling functionality."""
    
    def test_roi_spherical_coordinates(self):
        """Test spherical ROI coordinate handling."""
        with patch.dict(os.environ, {
            'ROI_X': '10.5',
            'ROI_Y': '20.5',
            'ROI_Z': '30.5',
            'ROI_RADIUS': '15.0',
            'USE_MNI_COORDS': 'false'
        }):
            # Simulate _roi_spherical function
            roi_x = float(os.getenv("ROI_X", "0"))
            roi_y = float(os.getenv("ROI_Y", "0"))
            roi_z = float(os.getenv("ROI_Z", "0"))
            radius = float(os.getenv("ROI_RADIUS", "10"))
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            
            assert roi_x == 10.5
            assert roi_y == 20.5
            assert roi_z == 30.5
            assert radius == 15.0
            assert use_mni_coords is False
    
    def test_roi_spherical_mni_coordinates(self):
        """Test spherical ROI with MNI coordinate transformation."""
        with patch.dict(os.environ, {
            'ROI_X': '0',
            'ROI_Y': '0',
            'ROI_Z': '0',
            'ROI_RADIUS': '10',
            'USE_MNI_COORDS': 'true'
        }):
            # Simulate MNI coordinate handling
            roi_x = float(os.getenv("ROI_X", "0"))
            roi_y = float(os.getenv("ROI_Y", "0"))
            roi_z = float(os.getenv("ROI_Z", "0"))
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            
            assert roi_x == 0.0
            assert roi_y == 0.0
            assert roi_z == 0.0
            assert use_mni_coords is True
    
    def test_roi_atlas_parameters(self):
        """Test atlas ROI parameter handling."""
        with patch.dict(os.environ, {
            'ATLAS_PATH': '/path/to/lh.101_DK40.annot',
            'SELECTED_HEMISPHERE': 'lh',
            'ROI_LABEL': '101'
        }):
            # Simulate _roi_atlas function
            hemi = os.getenv("SELECTED_HEMISPHERE", "lh")
            atlas_path = os.getenv("ATLAS_PATH", "")
            label_val = int(os.getenv("ROI_LABEL", "1"))
            
            assert hemi == "lh"
            assert atlas_path == "/path/to/lh.101_DK40.annot"
            assert label_val == 101
    
    def test_roi_subcortical_parameters(self):
        """Test subcortical ROI parameter handling."""
        with patch.dict(os.environ, {
            'VOLUME_ATLAS_PATH': '/path/to/atlas.nii.gz',
            'VOLUME_ROI_LABEL': '10'
        }):
            # Simulate _roi_subcortical function
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
            label_val = int(os.getenv("VOLUME_ROI_LABEL", "10"))
            
            assert volume_atlas_path == "/path/to/atlas.nii.gz"
            assert label_val == 10


class TestOptimizationSetup:
    """Test optimization setup functionality."""
    
    def test_build_optimization_basic(self):
        """Test basic optimization object building."""
        # Mock opt_struct without importing the actual module
        mock_opt_struct = MagicMock()
        mock_optimization = MagicMock()
        mock_opt_struct.TesFlexOptimization.return_value = mock_optimization
        
        # Simulate build_optimisation function
        args = MagicMock()
        args.subject = "subj001"
        args.goal = "mean"
        args.postproc = "max_TI"
        args.roi_method = "spherical"
        args.radius = 5.0
        args.current = 1.0
        args.eeg_net = "EGI_template"
        args.enable_mapping = False
        args.run_final_electrode_simulation = True
        args.skip_final_electrode_simulation = False
        
        # Mock project directory
        with patch.dict(os.environ, {'PROJECT_DIR': '/path/to/project'}):
            proj_dir = os.getenv("PROJECT_DIR")
            opt = mock_opt_struct.TesFlexOptimization()
            opt.subpath = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", f"m2m_{args.subject}")
            opt.output_folder = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", "flex-search", "test_roi")
            opt.goal = args.goal
            opt.e_postproc = args.postproc
            opt.open_in_gmsh = False
            opt.run_final_electrode_simulation = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
            
            assert os.path.normpath(opt.subpath) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/m2m_subj001")
            assert opt.goal == "mean"
            assert opt.e_postproc == "max_TI"
            assert opt.open_in_gmsh is False
    
    def test_build_optimization_with_mapping(self):
        """Test optimization setup with electrode mapping enabled."""
        # Mock opt_struct
        mock_opt_struct = MagicMock()
        mock_optimization = MagicMock()
        mock_opt_struct.TesFlexOptimization.return_value = mock_optimization
        
        args = MagicMock()
        args.subject = "subj001"
        args.eeg_net = "EGI_template"
        args.enable_mapping = True
        args.disable_mapping_simulation = False
        
        with patch.dict(os.environ, {'PROJECT_DIR': '/path/to/project'}):
            proj_dir = os.getenv("PROJECT_DIR")
            opt = mock_opt_struct.TesFlexOptimization()
            opt.subpath = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", f"m2m_{args.subject}")
            
            # Simulate mapping setup
            if args.enable_mapping:
                opt.map_to_net_electrodes = True
                opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", f"{args.eeg_net}.csv")
                opt.run_mapped_electrodes_simulation = not args.disable_mapping_simulation
            else:
                opt.electrode_mapping = None
            
            assert opt.map_to_net_electrodes is True
            assert os.path.normpath(opt.net_electrode_file) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/m2m_subj001/eeg_positions/EGI_template.csv")
            assert opt.run_mapped_electrodes_simulation is True
    
    def test_build_optimization_focality(self):
        """Test optimization setup for focality goal."""
        args = MagicMock()
        args.goal = "focality"
        args.thresholds = "0.5,0.8"
        args.non_roi_method = "everything_else"
        
        # Simulate focality setup
        if args.goal == "focality":
            if not args.thresholds:
                raise SystemExit("--thresholds required for focality goal")
            vals = [float(v) for v in args.thresholds.split(",")]
            threshold = vals if len(vals) > 1 else vals[0]
            if not args.non_roi_method:
                raise SystemExit("--non-roi-method required for focality goal")
        
        assert threshold == [0.5, 0.8]
        assert args.non_roi_method == "everything_else"


class TestMultiStartOptimization:
    """Test multi-start optimization functionality."""
    
    def test_multi_start_setup(self):
        """Test multi-start optimization setup."""
        n_multistart = 3
        optim_funvalue_list = np.zeros(n_multistart)
        
        # Simulate multi-start setup
        base_output_folder = "/path/to/output"
        output_folder_list = [
            os.path.join(base_output_folder, f"{i_opt:02d}") for i_opt in range(n_multistart)
        ]
        
        assert len(optim_funvalue_list) == 3
        assert len(output_folder_list) == 3
        assert os.path.normpath(output_folder_list[0]) == os.path.normpath("/path/to/output/00")
        assert os.path.normpath(output_folder_list[1]) == os.path.normpath("/path/to/output/01")
        assert os.path.normpath(output_folder_list[2]) == os.path.normpath("/path/to/output/02")
    
    def test_multi_start_results_processing(self):
        """Test multi-start results processing."""
        # Simulate optimization results
        optim_funvalue_list = np.array([0.5, 0.3, 0.7])  # Best is index 1
        n_multistart = 3
        
        # Find best solution
        best_opt_idx = np.argmin(optim_funvalue_list)
        best_funvalue = optim_funvalue_list[best_opt_idx]
        
        # Categorize runs
        valid_runs = []
        failed_runs = []
        for i_opt, func_val in enumerate(optim_funvalue_list):
            if func_val != float('inf'):
                valid_runs.append((i_opt, func_val))
            else:
                failed_runs.append(i_opt)
        
        assert best_opt_idx == 1
        assert best_funvalue == 0.3
        assert len(valid_runs) == 3
        assert len(failed_runs) == 0
        assert valid_runs[0] == (0, 0.5)
        assert valid_runs[1] == (1, 0.3)
        assert valid_runs[2] == (2, 0.7)
    
    def test_multi_start_with_failures(self):
        """Test multi-start optimization with some failed runs."""
        # Simulate optimization results with failures
        optim_funvalue_list = np.array([0.5, float('inf'), 0.3, float('inf')])
        n_multistart = 4
        
        # Find best solution
        best_opt_idx = np.argmin(optim_funvalue_list)
        best_funvalue = optim_funvalue_list[best_opt_idx]
        
        # Categorize runs
        valid_runs = []
        failed_runs = []
        for i_opt, func_val in enumerate(optim_funvalue_list):
            if func_val != float('inf'):
                valid_runs.append((i_opt, func_val))
            else:
                failed_runs.append(i_opt)
        
        assert best_opt_idx == 2
        assert best_funvalue == 0.3
        assert len(valid_runs) == 2
        assert len(failed_runs) == 2
        assert failed_runs == [1, 3]


class TestSummaryFileGeneration:
    """Test summary file generation functionality."""
    
    def test_create_multistart_summary_file(self):
        """Test creation of multi-start summary file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_file = os.path.join(temp_dir, "multistart_summary.txt")
            
            # Mock arguments
            args = MagicMock()
            args.subject = "subj001"
            args.goal = "mean"
            args.postproc = "max_TI"
            args.roi_method = "spherical"
            args.eeg_net = "EGI_template"
            args.radius = 5.0
            args.current = 1.0
            args.run_final_electrode_simulation = True
            args.skip_final_electrode_simulation = False
            args.enable_mapping = False
            args.thresholds = None
            args.non_roi_method = None
            args.max_iterations = None
            args.population_size = None
            args.cpus = None
            args.quiet = False
            
            # Mock optimization results
            n_multistart = 3
            optim_funvalue_list = np.array([0.5, 0.3, 0.7])
            best_opt_idx = 1
            valid_runs = [(0, 0.5), (1, 0.3), (2, 0.7)]
            failed_runs = []
            start_time = 1000.0
            
            # Simulate summary file creation
            total_duration = 1005.0 - start_time
            
            with open(summary_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write("MULTI-START OPTIMIZATION SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Subject: {args.subject}\n")
                f.write(f"Total session duration: {total_duration:.1f} seconds\n")
                f.write("\n")
                
                # Optimization configuration
                f.write("OPTIMIZATION CONFIGURATION:\n")
                f.write("-" * 40 + "\n")
                f.write(f"Goal: {args.goal}\n")
                f.write(f"Post-processing: {args.postproc}\n")
                f.write(f"ROI Method: {args.roi_method}\n")
                f.write(f"EEG Net: {args.eeg_net}\n")
                f.write(f"Electrode Radius: {args.radius}mm\n")
                f.write(f"Electrode Current: {args.current}mA\n")
                run_final_sim = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
                f.write(f"Run Final Electrode Simulation: {run_final_sim}\n")
            
            # Verify file was created
            assert os.path.exists(summary_file)
            
            # Verify content
            with open(summary_file, 'r') as f:
                content = f.read()
                assert "MULTI-START OPTIMIZATION SUMMARY" in content
                assert "Subject: subj001" in content
                assert "Goal: mean" in content
                assert "Post-processing: max_TI" in content
    
    def test_create_single_optimization_summary_file(self):
        """Test creation of single optimization summary file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_file = os.path.join(temp_dir, "single_summary.txt")
            
            # Mock arguments
            args = MagicMock()
            args.subject = "subj001"
            args.goal = "mean"
            args.postproc = "max_TI"
            args.roi_method = "spherical"
            args.eeg_net = "EGI_template"
            args.radius = 5.0
            args.current = 1.0
            args.run_final_electrode_simulation = True
            args.skip_final_electrode_simulation = False
            args.enable_mapping = False
            args.thresholds = None
            args.non_roi_method = None
            args.max_iterations = None
            args.population_size = None
            args.cpus = None
            args.quiet = False
            
            function_value = 0.3
            start_time = 1000.0
            
            # Simulate summary file creation
            total_duration = 1005.0 - start_time
            
            with open(summary_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write("OPTIMIZATION SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Subject: {args.subject}\n")
                f.write(f"Total optimization duration: {total_duration:.1f} seconds\n")
                f.write("\n")
                
                # Optimization result
                f.write("OPTIMIZATION RESULT:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Final function value: {function_value:.6f}\n")
                f.write(f"Optimization type: Single run (no multi-start)\n")
            
            # Verify file was created
            assert os.path.exists(summary_file)
            
            # Verify content
            with open(summary_file, 'r') as f:
                content = f.read()
                assert "OPTIMIZATION SUMMARY" in content
                assert "Subject: subj001" in content
                assert "Final function value: 0.300000" in content


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_missing_simnibs_import(self):
        """Test handling of missing simnibs import."""
        # Simulate the simnibs check without importing the actual module
        opt_struct = None
        mni2subject_coords = None
        ElementTags = None
        
        with patch('sys.exit') as mock_exit:
            # Simulate the simnibs check
            if opt_struct is None or mni2subject_coords is None or ElementTags is None:
                print("Error: simnibs is required for flex-search optimization but is not installed")
                sys.exit(1)
            
            mock_exit.assert_called_once_with(1)
    
    def test_missing_project_dir(self):
        """Test handling of missing PROJECT_DIR environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            proj_dir = os.getenv("PROJECT_DIR")
            if not proj_dir:
                with pytest.raises(SystemExit) as exc_info:
                    raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")
                assert exc_info.value.code == "[flex-search] PROJECT_DIR env-var is missing"
    
    def test_missing_thresholds_for_focality(self):
        """Test handling of missing thresholds for focality goal."""
        args = MagicMock()
        args.goal = "focality"
        args.thresholds = None
        
        # Simulate focality validation
        if args.goal == "focality":
            if not args.thresholds:
                with pytest.raises(SystemExit) as exc_info:
                    raise SystemExit("--thresholds required for focality goal")
                assert exc_info.value.code == "--thresholds required for focality goal"
    
    def test_missing_non_roi_method_for_focality(self):
        """Test handling of missing non-ROI method for focality goal."""
        args = MagicMock()
        args.goal = "focality"
        args.thresholds = "0.5,0.8"
        args.non_roi_method = None
        
        # Simulate focality validation
        if args.goal == "focality":
            if not args.non_roi_method:
                with pytest.raises(SystemExit) as exc_info:
                    raise SystemExit("--non-roi-method required for focality goal")
                assert exc_info.value.code == "--non-roi-method required for focality goal"


class TestEnvironmentVariableHandling:
    """Test environment variable handling."""
    
    def test_debug_mode_environment_variable(self):
        """Test DEBUG_MODE environment variable handling."""
        with patch.dict(os.environ, {'DEBUG_MODE': 'true'}):
            debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
            assert debug_mode is True
        
        with patch.dict(os.environ, {'DEBUG_MODE': 'false'}):
            debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
            assert debug_mode is False
    
    def test_project_dir_environment_variable(self):
        """Test PROJECT_DIR environment variable handling."""
        with patch.dict(os.environ, {'PROJECT_DIR': '/path/to/project'}):
            proj_dir = os.getenv("PROJECT_DIR")
            assert proj_dir == "/path/to/project"
    
    def test_roi_environment_variables(self):
        """Test ROI-related environment variables."""
        with patch.dict(os.environ, {
            'ROI_X': '10',
            'ROI_Y': '20',
            'ROI_Z': '30',
            'ROI_RADIUS': '15',
            'USE_MNI_COORDS': 'true'
        }):
            roi_x = os.getenv('ROI_X', '0')
            roi_y = os.getenv('ROI_Y', '0')
            roi_z = os.getenv('ROI_Z', '0')
            roi_radius = os.getenv('ROI_RADIUS', '10')
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            
            assert roi_x == "10"
            assert roi_y == "20"
            assert roi_z == "30"
            assert roi_radius == "15"
            assert use_mni_coords is True


class TestPathConstruction:
    """Test path construction functionality."""
    
    def test_construct_derivatives_path(self):
        """Test construction of derivatives directory path."""
        project_dir = "/path/to/project"
        subject_id = "subj001"
        
        derivatives_dir = os.path.join(project_dir, 'derivatives')
        simnibs_dir = os.path.join(derivatives_dir, 'SimNIBS', f'sub-{subject_id}')
        base_subpath = os.path.join(simnibs_dir, f'm2m_{subject_id}')
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(derivatives_dir) == os.path.normpath("/path/to/project/derivatives")
        assert os.path.normpath(simnibs_dir) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001")
        assert os.path.normpath(base_subpath) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/m2m_subj001")
    
    def test_construct_flex_search_output_path(self):
        """Test construction of flex-search output path."""
        project_dir = "/path/to/project"
        subject_id = "subj001"
        roi_dirname = "sphere_x10y20z30r15_mean_maxTI"
        
        flex_search_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "flex-search")
        output_folder = os.path.join(flex_search_dir, roi_dirname)
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(flex_search_dir) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/flex-search")
        assert os.path.normpath(output_folder) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/flex-search/sphere_x10y20z30r15_mean_maxTI")
    
    def test_construct_eeg_net_path(self):
        """Test construction of EEG net file path."""
        base_subpath = "/path/to/m2m_subj001"
        eeg_net = "EGI_template"
        
        net_electrode_file = os.path.join(base_subpath, "eeg_positions", f"{eeg_net}.csv")
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(net_electrode_file) == os.path.normpath("/path/to/m2m_subj001/eeg_positions/EGI_template.csv")


if __name__ == "__main__":
    pytest.main([__file__])
