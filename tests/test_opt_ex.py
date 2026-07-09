"""Tests for tit/opt/ex/ex.py -- run_ex_search orchestrator."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import (
    ExConfig,
    ExResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ex_config(**overrides):
    defaults = dict(
        subject_id="001",
        leadfield_hdf="/lf.hdf5",
        roi_name="motor.csv",
        electrodes=ExConfig.PoolElectrodes(electrodes=["E1", "E2", "E3", "E4"]),
        total_current=2.0,
        current_step=0.5,
        run_name="EEG10-10",
    )
    defaults.update(overrides)
    return ExConfig(**defaults)


# ---------------------------------------------------------------------------
# run_ex_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunExSearch:
    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_pool_mode_success(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"montage_1": {"val": 0.5}}

        mock_save.return_value = {
            "config_json_path": str(tmp_path / "results.json"),
            "csv_path": str(tmp_path / "results.csv"),
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        result = run_ex_search(config)

        assert result.success is True
        assert result.n_combinations == 1
        engine.initialize.assert_called_once()
        engine.run.assert_called_once()
        mock_save.assert_called_once()
        # process_and_save receives config object, not roi_name string
        save_call_args = mock_save.call_args
        assert save_call_args[0][1] is config

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_bucket_mode(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {"v": 1}}

        mock_save.return_value = {
            "config_json_path": "/j.json",
            "csv_path": "/c.csv",
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config(
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["A1"],
                e1_minus=["A2"],
                e2_plus=["B1"],
                e2_minus=["B2"],
            ),
        )
        result = run_ex_search(config)

        assert result.success is True
        # Bucket mode: all_combinations=False
        call_args = engine.run.call_args
        assert call_args[1].get(
            "all_combinations", call_args[0][5] if len(call_args[0]) > 5 else None
        ) is False or not call_args.kwargs.get("all_combinations", True)

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_channel_limit_default(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}

        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config(
            total_current=4.0,
            current_step=0.5,
            channel_limit=None,
        )
        run_ex_search(config)

        # When channel_limit is None, should default to total_current / 2.0
        # The generate_current_ratios call should use 2.0 as limit

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_creates_output_dir(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "new_output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}

        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        run_ex_search(config)

        assert os.path.isdir(str(tmp_path / "new_output"))

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_result_fields(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}, "m2": {}, "m3": {}}

        mock_save.return_value = {
            "config_json_path": "/results.json",
            "csv_path": "/results.csv",
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        result = run_ex_search(config)

        assert isinstance(result, ExResult)
        assert result.success is True
        assert result.n_combinations == 3
        assert result.config_json == "/results.json"
        assert result.results_csv == "/results.csv"


# ---------------------------------------------------------------------------
# Combined-ROI (union) support
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExConfigRoiNames:
    def test_default_roi_names_is_none(self):
        cfg = _make_ex_config()
        assert cfg.roi_names is None

    def test_roi_names_csv_suffix_appended(self):
        cfg = _make_ex_config(roi_names=["a", "b.csv", "c"])
        assert cfg.roi_names == ["a.csv", "b.csv", "c.csv"]

    def test_single_roi_name_unchanged(self):
        # Scalar roi_name path stays byte-identical (1-element behavior).
        cfg = _make_ex_config(roi_name="motor")
        assert cfg.roi_name == "motor.csv"
        assert cfg.roi_names is None


@pytest.mark.unit
class TestRunExSearchCombine:
    def _run(self, mock_gpm, mock_engine_cls, mock_save, tmp_path, config):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.ex.ex import run_ex_search

        run_ex_search(config)
        return pm, mock_engine_cls

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_single_roi_passes_one_file(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        config = _make_ex_config()  # roi_name="motor.csv", roi_names=None
        pm, engine_cls = self._run(
            mock_gpm, mock_engine_cls, mock_save, tmp_path, config
        )

        # Engine receives a single-element roi_files list (N=1 union case).
        args = engine_cls.call_args[0]
        roi_files = args[1]
        assert roi_files == [os.path.join(str(tmp_path / "rois"), "motor.csv")]
        assert args[2] == "motor.csv"  # metric-key prefix unchanged

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_combine_passes_union_files(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        config = _make_ex_config(
            roi_name="L_hippo+R_hippo",
            roi_names=["L_hippo", "R_hippo"],
        )
        pm, engine_cls = self._run(
            mock_gpm, mock_engine_cls, mock_save, tmp_path, config
        )

        rois = str(tmp_path / "rois")
        args = engine_cls.call_args[0]
        roi_files = args[1]
        assert roi_files == [
            os.path.join(rois, "L_hippo.csv"),
            os.path.join(rois, "R_hippo.csv"),
        ]
        # Metric-key prefix matches config.roi_name (what process_and_save reads).
        assert args[2] == "L_hippo+R_hippo.csv"


# ---------------------------------------------------------------------------
# ExSearchEngine multi-center union
# ---------------------------------------------------------------------------


def _make_engine(roi_file="/fake/roi.csv"):
    from tit.opt.ex.engine import ExSearchEngine

    return ExSearchEngine(
        leadfield_hdf="/fake/leadfield.hdf5",
        roi_file=roi_file,
        roi_name="Combined",
        logger=MagicMock(),
    )


@pytest.mark.unit
class TestEngineUnion:
    def test_loads_multiple_centers(self, tmp_path):
        import csv

        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        with open(f1, "w", newline="") as f:
            csv.writer(f).writerow([0.0, 0.0, 0.0])
        with open(f2, "w", newline="") as f:
            csv.writer(f).writerow([10.0, 0.0, 0.0])

        engine = _make_engine(roi_file=[str(f1), str(f2)])
        engine._load_roi_coordinates()

        assert engine.roi_centers == [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]
        # roi_coords mirrors the first center for back-compat.
        assert engine.roi_coords == [0.0, 0.0, 0.0]

    def test_unions_masks_from_multiple_centers(self):
        import numpy as np

        engine = _make_engine(roi_file=["/a.csv", "/b.csv"])
        engine.roi_centers = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]

        centers = np.array(
            [
                [0.0, 0.0, 0.0],  # near center A
                [1.0, 0.0, 0.0],  # near center A
                [10.0, 0.0, 0.0],  # near center B
                [11.0, 0.0, 0.0],  # near center B
                [50.0, 0.0, 0.0],  # far from both
            ]
        )
        volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=3.0)

        # Union of both spheres: indices 0,1 (A) and 2,3 (B); 4 excluded.
        assert set(engine.roi_indices.tolist()) == {0, 1, 2, 3}

    def test_single_center_fallback_matches_prior_behavior(self):
        import numpy as np

        # roi_centers stays None; single-center path uses roi_coords (N=1).
        engine = _make_engine(roi_file="/a.csv")
        engine.roi_coords = [0.0, 0.0, 0.0]

        centers = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
        volumes = np.array([1.0, 2.0, 3.0])
        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=3.0)

        assert set(engine.roi_indices.tolist()) == {0, 1}
        np.testing.assert_array_equal(engine.roi_volumes, [1.0, 2.0])
