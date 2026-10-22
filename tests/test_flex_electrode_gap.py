"""``min_electrode_distance`` is a gap between sampled skin nodes, not between electrode edges.

What this pins (audit_flex, package p08, 2026-10-22): SimNIBS's ``check_electrode_distance`` --
in the integration TI-Toolbox actually runs (``resources/map-electrodes/tes_flex_optimization.py``,
loaded by ``tit.opt.flex.runtime.integration_module``) -- refuses a placement when any skin-mesh
node under one electrode lies within ``min_electrode_distance`` of a node under another. Nodes
sit inside each footprint, so the physical gap between two discs (centre distance minus both
radii) may be smaller than the setting: on Dataset 000 a real ernie run placed two 8 mm discs of
different channels 9.75 mm apart, a 1.75 mm gap, with the 5 mm default. The decision taken here is
to state those semantics (FlexConfig's docstring and the Optimizer's "Min distance" help) rather
than to reject candidates after SimNIBS scored them, which would change what the optimiser
returns; this test proves the stated semantics against the real function.

How: a flat synthetic skin, nodes on a 2 mm grid; four disc electrodes (radius 4 mm) placed by
``get_node_mask_spherical_electrode`` (which returns each footprint and its 4x4 ``posmat``); the
first two, of different channels, ``d`` mm apart, the other two far away. Expected verdicts are
computed independently here with numpy: the node gap is the minimum distance between the two
footprints' nodes, the edge gap ``|t1 - t2| - 2 r`` from the posmats' translations. SimNIBS's
verdict must equal ``node gap > min distance`` for every ``d``, and differ from the edge-gap rule
for at least one ``d`` (here 10 and 12 mm: edge gaps 2 and 4 mm pass a 5 mm setting).

Two legs run the same placements and the same assertions. The host leg executes the two shipped
functions' own source, cut out of the integration file with ``ast`` (both use numpy only), so the
semantics are pinned on every host run; it fails if either function is renamed or starts to need
more than numpy. The container leg loads the whole integration through ``integration_module()``
in a subprocess that sees the real SimNIBS, not the host suite's mocks:
``simnibs_python -m pytest tests/test_flex_electrode_gap.py -q`` (on a host it skips).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# The placements, run against `module` (anything with SimNIBS's two functions); leaves `result`.
_PLACEMENTS = r"""
spacing, radius, min_distance = 2.0, 4.0, 5.0
axis = np.arange(-40.0, 260.0 + spacing / 2, spacing)
gx, gy = np.meshgrid(axis, np.arange(-20.0, 20.0 + spacing / 2, spacing))
skin = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])

rows = []
for d in (8.0, 10.0, 12.0, 14.0, 16.0):
    centres = [np.array(c) for c in ([0.0, 0, 0], [d, 0, 0], [120.0, 0, 0], [240.0, 0, 0])]
    masks, posmats = zip(*(module.get_node_mask_spherical_electrode(skin, c, radius) for c in centres))
    nodes = [skin[m] for m in masks]
    # channel 0: arrays 0 and 1 (electrodes 0 and 2); channel 1: arrays 0 and 1 (1 and 3) --
    # so the two close discs belong to different channels, as in the audited ernie run.
    order = [nodes[0], nodes[2], nodes[1], nodes[3]]
    valid = [[object(), object()], [object(), object()]]
    verdict, _ = module.check_electrode_distance(order, valid, [2, 2], 2, min_distance)
    rows.append({
        "d": d,
        "simnibs_valid": verdict is True,
        "nodes_a": nodes[0].tolist(),
        "nodes_b": nodes[1].tolist(),
        "t_a": np.asarray(posmats[0])[:3, 3].tolist(),
        "t_b": np.asarray(posmats[1])[:3, 3].tolist(),
        "posmat_shape": list(np.asarray(posmats[0]).shape),
    })
result = {"radius": radius, "min_distance": min_distance, "rows": rows}
"""

_SCRIPT = (
    "import json\n"
    "import numpy as np\n"
    "from tit.opt.flex.runtime import integration_module\n"
    "module = integration_module()\n" + _PLACEMENTS + "print(json.dumps(result))\n"
)

_SHIPPED = ("get_node_mask_spherical_electrode", "check_electrode_distance")


def _run_on_the_shipped_source() -> dict:
    """The placements against the two functions' source in the shipped integration file."""
    import numpy as np

    from tit.opt.flex.runtime import _SOURCE

    tree = ast.parse(_SOURCE.read_text())
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    missing = [name for name in _SHIPPED if name not in defs]
    assert not missing, f"{_SOURCE.name} no longer defines {missing}"
    namespace: dict = {"np": np}
    exec(  # noqa: S102 - the repository's own file, the code under test
        compile(
            ast.Module(body=[defs[n] for n in _SHIPPED], type_ignores=[]),
            str(_SOURCE),
            "exec",
        ),
        namespace,
    )
    module = SimpleNamespace(**{name: namespace[name] for name in _SHIPPED})
    scope: dict = {"np": np, "module": module}
    exec(_PLACEMENTS, scope)  # noqa: S102
    return scope["result"]


def _run_in_real_simnibs() -> dict:
    root = Path(__file__).resolve().parents[1]
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        print("skipping: real SimNIBS is not importable on this interpreter")
        pytest.skip(
            "real SimNIBS unavailable; run with simnibs_python in the image "
            "(idossha/ti-toolbox)"
        )
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_shipped_check_measures_min_distance_between_footprint_nodes_on_the_host():
    _assert_node_gap_semantics(_run_on_the_shipped_source())


def test_simnibs_min_distance_is_measured_between_footprint_nodes():
    _assert_node_gap_semantics(_run_in_real_simnibs())


def _assert_node_gap_semantics(data: dict) -> None:
    import numpy as np

    radius, min_distance = data["radius"], data["min_distance"]
    assert len(data["rows"]) == 5, "distances to check"
    edge_rule_disagrees = []
    for row in data["rows"]:
        assert row["posmat_shape"] == [4, 4]
        a, b = np.asarray(row["nodes_a"]), np.asarray(row["nodes_b"])
        assert len(a) and len(b), f"d={row['d']}: a footprint without skin nodes"
        node_gap = float(np.min(np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)))
        edge_gap = (
            float(np.linalg.norm(np.subtract(row["t_a"], row["t_b"]))) - 2 * radius
        )
        assert row["simnibs_valid"] is (
            node_gap > min_distance
        ), f"d={row['d']}: SimNIBS said {row['simnibs_valid']}, node gap {node_gap}"
        if row["simnibs_valid"] is not (edge_gap >= min_distance):
            edge_rule_disagrees.append((row["d"], edge_gap))
    # The documented discrepancy: placements SimNIBS accepts with an edge gap below the setting.
    assert [d for d, _ in edge_rule_disagrees] == [10.0, 12.0]
    assert all(gap < min_distance for _, gap in edge_rule_disagrees)
