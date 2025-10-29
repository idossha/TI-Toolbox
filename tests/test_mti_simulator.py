import os
import sys
import importlib.util
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest


def load_mti_module(tmpdir):
    # Mock external dependencies: simnibs and utils.logging_util
    simnibs_mod = ModuleType('simnibs')
    mesh_io = MagicMock()
    run_simnibs = MagicMock()

    class FakeTDCS:
        def __init__(self):
            self.cond = [MagicMock(), MagicMock()]
        def add_electrode(self):
            return MagicMock()

    class FakeSession:
        def __init__(self):
            self.subpath = ''
            self.anisotropy_type = ''
            # mTI.py sets S.pathfem = hf_dir (high_Frequency directory)
            self.pathfem = os.path.join(str(tmpdir), 'central_montage', 'high_Frequency')
            self.eeg_cap = ''
            self.map_to_surf = False
            self.map_to_fsavg = False
            self.map_to_vol = False
            self.map_to_mni = False
            self.open_in_gmsh = False
            self.tissues_in_niftis = 'all'
            self.dti_nii = ''
        def add_tdcslist(self, *_args, **_kwargs):
            return FakeTDCS()

    sim_struct = MagicMock()
    sim_struct.SESSION.side_effect = lambda: FakeSession()

    ti_utils = ModuleType('TI_utils')
    def get_maxTI(a, b):
        return np.ones_like(a) if isinstance(a, np.ndarray) else np.array([1.0])
    ti_utils.get_maxTI = get_maxTI

    simnibs_mod.mesh_io = mesh_io
    simnibs_mod.run_simnibs = run_simnibs
    simnibs_mod.sim_struct = sim_struct

    sys.modules['simnibs'] = simnibs_mod
    sys.modules['simnibs.utils'] = ModuleType('simnibs.utils')
    sys.modules['simnibs.utils'].TI_utils = ti_utils

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
    sys.modules['tools'] = utils_pkg
    sys.modules['tools.logging_util'] = logging_util

    # Mock core.paths module (PathManager)
    core_pkg = ModuleType('core')
    
    # Create mock PathManager
    class MockPathManager:
        def __init__(self):
            self.project_dir = str(tmpdir)
            
        def get_derivatives_dir(self):
            return os.path.join(str(tmpdir), 'derivatives')
        
        def get_simnibs_dir(self):
            return os.path.join(str(tmpdir), 'derivatives', 'SimNIBS')
        
        def get_m2m_dir(self, subject_id):
            # Return a path to m2m directory
            m2m_path = os.path.join(str(tmpdir), 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}')
            os.makedirs(m2m_path, exist_ok=True)
            return m2m_path
    
    mock_pm_instance = MockPathManager()
    
    def get_path_manager():
        return mock_pm_instance
    
    core_pkg.get_path_manager = get_path_manager
    sys.modules['core'] = core_pkg

    # Provide minimal CLI args expected by mTI.py to avoid IndexError at import time
    # Args: script, subject_id, sim_type, project_dir, simulation_dir, intensities, shape, dims, thickness, eeg_net, montage
    sys.argv = [
        'mTI.py',
        'subj001',                # subject_id (argv[1])
        'scalar',                 # sim_type (argv[2])
        str(tmpdir),              # project_dir (argv[3])
        str(tmpdir),              # simulation_dir (argv[4])
        '1.0,1.0,1.0,1.0',        # intensities for 4 channels (argv[5]) - NO sim_mode param
        'rect',                   # electrode_shape (argv[6])
        '10,20',                  # dimensions (argv[7])
        '2.0',                    # thickness (argv[8])
        'EGI_template.csv',       # eeg_net (argv[9])
        'central_montage'         # montage name (argv[10])
    ]

    module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ti-toolbox', 'sim', 'mTI.py')
    spec = importlib.util.spec_from_file_location('mti_module', module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mesh_io


def test_mti_resolves_hf_meshes_and_writes_intermediates(tmp_path):
    mod, mesh_io_mock = load_mti_module(tmp_path)
    # Prepare directories the way mTI.py expects: simulation_dir/<montage>/high_Frequency/
    montage_name = 'central_montage'
    montage_dir = os.path.join(str(tmp_path), montage_name)
    hf_dir = os.path.join(montage_dir, 'high_Frequency')
    ti_mesh_dir = os.path.join(montage_dir, 'TI', 'mesh')
    mti_mesh_dir = os.path.join(montage_dir, 'mTI', 'mesh')
    os.makedirs(hf_dir, exist_ok=True)
    os.makedirs(ti_mesh_dir, exist_ok=True)
    os.makedirs(mti_mesh_dir, exist_ok=True)
    # Configure module CLI-like globals first
    mod.subject_id = 'ernie_extended'
    
    # Create 4 HF mesh files in hf_dir (S.pathfem) with correct subject ID
    for i in range(1, 5):
        open(os.path.join(hf_dir, f'{mod.subject_id}_TDCS_{i}_scalar.msh'), 'w').close()
    mod.sim_type = 'scalar'
    mod.project_dir = '/mnt/test'
    mod.simulation_dir = str(tmp_path)
    mod.intensity1_ch1 = mod.intensity1_ch2 = mod.intensity2_ch1 = mod.intensity2_ch2 = 1.0
    mod.electrode_shape = 'rect'
    mod.dimensions = [2.0, 2.0]
    mod.thickness = 4.0
    mod.eeg_net = 'EEG10-20_extended_SPM12.csv'

    # Provide four distinct fake meshes to avoid zero/identical vectors causing divide-by-zero warnings
    def make_mesh(vec):
        m = MagicMock()
        f = MagicMock()
        # Non-zero, distinct vectors per mesh
        f.value = np.tile(np.array(vec, dtype=float), (10, 1))
        m.field = {'E': f}
        m.crop_mesh.return_value = m
        return m

    mesh_A = make_mesh([1.0, 0.0, 0.0])
    mesh_B = make_mesh([0.0, 1.0, 0.0])
    mesh_C = make_mesh([0.0, 0.0, 1.0])
    mesh_D = make_mesh([1.0, 1.0, 0.0])
    mesh_io_mock.read_msh.side_effect = [mesh_A, mesh_B, mesh_C, mesh_D]
    
    # Make write_msh create the file so we can assert on filesystem
    def write_msh_side_effect(_mesh, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').close()
    mesh_io_mock.write_msh.side_effect = write_msh_side_effect

    # Act
    try:
        out = mod.run_simulation(montage_name, [['E1', 'E2'], ['E3', 'E4'], ['E5', 'E6'], ['E7', 'E8']])
    except Exception as e:
        print(f"Exception during run_simulation: {e}")
        out = None

    # Assert HF meshes were read and cropped
    assert mesh_io_mock.read_msh.call_count >= 4
    assert mesh_A.crop_mesh.called
    assert mesh_B.crop_mesh.called
    assert mesh_C.crop_mesh.called
    assert mesh_D.crop_mesh.called
    
    # Assert intermediate TI meshes were written to TI/mesh/
    ti_ab_mesh = os.path.join(ti_mesh_dir, f'{montage_name}_TI_AB.msh')
    ti_cd_mesh = os.path.join(ti_mesh_dir, f'{montage_name}_TI_CD.msh')
    assert os.path.exists(ti_ab_mesh), f"TI_AB mesh not found at {ti_ab_mesh}"
    assert os.path.exists(ti_cd_mesh), f"TI_CD mesh not found at {ti_cd_mesh}"
    
    # Assert final mTI mesh was written to mTI/mesh/
    mti_mesh = os.path.join(mti_mesh_dir, f'{montage_name}_mTI.msh')
    assert os.path.exists(mti_mesh), f"mTI mesh not found at {mti_mesh}"
    
    # Assert return value is the mTI mesh path
    assert out == mti_mesh
    



if __name__ == "__main__":
    pytest.main([__file__])
