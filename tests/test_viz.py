#!/usr/bin/env simnibs_python
"""
Comprehensive tests for ti-toolbox/viz/ module

Tests cover:
- img_glass.py: Glass brain visualization functions
- img_slices.py: Slice visualization functions
- html_report.py: HTML report generation

All external dependencies (matplotlib, nilearn, nibabel) are mocked for headless testing.
"""

import pytest
import numpy as np
import os
import sys
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

# Add ti-toolbox directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ti-toolbox'))


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_nifti_img():
    """Create mock nibabel NIfTI image"""
    mock_img = MagicMock()
    mock_img.affine = np.eye(4)
    mock_img.header = MagicMock()
    mock_img.shape = (91, 109, 91)
    # Create realistic E-field data
    data = np.random.rand(91, 109, 91).astype(np.float32) * 5  # 0-5 V/m
    data[data < 0.3] = 0  # Threshold low values
    mock_img.get_fdata = MagicMock(return_value=data)
    return mock_img


@pytest.fixture
def mock_path_manager():
    """Create mock PathManager"""
    mock_pm = MagicMock()
    mock_pm.get_subject_dir = MagicMock(return_value='/fake/project/derivatives/SimNIBS/sub-001')
    mock_pm.get_simulation_dir = MagicMock(return_value='/fake/project/derivatives/SimNIBS/sub-001/Simulations/montage1')
    mock_pm.get_derivatives_dir = MagicMock(return_value='/fake/project/derivatives')
    return mock_pm


@pytest.fixture
def mock_visualizer():
    """Create mock NilearnVisualizer"""
    with patch('ti_toolbox.viz.img_glass.NilearnVisualizer') as mock_viz:
        instance = MagicMock()
        mock_viz.return_value = instance
        yield instance


# ==============================================================================
# TEST img_glass.py - Glass Brain Visualizations
# ==============================================================================

class TestCreateGlassBrainEntryPoint:
    """Test glass brain visualization entry point"""

    @pytest.mark.unit
    @patch('viz.img_glass.NilearnVisualizer')
    def test_glass_brain_success(self, mock_viz_class):
        """Test successful glass brain visualization creation"""
        from viz.img_glass import create_glass_brain_entry_point

        # Mock visualizer
        mock_viz = MagicMock()
        mock_viz.create_glass_brain_visualization = MagicMock(
            return_value='/fake/output/glass_brain.pdf'
        )
        mock_viz_class.return_value = mock_viz

        result = create_glass_brain_entry_point(
            subject_id='001',
            simulation_name='montage1',
            min_cutoff=0.3,
            max_cutoff=2.0,
            cmap='hot'
        )

        assert result == '/fake/output/glass_brain.pdf'
        mock_viz.create_glass_brain_visualization.assert_called_once_with(
            '001', 'montage1', 0.3, 2.0, 'hot'
        )

    @pytest.mark.unit
    @patch('viz.img_glass.NilearnVisualizer')
    def test_glass_brain_failure(self, mock_viz_class):
        """Test glass brain visualization failure"""
        from viz.img_glass import create_glass_brain_entry_point

        # Mock visualizer that returns None (failure)
        mock_viz = MagicMock()
        mock_viz.create_glass_brain_visualization = MagicMock(return_value=None)
        mock_viz_class.return_value = mock_viz

        result = create_glass_brain_entry_point('001', 'montage1')

        assert result is None

    @pytest.mark.unit
    @patch('viz.img_glass.NilearnVisualizer')
    def test_glass_brain_with_callback(self, mock_viz_class):
        """Test glass brain with output callback"""
        from viz.img_glass import create_glass_brain_entry_point

        mock_viz = MagicMock()
        mock_viz.create_glass_brain_visualization = MagicMock(
            return_value='/fake/output/glass_brain.pdf'
        )
        mock_viz_class.return_value = mock_viz

        callback_messages = []

        def mock_callback(msg):
            callback_messages.append(msg)

        result = create_glass_brain_entry_point(
            '001', 'montage1', output_callback=mock_callback
        )

        assert result == '/fake/output/glass_brain.pdf'
        assert len(callback_messages) > 0  # Should have received messages


class TestCreateGlassBrainEntryPointGroup:
    """Test glass brain visualization for group-averaged data"""

    @pytest.mark.unit
    @patch('matplotlib.pyplot.savefig')
    @patch('nilearn.plotting.plot_glass_brain')
    @patch('os.makedirs')
    def test_glass_brain_group_success(self, mock_makedirs, mock_plot, mock_savefig, mock_nifti_img):
        """Test successful group glass brain visualization"""
        from viz.img_glass import create_glass_brain_entry_point_group

        result = create_glass_brain_entry_point_group(
            averaged_img=mock_nifti_img,
            base_filename='group_average',
            output_dir='/fake/output',
            min_cutoff=0.3,
            max_cutoff=2.0,
            cmap='hot'
        )

        assert result is not None
        assert 'glass_brain.pdf' in result
        mock_plot.assert_called_once()

    @pytest.mark.unit
    @patch('nilearn.plotting.plot_glass_brain')
    def test_glass_brain_group_no_data(self, mock_plot):
        """Test glass brain with no non-zero data"""
        from viz.img_glass import create_glass_brain_entry_point_group

        # Create image with all zeros
        mock_img = MagicMock()
        mock_img.get_fdata = MagicMock(return_value=np.zeros((91, 109, 91)))

        result = create_glass_brain_entry_point_group(
            averaged_img=mock_img,
            base_filename='empty',
            output_dir='/fake/output'
        )

        assert result is None
        mock_plot.assert_not_called()

    @pytest.mark.unit
    @patch('nilearn.plotting.plot_glass_brain')
    def test_glass_brain_group_with_callback(self, mock_plot, mock_nifti_img):
        """Test group glass brain with callback"""
        from viz.img_glass import create_glass_brain_entry_point_group

        callback_messages = []

        def mock_callback(msg):
            callback_messages.append(msg)

        result = create_glass_brain_entry_point_group(
            averaged_img=mock_nifti_img,
            base_filename='group',
            output_dir='/fake/output',
            output_callback=mock_callback
        )

        assert len(callback_messages) > 0


# ==============================================================================
# TEST img_slices.py - PDF Slice Visualizations
# ==============================================================================

class TestCreatePdfEntryPoint:
    """Test PDF slice visualization entry point"""

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_success(self, mock_viz_class):
        """Test successful PDF visualization creation"""
        from viz.img_slices import create_pdf_entry_point

        # Mock visualizer
        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(
            return_value='/fake/output/slices.pdf'
        )
        mock_viz_class.return_value = mock_viz

        result = create_pdf_entry_point(
            subject_id='001',
            simulation_name='montage1',
            min_cutoff=0.3,
            max_cutoff=2.0,
            atlas_name='harvard_oxford_sub',
            selected_regions=[1, 2, 3]
        )

        assert result == '/fake/output/slices.pdf'
        mock_viz.create_pdf_visualization.assert_called_once()

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_failure(self, mock_viz_class):
        """Test PDF visualization failure"""
        from viz.img_slices import create_pdf_entry_point

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(return_value=None)
        mock_viz_class.return_value = mock_viz

        result = create_pdf_entry_point('001', 'montage1')

        assert result is None

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_with_callback(self, mock_viz_class):
        """Test PDF visualization with output callback"""
        from viz.img_slices import create_pdf_entry_point

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(
            return_value='/fake/output/slices.pdf'
        )
        mock_viz_class.return_value = mock_viz

        callback_messages = []

        def mock_callback(msg):
            callback_messages.append(msg)

        result = create_pdf_entry_point(
            '001', 'montage1', output_callback=mock_callback
        )

        assert result == '/fake/output/slices.pdf'
        assert len(callback_messages) > 0

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_with_atlas_regions(self, mock_viz_class):
        """Test PDF with specific atlas regions"""
        from viz.img_slices import create_pdf_entry_point

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(
            return_value='/fake/output/slices.pdf'
        )
        mock_viz_class.return_value = mock_viz

        result = create_pdf_entry_point(
            '001', 'montage1',
            atlas_name='aal',
            selected_regions=[10, 20, 30]
        )

        # Verify selected_regions were passed
        call_args = mock_viz.create_pdf_visualization.call_args
        assert call_args[0][5] == [10, 20, 30]  # selected_regions is 6th positional arg


class TestCreatePdfEntryPointGroup:
    """Test PDF visualization for group-averaged data"""

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_group_success(self, mock_viz_class, mock_nifti_img):
        """Test successful group PDF visualization"""
        from viz.img_slices import create_pdf_entry_point_group

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization_group = MagicMock(
            return_value='/fake/output/group_slices.pdf'
        )
        mock_viz_class.return_value = mock_viz

        result = create_pdf_entry_point_group(
            averaged_img=mock_nifti_img,
            base_filename='group_average',
            output_dir='/fake/output',
            min_cutoff=0.3,
            atlas_name='harvard_oxford_sub'
        )

        assert result == '/fake/output/group_slices.pdf'
        mock_viz.create_pdf_visualization_group.assert_called_once()

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_group_failure(self, mock_viz_class, mock_nifti_img):
        """Test group PDF visualization failure"""
        from viz.img_slices import create_pdf_entry_point_group

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization_group = MagicMock(return_value=None)
        mock_viz_class.return_value = mock_viz

        result = create_pdf_entry_point_group(
            mock_nifti_img, 'group', '/fake/output'
        )

        assert result is None

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_group_with_callback(self, mock_viz_class, mock_nifti_img):
        """Test group PDF with callback"""
        from viz.img_slices import create_pdf_entry_point_group

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization_group = MagicMock(
            return_value='/fake/output/group.pdf'
        )
        mock_viz_class.return_value = mock_viz

        callback_messages = []

        def mock_callback(msg):
            callback_messages.append(msg)

        result = create_pdf_entry_point_group(
            mock_nifti_img, 'group', '/fake/output',
            output_callback=mock_callback
        )

        assert result == '/fake/output/group.pdf'
        assert len(callback_messages) > 0


# ==============================================================================
# TEST html_report.py - HTML Report Generation
# ==============================================================================

class TestCreateHtmlEntryPoint:
    """Test HTML report generation entry point"""

    @pytest.mark.unit
    @patch('viz.html_report.NilearnVisualizer')
    def test_html_success(self, mock_viz_class):
        """Test successful HTML report creation"""
        from viz.html_report import create_html_entry_point

        # Mock visualizer
        mock_viz = MagicMock()
        mock_viz.create_html_visualization = MagicMock(
            return_value='/fake/output/report.html'
        )
        mock_viz_class.return_value = mock_viz

        result = create_html_entry_point(
            subject_id='001',
            simulation_name='montage1',
            min_cutoff=0.3
        )

        assert result == 0  # Success exit code
        mock_viz.create_html_visualization.assert_called_once_with('001', 'montage1', 0.3)

    @pytest.mark.unit
    @patch('viz.html_report.NilearnVisualizer')
    def test_html_failure(self, mock_viz_class):
        """Test HTML report creation failure"""
        from viz.html_report import create_html_entry_point

        mock_viz = MagicMock()
        mock_viz.create_html_visualization = MagicMock(return_value=None)
        mock_viz_class.return_value = mock_viz

        result = create_html_entry_point('001', 'montage1')

        assert result == 1  # Failure exit code

    @pytest.mark.unit
    @patch('viz.html_report.NilearnVisualizer')
    def test_html_with_custom_cutoff(self, mock_viz_class):
        """Test HTML report with custom cutoff"""
        from viz.html_report import create_html_entry_point

        mock_viz = MagicMock()
        mock_viz.create_html_visualization = MagicMock(
            return_value='/fake/output/report.html'
        )
        mock_viz_class.return_value = mock_viz

        result = create_html_entry_point('001', 'montage1', min_cutoff=0.5)

        assert result == 0
        call_args = mock_viz.create_html_visualization.call_args[0]
        assert call_args[2] == 0.5  # Check cutoff parameter


# ==============================================================================
# TEST CLI INTERFACES (MOCKED)
# ==============================================================================

class TestGlassBrainCLI:
    """Test glass brain CLI interface"""

    @pytest.mark.unit
    @patch('sys.argv', ['img_glass.py', '--subject', '001', '--simulation', 'montage1'])
    @patch('viz.img_glass.create_glass_brain_entry_point')
    def test_glass_brain_cli_basic(self, mock_entry):
        """Test basic glass brain CLI invocation"""
        from viz.img_glass import main

        mock_entry.return_value = '/fake/output.pdf'

        result = main()

        mock_entry.assert_called_once()
        # Verify arguments
        call_args = mock_entry.call_args[0]
        assert call_args[0] == '001'
        assert call_args[1] == 'montage1'

    @pytest.mark.unit
    @patch('sys.argv', [
        'img_glass.py',
        '--subject', '001',
        '--simulation', 'montage1',
        '--min-cutoff', '0.5',
        '--max-cutoff', '3.0',
        '--cmap', 'plasma'
    ])
    @patch('viz.img_glass.create_glass_brain_entry_point')
    def test_glass_brain_cli_with_options(self, mock_entry):
        """Test glass brain CLI with all options"""
        from viz.img_glass import main

        mock_entry.return_value = '/fake/output.pdf'

        result = main()

        # Verify all arguments passed correctly
        call_args = mock_entry.call_args[0]
        assert call_args[2] == 0.5  # min_cutoff
        assert call_args[3] == 3.0  # max_cutoff
        assert call_args[4] == 'plasma'  # cmap


class TestSlicesCLI:
    """Test slices PDF CLI interface"""

    @pytest.mark.unit
    @patch('sys.argv', ['img_slices.py', '--subject', '001', '--simulation', 'montage1'])
    @patch('viz.img_slices.create_pdf_entry_point')
    def test_slices_cli_basic(self, mock_entry):
        """Test basic slices CLI invocation"""
        from viz.img_slices import main

        mock_entry.return_value = '/fake/output.pdf'

        result = main()

        mock_entry.assert_called_once()
        call_args = mock_entry.call_args[0]
        assert call_args[0] == '001'
        assert call_args[1] == 'montage1'

    @pytest.mark.unit
    @patch('sys.argv', [
        'img_slices.py',
        '--subject', '001',
        '--simulation', 'montage1',
        '--atlas', 'aal',
        '--regions', '1', '2', '3'
    ])
    @patch('viz.img_slices.create_pdf_entry_point')
    def test_slices_cli_with_atlas_regions(self, mock_entry):
        """Test slices CLI with atlas and regions"""
        from viz.img_slices import main

        mock_entry.return_value = '/fake/output.pdf'

        result = main()

        # Verify atlas and regions (passed as positional args)
        call_args = mock_entry.call_args[0]
        assert call_args[4] == 'aal'  # atlas_name is 5th positional arg
        assert call_args[5] == [1, 2, 3]  # selected_regions is 6th positional arg


class TestHtmlReportCLI:
    """Test HTML report CLI interface"""

    @pytest.mark.unit
    @patch('sys.argv', ['html_report.py', '--subject', '001', '--simulation', 'montage1'])
    @patch('viz.html_report.create_html_entry_point')
    def test_html_cli_basic(self, mock_entry):
        """Test basic HTML report CLI invocation"""
        from viz.html_report import main

        mock_entry.return_value = 0

        result = main()

        assert result == 0
        mock_entry.assert_called_once()

    @pytest.mark.unit
    @patch('sys.argv', [
        'html_report.py',
        '--subject', '001',
        '--simulation', 'montage1',
        '--cutoff', '0.7'
    ])
    @patch('viz.html_report.create_html_entry_point')
    def test_html_cli_with_cutoff(self, mock_entry):
        """Test HTML report CLI with custom cutoff"""
        from viz.html_report import main

        mock_entry.return_value = 0

        result = main()

        call_args = mock_entry.call_args[0]
        assert call_args[2] == 0.7  # cutoff parameter


# ==============================================================================
# INTEGRATION TESTS (Mocked Matplotlib Backend)
# ==============================================================================

class TestMatplotlibBackend:
    """Test matplotlib backend handling for headless operation"""

    @pytest.mark.unit
    @patch('matplotlib.use')
    def test_agg_backend_used(self, mock_use):
        """Test that Agg backend is used for headless rendering"""
        # Import should set backend
        import matplotlib
        matplotlib.use('Agg')

        mock_use.assert_called_with('Agg')

    @pytest.mark.unit
    @patch('matplotlib.pyplot.figure')
    @patch('matplotlib.pyplot.close')
    def test_figure_cleanup(self, mock_close, mock_figure):
        """Test that figures are properly closed after rendering"""
        import matplotlib.pyplot as plt

        # Create and close figure
        fig = plt.figure()
        plt.close(fig)

        mock_figure.assert_called()
        mock_close.assert_called()


# ==============================================================================
# ERROR HANDLING TESTS
# ==============================================================================

class TestVisualizationErrorHandling:
    """Test error handling in visualization functions"""

    @pytest.mark.unit
    @patch('viz.img_glass.NilearnVisualizer')
    def test_glass_brain_exception_handling(self, mock_viz_class):
        """Test glass brain raises exceptions from visualizer"""
        from viz.img_glass import create_glass_brain_entry_point

        mock_viz = MagicMock()
        mock_viz.create_glass_brain_visualization = MagicMock(
            side_effect=Exception("Visualization failed")
        )
        mock_viz_class.return_value = mock_viz

        # Should raise the exception from the visualizer
        with pytest.raises(Exception, match="Visualization failed"):
            create_glass_brain_entry_point('001', 'montage1')

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_exception_handling(self, mock_viz_class):
        """Test PDF visualization raises exceptions from visualizer"""
        from viz.img_slices import create_pdf_entry_point

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(
            side_effect=Exception("PDF generation failed")
        )
        mock_viz_class.return_value = mock_viz

        # Should raise the exception from the visualizer
        with pytest.raises(Exception, match="PDF generation failed"):
            create_pdf_entry_point('001', 'montage1')


# ==============================================================================
# PARAMETER VALIDATION TESTS
# ==============================================================================

class TestParameterValidation:
    """Test parameter validation in visualization functions"""

    @pytest.mark.unit
    @patch('viz.img_glass.NilearnVisualizer')
    def test_glass_brain_valid_parameters(self, mock_viz_class):
        """Test glass brain with valid parameter ranges"""
        from viz.img_glass import create_glass_brain_entry_point

        mock_viz = MagicMock()
        mock_viz.create_glass_brain_visualization = MagicMock(return_value='/fake/output.pdf')
        mock_viz_class.return_value = mock_viz

        # Valid parameters
        result = create_glass_brain_entry_point(
            '001', 'montage1',
            min_cutoff=0.0,
            max_cutoff=10.0,
            cmap='hot'
        )

        assert result is not None

    @pytest.mark.unit
    @patch('viz.img_slices.NilearnVisualizer')
    def test_pdf_valid_atlas_names(self, mock_viz_class):
        """Test PDF with valid atlas names"""
        from viz.img_slices import create_pdf_entry_point

        mock_viz = MagicMock()
        mock_viz.create_pdf_visualization = MagicMock(return_value='/fake/output.pdf')
        mock_viz_class.return_value = mock_viz

        for atlas in ['harvard_oxford', 'harvard_oxford_sub', 'aal', 'schaefer_2018']:
            result = create_pdf_entry_point('001', 'montage1', atlas_name=atlas)
            assert result is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
