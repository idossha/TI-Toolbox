#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Comprehensive unit tests for montage_visualizer.py
Tests all classes and methods in the montage visualization system.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

from tit.tools.montage_visualizer import (
    ResourcePathManager,
    ElectrodeCoordinateReader,
    MontageVisualizer,
)


class TestResourcePathManager(unittest.TestCase):
    """Test cases for ResourcePathManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(__file__).parent / "amv"

    def test_detect_resources_dir_production_mode(self):
        """Resource directory is always /ti-toolbox/resources/amv."""
        with patch("os.path.isdir", return_value=True):
            manager = ResourcePathManager()
            result = manager._detect_resources_dir()
            self.assertEqual(result, "/ti-toolbox/resources/amv")

    def test_detect_resources_dir_not_found(self):
        """Test resource directory detection when directory is missing."""
        with patch("os.path.isdir", return_value=False):
            with self.assertRaises(FileNotFoundError):
                ResourcePathManager()._detect_resources_dir()

    def test_get_coordinate_file_gsn_hd_nets(self):
        """Test coordinate file retrieval for GSN-HD nets."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()

            gsn_nets = [
                "GSN-HydroCel-185",
                "GSN-HydroCel-185.csv",
                "GSN-HydroCel-256.csv",
            ]
            for net in gsn_nets:
                result = manager.get_coordinate_file(net)
                self.assertEqual(result, "/test/path/GSN-256.csv")

    def test_get_coordinate_file_10_10_nets(self):
        """Test coordinate file retrieval for 10-10 nets."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()

            ten_ten_nets = [
                "EEG10-10_UI_Jurak_2007.csv",
                "EEG10-10_Cutini_2011.csv",
                "EEG10-20_Okamoto_2004.csv",
                "EEG10-10_Neuroelectrics.csv",
            ]
            for net in ten_ten_nets:
                result = manager.get_coordinate_file(net)
                self.assertEqual(result, "/test/path/10-10.csv")

    def test_get_coordinate_file_freehand_modes(self):
        """Test coordinate file retrieval for freehand modes."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()
            result = manager.get_coordinate_file("freehand")
            self.assertIsNone(result)

            result = manager.get_coordinate_file("flex_mode")
            self.assertIsNone(result)

    def test_get_coordinate_file_unsupported(self):
        """Test coordinate file retrieval for unsupported EEG net."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()
            with self.assertRaises(ValueError):
                manager.get_coordinate_file("unsupported_net.csv")

    def test_get_template_image_gsn_hd(self):
        """Test template image retrieval for GSN-HD nets."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()

            gsn_nets = [
                "GSN-HydroCel-185",
                "GSN-HydroCel-185.csv",
                "GSN-HydroCel-256.csv",
            ]
            for net in gsn_nets:
                result = manager.get_template_image(net)
                self.assertEqual(result, "/test/path/GSN-256.png")

    def test_get_template_image_10_10(self):
        """Test template image retrieval for 10-10 nets."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()

            result = manager.get_template_image("EEG10-10_UI_Jurak_2007.csv")
            self.assertEqual(result, "/test/path/GSN-256.png")

    def test_get_ring_image(self):
        """Test ring image retrieval."""
        with patch.object(
            ResourcePathManager, "_detect_resources_dir", return_value="/test/path"
        ):
            manager = ResourcePathManager()

            # Test various indices
            self.assertEqual(manager.get_ring_image(0), "/test/path/pair1ring.png")
            self.assertEqual(manager.get_ring_image(7), "/test/path/pair8ring.png")
            self.assertEqual(
                manager.get_ring_image(8), "/test/path/pair1ring.png"
            )  # cycles back


class TestElectrodeCoordinateReader(unittest.TestCase):
    """Test cases for ElectrodeCoordinateReader class."""

    def test_init_gsn_hd_format(self):
        """Test initialization with GSN-256 format file."""
        reader = ElectrodeCoordinateReader("/path/to/GSN-256.csv")
        self.assertFalse(reader.is_gsn_hd)  # All files now use 3-column format

    def test_init_10_10_format(self):
        """Test initialization with 10-10 format file."""
        reader = ElectrodeCoordinateReader("/path/to/10-10.csv")
        self.assertFalse(reader.is_gsn_hd)

    def test_get_coordinates_gsn_hd_format(self):
        """Test coordinate reading from GSN-256 format."""
        mock_data = "electrode_name,x,y\nE001,100,200\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            reader = ElectrodeCoordinateReader("/path/to/GSN-256.csv")
            coords = reader.get_coordinates("E001")
            self.assertEqual(coords, (100, 200))  # Uses x,y columns

    def test_get_coordinates_10_10_format(self):
        """Test coordinate reading from 10-10 format."""
        mock_data = "electrode_name,x,y\nFp1,150,250\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            reader = ElectrodeCoordinateReader("/path/to/10-10-net.csv")
            coords = reader.get_coordinates("Fp1")
            self.assertEqual(coords, (150, 250))

    def test_get_coordinates_not_found(self):
        """Test coordinate reading when electrode is not found."""
        mock_data = "electrode_name,x,y\nFp1,150,250\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            reader = ElectrodeCoordinateReader("/path/to/10-10-net.csv")
            coords = reader.get_coordinates("NonExistent")
            self.assertIsNone(coords)

    def test_get_coordinates_invalid_data(self):
        """Test coordinate reading with invalid data."""
        mock_data = "electrode_name,x,y\nFp1,invalid,250\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            reader = ElectrodeCoordinateReader("/path/to/10-10-net.csv")
            coords = reader.get_coordinates("Fp1")
            self.assertIsNone(coords)

    def test_get_coordinates_file_error(self):
        """Test coordinate reading when file cannot be opened."""
        with patch("builtins.open", side_effect=IOError()):
            reader = ElectrodeCoordinateReader("/path/to/nonexistent.csv")
            coords = reader.get_coordinates("Fp1")
            self.assertIsNone(coords)


class TestMontageVisualizer(unittest.TestCase):
    """Test cases for MontageVisualizer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(__file__).parent
        self.resources_dir = self.test_dir / "amv"

        # Create temporary directory for outputs
        self.output_dir = tempfile.mkdtemp()

        # Create mock montage configuration
        self.montage_config = {
            "nets": {
                "GSN-HydroCel-256.csv": {
                    "uni_polar_montages": {"E010-E011": [["E010", "E011"]]},
                    "multi_polar_montages": {"E010-E011": [["E010", "E011"]]},
                }
            }
        }

        # Write montage config to temporary file
        self.montage_file = os.path.join(self.output_dir, "montage_list.json")
        with open(self.montage_file, "w") as f:
            json.dump(self.montage_config, f, indent=2)

    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temporary output directory
        import shutil

        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_init_freehand_mode(self):
        """Test initialization with freehand mode."""
        # Mock the resource manager
        mock_resource_manager = MagicMock()
        mock_resource_manager.get_coordinate_file.return_value = None

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=mock_resource_manager,
            eeg_net="freehand",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        self.assertTrue(visualizer.skip_visualization)

    def test_init_flex_mode(self):
        """Test initialization with flex mode."""
        # Mock the resource manager
        mock_resource_manager = MagicMock()
        mock_resource_manager.get_coordinate_file.return_value = None

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=mock_resource_manager,
            eeg_net="flex_mode",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        self.assertTrue(visualizer.skip_visualization)

    def test_visualize_montages_skip_freehand(self):
        """Test that visualization is skipped for freehand mode."""
        mock_resource_manager = MagicMock()
        mock_resource_manager.get_coordinate_file.return_value = None

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=mock_resource_manager,
            eeg_net="freehand",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        result = visualizer.visualize_montages(["test_montage"])
        self.assertTrue(result)

    def test_visualize_montages_invalid_montage_file(self):
        """Test handling of invalid montage file."""

        # Create a TestResourceManager that uses local test resources
        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_coordinate_file(self, eeg_net):
                if "GSN" in eeg_net:
                    return os.path.join(self.resources_dir, "GSN-256.csv")
                else:
                    return os.path.join(self.resources_dir, "10-10.csv")

            def get_template_image(self, eeg_net):
                if "GSN" in eeg_net:
                    return os.path.join(self.resources_dir, "GSN-256.png")
                else:
                    return os.path.join(
                        self.resources_dir, "GSN-256.png"
                    )  # Use same template

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file="/nonexistent/file.json",
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        result = visualizer.visualize_montages(["E010-E011"])
        self.assertFalse(result)

    def test_visualize_montages_missing_montage(self):
        """Test handling of missing montage in configuration."""

        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_coordinate_file(self, eeg_net):
                if "GSN" in eeg_net:
                    return os.path.join(self.resources_dir, "GSN-256.csv")
                else:
                    return os.path.join(self.resources_dir, "10-10.csv")

            def get_template_image(self, eeg_net):
                if "GSN" in eeg_net:
                    return os.path.join(self.resources_dir, "GSN-256.png")
                else:
                    return os.path.join(self.resources_dir, "GSN-256.png")

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        result = visualizer.visualize_montages(["NonExistent-Montage"])
        self.assertTrue(result)  # Should succeed but skip missing montage

    def test_draw_connection_line_missing_electrode(self):
        """Test connection line drawing with missing electrode coordinates."""

        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_coordinate_file(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.csv")

            def get_template_image(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.png")

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        # Test with non-existent electrode
        visualizer._draw_connection_line(
            "/fake/image.png", "NonExistent1", "NonExistent2", 0
        )
        # Should not crash, just log warning

    def test_overlay_ring_missing_electrode(self):
        """Test ring overlay with missing electrode coordinates."""

        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_coordinate_file(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.csv")

            def get_template_image(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.png")

            def get_ring_image(self, pair_index):
                return os.path.join(self.resources_dir, "pair1ring.png")

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        # Test with non-existent electrode
        visualizer._overlay_ring("/fake/image.png", "NonExistent", 0)
        # Should not crash, just log warning

    def test_copy_template(self):
        """Test template image copying."""

        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_template_image(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.png")

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
        )

        source = os.path.join(self.resources_dir, "GSN-256.png")
        dest = os.path.join(self.output_dir, "test_copy.png")

        visualizer._copy_template(source, dest)
        self.assertTrue(os.path.exists(dest))


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete visualization pipeline."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.test_dir = Path(__file__).parent
        self.resources_dir = self.test_dir / "amv"
        self.output_dir = tempfile.mkdtemp()

        # Create montage configuration
        self.montage_config = {
            "nets": {
                "GSN-HydroCel-256.csv": {
                    "uni_polar_montages": {"E010-E011": [["E010", "E011"]]}
                }
            }
        }

        self.montage_file = os.path.join(self.output_dir, "montage_list.json")
        with open(self.montage_file, "w") as f:
            json.dump(self.montage_config, f, indent=2)

    def tearDown(self):
        """Clean up integration test fixtures."""
        import shutil

        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_full_visualization_pipeline(self):
        """Test the complete visualization pipeline end-to-end."""

        # Create a TestResourceManager that uses local test resources
        class TestResourceManager(ResourcePathManager):
            def __init__(self, resources_dir):
                self.resources_dir = str(resources_dir)

            def get_coordinate_file(self, eeg_net):
                if "GSN" in eeg_net:
                    return os.path.join(self.resources_dir, "GSN-256.csv")
                else:
                    return os.path.join(self.resources_dir, "10-10.csv")

            def get_template_image(self, eeg_net):
                return os.path.join(self.resources_dir, "GSN-256.png")

        resource_manager = TestResourceManager(self.resources_dir)

        visualizer = MontageVisualizer(
            montage_file=self.montage_file,
            resource_manager=resource_manager,
            eeg_net="GSN-HydroCel-256.csv",
            sim_mode="U",
            output_directory=self.output_dir,
            verbose=False,  # Reduce output for test
        )

        result = visualizer.visualize_montages(["E010-E011"])
        self.assertTrue(result)

        # Check that output file was created
        expected_output = os.path.join(
            self.output_dir, "E010-E011_highlighted_visualization.png"
        )
        self.assertTrue(os.path.exists(expected_output))


if __name__ == "__main__":
    unittest.main()
