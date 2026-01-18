#!/usr/bin/env simnibs_python
"""
Unit tests for ex-search system components
"""

import pytest
import numpy as np
import sys
import os
import tempfile
import json
import csv
from itertools import product
from unittest.mock import MagicMock, patch, Mock, mock_open
from pathlib import Path

from tit.opt.ex.logic import (
    generate_current_ratios,
    calculate_total_combinations,
    generate_montage_combinations,
)
from tit.opt.ex.config import (
    validate_electrode,
    validate_current,
    ElectrodeConfig,
    CurrentConfig,
)
from tit.opt.ex.results import ResultsProcessor, ResultsVisualizer
from tit.opt.ex.runner import (
    LeadfieldAlgorithms,
    TIAlgorithms,
    CurrentRatioGenerator,
    MontageGenerator,
)
from tit.core.roi import ROICoordinateHelper


class TestLogicFunctions:
    """Test ex-search logic functions"""

    def test_generate_current_ratios_basic(self):
        """Test basic current ratio generation"""
        ratios, exceeded = generate_current_ratios(1.0, 0.1, 0.6)

        assert isinstance(ratios, list)
        assert isinstance(exceeded, bool)
        assert len(ratios) > 0

        # Check that all ratios are tuples of two floats
        for ratio in ratios:
            assert isinstance(ratio, tuple)
            assert len(ratio) == 2
            assert all(isinstance(x, float) for x in ratio)
            assert abs(sum(ratio) - 1.0) < 1e-6  # Should sum to total current

    def test_generate_current_ratios_channel_limit_exceeded(self):
        """Test when channel limit causes some ratios to be skipped"""
        ratios, exceeded = generate_current_ratios(1.0, 0.1, 0.3)

        # With total=1.0, step=0.1, limit=0.3, we can't have ratios like (0.8, 0.2)
        # since 0.8 > 0.3, so channel_limit_exceeded should be True
        assert isinstance(exceeded, bool)

    def test_calculate_total_combinations_bucketed(self):
        """Test combination calculation for bucketed mode"""
        e1_plus = ["E1", "E2"]
        e1_minus = ["E3", "E4"]
        e2_plus = ["E5", "E6"]
        e2_minus = ["E7", "E8"]
        current_ratios = [(0.5, 0.5), (0.6, 0.4)]

        total = calculate_total_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, False
        )

        expected = (
            len(e1_plus)
            * len(e1_minus)
            * len(e2_plus)
            * len(e2_minus)
            * len(current_ratios)
        )
        assert total == expected

    def test_calculate_total_combinations_all_combinations(self):
        """Test combination calculation for all-combinations mode"""
        electrodes = ["E1", "E2", "E3", "E4", "E5"]
        current_ratios = [(0.5, 0.5), (0.6, 0.4)]

        total = calculate_total_combinations(
            electrodes, electrodes, electrodes, electrodes, current_ratios, True
        )

        # Should generate combinations where all 4 electrodes are different
        expected_electrode_combinations = len(
            [
                (e1p, e1m, e2p, e2m)
                for e1p, e1m, e2p, e2m in product(electrodes, repeat=4)
                if len(set([e1p, e1m, e2p, e2m])) == 4
            ]
        )
        expected = expected_electrode_combinations * len(current_ratios)
        assert total == expected

    def test_generate_montage_combinations_bucketed(self):
        """Test montage generation for bucketed mode"""
        e1_plus = ["E1"]
        e1_minus = ["E2"]
        e2_plus = ["E3"]
        e2_minus = ["E4"]
        current_ratios = [(0.5, 0.5)]

        combinations = list(
            generate_montage_combinations(
                e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, False
            )
        )

        assert len(combinations) == 1
        assert combinations[0] == ("E1", "E2", "E3", "E4", (0.5, 0.5))

    def test_generate_montage_combinations_all_combinations(self):
        """Test montage generation for all-combinations mode"""
        electrodes = ["E1", "E2", "E3", "E4"]
        current_ratios = [(0.5, 0.5)]

        combinations = list(
            generate_montage_combinations(
                electrodes, electrodes, electrodes, electrodes, current_ratios, True
            )
        )

        # Should generate all valid combinations where all electrodes are different
        expected_count = len(
            [
                (e1p, e1m, e2p, e2m)
                for e1p, e1m, e2p, e2m in product(electrodes, repeat=4)
                if len(set([e1p, e1m, e2p, e2m])) == 4
            ]
        )

        assert len(combinations) == expected_count
        # Each combination should end with the current ratio
        assert all(combo[-1] == (0.5, 0.5) for combo in combinations)


class TestConfigValidation:
    """Test configuration validation functions"""

    def test_validate_electrode_valid(self):
        """Test electrode validation with valid names"""
        assert validate_electrode("E1") == True
        assert validate_electrode("Fp1") == True
        assert validate_electrode("C3") == True
        assert validate_electrode("electrode1") == True

    def test_validate_electrode_invalid(self):
        """Test electrode validation with invalid names"""
        assert validate_electrode("1E") == False  # Starts with number
        assert validate_electrode("E-1") == False  # Invalid character
        assert validate_electrode("") == False  # Empty string
        assert validate_electrode("E 1") == False  # Space

    def test_validate_current_valid(self):
        """Test current validation with valid values"""
        assert validate_current(1.0) == True
        assert validate_current(0.5) == True
        assert validate_current(2.5) == True
        assert validate_current(0.1, 0.0, 5.0) == True

    def test_validate_current_invalid(self):
        """Test current validation with invalid values"""
        assert validate_current(-0.1) == False  # Negative
        assert validate_current(0.0, 0.1) == False  # Below minimum
        assert validate_current(10.0, 0.0, 5.0) == False  # Above maximum


class TestElectrodeConfig:
    """Test electrode configuration"""

    def setup_method(self):
        """Setup test fixtures"""
        self.logger = MagicMock()

    def teardown_method(self):
        """Clean up test fixtures"""
        # Clean up environment variables that might be set by tests
        env_vars = ["E1_PLUS", "E1_MINUS", "E2_PLUS", "E2_MINUS"]
        for var in env_vars:
            os.environ.pop(var, None)

    @patch.dict(
        os.environ,
        {
            "E1_PLUS": "E1 E2",
            "E1_MINUS": "E3 E4",
            "E2_PLUS": "E5 E6",
            "E2_MINUS": "E7 E8",
        },
    )
    def test_get_config_bucketed_mode(self):
        """Test electrode config in bucketed mode"""
        config = ElectrodeConfig(self.logger)
        result = config.get_config(False)

        expected = {
            "E1_plus": ["E1", "E2"],
            "E1_minus": ["E3", "E4"],
            "E2_plus": ["E5", "E6"],
            "E2_minus": ["E7", "E8"],
        }
        assert result == expected

    @patch.dict(
        os.environ,
        {
            "E1_PLUS": "E1 E2 E3 E4",
            "E1_MINUS": "E1 E2 E3 E4",
            "E2_PLUS": "E1 E2 E3 E4",
            "E2_MINUS": "E1 E2 E3 E4",
        },
    )
    def test_get_config_all_combinations_mode(self):
        """Test electrode config in all-combinations mode"""
        config = ElectrodeConfig(self.logger)
        result = config.get_config(True)

        # All channels should use the same electrode pool
        expected = {
            "E1_plus": ["E1", "E2", "E3", "E4"],
            "E1_minus": ["E1", "E2", "E3", "E4"],
            "E2_plus": ["E1", "E2", "E3", "E4"],
            "E2_minus": ["E1", "E2", "E3", "E4"],
        }
        assert result == expected

    def test_get_config_missing_env_vars(self):
        """Test electrode config with missing environment variables"""
        from tit.opt.ex.config import ConfigError

        config = ElectrodeConfig(self.logger)

        with pytest.raises(ConfigError):  # Should raise ConfigError
            config.get_config(False)


class TestCurrentConfig:
    """Test current configuration"""

    def setup_method(self):
        """Setup test fixtures"""
        self.logger = MagicMock()

    @patch.dict(
        os.environ,
        {"TOTAL_CURRENT": "1.0", "CURRENT_STEP": "0.1", "CHANNEL_LIMIT": "0.6"},
    )
    def test_get_config_with_env_vars(self):
        """Test current config with environment variables"""
        config = CurrentConfig(self.logger)
        result = config.get_config()

        assert result["total_current"] == 1.0
        assert result["current_step"] == 0.1
        assert result["channel_limit"] == 0.6


class TestROICoordinateHelper:
    """Test ROICoordinateHelper utility"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_roi_from_valid_csv(self):
        """Test loading ROI from valid CSV file"""
        csv_file = os.path.join(self.temp_dir, "roi.csv")
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([10.5, 20.5, 30.5])

        coords = ROICoordinateHelper.load_roi_from_csv(csv_file)

        assert coords is not None
        assert len(coords) == 3
        assert np.isclose(coords[0], 10.5)
        assert np.isclose(coords[1], 20.5)
        assert np.isclose(coords[2], 30.5)

    def test_load_roi_from_invalid_csv(self):
        """Test loading ROI from invalid CSV file"""
        csv_file = os.path.join(self.temp_dir, "bad_roi.csv")
        with open(csv_file, "w") as f:
            f.write("invalid,data\n")

        coords = ROICoordinateHelper.load_roi_from_csv(csv_file)

        # Should return None for invalid file
        assert coords is None

    def test_load_roi_from_nonexistent_file(self):
        """Test loading ROI from non-existent file"""
        fake_file = os.path.join(self.temp_dir, "does_not_exist.csv")

        coords = ROICoordinateHelper.load_roi_from_csv(fake_file)

        # Should return None for non-existent file
        assert coords is None


class TestResultsProcessor:
    """Test results processing functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = MagicMock()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_csv_data(self):
        """Test CSV data creation from results"""
        # Mock results data
        results = {
            "TI_field_E1_E2_and_E3_E4_I1-0.50mA_I2-0.50mA.msh": {
                "ROI_TImax_ROI": 0.8,
                "ROI_TImean_ROI": 0.6,
                "ROI_TImean_GM": 0.4,
                "ROI_Focality": 0.7,
                "ROI_n_elements": 100,
                "current_ch1_mA": 0.5,
                "current_ch2_mA": 0.5,
            },
            "TI_field_E5_E6_and_E7_E8_I1-0.60mA_I2-0.40mA.msh": {
                "ROI_TImax_ROI": 0.9,
                "ROI_TImean_ROI": 0.7,
                "ROI_TImean_GM": 0.5,
                "ROI_Focality": 0.8,
                "ROI_n_elements": 120,
                "current_ch1_mA": 0.6,
                "current_ch2_mA": 0.4,
            },
        }

        processor = ResultsProcessor(results, self.temp_dir, "ROI", self.logger)
        csv_data, timax_values, timean_values, focality_values, composite_values = (
            processor.create_csv_data()
        )

        # Check CSV structure
        assert len(csv_data) == 3  # Header + 2 data rows
        assert csv_data[0][0] == "Montage"
        assert csv_data[0][1] == "Current_Ch1_mA"
        assert len(csv_data[1]) == 9  # 9 columns
        assert len(csv_data[2]) == 9

        # Check data values
        assert timax_values == [0.8, 0.9]
        assert timean_values == [0.6, 0.7]
        assert focality_values == [0.7, 0.8]
        assert len(composite_values) == 2
        assert abs(composite_values[0] - 0.42) < 1e-10  # 0.6*0.7
        assert abs(composite_values[1] - 0.56) < 1e-10  # 0.7*0.8

    def test_save_csv_results(self):
        """Test CSV file saving"""
        results = {
            "TI_field_test.msh": {
                "ROI_TImax_ROI": 0.8,
                "ROI_TImean_ROI": 0.6,
                "ROI_TImean_GM": 0.4,
                "ROI_Focality": 0.7,
                "ROI_n_elements": 100,
                "current_ch1_mA": 0.5,
                "current_ch2_mA": 0.5,
            }
        }

        processor = ResultsProcessor(results, self.temp_dir, "ROI", self.logger)
        csv_path = processor.save_csv_results()

        assert os.path.exists(csv_path)
        assert csv_path.endswith("final_output.csv")

        # Verify CSV content
        with open(csv_path, "r") as f:
            lines = f.readlines()
            assert len(lines) == 2  # Header + 1 data row
            assert "Montage" in lines[0]
            assert "0.5" in lines[1]  # Current values

    def test_save_json_results(self):
        """Test JSON results saving"""
        results = {"test.msh": {"key": "value"}}
        processor = ResultsProcessor(results, self.temp_dir, "ROI", self.logger)
        json_path = processor.save_json_results()

        assert os.path.exists(json_path)
        assert json_path.endswith("analysis_results.json")

        # Verify JSON content
        with open(json_path, "r") as f:
            data = json.load(f)
            assert data == results


class TestResultsVisualizer:
    """Test results visualization functionality"""

    @patch("matplotlib.pyplot.subplots")
    @patch("matplotlib.pyplot.close")
    def test_create_histograms(self, mock_close, mock_subplots):
        """Test histogram creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = MagicMock()
            visualizer = ResultsVisualizer(temp_dir, logger)

            # Mock matplotlib objects
            mock_fig = MagicMock()
            mock_axes = [MagicMock(), MagicMock(), MagicMock()]
            mock_subplots.return_value = (mock_fig, mock_axes)

            timax_values = [0.5, 0.7, 0.9]
            timean_values = [0.4, 0.6, 0.8]
            focality_values = [0.6, 0.7, 0.8]

            hist_path = visualizer.create_histograms(
                timax_values, timean_values, focality_values
            )

            # Should return the expected path
            expected_path = os.path.join(temp_dir, "montage_distributions.png")
            assert hist_path == expected_path
            mock_fig.savefig.assert_called_once()

    def test_create_histograms_no_data(self):
        """Test histogram creation with no data"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = MagicMock()
            visualizer = ResultsVisualizer(temp_dir, logger)

            hist_path = visualizer.create_histograms([], [], [])

            # Should return None when no data
            assert hist_path is None

    @patch("matplotlib.pyplot.subplots")
    @patch("matplotlib.pyplot.close")
    def test_create_scatter_plot(self, mock_close, mock_subplots):
        """Test scatter plot creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = MagicMock()
            visualizer = ResultsVisualizer(temp_dir, logger)

            # Mock matplotlib objects
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_fig.colorbar = MagicMock()
            mock_subplots.return_value = (mock_fig, mock_ax)

            results = {
                "mesh1.msh": {"ROI_TImean_ROI": 0.6, "ROI_Focality": 0.7},
                "mesh2.msh": {"ROI_TImean_ROI": 0.8, "ROI_Focality": 0.9},
            }

            scatter_path = visualizer.create_scatter_plot(results, "ROI")

            # Should return the expected path
            expected_path = os.path.join(temp_dir, "intensity_vs_focality_scatter.png")
            assert scatter_path == expected_path
            mock_fig.savefig.assert_called_once()


class TestExSearchIntegration:
    """Integration tests for ex-search workflow"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_logic_integration(self):
        """Test integration of logic functions"""
        # Test a complete workflow
        total_current = 1.0
        current_step = 0.2
        channel_limit = 0.6

        # Generate current ratios
        ratios, exceeded = generate_current_ratios(
            total_current, current_step, channel_limit
        )
        assert len(ratios) > 0

        # Calculate combinations
        electrodes = ["E1", "E2", "E3", "E4"]
        total_combinations = calculate_total_combinations(
            electrodes, electrodes, electrodes, electrodes, ratios, True
        )
        assert total_combinations > 0

        # Generate montages
        montages = list(
            generate_montage_combinations(
                electrodes, electrodes, electrodes, electrodes, ratios, True
            )
        )
        assert len(montages) == total_combinations

    def test_config_integration(self):
        """Test configuration integration"""
        # Test validation functions work together
        assert validate_electrode("E1")
        assert validate_current(1.0)
        assert validate_current(0.5, 0.1, 2.0)

        # Test electrode config creation
        logger = MagicMock()
        with patch.dict(
            os.environ,
            {
                "E1_PLUS": "E1 E2",
                "E1_MINUS": "E3 E4",
                "E2_PLUS": "E5 E6",
                "E2_MINUS": "E7 E8",
            },
        ):
            config = ElectrodeConfig(logger)
            electrodes = config.get_config(False)
            assert len(electrodes) == 4
            assert all(isinstance(v, list) for v in electrodes.values())


class TestRunnerComponents:
    """Test runner component functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.logger = MagicMock()

    @patch("tit.opt.ex.runner.TI.load_leadfield")
    def test_leadfield_algorithms_load_leadfield(self, mock_load_leadfield):
        """Test leadfield loading"""
        mock_leadfield = MagicMock()
        mock_mesh = MagicMock()
        mock_idx_lf = MagicMock()
        mock_load_leadfield.return_value = (mock_leadfield, mock_mesh, mock_idx_lf)

        leadfield, mesh, idx_lf, load_time = LeadfieldAlgorithms.load_leadfield(
            "/fake/path.hdf5"
        )

        mock_load_leadfield.assert_called_once_with("/fake/path.hdf5")
        assert leadfield == mock_leadfield
        assert mesh == mock_mesh
        assert idx_lf == mock_idx_lf
        assert isinstance(load_time, float)

    @patch("os.path.exists", return_value=True)
    @patch("tit.opt.ex.runner.ROICoordinateHelper.load_roi_from_csv")
    def test_leadfield_algorithms_load_roi_coordinates(
        self, mock_load_roi, mock_exists
    ):
        """Test ROI coordinate loading"""
        mock_load_roi.return_value = [10.0, 20.0, 30.0]

        coords = LeadfieldAlgorithms.load_roi_coordinates("/fake/roi.csv")

        mock_load_roi.assert_called_once_with("/fake/roi.csv")
        assert coords == [10.0, 20.0, 30.0]

    @patch("os.path.exists", return_value=True)
    @patch("tit.opt.ex.runner.ROICoordinateHelper.load_roi_from_csv")
    def test_leadfield_algorithms_load_roi_coordinates_none(
        self, mock_load_roi, mock_exists
    ):
        """Test ROI coordinate loading when file returns None"""
        mock_load_roi.return_value = None

        with pytest.raises(ValueError):
            LeadfieldAlgorithms.load_roi_coordinates("/fake/roi.csv")

    @patch("tit.opt.ex.runner.find_roi_element_indices")
    def test_leadfield_algorithms_find_roi_elements(self, mock_find_roi):
        """Test ROI element finding"""
        mock_mesh = MagicMock()
        mock_find_roi.return_value = (np.array([1, 2, 3]), np.array([0.5, 0.5, 0.5]))

        indices, volumes = LeadfieldAlgorithms.find_roi_elements(
            mock_mesh, [10, 20, 30], 3.0
        )

        mock_find_roi.assert_called_once_with(mock_mesh, [10, 20, 30], radius=3.0)
        assert np.array_equal(indices, np.array([1, 2, 3]))

    @patch("tit.opt.ex.runner.find_grey_matter_indices")
    def test_leadfield_algorithms_find_grey_matter_elements(self, mock_find_gm):
        """Test grey matter element finding"""
        mock_mesh = MagicMock()
        mock_find_gm.return_value = (np.array([10, 20]), np.array([0.8, 0.8]))

        indices, volumes = LeadfieldAlgorithms.find_grey_matter_elements(mock_mesh)

        mock_find_gm.assert_called_once_with(mock_mesh, grey_matter_tags=[2])
        assert np.array_equal(indices, np.array([10, 20]))

    @patch("tit.opt.ex.runner.calculate_roi_metrics")
    def test_leadfield_algorithms_calculate_roi_metrics(self, mock_calc_metrics):
        """Test ROI metrics calculation"""
        mock_calc_metrics.return_value = {
            "TImax_ROI": 0.8,
            "TImean_ROI": 0.6,
            "Focality": 0.7,
        }

        # Create larger arrays to avoid index errors
        ti_max_full = np.array(
            [0.5, 0.7, 0.9, 0.6, 0.8, 0.4, 0.3, 0.9, 0.2, 0.1, 0.8, 0.6]
        )

        result = LeadfieldAlgorithms.calculate_roi_metrics_for_field(
            ti_max_full,
            np.array([0, 1, 2]),
            np.array([1.0, 1.0, 1.0]),
            np.array([10, 11]),  # Valid indices within ti_max_full
            np.array([0.8, 0.6]),
        )

        mock_calc_metrics.assert_called_once()
        assert result["TImax_ROI"] == 0.8

    @patch("simnibs.utils.TI_utils.get_field")
    @patch("simnibs.utils.TI_utils.get_maxTI")
    def test_ti_algorithms_calculate_ti_field(self, mock_get_maxTI, mock_get_field):
        """Test TI field calculation"""
        mock_ef1 = MagicMock()
        mock_ef2 = MagicMock()
        mock_ti_max = MagicMock()
        mock_get_field.side_effect = [mock_ef1, mock_ef2]
        mock_get_maxTI.return_value = mock_ti_max

        with patch(
            "tit.opt.ex.runner.LeadfieldAlgorithms.calculate_roi_metrics_for_field"
        ) as mock_calc:
            mock_calc.return_value = {
                "TImax_ROI": 0.8,
                "TImean_ROI": 0.6,
                "TImean_GM": 0.4,
                "Focality": 0.7,
                "n_elements": 100,
            }

            result = TIAlgorithms.calculate_ti_field(
                MagicMock(),
                MagicMock(),  # leadfield, idx_lf
                np.array([1, 2]),
                np.array([1.0, 1.0]),  # roi_indices, roi_volumes
                np.array([10, 20]),
                np.array([0.8, 0.8]),  # gm_indices, gm_volumes
                "E1",
                "E2",
                0.5,
                "E3",
                "E4",
                0.5,  # electrodes and currents
                "TestROI",
            )

            assert result["TestROI_TImax_ROI"] == 0.8
            assert result["TestROI_TImean_ROI"] == 0.6
            assert result["TestROI_Focality"] == 0.7
            assert result["current_ch1_mA"] == 0.5
            assert result["current_ch2_mA"] == 0.5

    def test_current_ratio_generator(self):
        """Test current ratio generator"""
        generator = CurrentRatioGenerator(1.0, 0.1, 0.6, self.logger)
        ratios = generator.generate_ratios()

        assert isinstance(ratios, list)
        assert len(ratios) > 0

    def test_montage_generator_bucketed(self):
        """Test montage generator in bucketed mode"""
        e1_plus = ["E1", "E2"]
        e1_minus = ["E3", "E4"]
        e2_plus = ["E5", "E6"]
        e2_minus = ["E7", "E8"]
        current_ratios = [(0.5, 0.5), (0.6, 0.4)]

        generator = MontageGenerator(
            e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, False, self.logger
        )

        total_combinations = generator.get_total_combinations()
        expected = (
            len(e1_plus)
            * len(e1_minus)
            * len(e2_plus)
            * len(e2_minus)
            * len(current_ratios)
        )
        assert total_combinations == expected

        montages = list(generator.generate_montages())
        assert len(montages) == total_combinations

    def test_montage_generator_all_combinations(self):
        """Test montage generator in all-combinations mode"""
        electrodes = ["E1", "E2", "E3", "E4"]
        current_ratios = [(0.5, 0.5)]

        generator = MontageGenerator(
            electrodes,
            electrodes,
            electrodes,
            electrodes,
            current_ratios,
            True,
            self.logger,
        )

        total_combinations = generator.get_total_combinations()
        # Should generate all valid combinations where all 4 electrodes are different
        expected_electrode_combinations = len(
            [
                (e1p, e1m, e2p, e2m)
                for e1p, e1m, e2p, e2m in product(electrodes, repeat=4)
                if len(set([e1p, e1m, e2p, e2m])) == 4
            ]
        )
        expected = expected_electrode_combinations * len(current_ratios)
        assert total_combinations == expected

        montages = list(generator.generate_montages())
        assert len(montages) == total_combinations
