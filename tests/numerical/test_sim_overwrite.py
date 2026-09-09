"""Exercise the real SimNIBS existing-result guard, without running a FEM solve."""

import subprocess
import sys
import textwrap

import pytest


def test_confirmed_overwrite_reaches_real_simnibs_session(tmp_path):
    # A subprocess avoids the host suite's SimNIBS mocks. Only optional installation
    # absence skips; any error in the real guard or production adapter fails.
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip("Real SimNIBS is required (run this test in the toolbox container)")
    code = textwrap.dedent("""
        import logging
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from simnibs import sim_struct
        from simnibs.simulation import sim_struct as implementation
        from tit.sim.base import BaseSimulation

        root = Path(sys.argv[1])
        hf = root / "high_Frequency"
        hf.mkdir()
        marker = hf / "simnibs_simulation_existing.mat"
        marker.write_bytes(b"keep existing session record")
        output = hf / "field.msh"
        output.write_text("old result")
        class Poslist:
            name = "fixture"
            def run_simulation(self, *args, **kwargs):
                output.write_text("new result")
                return [str(output)], []
        session = sim_struct.SESSION()
        session.pathfem = str(hf)
        session.fnamehead = "fixture.msh"
        session.poslists = [Poslist()]
        session._prepare = lambda: None
        session._set_logger = lambda: None
        session._finish_logger = lambda: None
        session.map_to_surf = session.map_to_fsavg = False
        session.map_to_vol = session.map_to_MNI = False
        class Simulation(BaseSimulation):
            _simulation_mode = "fixture"
            _montage_type_label = "TI"
            _montage_imgs_key = "images"
            def _build_session(self, output_dir):
                return session
            def _post_process(self, dirs):
                return str(output)
        simulation = object.__new__(Simulation)
        simulation.pm = SimpleNamespace(simulation=lambda *args: str(root))
        simulation.config = SimpleNamespace(subject_id="fixture")
        simulation.montage = SimpleNamespace(name="fixture", is_xyz=True, eeg_net="")
        simulation.logger = logging.getLogger("fixture")
        dirs = {"hf_dir": str(hf), "documentation": str(root), "images": str(root)}
        with patch("tit.sim.base.setup_montage_directories", return_value=dirs), \\
             patch("tit.sim.base.create_simulation_config_file"), \\
             patch("tit.sim.base.run_montage_visualization"), \\
             patch.object(implementation, "save_matlab_sim_struct"):
            try:
                simulation.run(str(root))
            except OSError as error:
                assert "already existing simulation results" in str(error)
            else:
                raise AssertionError("Unconfirmed run bypassed existing-result guard")
            assert output.read_text() == "old result"
            result = simulation.run(str(root), overwrite=True)
            assert result["status"] == "completed"
            assert output.read_text() == "new result"
            assert marker.read_bytes() == b"keep existing session record"
    """)
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
