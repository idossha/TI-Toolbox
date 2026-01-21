#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox tissue analyzer wrapper (pre/tissue_analyzer.py)
"""

import os
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.tissue_analyzer import (
    DEFAULT_TISSUES,
    run_tissue_analysis,
)
from pre.common import PreprocessError


class TestDefaultTissuesConstant:
    """Test DEFAULT_TISSUES constant"""

    def test_default_tissues_contains_expected_values(self):
        """Test DEFAULT_TISSUES contains expected tissue types"""
        assert "bone" in DEFAULT_TISSUES
        assert "csf" in DEFAULT_TISSUES
        assert "skin" in DEFAULT_TISSUES

    def test_default_tissues_is_tuple(self):
        """Test DEFAULT_TISSUES is a tuple"""
        assert isinstance(DEFAULT_TISSUES, tuple)

    def test_default_tissues_has_correct_count(self):
        """Test DEFAULT_TISSUES has exactly 3 tissues"""
        assert len(DEFAULT_TISSUES) == 3


class TestRunTissueAnalysis:
    """Test run_tissue_analysis function"""

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_raises_if_labeling_not_found(self, mock_get_pm):
        """Test raises PreprocessError if Labeling.nii.gz not found"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            mock_pm.path.return_value = str(label_path)

            logger = MagicMock()

            with pytest.raises(PreprocessError) as exc_info:
                run_tissue_analysis(tmpdir, "001", logger=logger)

            assert "Labeling.nii.gz not found" in str(exc_info.value)

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_raises_if_script_not_found(self, mock_get_pm):
        """Test raises PreprocessError if tissue_analyzer.py script not found"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()
            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(Path(tmpdir) / "output")

            logger = MagicMock()

            # Mock Path.exists to return False for tissue_analyzer.py
            original_exists = Path.exists
            def mock_exists(self):
                if "tissue_analyzer.py" in str(self):
                    return False
                return original_exists(self)

            with patch.object(Path, "exists", mock_exists):
                with pytest.raises(PreprocessError) as exc_info:
                    run_tissue_analysis(tmpdir, "001", logger=logger)

                assert "tissue_analyzer.py not found" in str(exc_info.value)

    @patch("pre.tissue_analyzer.get_path_manager")
    @patch("subprocess.call")
    def test_run_processes_default_tissues(self, mock_call, mock_get_pm):
        """Test processes default tissue types"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            # Mock the script path resolution
            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                # Make script_path.exists() return True
                actual_script_path = script_dir / "tissue_analyzer.py"
                with patch.object(Path, "exists", return_value=True):
                    mock_call.return_value = 0

                    logger = MagicMock()

                    run_tissue_analysis(tmpdir, "001", logger=logger)

                    # Verify called for each default tissue
                    assert mock_call.call_count == len(DEFAULT_TISSUES)

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_processes_custom_tissues(self, mock_get_pm):
        """Test processes custom tissue types"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            custom_tissues = ["gray", "white"]

            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                with patch.object(Path, "exists", return_value=True):
                    run_tissue_analysis(
                        tmpdir,
                        "001",
                        tissues=custom_tissues,
                        logger=logger,
                        runner=runner
                    )

                    # Verify called for each custom tissue
                    assert runner.run.call_count == len(custom_tissues)

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_raises_on_analysis_failure(self, mock_get_pm):
        """Test raises PreprocessError when tissue analysis fails"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 1  # Failure

            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                with patch.object(Path, "exists", return_value=True):
                    with pytest.raises(PreprocessError) as exc_info:
                        run_tissue_analysis(tmpdir, "001", logger=logger, runner=runner)

                    assert "Tissue analysis failed" in str(exc_info.value)

    @patch("pre.tissue_analyzer.get_path_manager")
    @patch("subprocess.call")
    def test_run_uses_subprocess_call_when_no_runner(self, mock_call, mock_get_pm):
        """Test uses subprocess.call when runner not provided"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            mock_call.return_value = 0

            logger = MagicMock()

            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                with patch.object(Path, "exists", return_value=True):
                    run_tissue_analysis(tmpdir, "001", logger=logger, runner=None)

                    # Verify subprocess.call was used
                    assert mock_call.call_count == len(DEFAULT_TISSUES)

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_uses_runner_when_provided(self, mock_get_pm):
        """Test uses CommandRunner when provided"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                with patch.object(Path, "exists", return_value=True):
                    run_tissue_analysis(tmpdir, "001", logger=logger, runner=runner)

                    # Verify runner was used
                    assert runner.run.call_count == len(DEFAULT_TISSUES)

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_run_creates_output_directories(self, mock_get_pm):
        """Test creates output directories for each tissue"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()

            # Create dummy script
            script_dir = Path(tmpdir) / "tools"
            script_dir.mkdir()
            script_path = script_dir / "tissue_analyzer.py"
            script_path.touch()

            output_root = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_root)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            with patch("pre.tissue_analyzer.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value.parents = [script_dir.parent, Path("/")]
                mock_path_class.return_value = mock_path_instance

                with patch.object(Path, "exists", return_value=True):
                    run_tissue_analysis(tmpdir, "001", logger=logger, runner=runner)

                    # Verify ensure_dir was called
                    mock_pm.ensure_dir.assert_called_once_with(
                        "tissue_analysis_output", subject_id="001"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
