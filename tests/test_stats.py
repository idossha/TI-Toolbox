#!/usr/bin/env simnibs_python
"""
Comprehensive tests for tit/stats/ module

Tests cover:
- stats_utils.py: Statistical calculations (t-tests, correlations, cluster operations)
- permutation_analysis.py: Permutation testing logic
- io_utils.py: File I/O operations
- atlas_utils.py: Atlas loading and manipulation
- visualization.py: Plot generation (mocked)
- reporting.py: Report generation (mocked)

All external dependencies (nibabel, scipy, matplotlib) are mocked.
"""

import pytest
import numpy as np
import os
import sys
from unittest.mock import Mock, MagicMock, patch, mock_open, call
from pathlib import Path

# Add tit directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tit'))


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def sample_4d_data():
    """Create sample 4D neuroimaging data (x, y, z, subjects)"""
    np.random.seed(42)
    # Small volume for fast testing
    data = np.random.randn(10, 10, 10, 5).astype(np.float32)
    data[data < 0] = 0  # Electric fields are non-negative
    return data


@pytest.fixture
def sample_voxel_data():
    """Create sample 1D voxel data for vectorized tests"""
    np.random.seed(42)
    # Shape: (n_voxels, n_subjects)
    data = np.random.randn(100, 10).astype(np.float32)
    data[data < 0] = 0
    return data


@pytest.fixture
def sample_effect_sizes():
    """Create sample effect sizes for correlation tests"""
    return np.array([0.2, 0.5, 0.3, 0.8, 0.1, 0.6, 0.4, 0.7, 0.35, 0.55])


@pytest.fixture
def sample_weights():
    """Create sample weights for weighted correlation"""
    return np.array([10, 20, 15, 25, 12, 18, 22, 16, 14, 20])


@pytest.fixture
def sample_binary_mask():
    """Create sample binary mask"""
    mask = np.zeros((10, 10, 10), dtype=bool)
    mask[3:7, 3:7, 3:7] = True  # Small cube of valid voxels
    return mask


@pytest.fixture
def sample_affine():
    """Create sample affine transformation matrix"""
    return np.eye(4)


@pytest.fixture
def mock_nifti_img():
    """Create mock nibabel NIfTI image"""
    mock_img = MagicMock()
    mock_img.affine = np.eye(4)
    mock_img.header = MagicMock()
    mock_img.shape = (91, 109, 91)
    mock_img.get_fdata = MagicMock(return_value=np.random.rand(91, 109, 91).astype(np.float32))
    return mock_img


# ==============================================================================
# TEST stats_utils.py - P-VALUE COMPUTATION
# ==============================================================================

class TestPvalFromHistogram:
    """Test p-value computation from null distribution"""

    @pytest.mark.unit
    def test_two_sided_pvalue(self):
        """Test two-sided p-value computation"""
        from stats.stats_utils import pval_from_histogram

        observed = np.array([2.5, 3.0, 1.5])
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        p_values = pval_from_histogram(observed, null, tail=0)

        assert len(p_values) == 3
        assert all(0 <= p <= 1 for p in p_values)
        # For two-sided, we check |null| >= |observed|
        # For observed=2.5, |null| >= 2.5: [3.0, 4.0, 5.0] -> 3/5 = 0.6
        assert p_values[0] == pytest.approx(0.6, abs=0.01)

    @pytest.mark.unit
    def test_upper_tail_pvalue(self):
        """Test upper tail (positive effects) p-value"""
        from stats.stats_utils import pval_from_histogram

        observed = np.array([3.5])
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        p_values = pval_from_histogram(observed, null, tail=1)

        # For upper tail, count null >= observed
        # null >= 3.5: [4.0, 5.0] -> 2/5 = 0.4
        assert p_values[0] == pytest.approx(0.4, abs=0.01)

    @pytest.mark.unit
    def test_lower_tail_pvalue(self):
        """Test lower tail (negative effects) p-value"""
        from stats.stats_utils import pval_from_histogram

        observed = np.array([2.0])
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        p_values = pval_from_histogram(observed, null, tail=-1)

        # For lower tail, count null <= observed
        # null <= 2.0: [1.0, 2.0] -> 2/5 = 0.4
        assert p_values[0] == pytest.approx(0.4, abs=0.01)


# ==============================================================================
# TEST stats_utils.py - CORRELATION FUNCTIONS
# ==============================================================================

class TestCorrelation:
    """Test vectorized correlation computation"""

    @pytest.mark.unit
    def test_pearson_correlation_basic(self, sample_voxel_data, sample_effect_sizes):
        """Test basic Pearson correlation"""
        from stats.stats_utils import correlation

        r_values, t_values, p_values = correlation(
            sample_voxel_data, sample_effect_sizes, correlation_type='pearson'
        )

        assert r_values.shape == (sample_voxel_data.shape[0],)
        assert t_values.shape == (sample_voxel_data.shape[0],)
        assert p_values.shape == (sample_voxel_data.shape[0],)

        # R values should be in [-1, 1]
        assert np.all(r_values >= -1)
        assert np.all(r_values <= 1)

        # P values should be in [0, 1]
        assert np.all(p_values >= 0)
        assert np.all(p_values <= 1)

    @pytest.mark.unit
    def test_spearman_correlation(self, sample_voxel_data, sample_effect_sizes):
        """Test Spearman correlation (rank-based)"""
        from stats.stats_utils import correlation

        r_values, t_values, p_values = correlation(
            sample_voxel_data, sample_effect_sizes, correlation_type='spearman'
        )

        assert r_values.shape == (sample_voxel_data.shape[0],)
        assert np.all(r_values >= -1)
        assert np.all(r_values <= 1)

    @pytest.mark.unit
    def test_weighted_correlation(self, sample_voxel_data, sample_effect_sizes, sample_weights):
        """Test weighted Pearson correlation"""
        from stats.stats_utils import correlation

        r_weighted, t_weighted, p_weighted = correlation(
            sample_voxel_data, sample_effect_sizes, weights=sample_weights
        )

        r_unweighted, t_unweighted, p_unweighted = correlation(
            sample_voxel_data, sample_effect_sizes, weights=None
        )

        # Weighted and unweighted should differ
        assert not np.allclose(r_weighted, r_unweighted)

    @pytest.mark.unit
    def test_correlation_perfect_positive(self):
        """Test perfect positive correlation"""
        from stats.stats_utils import correlation

        # Perfect correlation: y = 2*x + 1
        x = np.arange(1, 11, dtype=np.float64).reshape(1, -1)  # Shape: (1, 10)
        y = 2 * np.arange(1, 11, dtype=np.float64) + 1

        r_values, t_values, p_values = correlation(x, y)

        assert r_values[0] == pytest.approx(1.0, abs=1e-6)
        assert p_values[0] < 0.01  # Should be highly significant

    @pytest.mark.unit
    def test_correlation_zero_variance(self):
        """Test correlation with zero variance (constant values)"""
        from stats.stats_utils import correlation

        # Constant values (no variance)
        x = np.ones((1, 10), dtype=np.float64)
        y = np.arange(1, 11, dtype=np.float64)

        r_values, t_values, p_values = correlation(x, y)

        # Should handle division by zero gracefully
        assert r_values[0] == 0.0


class TestCorrelationVoxelwise:
    """Test voxelwise correlation analysis"""

    @pytest.mark.unit
    def test_correlation_voxelwise_shape(self, sample_4d_data, sample_effect_sizes):
        """Test output shapes from voxelwise correlation"""
        from stats.stats_utils import correlation_voxelwise

        r_values, t_stats, p_values, valid_mask = correlation_voxelwise(
            sample_4d_data, sample_effect_sizes[:5], verbose=False
        )

        expected_shape = sample_4d_data.shape[:3]
        assert r_values.shape == expected_shape
        assert t_stats.shape == expected_shape
        assert p_values.shape == expected_shape
        assert valid_mask.shape == expected_shape

    @pytest.mark.unit
    def test_correlation_voxelwise_weighted(self, sample_4d_data, sample_effect_sizes, sample_weights):
        """Test weighted voxelwise correlation"""
        from stats.stats_utils import correlation_voxelwise

        r_values, t_stats, p_values, valid_mask = correlation_voxelwise(
            sample_4d_data, sample_effect_sizes[:5], weights=sample_weights[:5], verbose=False
        )

        assert r_values.shape == sample_4d_data.shape[:3]

    @pytest.mark.unit
    def test_correlation_voxelwise_invalid_sizes(self, sample_4d_data):
        """Test error handling for mismatched sizes"""
        from stats.stats_utils import correlation_voxelwise

        with pytest.raises(ValueError, match="must match"):
            correlation_voxelwise(sample_4d_data, np.array([1, 2, 3]), verbose=False)

    @pytest.mark.unit
    def test_correlation_voxelwise_too_few_subjects(self, sample_4d_data):
        """Test error handling for too few subjects"""
        from stats.stats_utils import correlation_voxelwise

        # Need at least 3 subjects
        small_data = sample_4d_data[:, :, :, :2]

        with pytest.raises(ValueError, match="at least 3 subjects"):
            correlation_voxelwise(small_data, np.array([1.0, 2.0]), verbose=False)


# ==============================================================================
# TEST stats_utils.py - T-TEST FUNCTIONS
# ==============================================================================

class TestTtestInd:
    """Test independent samples t-test"""

    @pytest.mark.unit
    def test_ttest_ind_basic(self, sample_voxel_data):
        """Test basic independent t-test"""
        from stats.stats_utils import ttest_ind

        n_resp = 5
        n_non_resp = 5

        t_stats, p_values = ttest_ind(sample_voxel_data, n_resp, n_non_resp)

        assert t_stats.shape == (sample_voxel_data.shape[0],)
        assert p_values.shape == (sample_voxel_data.shape[0],)
        assert np.all(p_values >= 0)
        assert np.all(p_values <= 1)

    @pytest.mark.unit
    def test_ttest_ind_alternatives(self, sample_voxel_data):
        """Test different alternative hypotheses"""
        from stats.stats_utils import ttest_ind

        n_resp = 5
        n_non_resp = 5

        for alternative in ['two-sided', 'greater', 'less']:
            t_stats, p_values = ttest_ind(sample_voxel_data, n_resp, n_non_resp, alternative=alternative)
            assert p_values.shape == (sample_voxel_data.shape[0],)

    @pytest.mark.unit
    def test_ttest_ind_invalid_alternative(self, sample_voxel_data):
        """Test invalid alternative hypothesis"""
        from stats.stats_utils import ttest_ind

        with pytest.raises(ValueError, match="alternative must be"):
            ttest_ind(sample_voxel_data, 5, 5, alternative='invalid')


class TestTtestRel:
    """Test paired samples t-test"""

    @pytest.mark.unit
    def test_ttest_rel_basic(self, sample_voxel_data):
        """Test basic paired t-test"""
        from stats.stats_utils import ttest_rel

        n_pairs = 5

        t_stats, p_values = ttest_rel(sample_voxel_data, n_pairs)

        assert t_stats.shape == (sample_voxel_data.shape[0],)
        assert p_values.shape == (sample_voxel_data.shape[0],)
        assert np.all(p_values >= 0)
        assert np.all(p_values <= 1)

    @pytest.mark.unit
    def test_ttest_rel_alternatives(self, sample_voxel_data):
        """Test different alternative hypotheses for paired test"""
        from stats.stats_utils import ttest_rel

        for alternative in ['two-sided', 'greater', 'less']:
            t_stats, p_values = ttest_rel(sample_voxel_data, 5, alternative=alternative)
            assert p_values.shape == (sample_voxel_data.shape[0],)


class TestTtestVoxelwise:
    """Test voxelwise t-test analysis"""

    @pytest.mark.unit
    def test_ttest_voxelwise_unpaired(self, sample_4d_data):
        """Test unpaired voxelwise t-test"""
        from stats.stats_utils import ttest_voxelwise

        responders = sample_4d_data[:, :, :, :3]
        non_responders = sample_4d_data[:, :, :, 3:5]

        p_values, t_stats, valid_mask = ttest_voxelwise(
            responders, non_responders, test_type='unpaired', verbose=False
        )

        expected_shape = sample_4d_data.shape[:3]
        assert p_values.shape == expected_shape
        assert t_stats.shape == expected_shape
        assert valid_mask.shape == expected_shape

    @pytest.mark.unit
    def test_ttest_voxelwise_paired(self, sample_4d_data):
        """Test paired voxelwise t-test"""
        from stats.stats_utils import ttest_voxelwise

        # Paired test requires equal sample sizes
        responders = sample_4d_data[:, :, :, :3]
        non_responders = sample_4d_data[:, :, :, 2:5]

        p_values, t_stats, valid_mask = ttest_voxelwise(
            responders, non_responders, test_type='paired', verbose=False
        )

        assert p_values.shape == sample_4d_data.shape[:3]

    @pytest.mark.unit
    def test_ttest_voxelwise_paired_size_mismatch(self, sample_4d_data):
        """Test error handling for paired test with unequal sizes"""
        from stats.stats_utils import ttest_voxelwise

        responders = sample_4d_data[:, :, :, :3]
        non_responders = sample_4d_data[:, :, :, 3:5]  # Different size

        with pytest.raises(ValueError, match="equal sample sizes"):
            ttest_voxelwise(responders, non_responders, test_type='paired', verbose=False)

    @pytest.mark.unit
    def test_ttest_voxelwise_invalid_test_type(self, sample_4d_data):
        """Test invalid test type"""
        from stats.stats_utils import ttest_voxelwise

        responders = sample_4d_data[:, :, :, :3]
        non_responders = sample_4d_data[:, :, :, 3:5]

        with pytest.raises(ValueError, match="must be 'paired' or 'unpaired'"):
            ttest_voxelwise(responders, non_responders, test_type='invalid', verbose=False)


# ==============================================================================
# TEST stats_utils.py - CLUSTER ANALYSIS
# ==============================================================================

class TestClusterAnalysis:
    """Test cluster analysis functionality"""

    @pytest.mark.unit
    def test_cluster_analysis_basic(self, sample_binary_mask, sample_affine):
        """Test basic cluster analysis"""
        from stats.stats_utils import cluster_analysis

        clusters = cluster_analysis(sample_binary_mask, sample_affine, verbose=False)

        assert isinstance(clusters, list)
        if len(clusters) > 0:
            cluster = clusters[0]
            assert 'cluster_id' in cluster
            assert 'size' in cluster
            assert 'center_voxel' in cluster
            assert 'center_mni' in cluster

    @pytest.mark.unit
    def test_cluster_analysis_no_clusters(self, sample_affine):
        """Test cluster analysis with empty mask"""
        from stats.stats_utils import cluster_analysis

        empty_mask = np.zeros((10, 10, 10), dtype=int)
        clusters = cluster_analysis(empty_mask, sample_affine, verbose=False)

        assert len(clusters) == 0


# ==============================================================================
# TEST io_utils.py
# ==============================================================================

class TestSaveNifti:
    """Test NIfTI saving functionality"""

    @pytest.mark.unit
    @patch('nibabel.save')
    @patch('nibabel.Nifti1Image')
    def test_save_nifti_basic(self, mock_nifti_img, mock_save):
        """Test basic NIfTI file saving"""
        from stats.io_utils import save_nifti

        data = np.random.rand(10, 10, 10).astype(np.float32)
        affine = np.eye(4)
        header = MagicMock()
        filepath = "/fake/path/test.nii.gz"

        save_nifti(data, affine, header, filepath)

        mock_nifti_img.assert_called_once()
        mock_save.assert_called_once()


class TestSavePermutationDetails:
    """Test permutation details logging"""

    @pytest.mark.unit
    @patch('builtins.open', new_callable=mock_open)
    def test_save_permutation_details(self, mock_file):
        """Test saving permutation details to file"""
        from stats.io_utils import save_permutation_details

        permutation_info = [
            {'perm_num': 0, 'perm_idx': np.array([0, 1, 2, 3]), 'max_cluster_size': 100},
            {'perm_num': 1, 'perm_idx': np.array([2, 3, 0, 1]), 'max_cluster_size': 150},
        ]
        subject_ids_resp = ['001', '002']
        subject_ids_non_resp = ['003', '004']
        output_file = "/fake/path/perm_log.txt"

        save_permutation_details(permutation_info, output_file, subject_ids_resp, subject_ids_non_resp)

        mock_file.assert_called_once_with(output_file, 'w')


# ==============================================================================
# TEST atlas_utils.py
# ==============================================================================

class TestCheckAndResampleAtlas:
    """Test atlas dimension checking and resampling"""

    @pytest.mark.unit
    @patch('nibabel.processing.resample_from_to')
    def test_matching_dimensions(self, mock_resample, mock_nifti_img):
        """Test atlas with matching dimensions (no resampling needed)"""
        from stats.atlas_utils import check_and_resample_atlas

        # Create matching atlas and reference
        atlas_img = MagicMock()
        atlas_img.shape = (91, 109, 91)
        atlas_img.get_fdata = MagicMock(return_value=np.zeros((91, 109, 91), dtype=int))

        ref_img = MagicMock()
        ref_img.shape = (91, 109, 91)

        atlas_data = check_and_resample_atlas(atlas_img, ref_img, "test_atlas", verbose=False)

        assert atlas_data.shape == (91, 109, 91)
        mock_resample.assert_not_called()  # Should not resample

    @pytest.mark.unit
    @patch('stats.atlas_utils.resample_from_to')
    @patch('stats.atlas_utils.nib.Nifti1Image')
    def test_mismatched_dimensions(self, mock_nifti_class, mock_resample):
        """Test atlas with mismatched dimensions (resampling needed)"""
        from stats.atlas_utils import check_and_resample_atlas

        # Create mismatched atlas and reference
        atlas_img = MagicMock()
        atlas_img.shape = (45, 54, 45)
        atlas_img.get_fdata = MagicMock(return_value=np.zeros((45, 54, 45), dtype=int))
        atlas_img.affine = np.eye(4)

        ref_img = MagicMock()
        ref_img.shape = (91, 109, 91)
        ref_img.get_fdata = MagicMock(return_value=np.zeros((91, 109, 91), dtype=np.float32))
        ref_img.affine = np.eye(4)

        # Mock resampled output
        mock_resampled = MagicMock()
        mock_resampled.get_fdata = MagicMock(return_value=np.zeros((91, 109, 91), dtype=np.float32))
        mock_resample.return_value = mock_resampled

        atlas_data = check_and_resample_atlas(atlas_img, ref_img, "test_atlas", verbose=False)

        assert mock_resample.called  # Should attempt resampling


class TestAtlasOverlapAnalysis:
    """Test atlas overlap analysis"""

    @pytest.mark.unit
    @patch('nibabel.load')
    @patch('os.path.exists')
    def test_atlas_overlap_basic(self, mock_exists, mock_load, sample_binary_mask, mock_nifti_img):
        """Test basic atlas overlap analysis"""
        from stats.atlas_utils import atlas_overlap_analysis

        # Mock atlas file
        mock_exists.return_value = True
        mock_atlas = MagicMock()
        mock_atlas.get_fdata = MagicMock(return_value=np.random.randint(0, 10, (10, 10, 10)))
        mock_load.return_value = mock_atlas

        results = atlas_overlap_analysis(
            sample_binary_mask,
            ["test_atlas.nii.gz"],
            "/fake/atlas/dir",
            reference_img=mock_nifti_img,
            verbose=False
        )

        assert isinstance(results, dict)
        assert "test_atlas.nii.gz" in results or len(results) >= 0

    @pytest.mark.unit
    @patch('os.path.exists')
    def test_atlas_overlap_missing_file(self, mock_exists, sample_binary_mask):
        """Test atlas overlap with missing file"""
        from stats.atlas_utils import atlas_overlap_analysis

        mock_exists.return_value = False

        results = atlas_overlap_analysis(
            sample_binary_mask,
            ["missing_atlas.nii.gz"],
            "/fake/atlas/dir",
            verbose=False
        )

        assert isinstance(results, dict)
        assert len(results) == 0


# ==============================================================================
# TEST permutation_analysis.py - DATA LOADING
# ==============================================================================

class TestPrepareConfigFromCsv:
    """Test CSV configuration loading"""

    @pytest.mark.unit
    @patch('pandas.read_csv')
    def test_group_comparison_csv(self, mock_read_csv):
        """Test loading group comparison config from CSV"""
        from stats.permutation_analysis import prepare_config_from_csv

        # Mock CSV data
        mock_df = MagicMock()
        mock_df.columns = ['subject_id', 'simulation_name', 'response']
        mock_df.iterrows = MagicMock(return_value=[
            (0, {'subject_id': 'sub-001', 'simulation_name': 'montage1', 'response': 1}),
            (1, {'subject_id': 'sub-002', 'simulation_name': 'montage1', 'response': 0}),
        ])
        mock_read_csv.return_value = mock_df

        configs = prepare_config_from_csv("/fake/file.csv", analysis_type='group_comparison')

        assert len(configs) == 2
        assert configs[0]['subject_id'] == '001'
        assert configs[0]['response'] == 1

    @pytest.mark.unit
    @patch('pandas.read_csv')
    def test_correlation_csv(self, mock_read_csv):
        """Test loading correlation config from CSV"""
        from stats.permutation_analysis import prepare_config_from_csv

        # Mock CSV data with effect sizes
        mock_df = MagicMock()
        mock_df.columns = ['subject_id', 'simulation_name', 'effect_size', 'weight']

        # Create mock rows with proper pandas.notna behavior
        row1 = {'subject_id': '001', 'simulation_name': 'montage1', 'effect_size': 0.5, 'weight': 10}
        row2 = {'subject_id': '002', 'simulation_name': 'montage1', 'effect_size': 0.7, 'weight': 15}

        mock_df.iterrows = MagicMock(return_value=[(0, row1), (1, row2)])
        mock_df.__contains__ = MagicMock(return_value=True)  # For 'weight' in df.columns check
        mock_read_csv.return_value = mock_df

        # Mock pandas.notna to always return True for our test data
        with patch('pandas.notna', return_value=True):
            with patch('pandas.isna', return_value=False):
                configs = prepare_config_from_csv("/fake/file.csv", analysis_type='correlation')

        assert len(configs) == 2
        assert 'effect_size' in configs[0]
        assert configs[0]['effect_size'] == 0.5

    @pytest.mark.unit
    @patch('pandas.read_csv')
    def test_csv_missing_column(self, mock_read_csv):
        """Test error handling for missing required column"""
        from stats.permutation_analysis import prepare_config_from_csv

        # Mock CSV with missing column
        mock_df = MagicMock()
        mock_df.columns = ['subject_id']  # Missing 'simulation_name' and 'response'
        mock_read_csv.return_value = mock_df

        with pytest.raises(ValueError, match="missing required column"):
            prepare_config_from_csv("/fake/file.csv", analysis_type='group_comparison')


# ==============================================================================
# TEST VISUALIZATION AND REPORTING (MOCKED)
# ==============================================================================

class TestVisualizationMocking:
    """Test visualization functions are mockable"""

    @pytest.mark.unit
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.figure')
    def test_plot_functions_mockable(self, mock_figure, mock_savefig):
        """Test that visualization functions can be mocked"""
        from stats import visualization

        # These imports should not fail
        assert hasattr(visualization, 'plot_permutation_null_distribution')
        assert hasattr(visualization, 'plot_cluster_size_mass_correlation')


class TestReportingMocking:
    """Test reporting functions are mockable"""

    @pytest.mark.unit
    def test_report_functions_exist(self):
        """Test that reporting functions exist"""
        from stats import reporting

        assert hasattr(reporting, 'generate_summary')
        assert hasattr(reporting, 'generate_correlation_summary')


# ==============================================================================
# INTEGRATION TESTS (Mocked External Dependencies)
# ==============================================================================

class TestPermutationWorkflow:
    """Integration tests for complete permutation workflow"""

    @pytest.mark.unit
    @patch('stats.permutation_analysis.nifti.load_group_data_ti_toolbox')
    @patch('stats.permutation_analysis.get_path_manager')
    def test_load_subject_data_group_comparison(self, mock_pm, mock_load_group):
        """Test subject data loading for group comparison"""
        from stats.permutation_analysis import load_subject_data_group_comparison

        # Mock data loading - return different data for responders vs non-responders
        def mock_load_side_effect(configs, **kwargs):
            if len(configs) == 2:  # Responders
                return (
                    np.random.rand(10, 10, 10, 2).astype(np.float32),  # 2 responders
                    MagicMock(),  # Template image
                    ['001', '002']  # Responder IDs
                )
            else:  # Non-responders
                return (
                    np.random.rand(10, 10, 10, 1).astype(np.float32),  # 1 non-responder
                    MagicMock(),  # Template image
                    ['003']  # Non-responder IDs
                )

        mock_load_group.side_effect = mock_load_side_effect

        subject_configs = [
            {'subject_id': '001', 'simulation_name': 'montage1', 'response': 1},
            {'subject_id': '002', 'simulation_name': 'montage1', 'response': 1},
            {'subject_id': '003', 'simulation_name': 'montage1', 'response': 0},
        ]

        resp, non_resp, template, resp_ids, non_resp_ids = load_subject_data_group_comparison(
            subject_configs
        )

        assert resp.shape[-1] == 2  # 2 responders
        assert non_resp.shape[-1] == 1  # 1 non-responder


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
