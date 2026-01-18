#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox calculation utilities (core/calc.py)
"""

import pytest
import numpy as np
import sys
import os

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from core.calc import (
    get_TI_vectors,
    get_mTI_vectors,
)


class TestGetTIVectors:
    """Test get_TI_vectors function"""

    def test_parallel_equal_magnitude_vectors(self):
        """Test TI vectors for parallel equal magnitude E-fields"""
        # Two parallel vectors of equal magnitude
        E1 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

        TI_vectors = get_TI_vectors(E1, E2)

        # For equal parallel vectors, TI envelope should be 2*E
        expected = 2 * E2
        np.testing.assert_array_almost_equal(TI_vectors, expected)

    def test_perpendicular_equal_magnitude_vectors(self):
        """Test TI vectors for perpendicular equal magnitude E-fields"""
        # Two perpendicular vectors of equal magnitude
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.0, 1.0, 0.0]])

        TI_vectors = get_TI_vectors(E1, E2)

        # Check that result has correct shape
        assert TI_vectors.shape == (1, 3)
        # For perpendicular equal vectors, the cross product formula gives sqrt(2) * |E|
        magnitude = np.linalg.norm(TI_vectors[0])
        expected_magnitude = np.sqrt(2)  # sqrt(2) for perpendicular equal magnitude
        assert abs(magnitude - expected_magnitude) < 0.01

    def test_antiparallel_vectors(self):
        """Test TI vectors for antiparallel E-fields"""
        # Two antiparallel vectors (should be flipped to < 90 degrees)
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[-0.5, 0.0, 0.0]])

        TI_vectors = get_TI_vectors(E1, E2)

        # Should produce valid result (no NaNs)
        assert not np.any(np.isnan(TI_vectors))

    def test_different_magnitude_vectors(self):
        """Test TI vectors for different magnitude E-fields"""
        E1 = np.array([[2.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0]])

        TI_vectors = get_TI_vectors(E1, E2)

        # Should produce valid result
        assert TI_vectors.shape == (1, 3)
        assert not np.any(np.isnan(TI_vectors))

    def test_multiple_points(self):
        """Test TI vectors for multiple spatial points"""
        n_points = 100
        E1 = np.random.rand(n_points, 3)
        E2 = np.random.rand(n_points, 3)

        TI_vectors = get_TI_vectors(E1, E2)

        assert TI_vectors.shape == (n_points, 3)
        assert not np.any(np.isnan(TI_vectors))

    def test_zero_vectors(self):
        """Test TI vectors when one field is zero"""
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.0, 0.0, 0.0]])

        TI_vectors = get_TI_vectors(E1, E2)

        # Should produce zero TI vector
        expected = np.array([[0.0, 0.0, 0.0]])
        np.testing.assert_array_almost_equal(TI_vectors, expected)

    def test_input_not_modified(self):
        """Test that input arrays are not modified"""
        E1_orig = np.array([[1.0, 0.5, 0.3]])
        E2_orig = np.array([[0.8, 0.2, 0.1]])

        E1 = E1_orig.copy()
        E2 = E2_orig.copy()

        get_TI_vectors(E1, E2)

        # Original arrays should not be modified
        np.testing.assert_array_equal(E1, E1_orig)
        np.testing.assert_array_equal(E2, E2_orig)


class TestGetMTIVectors:
    """Test get_mTI_vectors function"""

    def test_basic_mti_calculation(self):
        """Test basic mTI vectors calculation with four channels"""
        # Create simple parallel fields for all four channels
        E1 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        E3 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        E4 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

        mTI_vectors = get_mTI_vectors(E1, E2, E3, E4)

        # Should produce valid result
        assert mTI_vectors.shape == (2, 3)
        assert not np.any(np.isnan(mTI_vectors))
        assert not np.any(np.isinf(mTI_vectors))

    def test_mti_different_channel_pairs(self):
        """Test mTI with different field patterns for channel pairs"""
        # Channel pair 1: fields in x direction
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.8, 0.0, 0.0]])

        # Channel pair 2: fields in y direction
        E3 = np.array([[0.0, 1.0, 0.0]])
        E4 = np.array([[0.0, 0.8, 0.0]])

        mTI_vectors = get_mTI_vectors(E1, E2, E3, E4)

        assert mTI_vectors.shape == (1, 3)
        assert not np.any(np.isnan(mTI_vectors))

    def test_mti_multiple_points(self):
        """Test mTI calculation for multiple spatial points"""
        n_points = 50
        E1 = np.random.rand(n_points, 3) * 2.0
        E2 = np.random.rand(n_points, 3) * 2.0
        E3 = np.random.rand(n_points, 3) * 2.0
        E4 = np.random.rand(n_points, 3) * 2.0

        mTI_vectors = get_mTI_vectors(E1, E2, E3, E4)

        assert mTI_vectors.shape == (n_points, 3)
        assert not np.any(np.isnan(mTI_vectors))

    def test_mti_with_zero_channels(self):
        """Test mTI when some channels are zero"""
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.5, 0.0, 0.0]])
        E3 = np.array([[0.0, 0.0, 0.0]])  # Zero field
        E4 = np.array([[0.0, 0.0, 0.0]])  # Zero field

        mTI_vectors = get_mTI_vectors(E1, E2, E3, E4)

        # Should handle zero fields gracefully
        assert mTI_vectors.shape == (1, 3)
        assert not np.any(np.isnan(mTI_vectors))

    def test_mti_shape_validation(self):
        """Test that mTI validates input shapes"""
        # Mismatched shapes should raise ValueError
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0], [0.5, 0.0, 0.0]])  # Different shape
        E3 = np.array([[1.0, 0.0, 0.0]])
        E4 = np.array([[1.0, 0.0, 0.0]])

        with pytest.raises(ValueError, match="identical shapes"):
            get_mTI_vectors(E1, E2, E3, E4)

    def test_mti_dimension_validation(self):
        """Test that mTI validates 3D vector requirement"""
        # 2D vectors should raise ValueError
        E1 = np.array([[1.0, 0.0]])  # Only 2D
        E2 = np.array([[1.0, 0.0]])
        E3 = np.array([[1.0, 0.0]])
        E4 = np.array([[1.0, 0.0]])

        with pytest.raises(ValueError, match="must have shape \\(N, 3\\)"):
            get_mTI_vectors(E1, E2, E3, E4)

    def test_mti_realistic_fields(self):
        """Test with realistic electric field values"""
        # Realistic E-fields in V/m from simulation
        n = 10
        E1 = np.random.rand(n, 3) * 0.5 + 0.1  # 0.1-0.6 V/m
        E2 = np.random.rand(n, 3) * 0.4 + 0.1  # 0.1-0.5 V/m
        E3 = np.random.rand(n, 3) * 0.5 + 0.1
        E4 = np.random.rand(n, 3) * 0.4 + 0.1

        mTI_vectors = get_mTI_vectors(E1, E2, E3, E4)

        # mTI magnitude should be reasonable (typically < 2x max input)
        mti_magnitudes = np.linalg.norm(mTI_vectors, axis=1)
        max_input_mag = np.max(
            [
                np.linalg.norm(E1, axis=1).max(),
                np.linalg.norm(E2, axis=1).max(),
                np.linalg.norm(E3, axis=1).max(),
                np.linalg.norm(E4, axis=1).max(),
            ]
        )

        # mTI should be bounded
        assert np.all(mti_magnitudes < 4 * max_input_mag)
        assert np.all(mti_magnitudes >= 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
