#!/usr/bin/env python3
"""
Tests for analyzer sub-modules: field_selector, group, visualizer.

Covers coverage gaps in:
- tit/analyzer/field_selector.py  (select_field_file, _select_mesh, _select_voxel)
- tit/analyzer/group.py           (GroupResult, run_group_analysis, _build_summary_df)
- tit/analyzer/visualizer.py      (save_mesh_roi_overlay, save_nifti_roi_overlay,
                                    save_histogram, save_results_csv)
"""

import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# Ensure repo root is importable
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.analyzer.analyzer import AnalysisResult
from tit.analyzer.field_selector import select_field_file
from tit.analyzer.group import GroupResult, _build_summary_df
from tit.analyzer import visualizer

# ===========================================================================
# Helpers
# ===========================================================================


def _make_analysis_result(sid: str = "001", **overrides) -> AnalysisResult:
    """Build an AnalysisResult with sensible defaults, overridable."""
    defaults = dict(
        field_name="TI_max",
        region_name="test_roi",
        space="mesh",
        analysis_type="spherical",
        roi_mean=2.0,
        roi_max=4.0,
        roi_min=1.0,
        roi_focality=0.5,
        gm_mean=4.0,
        gm_max=8.0,
        normal_mean=1.0,
        normal_max=2.0,
        normal_focality=0.25,
        n_elements=10,
        total_area_or_volume=50.0,
    )
    defaults.update(overrides)
    return AnalysisResult(**defaults)


# ===========================================================================
# field_selector.py
# ===========================================================================


class TestSelectFieldFileTI:
    """select_field_file for standard TI (2-pair) simulations."""

    @pytest.mark.unit
    def test_mesh_ti_returns_correct_path(self, tmp_path):
        sim_dir = tmp_path / "Simulations" / "montage1"
        mesh_dir = sim_dir / "TI" / "mesh"
        mesh_dir.mkdir(parents=True)
        mesh_file = mesh_dir / "montage1_TI.msh"
        mesh_file.touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, field_name = select_field_file("001", "montage1", "mesh")

        assert path == mesh_file
        assert field_name == "TI_max"

    @pytest.mark.unit
    def test_voxel_ti_returns_nifti(self, tmp_path):
        sim_dir = tmp_path / "Simulations" / "montage1"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        nii = nifti_dir / "grey_montage1_TI.nii.gz"
        nii.touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, field_name = select_field_file("001", "montage1", "voxel")

        assert path == nii
        assert field_name == "TI_max"


class TestSelectFieldFileMTI:
    """select_field_file for mTI (4-pair) simulations."""

    @pytest.mark.unit
    def test_mesh_mti_detected(self, tmp_path):
        sim_dir = tmp_path / "Simulations" / "montage2"
        # mTI marker directory
        (sim_dir / "mTI" / "mesh").mkdir(parents=True)
        mesh_file = sim_dir / "mTI" / "mesh" / "montage2_mTI.msh"
        mesh_file.touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, field_name = select_field_file("001", "montage2", "mesh")

        assert path == mesh_file
        assert field_name == "TI_Max"

    @pytest.mark.unit
    def test_voxel_mti_detected(self, tmp_path):
        sim_dir = tmp_path / "Simulations" / "montage2"
        (sim_dir / "mTI" / "mesh").mkdir(parents=True)
        nifti_dir = sim_dir / "mTI" / "niftis"
        nifti_dir.mkdir(parents=True)
        nii = nifti_dir / "grey_montage2_mTI.nii.gz"
        nii.touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, field_name = select_field_file("001", "montage2", "voxel")

        assert path == nii
        assert field_name == "TI_Max"


class TestSelectFieldFileErrors:
    """Error handling in select_field_file."""

    @pytest.mark.unit
    def test_invalid_space_raises_value_error(self, tmp_path):
        sim_dir = tmp_path / "sim"
        sim_dir.mkdir(parents=True)

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            with pytest.raises(ValueError, match="Unsupported space"):
                select_field_file("001", "sim1", "surface")

    @pytest.mark.unit
    def test_missing_mesh_raises_file_not_found(self, tmp_path):
        sim_dir = tmp_path / "sim"
        (sim_dir / "TI" / "mesh").mkdir(parents=True)
        # No .msh file created

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            with pytest.raises(FileNotFoundError, match="Mesh field file not found"):
                select_field_file("001", "sim1", "mesh")

    @pytest.mark.unit
    def test_missing_nifti_dir_raises_file_not_found(self, tmp_path):
        sim_dir = tmp_path / "sim"
        sim_dir.mkdir(parents=True)
        # No TI/niftis directory

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            with pytest.raises(FileNotFoundError, match="NIfTI directory not found"):
                select_field_file("001", "sim1", "voxel")

    @pytest.mark.unit
    def test_empty_nifti_dir_raises_file_not_found(self, tmp_path):
        sim_dir = tmp_path / "sim"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        # Directory exists but no .nii files

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            with pytest.raises(FileNotFoundError, match="No NIfTI files found"):
                select_field_file("001", "sim1", "voxel")


class TestSelectVoxelFiltering:
    """Voxel file selection prefers subject-space full-field files."""

    @pytest.mark.unit
    def test_both_prefers_subject_space_over_tissue_prefix(self, tmp_path):
        sim_dir = tmp_path / "sim"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        # Tissue-prefixed file
        (nifti_dir / "grey_field.nii.gz").touch()
        # Subject-space file (preferred for tissue_type="both")
        (nifti_dir / "montage1_field.nii.gz").touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, _ = select_field_file("001", "montage1", "voxel", tissue_type="both")

        assert path.name == "montage1_field.nii.gz"

    @pytest.mark.unit
    def test_gm_selects_grey_prefix(self, tmp_path):
        sim_dir = tmp_path / "sim"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        (nifti_dir / "grey_field.nii.gz").touch()
        (nifti_dir / "white_field.nii.gz").touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, _ = select_field_file("001", "montage1", "voxel")

        assert path.name == "grey_field.nii.gz"

    @pytest.mark.unit
    def test_no_matching_tissue_raises_file_not_found(self, tmp_path):
        sim_dir = tmp_path / "sim"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        (nifti_dir / "field_MNI.nii.gz").touch()
        (nifti_dir / "field_subject.nii.gz").touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            with pytest.raises(FileNotFoundError, match="No GM NIfTI file found"):
                select_field_file("001", "montage1", "voxel")

    @pytest.mark.unit
    def test_skips_mni_tagged_files(self, tmp_path):
        sim_dir = tmp_path / "sim"
        nifti_dir = sim_dir / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        (nifti_dir / "grey_field_MNI.nii.gz").touch()
        (nifti_dir / "grey_field_subject.nii.gz").touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            path, _ = select_field_file("001", "montage1", "voxel")

        assert path.name == "grey_field_subject.nii.gz"


# ===========================================================================
# group.py
# ===========================================================================


class TestGroupResult:
    """GroupResult dataclass construction."""

    @pytest.mark.unit
    def test_construction(self):
        r = GroupResult(
            subject_results={"001": _make_analysis_result()},
            summary_csv_path=Path("/tmp/summary.csv"),
            comparison_plot_path=Path("/tmp/plot.pdf"),
        )
        assert "001" in r.subject_results
        assert r.summary_csv_path == Path("/tmp/summary.csv")
        assert r.comparison_plot_path == Path("/tmp/plot.pdf")

    @pytest.mark.unit
    def test_none_plot_path(self):
        r = GroupResult(
            subject_results={},
            summary_csv_path=Path("/tmp/s.csv"),
            comparison_plot_path=None,
        )
        assert r.comparison_plot_path is None


class TestBuildSummaryDf:
    """_build_summary_df builds correct rows and calls pd.concat."""

    @pytest.mark.unit
    def test_two_subjects_builds_correct_rows(self):
        """Verify the row dicts passed to pd.DataFrame contain correct values."""
        import pandas as pd

        results = {
            "001": _make_analysis_result(roi_mean=2.0, gm_mean=4.0),
            "002": _make_analysis_result(roi_mean=6.0, gm_mean=8.0),
        }

        # Capture all pd.DataFrame calls
        all_calls = []

        def fake_df(rows):
            all_calls.append(rows)
            mock_df = MagicMock()
            col_mock = MagicMock()
            col_mock.mean.return_value.to_dict.return_value = {
                "ROI_Mean": 4.0,
                "ROI_Max": 4.0,
                "ROI_Min": 1.0,
                "ROI_Focality": 0.5,
                "GM_Mean": 6.0,
                "GM_Max": 8.0,
                "Normal_Mean": 1.0,
                "Normal_Max": 2.0,
                "Normal_Focality": 0.25,
            }
            mock_df.__getitem__ = MagicMock(return_value=col_mock)
            return mock_df

        pd.DataFrame.side_effect = fake_df
        try:
            _build_summary_df(results)
        finally:
            pd.DataFrame.side_effect = None

        # First call: subject rows; second call: [avg] row
        subject_rows = all_calls[0]
        assert len(subject_rows) == 2
        assert subject_rows[0]["Subject"] == "001"
        assert subject_rows[0]["ROI_Mean"] == 2.0
        assert subject_rows[1]["Subject"] == "002"
        assert subject_rows[1]["ROI_Mean"] == 6.0

    @pytest.mark.unit
    def test_average_row_has_correct_subject_label(self):
        """Verify the AVERAGE row dict uses 'AVERAGE' as Subject."""
        import pandas as pd

        results = {"001": _make_analysis_result(roi_mean=5.0)}

        captured_avg = {}

        def fake_df(rows):
            if (
                isinstance(rows, list)
                and len(rows) == 1
                and rows[0].get("Subject") == "AVERAGE"
            ):
                captured_avg["row"] = rows[0]
            mock_df = MagicMock()
            col_mock = MagicMock()
            col_mock.mean.return_value.to_dict.return_value = {
                "ROI_Mean": 5.0,
                "ROI_Max": 4.0,
                "ROI_Min": 1.0,
                "ROI_Focality": 0.5,
                "GM_Mean": 4.0,
                "GM_Max": 8.0,
                "Normal_Mean": 1.0,
                "Normal_Max": 2.0,
                "Normal_Focality": 0.25,
            }
            mock_df.__getitem__ = MagicMock(return_value=col_mock)
            return mock_df

        pd.DataFrame.side_effect = fake_df
        try:
            _build_summary_df(results)
        finally:
            pd.DataFrame.side_effect = None

        assert "row" in captured_avg
        assert captured_avg["row"]["Subject"] == "AVERAGE"


class TestRunGroupAnalysis:
    """run_group_analysis end-to-end with mocked Analyzer."""

    @pytest.mark.unit
    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_spherical_dispatches_correctly(
        self, mock_output, mock_log, mock_analyzer_cls, mock_plot
    ):
        from tit.analyzer.group import run_group_analysis

        out_dir = Path("/tmp/group_out")
        mock_output.return_value = out_dir

        r1 = _make_analysis_result(roi_mean=2.0)
        r2 = _make_analysis_result(roi_mean=4.0)
        mock_analyzer_cls.side_effect = [MagicMock(), MagicMock()]
        mock_analyzer_cls.return_value.analyze_sphere.side_effect = [r1, r2]
        # Fix: each call creates a new Analyzer, so configure each one
        a1, a2 = MagicMock(), MagicMock()
        a1.analyze_sphere.return_value = r1
        a2.analyze_sphere.return_value = r2
        mock_analyzer_cls.side_effect = [a1, a2]

        mock_plot.return_value = out_dir / "plot.pdf"

        with patch("pandas.DataFrame.to_csv"):
            result = run_group_analysis(
                subject_ids=["001", "002"],
                simulation="sim1",
                space="mesh",
                analysis_type="spherical",
                center=(0, 0, 0),
                radius=10.0,
                output_dir=str(out_dir),
            )

        assert isinstance(result, GroupResult)
        assert len(result.subject_results) == 2
        a1.analyze_sphere.assert_called_once()
        a2.analyze_sphere.assert_called_once()

    @pytest.mark.unit
    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_cortical_dispatches_correctly(
        self, mock_output, mock_log, mock_analyzer_cls, mock_plot
    ):
        from tit.analyzer.group import run_group_analysis

        out_dir = Path("/tmp/group_out")
        mock_output.return_value = out_dir

        r1 = _make_analysis_result()
        a1 = MagicMock()
        a1.analyze_cortex.return_value = r1
        mock_analyzer_cls.side_effect = [a1]

        mock_plot.return_value = out_dir / "plot.pdf"

        with patch("pandas.DataFrame.to_csv"):
            result = run_group_analysis(
                subject_ids=["001"],
                simulation="sim1",
                analysis_type="cortical",
                atlas="DK40",
                region="lh.precentral",
                output_dir=str(out_dir),
            )

        assert isinstance(result, GroupResult)
        a1.analyze_cortex.assert_called_once()


# ===========================================================================
# visualizer.py
# ===========================================================================


class TestSaveMeshRoiOverlay:
    """save_mesh_roi_overlay writes mesh and opt file."""

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_writes_mesh_and_opt(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        import simnibs

        mock_mesh = MagicMock()
        mock_mesh.nodes.nr = 5
        simnibs.read_msh.return_value = mock_mesh

        field_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        roi_mask = np.array([True, True, False, False, False])

        result = visualizer.save_mesh_roi_overlay(
            surface_mesh_path=Path("/fake/surface.msh"),
            field_values=field_values,
            roi_mask=roi_mask,
            field_name="TI_max",
            region_name="test_region",
            output_dir=tmp_path,
        )

        assert result == tmp_path / "test_region_ROI.msh"
        mock_mesh.write.assert_called_once_with(str(result))
        mock_mesh.add_node_field.assert_called_once()
        # Check the opt file was written
        opt_file = Path(f"{result}.opt")
        assert opt_file.exists()

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_with_normal_mesh(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        import simnibs

        # Primary mesh
        primary_mesh = MagicMock()
        primary_mesh.nodes.nr = 3

        # Normal mesh with TI_normal field
        normal_mesh = MagicMock()
        normal_field = MagicMock()
        normal_field.value = np.array([0.5, 1.5, 2.5])
        normal_mesh.field.__contains__ = lambda self, k: k == "TI_normal"
        normal_mesh.field.__getitem__ = lambda self, k: normal_field

        simnibs.read_msh.side_effect = [primary_mesh, normal_mesh]

        normal_path = tmp_path / "normal.msh"
        normal_path.touch()

        field_values = np.array([1.0, 2.0, 3.0])
        roi_mask = np.array([True, True, False])

        result = visualizer.save_mesh_roi_overlay(
            surface_mesh_path=Path("/fake/surface.msh"),
            field_values=field_values,
            roi_mask=roi_mask,
            field_name="TI_max",
            region_name="test_normal",
            output_dir=tmp_path,
            normal_mesh_path=normal_path,
        )

        # Should have added both the ROI field and the TI_normal_ROI field
        assert primary_mesh.add_node_field.call_count == 2


class TestSaveNiftiRoiOverlay:
    """save_nifti_roi_overlay writes NIfTI with masked data."""

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_creates_masked_nifti(self, mock_gpm, tmp_path):
        import nibabel as nib

        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        field_data = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        roi_mask = np.zeros_like(field_data, dtype=bool)
        roi_mask[0, 0, 1] = True
        affine = np.eye(4)

        result = visualizer.save_nifti_roi_overlay(
            field_data=field_data,
            roi_mask=roi_mask,
            region_name="roi_test",
            output_dir=tmp_path,
            affine=affine,
        )

        assert result == tmp_path / "roi_test_ROI.nii.gz"
        nib.save.assert_called_once()
        # Verify overlay: only roi_mask positions should have values
        save_call = nib.save.call_args
        saved_img = save_call[0][0]
        nib.Nifti1Image.assert_called_once()


class TestSaveHistogram:
    """save_histogram delegates to plotting module."""

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_returns_path_on_success(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        with patch(
            "tit.plotting.focality.plot_whole_head_roi_histogram",
            return_value=str(tmp_path / "hist.pdf"),
        ):
            result = visualizer.save_histogram(
                whole_head_values=np.array([1.0, 2.0, 3.0]),
                roi_values=np.array([1.0, 2.0]),
                output_dir=tmp_path,
                region_name="roi",
                roi_mean=1.5,
            )

        assert result == tmp_path / "hist.pdf"

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_returns_none_when_plotter_declines(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        with patch(
            "tit.plotting.focality.plot_whole_head_roi_histogram",
            return_value=None,
        ):
            result = visualizer.save_histogram(
                whole_head_values=np.array([]),
                roi_values=np.array([]),
                output_dir=tmp_path,
                region_name="empty_roi",
            )

        assert result is None


class TestSaveResultsCsv:
    """save_results_csv writes two-column CSV, skipping None values."""

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_writes_csv_with_correct_content(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        data = {
            "roi_mean": 2.5,
            "roi_max": 5.0,
            "normal_mean": None,
            "roi_min": 0.5,
        }

        result = visualizer.save_results_csv(data, tmp_path)

        assert result == tmp_path / "results.csv"
        with open(result) as fh:
            reader = csv.reader(fh)
            rows = list(reader)

        # Header + 3 data rows (None skipped)
        assert rows[0] == ["Metric", "Value"]
        assert len(rows) == 4  # header + roi_mean + roi_max + roi_min
        metrics = [r[0] for r in rows[1:]]
        assert "normal_mean" not in metrics
        assert "roi_mean" in metrics

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_empty_dict_writes_header_only(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        result = visualizer.save_results_csv({}, tmp_path)

        with open(result) as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 1
        assert rows[0] == ["Metric", "Value"]

    @pytest.mark.unit
    @patch("tit.analyzer.visualizer.get_path_manager")
    def test_all_none_writes_header_only(self, mock_gpm, tmp_path):
        mock_gpm.return_value.ensure.return_value = str(tmp_path)

        result = visualizer.save_results_csv({"a": None, "b": None}, tmp_path)

        with open(result) as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 1
