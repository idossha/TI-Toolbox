"""A field produced on demand is the field the simulator would have written (real SimNIBS meshes).

Pins (2026-10-30, docs/dev/DECISIONS.md "field meshes by default"): on SimNIBS's own test mesh
``sphere3.msh`` with two random channel fields written by ``mesh_io.write_msh`` (binary, as a run
keeps them in ``high_Frequency/mesh/``):

* a run that saved only ``TI_max`` (written by ``BaseSimulation._write_volume_mesh`` itself) gets
  ``hf_peak`` and ``hf_rms`` from ``tit.volume_fields.ensure_mesh_fields``, and the saved values are
  bit-identical to a run that selected them (the same ``compute_volume_fields``, the same crop);
* ``hf_peak`` equals ``max(|E1 + E2|, |E1 - E2|)`` and ``hf_rms`` ``sqrt((|E1|^2 + |E2|^2) / 2)`` on the
  brain-cropped elements, computed here with numpy from the channel meshes read back by SimNIBS;
* the header reader ``tit.tools.msh_fields`` (no SimNIBS) reads SimNIBS's binary output: the field
  list, and ``TI_max``'s values equal to what ``mesh_io.read_msh`` reads.

The grey/white cut (sphere3 has no GM/WM tags) and ``msh2cortex`` (needs an m2m) are stubbed; the image run in the
change's report covers them on Ernie.

Reproduce in the image: ``simnibs_python -m pytest tests/numerical/test_sim_fields_on_demand_real.py -q``
(the subprocess avoids the host conftest's SimNIBS mocks). Wiring, failures and NIfTI naming are
``tests/test_sim_fields_on_demand.py``.
"""

import subprocess
import sys

import pytest

_SCRIPT = r"""
import json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import simnibs
from simnibs.mesh_tools import mesh_io

import tit.sim.utils
from tit.paths import get_path_manager

# sphere3 has no GM/scalp triangles for the Gmsh view's percentile window; the view is not
# what this pins, so the .opt beside the mesh is skipped.
mesh_io.Msh.view = lambda self, **kw: SimpleNamespace(write_opt=lambda path: None)
from tit import volume_fields as fields
from tit.sim.base import BaseSimulation
from tit.tools.msh_fields import msh_element_field, msh_field_names

root = Path(tempfile.mkdtemp())
(root / "derivatives" / "SimNIBS" / "sub-s" / "m2m_s").mkdir(parents=True)
pm = get_path_manager(str(root))
sim = Path(pm.simulation("s", "M"))
hf = sim / "high_Frequency" / "mesh"
hf.mkdir(parents=True)
(sim / "TI" / "mesh" / "surfaces").mkdir(parents=True)
(sim / "documentation").mkdir()
(sim / "documentation" / "config.json").write_text(json.dumps(
    {"subject_id": "s", "conductivity": "scalar", "electrode_pairs": [["a", "b"], ["c", "d"]],
     "carrier_only": False}))

sphere = mesh_io.read_msh(os.path.join(os.path.dirname(simnibs.__file__),
                          "_internal_resources", "testing_files", "sphere3.msh"))
rng = np.random.default_rng(7)
for i in (1, 2):
    m = mesh_io.read_msh(os.path.join(os.path.dirname(simnibs.__file__),
                         "_internal_resources", "testing_files", "sphere3.msh"))
    m.elmdata = []
    m.add_element_field(rng.normal(size=(m.elm.nr, 3)), "E")
    mesh_io.write_msh(m, str(hf / f"s_TDCS_{i}_scalar.msh"))

channels = [mesh_io.read_msh(str(hf / f"s_TDCS_{i}_scalar.msh")).crop_mesh(tags=fields.BRAIN_TAGS)
            for i in (1, 2)]
assert channels[0].elm.nr > 0
def written_by_the_simulator(output_fields, path):
    stub = SimpleNamespace(config=SimpleNamespace(output_fields=output_fields, carrier_only=False),
                           logger=SimpleNamespace(info=lambda *a: None), _montage_type_label="TI")
    BaseSimulation._write_volume_mesh(stub, [m for m in channels], "TI_max", str(path))

volume = sim / "TI" / "mesh" / "M_TI.msh"
written_by_the_simulator(["TI_max"], volume)
assert msh_field_names(volume) == {"TI_max"}
assert np.array_equal(msh_element_field(volume, "TI_max"),
                      mesh_io.read_msh(str(volume)).field["TI_max"].value)

import shutil

def cut(volume, out_dir, stem, *rest):  # sphere3 has no GM/WM tags: copy, as a cut would
    for tissue in ("grey", "white"):
        shutil.copy(volume, Path(out_dir) / f"{tissue}_{stem}.msh")

with patch.object(tit.sim.utils, "extract_fields", cut), \
     patch.object(tit.sim.utils, "generate_central_surface", lambda *a: None):
    notices = fields.ensure_mesh_fields("s", "M", ["TI_max", "hf_peak", "hf_rms"])
assert notices == ["hf_peak and hf_rms were not saved for M; computing them from the channel "
                   "fields and saving them to M_TI.msh."], notices
assert msh_field_names(volume) == {"TI_max", "hf_peak", "hf_rms"}

selected = Path(tempfile.mkdtemp()) / "M_TI.msh"
written_by_the_simulator(["TI_max", "hf_peak", "hf_rms"], selected)
produced, reference = mesh_io.read_msh(str(volume)), mesh_io.read_msh(str(selected))
for name in ("TI_max", "hf_peak", "hf_rms"):
    assert np.array_equal(produced.field[name].value, reference.field[name].value), name

e1, e2 = (c.field["E"].value for c in channels)
peak = np.maximum(np.linalg.norm(e1 + e2, axis=1), np.linalg.norm(e1 - e2, axis=1))
np.testing.assert_allclose(produced.field["hf_peak"].value, peak, rtol=1e-12)
np.testing.assert_allclose(produced.field["hf_rms"].value,
                           np.sqrt(((e1 ** 2).sum(axis=1) + (e2 ** 2).sum(axis=1)) / 2), rtol=1e-12)
print("OK", produced.elm.nr)
"""


def test_an_on_demand_field_equals_what_the_simulator_writes():
    pytest.importorskip("simnibs")
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True, timeout=600
    )
    if "No module named 'simnibs'" in proc.stderr:
        pytest.skip("skipping: needs the real SimNIBS (run in the image)")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().startswith("OK"), proc.stdout
