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
  list, ``TI_max``'s values equal to what ``mesh_io.read_msh`` reads, and with ``tags`` the values of
  the elements of one tissue tag only.

The central surface (needs an m2m's central surfaces) is stubbed; it is
tests/numerical/test_central_surface_real.py.

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

from tit.paths import get_path_manager

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
read_back = mesh_io.read_msh(str(volume))
assert np.array_equal(msh_element_field(volume, "TI_max"), read_back.field["TI_max"].value)
# The binary element-tag read (the Viewer's tissue window): one tag's values, as SimNIBS tags them.
tag = int(read_back.elm.tag1[0])
assert np.array_equal(msh_element_field(volume, "TI_max", tags=[tag]),
                      read_back.field["TI_max"].value[read_back.elm.tag1 == tag])
assert 0 < (read_back.elm.tag1 == tag).sum() < read_back.elm.nr

# sphere3 has no m2m central surfaces: the surface is the volume itself here (its own numbers
# are tests/numerical/test_central_surface_real.py's).
with patch.object(fields, "central_surface", lambda volume, m2m, e_fields=None: volume):
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
