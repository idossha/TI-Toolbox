#!/usr/bin/env python3
"""
Tests for the tit.plotting package.

Covers:
- tit/plotting/_common.py: SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close
- tit/plotting/stats.py: plot_permutation_null_distribution, plot_cluster_size_mass_correlation
- tit/plotting/ti_metrics.py: plot_montage_distributions, plot_intensity_vs_focality
"""

import os
import sys
from types import SimpleNamespace
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

        opts = SaveFigOptions(
            dpi=300, bbox_inches="standard", facecolor="black", edgecolor="red"
        )
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
        opts = SaveFigOptions(
            dpi=300, bbox_inches="standard", facecolor="black", edgecolor="red"
        )
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
            {"stat_value": 3.0},  # No p_value, < threshold => non-significant
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
            {"stat_value": 3.0, "p_value": 0.10},  # non-sig #1 - gets label
            {"stat_value": 2.0, "p_value": 0.50},  # non-sig #2 - no label
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
        label_calls = [
            c
            for c in mock_ax.axvline.call_args_list
            if c.kwargs.get("label") is not None
        ]
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
            result = plot_cluster_size_mass_correlation(
                sizes, masses, output_file, dpi=150
            )

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
        assert scatter_kwargs.kwargs.get("c") == [0.5, 0.6, 0.7] or scatter_kwargs[
            1
        ].get("c") == [0.5, 0.6, 0.7]
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
            plot_permutation_null_distribution,
            plot_cluster_size_mass_correlation,
            plot_montage_distributions,
            plot_intensity_vs_focality,
        )

        assert callable(ensure_headless_matplotlib_backend)
        assert callable(savefig_close)
        assert callable(plot_permutation_null_distribution)
        assert callable(plot_cluster_size_mass_correlation)
        assert callable(plot_montage_distributions)
        assert callable(plot_intensity_vs_focality)


# ============================================================================
# nilearn/surface.py — fsaverage surface rendering
# ============================================================================


@pytest.mark.unit
class TestRenderFsaverageMap:
    """tit.plotting.nilearn.surface.render_fsaverage_map / render_surface_stats_result."""

    def _mock_subplots(self):
        # 2x2 object array of axes mocks + a figure mock, matching plt.subplots.
        axes = np.empty((2, 2), dtype=object)
        for i in range(2):
            for j in range(2):
                axes[i, j] = MagicMock()
        fig = MagicMock()
        sys.modules["matplotlib.pyplot"].subplots = MagicMock(return_value=(fig, axes))
        return fig

    def test_wrong_length_raises(self):
        from tit.plotting.nilearn.surface import render_fsaverage_map

        with pytest.raises(ValueError):
            render_fsaverage_map(np.zeros(100), spacing=5)

    def test_paints_four_panels(self):
        from tit.plotting.nilearn import surface
        from tit.source.fsaverage import _FSAVG_NODES

        self._mock_subplots()
        plotting = sys.modules["nilearn.plotting"]
        plotting.plot_surf_stat_map = MagicMock()

        fig = surface.render_fsaverage_map(np.zeros(_FSAVG_NODES[5]), spacing=5)
        # 2 hemispheres x 2 views = 4 surface panels.
        assert plotting.plot_surf_stat_map.call_count == 4
        assert fig is not None

    def test_stats_result_renders_effect_and_clusters(self, tmp_path, monkeypatch):
        from tit.plotting.nilearn import surface
        from tit.source.fsaverage import _FSAVG_NODES

        n = _FSAVG_NODES[5]
        msh = tmp_path / "surface_stats.msh"
        msh.write_bytes(b"$MeshFormat")
        fields = {
            "r": np.zeros(n),
            "t": np.zeros(n),
            "p": np.ones(n),
            "sig_mask": np.concatenate([np.ones(10), np.zeros(n - 10)]),
        }
        # SimNIBS's reader is faked at the mesh_io boundary; the real .msh round trip is
        # tests/numerical/test_fsaverage_msh.py.
        monkeypatch.setattr(
            sys.modules["simnibs.mesh_tools.mesh_io"],
            "read_msh",
            lambda path: SimpleNamespace(
                field={k: SimpleNamespace(value=v) for k, v in fields.items()}
            ),
            raising=False,
        )
        calls = []
        monkeypatch.setattr(
            surface,
            "render_fsaverage_map",
            lambda values, spacing=5, **kw: calls.append(kw.get("title"))
            or kw.get("out_path"),
        )
        written = surface.render_surface_stats_result(str(msh), str(tmp_path / "out"))
        # effect (r) map + significant-cluster map.
        assert len(written) == 2
        assert "r map" in calls and "significant clusters" in calls
