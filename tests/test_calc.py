#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox calculation utilities (core/calc.py)
"""

import pytest
import numpy as np
import sys
import os

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'tit')
sys.path.insert(0, ti_toolbox_dir)

from core.calc import (
    get_TI_vectors,
    get_mTI_vectors,
    calculate_ti_field_from_leadfield,
    create_stim_patterns
)


class TestGetTIVectors:
    """Test get_TI_vectors function"""

    def test_parallel_equal_magnitude_vectors(self):
        """Test TI vectors for parallel equal magnitude E-fields"""
        # Two parallel vectors of equal magnitude
        E1 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])

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
        E1 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])
        E3 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])
        E4 = np.array([[1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0]])

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
        max_input_mag = np.max([
            np.linalg.norm(E1, axis=1).max(),
            np.linalg.norm(E2, axis=1).max(),
            np.linalg.norm(E3, axis=1).max(),
            np.linalg.norm(E4, axis=1).max()
        ])

        # mTI should be bounded
        assert np.all(mti_magnitudes < 4 * max_input_mag)
        assert np.all(mti_magnitudes >= 0)


class TestCalculateTIFieldFromLeadfield:
    """Test calculate_ti_field_from_leadfield function"""

    def test_basic_leadfield_calculation(self):
        """Test basic TI field calculation from leadfield"""
        # Simple leadfield: 2 electrodes, 3 elements, 3D vectors
        n_electrodes = 2
        n_elements = 3

        leadfield = np.random.rand(n_electrodes, n_elements, 3) * 100  # mV/mm
        stim1 = np.array([1.0, -1.0])  # mA
        stim2 = np.array([0.5, -0.5])  # mA

        ti_field = calculate_ti_field_from_leadfield(leadfield, stim1, stim2)

        assert ti_field.shape == (n_elements,)
        assert np.all(ti_field >= 0)  # TI field should be non-negative
        assert not np.any(np.isnan(ti_field))

    def test_leadfield_with_target_indices(self):
        """Test leadfield calculation with subset of elements"""
        n_electrodes = 4
        n_elements = 100

        leadfield = np.random.rand(n_electrodes, n_elements, 3) * 100
        stim1 = np.array([1.0, -1.0, 0.0, 0.0])
        stim2 = np.array([0.0, 0.0, 1.0, -1.0])

        # Calculate for subset of elements
        target_indices = np.array([10, 20, 30, 40, 50])
        ti_field = calculate_ti_field_from_leadfield(
            leadfield, stim1, stim2, target_indices=target_indices
        )

        assert ti_field.shape == (len(target_indices),)
        assert not np.any(np.isnan(ti_field))

    def test_leadfield_unit_conversion(self):
        """Test that leadfield is correctly converted from mV/mm to V/m"""
        # Simple case where we can verify unit conversion
        n_electrodes = 2
        n_elements = 1

        # Create leadfield that produces known E-field
        leadfield = np.array([[[1000.0, 0.0, 0.0]],   # 1000 mV/mm = 1 V/m
                               [[0.0, 0.0, 0.0]]])
        stim1 = np.array([1.0, 0.0])  # 1 mA on electrode 1
        stim2 = np.array([1.0, 0.0])  # Same for stim2

        ti_field = calculate_ti_field_from_leadfield(leadfield, stim1, stim2)

        # Both fields are [1, 0, 0] V/m, so envelope should be 2.0 V/m
        expected = 2.0
        np.testing.assert_almost_equal(ti_field[0], expected, decimal=5)

    def test_bipolar_stimulation_pattern(self):
        """Test with bipolar stimulation pattern"""
        n_electrodes = 4
        n_elements = 10

        leadfield = np.random.rand(n_electrodes, n_elements, 3) * 50
        # Bipolar: +1mA on electrodes 0,2 and -1mA on electrodes 1,3
        stim1 = np.array([1.0, -1.0, 0.0, 0.0])
        stim2 = np.array([0.0, 0.0, 1.0, -1.0])

        ti_field = calculate_ti_field_from_leadfield(leadfield, stim1, stim2)

        assert ti_field.shape == (n_elements,)
        assert not np.any(np.isnan(ti_field))

    def test_zero_stimulation(self):
        """Test with zero stimulation"""
        n_electrodes = 4
        n_elements = 5

        leadfield = np.random.rand(n_electrodes, n_elements, 3) * 100
        stim1 = np.zeros(n_electrodes)
        stim2 = np.zeros(n_electrodes)

        ti_field = calculate_ti_field_from_leadfield(leadfield, stim1, stim2)

        # Should produce zero TI field
        np.testing.assert_array_almost_equal(ti_field, np.zeros(n_elements))


class TestCreateStimPatterns:
    """Test create_stim_patterns function"""

    def test_simple_bipolar_pattern(self):
        """Test creating simple bipolar stimulation pattern"""
        electrode_names = ['E1', 'E2', 'E3', 'E4']
        e1_plus = ['E1']
        e1_minus = ['E2']
        e2_plus = ['E3']
        e2_minus = ['E4']
        intensity = 0.001  # 1 mA

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus, intensity
        )

        # Check stim1
        assert stim1[0] == 1.0  # E1: +1 mA
        assert stim1[1] == -1.0  # E2: -1 mA
        assert stim1[2] == 0.0  # E3: 0 mA
        assert stim1[3] == 0.0  # E4: 0 mA

        # Check stim2
        assert stim2[0] == 0.0  # E1: 0 mA
        assert stim2[1] == 0.0  # E2: 0 mA
        assert stim2[2] == 1.0  # E3: +1 mA
        assert stim2[3] == -1.0  # E4: -1 mA

    def test_multiple_electrodes_per_pair(self):
        """Test with multiple electrodes per stimulation pair"""
        electrode_names = ['E1', 'E2', 'E3', 'E4', 'E5', 'E6']
        e1_plus = ['E1', 'E2']  # 2 positive electrodes
        e1_minus = ['E3', 'E4']  # 2 negative electrodes
        e2_plus = ['E5']
        e2_minus = ['E6']
        intensity = 0.002  # 2 mA

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus, intensity
        )

        # Each positive electrode gets intensity/2 = 1 mA
        assert stim1[0] == 1.0  # E1
        assert stim1[1] == 1.0  # E2
        # Each negative electrode gets -intensity/2 = -1 mA
        assert stim1[2] == -1.0  # E3
        assert stim1[3] == -1.0  # E4

        # Check current balance for stim1
        assert abs(np.sum(stim1)) < 1e-10  # Should sum to zero

    def test_different_intensity(self):
        """Test with different stimulation intensity"""
        electrode_names = ['E1', 'E2', 'E3', 'E4']
        e1_plus = ['E1']
        e1_minus = ['E2']
        e2_plus = ['E3']
        e2_minus = ['E4']
        intensity = 0.0015  # 1.5 mA

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus, intensity
        )

        assert stim1[0] == 1.5
        assert stim1[1] == -1.5

    def test_nonexistent_electrode_names(self):
        """Test with electrode names not in the list"""
        electrode_names = ['E1', 'E2', 'E3', 'E4']
        e1_plus = ['E1', 'E99']  # E99 doesn't exist
        e1_minus = ['E2']
        e2_plus = ['E3']
        e2_minus = ['E4']

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus
        )

        # Should handle gracefully (E99 ignored)
        assert len(stim1) == 4
        # E1 gets full intensity since E99 is ignored
        assert stim1[0] == 0.5  # Split between E1 and E99, but E99 not applied

    def test_current_balance(self):
        """Test that stimulation patterns are current-balanced"""
        electrode_names = ['E1', 'E2', 'E3', 'E4', 'E5']
        e1_plus = ['E1', 'E2']
        e1_minus = ['E3']
        e2_plus = ['E4']
        e2_minus = ['E5']

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus
        )

        # Both patterns should be current-balanced (sum to zero)
        assert abs(np.sum(stim1)) < 1e-10
        assert abs(np.sum(stim2)) < 1e-10

    def test_default_intensity(self):
        """Test with default intensity (1 mA)"""
        electrode_names = ['E1', 'E2', 'E3', 'E4']
        e1_plus = ['E1']
        e1_minus = ['E2']
        e2_plus = ['E3']
        e2_minus = ['E4']

        stim1, stim2 = create_stim_patterns(
            electrode_names, e1_plus, e1_minus, e2_plus, e2_minus
        )

        # Default intensity is 0.001 A = 1 mA
        assert stim1[0] == 1.0
        assert stim1[1] == -1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
