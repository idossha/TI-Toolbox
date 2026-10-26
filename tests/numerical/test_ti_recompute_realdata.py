"""The stored TI_max of a real simulation is the envelope of its stored carriers, and the carriers ran at the configured currents.

Pins (2026-10-22, package p25), on Dataset 000 read-only, no FEM:

* **Recompute (image, SimNIBS mesh_io)**: for sub-LA ``L_Insula`` (the smallest head, two 356 MB
  carrier meshes) the carrier meshes ``high_Frequency/mesh/LA_TDCS_{1,2}_scalar.msh`` cropped to
  ``BRAIN_TISSUE_TAG_RANGES`` (every head tissue below tag 100 and its surface, electrodes
  removed: 5.0 M elements) have exactly the elements and tags of the stored
  ``TI/mesh/L_Insula_TI.msh``, and ``|tit.calc.get_TI_vectors([E1, E2])|`` (the Hirata 2024
  closed form) equals the stored ``TI_max`` that SimNIBS's ``TI.get_maxTI`` (Grossman 2017
  preprocess-then-branch form) wrote, to ``rtol 1e-4``: two independent implementations of one
  formula on every one of those elements. On the same fields: ``TI_max <= 2 min(|E1|, |E2|)``,
  ``TI_max <= hf_peak`` and ``hf_sar <= hf_peak^2 <= 2 hf_sar`` (derivations in
  ``tests/test_field_physics_invariants.py``). No Dataset 000 simulation stores hf_peak/hf_sar,
  so those are computed here from the stored carriers.
* **What ran (host)**: every simulation's newest SimNIBS log (``documentation/simnibs_simulation_*.log``)
  prints ``Currents (A): [I, -I]`` once per pair, and ``I * 1000`` is the pair's
  ``config.json`` intensity (mA): an independent record of the dose that ran.

Gated: ``export TIT_DATASET_000=/path/to/Dataset000`` (read-only; mtimes of the files read are
compared before and after); skips with the reason otherwise. The recompute needs SimNIBS::

    docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox -v /path/to/000:/data/000:ro -e TIT_DATASET_000=/data/000 \\
      idossha/ti-toolbox:v3.1.1 -lc \\
      'simnibs_python -m pytest tests/numerical/test_ti_recompute_realdata.py -q -p no:cacheprovider'
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
_SIMNIBS = Path(ROOT) / "derivatives" / "SimNIBS"
real_data = pytest.mark.skipif(
    not ROOT or not _SIMNIBS.is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS "
    "(export TIT_DATASET_000=/path/to/Dataset000, read-only)",
)

#: The smallest real head in Dataset 000 (2 x 356 MB carrier meshes).
SUBJECT, SIMULATION = "LA", "L_Insula"
#: The two implementations differ in operation order only; float64 round-off is ~1e-12.
RTOL = 1e-4
#: Below this the envelope is numerically zero (V/m): relative error is meaningless there.
ATOL = 1e-9
_CURRENTS = re.compile(r"Currents \(A\): (\[[^\]]*\])")


def _mtimes(paths: list[Path]) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in paths}


@pytest.mark.host_numerical
@real_data
def test_every_simulation_log_records_the_configured_currents():
    configs = sorted(_SIMNIBS.glob("sub-*/Simulations/*/documentation/config.json"))
    assert configs, "has no simulations to check"
    logs = [sorted(c.parent.glob("simnibs_simulation_*.log"))[-1] for c in configs]
    before = _mtimes(configs + logs)
    for config_path, log in zip(configs, logs):
        config = json.loads(config_path.read_text())
        n_pairs = len(config["electrode_pairs"])
        ran = [
            ast.literal_eval(m)
            for m in _CURRENTS.findall(log.read_text(errors="replace"))
        ]
        assert len(ran) == n_pairs, (log, ran)
        for (plus, minus), mA in zip(ran, config["intensities"][:n_pairs]):
            assert plus == -minus, (log, plus, minus)
            assert plus * 1000 == pytest.approx(float(mA), rel=1e-12), (log, plus, mA)
    assert _mtimes(configs + logs) == before


@pytest.fixture
def mesh_io():
    """The real ``simnibs.mesh_tools.mesh_io`` in place of ``tests/conftest.py``'s ``simnibs``
    mock (which would hand back empty fields); skips without SimNIBS."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        module = importlib.import_module("simnibs.mesh_tools.mesh_io")
    except ImportError:
        sys.modules.update(saved)
        pytest.skip("skipping: real SimNIBS is unavailable; run in the toolbox image")
    yield module
    for k in [k for k in sys.modules if k.split(".")[0] == "simnibs"]:
        del sys.modules[k]
    sys.modules.update(saved)


@real_data
def test_the_stored_envelope_is_the_envelope_of_the_stored_carriers(mesh_io):
    from tit import constants as const
    from tit import roi_confirmation
    from tit.calc import get_TI_vectors
    from tit.fields import hf_peak, hf_sar

    sim = _SIMNIBS / f"sub-{SUBJECT}" / "Simulations" / SIMULATION
    carriers = [
        sim / "high_Frequency" / "mesh" / f"{SUBJECT}_TDCS_{k}_scalar.msh"
        for k in (1, 2)
    ]
    stored = sim / "TI" / "mesh" / f"{SIMULATION}_TI.msh"
    if not all(p.is_file() for p in [*carriers, stored]):
        pytest.skip(f"skipping: {sim} lacks its carrier or TI meshes")
    before = _mtimes([*carriers, stored])
    keep = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])

    fields, tags = [], []
    for path in carriers:
        mesh = mesh_io.read_msh(str(path)).crop_mesh(tags=keep)
        fields.append(np.asarray(mesh.field["E"].value, dtype=np.float64))
        tags.append(np.asarray(mesh.elm.tag1))
        del mesh
    ti_mesh = mesh_io.read_msh(str(stored))
    ti_stored = np.asarray(ti_mesh.field["TI_max"].value, dtype=np.float64)
    ti_tags = np.asarray(ti_mesh.elm.tag1)
    del ti_mesh

    e1, e2 = fields
    assert e1.shape == e2.shape and e1.shape[1] == 3
    assert len(ti_stored) == len(e1) > 100_000, (len(ti_stored), len(e1))
    assert np.array_equal(tags[0], ti_tags) and np.array_equal(tags[1], ti_tags)

    ours = np.linalg.norm(get_TI_vectors([e1, e2]), axis=1)
    np.testing.assert_allclose(ours, ti_stored, rtol=RTOL, atol=ATOL)

    n1, n2 = np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1)
    assert np.all(ti_stored <= 2 * np.minimum(n1, n2) + ATOL)
    peak, sar = hf_peak(e1, e2), hf_sar(e1, e2)
    assert np.all(ti_stored <= peak + ATOL)
    assert np.all(sar <= peak**2 * (1 + 1e-12) + ATOL)
    assert np.all(peak**2 <= 2 * sar * (1 + 1e-12) + ATOL)
    # Not a field of zeros: at 1 mA per pair the grey-matter (tag 2) envelope's 99.9th
    # percentile is 0.01-1 V/m (the scalp under the electrodes reaches several V/m).
    grey = ti_stored[ti_tags == roi_confirmation.GM_TISSUE_LABEL]
    assert grey.size > 100_000
    assert 0.01 <= float(np.percentile(grey, 99.9)) <= 1.0
    assert _mtimes([*carriers, stored]) == before
