#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox core mesh utilities (core/mesh.py)
"""

import pytest
import sys
import os
from pathlib import Path

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'tit')
sys.path.insert(0, ti_toolbox_dir)

from core.mesh import create_mesh_opt_file


class TestCreateMeshOptFile:
    """Test create_mesh_opt_file function"""

    def test_basic_opt_file_creation(self, tmp_path):
        """Test creating a basic .opt file without field info"""
        mesh_path = tmp_path / "test_mesh.msh"
        mesh_path.touch()  # Create empty mesh file

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')))

        assert os.path.exists(opt_path)
        assert opt_path.endswith('.opt')

        # Read and verify content
        with open(opt_path, 'r') as f:
            content = f.read()

        assert "Mesh.SurfaceFaces" in content
        assert "Mesh.SurfaceEdges" in content
        assert "Mesh.Points" in content

    def test_opt_file_with_single_field(self, tmp_path):
        """Test creating .opt file with single field"""
        mesh_path = tmp_path / "field_mesh.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE'],
            'max_values': {'normE': 1.5},
            'field_type': 'node'
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Verify field configuration
        assert 'View[1]' in content
        assert 'normE' in content
        assert '1.5' in content or '1.500000' in content  # May have different precision

    def test_opt_file_with_multiple_fields(self, tmp_path):
        """Test creating .opt file with multiple fields"""
        mesh_path = tmp_path / "multi_field.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE', 'normJ', 'TImax'],
            'max_values': {'normE': 1.5, 'normJ': 0.025, 'TImax': 2.0},
            'field_type': 'node'
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Verify all fields are configured
        assert 'View[1]' in content  # normE
        assert 'View[2]' in content  # normJ
        assert 'View[3]' in content  # TImax

        assert 'normE' in content
        assert 'normJ' in content
        assert 'TImax' in content

        # Verify max values
        assert '1.5' in content or '1.500000' in content
        assert '0.025' in content or '0.025000' in content
        assert '2.0' in content or '2.000000' in content

    def test_opt_file_without_max_values(self, tmp_path):
        """Test creating .opt file when max_values not provided"""
        mesh_path = tmp_path / "no_max.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE', 'normJ'],
            'field_type': 'node'
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Should use default max value of 1.0
        assert 'CustomMax = 1' in content or 'CustomMax = 1.0' in content

    def test_opt_file_colormap_settings(self, tmp_path):
        """Test that colormap settings are included"""
        mesh_path = tmp_path / "colormap.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE'],
            'max_values': {'normE': 1.0}
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Verify colormap settings
        assert 'ColormapNumber' in content
        assert 'RangeType = 2' in content  # Custom range
        assert 'CustomMin = 0' in content
        assert 'ShowScale = 1' in content

    def test_opt_file_transparency_settings(self, tmp_path):
        """Test that transparency/alpha settings are included"""
        mesh_path = tmp_path / "alpha.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE'],
            'max_values': {'normE': 1.0}
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Verify alpha settings
        assert 'ColormapAlpha' in content
        assert 'ColormapAlphaPower' in content

    def test_opt_file_field_comments(self, tmp_path):
        """Test that field information comments are included"""
        mesh_path = tmp_path / "comments.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE', 'TImax'],
            'max_values': {'normE': 1.234567, 'TImax': 2.345678}
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Verify field information comments
        assert '// Field information:' in content
        assert 'normE field' in content
        assert 'TImax field' in content
        assert 'max value:' in content

    def test_opt_file_element_type(self, tmp_path):
        """Test creating .opt file with element field type"""
        mesh_path = tmp_path / "element.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE'],
            'max_values': {'normE': 1.0},
            'field_type': 'element'
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        # Should create file successfully (field_type stored but not written)
        assert os.path.exists(opt_path)

    def test_opt_file_path_with_extension(self, tmp_path):
        """Test that .opt is added correctly to path"""
        mesh_path = tmp_path / "test.msh"
        mesh_path.touch()

        # Pass path without extension (e.g., "test")
        # Function adds ".opt" to the given path, so "test" -> "test.opt"
        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')))

        assert opt_path == str(tmp_path / "test.opt")

    def test_opt_file_empty_field_list(self, tmp_path):
        """Test creating .opt file with empty field list"""
        mesh_path = tmp_path / "empty.msh"
        mesh_path.touch()

        field_info = {
            'fields': [],
            'max_values': {},
            'field_type': 'node'
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Should still have mesh settings
        assert "Mesh.SurfaceFaces" in content
        # Should not have any View configurations
        assert 'View[1]' not in content

    def test_opt_file_partial_max_values(self, tmp_path):
        """Test with some fields having max values and others not"""
        mesh_path = tmp_path / "partial.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['normE', 'normJ', 'TImax'],
            'max_values': {'normE': 1.5, 'TImax': 2.0}  # normJ missing
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Should use default for normJ
        lines = content.split('\n')
        view2_lines = [l for l in lines if 'View[2]' in l]
        # Check that View[2] (normJ) has max value of 1.0 (default)
        assert any('CustomMax = 1' in l for l in view2_lines)

    def test_opt_file_special_characters_in_field_name(self, tmp_path):
        """Test handling field names with special characters"""
        mesh_path = tmp_path / "special.msh"
        mesh_path.touch()

        field_info = {
            'fields': ['E_normal', 'normE_max'],
            'max_values': {'E_normal': 1.0, 'normE_max': 2.0}
        }

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')), field_info)

        with open(opt_path, 'r') as f:
            content = f.read()

        # Should handle underscores correctly
        assert 'E_normal' in content
        assert 'normE_max' in content

    def test_opt_file_return_value(self, tmp_path):
        """Test that function returns correct path"""
        mesh_path = tmp_path / "return.msh"
        mesh_path.touch()

        opt_path = create_mesh_opt_file(str(mesh_path.with_suffix('')))

        # Function adds ".opt" to the given path ("return" -> "return.opt")
        expected_path = str(tmp_path / "return.opt")
        assert opt_path == expected_path

    def test_opt_file_overwrite_existing(self, tmp_path):
        """Test that existing .opt file is overwritten"""
        mesh_path = tmp_path / "overwrite.msh"
        mesh_path.touch()

        # Create initial .opt file
        opt_path_1 = create_mesh_opt_file(str(mesh_path.with_suffix('')), {
            'fields': ['normE'],
            'max_values': {'normE': 1.0}
        })

        with open(opt_path_1, 'r') as f:
            content_1 = f.read()

        # Create new .opt file with different settings
        opt_path_2 = create_mesh_opt_file(str(mesh_path.with_suffix('')), {
            'fields': ['TImax'],
            'max_values': {'TImax': 2.0}
        })

        with open(opt_path_2, 'r') as f:
            content_2 = f.read()

        # Paths should be the same
        assert opt_path_1 == opt_path_2

        # Content should be different
        assert content_1 != content_2
        assert 'TImax' in content_2
        assert 'normE' not in content_2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
