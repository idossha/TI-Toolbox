"""Tests for tit/stats/__main__.py and supplementary coverage for config.py and nifti.py.

Covers:
- __main__.main() with group_comparison and correlation modes
- __main__._run_group_comparison / _run_correlation
- __main__._emit_output_artifacts: the nine files a permutation run writes are reported
  as job artifacts (lane FX3; the sibling runners' cases are in
  tests/test_runner_artifacts.py, which cannot import this module's real-scipy restore)
- config._nifti_pattern_for_tissue WHITE and ALL branches
- config.GroupComparisonConfig validation: 0 responders or 0 non-responders
- nifti.load_subject_nifti_ti_toolbox FileNotFoundError with directory listing

Building `GroupComparisonConfig.Subject`/`CorrelationConfig.Subject` lists from raw JSON
dicts is `tit.config_io.deserialize_config`'s job now (see tests/test_config_schema.py's
round-trip coverage) -- `__main__.py` no longer hand-rolls `_build_group_subjects` /
`_build_correlation_subjects`.
"""

import importlib
import json
import os
import sys
from contextlib import nullcontext
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
    _run_correlation,
    _run_group_comparison,
    main,
)
from types import SimpleNamespace  # noqa: E402

# ============================================================================
# Shared helpers for the artifact-reporting cases below
# ============================================================================


def _read_events(path) -> list:
    """Every event line the runner wrote to $TIT_EVENTS_FILE, in order."""
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _artifact_paths(path) -> list:
    return [e["path"] for e in _read_events(path) if e["type"] == "artifact"]


def _results(path) -> list:
    return [e for e in _read_events(path) if e["type"] == "result"]


@pytest.fixture
def events_file(tmp_path, monkeypatch):
    """A fresh ``$TIT_EVENTS_FILE`` and a clean artifact accumulator."""
    from tit.jobs import events

    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("TIT_EVENTS_FILE", str(path))
    events._reset_state()
    yield path
    events._reset_state()


def _write_outputs(directory, names) -> list:
    os.makedirs(directory, exist_ok=True)
    written = []
    for name in names:
        p = os.path.join(directory, name)
        with open(p, "w") as fh:
            fh.write("x")
        written.append(p)
    return written


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
                analysis_name="test",
                subjects=subjects,
            )

    def test_empty_subjects_raises(self):
        with pytest.raises(
            ValueError, match="at least one responder and one non-responder"
        ):
            GroupComparisonConfig(
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
            analysis_name="test",
            subjects=self._make_group_subjects(),
            tissue_type=GroupComparisonConfig.TissueType.WHITE,
        )
        assert (
            cfg.nifti_file_pattern == "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_group_all_tissue_type(self):
        cfg = GroupComparisonConfig(
            analysis_name="test",
            subjects=self._make_group_subjects(),
            tissue_type=GroupComparisonConfig.TissueType.ALL,
        )
        assert cfg.nifti_file_pattern == "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"

    def test_corr_white_tissue_type(self):
        cfg = CorrelationConfig(
            analysis_name="test",
            subjects=self._make_corr_subjects(),
            tissue_type=CorrelationConfig.TissueType.WHITE,
        )
        assert (
            cfg.nifti_file_pattern == "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_corr_all_tissue_type(self):
        cfg = CorrelationConfig(
            analysis_name="test",
            subjects=self._make_corr_subjects(),
            tissue_type=CorrelationConfig.TissueType.ALL,
        )
        assert cfg.nifti_file_pattern == "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


# ============================================================================
# _run_group_comparison
# ============================================================================


def _make_group_config(**overrides) -> GroupComparisonConfig:
    subjects = overrides.pop(
        "subjects",
        [
            GroupComparisonConfig.Subject("s1", "sim1", 1),
            GroupComparisonConfig.Subject("s2", "sim2", 0),
        ],
    )
    return GroupComparisonConfig(
        analysis_name="gc_test", subjects=subjects, **overrides
    )


def _make_correlation_config(**overrides) -> CorrelationConfig:
    subjects = overrides.pop(
        "subjects",
        [
            CorrelationConfig.Subject("s1", "sim1", 0.5),
            CorrelationConfig.Subject("s2", "sim2", 1.0),
            CorrelationConfig.Subject("s3", "sim3", 1.5),
        ],
    )
    return CorrelationConfig(analysis_name="corr_test", subjects=subjects, **overrides)


@pytest.mark.unit
class TestRunGroupComparison:
    """Test _run_group_comparison with mocked permutation.run_group_comparison.

    ``_run_group_comparison`` now takes an already-built ``GroupComparisonConfig``
    (``__main__.main`` builds it via ``deserialize_config`` before dispatching) and
    returns an exit code rather than calling ``sys.exit`` itself.
    """

    def test_run_group_comparison_success(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.n_significant_clusters = 3
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ) as mock_run:
            assert _run_group_comparison(_make_group_config()) == 0
            mock_run.assert_called_once()

    def test_run_group_comparison_with_all_options(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.n_significant_clusters = 0
        config = _make_group_config(
            test_type=GroupComparisonConfig.TestType.PAIRED,
            alternative=GroupComparisonConfig.Alternative.GREATER,
            cluster_stat=GroupComparisonConfig.ClusterStat.SIZE,
            n_permutations=500,
            tissue_type=GroupComparisonConfig.TissueType.WHITE,
        )
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ) as mock_run:
            assert _run_group_comparison(config) == 0
            call_args = mock_run.call_args
            passed_config = call_args[0][0]
            assert passed_config.test_type == GroupComparisonConfig.TestType.PAIRED
            assert (
                passed_config.alternative == GroupComparisonConfig.Alternative.GREATER
            )
            assert passed_config.cluster_stat == GroupComparisonConfig.ClusterStat.SIZE
            assert passed_config.n_permutations == 500
            assert passed_config.tissue_type == GroupComparisonConfig.TissueType.WHITE

    def test_run_group_comparison_failure(self):
        """A failed result (``success=False``) should return exit code 1."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.n_significant_clusters = 0
        with patch(
            "tit.stats.permutation.run_group_comparison", return_value=mock_result
        ):
            assert _run_group_comparison(_make_group_config()) == 1


# ============================================================================
# _run_correlation
# ============================================================================


@pytest.mark.unit
class TestRunCorrelation:
    """Test _run_correlation with mocked permutation.run_correlation."""

    def test_run_correlation_success(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.n_significant_clusters = 2
        with patch(
            "tit.stats.permutation.run_correlation", return_value=mock_result
        ) as mock_run:
            assert _run_correlation(_make_correlation_config()) == 0
            mock_run.assert_called_once()

    def test_run_correlation_with_options(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.n_significant_clusters = 0
        config = _make_correlation_config(
            correlation_type=CorrelationConfig.CorrelationType.SPEARMAN,
            cluster_stat=CorrelationConfig.ClusterStat.SIZE,
            n_permutations=200,
            effect_metric="Improvement Score",
        )
        with patch(
            "tit.stats.permutation.run_correlation", return_value=mock_result
        ) as mock_run:
            assert _run_correlation(config) == 0
            passed_config = mock_run.call_args[0][0]
            assert (
                passed_config.correlation_type
                == CorrelationConfig.CorrelationType.SPEARMAN
            )
            assert passed_config.cluster_stat == CorrelationConfig.ClusterStat.SIZE
            assert passed_config.n_permutations == 200
            assert passed_config.effect_metric == "Improvement Score"

    def test_run_correlation_failure(self):
        """A failed result (``success=False``) should return exit code 1."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.n_significant_clusters = 0
        with patch("tit.stats.permutation.run_correlation", return_value=mock_result):
            assert _run_correlation(_make_correlation_config()) == 1


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
    @patch("tit.paths.get_path_manager")
    def test_main_group_comparison_mode(
        self, mock_pm, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        mock_gc.return_value = 0
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
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

        mock_setup.assert_called_once_with("INFO")
        mock_stream.assert_called_once_with("tit.stats")
        mock_gc.assert_called_once()
        mock_corr.assert_not_called()
        # main() now builds a typed GroupComparisonConfig (via deserialize_config)
        # before dispatching, not a raw dict with mode/project_dir popped.
        passed_config = mock_gc.call_args[0][0]
        assert isinstance(passed_config, GroupComparisonConfig)
        assert passed_config.analysis_name == "test_gc"

    @patch("tit.stats.__main__._run_group_comparison")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    @patch("tit.paths.get_path_manager")
    def test_main_correlation_mode(
        self, mock_pm, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        mock_corr.return_value = 0
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
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

        mock_corr.assert_called_once()
        mock_gc.assert_not_called()

    @patch("tit.stats.__main__._hold_locks")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    @patch("tit.paths.get_path_manager")
    def test_the_lock_request_still_sees_the_mode(
        self, mock_pm, mock_setup, mock_stream, mock_corr, mock_locks, tmp_path
    ):
        """``mode`` is popped before the config is built, but the lock key needs it.

        ``tit.jobs.locks.keys_for("stats", ...)`` reads ``mode`` off the request dict to
        build ``project:stats:<mode>/<analysis_name>``; handing it the already-popped dict
        filed every correlation run under the group_comparison key instead.
        """
        mock_corr.return_value = 0
        mock_locks.return_value = nullcontext()
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
            with pytest.raises(SystemExit):
                main()

        kind, subject_ids, config_dict = mock_locks.call_args[0]
        assert kind == "stats"
        assert config_dict["mode"] == "correlation"
        assert config_dict["analysis_name"] == "test_corr"

    @patch("tit.stats.__main__._run_group_comparison")
    @patch("tit.stats.__main__._run_correlation")
    @patch("tit.logger.add_stream_handler")
    @patch("tit.logger.setup_logging")
    @patch("tit.paths.get_path_manager")
    def test_main_default_mode_is_group_comparison(
        self, mock_pm, mock_setup, mock_stream, mock_corr, mock_gc, tmp_path
    ):
        """When 'mode' key is absent, should default to group_comparison."""
        mock_gc.return_value = 0
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
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

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
        sim_dir = os.path.join(pm.simulation("001", "test_sim"), "TI", "niftis")
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

        sim_dir = os.path.join(pm.simulation("001", "test_sim"), "TI", "niftis")
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

        sim_dir = os.path.join(pm.simulation("001", "test_sim"), "TI", "niftis")
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

        sim_dir = os.path.join(pm.simulation("001", "test_sim"), "TI", "niftis")
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


# ============================================================================
# artifact reporting (lane FX3)
# ============================================================================

#: The file set the maintainer's own group-comparison job left on disk while reporting
#: `artifacts: []` -- the evidence row of dev/notes/v3-pipelines/2026-09-03-smoke.md.
_STATS_OUTPUTS = [
    "average_non_responders.nii.gz",
    "average_responders.nii.gz",
    "analysis_summary.txt",
    "cluster_size_mass_correlation.pdf",
    "difference_map.nii.gz",
    "group_comparison_analysis_20260904.log",
    "permutation_details.txt",
    "permutation_null_distribution.pdf",
    "pvalues_map.nii.gz",
    "significant_voxels_mask.nii.gz",
]


@pytest.mark.unit
class TestStatsArtifacts:
    def test_group_comparison_reports_every_file_it_wrote(self, tmp_path, events_file):
        out_dir = tmp_path / "group_comparison" / "smoke"
        written = _write_outputs(out_dir, _STATS_OUTPUTS)
        result = SimpleNamespace(
            success=True, n_significant_clusters=2, output_dir=str(out_dir)
        )
        with patch("tit.stats.permutation.run_group_comparison", return_value=result):
            assert _run_group_comparison(MagicMock(), started=0.0) == 0

        assert sorted(_artifact_paths(events_file)) == sorted(written)

    def test_group_comparison_result_names_the_output_dir(self, tmp_path, events_file):
        out_dir = tmp_path / "group_comparison" / "smoke"
        _write_outputs(out_dir, ["analysis_summary.txt"])
        result = SimpleNamespace(
            success=True, n_significant_clusters=0, output_dir=str(out_dir)
        )
        with patch("tit.stats.permutation.run_group_comparison", return_value=result):
            _run_group_comparison(MagicMock(), started=0.0)

        [event] = _results(events_file)
        assert event["outputs"]["output_dir"] == str(out_dir)
        # The result event alone lists the job's files (events.emit_result's contract).
        assert [a["path"] for a in event["artifacts"]] == [
            str(out_dir / "analysis_summary.txt")
        ]

    def test_correlation_reports_its_files_too(self, tmp_path, events_file):
        out_dir = tmp_path / "correlation" / "smoke"
        written = _write_outputs(
            out_dir, ["correlation_map.nii.gz", "analysis_summary.txt"]
        )
        result = SimpleNamespace(
            success=True, n_significant_clusters=1, output_dir=str(out_dir)
        )
        with patch("tit.stats.permutation.run_correlation", return_value=result):
            assert _run_correlation(MagicMock(), started=0.0) == 0

        assert sorted(_artifact_paths(events_file)) == sorted(written)

    def test_a_non_string_output_dir_is_not_fatal(self, events_file):
        """A partial/mocked result must not turn a finished analysis into a failure."""
        result = MagicMock()
        result.success = True
        result.n_significant_clusters = 0
        with patch("tit.stats.permutation.run_group_comparison", return_value=result):
            assert _run_group_comparison(MagicMock(), started=0.0) == 0
        assert _artifact_paths(events_file) == []
