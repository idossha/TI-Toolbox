import os
import sys
import importlib.util
from types import SimpleNamespace, ModuleType
import pytest


def load_flex_module():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ti-toolbox'))
    sys.path.insert(0, base_dir)
    # Import the flex_config module which has parse_arguments
    from opt.flex import flex_config
    return flex_config


def load_flex_utils_module():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ti-toolbox'))
    sys.path.insert(0, base_dir)
    # Import the utils module which has roi_dirname
    from opt.flex import utils
    return utils


class TestParseArguments:
    def test_parse_required_arguments(self, monkeypatch):
        mod = load_flex_module()
        argv = [
            'flex_search',
            '--subject', 'subj001',
            '--goal', 'mean',
            '--postproc', 'max_TI',
            '--eeg-net', 'EGI_template',
            '--radius', '5',
            '--current', '1',
            '--roi-method', 'spherical'
        ]
        monkeypatch.setattr(sys, 'argv', argv)
        args = mod.parse_arguments()
        assert args.subject == 'subj001'
        assert args.goal == 'mean'
        assert args.postproc == 'max_TI'
        assert args.eeg_net == 'EGI_template'
        assert args.radius == 5
        assert args.current == 1
        assert args.roi_method == 'spherical'


class TestRoiDirname:
    def test_roi_dirname_spherical(self, monkeypatch):
        utils_mod = load_flex_utils_module()
        args = SimpleNamespace(goal='max', postproc='max_TI', roi_method='spherical')
        monkeypatch.setenv('ROI_X', '-50')
        monkeypatch.setenv('ROI_Y', '0')
        monkeypatch.setenv('ROI_Z', '0')
        monkeypatch.setenv('ROI_RADIUS', '5')
        assert utils_mod.roi_dirname(args) == 'sphere_x-50y0z0r5_max_maxTI'

    def test_roi_dirname_atlas(self, monkeypatch):
        utils_mod = load_flex_utils_module()
        args = SimpleNamespace(goal='max', postproc='dir_TI_normal', roi_method='atlas')
        monkeypatch.setenv('ATLAS_PATH', '/some/path/lh.101_DK40.annot')
        monkeypatch.setenv('SELECTED_HEMISPHERE', 'lh')
        monkeypatch.setenv('ROI_LABEL', '101')
        assert utils_mod.roi_dirname(args) == 'lh_DK40_101_max_normalTI'

    def test_roi_dirname_subcortical(self, monkeypatch):
        utils_mod = load_flex_utils_module()
        args = SimpleNamespace(goal='focality', postproc='dir_TI_tangential', roi_method='subcortical')
        monkeypatch.setenv('VOLUME_ATLAS_PATH', '/some/path/atlas.nii.gz')
        monkeypatch.setenv('VOLUME_ROI_LABEL', '10')
        assert utils_mod.roi_dirname(args) == 'subcortical_atlas_10_focality_tangentialTI'


 
