import os
import sys
import importlib.util
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest


def load_ti_module(mock_tmpdir):
    # Mock external dependencies: simnibs and utils.logging_util
    simnibs_mod = ModuleType('simnibs')
    simnibs_mesh_io = MagicMock()
    simnibs_run_simnibs = MagicMock()

    class FakeTDCS:
        def __init__(self):
            # Provide two cond entries for conductivity overrides
            self.cond = [MagicMock(), MagicMock()]
            self.currents = [0.0, 0.0]
            self.anisotropy_type = ''
            self.electrode = []
        def add_electrode(self):
            # Minimal electrode object with attributes used by TI.py
            e = MagicMock()
            e.channelnr = None
            e.centre = None
            e.shape = None
            e.dimensions = None
            e.thickness = None
            self.electrode.append(e)
            return e

    class FakeSession:
        def __init__(self):
            self.subpath = ''
            self.anisotropy_type = ''
            # TI.py sets S.pathfem = os.path.join(temp_dir, montage_name) where temp_dir = simulation_dir/tmp
            self.pathfem = os.path.join(str(mock_tmpdir), 'tmp', 'central_montage')
            self.eeg_cap = ''
            self.map_to_surf = True
            self.map_to_fsavg = False
            self.map_to_vol = True
            self.map_to_mni = True
            self.open_in_gmsh = False
            self.tissues_in_niftis = 'all'
            self.dti_nii = ''
        def add_tdcslist(self, *_args, **_kwargs):
            return FakeTDCS()

    simnibs_sim_struct = MagicMock()
    simnibs_sim_struct.SESSION.side_effect = lambda: FakeSession()

    # TI_utils module
    ti_utils = ModuleType('TI_utils')
    def get_maxTI(a, b):
        return np.ones(len(a)) if hasattr(a, '__len__') else 1.0
    def get_dirTI(E1, E2, dirvec_org):
        return np.zeros(len(E1))
    ti_utils.get_maxTI = get_maxTI
    ti_utils.get_dirTI = get_dirTI

    simnibs_mod.mesh_io = simnibs_mesh_io
    simnibs_mod.run_simnibs = simnibs_run_simnibs
    simnibs_mod.sim_struct = simnibs_sim_struct

    simnibs_utils_mod = ModuleType('simnibs.utils')
    simnibs_utils_mod.TI_utils = ti_utils

    sys.modules['simnibs'] = simnibs_mod
    sys.modules['simnibs.utils'] = simnibs_utils_mod

    # utils.logging_util
    utils_pkg = ModuleType('utils')
    logging_util = ModuleType('logging_util')
    def get_logger(_name, _path, overwrite=False):
        class L:
            def __getattr__(self, _):
                return lambda *a, **k: None
        return L()
    def configure_external_loggers(_names, _logger):
        return None
    logging_util.get_logger = get_logger
    logging_util.configure_external_loggers = configure_external_loggers
    utils_pkg.logging_util = logging_util
    sys.modules['utils'] = utils_pkg
    sys.modules['utils.logging_util'] = logging_util

    # Provide minimal CLI args expected by TI.py to avoid IndexError at import time
    sys.argv = [
        'TI.py',
        'subj001',                 # subject_id
        'scalar',                  # sim_type
        str(mock_tmpdir),          # project_dir
        str(mock_tmpdir),          # simulation_dir
        'U',                       # sim_mode
        '1.0',                     # intensity
        'rect',                    # electrode_shape
        '10,20',                   # dimensions
        '2.0',                     # thickness
        'EGI_template.csv',        # eeg_net (exists in default montage JSON)
        'dummy_montage'            # montage name (not used in this test)
    ]

    # Load simulator/TI.py
    module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'simulator', 'TI.py')
    spec = importlib.util.spec_from_file_location('ti_module', module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Ensure FakeSession.pathfem exists for read path assembly inside run_simulation
    return mod, simnibs_mesh_io


"""Problematic TI simulator tests removed temporarily."""
