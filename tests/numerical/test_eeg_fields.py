"""Independent small-array checks; no participant data or FEM reproduction."""

from __future__ import annotations
import numpy as np
import pytest


def test_carrier_metrics_manual_vectors():
    from tit.fields import carrier_metrics

    a = np.array([[3.0, 0, 0], [3, 0, 0], [3, 0, 0]])
    b = np.array([[2.0, 0, 0], [0, 4, 0], [-2, 0, 0]])
    normals = np.array([[1.0, 0, 0], [1, 0, 0], [1, 0, 0]])
    result = carrier_metrics([a, b], normals)
    np.testing.assert_allclose(result["hf_peak"], [5, 5, 5])
    np.testing.assert_allclose(result["hf_sar"], [13, 25, 13])
    np.testing.assert_allclose(result["carrier_sum"], [5, 7, 5])
    np.testing.assert_allclose(result["TI_normal"], [4, 0, 4])
    np.testing.assert_allclose(result["carrier_normal_sum"], [5, 3, 1])
    with pytest.raises(ValueError):
        carrier_metrics([a, b], normals * 2)
    with pytest.raises(ValueError):
        carrier_metrics([a, b * np.nan])


def test_nonlinear_scalar_precedes_surface_morph():
    from tit.fields import carrier_metrics
    from tit.source.fsaverage import _morph_split

    class Average:
        def resample(self, values):
            return np.array([np.mean(values)])

    a = np.array([[3.0, 0, 0], [-3, 0, 0], [1, 0, 0], [1, 0, 0]])
    b = np.array([[1.0, 0, 0], [-1, 0, 0], [2, 0, 0], [2, 0, 0]])
    native = carrier_metrics([a, b])["hf_peak"]
    actual = _morph_split(native, 2, 2, dict(lh=Average(), rh=Average()), ("lh", "rh"))
    np.testing.assert_allclose(actual, [4, 3])
    # Averaging left carrier vectors first would cancel both fields to zero.
    assert carrier_metrics([a[:2].mean(0), b[:2].mean(0)])["hf_peak"] == 0


def test_parcel_reduction_order_weights_missing_and_nans():
    from tit.atlas.surface import parcel_means

    labels = np.array([1, 1, 5, -1])
    values = np.array([[2.0, 8.0, 9.0, 100.0], [4.0, np.nan, 6.0, 100.0]])
    means, ids = parcel_means(values, labels, region_ids=np.array([5, 1, 3]))
    np.testing.assert_equal(ids, [5, 1, 3])
    np.testing.assert_allclose(
        means, [[9, 5, np.nan], [6, np.nan, np.nan]], equal_nan=True
    )
    weighted, _ = parcel_means(
        values, labels, weights=np.array([1.0, 3.0, 2.0, 1.0]), nan_policy="omit"
    )
    np.testing.assert_allclose(weighted, [[6.5, 9], [4, 6]])
    vector, _ = parcel_means(values[0], labels, weights=np.array([1.0, 3.0, 2.0, 1.0]))
    np.testing.assert_allclose(vector, [6.5, 9])
    with pytest.raises(ValueError):
        parcel_means(values, labels, nan_policy="raise")


def test_nearest_vertices_enforces_coordinate_tolerance():
    from tit.atlas.surface import nearest_vertex_ids

    reference = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
    np.testing.assert_array_equal(
        nearest_vertex_ids(reference, reference[[2, 0]], max_distance=0), [2, 0]
    )
    with pytest.raises(ValueError):
        nearest_vertex_ids(reference, [[8, 0, 0]], max_distance=0.1)


def test_array_cache_rejects_stale_partial_and_unsafe(tmp_path):
    from tit.source.cache import input_fingerprints, read_array_cache, write_array_cache

    source = tmp_path / "mesh"
    source.write_bytes(b"original")
    metadata = {"version": 1, "inputs": input_fingerprints([source])}
    cache = tmp_path / "fields.npz"
    write_array_cache(cache, {"x": np.arange(3)}, metadata)
    np.testing.assert_array_equal(
        read_array_cache(cache, metadata, ("x",))["x"], [0, 1, 2]
    )
    assert read_array_cache(cache, metadata, ("x", "missing")) is None
    source.write_bytes(b"modified")
    assert (
        read_array_cache(
            cache, {"version": 1, "inputs": input_fingerprints([source])}, ("x",)
        )
        is None
    )
    with pytest.raises(ValueError):
        write_array_cache(cache, {"x": np.array([{}], object)}, metadata)
    assert read_array_cache(cache, metadata, ("x",)) is not None
    cache.write_bytes(b"PK\x03\x04interrupted ZIP archive")
    assert read_array_cache(cache, metadata, ("x",)) is None


def test_study_projection_snapshot_parity(monkeypatch):
    """Optional unpublished study checkout: compare the saved projection scorer."""
    import ast
    import os
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    from tit.source import fsaverage as fs

    roots = os.environ.get("TIT_STUDY_CHECKOUTS", "").split(os.pathsep)
    roots = [Path(p) for p in roots if p]
    if not roots:
        pytest.skip(
            "set TIT_STUDY_CHECKOUTS to check v1.0-preliminary projection parity"
        )
    rng = np.random.default_rng(8)
    vector = {k: rng.normal(size=(7, 3)) for k in ("a", "b")}
    normal = rng.normal(size=(7, 3))
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    central = {}

    class Morph:
        def __init__(self, matrix):
            self.matrix = matrix

        def resample(self, value):
            return self.matrix @ value

    morph = {
        "lh": Morph(np.array([[0.5, 0.5, 0], [0, 0, 1.0]])),
        "rh": Morph(np.array([[0.5, 0.5, 0, 0], [0, 0, 0.5, 0.5]])),
    }
    for h, ids in [("lh", slice(0, 3)), ("rh", slice(3, 7))]:
        n = normal[ids]
        central[h] = SimpleNamespace(
            nodes=SimpleNamespace(nr=len(n)),
            nodes_normals=lambda n=n: SimpleNamespace(value=n),
        )
    subject = SimpleNamespace(subpath="m2m_fixture", hemispheres=("lh", "rh"))
    monkeypatch.setattr(
        fs, "_subject_geometry", lambda *a: (central, morph, subject.hemispheres)
    )
    monkeypatch.setattr(fs, "_load_carrier_mesh", lambda path: (path.name, None))
    monkeypatch.setattr(fs, "_interp_to_central", lambda mesh, *a: vector[mesh])
    monkeypatch.setitem(fs._FSAVG_NODES, 5, 4)

    def extract(source, name):
        tree = ast.parse(source)
        node = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        return compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            str(name),
            "exec",
        )

    for root in roots:
        path = "src/simulation/scripts/hf_project.py"
        old = subprocess.check_output(
            ["git", "show", f"v1.0-preliminary:{path}"], cwd=root, text=True
        )
        context = {
            "np": np,
            "Path": Path,
            "SubjectFiles": object,
            "config": SimpleNamespace(N_FSAVG5_NODES=4),
            "FSAVERAGE_SUBSAMPLING": 5,
            "mesh_io": SimpleNamespace(load_subject_surfaces=lambda *a: central),
            "cross_subject_map": lambda *a, **k: morph,
            "_surface_vector_field": lambda path, *a: {
                "lh": vector[str(path)][:3],
                "rh": vector[str(path)][3:],
            },
        }
        exec(extract(old, "_project_hf_fields"), context)
        expected = context["_project_hf_fields"](Path("a"), Path("b"), subject)
        current = {"Path": Path, "SubjectFiles": object, "FSAVERAGE_SUBSAMPLING": 5}
        exec(extract((root / path).read_text(), "_project_hf_fields"), current)
        actual = current["_project_hf_fields"](Path("a"), Path("b"), subject)
        assert actual.keys() == expected.keys()
        for key in expected:
            np.testing.assert_allclose(
                actual[key], expected[key], atol=1e-14, rtol=1e-13
            )


def test_projection_metadata_invalidates_runtime_change(tmp_path, monkeypatch):
    from importlib import metadata
    from types import SimpleNamespace
    from tit.source.fsaverage import _projection_metadata
    from tit.source.config import FsavgMapConfig

    pm = SimpleNamespace(m2m=lambda subject: tmp_path)
    cfg = FsavgMapConfig(fields=("hf_peak",))
    from tit.source import fsaverage as fs

    monkeypatch.setattr(fs, "_carrier_volume_meshes", lambda *a: ())
    monkeypatch.setattr(metadata, "version", lambda package: "1")
    before = _projection_metadata(pm, "fixture", "simulation", cfg)
    monkeypatch.setattr(
        metadata, "version", lambda package: "2" if package == "simnibs" else "1"
    )
    after = _projection_metadata(pm, "fixture", "simulation", cfg)
    assert before["inputs"] == after["inputs"]
    assert before != after
