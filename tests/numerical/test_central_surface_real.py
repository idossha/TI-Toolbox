"""The in-process central surface reproduces SimNIBS's msh2cortex mesh and the old TI_normal mesh.

Pins (2026-10-30, docs/dev/DECISIONS.md "one central surface mesh per run"): the simulator now
writes ``<sim>/<TI|mTI>/mesh/surfaces/<sim>_<TI|mTI>_central.msh`` itself
(:func:`tit.volume_fields.central_surface`) instead of running SimNIBS's surface overlays
(``map_to_surf``) and ``msh2cortex``. On a real run made by the previous pipeline, sub-ernie
``AF3_PO10_and_AF4_Oz`` in Dataset 000 (vn conductivity, written 2026-09-23 by
``map_to_surf`` + ``msh2cortex`` + ``BaseSimulation._write_ti_normal``), rebuilding the surface
from that run's own volume mesh and channel meshes gives

* the same nodes, in the same order, as ``TI/mesh/surfaces/<sim>_TI_central.msh`` (msh2cortex);
* ``TI_max`` equal to msh2cortex's ``TI_max`` node field;
* ``TI_normal`` equal to the old ``TI/mesh/<sim>_normal.msh`` (the envelope along the node normals
  of the channels' E as SimNIBS's surface overlays carried it, ``E_normal``).

Where the expected numbers come from: the files the old pipeline wrote (SimNIBS's own
``middle_gm_interpolation`` for both the overlays and ``msh2cortex``), never this code. Tolerance:
``atol = 1e-10`` V/m on fields of ~0.01-1 V/m; it absorbs only summation-order rounding of the
same interpolation (the investigator measured a worst case of 3e-14 V/m), so any change of
interpolation scheme, element set or normal convention fails it.

Gated: ``export TIT_DATASET_000=/path/to/Dataset000`` (read-only); skips with the reason otherwise.
Needs SimNIBS, so it runs in the image::

    docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox -e PYTHONPATH=/ti-toolbox -v /path/to/000:/data/000:ro \\
      -e TIT_DATASET_000=/data/000 idossha/ti-toolbox:v3.1.2 -lc \\
      'simnibs_python -m pytest tests/numerical/test_central_surface_real.py -q -p no:cacheprovider'

Deliberately elsewhere: the on-demand upgrade of an old run (tests/test_sim_fields_on_demand.py,
synthetic) and the simulator wiring (tests/test_sim_pipeline.py).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
_SIM = "AF3_PO10_and_AF4_Oz"
_RUN = Path(ROOT) / "derivatives" / "SimNIBS" / "sub-ernie" / "Simulations" / _SIM
pytestmark = pytest.mark.skipif(
    not ROOT or not (_RUN / "TI" / "mesh" / f"{_SIM}_normal.msh").is_file(),
    reason="skipping: TIT_DATASET_000 is unset or has no sub-ernie/AF3_PO10_and_AF4_Oz "
    "old-layout run (export TIT_DATASET_000=/path/to/Dataset000, read-only)",
)

#: Run in a fresh interpreter: the host conftest replaces SimNIBS with mocks in this process.
_SCRIPT = r"""
import sys
from pathlib import Path

import numpy as np
from simnibs import mesh_io

from tit.volume_fields import BRAIN_TAGS, central_surface

ATOL = 1e-10  # V/m: summation-order rounding only (measured 3e-14)
run, sim = Path(sys.argv[1]), sys.argv[2]
subject = run.parents[1]
volume = mesh_io.read_msh(str(run / "TI" / "mesh" / f"{sim}_TI.msh"))
e_fields = [
    mesh_io.read_msh(str(run / "high_Frequency" / "mesh" / f"ernie_TDCS_{k}_vn.msh"))
    .crop_mesh(tags=BRAIN_TAGS).field["E"].value
    for k in (1, 2)
]
surface = central_surface(volume, subject / "m2m_ernie", e_fields=e_fields)

old = mesh_io.read_msh(str(run / "TI" / "mesh" / "surfaces" / f"{sim}_TI_central.msh"))
assert surface.nodes.nr == old.nodes.nr > 100_000, (surface.nodes.nr, old.nodes.nr)
np.testing.assert_array_equal(surface.nodes.node_coord, old.nodes.node_coord)
np.testing.assert_array_equal(surface.elm.node_number_list, old.elm.node_number_list)
d_max = np.abs(surface.field["TI_max"].value - old.field["TI_max"].value).max()
np.testing.assert_allclose(surface.field["TI_max"].value, old.field["TI_max"].value,
                           rtol=0, atol=ATOL)

normal = mesh_io.read_msh(str(run / "TI" / "mesh" / f"{sim}_normal.msh"))
new, ref = np.asarray(surface.field["TI_normal"].value), np.asarray(normal.field["TI_normal"].value)
assert new.shape == ref.shape and np.isfinite(new).all() and ref.max() > 0
d_normal = np.abs(new - ref).max()
np.testing.assert_allclose(new, ref, rtol=0, atol=ATOL)
print(f"OK nodes={surface.nodes.nr} max|dTI_max|={d_max:.2e} max|dTI_normal|={d_normal:.2e}")
"""


def test_the_central_surface_is_msh2cortex_s_and_ti_normal_the_old_mesh_s() -> None:
    pytest.importorskip("simnibs")
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(_RUN), _SIM],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if "No module named 'simnibs'" in proc.stderr:
        pytest.skip("skipping: needs the real SimNIBS (run in the image)")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().startswith("OK"), proc.stdout
    print(proc.stdout)
