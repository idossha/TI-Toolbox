"""The fsaverage projection ``.msh``: node ``i`` is fsaverage vertex ``i``, lh then rh.

Pins (2026-09-30), each against real SimNIBS 4.6 in a subprocess (``tests/conftest.py``
mocks ``simnibs`` in-process):

1. **Vertex order.** ``cross_subject_map(..., subsampling_to=s)`` resamples onto SimNIBS's
   fsaverage<s> *sphere*; the writer joins the fsaverage<s> *central* template. The two share
   their face arrays (one numbering), and a linear function of the sphere-7 coordinates morphed
   fsaverage7 -> fsaverage<s> equals the same function of the sphere-<s> coordinates, so the
   morph's output index is the template's vertex index.
2. **Layout.** The written mesh has ``FSAVG_NODES[s] // 2`` nodes per hemisphere, lh first
   (its first half is the lh template's coordinates), and the vendored
   ``resources/fsaverage/<s>`` surfaces the stats adjacency is built from are that template.
3. **Round trip.** ``write_fsaverage_msh`` -> ``load_group_surface_data`` returns the
   synthetic columns exactly, with the ``.opt`` view and the ``.json`` provenance beside it;
   Gmsh's own reader (not SimNIBS) opens the file and sees every field node-for-node.
4. **Independent source.** FreeSurfer's own ``fsaverage/surf/{lh,rh}.sphere`` (MNE's
   fsaverage data, read with nibabel) is SimNIBS's sphere-7, and its first 10242 / 40962
   vertices are sphere-5 / sphere-6 -- the icosahedral prefix FreeSurfer's fsaverage5/6 are
   built on. Skips, with a reason, when that data is not on the machine.

Expected values come from the synthetic inputs and FreeSurfer's files, never the writer.
Reproduce: ``simnibs_python -m pytest tests/numerical/test_fsaverage_msh.py -q``
(container: ``docker exec -w /ti-toolbox <c> simnibs_python -m pytest ...``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _run(check: str, *args: str) -> None:
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True
    )
    if probe.returncode:
        pytest.skip("Real SimNIBS is required; run under simnibs_python")
    code = (
        "import runpy,sys; " "runpy.run_path(sys.argv[1])[sys.argv[2]](*sys.argv[3:])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, __file__, check, *args],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=_REPO,
        env={**os.environ, "PYTHONPATH": str(_REPO)},
    )
    if result.returncode == 3:
        pytest.skip(result.stdout.strip() or "skipped by the check")
    assert result.returncode == 0, result.stdout + result.stderr


# ── checks (run inside the subprocess) ──────────────────────────────────────


def _check_vertex_order() -> None:
    import nibabel as nib
    import numpy as np
    from simnibs.utils.file_finder import get_fsaverage_template
    from simnibs.utils.transformations import cross_subject_map

    coef = np.array([1.0, 2.0, -3.0])
    for spacing in (5, 6):
        morph = cross_subject_map(
            "fsaverage", "fsaverage", subsampling_from=7, subsampling_to=spacing
        )
        for hemi in ("lh", "rh"):
            sphere = nib.load(get_fsaverage_template(hemi, "sphere", spacing))
            central = nib.load(get_fsaverage_template(hemi, "central", spacing))
            assert np.array_equal(sphere.darrays[1].data, central.darrays[1].data)
            s7 = nib.load(get_fsaverage_template(hemi, "sphere", 7)).darrays[0].data
            got = np.asarray(morph[hemi].resample(s7.astype(float) @ coef))
            want = sphere.darrays[0].data.astype(float) @ coef
            assert np.abs(got - want).max() < 1e-9, (spacing, hemi)
    for hemi in ("lh", "rh"):  # spacing 7 is the identity morph; its faces still agree
        assert np.array_equal(
            nib.load(get_fsaverage_template(hemi, "sphere", 7)).darrays[1].data,
            nib.load(get_fsaverage_template(hemi, "central", 7)).darrays[1].data,
        )


def _check_layout_and_round_trip(tmp: str) -> None:
    import json

    import nibabel as nib
    import numpy as np
    from simnibs.mesh_tools import mesh_io

    from tit.constants import FSAVG_NODES
    from tit.paths import get_path_manager
    from tit.source.fsaverage import write_fsaverage_msh
    from tit.stats.surface import load_group_surface_data

    pm = get_path_manager(tmp)
    for spacing in (5, 6, 7):
        template = mesh_io.load_fsaverage_template("central", spacing)
        n = FSAVG_NODES[spacing]
        assert template["lh"].nodes.nr == template["rh"].nodes.nr == n // 2
        for hemi in ("lh", "rh"):
            vendored = nib.load(
                _REPO / f"resources/fsaverage/{spacing}/{hemi}.central.gii"
            )
            assert np.allclose(
                vendored.darrays[0].data, template[hemi].nodes.node_coord
            )
            assert np.array_equal(
                vendored.darrays[1].data + 1, template[hemi].elm.node_number_list[:, :3]
            )

    spacing, n = 5, FSAVG_NODES[5]
    rng = np.random.default_rng(0)
    columns = {sid: rng.normal(size=n) for sid in ("001", "002")}
    for sid, values in columns.items():
        path = Path(pm.sim_fsaverage_fields(sid, "sim", spacing))
        maps = {"TI_max": values, "hf_sar": -values}
        write_fsaverage_msh(
            path,
            maps,
            spacing,
            {"subject_id": sid, "simulation": "sim", "carrier_only": False},
        )
        assert Path(f"{path}.opt").is_file()
        assert json.loads(path.with_suffix(".json").read_text()) == {
            "subject_id": sid,
            "simulation": "sim",
            "carrier_only": False,
            "fields": ["TI_max", "hf_sar"],
        }
        mesh = mesh_io.read_msh(str(path))
        lh = mesh_io.load_fsaverage_template("central", spacing)["lh"]
        assert np.allclose(mesh.nodes.node_coord[: n // 2], lh.nodes.node_coord)
        assert set(mesh.field) == {"TI_max", "hf_sar"}

    data, ids = load_group_surface_data(
        [("001", "sim"), ("002", "sim")], "TI_max", spacing
    )
    assert ids == ["001", "002"]
    assert np.array_equal(data, np.column_stack([columns["001"], columns["002"]]))
    data, _ = load_group_surface_data([("001", "sim")], "hf_sar", spacing)
    assert np.array_equal(data[:, 0], -columns["001"])


def _check_gmsh_reads_it(tmp: str) -> None:
    """Gmsh -- the viewer SimNIBS's own ``.opt`` targets, and a reader that is not SimNIBS."""
    import numpy as np

    from tit.constants import FSAVG_NODES
    from tit.source.fsaverage import write_fsaverage_msh

    try:
        import gmsh
    except ImportError:
        print("skipping: the gmsh Python module is not importable here")
        sys.exit(3)
    n = FSAVG_NODES[5]
    maps = {"TI_max": np.linspace(0.0, 1.0, n), "TI_normal": np.linspace(-1.0, 1.0, n)}
    path = Path(tmp) / "sub-001_sim-sim_space-fsaverage5_fields.msh"
    write_fsaverage_msh(path, maps, 5, {"subject_id": "001", "simulation": "sim"})
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(path))
        seen = {}
        for tag in gmsh.view.getTags():
            name = gmsh.option.getString(f"View[{gmsh.view.getIndex(tag)}].Name")
            kind, nodes, data, _, _ = gmsh.view.getModelData(tag, 0)
            assert kind == "NodeData", kind
            values = np.empty(n)
            values[np.asarray(nodes) - 1] = np.asarray(data).ravel()
            seen[name] = values
    finally:
        gmsh.finalize()
    assert set(seen) == set(maps)
    for name, values in maps.items():
        assert np.allclose(seen[name], values), name


def _check_freesurfer_sphere() -> None:
    import nibabel as nib
    import numpy as np
    from simnibs.utils.file_finder import get_fsaverage_template

    root = Path(os.environ.get("MNE_DATA", Path.home() / "mne_data"))
    surf = root / "MNE-fsaverage-data" / "fsaverage" / "surf"
    if not (surf / "lh.sphere").is_file():
        print(f"skipping: FreeSurfer fsaverage sphere not found under {surf}")
        sys.exit(3)
    for hemi in ("lh", "rh"):
        fs, _ = nib.freesurfer.read_geometry(str(surf / f"{hemi}.sphere"))
        for spacing in (5, 6, 7):
            s = (
                nib.load(get_fsaverage_template(hemi, "sphere", spacing))
                .darrays[0]
                .data
            )
            assert np.abs(fs[: len(s)] - s).max() < 1e-4, (hemi, spacing)


# ── tests ───────────────────────────────────────────────────────────────────


def test_morph_output_index_is_the_template_vertex_index() -> None:
    _run("_check_vertex_order")


def test_written_msh_reads_back_as_the_projected_columns(tmp_path) -> None:
    _run("_check_layout_and_round_trip", str(tmp_path))


def test_gmsh_opens_it_with_every_field(tmp_path) -> None:
    _run("_check_gmsh_reads_it", str(tmp_path))


def test_simnibs_fsaverage_sphere_is_freesurfers() -> None:
    _run("_check_freesurfer_sphere")
