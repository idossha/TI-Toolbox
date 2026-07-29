"""Tests for tit/opt/montage_eval.py -- FEM-based montage evaluator.

``tit.opt.montage_eval`` resolves all heavy dependencies (simnibs,
nibabel, scipy) via lazy in-function imports (mirroring
``tit/opt/leadfield.py`` / ``tit/opt/flex/builder.py``), so patching the
shared mocked modules installed into ``sys.modules`` by ``conftest.py``
reaches the real call sites -- no risk of the "patch a fresh reimport of a
mocked submodule" trap documented for module-level
``from simnibs.utils import TI_utils as TI``-style bindings (see
``tests/test_opt_engine.py``'s ``ti_mocks`` fixture docstring).
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.calc import mti_modulation_depth
from tit.opt import montage_eval as me

# ---------------------------------------------------------------------------
# Fake mesh helper
# ---------------------------------------------------------------------------


def _fake_mesh(tags, bary, vol, e_field):
    """Lightweight stand-in for a SimNIBS ``Msh`` -- a plain object exposing
    just the surface ``montage_eval`` touches (``.elm.tag1``, ``.field``
    dict-style access, ``.elements_baricenters()``,
    ``.elements_volumes_and_areas()``). A real dict for ``.field`` lets
    production-style ``mesh.field["E"]`` item access work without fighting
    ``MagicMock``'s ``__getitem__`` semantics.
    """
    return SimpleNamespace(
        elm=SimpleNamespace(tag1=np.asarray(tags)),
        field={"E": SimpleNamespace(value=np.asarray(e_field, dtype=float))},
        elements_baricenters=lambda: SimpleNamespace(
            value=np.asarray(bary, dtype=float)
        ),
        elements_volumes_and_areas=lambda: SimpleNamespace(
            value=np.asarray(vol, dtype=float)
        ),
    )


# ---------------------------------------------------------------------------
# _element_volumes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestElementVolumes:
    def test_1d_passthrough(self):
        mesh = _fake_mesh([2], [[0, 0, 0]], [5.0], [[1, 0, 0]])
        result = me._element_volumes(mesh)
        np.testing.assert_array_equal(result, [5.0])

    def test_2d_takes_first_column(self):
        mesh = SimpleNamespace(
            elements_volumes_and_areas=lambda: SimpleNamespace(
                value=np.array([[1.0, 99.0], [2.0, 99.0]])
            )
        )
        result = me._element_volumes(mesh)
        np.testing.assert_array_equal(result, [1.0, 2.0])


# ---------------------------------------------------------------------------
# _half_max_spread_cm
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHalfMaxSpreadCm:
    def test_known_volume_gives_known_radius(self):
        # A single element with volume 4/3*pi*1000 mm^3 (1 cm radius sphere
        # equivalent), envelope exactly at the threshold -> included.
        vol_mm3 = 4.0 / 3.0 * np.pi * 1000.0
        gm_env = np.array([1.0])
        gm_vol = np.array([vol_mm3])
        r_cm = me._half_max_spread_cm(gm_env, gm_vol, roi_max=2.0)  # threshold=1.0
        assert r_cm == pytest.approx(1.0, rel=1e-6)

    def test_below_threshold_excluded(self):
        gm_env = np.array([0.1, 0.1])
        gm_vol = np.array([1000.0, 1000.0])
        r_cm = me._half_max_spread_cm(gm_env, gm_vol, roi_max=10.0)  # threshold=5.0
        assert r_cm == 0.0

    def test_zero_roi_max_returns_zero(self):
        assert me._half_max_spread_cm(np.array([1.0]), np.array([1.0]), 0.0) == 0.0

    def test_mixed_above_below_threshold(self):
        gm_env = np.array([5.0, 1.0])  # threshold = 2.5
        gm_vol = np.array([100.0, 900.0])
        r_cm = me._half_max_spread_cm(gm_env, gm_vol, roi_max=10.0)
        expected_radius_mm = (3.0 * 100.0 / (4.0 * np.pi)) ** (1.0 / 3.0)
        assert r_cm == pytest.approx(expected_radius_mm / 10.0, rel=1e-9)


# ---------------------------------------------------------------------------
# _compute_metrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeMetrics:
    def _ref_mesh(self):
        # 5 elements: 4 GM (tag 2), 1 WM (tag 1). ROI = first 2 GM elements.
        tags = [2, 2, 2, 2, 1]
        bary = [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0]]
        vol = [10.0, 20.0, 30.0, 40.0, 50.0]
        return tags, bary, vol

    def test_metrics_match_hand_computation(self):
        tags, bary, vol = self._ref_mesh()
        rng = np.random.default_rng(0)
        e1 = rng.normal(size=(5, 3))
        e2 = rng.normal(size=(5, 3))
        mesh = _fake_mesh(tags, bary, vol, e1)  # e_field arg unused by ref_mesh path

        roi_mask_fn = lambda b: np.array([True, True, False, False])  # noqa: E731

        result = me._compute_metrics([e1, e2], mesh, roi_mask_fn)

        envelope = mti_modulation_depth([e1, e2])["md"]
        carrier = 0.5 * (np.sum(e1 * e1, axis=1) + np.sum(e2 * e2, axis=1))

        gm_idx = [0, 1, 2, 3]  # tag == 2
        gm_env = envelope[gm_idx]
        gm_vol = np.array(vol)[gm_idx]
        gm_carrier = carrier[gm_idx]

        roi_env = gm_env[[0, 1]]
        roi_vol = gm_vol[[0, 1]]

        expected_roi_mean = float(np.average(roi_env, weights=roi_vol))
        expected_gm_mean = float(np.average(gm_env, weights=gm_vol))

        assert result["roi_mean_Vm"] == pytest.approx(expected_roi_mean)
        assert result["gm_mean_Vm"] == pytest.approx(expected_gm_mean)
        assert result["focality_roi_over_gm"] == pytest.approx(
            expected_roi_mean / expected_gm_mean
        )
        assert result["roi_max_Vm"] == pytest.approx(float(np.max(roi_env)))
        assert result["roi_p999_Vm"] == pytest.approx(
            float(np.percentile(roi_env, 99.9))
        )
        assert result["carrier_rms_gm_Vm"] == pytest.approx(
            float(np.sqrt(np.average(gm_carrier, weights=gm_vol)))
        )
        assert result["carrier_peak_gm_Vm"] == pytest.approx(
            float(np.sqrt(np.max(gm_carrier)))
        )
        assert result["n_roi_elements"] == 2
        assert result["n_gm_elements"] == 4
        assert result["focality_cm"] >= 0.0

    def test_wm_elements_excluded_from_gm_metrics(self):
        tags = [2, 1]  # one GM, one WM
        bary = [[0, 0, 0], [1, 0, 0]]
        vol = [10.0, 999999.0]  # huge WM volume -- would dominate if not excluded
        e1 = np.array([[1.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
        e2 = np.array([[1.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
        mesh = _fake_mesh(tags, bary, vol, e1)

        roi_mask_fn = lambda b: np.array([True])  # noqa: E731 -- only the GM element
        result = me._compute_metrics([e1, e2], mesh, roi_mask_fn)

        assert result["n_gm_elements"] == 1
        # Grossman K=1 exact form: MD = 2*min(|E1|,|E2|) for co-aligned fields
        assert result["gm_mean_Vm"] == pytest.approx(2.0)

    def test_zero_gm_mean_gives_zero_focality(self):
        tags = [2, 2]
        bary = [[0, 0, 0], [1, 0, 0]]
        vol = [1.0, 1.0]
        zeros = np.zeros((2, 3))
        mesh = _fake_mesh(tags, bary, vol, zeros)

        roi_mask_fn = lambda b: np.array([True, False])  # noqa: E731
        result = me._compute_metrics([zeros, zeros], mesh, roi_mask_fn)

        assert result["gm_mean_Vm"] == 0.0
        assert result["focality_roi_over_gm"] == 0.0

    def test_empty_roi_raises(self):
        tags, bary, vol = self._ref_mesh()
        e1 = np.ones((5, 3))
        e2 = np.ones((5, 3))
        mesh = _fake_mesh(tags, bary, vol, e1)

        roi_mask_fn = lambda b: np.zeros(len(b), dtype=bool)  # noqa: E731
        with pytest.raises(ValueError, match="0 elements"):
            me._compute_metrics([e1, e2], mesh, roi_mask_fn)


# ---------------------------------------------------------------------------
# _align_channel_fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAlignChannelFields:
    def test_matching_tags_combine_directly(self):
        tags = [2, 2, 1]
        bary = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
        vol = [1.0, 1.0, 1.0]
        e1 = np.array([[1.0, 0, 0], [2.0, 0, 0], [3.0, 0, 0]])
        e2 = np.array([[4.0, 0, 0], [5.0, 0, 0], [6.0, 0, 0]])
        m1 = _fake_mesh(tags, bary, vol, e1)
        m2 = _fake_mesh(tags, bary, vol, e2)

        e_fields, ref = me._align_channel_fields([m1, m2])

        np.testing.assert_array_equal(e_fields[0], e1)
        np.testing.assert_array_equal(e_fields[1], e2)
        assert ref is m1

    def test_mismatched_tags_falls_back_to_nn_interpolation(self, monkeypatch):
        # Reference mesh: 2 elements. Source mesh: 3 elements (mismatched
        # count) -- must trigger the interpolation fallback.
        ref_tags = [2, 2]
        ref_bary = [[0, 0, 0], [1, 0, 0]]
        ref_vol = [1.0, 1.0]
        e1 = np.array([[1.0, 0, 0], [2.0, 0, 0]])
        m1 = _fake_mesh(ref_tags, ref_bary, ref_vol, e1)

        src_tags = [2, 2, 1]
        src_bary = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
        src_vol = [1.0, 1.0, 1.0]
        e2 = np.array([[10.0, 0, 0], [20.0, 0, 0], [30.0, 0, 0]])
        m2 = _fake_mesh(src_tags, src_bary, src_vol, e2)

        # Fake cKDTree: nearest neighbour of ref_bary[i] in src_bary is
        # simply index i (by construction of the coordinates above).
        class _FakeTree:
            def __init__(self, data):
                self.data = np.asarray(data)

            def query(self, points, k=1):
                points = np.asarray(points)
                dists = np.zeros(len(points))
                idx = np.arange(len(points))
                return dists, idx

        monkeypatch.setitem(sys.modules, "scipy.spatial", MagicMock(cKDTree=_FakeTree))

        e_fields, ref = me._align_channel_fields([m1, m2])

        np.testing.assert_array_equal(e_fields[0], e1)
        np.testing.assert_array_equal(e_fields[1], e2[[0, 1]])
        assert ref is m1

    def test_three_channels_one_mismatched(self):
        """Only the mismatched channel should be interpolated; the matching
        one combines directly."""
        ref_tags = [2, 2]
        ref_bary = [[0, 0, 0], [1, 0, 0]]
        ref_vol = [1.0, 1.0]
        e1 = np.array([[1.0, 0, 0], [2.0, 0, 0]])
        m1 = _fake_mesh(ref_tags, ref_bary, ref_vol, e1)

        e2 = np.array([[9.0, 0, 0], [8.0, 0, 0]])
        m2 = _fake_mesh(ref_tags, ref_bary, ref_vol, e2)  # matches exactly

        e_fields, ref = me._align_channel_fields([m1, m2])
        np.testing.assert_array_equal(e_fields[1], e2)


# ---------------------------------------------------------------------------
# make_atlas_label_roi_fn
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeAtlasLabelRoiFn:
    def test_exact_voxel_containment(self, monkeypatch):
        # 2x2x2 label volume, identity affine (1mm iso, origin at 0).
        data = np.zeros((2, 2, 2), dtype=np.int16)
        data[1, 0, 0] = 17
        fake_img = SimpleNamespace(dataobj=data, affine=np.eye(4))

        fake_nib = MagicMock()
        fake_nib.load.return_value = fake_img
        monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

        roi_fn = me.make_atlas_label_roi_fn("/fake/atlas.nii.gz", label=17)

        barycenters = np.array(
            [
                [1.0, 0.0, 0.0],  # rounds to voxel (1,0,0) -> label 17 -> True
                [0.0, 0.0, 0.0],  # voxel (0,0,0) -> label 0 -> False
                [0.6, 0.0, 0.0],  # rounds to (1,0,0) -> True
            ]
        )
        mask = roi_fn(barycenters)
        np.testing.assert_array_equal(mask, [True, False, True])

    def test_out_of_bounds_excluded(self, monkeypatch):
        data = np.zeros((2, 2, 2), dtype=np.int16)
        fake_img = SimpleNamespace(dataobj=data, affine=np.eye(4))
        fake_nib = MagicMock()
        fake_nib.load.return_value = fake_img
        monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

        roi_fn = me.make_atlas_label_roi_fn("/fake/atlas.nii.gz", label=17)
        mask = roi_fn(np.array([[100.0, 100.0, 100.0]]))
        assert mask == np.array([False])

    def test_oblique_affine_handled_via_full_inverse(self, monkeypatch):
        """Regression guard for the oblique-affine bug documented in
        tit/opt/roi.py: a permutation-style affine with an all-zero
        diagonal must still resolve correctly because the inverse of the
        *full* matrix is used, never a diagonal-derived voxel size."""
        data = np.zeros((3, 3, 3), dtype=np.int16)
        data[2, 1, 0] = 17
        # Oblique affine: axes permuted, scale in the off-diagonal terms,
        # diagonal is all zero.
        affine = np.array(
            [
                [0.0, 0.0, 1.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        assert np.all(np.diag(affine)[:3] == 0)
        fake_img = SimpleNamespace(dataobj=data, affine=affine)
        fake_nib = MagicMock()
        fake_nib.load.return_value = fake_img
        monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

        roi_fn = me.make_atlas_label_roi_fn("/fake/atlas.nii.gz", label=17)
        # World point that the affine maps voxel (2,1,0) to: affine @ [2,1,0,1]
        world = (affine @ np.array([2, 1, 0, 1]))[:3]
        mask = roi_fn(np.array([world]))
        assert mask == np.array([True])


# ---------------------------------------------------------------------------
# _load_channel_meshes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadChannelMeshes:
    def test_globs_and_reads_each_pair(self, tmp_path):
        (tmp_path / "ernie_TDCS_1_scalar.msh").write_text("x")
        (tmp_path / "ernie_TDCS_1_scalar.msh.opt").write_text("x")  # must be skipped
        (tmp_path / "ernie_TDCS_2_scalar.msh").write_text("x")

        mesh_io = MagicMock()
        mesh_io.read_msh.side_effect = lambda p: f"mesh:{Path(p).name}"

        result = me._load_channel_meshes(mesh_io, str(tmp_path), "ernie", n_pairs=2)

        assert result == [
            "mesh:ernie_TDCS_1_scalar.msh",
            "mesh:ernie_TDCS_2_scalar.msh",
        ]

    def test_missing_pair_raises(self, tmp_path):
        (tmp_path / "ernie_TDCS_1_scalar.msh").write_text("x")
        mesh_io = MagicMock()

        with pytest.raises(FileNotFoundError, match="pair 2"):
            me._load_channel_meshes(mesh_io, str(tmp_path), "ernie", n_pairs=2)


# ---------------------------------------------------------------------------
# _build_session
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildSession:
    def test_wires_electrodes_and_currents(self, monkeypatch):
        fake_sim_struct = MagicMock()
        session = MagicMock()
        fake_sim_struct.SESSION.return_value = session

        tdcs_list = []

        def _add_tdcslist():
            t = MagicMock()
            t.add_electrode.side_effect = lambda: MagicMock()
            tdcs_list.append(t)
            return t

        session.add_tdcslist.side_effect = _add_tdcslist

        monkeypatch.setitem(
            sys.modules, "simnibs", MagicMock(sim_struct=fake_sim_struct)
        )

        pairs = [
            ([-78.1, -22.5, -3.0], [-76.2, 21.2, -0.7]),
            ([-56.6, -16.6, 77.6], [-71.5, 39.4, 36.6]),
        ]
        currents_mA = [2.0, 2.0]

        result = me._build_session(
            "/m2m/ernie",
            "/m2m/ernie/ernie.msh",
            "/work",
            pairs,
            currents_mA,
            "ellipse",
            (8.0, 8.0),
            4.0,
        )

        assert result is session
        assert session.subpath == "/m2m/ernie"
        assert session.fnamehead == "/m2m/ernie/ernie.msh"
        assert session.pathfem == "/work"
        assert session.add_tdcslist.call_count == 2

        assert tdcs_list[0].currents == [0.002, -0.002]
        assert tdcs_list[1].currents == [0.002, -0.002]
        # 2 electrodes added per pair
        assert tdcs_list[0].add_electrode.call_count == 2
        assert tdcs_list[1].add_electrode.call_count == 2


# ---------------------------------------------------------------------------
# _cleanup_workdir
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCleanupWorkdir:
    def test_remove_dir_removes_everything(self, tmp_path):
        (tmp_path / "keep_me.txt").write_text("x")
        me._cleanup_workdir(str(tmp_path), remove_dir=True)
        assert not tmp_path.exists()

    def test_keep_dir_removes_only_large_intermediates(self, tmp_path):
        mesh = tmp_path / "sub_TDCS_1_scalar.msh"
        mesh.write_text("big")
        opt = tmp_path / "sub_TDCS_1_scalar.msh.opt"
        opt.write_text("opt")
        geo = tmp_path / "sub_TDCS_1_el_currents.geo"
        geo.write_text("geo")
        mat = tmp_path / "simnibs_simulation_20260101-000000.mat"
        mat.write_text("mat")
        keep = tmp_path / "summary.txt"
        keep.write_text("keep")

        me._cleanup_workdir(str(tmp_path), remove_dir=False)

        assert tmp_path.exists()
        assert not mesh.exists()
        assert not opt.exists()
        assert not geo.exists()
        assert not mat.exists()
        assert keep.exists()


# ---------------------------------------------------------------------------
# evaluate_montage_fem (integration, fully mocked SimNIBS)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEvaluateMontageFem:
    def test_raises_on_length_mismatch(self):
        with pytest.raises(ValueError, match="same length"):
            me.evaluate_montage_fem(
                subject_id="ernie",
                pairs=[([0, 0, 0], [1, 0, 0])],
                currents_mA=[2.0, 2.0],
                roi_mask_fn=lambda b: np.ones(len(b), dtype=bool),
            )

    def test_end_to_end_with_mocked_simnibs(self, monkeypatch, tmp_path):
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path)
        monkeypatch.setattr("tit.paths.get_path_manager", lambda: pm)

        tags = [2, 2, 1]
        bary = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
        vol = [1.0, 1.0, 1.0]
        e1 = np.array([[1.0, 0, 0], [2.0, 0, 0], [3.0, 0, 0]])
        e2 = np.array([[4.0, 0, 0], [5.0, 0, 0], [6.0, 0, 0]])
        m1 = _fake_mesh(tags, bary, vol, e1)
        m2 = _fake_mesh(tags, bary, vol, e2)
        m1.crop_mesh = lambda tags: m1
        m2.crop_mesh = lambda tags: m2

        workdir = tmp_path / "work"
        workdir.mkdir()

        def _fake_run_simnibs(session):
            # Simulate SimNIBS writing its two per-pair output meshes.
            (workdir / "ernie_TDCS_1_scalar.msh").write_text("x")
            (workdir / "ernie_TDCS_2_scalar.msh").write_text("x")

        fake_sim_struct = MagicMock()
        fake_session = MagicMock()
        fake_sim_struct.SESSION.return_value = fake_session
        fake_session.add_tdcslist.side_effect = lambda: MagicMock(
            add_electrode=MagicMock(side_effect=lambda: MagicMock())
        )

        fake_mesh_io = MagicMock()
        fake_mesh_io.read_msh.side_effect = lambda p: (m1 if "TDCS_1" in p else m2)

        import simnibs

        monkeypatch.setattr(simnibs, "sim_struct", fake_sim_struct, raising=False)
        monkeypatch.setattr(simnibs, "mesh_io", fake_mesh_io, raising=False)
        monkeypatch.setattr(simnibs, "run_simnibs", _fake_run_simnibs, raising=False)

        roi_mask_fn = lambda b: np.array([True, False])  # noqa: E731

        result = me.evaluate_montage_fem(
            subject_id="ernie",
            pairs=[
                ([-78.1, -22.5, -3.0], [-76.2, 21.2, -0.7]),
                ([-56.6, -16.6, 77.6], [-71.5, 39.4, 36.6]),
            ],
            currents_mA=[2.0, 2.0],
            roi_mask_fn=roi_mask_fn,
            workdir=str(workdir),
            cleanup=True,
        )

        expected_keys = {
            "roi_mean_Vm",
            "gm_mean_Vm",
            "focality_roi_over_gm",
            "roi_max_Vm",
            "roi_p999_Vm",
            "focality_cm",
            "carrier_rms_gm_Vm",
            "carrier_peak_gm_Vm",
            "n_roi_elements",
            "n_gm_elements",
        }
        assert expected_keys.issubset(result.keys())
        assert result["n_gm_elements"] == 2
        assert result["n_roi_elements"] == 1
        # cleanup=True + caller-provided workdir -> large intermediates removed,
        # but the (caller-owned) directory itself is kept.
        assert workdir.exists()
        assert not (workdir / "ernie_TDCS_1_scalar.msh").exists()

    def test_cleanup_false_keeps_all_intermediates(self, monkeypatch, tmp_path):
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path)
        monkeypatch.setattr("tit.paths.get_path_manager", lambda: pm)

        tags = [2, 2, 1]
        bary = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
        vol = [1.0, 1.0, 1.0]
        e1 = np.array([[1.0, 0, 0], [2.0, 0, 0], [3.0, 0, 0]])
        e2 = np.array([[4.0, 0, 0], [5.0, 0, 0], [6.0, 0, 0]])
        m1 = _fake_mesh(tags, bary, vol, e1)
        m2 = _fake_mesh(tags, bary, vol, e2)
        m1.crop_mesh = lambda tags: m1
        m2.crop_mesh = lambda tags: m2

        workdir = tmp_path / "work"
        workdir.mkdir()

        def _fake_run_simnibs(session):
            (workdir / "ernie_TDCS_1_scalar.msh").write_text("x")
            (workdir / "ernie_TDCS_2_scalar.msh").write_text("x")

        fake_sim_struct = MagicMock()
        fake_session = MagicMock()
        fake_sim_struct.SESSION.return_value = fake_session
        fake_session.add_tdcslist.side_effect = lambda: MagicMock(
            add_electrode=MagicMock(side_effect=lambda: MagicMock())
        )
        fake_mesh_io = MagicMock()
        fake_mesh_io.read_msh.side_effect = lambda p: (m1 if "TDCS_1" in p else m2)

        import simnibs

        monkeypatch.setattr(simnibs, "sim_struct", fake_sim_struct, raising=False)
        monkeypatch.setattr(simnibs, "mesh_io", fake_mesh_io, raising=False)
        monkeypatch.setattr(simnibs, "run_simnibs", _fake_run_simnibs, raising=False)

        me.evaluate_montage_fem(
            subject_id="ernie",
            pairs=[([0, 0, 0], [1, 0, 0]), ([2, 0, 0], [3, 0, 0])],
            currents_mA=[2.0, 2.0],
            roi_mask_fn=lambda b: np.ones(len(b), dtype=bool),
            workdir=str(workdir),
            cleanup=False,
        )

        assert (workdir / "ernie_TDCS_1_scalar.msh").exists()
        assert (workdir / "ernie_TDCS_2_scalar.msh").exists()

    def test_temp_workdir_removed_by_default(self, monkeypatch, tmp_path):
        # A single electrode pair has no second carrier to interfere with,
        # so mti_modulation_depth correctly rejects it -- exercise the
        # minimum meaningful (2-pair, standard TI) case here too.
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path)
        monkeypatch.setattr("tit.paths.get_path_manager", lambda: pm)

        tags = [2]
        bary = [[0, 0, 0]]
        vol = [1.0]
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[3.0, 0, 0]])
        m1 = _fake_mesh(tags, bary, vol, e1)
        m2 = _fake_mesh(tags, bary, vol, e2)
        m1.crop_mesh = lambda tags: m1
        m2.crop_mesh = lambda tags: m2

        created_dirs = []

        def _fake_run_simnibs(session):
            workdir = session.pathfem
            created_dirs.append(workdir)
            Path(workdir, "ernie_TDCS_1_scalar.msh").write_text("x")
            Path(workdir, "ernie_TDCS_2_scalar.msh").write_text("x")

        fake_sim_struct = MagicMock()
        fake_session = MagicMock()
        fake_sim_struct.SESSION.return_value = fake_session
        fake_session.add_tdcslist.side_effect = lambda: MagicMock(
            add_electrode=MagicMock(side_effect=lambda: MagicMock())
        )

        fake_mesh_io = MagicMock()
        fake_mesh_io.read_msh.side_effect = lambda p: m1 if "TDCS_1" in p else m2

        import simnibs

        monkeypatch.setattr(simnibs, "sim_struct", fake_sim_struct, raising=False)
        monkeypatch.setattr(simnibs, "mesh_io", fake_mesh_io, raising=False)
        monkeypatch.setattr(simnibs, "run_simnibs", _fake_run_simnibs, raising=False)

        me.evaluate_montage_fem(
            subject_id="ernie",
            pairs=[([0, 0, 0], [1, 0, 0]), ([2, 0, 0], [3, 0, 0])],
            currents_mA=[2.0, 2.0],
            roi_mask_fn=lambda b: np.ones(len(b), dtype=bool),
        )

        assert len(created_dirs) == 1
        assert not Path(created_dirs[0]).exists()  # temp dir cleaned up
