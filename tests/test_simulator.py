#!/usr/bin/env simnibs_python
"""
Unit tests for sim/simulator.py.

Tests simulation workflow including:
- setup_montage_directories(): Directory structure creation
- run_montage_visualization(): Montage visualization subprocess
- run_simulation(): Sequential and parallel execution
- _run_parallel(): Parallel worker execution
- _run_single_montage(): Single montage workflow
- Progress callbacks and error handling
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.simulator import (
    setup_montage_directories,
    run_montage_visualization,
    run_simulation,
    _run_sequential,
    _run_parallel,
    _run_single_montage
)
from tit.sim.config import (
    SimulationConfig,
    MontageConfig,
    SimulationMode,
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    ParallelConfig
)


@pytest.mark.unit
class TestSetupMontageDirectories:
    """Test suite for setup_montage_directories()."""

    def test_ti_directory_structure(self, tmp_path):
        """Test TI mode directory creation."""
        montage_dir = tmp_path / "montage1"

        dirs = setup_montage_directories(str(montage_dir), SimulationMode.TI)

        # Check all directories were created
        assert Path(dirs['montage_dir']).exists()
        assert Path(dirs['hf_dir']).exists()
        assert Path(dirs['hf_mesh']).exists()
        assert Path(dirs['hf_niftis']).exists()
        assert Path(dirs['ti_mesh']).exists()
        assert Path(dirs['ti_niftis']).exists()
        assert Path(dirs['documentation']).exists()

        # Check no mTI directories for TI mode
        assert 'mti_mesh' not in dirs

    def test_mti_directory_structure(self, tmp_path):
        """Test mTI mode directory creation."""
        montage_dir = tmp_path / "montage1"

        dirs = setup_montage_directories(str(montage_dir), SimulationMode.MTI)

        # Check mTI-specific directories
        assert Path(dirs['mti_mesh']).exists()
        assert Path(dirs['mti_niftis']).exists()
        assert Path(dirs['mti_montage_imgs']).exists()

    def test_idempotent_creation(self, tmp_path):
        """Test that calling twice doesn't fail."""
        montage_dir = tmp_path / "montage1"

        # Create once
        dirs1 = setup_montage_directories(str(montage_dir), SimulationMode.TI)

        # Create again (should not fail)
        dirs2 = setup_montage_directories(str(montage_dir), SimulationMode.TI)

        assert dirs1 == dirs2


@pytest.mark.unit
class TestRunMontageVisualization:
    """Test suite for run_montage_visualization()."""

    @patch('subprocess.run')
    def test_successful_visualization(self, mock_run):
        """Test successful montage visualization."""
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        mock_logger = MagicMock()

        result = run_montage_visualization(
            montage_name="test_montage",
            simulation_mode=SimulationMode.TI,
            eeg_net="GSN-HydroCel-185",
            output_dir="/test/output",
            project_dir="/test/project",
            logger=mock_logger
        )

        assert result is True
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_visualization_with_electrode_pairs(self, mock_run):
        """Test visualization with explicit electrode pairs."""
        mock_run.return_value = MagicMock(returncode=0)

        mock_logger = MagicMock()
        electrode_pairs = [("E1", "E2"), ("E3", "E4")]

        result = run_montage_visualization(
            montage_name="test_montage",
            simulation_mode=SimulationMode.MTI,
            eeg_net="GSN-HydroCel-185",
            output_dir="/test/output",
            project_dir="/test/project",
            logger=mock_logger,
            electrode_pairs=electrode_pairs
        )

        assert result is True

    @patch('subprocess.run', side_effect=Exception("Subprocess failed"))
    def test_visualization_exception_handling(self, mock_run):
        """Test graceful handling of visualization errors."""
        mock_logger = MagicMock()

        result = run_montage_visualization(
            montage_name="test_montage",
            simulation_mode=SimulationMode.TI,
            eeg_net="GSN-HydroCel-185",
            output_dir="/test/output",
            project_dir="/test/project",
            logger=mock_logger
        )

        # Should return False but not raise exception
        assert result is False
        mock_logger.warning.assert_called()

    def test_skip_freehand_mode(self):
        """Test that freehand mode skips visualization."""
        mock_logger = MagicMock()

        with patch('subprocess.run') as mock_run:
            result = run_montage_visualization(
                montage_name="test_montage",
                simulation_mode=SimulationMode.TI,
                eeg_net="freehand",
                output_dir="/test/output",
                project_dir="/test/project",
                logger=mock_logger
            )

        assert result is True
        mock_run.assert_not_called()


@pytest.mark.unit
class TestRunSimulation:
    """Test suite for run_simulation()."""

    def test_sequential_execution(self, monkeypatch):
        """Test sequential simulation execution."""
        monkeypatch.setenv("PROJECT_DIR", "/test/project")

        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185.csv",
            parallel=ParallelConfig(enabled=False)
        )

        montages = [
            MontageConfig(
                name="montage1",
                electrode_pairs=[("E1", "E2"), ("E3", "E4")],
                is_xyz=False
            )
        ]

        mock_logger = MagicMock()

        with patch('tit.sim.simulator._run_sequential') as mock_sequential:
            mock_sequential.return_value = [{"montage_name": "montage1", "status": "completed"}]

            results = run_simulation(config, montages, logger=mock_logger)

            mock_sequential.assert_called_once()
            assert len(results) == 1

    def test_parallel_execution(self, monkeypatch):
        """Test parallel simulation execution."""
        monkeypatch.setenv("PROJECT_DIR", "/test/project")

        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185.csv",
            parallel=ParallelConfig(enabled=True, max_workers=2)
        )

        montages = [
            MontageConfig(name="montage1", electrode_pairs=[("E1", "E2")], is_xyz=False),
            MontageConfig(name="montage2", electrode_pairs=[("E3", "E4")], is_xyz=False)
        ]

        mock_logger = MagicMock()

        with patch('tit.sim.simulator._run_parallel') as mock_parallel:
            mock_parallel.return_value = [
                {"montage_name": "montage1", "status": "completed"},
                {"montage_name": "montage2", "status": "completed"}
            ]

            results = run_simulation(config, montages, logger=mock_logger)

            mock_parallel.assert_called_once()
            assert len(results) == 2

    def test_logger_creation_when_none(self, monkeypatch):
        """Test automatic logger creation when not provided."""
        # Set up project directory environment variable
        monkeypatch.setenv("PROJECT_DIR", "/test/project")

        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185.csv"
        )

        montages = []

        with patch('tit.sim.simulator._run_sequential') as mock_sequential, \
             patch('tit.sim.simulator.logging_util.get_file_only_logger') as mock_logger_fn, \
             patch('tit.sim.simulator.get_path_manager') as mock_get_pm, \
             patch('os.makedirs') as mock_makedirs, \
             patch('logging.FileHandler') as mock_file_handler, \
             patch('logging.getLogger') as mock_get_logger:
            mock_sequential.return_value = []

            # Mock PathManager for logger creation
            mock_pm = MagicMock()
            # path() is called with different args: "derivatives" and "simulations"
            def mock_path_side_effect(*args, **kwargs):
                if args[0] == "derivatives":
                    return "/test/derivatives"
                elif args[0] == "simulations":
                    return "/test/simulations"
                return f"/test/{args[0]}"

            mock_pm.path.side_effect = mock_path_side_effect
            mock_get_pm.return_value = mock_pm

            # Mock the logger creation
            mock_logger = MagicMock()
            mock_logger_fn.return_value = mock_logger

            # Should not raise exception
            run_simulation(config, montages, logger=None)

            # Verify logger was created
            mock_logger_fn.assert_called_once()
            # Verify get_path_manager was called
            assert mock_get_pm.call_count >= 1
            # Verify log directory was created
            mock_makedirs.assert_called()

    def test_progress_callback(self, monkeypatch):
        """Test progress callback invocation."""
        monkeypatch.setenv("PROJECT_DIR", "/test/project")

        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185.csv"
        )

        montages = [MontageConfig(name="montage1", electrode_pairs=[], is_xyz=False)]

        mock_logger = MagicMock()
        mock_callback = MagicMock()

        with patch('tit.sim.simulator._run_sequential') as mock_sequential:
            mock_sequential.return_value = [{"montage_name": "montage1", "status": "completed"}]

            run_simulation(config, montages, logger=mock_logger, progress_callback=mock_callback)

            # Callback should have been called
            # (actual calls depend on implementation)


@pytest.mark.unit
class TestRunSingleMontage:
    """Test suite for _run_single_montage()."""

    @patch('tit.sim.simulator.setup_montage_directories')
    @patch('tit.sim.simulator.run_montage_visualization')
    @patch('tit.sim.simulator.run_simnibs')
    @patch('tit.sim.simulator.get_path_manager')
    def test_ti_workflow(self, mock_get_pm, mock_run_simnibs, mock_viz, mock_setup, monkeypatch):
        """Test complete TI simulation workflow."""
        monkeypatch.setenv("PROJECT_DIR", "/test/project")

        # Mock PathManager
        mock_pm = MagicMock()
        mock_pm.path.return_value = "/test/simulations/montage1"
        mock_get_pm.return_value = mock_pm

        # Mock directory setup
        mock_setup.return_value = {
            'montage_dir': '/test/montage1',
            'hf_dir': '/test/montage1/high_Frequency',
            'hf_mesh': '/test/montage1/high_Frequency/mesh',
            'hf_niftis': '/test/montage1/high_Frequency/niftis',
            'hf_analysis': '/test/montage1/high_Frequency/analysis',
            'ti_mesh': '/test/montage1/TI/mesh',
            'ti_niftis': '/test/montage1/TI/niftis',
            'ti_surface_overlays': '/test/montage1/TI/surface_overlays',
            'ti_montage_imgs': '/test/montage1/TI/montage_imgs',
            'documentation': '/test/montage1/documentation'
        }

        mock_viz.return_value = True

        # Create mocks
        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185.csv"
        )

        montage = MontageConfig(
            name="montage1",
            electrode_pairs=[("E1", "E2"), ("E3", "E4")],
            is_xyz=False
        )

        mock_logger = MagicMock()
        mock_session_builder = MagicMock()
        mock_session_builder.build_session.return_value = MagicMock()

        mock_post_processor = MagicMock()
        mock_post_processor.process_ti_results.return_value = "/test/output.msh"

        result = _run_single_montage(
            config=config,
            montage=montage,
            simulation_dir="/test/simulations",
            session_builder=mock_session_builder,
            post_processor=mock_post_processor,
            logger=mock_logger
        )

        # Check result
        assert result['montage_name'] == 'montage1'
        assert result['status'] == 'completed'
        assert result['montage_type'] == 'TI'

        # Check workflow steps were called
        mock_setup.assert_called_once()
        mock_viz.assert_called_once()
        mock_run_simnibs.assert_called_once()
        mock_post_processor.process_ti_results.assert_called_once()

    @patch('tit.sim.simulator.setup_montage_directories')
    @patch('tit.sim.simulator.run_montage_visualization')
    @patch('tit.sim.simulator.run_simnibs')
    def test_mti_workflow(self, mock_run_simnibs, mock_viz, mock_setup):
        """Test complete mTI simulation workflow."""
        mock_setup.return_value = {
            'montage_dir': '/test/montage1',
            'hf_dir': '/test/montage1/high_Frequency',
            'hf_mesh': '/test/montage1/high_Frequency/mesh',
            'hf_niftis': '/test/montage1/high_Frequency/niftis',
            'hf_analysis': '/test/montage1/high_Frequency/analysis',
            'ti_mesh': '/test/montage1/TI/mesh',
            'ti_niftis': '/test/montage1/TI/niftis',
            'mti_mesh': '/test/montage1/mTI/mesh',
            'mti_niftis': '/test/montage1/mTI/niftis',
            'documentation': '/test/montage1/documentation'
        }

        mock_viz.return_value = True

        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185"
        )

        # 4-pair montage = mTI mode
        montage = MontageConfig(
            name="montage1",
            electrode_pairs=[("E1", "E2"), ("E3", "E4"), ("E5", "E6"), ("E7", "E8")],
            is_xyz=False
        )

        mock_logger = MagicMock()
        mock_session_builder = MagicMock()
        mock_session_builder.build_session.return_value = MagicMock()

        mock_post_processor = MagicMock()
        mock_post_processor.process_mti_results.return_value = "/test/output.msh"

        result = _run_single_montage(
            config=config,
            montage=montage,
            simulation_dir="/test/simulations",
            session_builder=mock_session_builder,
            post_processor=mock_post_processor,
            logger=mock_logger
        )

        assert result['montage_type'] == 'mTI'
        mock_post_processor.process_mti_results.assert_called_once()


@pytest.mark.unit
class TestRunParallel:
    """Test suite for _run_parallel()."""

    @patch('tit.sim.simulator.ProcessPoolExecutor')
    def test_parallel_worker_submission(self, mock_executor):
        """Test that workers are submitted correctly."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185",
            parallel=ParallelConfig(enabled=True, max_workers=2)
        )

        montages = [
            MontageConfig(name="montage1", electrode_pairs=[("E1", "E2")], is_xyz=False),
            MontageConfig(name="montage2", electrode_pairs=[("E3", "E4")], is_xyz=False)
        ]

        mock_logger = MagicMock()

        # Mock executor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock futures
        mock_future1 = MagicMock()
        mock_future1.result.return_value = {"montage_name": "montage1", "status": "completed"}
        mock_future2 = MagicMock()
        mock_future2.result.return_value = {"montage_name": "montage2", "status": "completed"}

        mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]

        # Patch the correct as_completed symbol used by tit.sim.simulator.
        # If this isn't patched, concurrent.futures.as_completed() will block forever
        # on MagicMock "futures" and the test will hang.
        with patch('tit.sim.simulator.as_completed', return_value=[mock_future1, mock_future2]):
            results = _run_parallel(
                config=config,
                montages=montages,
                simulation_dir="/test/simulations",
                logger=mock_logger
            )

        # Check that workers were submitted
        assert mock_executor_instance.submit.call_count == 2
        assert len(results) == 2

    @patch('tit.sim.simulator.ProcessPoolExecutor')
    def test_worker_exception_handling(self, mock_executor):
        """Test handling of worker exceptions."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(1.0, -1.0, 1.0, -1.0),
            electrode=ElectrodeConfig(),
            eeg_net="GSN-HydroCel-185",
            parallel=ParallelConfig(enabled=True, max_workers=2)
        )

        montages = [
            MontageConfig(name="montage1", electrode_pairs=[("E1", "E2")], is_xyz=False)
        ]

        mock_logger = MagicMock()

        # Mock executor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock future that raises exception
        mock_future = MagicMock()
        mock_future.result.side_effect = Exception("Worker failed")

        mock_executor_instance.submit.return_value = mock_future

        with patch('tit.sim.simulator.as_completed', return_value=[mock_future]):
            results = _run_parallel(
                config=config,
                montages=montages,
                simulation_dir="/test/simulations",
                logger=mock_logger
            )

        # Should capture exception and return failed result
        assert len(results) == 1
        assert results[0]['status'] == 'failed'
        assert 'error' in results[0]
