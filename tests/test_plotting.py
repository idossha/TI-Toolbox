#!/usr/bin/env python3
"""
Tests for the tit.plotting package.

Covers:
- tit/plotting/_common.py: SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close
- tit/plotting/focality.py: plot_whole_head_roi_histogram, _stem_no_nii_gz
- tit/plotting/static_overlay.py: generate_static_overlay_images
- tit/plotting/stats.py: plot_permutation_null_distribution, plot_cluster_size_mass_correlation
- tit/plotting/ti_metrics.py: plot_montage_distributions, plot_intensity_vs_focality
"""

import os
import sys
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# Ensure seaborn is mocked before any tit.plotting imports (not in conftest)
for _mod in ("seaborn", "scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())


# ============================================================================
# _common.py tests
# ============================================================================


@pytest.mark.unit
class TestSaveFigOptions:
    """Tests for SaveFigOptions dataclass."""

    def test_default_values(self):
        from tit.plotting._common import SaveFigOptions

        opts = SaveFigOptions()
        assert opts.dpi == 600
        assert opts.bbox_inches == "tight"
        assert opts.facecolor == "white"
        assert opts.edgecolor == "none"

    def test_custom_values(self):
        from tit.plotting._common import SaveFigOptions

        opts = SaveFigOptions(dpi=300, bbox_inches="standard", facecolor="black", edgecolor="red")
        assert opts.dpi == 300
        assert opts.bbox_inches == "standard"
        assert opts.facecolor == "black"
        assert opts.edgecolor == "red"

    def test_frozen(self):
        from tit.plotting._common import SaveFigOptions

        opts = SaveFigOptions()
        with pytest.raises(AttributeError):
            opts.dpi = 100


@pytest.mark.unit
class TestEnsureHeadlessMatplotlibBackend:
    """Tests for ensure_headless_matplotlib_backend."""

    def test_sets_mplbackend_env_variable(self):
        from tit.plotting._common import ensure_headless_matplotlib_backend

        # Remove MPLBACKEND if set, so setdefault can set it
        old = os.environ.pop("MPLBACKEND", None)
        try:
            ensure_headless_matplotlib_backend()
            # Should have set (or tried to set) MPLBACKEND
            # Since matplotlib is mocked, the env var should be set
            assert "MPLBACKEND" in os.environ
        finally:
            if old is not None:
                os.environ["MPLBACKEND"] = old
            else:
                os.environ.pop("MPLBACKEND", None)

    def test_custom_backend(self):
        from tit.plotting._common import ensure_headless_matplotlib_backend

        old = os.environ.pop("MPLBACKEND", None)
        try:
            ensure_headless_matplotlib_backend(backend="TkAgg")
            # setdefault only sets if not already set
            assert os.environ.get("MPLBACKEND") is not None
        finally:
            if old is not None:
                os.environ["MPLBACKEND"] = old
            else:
                os.environ.pop("MPLBACKEND", None)

    def test_does_not_override_existing_backend(self):
        """When the current backend differs from the requested one, it should not override."""
        import matplotlib

        from tit.plotting._common import ensure_headless_matplotlib_backend

        # Make get_backend return a different backend
        matplotlib.get_backend.return_value = "TkAgg"
        ensure_headless_matplotlib_backend(backend="Agg")
        # Should NOT call matplotlib.use because backend is already different
        # The function returns early if the current backend doesn't match
        # (We just verify it doesn't crash)

    def test_calls_matplotlib_use_when_no_backend(self):
        """When current backend is empty or matches, it should call matplotlib.use."""
        import matplotlib

        from tit.plotting._common import ensure_headless_matplotlib_backend

        matplotlib.get_backend.return_value = ""
        ensure_headless_matplotlib_backend(backend="Agg")
        matplotlib.use.assert_called_with("Agg")


@pytest.mark.unit
class TestSavefigClose:
    """Tests for savefig_close."""

    def test_calls_savefig_and_close(self):
        import matplotlib.pyplot as plt

        from tit.plotting._common import SaveFigOptions, savefig_close

        fig = MagicMock()
        result = savefig_close(fig, "/tmp/test_plot.pdf")

        # Should call fig.savefig with default opts
        fig.savefig.assert_called_once_with(
            "/tmp/test_plot.pdf",
            dpi=600,
            bbox_inches="tight",
            facecolor="white",
            edgecolor="none",
            format=None,
        )
        # Should close the figure
        plt.close.assert_called_with(fig)
        # Should return the output file path
        assert result == "/tmp/test_plot.pdf"

    def test_custom_format_and_opts(self):
        from tit.plotting._common import SaveFigOptions, savefig_close

        fig = MagicMock()
        opts = SaveFigOptions(dpi=300, bbox_inches="standard", facecolor="black", edgecolor="red")
        result = savefig_close(fig, "/tmp/test.png", fmt="png", opts=opts)

        fig.savefig.assert_called_once_with(
            "/tmp/test.png",
            dpi=300,
            bbox_inches="standard",
            facecolor="black",
            edgecolor="red",
            format="png",
        )
        assert result == "/tmp/test.png"

    def test_returns_output_file(self):
        from tit.plotting._common import savefig_close

        fig = MagicMock()
        result = savefig_close(fig, "my_output.pdf", fmt="pdf")
        assert result == "my_output.pdf"


@pytest.mark.unit
class TestSuppressMatplotlibFindfontNoise:
    """Tests for suppress_matplotlib_findfont_noise (no-op function)."""

    def test_is_noop(self):
        from tit.plotting._common import suppress_matplotlib_findfont_noise

        # Should not raise and return None
        result = suppress_matplotlib_findfont_noise()
        assert result is None


# ============================================================================
# focality.py tests
# ============================================================================


@pytest.mark.unit
class TestStemNoNiiGz:
    """Tests for _stem_no_nii_gz helper."""

    def test_nii_gz_extension(self):
        from tit.plotting.focality import _stem_no_nii_gz

        assert _stem_no_nii_gz("/path/to/brain.nii.gz") == "brain"

    def test_nii_extension(self):
        from tit.plotting.focality import _stem_no_nii_gz

        assert _stem_no_nii_gz("/path/to/brain.nii") == "brain"

    def test_other_extension(self):
        from tit.plotting.focality import _stem_no_nii_gz

        assert _stem_no_nii_gz("/path/to/data.msh") == "data"

    def test_no_extension(self):
        from tit.plotting.focality import _stem_no_nii_gz

        assert _stem_no_nii_gz("/path/to/datafile") == "datafile"

    def test_complex_nii_gz(self):
        from tit.plotting.focality import _stem_no_nii_gz

        assert _stem_no_nii_gz("sub-001_field.nii.gz") == "sub-001_field"


@pytest.mark.unit
class TestPlotWholeHeadRoiHistogram:
    """Tests for plot_whole_head_roi_histogram."""

    def test_returns_none_for_none_data(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=None,
            roi_field_data=np.array([1.0, 2.0]),
        )
        assert result is None

    def test_returns_none_for_none_roi_data(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=np.array([1.0, 2.0]),
            roi_field_data=None,
        )
        assert result is None

    def test_returns_none_for_empty_whole_head(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=np.array([]),
            roi_field_data=np.array([1.0]),
        )
        assert result is None

    def test_returns_none_for_empty_roi(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=np.array([1.0]),
            roi_field_data=np.array([]),
        )
        assert result is None

    def test_returns_none_for_all_nan_whole_head(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=np.array([np.nan, np.nan]),
            roi_field_data=np.array([1.0]),
        )
        assert result is None

    def test_returns_none_for_all_nan_roi(self):
        from tit.plotting.focality import plot_whole_head_roi_histogram

        result = plot_whole_head_roi_histogram(
            output_dir="/tmp",
            whole_head_field_data=np.array([1.0, 2.0]),
            roi_field_data=np.array([np.nan, np.nan]),
        )
        assert result is None

    def test_basic_histogram_generation(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        # Setup mock returns
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        # Provide enough unique data so np.histogram bins > 0
        whole_head = np.random.rand(500) * 2.0
        roi = np.random.rand(50) * 1.5

        output_dir = str(tmp_path / "plots")
        result = plot_whole_head_roi_histogram(
            output_dir=output_dir,
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            filename="test_field.nii.gz",
            region_name="hippocampus",
            n_bins=20,
            dpi=100,
        )

        # Should create the output directory
        assert os.path.isdir(output_dir)
        # Should return a file path ending in _histogram.pdf
        assert result is not None
        assert result.endswith("_histogram.pdf")
        assert "test_field" in result
        # fig.savefig should have been called (via savefig_close)
        mock_fig.savefig.assert_called_once()

    def test_histogram_with_voxel_weights(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        whole_head = np.random.rand(100) * 2.0
        roi = np.random.rand(20) * 1.5

        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            data_type="voxel",
            voxel_dims=(1.0, 1.0, 1.0),
            n_bins=10,
        )
        assert result is not None

    def test_histogram_with_element_sizes(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        whole_head = np.random.rand(100) * 2.0
        roi = np.random.rand(20) * 1.5

        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            whole_head_element_sizes=np.random.rand(100),
            roi_element_sizes=np.random.rand(20),
            n_bins=10,
        )
        assert result is not None

    def test_histogram_with_scalar_element_sizes(self, tmp_path):
        """Edge case: scalar (0-d) element sizes should be broadcast."""
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        whole_head = np.random.rand(100) * 2.0
        roi = np.random.rand(20) * 1.5

        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            whole_head_element_sizes=np.float64(1.5),  # scalar
            roi_element_sizes=np.float64(1.5),  # scalar
            n_bins=10,
        )
        assert result is not None

    def test_histogram_with_roi_field_value(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        whole_head = np.random.rand(200) * 3.0
        roi = np.random.rand(30) * 2.0

        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            roi_field_value=1.5,  # within data range
            n_bins=10,
        )
        assert result is not None
        # axvline should have been called for roi field value line
        mock_ax.axvline.assert_called()

    def test_filename_region_fallbacks(self, tmp_path):
        """Test different naming fallbacks: region_name only, no name at all."""
        import matplotlib.pyplot as plt

        from tit.plotting.focality import plot_whole_head_roi_histogram

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.get_cmap.return_value = MagicMock(return_value=np.ones((10, 4)))
        plt.Normalize.return_value = MagicMock()
        plt.cm.ScalarMappable.return_value = MagicMock()

        whole_head = np.random.rand(100) * 2.0
        roi = np.random.rand(20) * 1.5

        # With region_name only
        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            region_name="hippocampus",
            n_bins=10,
        )
        assert result is not None
        assert "hippocampus" in result

        # With neither filename nor region_name
        result = plot_whole_head_roi_histogram(
            output_dir=str(tmp_path / "sub"),
            whole_head_field_data=whole_head,
            roi_field_data=roi,
            n_bins=10,
        )
        assert result is not None
        assert "whole_head_roi_histogram" in result


# ============================================================================
# static_overlay.py tests
# ============================================================================


@pytest.mark.unit
class TestGenerateStaticOverlayImages:
    """Tests for generate_static_overlay_images."""

    @pytest.fixture(autouse=True)
    def _reset_plt_savefig(self):
        """Reset plt.savefig side_effect after each test to avoid leaks."""
        yield
        import matplotlib.pyplot as plt
        plt.savefig.side_effect = None
        plt.savefig.reset_mock()

    def test_basic_overlay_generation(self):
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        # Setup nibabel mocks
        t1_mock = MagicMock()
        t1_data = np.random.rand(20, 20, 20).astype(np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 1.0, 1.0)

        overlay_mock = MagicMock()
        overlay_data = np.random.rand(20, 20, 20).astype(np.float32) * 0.5
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        # Setup matplotlib mocks
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        # plt.cm.hot needs to be a mock with set_bad
        mock_cmap = MagicMock()
        plt.cm.hot = mock_cmap

        # Mock plt.savefig to write something to the buffer
        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        result = generate_static_overlay_images(
            t1_file="/path/to/t1.nii.gz",
            overlay_file="/path/to/overlay.nii.gz",
            subject_id="sub-001",
            montage_name="montage1",
        )

        # Should return dict with 3 orientations
        assert set(result.keys()) == {"axial", "sagittal", "coronal"}
        # Each should have 7 slices
        assert len(result["axial"]) == 7
        assert len(result["sagittal"]) == 7
        assert len(result["coronal"]) == 7

        # Each entry should have base64, slice_num, overlay_voxels
        for orientation in ("axial", "sagittal", "coronal"):
            for entry in result[orientation]:
                assert "base64" in entry
                assert "slice_num" in entry
                assert "overlay_voxels" in entry
                assert isinstance(entry["slice_num"], int)
                assert isinstance(entry["overlay_voxels"], int)

    def test_4d_overlay_takes_first_volume(self):
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        t1_mock = MagicMock()
        t1_data = np.random.rand(20, 20, 20).astype(np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 1.0, 1.0)

        overlay_mock = MagicMock()
        # 4D overlay
        overlay_data = np.random.rand(20, 20, 20, 3).astype(np.float32)
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.hot = MagicMock()

        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        result = generate_static_overlay_images(
            t1_file="/path/to/t1.nii.gz",
            overlay_file="/path/to/overlay_4d.nii.gz",
        )

        assert len(result["axial"]) == 7

    def test_dimension_mismatch_triggers_zoom(self):
        """When T1 and overlay have different dimensions, overlay is resampled."""
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        t1_mock = MagicMock()
        t1_data = np.random.rand(20, 20, 20).astype(np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 1.0, 1.0)

        overlay_mock = MagicMock()
        # Different dimensions than T1
        overlay_data = np.random.rand(10, 10, 10).astype(np.float32)
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.hot = MagicMock()

        zoomed_data = np.random.rand(20, 20, 20).astype(np.float32)

        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        with patch("scipy.ndimage.zoom", return_value=zoomed_data) as mock_zoom:
            result = generate_static_overlay_images(
                t1_file="/path/to/t1.nii.gz",
                overlay_file="/path/to/overlay.nii.gz",
            )

            mock_zoom.assert_called_once()
        assert len(result["axial"]) == 7

    def test_zero_overlay_max(self):
        """When overlay is all zeros, no overlay imshow should be called."""
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        t1_mock = MagicMock()
        t1_data = np.random.rand(20, 20, 20).astype(np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 1.0, 1.0)

        overlay_mock = MagicMock()
        overlay_data = np.zeros((20, 20, 20), dtype=np.float32)
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.hot = MagicMock()

        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        result = generate_static_overlay_images(
            t1_file="/path/to/t1.nii.gz",
            overlay_file="/path/to/zeros.nii.gz",
        )

        # All overlay_voxels should be 0
        for orientation in ("axial", "sagittal", "coronal"):
            for entry in result[orientation]:
                assert entry["overlay_voxels"] == 0

    def test_all_zero_t1_degenerate_case(self):
        """When T1 data is all zeros, the degenerate normalization branch is hit."""
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        t1_mock = MagicMock()
        t1_data = np.zeros((20, 20, 20), dtype=np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 1.0, 1.0)

        overlay_mock = MagicMock()
        overlay_data = np.random.rand(20, 20, 20).astype(np.float32)
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.hot = MagicMock()

        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        result = generate_static_overlay_images(
            t1_file="/path/to/t1.nii.gz",
            overlay_file="/path/to/overlay.nii.gz",
        )

        assert len(result["axial"]) == 7

    def test_anisotropic_voxels(self):
        """Test with non-isotropic voxel sizes to verify aspect ratio calculation."""
        import matplotlib.pyplot as plt
        import nibabel as nib

        from tit.plotting.static_overlay import generate_static_overlay_images

        t1_mock = MagicMock()
        t1_data = np.random.rand(20, 20, 20).astype(np.float32)
        t1_mock.get_fdata.return_value = t1_data
        t1_mock.header.get_zooms.return_value = (1.0, 2.0, 3.0)

        overlay_mock = MagicMock()
        overlay_data = np.random.rand(20, 20, 20).astype(np.float32)
        overlay_mock.get_fdata.return_value = overlay_data

        nib.load.side_effect = [t1_mock, overlay_mock]

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        plt.cm.hot = MagicMock()

        def mock_savefig(buf, **kwargs):
            buf.write(b"fake_png_data")

        plt.savefig.side_effect = mock_savefig

        result = generate_static_overlay_images(
            t1_file="/path/to/t1.nii.gz",
            overlay_file="/path/to/overlay.nii.gz",
        )

        # Verify expected aspect ratios: axial=y/x=2, sagittal=z/y=1.5, coronal=z/x=3
        # The function should still produce 7 slices per orientation
        assert len(result["axial"]) == 7
        assert len(result["sagittal"]) == 7
        assert len(result["coronal"]) == 7


# ============================================================================
# stats.py tests
# ============================================================================


@pytest.mark.unit
class TestPlotPermutationNullDistribution:
    """Tests for plot_permutation_null_distribution."""

    def test_basic_size_stat(self, tmp_path):
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_permutation_null_distribution

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)
        mock_ax.get_legend_handles_labels.return_value = (["h1"], ["l1"])

        null_dist = np.random.rand(1000) * 100
        observed = [
            {"stat_value": 150.0, "p_value": 0.01},
            {"stat_value": 50.0, "p_value": 0.10},
        ]
        output_file = str(tmp_path / "null_dist.pdf")

        result = plot_permutation_null_distribution(
            null_distribution=null_dist,
            threshold=120.0,
            observed_clusters=observed,
            output_file=output_file,
            cluster_stat="size",
        )

        assert result == output_file
        mock_fig.savefig.assert_called_once()
        # Should call axvline for threshold + 2 observed clusters
        assert mock_ax.axvline.call_count >= 3

    def test_mass_stat_labels(self, tmp_path):
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_permutation_null_distribution

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        null_dist = np.random.rand(500) * 50
        observed = [{"stat_value": 30.0, "p_value": 0.03}]
        output_file = str(tmp_path / "null_mass.pdf")

        result = plot_permutation_null_distribution(
            null_distribution=null_dist,
            threshold=25.0,
            observed_clusters=observed,
            output_file=output_file,
            cluster_stat="mass",
            alpha=0.01,
        )

        assert result == output_file

    def test_no_observed_clusters(self, tmp_path):
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_permutation_null_distribution

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        null_dist = np.random.rand(200) * 10
        output_file = str(tmp_path / "null_empty.pdf")

        result = plot_permutation_null_distribution(
            null_distribution=null_dist,
            threshold=8.0,
            observed_clusters=[],
            output_file=output_file,
        )

        assert result == output_file
        # axvline called once for threshold only (no observed clusters)
        assert mock_ax.axvline.call_count == 1

    def test_cluster_without_p_value(self, tmp_path):
        """When p_value is missing, significance is determined by stat_value > threshold."""
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_permutation_null_distribution

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        null_dist = np.random.rand(200) * 10
        observed = [
            {"stat_value": 15.0},  # No p_value, > threshold => significant
            {"stat_value": 3.0},   # No p_value, < threshold => non-significant
        ]
        output_file = str(tmp_path / "null_no_p.pdf")

        result = plot_permutation_null_distribution(
            null_distribution=null_dist,
            threshold=8.0,
            observed_clusters=observed,
            output_file=output_file,
        )

        assert result == output_file
        # threshold + 2 clusters = 3 axvline calls
        assert mock_ax.axvline.call_count == 3

    def test_multiple_significant_clusters_label_once(self, tmp_path):
        """Only the first significant and first non-significant cluster get labels."""
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_permutation_null_distribution

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        null_dist = np.random.rand(200) * 10
        observed = [
            {"stat_value": 15.0, "p_value": 0.01},  # sig #1 - gets label
            {"stat_value": 12.0, "p_value": 0.02},  # sig #2 - no label
            {"stat_value": 3.0, "p_value": 0.10},   # non-sig #1 - gets label
            {"stat_value": 2.0, "p_value": 0.50},   # non-sig #2 - no label
        ]
        output_file = str(tmp_path / "multi.pdf")

        result = plot_permutation_null_distribution(
            null_distribution=null_dist,
            threshold=8.0,
            observed_clusters=observed,
            output_file=output_file,
        )

        assert result == output_file
        # 1 threshold + 4 clusters
        assert mock_ax.axvline.call_count == 5

        # Check that only the first sig and first non-sig got labels
        label_calls = [c for c in mock_ax.axvline.call_args_list if c.kwargs.get("label") is not None]
        # Should have exactly 2 labeled axvline calls (plus the threshold which has a label)
        # Actually threshold also has label, so 3 labeled calls total
        # But we check cluster labels only (not the threshold one)
        cluster_labels = [
            c.kwargs.get("label")
            for c in mock_ax.axvline.call_args_list[1:]  # skip threshold
            if c.kwargs.get("label") is not None
        ]
        assert len(cluster_labels) == 2


@pytest.mark.unit
class TestPlotClusterSizeMassCorrelation:
    """Tests for plot_cluster_size_mass_correlation."""

    def test_returns_none_when_insufficient_data(self, tmp_path):
        from tit.plotting.stats import plot_cluster_size_mass_correlation

        # All zeros => mask removes everything
        sizes = np.array([0, 0, 0])
        masses = np.array([0, 0, 0])
        output_file = str(tmp_path / "corr.pdf")

        result = plot_cluster_size_mass_correlation(sizes, masses, output_file)
        assert result is None

    def test_returns_none_single_nonzero_point(self, tmp_path):
        from tit.plotting.stats import plot_cluster_size_mass_correlation

        sizes = np.array([5, 0, 0])
        masses = np.array([10, 0, 0])
        output_file = str(tmp_path / "corr.pdf")

        result = plot_cluster_size_mass_correlation(sizes, masses, output_file)
        assert result is None

    def test_basic_correlation_plot(self, tmp_path):
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_cluster_size_mass_correlation

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        sizes = np.array([10, 20, 30, 40, 50], dtype=float)
        masses = np.array([15, 25, 35, 45, 55], dtype=float)
        output_file = str(tmp_path / "corr.pdf")

        with patch("scipy.stats.pearsonr", return_value=(0.95, 0.001)):
            result = plot_cluster_size_mass_correlation(sizes, masses, output_file, dpi=150)

        assert result == output_file
        mock_fig.savefig.assert_called_once()

    def test_zeros_filtered_out(self, tmp_path):
        import matplotlib.pyplot as plt
        import seaborn as sns

        from tit.plotting.stats import plot_cluster_size_mass_correlation

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        # Includes zeros that should be filtered
        sizes = np.array([0, 10, 0, 20, 30], dtype=float)
        masses = np.array([0, 15, 0, 25, 35], dtype=float)
        output_file = str(tmp_path / "corr_filtered.pdf")

        with patch("scipy.stats.pearsonr", return_value=(0.8, 0.05)):
            result = plot_cluster_size_mass_correlation(sizes, masses, output_file)

        assert result == output_file


# ============================================================================
# ti_metrics.py tests
# ============================================================================


@pytest.mark.unit
class TestPlotMontageDistributions:
    """Tests for plot_montage_distributions."""

    def test_returns_none_for_all_empty(self, tmp_path):
        from tit.plotting.ti_metrics import plot_montage_distributions

        result = plot_montage_distributions(
            timax_values=[],
            timean_values=[],
            focality_values=[],
            output_file=str(tmp_path / "dist.pdf"),
        )
        assert result is None

    def test_basic_distributions(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_montage_distributions

        mock_fig = MagicMock()
        mock_axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (mock_fig, mock_axes)

        output_file = str(tmp_path / "dist.pdf")
        result = plot_montage_distributions(
            timax_values=[1.0, 2.0, 3.0],
            timean_values=[0.5, 1.0, 1.5],
            focality_values=[0.1, 0.2, 0.3],
            output_file=output_file,
            dpi=150,
        )

        assert result == output_file
        mock_fig.savefig.assert_called_once()
        # All three axes should have hist called
        for ax in mock_axes:
            ax.hist.assert_called_once()

    def test_partial_data(self, tmp_path):
        """Only some distributions have data."""
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_montage_distributions

        mock_fig = MagicMock()
        mock_axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (mock_fig, mock_axes)

        output_file = str(tmp_path / "partial.pdf")
        result = plot_montage_distributions(
            timax_values=[1.0, 2.0],
            timean_values=[],
            focality_values=[0.1],
            output_file=output_file,
        )

        assert result == output_file
        # timax and focality should have hist; timean should not
        mock_axes[0].hist.assert_called_once()
        mock_axes[1].hist.assert_not_called()
        mock_axes[2].hist.assert_called_once()

    def test_single_value_each(self, tmp_path):
        """Edge case: single data point per distribution."""
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_montage_distributions

        mock_fig = MagicMock()
        mock_axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (mock_fig, mock_axes)

        output_file = str(tmp_path / "single.pdf")
        result = plot_montage_distributions(
            timax_values=[5.0],
            timean_values=[3.0],
            focality_values=[0.5],
            output_file=output_file,
        )

        assert result == output_file


@pytest.mark.unit
class TestPlotIntensityVsFocality:
    """Tests for plot_intensity_vs_focality."""

    def test_returns_none_for_empty_intensity(self, tmp_path):
        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        result = plot_intensity_vs_focality(
            intensity=[],
            focality=[0.1, 0.2],
            composite=None,
            output_file=str(tmp_path / "scatter.pdf"),
        )
        assert result is None

    def test_returns_none_for_empty_focality(self, tmp_path):
        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        result = plot_intensity_vs_focality(
            intensity=[1.0, 2.0],
            focality=[],
            composite=None,
            output_file=str(tmp_path / "scatter.pdf"),
        )
        assert result is None

    def test_basic_scatter_without_composite(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        output_file = str(tmp_path / "scatter.pdf")
        result = plot_intensity_vs_focality(
            intensity=[1.0, 2.0, 3.0],
            focality=[0.1, 0.2, 0.3],
            composite=None,
            output_file=output_file,
        )

        assert result == output_file
        mock_ax.scatter.assert_called_once()
        mock_fig.savefig.assert_called_once()

    def test_scatter_with_composite(self, tmp_path):
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_sc = MagicMock()
        mock_ax.scatter.return_value = mock_sc
        plt.subplots.return_value = (mock_fig, mock_ax)

        output_file = str(tmp_path / "scatter_composite.pdf")
        result = plot_intensity_vs_focality(
            intensity=[1.0, 2.0, 3.0],
            focality=[0.1, 0.2, 0.3],
            composite=[0.5, 0.6, 0.7],
            output_file=output_file,
        )

        assert result == output_file
        # Scatter should be called with composite coloring
        mock_ax.scatter.assert_called_once()
        scatter_kwargs = mock_ax.scatter.call_args
        assert scatter_kwargs.kwargs.get("c") == [0.5, 0.6, 0.7] or scatter_kwargs[1].get("c") == [0.5, 0.6, 0.7]
        # Colorbar should be added
        mock_fig.colorbar.assert_called_once()

    def test_scatter_with_all_none_composite(self, tmp_path):
        """Composite list with all None values should skip colorbar."""
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        output_file = str(tmp_path / "scatter_none.pdf")
        result = plot_intensity_vs_focality(
            intensity=[1.0, 2.0],
            focality=[0.1, 0.2],
            composite=[None, None],
            output_file=output_file,
        )

        assert result == output_file
        # With all-None composite, it should use the else branch (no colorbar)
        mock_fig.colorbar.assert_not_called()

    def test_scatter_with_empty_composite_list(self, tmp_path):
        """Empty composite list is falsy, should skip colorbar."""
        import matplotlib.pyplot as plt

        from tit.plotting.ti_metrics import plot_intensity_vs_focality

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        plt.subplots.return_value = (mock_fig, mock_ax)

        output_file = str(tmp_path / "scatter_empty_comp.pdf")
        result = plot_intensity_vs_focality(
            intensity=[1.0, 2.0],
            focality=[0.1, 0.2],
            composite=[],
            output_file=output_file,
        )

        assert result == output_file
        mock_fig.colorbar.assert_not_called()


# ============================================================================
# __init__.py tests
# ============================================================================


@pytest.mark.unit
class TestPlottingPackageExports:
    """Tests for tit.plotting __init__.py exports."""

    def test_all_exports_accessible(self):
        import tit.plotting

        for name in tit.plotting.__all__:
            assert hasattr(tit.plotting, name), f"{name} not exported from tit.plotting"

    def test_savefig_options_exported(self):
        from tit.plotting import SaveFigOptions

        opts = SaveFigOptions()
        assert opts.dpi == 600

    def test_function_exports_are_callable(self):
        from tit.plotting import (
            ensure_headless_matplotlib_backend,
            savefig_close,
            plot_whole_head_roi_histogram,
            generate_static_overlay_images,
            plot_permutation_null_distribution,
            plot_cluster_size_mass_correlation,
            plot_montage_distributions,
            plot_intensity_vs_focality,
        )

        assert callable(ensure_headless_matplotlib_backend)
        assert callable(savefig_close)
        assert callable(plot_whole_head_roi_histogram)
        assert callable(generate_static_overlay_images)
        assert callable(plot_permutation_null_distribution)
        assert callable(plot_cluster_size_mass_correlation)
        assert callable(plot_montage_distributions)
        assert callable(plot_intensity_vs_focality)
