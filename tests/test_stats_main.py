"""Tests for tit/stats/__main__.py and supplementary coverage for config.py and nifti.py.

Covers:
- __main__._build_group_subjects / _build_correlation_subjects
- __main__.main() with group_comparison and correlation modes
- __main__._run_group_comparison / _run_correlation
- config._nifti_pattern_for_tissue WHITE and ALL branches
- config.GroupComparisonConfig validation: 0 responders or 0 non-responders
- nifti.load_subject_nifti_ti_toolbox FileNotFoundError with directory listing
"""

import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Restore real scipy so that tit.stats.engine can load properly.
# (Same pattern as test_stats_engine.py / test_stats_coverage.py)
# ---------------------------------------------------------------------------
_scipy_keys = [k for k in list(sys.modules) if k == "scipy" or k.startswith("scipy.")]
_saved = {k: sys.modules.pop(k) for k in _scipy_keys}

import scipy  # noqa: E402
import scipy.ndimage  # noqa: E402
import scipy.stats  # noqa: E402

try:
    import scipy.optimize  # noqa: E402
except ImportError:
    sys.modules["scipy.optimize"] = MagicMock()

sys.modules.setdefault("scipy.spatial", MagicMock())
sys.modules.setdefault("scipy.spatial.transform", MagicMock())

# Force-reload engine so its top-level from-imports bind to real scipy
import tit.stats.engine  # noqa: E402

importlib.reload(tit.stats.engine)

# ---------------------------------------------------------------------------
# Now safe to import from tit.stats
# ---------------------------------------------------------------------------
from tit.stats.config import (  # noqa: E402
    CorrelationConfig,
    GroupComparisonConfig,
    _TissueType,
    _nifti_pattern_for_tissue,
)
from tit.stats.__main__ import (  # noqa: E402
    _build_correlation_subjects,
    _build_group_subjects,
    _run_correlation,
    _run_group_comparison,
    main,
)


# ============================================================================
# _nifti_pattern_for_tissue — WHITE and ALL branches
# ============================================================================


@pytest.mark.unit
class TestNiftiPatternForTissue:
    """Cover the WHITE and ALL branches of _nifti_pattern_for_tissue."""

    def test_grey_pattern(self):
        result = _nifti_pattern_for_tissue(_TissueType.GREY)
        assert result == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"

    def test_white_pattern(self):
        result = _nifti_pattern_for_tissue(_TissueType.WHITE)
        assert result == "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"

    def test_all_pattern(self):
        result = _nifti_pattern_for_tissue(_TissueType.ALL)
        assert result == "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


# ============================================================================
# GroupComparisonConfig validation — 0 responders or 0 non-responders
# ============================================================================


@pytest.mark.unit
class TestGroupComparisonValidation:
    """Cover the ValueError when all subjects are responders or non-responders."""

    def test_all_responders_raises(self):
        subjects = [
            GroupComparisonConfig.Subject("s1", "sim1", 1),
            GroupComparisonConfig.Subject("s2", "sim2", 1),
        ]
        with pytest.raises(
            ValueError, match="at least one responder and one non-responder"
        ):
            GroupComparisonConfig(
                project_dir="/data/project",
                analysis_name="test",
                subjects=subjects,
            )

    def test_all_non_responders_raises(self):
        subjects = [
            GroupComparisonConfig.Subject("s1", "sim1", 0),
            GroupComparisonConfig.Subject("s2", "sim2", 0),
        ]
        with pytest.raises(
            ValueError, match="at least one responder and one non-responder"
        ):
            GroupComparisonConfig(
                project_dir="/data/project",
                analysis_name="test",
                subjects=subjects,
            )

    def test_empty_subjects_raises(self):
        with pytest.raises(
            ValueError, match="at least one responder and one non-responder"
        ):
            GroupComparisonConfig(
                project_dir="/data/project",
                analysis_name="test",
                subjects=[],
            )


# ============================================================================
# GroupComparisonConfig / CorrelationConfig with WHITE and ALL tissue types
# ============================================================================


@pytest.mark.unit
class TestConfigTissueTypes:
    """Cover __post_init__ path that sets nifti_file_pattern for WHITE and ALL."""

    def _make_group_subjects(self):
        return [
            GroupComparisonConfig.Subject("s1", "sim1", 1),
            GroupComparisonConfig.Subject("s2", "sim2", 0),
        ]

    def _make_corr_subjects(self):
        return [
            CorrelationConfig.Subject("s1", "sim1", 0.5),
            CorrelationConfig.Subject("s2", "sim2", 1.0),
            CorrelationConfig.Subject("s3", "sim3", 1.5),
        ]

    def test_group_white_tissue_type(self):
        cfg = GroupComparisonConfig(
            project_dir="/data",
            analysis_name="test",
            subjects=self._make_group_subjects(),
            tissue_type=GroupComparisonConfig.TissueType.WHITE,
        )
        assert (
            cfg.nifti_file_pattern
            == "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_group_all_tissue_type(self):
        cfg = GroupComparisonConfig(
            project_dir="/data",
            analysis_name="test",
            subjects=self._make_group_subjects(),
            tissue_type=GroupComparisonConfig.TissueType.ALL,
        )
        assert (
            cfg.nifti_file_pattern == "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_corr_white_tissue_type(self):
        cfg = CorrelationConfig(
            project_dir="/data",
            analysis_name="test",
            subjects=self._make_corr_subjects(),
            tissue_type=CorrelationConfig.TissueType.WHITE,
        )
        assert (
            cfg.nifti_file_pattern
            == "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_corr_all_tissue_type(self):
        cfg = CorrelationConfig(
            project_dir="/data",
            analysis_name="test",
            subjects=self._make_corr_subjects(),
            tissue_type=CorrelationConfig.TissueType.ALL,
        )
        assert (
            cfg.nifti_file_pattern == "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )


# ============================================================================
# _build_group_subjects / _build_correlation_subjects
# ============================================================================


@pytest.mark.unit
class TestBuildSubjects:
    """Test the JSON-to-Subject conversion helpers in __main__."""

    def test_build_group_subjects(self):
        raw = [
            {"subject_id": "001", "simulation_name": "sim_a", "response": 1},
            {"subject_id": "002", "simulation_name": "sim_b", "response": 0},
        ]
        subjects = _build_group_subjects(raw)
        assert len(subjects) == 2
        assert isinstance(subjects[0], GroupComparisonConfig.Subject)
        assert subjects[0].subject_id == "001"
        assert subjects[0].simulation_name == "sim_a"
        assert subjects[0].response == 1
        assert subjects[1].subject_id == "002"
        assert subjects[1].response == 0

    def test_build_group_subjects_empty(self):
        subjects = _build_group_subjects([])
        assert subjects == []

    def test_build_correlation_subjects(self):
        raw = [
            {"subject_id": "010", "simulation_name": "sim_x", "effect_size": 0.5},
            {
                "subject_id": "020",
                "simulation_name": "sim_y",
                "effect_size": 1.2,
                "weight": 2.0,
            },
        ]
        subjects = _build_correlation_subjects(raw)
        assert len(subjects) == 2
        assert isinstance(subjects[0], CorrelationConfig.Subject)
        assert subjects[0].subject_id == "010"
        assert subjects[0].effect_size == 0.5
        assert subjects[0].weight == 1.0  # default
        assert subjects[1].weight == 2.0

    def test_build_correlation_subjects_empty(self):
        subjects = _build_correlation_subjects([])
        assert subjects == []


# ============================================================================
# _run_group_comparison
# ============================================================================


@pytest.mark.unit
class TestRunGroupComparison:
    """Test _run_group_comparison with mocked permutation.run_group_comparison."""

    def _make_data(self):
        return {
            "project_dir": "/data/project",
            "analysis_name": "gc_test",
            "subjects": [
                {"subject_id": "s1", "simulation_name": "sim1", "response": 1},
                {"subject_id": "s2", "simulation_name": "sim2", "response": 0},
            ],
        }

    @patch("tit.stats.__main__.sys")
    def test_run_group_comparison_success(self, mock_sys):
        mock_result = MagicMock()
        mock_result.n_significant_clusters = 3
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ) as mock_run:
            data = self._make_data()
            _run_group_comparison(data)
            mock_run.assert_called_once()
            # Should call sys.exit(0) since n_significant_clusters >= 0
            mock_sys.exit.assert_called_once_with(0)

    @patch("tit.stats.__main__.sys")
    def test_run_group_comparison_with_all_options(self, mock_sys):
        mock_result = MagicMock()
        mock_result.n_significant_clusters = 0
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ) as mock_run:
            data = self._make_data()
            data["test_type"] = "paired"
            data["alternative"] = "greater"
            data["cluster_stat"] = "size"
            data["n_permutations"] = 500
            data["tissue_type"] = "white"
            _run_group_comparison(data)
            # Verify the config was built correctly
            call_args = mock_run.call_args
            config = call_args[0][0]
            assert config.test_type == GroupComparisonConfig.TestType.PAIRED
            assert (
                config.alternative == GroupComparisonConfig.Alternative.GREATER
            )
            assert config.cluster_stat == GroupComparisonConfig.ClusterStat.SIZE
            assert config.n_permutations == 500
            assert config.tissue_type == GroupComparisonConfig.TissueType.WHITE
            mock_sys.exit.assert_called_once_with(0)

    @patch("tit.stats.__main__.sys")
    def test_run_group_comparison_negative_clusters(self, mock_sys):
        """Result with n_significant_clusters < 0 should exit with 1."""
        mock_result = MagicMock()
        mock_result.n_significant_clusters = -1
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ):
            data = self._make_data()
            _run_group_comparison(data)
            mock_sys.exit.assert_called_once_with(1)


# ============================================================================
# _run_correlation
# ============================================================================


@pytest.mark.unit
class TestRunCorrelation:
    """Test _run_correlation with mocked permutation.run_correlation."""

    def _make_data(self):
        return {
            "project_dir": "/data/project",
            "analysis_name": "corr_test",
            "subjects": [
                {"subject_id": "s1", "simulation_name": "sim1", "effect_size": 0.5},
                {"subject_id": "s2", "simulation_name": "sim2", "effect_size": 1.0},
                {"subject_id": "s3", "simulation_name": "sim3", "effect_size": 1.5},
            ],
        }

    @patch("tit.stats.__main__.sys")
    def test_run_correlation_success(self, mock_sys):
        mock_result = MagicMock()
        mock_result.n_significant_clusters = 2
        with patch(
            "tit.stats.permutation.run_correlation", return_value=mock_result
        ) as mock_run:
            data = self._make_data()
            _run_correlation(data)
            mock_run.assert_called_once()
            mock_sys.exit.assert_called_once_with(0)

    @patch("tit.stats.__main__.sys")
    def test_run_correlation_with_options(self, mock_sys):
        mock_result = MagicMock()
        mock_result.n_significant_clusters = 0
        with patch(
            "tit.stats.permutation.run_correlation", return_value=mock_result
        ) as mock_run:
            data = self._make_data()
            data["correlation_type"] = "spearman"
            data["cluster_stat"] = "size"
            data["n_permutations"] = 200
            data["effect_metric"] = "Improvement Score"
            _run_correlation(data)
            config = mock_run.call_args[0][0]
            assert (
                config.correlation_type
                == CorrelationConfig.CorrelationType.SPEARMAN
            )
            assert config.cluster_stat == CorrelationConfig.ClusterStat.SIZE
            assert config.n_permutations == 200
            assert config.effect_metric == "Improvement Score"
            mock_sys.exit.assert_called_once_with(0)

    @patch("tit.stats.__main__.sys")
    def test_run_correlation_negative_clusters(self, mock_sys):
        mock_result = MagicMock()
        mock_result.n_significant_clusters = -1
        with patch(
            "tit.stats.permutation.run_correlation", return_value=mock_result
        ):
            data = self._make_data()
            _run_correlation(data)
            mock_sys.exit.assert_called_once_with(1)


# ============================================================================
# main()
# ============================================================================


@pytest.mark.unit
class TestMain:
    """Test main() entry point — JSON parsing and mode dispatch."""

    def _write_config(self, tmp_path, data):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(data))
        return str(config_path)

    @patch("tit.stats.__main__._run_group_comparison")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    def test_main_group_comparison_mode(
        self, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        data = {
            "mode": "group_comparison",
            "project_dir": "/data/project",
            "analysis_name": "test_gc",
            "subjects": [
                {"subject_id": "s1", "simulation_name": "sim1", "response": 1},
                {"subject_id": "s2", "simulation_name": "sim2", "response": 0},
            ],
        }
        config_path = self._write_config(tmp_path, data)

        with patch.object(sys, "argv", ["__main__", config_path]):
            main()

        mock_setup.assert_called_once_with("INFO")
        mock_stream.assert_called_once_with("tit.stats")
        mock_gc.assert_called_once()
        mock_corr.assert_not_called()
        # Verify the data dict passed to _run_group_comparison has mode popped
        call_data = mock_gc.call_args[0][0]
        assert "mode" not in call_data
        assert call_data["project_dir"] == "/data/project"

    @patch("tit.stats.__main__._run_group_comparison")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    def test_main_correlation_mode(
        self, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        data = {
            "mode": "correlation",
            "project_dir": "/data/project",
            "analysis_name": "test_corr",
            "subjects": [
                {"subject_id": "s1", "simulation_name": "sim1", "effect_size": 0.5},
                {"subject_id": "s2", "simulation_name": "sim2", "effect_size": 1.0},
                {"subject_id": "s3", "simulation_name": "sim3", "effect_size": 1.5},
            ],
        }
        config_path = self._write_config(tmp_path, data)

        with patch.object(sys, "argv", ["__main__", config_path]):
            main()

        mock_corr.assert_called_once()
        mock_gc.assert_not_called()

    @patch("tit.stats.__main__._run_group_comparison")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    def test_main_default_mode_is_group_comparison(
        self, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        """When 'mode' key is absent, should default to group_comparison."""
        data = {
            "project_dir": "/data/project",
            "analysis_name": "test_default",
            "subjects": [
                {"subject_id": "s1", "simulation_name": "sim1", "response": 1},
                {"subject_id": "s2", "simulation_name": "sim2", "response": 0},
            ],
        }
        config_path = self._write_config(tmp_path, data)

        with patch.object(sys, "argv", ["__main__", config_path]):
            main()

        mock_gc.assert_called_once()
        mock_corr.assert_not_called()


# ============================================================================
# nifti.load_subject_nifti_ti_toolbox FileNotFoundError with dir listing
# ============================================================================


@pytest.mark.unit
class TestNiftiFileNotFound:
    """Cover the FileNotFoundError path in nifti.load_subject_nifti_ti_toolbox
    when the directory exists but the specific file doesn't."""

    def test_file_not_found_with_directory_listing(self, tmp_path, init_pm):
        """When the nifti directory exists but file is missing, error should
        list existing files in the directory."""
        pm = init_pm

        # Build the expected directory structure
        sim_dir = os.path.join(
            pm.simulation("001", "test_sim"), "TI", "niftis"
        )
        os.makedirs(sim_dir, exist_ok=True)

        # Create some files in the directory so they show in the error
        for fname in ("other_file.nii.gz", "another.nii.gz"):
            with open(os.path.join(sim_dir, fname), "w") as f:
                f.write("")

        from tit.stats.nifti import load_subject_nifti_ti_toolbox

        with pytest.raises(FileNotFoundError, match="Directory exists"):
            load_subject_nifti_ti_toolbox(
                subject_id="001",
                simulation_name="test_sim",
                nifti_file_pattern="nonexistent_{simulation_name}.nii.gz",
            )

    def test_file_not_found_includes_file_names(self, tmp_path, init_pm):
        """Error message should include the names of files in the directory."""
        pm = init_pm

        sim_dir = os.path.join(
            pm.simulation("001", "test_sim"), "TI", "niftis"
        )
        os.makedirs(sim_dir, exist_ok=True)

        # Create a known file
        with open(os.path.join(sim_dir, "existing_file.nii.gz"), "w") as f:
            f.write("")

        from tit.stats.nifti import load_subject_nifti_ti_toolbox

        with pytest.raises(FileNotFoundError, match="existing_file.nii.gz"):
            load_subject_nifti_ti_toolbox(
                subject_id="001",
                simulation_name="test_sim",
                nifti_file_pattern="missing_{simulation_name}.nii.gz",
            )

    def test_file_not_found_no_directory(self, tmp_path, init_pm):
        """When the nifti directory itself doesn't exist, a simpler error."""
        from tit.stats.nifti import load_subject_nifti_ti_toolbox

        with pytest.raises(FileNotFoundError, match="NIfTI file not found"):
            load_subject_nifti_ti_toolbox(
                subject_id="001",
                simulation_name="nonexistent_sim",
                nifti_file_pattern="grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
            )

    def test_file_not_found_many_files_truncated(self, tmp_path, init_pm):
        """When directory has >20 files, the error should show a truncation note."""
        pm = init_pm

        sim_dir = os.path.join(
            pm.simulation("001", "test_sim"), "TI", "niftis"
        )
        os.makedirs(sim_dir, exist_ok=True)

        # Create 25 files so we exceed the 20-file preview limit
        for i in range(25):
            with open(os.path.join(sim_dir, f"file_{i:03d}.nii.gz"), "w") as f:
                f.write("")

        from tit.stats.nifti import load_subject_nifti_ti_toolbox

        with pytest.raises(FileNotFoundError, match=r"showing first 20 of 25"):
            load_subject_nifti_ti_toolbox(
                subject_id="001",
                simulation_name="test_sim",
                nifti_file_pattern="missing_{simulation_name}.nii.gz",
            )

    def test_file_not_found_os_listdir_oserror(self, tmp_path, init_pm):
        """When os.listdir raises OSError, the error should still report
        with an empty file list (covers lines 73-74)."""
        pm = init_pm

        sim_dir = os.path.join(
            pm.simulation("001", "test_sim"), "TI", "niftis"
        )
        os.makedirs(sim_dir, exist_ok=True)

        from tit.stats.nifti import load_subject_nifti_ti_toolbox

        # Mock os.listdir to raise OSError while keeping os.path functions real
        with patch("tit.stats.nifti.os.listdir", side_effect=OSError("perm denied")):
            with pytest.raises(FileNotFoundError, match=r"Files in directory: \[\]"):
                load_subject_nifti_ti_toolbox(
                    subject_id="001",
                    simulation_name="test_sim",
                    nifti_file_pattern="missing_{simulation_name}.nii.gz",
                )
