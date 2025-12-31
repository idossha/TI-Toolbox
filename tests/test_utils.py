#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox utility module (core/utils.py)

Tests utility functions for mesh analysis and ROI calculations.
These functions are used extensively in analyzer modules.
"""

import pytest
import numpy as np
import sys
import os
from unittest.mock import Mock, MagicMock

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'tit')
sys.path.insert(0, ti_toolbox_dir)

from core.utils import (
    find_sphere_element_indices,
    find_grey_matter_indices,
    calculate_roi_metrics
)


class TestFindSphereElementIndices:
    """Test find_sphere_element_indices function"""

    @pytest.fixture
    def mock_mesh(self):
        """Create a mock SimNIBS mesh object"""
        mesh = Mock()

        # Create a simple grid of element centers
        # 5x5x5 grid centered at origin
        x = np.linspace(-10, 10, 5)
        y = np.linspace(-10, 10, 5)
        z = np.linspace(-10, 10, 5)
        xx, yy, zz = np.meshgrid(x, y, z)
        element_centers = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

        mesh.elements_baricenters.return_value = element_centers

        # Mock element volumes (125 elements, all volume 1.0)
        mesh.elements_volumes_and_areas.return_value = np.ones(125)

        return mesh

    def test_sphere_at_origin(self, mock_mesh):
        """Test finding elements within sphere centered at origin"""
        roi_coords = [0, 0, 0]
        radius = 5.0

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # Should find elements within 5mm of origin
        assert len(roi_indices) > 0
        assert len(element_volumes) == len(roi_indices)

        # Verify that found elements are actually within radius
        element_centers = mock_mesh.elements_baricenters()
        for idx in roi_indices:
            center = element_centers[idx]
            distance = np.sqrt(np.sum((center - roi_coords)**2))
            assert distance <= radius + 1e-6  # Small tolerance for floating point

    def test_sphere_offset_position(self, mock_mesh):
        """Test finding elements in sphere at offset position"""
        roi_coords = [5, 5, 5]
        radius = 3.0

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        assert len(roi_indices) > 0
        assert len(element_volumes) == len(roi_indices)

    def test_sphere_small_radius(self, mock_mesh):
        """Test with very small radius"""
        roi_coords = [0, 0, 0]
        radius = 0.5

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # With small radius, might find 0 or 1 element
        assert len(roi_indices) >= 0
        assert len(element_volumes) == len(roi_indices)

    def test_sphere_large_radius(self, mock_mesh):
        """Test with large radius that includes all elements"""
        roi_coords = [0, 0, 0]
        radius = 50.0  # Larger than grid extent

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # Should find all 125 elements
        assert len(roi_indices) == 125
        assert len(element_volumes) == 125

    def test_sphere_at_edge(self, mock_mesh):
        """Test sphere at edge of mesh"""
        roi_coords = [10, 10, 10]  # At corner of grid
        radius = 3.0

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # Should find at least one element
        assert len(roi_indices) >= 1

    def test_sphere_outside_mesh(self, mock_mesh):
        """Test sphere completely outside mesh"""
        roi_coords = [100, 100, 100]  # Far from grid
        radius = 1.0

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # Should find no elements
        assert len(roi_indices) == 0
        assert len(element_volumes) == 0

    def test_element_volumes_match_indices(self, mock_mesh):
        """Test that element volumes array matches indices"""
        roi_coords = [0, 0, 0]
        radius = 5.0

        roi_indices, element_volumes = find_sphere_element_indices(
            mock_mesh, roi_coords, radius
        )

        # Number of volumes should match number of indices
        assert len(element_volumes) == len(roi_indices)

        # All volumes should be 1.0 (as set in mock)
        assert np.all(element_volumes == 1.0)


class TestFindGreyMatterIndices:
    """Test find_grey_matter_indices function"""

    @pytest.fixture
    def mock_mesh_with_tissues(self):
        """Create mock mesh with tissue tags"""
        mesh = Mock()

        # Create element tags: mix of tissues
        # 0: unknown, 1: white matter, 2: grey matter, 3: CSF, etc.
        element_tags = np.array([1, 2, 2, 3, 1, 2, 1, 2, 2, 0,
                                2, 1, 2, 2, 3, 2, 2, 1, 2, 2])

        mesh.elm = Mock()
        mesh.elm.tag1 = element_tags

        # Mock volumes
        mesh.elements_volumes_and_areas.return_value = np.ones(len(element_tags))

        return mesh

    def test_find_grey_matter_default(self, mock_mesh_with_tissues):
        """Test finding grey matter with default tag [2]"""
        gm_indices, gm_volumes = find_grey_matter_indices(mock_mesh_with_tissues)

        # Count elements with tag 2
        expected_count = np.sum(mock_mesh_with_tissues.elm.tag1 == 2)
        assert len(gm_indices) == expected_count
        assert len(gm_volumes) == expected_count

    def test_find_grey_matter_custom_tags(self, mock_mesh_with_tissues):
        """Test finding elements with custom tissue tags"""
        # Find white matter (tag 1)
        gm_indices, gm_volumes = find_grey_matter_indices(
            mock_mesh_with_tissues,
            grey_matter_tags=[1]
        )

        expected_count = np.sum(mock_mesh_with_tissues.elm.tag1 == 1)
        assert len(gm_indices) == expected_count

    def test_find_grey_matter_multiple_tags(self, mock_mesh_with_tissues):
        """Test finding elements with multiple tissue tags"""
        # Find grey matter (2) and CSF (3)
        gm_indices, gm_volumes = find_grey_matter_indices(
            mock_mesh_with_tissues,
            grey_matter_tags=[2, 3]
        )

        expected_mask = np.isin(mock_mesh_with_tissues.elm.tag1, [2, 3])
        expected_count = np.sum(expected_mask)
        assert len(gm_indices) == expected_count

    def test_find_grey_matter_no_matches(self, mock_mesh_with_tissues):
        """Test with tissue tag that doesn't exist"""
        gm_indices, gm_volumes = find_grey_matter_indices(
            mock_mesh_with_tissues,
            grey_matter_tags=[99]  # Non-existent tag
        )

        assert len(gm_indices) == 0
        assert len(gm_volumes) == 0

    def test_grey_matter_volumes_match(self, mock_mesh_with_tissues):
        """Test that volumes match indices"""
        gm_indices, gm_volumes = find_grey_matter_indices(mock_mesh_with_tissues)

        assert len(gm_volumes) == len(gm_indices)
        assert np.all(gm_volumes == 1.0)  # As set in mock


class TestCalculateROIMetrics:
    """Test calculate_roi_metrics function"""

    def test_basic_roi_metrics(self):
        """Test basic ROI metrics calculation"""
        ti_field_roi = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        element_volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])

        metrics = calculate_roi_metrics(ti_field_roi, element_volumes)

        assert 'TImax_ROI' in metrics
        assert 'TImean_ROI' in metrics
        assert 'n_elements' in metrics

        assert metrics['TImax_ROI'] == 5.0
        assert metrics['TImean_ROI'] == 3.0  # Average of 1,2,3,4,5
        assert metrics['n_elements'] == 5

    def test_roi_metrics_weighted_average(self):
        """Test weighted average calculation"""
        ti_field_roi = np.array([1.0, 2.0, 3.0])
        element_volumes = np.array([1.0, 2.0, 1.0])  # Middle element has 2x volume

        metrics = calculate_roi_metrics(ti_field_roi, element_volumes)

        # Weighted mean: (1*1 + 2*2 + 3*1) / (1 + 2 + 1) = 8/4 = 2.0
        assert metrics['TImean_ROI'] == 2.0

    def test_roi_metrics_with_focality(self):
        """Test ROI metrics with focality calculation"""
        ti_field_roi = np.array([4.0, 5.0, 6.0])
        element_volumes_roi = np.array([1.0, 1.0, 1.0])

        ti_field_gm = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        gm_volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])

        metrics = calculate_roi_metrics(
            ti_field_roi, element_volumes_roi,
            ti_field_gm, gm_volumes
        )

        assert 'Focality' in metrics
        assert 'TImean_GM' in metrics

        # TImean_ROI = 5.0, TImean_GM = 3.0
        assert metrics['TImean_ROI'] == 5.0
        assert metrics['TImean_GM'] == 3.0
        assert metrics['Focality'] == pytest.approx(5.0 / 3.0)

    def test_roi_metrics_empty_roi(self):
        """Test with empty ROI"""
        ti_field_roi = np.array([])
        element_volumes = np.array([])

        metrics = calculate_roi_metrics(ti_field_roi, element_volumes)

        assert metrics['TImax_ROI'] == 0.0
        assert metrics['TImean_ROI'] == 0.0
        assert metrics['n_elements'] == 0
        assert metrics['Focality'] == 0.0

    def test_roi_metrics_single_element(self):
        """Test with single element ROI"""
        ti_field_roi = np.array([3.5])
        element_volumes = np.array([1.0])

        metrics = calculate_roi_metrics(ti_field_roi, element_volumes)

        assert metrics['TImax_ROI'] == 3.5
        assert metrics['TImean_ROI'] == 3.5
        assert metrics['n_elements'] == 1

    def test_focality_zero_gm_mean(self):
        """Test focality when GM mean is zero"""
        ti_field_roi = np.array([1.0, 2.0])
        element_volumes_roi = np.array([1.0, 1.0])

        ti_field_gm = np.array([0.0, 0.0, 0.0])
        gm_volumes = np.array([1.0, 1.0, 1.0])

        metrics = calculate_roi_metrics(
            ti_field_roi, element_volumes_roi,
            ti_field_gm, gm_volumes
        )

        assert metrics['Focality'] == 0.0

    def test_focality_empty_gm(self):
        """Test with empty grey matter data"""
        ti_field_roi = np.array([1.0, 2.0])
        element_volumes_roi = np.array([1.0, 1.0])

        ti_field_gm = np.array([])
        gm_volumes = np.array([])

        metrics = calculate_roi_metrics(
            ti_field_roi, element_volumes_roi,
            ti_field_gm, gm_volumes
        )

        # Focality should not be calculated
        assert 'Focality' not in metrics

    def test_focality_none_inputs(self):
        """Test with None grey matter inputs"""
        ti_field_roi = np.array([1.0, 2.0])
        element_volumes_roi = np.array([1.0, 1.0])

        metrics = calculate_roi_metrics(
            ti_field_roi, element_volumes_roi,
            ti_field_gm=None, gm_volumes=None
        )

        # Focality should not be calculated
        assert 'Focality' not in metrics

    def test_metrics_data_types(self):
        """Test that returned metrics have correct data types"""
        ti_field_roi = np.array([1.0, 2.0, 3.0])
        element_volumes = np.array([1.0, 1.0, 1.0])

        metrics = calculate_roi_metrics(ti_field_roi, element_volumes)

        assert isinstance(metrics['TImax_ROI'], float)
        assert isinstance(metrics['TImean_ROI'], float)
        assert isinstance(metrics['n_elements'], int)

    def test_high_field_values(self):
        """Test with realistic high field values"""
        # Realistic TI field values in V/m
        ti_field_roi = np.array([0.5, 0.8, 1.2, 1.5, 0.9])
        element_volumes = np.array([0.001, 0.001, 0.001, 0.001, 0.001])  # mm^3

        ti_field_gm = np.array([0.1, 0.2, 0.3, 0.4, 0.3, 0.2])
        gm_volumes = np.array([0.001] * 6)

        metrics = calculate_roi_metrics(
            ti_field_roi, element_volumes,
            ti_field_gm, gm_volumes
        )

        assert metrics['TImax_ROI'] == 1.5
        assert metrics['TImean_ROI'] > 0.9
        assert metrics['TImean_GM'] < 0.3
        assert metrics['Focality'] > 1.0  # ROI should be more focal than GM


class TestIntegration:
    """Test integration between utility functions"""

    @pytest.fixture
    def mock_mesh_full(self):
        """Create comprehensive mock mesh"""
        mesh = Mock()

        # Create element centers in a grid
        x = np.linspace(-10, 10, 5)
        y = np.linspace(-10, 10, 5)
        z = np.linspace(-10, 10, 5)
        xx, yy, zz = np.meshgrid(x, y, z)
        element_centers = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

        mesh.elements_baricenters.return_value = element_centers

        # Assign tissue tags (alternate grey and white matter)
        n_elements = len(element_centers)
        element_tags = np.array([2 if i % 2 == 0 else 1 for i in range(n_elements)])
        mesh.elm = Mock()
        mesh.elm.tag1 = element_tags

        # All volumes are 1.0
        mesh.elements_volumes_and_areas.return_value = np.ones(n_elements)

        return mesh

    def test_sphere_and_grey_matter_combined(self, mock_mesh_full):
        """Test finding grey matter within spherical ROI"""
        # Find elements in sphere
        roi_coords = [0, 0, 0]
        radius = 7.0
        sphere_indices, _ = find_sphere_element_indices(
            mock_mesh_full, roi_coords, radius
        )

        # Find grey matter elements
        gm_indices, _ = find_grey_matter_indices(mock_mesh_full)

        # Find intersection (grey matter within sphere)
        gm_in_sphere = np.intersect1d(sphere_indices, gm_indices)

        assert len(gm_in_sphere) > 0
        assert len(gm_in_sphere) <= len(sphere_indices)
        assert len(gm_in_sphere) <= len(gm_indices)

    def test_complete_roi_analysis_pipeline(self, mock_mesh_full):
        """Test complete pipeline: sphere -> grey matter -> metrics"""
        # Step 1: Find ROI elements
        roi_coords = [0, 0, 0]
        radius = 5.0
        roi_indices, roi_volumes = find_sphere_element_indices(
            mock_mesh_full, roi_coords, radius
        )

        # Step 2: Find grey matter elements
        gm_indices, gm_volumes = find_grey_matter_indices(mock_mesh_full)

        # Step 3: Create mock field data
        n_elements = len(mock_mesh_full.elements_baricenters())
        ti_field = np.random.rand(n_elements) * 2.0  # Random field 0-2 V/m

        # Extract ROI and GM field values
        ti_field_roi = ti_field[roi_indices]
        ti_field_gm = ti_field[gm_indices]

        # Step 4: Calculate metrics
        metrics = calculate_roi_metrics(
            ti_field_roi, roi_volumes,
            ti_field_gm, gm_volumes
        )

        # Verify complete metrics
        assert 'TImax_ROI' in metrics
        assert 'TImean_ROI' in metrics
        assert 'n_elements' in metrics
        assert 'Focality' in metrics
        assert 'TImean_GM' in metrics

        # Sanity checks
        assert metrics['TImax_ROI'] >= 0
        assert metrics['TImax_ROI'] <= 2.0
        assert metrics['n_elements'] == len(roi_indices)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
