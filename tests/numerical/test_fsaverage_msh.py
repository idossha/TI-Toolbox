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
5. **Group outputs.** A surface correlation and a group comparison over synthetic subject
   projections (one planted patch) write ``surface_stats.msh`` whose ``cluster_id`` matches
   ``significant_clusters.csv`` and ``sig_mask``, whose group means equal the inputs' means,
   a ``null_distribution.csv`` of ``n_permutations`` rows, and a ``cluster_subject_values.csv``
   whose means equal the inputs averaged over each cluster; the nilearn renderer draws its
   PDFs from that ``.msh`` (Agg backend, no window).

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


_N_PERM = 40


def _surface_case(tmp: str, analysis: str) -> None:
    """Run one surface analysis on planted data and check every output against the inputs."""
    import csv
    import json

    import numpy as np
    from simnibs.mesh_tools import mesh_io

    from tit.constants import FSAVG_NODES
    from tit.paths import get_path_manager
    from tit.plotting.nilearn.surface import render_surface_stats_result
    from tit.source.fsaverage import read_fsaverage_fields, write_fsaverage_msh
    from tit.stats.config import CorrelationConfig, GroupComparisonConfig

    pm = get_path_manager(tmp)
    n = FSAVG_NODES[5]
    lh = mesh_io.load_fsaverage_template("central", 5)["lh"].nodes.node_coord
    patch = np.zeros(n, bool)
    patch[: n // 2] = np.linalg.norm(lh - lh[0], axis=1) < 20.0
    rng = np.random.default_rng(1)
    gains = np.arange(1.0, 11.0)
    inputs = {}
    for k, gain in enumerate(gains):
        sid = f"{k + 1:03d}"
        if analysis == "group_comparison":
            gain = 2.0 if k < 5 else 0.0
        inputs[sid] = 1.0 + gain * patch + 0.01 * rng.normal(size=n)
        write_fsaverage_msh(
            Path(pm.sim_fsaverage_fields(sid, "sim", 5)),
            {"TI_max": inputs[sid]},
            5,
            {"subject_id": sid, "simulation": "sim"},
        )
    ids = list(inputs)
    stack = np.column_stack([inputs[s] for s in ids])

    if analysis == "correlation":
        from tit.stats.surface import run_surface_correlation as run

        config = CorrelationConfig(
            analysis_name="surf",
            subjects=[
                CorrelationConfig.Subject(s, "sim", g) for s, g in zip(ids, gains)
            ],
            space=CorrelationConfig.AnalysisSpace.FSAVERAGE,
            n_permutations=_N_PERM,
            use_weights=False,
        )
        means = {"mean_field": stack.mean(axis=1)}
        values = {s: str(g) for s, g in zip(ids, gains)}
    else:
        from tit.stats.surface import run_surface_group_comparison as run

        config = GroupComparisonConfig(
            analysis_name="surf",
            subjects=[
                GroupComparisonConfig.Subject(s, "sim", int(k < 5))
                for k, s in enumerate(ids)
            ],
            space=GroupComparisonConfig.AnalysisSpace.FSAVERAGE,
            n_permutations=_N_PERM,
        )
        means = {
            "mean_responders": stack[:, :5].mean(axis=1),
            "mean_non_responders": stack[:, 5:].mean(axis=1),
        }
        values = {
            s: "Responders" if k < 5 else "Non-Responders" for k, s in enumerate(ids)
        }

    out = Path(run(config).output_dir)
    fields = read_fsaverage_fields(out / "surface_stats.msh")
    for name, mean in means.items():
        assert np.allclose(fields[name], mean), name
    cluster_id = fields["cluster_id"]
    with open(out / "significant_clusters.csv") as fh:
        clusters = list(csv.DictReader(fh))
    assert clusters, "the planted patch must come out significant"
    assert {int(c["id"]) for c in clusters} == set(np.unique(cluster_id)) - {0}
    for c in clusters:
        assert int(c["size"]) == int((cluster_id == int(c["id"])).sum())
    assert np.array_equal(fields["sig_mask"] > 0, cluster_id > 0)
    assert (cluster_id[patch] > 0).mean() > 0.9

    with open(out / "null_distribution.csv") as fh:
        assert len(list(csv.DictReader(fh))) == _N_PERM
    with open(out / "cluster_subject_values.csv") as fh:
        rows = list(csv.DictReader(fh))
    column = "response" if analysis == "correlation" else "group"
    assert len(rows) == len(ids) * len(clusters)
    for row in rows:
        want = inputs[row["subject_id"]][cluster_id == int(row["cluster_id"])].mean()
        assert abs(float(row["mean_field"]) - want) < 1e-9
        assert row[column] == values[row["subject_id"]]
    meta = json.loads((out / "surface_stats.json").read_text())
    assert meta["analysis_type"] == analysis and meta["n_permutations"] == _N_PERM
    assert meta["fsaverage_spacing"] == 5 and meta["field"] == "TI_max"

    pdfs = render_surface_stats_result(
        str(out / "surface_stats.msh"), str(out / "figs")
    )
    assert len(pdfs) == 2
    assert all(Path(pdf).stat().st_size > 1000 for pdf in pdfs)


def _check_surface_correlation_outputs(tmp: str) -> None:
    _surface_case(tmp, "correlation")


def _check_surface_group_outputs(tmp: str) -> None:
    _surface_case(tmp, "group_comparison")


# ── tests ───────────────────────────────────────────────────────────────────


def test_morph_output_index_is_the_template_vertex_index() -> None:
    _run("_check_vertex_order")


def test_written_msh_reads_back_as_the_projected_columns(tmp_path) -> None:
    _run("_check_layout_and_round_trip", str(tmp_path))


def test_gmsh_opens_it_with_every_field(tmp_path) -> None:
    _run("_check_gmsh_reads_it", str(tmp_path))


def test_simnibs_fsaverage_sphere_is_freesurfers() -> None:
    _run("_check_freesurfer_sphere")


def test_surface_correlation_writes_msh_and_tables_matching_the_inputs(
    tmp_path,
) -> None:
    _run("_check_surface_correlation_outputs", str(tmp_path))


def test_surface_group_comparison_writes_msh_and_tables_matching_the_inputs(
    tmp_path,
) -> None:
    _run("_check_surface_group_outputs", str(tmp_path))
