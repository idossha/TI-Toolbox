#!/usr/bin/env simnibs_python
"""
Unit tests for MOVEA optimizer (ti-toolbox/opt/movea/optimizer.py)
"""

import pytest
import numpy as np
import sys
import os
from unittest.mock import MagicMock, patch, Mock

# Add ti-toolbox directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'ti-toolbox')
sys.path.insert(0, ti_toolbox_dir)

from opt.movea.optimizer import TIOptimizer
from opt.ti_calculations import find_target_voxels, validate_ti_montage


class TestTIOptimizer:
    """Test TIOptimizer class"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create synthetic leadfield matrix [n_electrodes, n_voxels, 3]
        self.num_electrodes = 10
        self.num_voxels = 100
        self.lfm = np.random.rand(self.num_electrodes, self.num_voxels, 3) * 0.1

        # Create voxel positions in a 10x10 grid (z=0)
        x = np.linspace(-50, 50, 10)
        y = np.linspace(-50, 50, 10)
        xx, yy = np.meshgrid(x, y)
        self.positions = np.column_stack([xx.ravel(), yy.ravel(), np.zeros(100)])

        self.optimizer = TIOptimizer(
            self.lfm,
            self.positions,
            num_electrodes=self.num_electrodes
        )

    def test_initialization(self):
        """Test optimizer initialization"""
        assert self.optimizer.lfm.shape == (self.num_electrodes, self.num_voxels, 3)
        assert self.optimizer.positions.shape == (self.num_voxels, 3)
        assert self.optimizer.num_electrodes == self.num_electrodes
        assert self.optimizer.target_indices is None
        assert self.optimizer._eval_count == 0

    def test_set_target_valid(self):
        """Test setting a valid target"""
        target = [0, 0, 0]
        radius = 10.0

        self.optimizer.set_target(target, radius)

        assert self.optimizer.target_indices is not None
        assert len(self.optimizer.target_indices) > 0
        assert isinstance(self.optimizer.target_indices, np.ndarray)

    def test_set_target_no_voxels(self):
        """Test setting target with no voxels in range"""
        target = [1000, 1000, 1000]  # Far from any voxels
        radius = 1.0

        with pytest.raises(ValueError, match="No voxels found"):
            self.optimizer.set_target(target, radius)

    def test_evaluate_montage_valid(self):
        """Test evaluating a valid montage"""
        self.optimizer.set_target([0, 0, 0], 10.0)

        electrode_indices = np.array([0, 1, 2, 3])
        current_ratio = 0.5

        cost = self.optimizer.evaluate_montage(
            electrode_indices,
            current_ratio,
            return_dual_objective=False
        )

        assert isinstance(cost, (float, np.floating))
        assert not np.isnan(cost)
        assert not np.isinf(cost)

    def test_evaluate_montage_dual_objective(self):
        """Test evaluating montage with dual objectives"""
        self.optimizer.set_target([0, 0, 0], 10.0)

        electrode_indices = np.array([0, 1, 2, 3])
        objectives = self.optimizer.evaluate_montage(
            electrode_indices,
            0.5,
            return_dual_objective=True
        )

        assert isinstance(objectives, np.ndarray)
        assert len(objectives) == 2
        assert not np.any(np.isnan(objectives))

    def test_evaluate_montage_invalid_electrodes(self):
        """Test evaluating with invalid electrode indices"""
        self.optimizer.set_target([0, 0, 0], 10.0)

        # Out of range electrode
        electrode_indices = np.array([0, 1, 2, 100])

        cost = self.optimizer.evaluate_montage(electrode_indices, 0)

        # Should return infinity for invalid montage
        assert np.isinf(cost)

    def test_evaluate_montage_duplicate_electrodes(self):
        """Test evaluating with duplicate electrodes"""
        self.optimizer.set_target([0, 0, 0], 10.0)

        # Duplicate electrodes
        electrode_indices = np.array([0, 0, 1, 2])

        cost = self.optimizer.evaluate_montage(electrode_indices, 0)

        # Should return infinity for invalid montage
        assert np.isinf(cost)

    def test_log_with_callback(self):
        """Test logging with progress callback"""
        messages = []
        def callback(msg, msg_type):
            messages.append((msg, msg_type))

        optimizer = TIOptimizer(self.lfm, self.positions, progress_callback=callback)
        optimizer._log("Test message", "info")

        assert len(messages) == 1
        assert messages[0] == ("Test message", "info")

    def test_log_without_callback(self, capsys):
        """Test logging without callback (falls back to print)"""
        self.optimizer._log("Test message", "warning")

        captured = capsys.readouterr()
        assert "Test message" in captured.out


class TestFindTargetVoxels:
    """Test find_target_voxels utility function"""

    def test_find_voxels_in_sphere(self):
        """Test finding voxels within sphere"""
        # Create grid of voxels
        positions = np.array([
            [0, 0, 0],
            [5, 0, 0],
            [10, 0, 0],
            [0, 5, 0],
            [0, 0, 5]
        ])

        center = [0, 0, 0]
        radius = 6.0

        indices = find_target_voxels(positions, center, radius)

        # Should find voxels at (0,0,0), (5,0,0), (0,5,0), (0,0,5)
        assert len(indices) == 4
        assert 0 in indices  # Center voxel
        assert 1 in indices  # (5,0,0)
        assert 3 in indices  # (0,5,0)
        assert 4 in indices  # (0,0,5)

    def test_find_voxels_no_match(self):
        """Test when no voxels are within radius"""
        positions = np.array([[10, 10, 10]])
        center = [0, 0, 0]
        radius = 1.0

        indices = find_target_voxels(positions, center, radius)

        assert len(indices) == 0

    def test_find_voxels_all_match(self):
        """Test when all voxels are within radius"""
        positions = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0]
        ])
        center = [0, 0, 0]
        radius = 10.0

        indices = find_target_voxels(positions, center, radius)

        assert len(indices) == 3


class TestValidateTIMontage:
    """Test validate_ti_montage utility function"""

    def test_valid_montage(self):
        """Test validation of valid montage"""
        electrodes = [0, 1, 2, 3]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is True

    def test_invalid_too_few_electrodes(self):
        """Test validation with too few electrodes"""
        electrodes = [0, 1, 2]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is False

    def test_invalid_too_many_electrodes(self):
        """Test validation with too many electrodes"""
        electrodes = [0, 1, 2, 3, 4]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is False

    def test_invalid_duplicate_electrodes(self):
        """Test validation with duplicate electrodes"""
        electrodes = [0, 0, 1, 2]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is False

    def test_invalid_out_of_range(self):
        """Test validation with out-of-range electrodes"""
        electrodes = [0, 1, 2, 100]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is False

    def test_invalid_negative_index(self):
        """Test validation with negative electrode index"""
        electrodes = [-1, 0, 1, 2]
        num_electrodes = 10

        assert validate_ti_montage(electrodes, num_electrodes) is False


class TestEvaluateMontageParallel:
    """Test parallel montage evaluation"""

    def test_parallel_evaluation_valid(self):
        """Test parallel evaluation with valid montage"""
        from opt.movea.optimizer import _evaluate_montage_parallel

        # Create mock optimizer
        optimizer = MagicMock()
        optimizer.evaluate_montage.return_value = np.array([0.5, 0.3])

        individual = np.array([0, 1, 2, 3, 0.5])
        args = (optimizer, 0, individual)

        idx, objectives = _evaluate_montage_parallel(args)

        assert idx == 0
        assert len(objectives) == 2
        optimizer.evaluate_montage.assert_called_once()

    def test_parallel_evaluation_exception(self):
        """Test parallel evaluation handles exceptions"""
        from opt.movea.optimizer import _evaluate_montage_parallel

        # Create mock optimizer that raises exception
        optimizer = MagicMock()
        optimizer.evaluate_montage.side_effect = Exception("Test error")

        individual = np.array([0, 1, 2, 3, 0.5])
        args = (optimizer, 0, individual)

        idx, objectives = _evaluate_montage_parallel(args)

        assert idx == 0
        assert np.all(np.isinf(objectives))


class TestOptimizerIntegration:
    """Integration tests for full optimization workflow"""

    def test_optimization_completes(self):
        """Test that optimization runs to completion"""
        # Create small synthetic problem
        num_electrodes = 8
        num_voxels = 50
        lfm = np.random.rand(num_electrodes, num_voxels, 3) * 0.1
        positions = np.random.rand(num_voxels, 3) * 100 - 50

        # Ensure at least one voxel is near the target [0,0,0]
        positions[0] = [0, 0, 0]  # Place first voxel at target

        optimizer = TIOptimizer(lfm, positions, num_electrodes=num_electrodes)
        optimizer.set_target([0, 0, 0], 10.0)

        # Should not raise any exceptions
        cost = optimizer.evaluate_montage([0, 1, 2, 3], 0.5)
        assert not np.isnan(cost)
        assert not np.isinf(cost)

    def test_optimization_different_targets(self):
        """Test optimization with different target locations"""
        num_electrodes = 8
        num_voxels = 50
        lfm = np.random.rand(num_electrodes, num_voxels, 3) * 0.1
        positions = np.random.rand(num_voxels, 3) * 100 - 50

        # Place voxels at the test target locations
        positions[0] = [0, 0, 0]
        positions[1] = [10, 10, 0]
        positions[2] = [-10, -10, 0]

        optimizer = TIOptimizer(lfm, positions, num_electrodes=num_electrodes)

        targets = [
            [0, 0, 0],
            [10, 10, 0],
            [-10, -10, 0]
        ]

        for target in targets:
            optimizer.set_target(target, 10.0)
            cost = optimizer.evaluate_montage([0, 1, 2, 3], 0.5)
            assert not np.isnan(cost)
            assert not np.isinf(cost)
