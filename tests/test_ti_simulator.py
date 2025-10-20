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
            # TI.py sets S.pathfem = hf_dir (high_Frequency directory)
            self.pathfem = os.path.join(str(mock_tmpdir), 'central_montage', 'high_Frequency')
            self.eeg_cap = ''
            self.map_to_surf = True
            self.map_to_fsavg = False
            self.map_to_vol = True
            self.map_to_mni = True
            self.open_in_gmsh = False
            self.tissues_in_niftis = 'all'
            self.dti_nii = ''
        def add_tdcslist(self, *args, **_kwargs):
            # If a pre-populated tdcs object is provided (deepcopy), use it
            if len(args) >= 1 and isinstance(args[0], FakeTDCS):
                return args[0]
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
    sys.modules['tools'] = utils_pkg
    sys.modules['tools.logging_util'] = logging_util

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


def test_ti_reads_hf_meshes_and_writes_output(tmp_path):
    mod, mesh_io_mock = load_ti_module(tmp_path)
    # Ensure TI.py uses our mock directly
    mod.mesh_io = mesh_io_mock

    # Prepare directories the way TI.py expects: simulation_dir/<montage>/high_Frequency/
    montage_name = 'central_montage'
    montage_dir = os.path.join(str(tmp_path), montage_name)
    hf_dir = os.path.join(montage_dir, 'high_Frequency')
    ti_mesh_dir = os.path.join(montage_dir, 'TI', 'mesh')
    os.makedirs(hf_dir, exist_ok=True)
    os.makedirs(ti_mesh_dir, exist_ok=True)
    # Expected filenames use subject_id and anisotropy type set in sys.argv within loader
    # TI.py expects these in S.pathfem which is hf_dir
    open(os.path.join(hf_dir, 'subj001_TDCS_1_scalar.msh'), 'w').close()
    open(os.path.join(hf_dir, 'subj001_TDCS_2_scalar.msh'), 'w').close()

    # Minimal fake mesh object implementing required API
    class FakeField:
        def __init__(self, value):
            self.value = value

    class FakeViewer:
        def write_opt(self, _path):
            return None

    class FakeMesh:
        def __init__(self, vec):
            self.field = {'E': FakeField(np.tile(np.array(vec, dtype=float), (10, 1)))}
            # Element tags for fallback path; set to zeros so no GM selection
            self.elm = type('E', (), {'tag1': np.zeros(10, dtype=int)})()
            self.nodedata = []
            self.elmdata = []
            self.crop_mesh_called = False
        def crop_mesh(self, **_kwargs):
            self.crop_mesh_called = True
            return self
        def add_element_field(self, *_args, **_kwargs):
            return None
        def add_node_field(self, *_args, **_kwargs):
            return None
        def view(self, **_kwargs):
            return FakeViewer()
        def __deepcopy__(self, _memo):
            # Produce a shallow functional copy for test purposes
            new = FakeMesh([1.0, 0.0, 0.0])
            new.field = {'E': FakeField(self.field['E'].value.copy())}
            new.elm = type('E', (), {'tag1': self.elm.tag1.copy()})()
            return new

    mesh_A = FakeMesh([1.0, 0.0, 0.0])
    mesh_B = FakeMesh([0.0, 1.0, 0.0])
    mesh_io_mock.read_msh.side_effect = [mesh_A, mesh_B]

    # Make write_msh create the file so we can assert on filesystem
    def write_msh_side_effect(_mesh, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').close()
    mesh_io_mock.write_msh.side_effect = write_msh_side_effect

    # Act (let exceptions surface to aid debugging if any)
    mod.run_simulation(montage_name, [['E1', 'E2'], ['E3', 'E4']], is_xyz=False)

    # Assert TI output was written to TI/mesh/ directory
    ti_out = os.path.join(ti_mesh_dir, f'{montage_name}_TI.msh')
    assert os.path.exists(ti_out)


def test_ti_uses_central_surface_when_available(tmp_path):
    mod, mesh_io_mock = load_ti_module(tmp_path)
    # Ensure TI.py uses our mock directly
    mod.mesh_io = mesh_io_mock

    montage_name = 'central_montage'
    montage_dir = os.path.join(str(tmp_path), montage_name)
    hf_dir = os.path.join(montage_dir, 'high_Frequency')
    ti_mesh_dir = os.path.join(montage_dir, 'TI', 'mesh')
    overlays_dir = os.path.join(hf_dir, 'subject_overlays')
    os.makedirs(hf_dir, exist_ok=True)
    os.makedirs(ti_mesh_dir, exist_ok=True)
    os.makedirs(overlays_dir, exist_ok=True)
    # Create required HF mesh files in hf_dir (S.pathfem)
    open(os.path.join(hf_dir, 'subj001_TDCS_1_scalar.msh'), 'w').close()
    open(os.path.join(hf_dir, 'subj001_TDCS_2_scalar.msh'), 'w').close()
    # Create central surface files to trigger central path
    open(os.path.join(overlays_dir, 'subj001_TDCS_1_scalar_central.msh'), 'w').close()
    open(os.path.join(overlays_dir, 'subj001_TDCS_2_scalar_central.msh'), 'w').close()

    class FakeField:
        def __init__(self, value):
            self.value = value

    class FakeViewer:
        def write_opt(self, _path):
            return None

    class FakeMesh:
        def __init__(self, vec):
            self.field = {'E': FakeField(np.tile(np.array(vec, dtype=float), (10, 1)))}
            self.elm = type('E', (), {'tag1': np.zeros(10, dtype=int)})()
            self.nodedata = []
            self.elmdata = []
            self.crop_mesh_called = False
        def crop_mesh(self, **_kwargs):
            self.crop_mesh_called = True
            return self
        def add_element_field(self, *_args, **_kwargs):
            return None
        def add_node_field(self, *_args, **_kwargs):
            return None
        def view(self, **_kwargs):
            return FakeViewer()
        def __deepcopy__(self, _memo):
            new = FakeMesh([1.0, 0.0, 0.0])
            new.field = {'E': FakeField(self.field['E'].value.copy())}
            new.elm = type('E', (), {'tag1': self.elm.tag1.copy()})()
            new.nodedata = []
            new.elmdata = []
            return new

    class FakeCentralMesh(FakeMesh):
        def __init__(self, vec):
            super().__init__(vec)
        def add_node_field(self, *_args, **_kwargs):
            return None
        def nodes_normals(self):
            return type('N', (), {'value': np.tile(np.array([0.0, 0.0, 1.0]), (10, 1))})()

    hf_A = FakeMesh([1.0, 0.0, 0.0])
    hf_B = FakeMesh([0.0, 1.0, 0.0])
    central_1 = FakeCentralMesh([1.0, 0.0, 0.0])
    central_2 = FakeCentralMesh([0.0, 1.0, 0.0])

    # read_msh sequence: TDCS1, TDCS2, central1, central2
    mesh_io_mock.read_msh.side_effect = [hf_A, hf_B, central_1, central_2]

    # Make write_msh create files
    def write_msh_side_effect(_mesh, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').close()
    mesh_io_mock.write_msh.side_effect = write_msh_side_effect

    # Act
    mod.run_simulation(montage_name, [['E1', 'E2'], ['E3', 'E4']], is_xyz=False)

    # Assert central TI normal surface output was written to TI/mesh/
    central_out = os.path.join(ti_mesh_dir, f'{montage_name}_normal.msh')
    assert os.path.exists(central_out)


if __name__ == "__main__":
    pytest.main([__file__])
