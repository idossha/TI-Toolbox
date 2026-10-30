"""A simulation scene shows its field mesh, coloured by the envelope it saved (2026-10-30).

What this pins
    Field NIfTIs are opt-in, so the simulation scene cannot rely on them: ``build_view``'s
    simulation kind adds the grey-matter field mesh ``<TI|mTI>/mesh/grey_<sim>_<TI|mTI>.msh``
    with ``mesh_field`` naming the field it opens on -- ``TI_max``, ``mTI_max`` for mTI, a
    carrier-only run's ``hf_peak`` -- read from the mesh's own headers, so the other saved fields
    are a field switch away in TetraVox. With no NIfTI to borrow a window from, the scene windows
    the mesh on its own element values (p95 to p99.9 of the non-zero ones, the field rule of the
    volume layers); and the catalog lists what the simulation saved from its field mesh too.

Where the expected numbers come from: ``numpy.percentile`` of the authored element values (the
reader is ``tit.tools.msh_fields``, checked against SimNIBS's binary output in
``tests/numerical/test_sim_fields_on_demand_real.py``).

Reproduce: ``.venv/bin/python -m pytest tests/test_viewspec_field_mesh.py -q -p no:cacheprovider``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tit import catalog, viewspec
from tit.paths import get_path_manager, reset_path_manager

SID = "ernie"


@pytest.fixture(autouse=True)
def _fresh():
    reset_path_manager()
    viewspec.clear_percentile_cache()
    yield
    reset_path_manager()


def write_msh(path: Path, data: dict[str, np.ndarray]) -> None:
    """A Gmsh 2.2 ASCII mesh of len(values) tetrahedra carrying *data* as element fields."""
    n = len(next(iter(data.values())))
    out = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$Nodes", "4"]
    out += [f"{i} {x} {y} {z}" for i, (x, y, z) in enumerate(np.eye(4)[:, :3] * 10, 1)]
    out += ["$EndNodes", "$Elements", str(n)]
    out += [f"{i} 4 2 2 2 1 2 3 4" for i in range(1, n + 1)]
    out += ["$EndElements"]
    for name, values in data.items():
        out += ["$ElementData", "1", f'"{name}"', "1", "0.0", "3", "0", "1", str(n)]
        out += [f"{i} {v:.17g}" for i, v in enumerate(values, 1)]
        out += ["$EndElementData"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")


VALUES = np.r_[
    np.zeros(20), np.linspace(0.01, 0.4, 400)
]  # 20 exact zeros outside the brain


def simulation(tmp_path: Path, name: str, mode: str, data: dict) -> Path:
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m(SID)).mkdir(parents=True)
    Path(pm.m2m(SID), "T1.nii.gz").write_bytes(b"t1")
    mesh_dir = Path(pm.simulation(SID, name)) / mode / "mesh"
    write_msh(mesh_dir / f"grey_{name}_{mode}.msh", data)
    write_msh(mesh_dir / f"{name}_{mode}.msh", data)
    return mesh_dir


def mesh_layers(name: str) -> tuple[list[dict], list[dict]]:
    spec = viewspec.build_view("simulation", subject=SID, simulation=name)
    assert spec is not None
    return (
        [layer for layer in spec["layers"] if layer["path"].endswith(".msh")],
        [layer for layer in spec["scene"]["layers"] if layer["kind"] == "mesh"],
    )


def test_a_simulation_without_niftis_shows_its_field_mesh_coloured_by_ti_max(
    tmp_path: Path,
) -> None:
    simulation(
        tmp_path,
        "M1",
        "TI",
        {"TI_max": VALUES, "hf_peak": 2 * VALUES, "hf_rms": VALUES},
    )
    spec_layers, scene_layers = mesh_layers("M1")
    assert [Path(la["path"]).name for la in spec_layers] == ["grey_M1_TI.msh"]
    assert spec_layers[0]["mesh_field"] == {"source": "elm", "name": "TI_max"}
    assert spec_layers[0]["visible"] is True
    (mesh,) = scene_layers
    assert mesh["visible"] is True and mesh["colorMode"] == "field"
    assert mesh["field"] == {"source": "elm", "name": "TI_max", "component": "mag"}
    lo, hi = np.percentile(VALUES[VALUES != 0], [95, 99.9])
    assert mesh["scale"] == {
        "kind": "linear",
        "lo": pytest.approx(lo),
        "hi": pytest.approx(hi),
    }
    assert mesh["threshold"]["lo"] == pytest.approx(lo)


def test_an_mti_simulation_opens_on_mti_max(tmp_path: Path) -> None:
    simulation(tmp_path, "M4", "mTI", {"mTI_max": VALUES, "hf_peak": VALUES})
    spec_layers, scene_layers = mesh_layers("M4")
    assert [Path(la["path"]).name for la in spec_layers] == ["grey_M4_mTI.msh"]
    assert scene_layers[0]["field"]["name"] == "mTI_max"


def test_a_carrier_only_run_opens_on_its_carrier_field(tmp_path: Path) -> None:
    simulation(tmp_path, "C0", "TI", {"hf_rms": VALUES, "hf_peak": 3 * VALUES})
    _, scene_layers = mesh_layers("C0")
    assert scene_layers[0]["field"]["name"] == "hf_peak"
    lo, hi = np.percentile(3 * VALUES[VALUES != 0], [95, 99.9])
    assert scene_layers[0]["scale"]["lo"] == pytest.approx(lo)
    assert scene_layers[0]["scale"]["hi"] == pytest.approx(hi)


def test_the_catalog_lists_the_fields_the_mesh_saved(tmp_path: Path) -> None:
    mesh_dir = simulation(
        tmp_path, "M1", "TI", {"TI_max": VALUES, "hf_peak": VALUES, "hf_rms": VALUES}
    )
    niftis = mesh_dir.parent / "niftis"
    niftis.mkdir()
    (niftis / "grey_M1_TI_subject_TI_avg.nii.gz").write_bytes(
        b"x"
    )  # one written on demand
    detail = catalog.simulation_detail(get_path_manager(), SID, "M1")
    assert detail["fields"] == ["TI_avg", "TI_max", "hf_peak", "hf_rms"]
    assert detail["carrier_only"] is False  # no run record says otherwise


def test_the_catalog_says_a_run_is_a_carrier_only_control(tmp_path: Path) -> None:
    import json

    mesh_dir = simulation(tmp_path, "C0", "TI", {"hf_peak": VALUES, "hf_rms": VALUES})
    record = mesh_dir.parents[1] / "documentation" / "config.json"
    record.parent.mkdir()
    record.write_text(json.dumps({"carrier_only": True}))
    detail = catalog.simulation_detail(get_path_manager(), SID, "C0")
    assert detail["carrier_only"] is True and detail["fields"] == ["hf_peak", "hf_rms"]
