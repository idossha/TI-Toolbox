"""Tests for tit/opt/roi.py -- ROIResolver on volume-only leadfield meshes.

General ROIResolver coverage (spherical ROI, tissue filtering, non-ROI
resolution, the surface-only AtlasROI rejection) already lives in
``tests/test_opt_mp.py`` alongside the rest of the multi-polar search
suite. This file adds dedicated coverage for the ``CorticalROI``
surface-to-volume projection path added in the volumetric-cortical-roi
track: an ``.annot`` cortical label rasterized into the subject's aseg
voxel grid and intersected with the GM ribbon, so it can be handed to the
leadfield-based optimizers exactly like a ``SubcorticalROI``.

numpy is real; simnibs/scipy/nibabel are mocked (see conftest.py) --
``nibabel``/``nibabel.freesurfer``/``scipy.spatial`` are monkeypatched
per-test with small, deterministic fakes so the projection math itself
(not just "it runs") is verified.
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

from tit.opt.config import FlexConfig

SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
CorticalROI = FlexConfig.CorticalROI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BruteForceTree:
    """Pure-numpy stand-in for ``scipy.spatial.cKDTree`` (exact NN query).

    ``scipy.spatial`` is mocked wholesale by conftest.py; the test data
    here is always small enough that a brute-force nearest-neighbour
    search is both exact and fast, so it can stand in for the real
    ``cKDTree`` that ``ROIResolver`` imports lazily.
    """

    def __init__(self, data):
        self.data = np.asarray(data, dtype=float)

    def query(self, points, k=1):
        points = np.atleast_2d(np.asarray(points, dtype=float))
        diffs = points[:, None, :] - self.data[None, :, :]
        dists = np.linalg.norm(diffs, axis=2)
        idx = np.argmin(dists, axis=1)
        return dists[np.arange(len(points)), idx], idx


def _make_mock_mesh(barycenters, tags, volumes=None):
    """Mock mesh exposing exactly what ROIResolver touches.

    Unlike ``test_opt_mp.py``'s random-barycenter helper, coordinates here
    are caller-specified so a CorticalROI's projected world points can be
    matched against known element positions.
    """
    barycenters = np.asarray(barycenters, dtype=float)
    tags = np.asarray(tags)
    if volumes is None:
        volumes = np.ones(len(tags))

    mesh = MagicMock()
    mesh.elements_baricenters.return_value = SimpleNamespace(value=barycenters)
    mesh.elements_volumes_and_areas.return_value = SimpleNamespace(
        value=np.asarray(volumes, dtype=float)
    )
    mesh.elm = SimpleNamespace(tag1=tags)
    return mesh


def _install_fake_nibabel(monkeypatch, aseg, aseg_affine, gifti_points):
    """Patch ``sys.modules["nibabel"]``/``["nibabel.freesurfer"]``.

    Parameters
    ----------
    aseg : ndarray
        3D aseg-style label volume (stands in for labeling.nii.gz).
    aseg_affine : ndarray, shape (4, 4)
        Affine for *aseg*.
    gifti_points : dict[str, ndarray]
        Maps a path suffix (e.g. ``"lh.white.gii"``) to the (N, 3) vertex
        array ``nib.load(path).darrays[0].data`` should return for a path
        ending in that suffix.

    Returns
    -------
    fake_nib : MagicMock
        The installed ``nibabel`` stand-in (``fake_nib.load`` call args can
        be inspected for cache-hit assertions).
    fake_freesurfer : MagicMock
        The installed ``nibabel.freesurfer`` stand-in (``read_annot``).
    """

    def _load(path):
        path = str(path)
        if path.endswith(".gii"):
            for suffix, pts in gifti_points.items():
                if path.endswith(suffix):
                    return SimpleNamespace(darrays=[SimpleNamespace(data=pts)])
            raise AssertionError(f"Unexpected GIFTI load: {path}")
        return SimpleNamespace(dataobj=aseg, affine=aseg_affine)

    fake_nib = MagicMock()
    fake_nib.load.side_effect = _load
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

    fake_freesurfer = MagicMock()
    monkeypatch.setitem(sys.modules, "nibabel.freesurfer", fake_freesurfer)
    # ``import nibabel.freesurfer as nfs`` resolves via getattr() on the
    # already-imported parent package, not a direct sys.modules lookup for
    # the dotted name -- so the submodule must also be wired up as a real
    # attribute of the parent mock, exactly as a genuine import would leave
    # it (otherwise MagicMock auto-vivifies an unrelated child attribute).
    fake_nib.freesurfer = fake_freesurfer

    monkeypatch.setitem(
        sys.modules, "scipy.spatial", MagicMock(cKDTree=_BruteForceTree)
    )

    return fake_nib, fake_freesurfer


# ---------------------------------------------------------------------------
# Synthetic subject fixture
# ---------------------------------------------------------------------------
#
# A tiny, fully deterministic "subject": identity affine (world coords ==
# voxel indices) so the projection math is easy to hand-verify.
#
# 6 lh vertices: vertices 0/1 carry the target label (5) and sit at aseg
# voxels (5,5,5) / (5,5,6), both tagged Left-Cerebral-Cortex (3) -- inside
# the GM ribbon. Vertex 2 also carries label 5 but sits at (2,2,2), tagged
# White-Matter (2) in the fake aseg -- outside the ribbon, so it must be
# filtered out by the cortex-tag intersection. Vertices 3-5 carry a
# different label (0) and are irrelevant.
#
# white == pial per vertex (zero cortical thickness) so every one of the
# 6 t-samples collapses onto the same voxel -- exercises the ribbon
# sampling code path without needing non-trivial geometry to hand-verify.


def _lh_annot_labels():
    return np.array([5, 5, 5, 0, 0, 0])


def _lh_gifti_points():
    pts = np.array(
        [
            [5.0, 5.0, 5.0],
            [5.0, 5.0, 6.0],
            [2.0, 2.0, 2.0],
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
            [9.0, 9.0, 9.0],
        ]
    )
    return pts


def _make_aseg():
    aseg = np.zeros((10, 10, 10), dtype=int)
    aseg[5, 5, 5] = 3  # Left-Cerebral-Cortex
    aseg[5, 5, 6] = 3  # Left-Cerebral-Cortex
    aseg[2, 2, 2] = 2  # Left-Cerebral-White-Matter (outside the GM ribbon)
    return aseg, np.eye(4)


def _setup_subject(
    monkeypatch, tmp_path, names=("unknown", "a", "b", "c", "d", "target")
):
    """Wire up the fake nibabel + a real (empty) m2m directory tree.

    ``os.path.isfile`` guards in ``_resolve_cortical_surface`` need real
    paths to exist; content is irrelevant since ``nib.load``/
    ``read_annot`` are patched to ignore it.
    """
    m2m = tmp_path / "m2m_test"
    seg_dir = m2m / "segmentation"
    surf_dir = m2m / "surfaces"
    seg_dir.mkdir(parents=True)
    surf_dir.mkdir(parents=True)

    annot_path = seg_dir / "lh.test_a2009s.annot"
    annot_path.write_bytes(b"")
    (seg_dir / "labeling.nii.gz").write_bytes(b"")
    (surf_dir / "lh.white.gii").write_bytes(b"")
    (surf_dir / "lh.pial.gii").write_bytes(b"")

    aseg, aseg_affine = _make_aseg()
    gifti_points = {
        "lh.white.gii": _lh_gifti_points(),
        "lh.pial.gii": _lh_gifti_points(),
    }
    fake_nib, fake_freesurfer = _install_fake_nibabel(
        monkeypatch, aseg, aseg_affine, gifti_points
    )
    fake_freesurfer.read_annot.return_value = (
        _lh_annot_labels(),
        np.zeros((len(names), 5)),
        list(names),
    )
    return str(m2m), str(annot_path), fake_nib, fake_freesurfer


# ===========================================================================
# CorticalROI dataclass
# ===========================================================================


@pytest.mark.unit
class TestCorticalROIDataclass:
    def test_defaults(self):
        roi = CorticalROI(atlas_path="/a.annot", label=5)
        assert roi.hemisphere == "lh"
        assert roi.tissues == "GM"

    def test_rejects_empty_label(self):
        with pytest.raises(ValueError, match="label must be non-empty"):
            CorticalROI(atlas_path="/a.annot", label=[])

    def test_rejects_mismatched_atlas_path_length(self):
        with pytest.raises(ValueError, match="atlas_path must be a scalar"):
            CorticalROI(atlas_path=["/a.annot", "/b.annot"], label=[1, 2, 3])

    def test_rejects_mismatched_hemisphere_length(self):
        with pytest.raises(ValueError, match="hemisphere must be a scalar"):
            CorticalROI(
                atlas_path="/a.annot", label=[1, 2], hemisphere=["lh", "rh", "lh"]
            )

    def test_union_of_labels_accepted(self):
        roi = CorticalROI(
            atlas_path="/a.annot", label=[1, 2], hemisphere=["lh", "rh"], tissues="both"
        )
        assert roi.label == [1, 2]
        assert roi.tissues == "both"


# ===========================================================================
# ROIResolver.resolve_roi dispatch
# ===========================================================================


@pytest.mark.unit
class TestResolveRoiDispatch:
    def test_still_rejects_atlas_roi(self):
        """Regression: switching resolve_roi's AtlasROI check from
        duck-typing (``hasattr(roi, "hemisphere")``) to an isinstance check
        must not stop rejecting the real surface-only AtlasROI -- both
        AtlasROI and the new CorticalROI carry a ``hemisphere`` attribute,
        so hasattr alone can no longer tell them apart.
        """
        from tit.opt.roi import ROIResolver

        mesh = _make_mock_mesh([[0, 0, 0]], [2])
        resolver = ROIResolver(mesh)
        with pytest.raises(ValueError, match="AtlasROI"):
            resolver.resolve_roi(AtlasROI(atlas_path="/a.annot", label=1))

    def test_dispatches_cortical_roi_to_projection(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh(
            [[5.0, 5.0, 5.0], [5.0, 5.0, 6.0]],
            [2, 2],
        )
        resolver = ROIResolver(mesh, m2m_path)
        idx, vol = resolver.resolve_roi(
            CorticalROI(atlas_path=annot_path, label=5, hemisphere="lh")
        )
        assert set(idx.tolist()) == {0, 1}


# ===========================================================================
# ROIResolver._resolve_cortical_surface
# ===========================================================================


@pytest.mark.unit
class TestResolveCorticalSurface:
    def test_requires_m2m_path(self):
        from tit.opt.roi import ROIResolver

        mesh = _make_mock_mesh([[0, 0, 0]], [2])
        resolver = ROIResolver(mesh, m2m_path=None)
        with pytest.raises(ValueError, match="m2m_path is required"):
            resolver.resolve_roi(CorticalROI(atlas_path="/a.annot", label=5))

    def test_label_lookup_failure_gives_clear_error(self, monkeypatch, tmp_path):
        """Acceptance criterion: label lookup failure must be a clear error."""
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh([[5.0, 5.0, 5.0]], [2])
        resolver = ROIResolver(mesh, m2m_path)

        with pytest.raises(ValueError, match="Label index 99 not found"):
            resolver.resolve_roi(
                CorticalROI(atlas_path=annot_path, label=99, hemisphere="lh")
            )

    def test_label_with_zero_vertices_gives_clear_error(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        # "c" (index 3) exists in the colour table but no vertex carries it.
        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh([[5.0, 5.0, 5.0]], [2])
        resolver = ROIResolver(mesh, m2m_path)

        with pytest.raises(ValueError, match="zero vertices"):
            resolver.resolve_roi(
                CorticalROI(atlas_path=annot_path, label=3, hemisphere="lh")
            )

    def test_empty_projection_after_gm_ribbon_intersection(self, monkeypatch, tmp_path):
        """Acceptance criterion: empty projection must be a clear error.

        Vertex 2 carries the target label but sits at an aseg voxel tagged
        White-Matter, not cortex -- if it were the *only* masked vertex,
        the GM-ribbon intersection must drop every candidate voxel and
        raise, rather than silently returning an empty-but-successful ROI.
        """
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, fake_freesurfer = _setup_subject(monkeypatch, tmp_path)
        # Only vertex 2 (off-ribbon) carries the target label this time.
        fake_freesurfer.read_annot.return_value = (
            np.array([0, 0, 5, 0, 0, 0]),
            np.zeros((6, 5)),
            ["unknown", "a", "b", "c", "d", "target"],
        )
        mesh = _make_mock_mesh([[2.0, 2.0, 2.0]], [2])
        resolver = ROIResolver(mesh, m2m_path)

        with pytest.raises(ValueError, match="0 voxels after intersecting"):
            resolver.resolve_roi(
                CorticalROI(atlas_path=annot_path, label=5, hemisphere="lh")
            )

    def test_missing_aseg_segmentation_gives_clear_error(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        m2m = tmp_path / "m2m_missing_aseg"
        (m2m / "segmentation").mkdir(parents=True)
        (m2m / "surfaces").mkdir(parents=True)
        annot_path = m2m / "segmentation" / "lh.test_a2009s.annot"
        annot_path.write_bytes(b"")
        fake_nib = MagicMock()
        fake_freesurfer = MagicMock()
        fake_nib.freesurfer = fake_freesurfer
        monkeypatch.setitem(sys.modules, "nibabel", fake_nib)
        monkeypatch.setitem(sys.modules, "nibabel.freesurfer", fake_freesurfer)

        mesh = _make_mock_mesh([[0.0, 0.0, 0.0]], [2])
        resolver = ROIResolver(mesh, str(m2m))
        with pytest.raises(ValueError, match="aseg segmentation"):
            resolver.resolve_roi(CorticalROI(atlas_path=str(annot_path), label=5))

    def test_missing_surface_gives_clear_error(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        m2m = tmp_path / "m2m_no_surf"
        (m2m / "segmentation").mkdir(parents=True)
        (m2m / "surfaces").mkdir(parents=True)
        annot_path = m2m / "segmentation" / "lh.test_a2009s.annot"
        annot_path.write_bytes(b"")
        (m2m / "segmentation" / "labeling.nii.gz").write_bytes(b"")
        # White/pial surfaces intentionally not created.

        aseg, aseg_affine = _make_aseg()
        fake_nib = MagicMock()
        fake_nib.load.return_value = SimpleNamespace(dataobj=aseg, affine=aseg_affine)
        monkeypatch.setitem(sys.modules, "nibabel", fake_nib)
        fake_freesurfer = MagicMock()
        fake_freesurfer.read_annot.return_value = (
            _lh_annot_labels(),
            np.zeros((6, 5)),
            ["unknown", "a", "b", "c", "d", "target"],
        )
        monkeypatch.setitem(sys.modules, "nibabel.freesurfer", fake_freesurfer)
        fake_nib.freesurfer = fake_freesurfer

        mesh = _make_mock_mesh([[5.0, 5.0, 5.0]], [2])
        resolver = ROIResolver(mesh, str(m2m))
        with pytest.raises(ValueError, match="white/pial surface"):
            resolver.resolve_roi(
                CorticalROI(atlas_path=str(annot_path), label=5, hemisphere="lh")
            )

    def test_rejects_invalid_hemisphere(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh([[5.0, 5.0, 5.0]], [2])
        resolver = ROIResolver(mesh, m2m_path)
        with pytest.raises(ValueError, match="hemisphere must be 'lh' or 'rh'"):
            resolver.resolve_roi(
                CorticalROI(atlas_path=annot_path, label=5, hemisphere="center")
            )

    def test_known_region_resolves_expected_elements_only(self, monkeypatch, tmp_path):
        """Acceptance criterion: a known region's expected volume.

        The synthetic subject places the target label's GM-ribbon voxels at
        (5,5,5) and (5,5,6) only -- vertex 2 carries the same label but its
        voxel is tagged white matter and must be excluded by the GM-ribbon
        intersection. The leadfield mesh has a GM element at each of the
        three candidate voxels; only the two true-GM ones may be selected.
        """
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh(
            barycenters=[
                [5.0, 5.0, 5.0],  # in-ribbon -> expected match
                [5.0, 5.0, 6.0],  # in-ribbon -> expected match
                [2.0, 2.0, 2.0],  # off-ribbon (WM aseg tag) -> must be excluded
                [9.0, 9.0, 9.0],  # far away, irrelevant GM element
            ],
            tags=[2, 2, 2, 2],
            volumes=[1.5, 2.5, 3.5, 4.5],
        )
        resolver = ROIResolver(mesh, m2m_path)
        idx, vol = resolver.resolve_roi(
            CorticalROI(atlas_path=annot_path, label=5, hemisphere="lh")
        )

        assert set(idx.tolist()) == {0, 1}
        assert sorted(vol.tolist()) == [1.5, 2.5]

    def test_tissue_filter_excludes_wm_elements(self, monkeypatch, tmp_path):
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, _, _ = _setup_subject(monkeypatch, tmp_path)
        mesh = _make_mock_mesh(
            barycenters=[[5.0, 5.0, 5.0], [5.0, 5.0, 6.0]],
            tags=[2, 1],  # second element is WM, not GM
        )
        resolver = ROIResolver(mesh, m2m_path)
        idx, _ = resolver.resolve_roi(
            CorticalROI(atlas_path=annot_path, label=5, hemisphere="lh", tissues="GM")
        )
        assert idx.tolist() == [0]

    def test_caches_projection_across_calls(self, monkeypatch, tmp_path):
        """Acceptance/task-2: the projection must be memoized per-resolver so
        resolving the same CorticalROI twice (e.g. roi then a "specific"
        non_roi referencing it) doesn't redo the annot read + rasterization.
        """
        from tit.opt.roi import ROIResolver

        m2m_path, annot_path, fake_nib, fake_freesurfer = _setup_subject(
            monkeypatch, tmp_path
        )
        mesh = _make_mock_mesh([[5.0, 5.0, 5.0], [5.0, 5.0, 6.0]], [2, 2])
        resolver = ROIResolver(mesh, m2m_path)
        roi = CorticalROI(atlas_path=annot_path, label=5, hemisphere="lh")

        resolver.resolve_roi(roi)
        annot_calls_after_first = fake_freesurfer.read_annot.call_count
        resolver.resolve_roi(roi)
        annot_calls_after_second = fake_freesurfer.read_annot.call_count

        assert annot_calls_after_first == 1
        assert annot_calls_after_second == 1  # no repeat read on the cache hit

    def test_union_across_two_labels(self, monkeypatch, tmp_path):
        """A two-label union (mirrors AtlasROI's union semantics) should
        combine both labels' matched elements."""
        from tit.opt.roi import ROIResolver

        m2m = tmp_path / "m2m_union"
        seg_dir = m2m / "segmentation"
        surf_dir = m2m / "surfaces"
        seg_dir.mkdir(parents=True)
        surf_dir.mkdir(parents=True)
        annot_path = seg_dir / "lh.test_a2009s.annot"
        annot_path.write_bytes(b"")
        (seg_dir / "labeling.nii.gz").write_bytes(b"")
        (surf_dir / "lh.white.gii").write_bytes(b"")
        (surf_dir / "lh.pial.gii").write_bytes(b"")

        aseg, aseg_affine = _make_aseg()
        aseg[7, 7, 7] = 3  # a second cortex voxel for the second label
        gifti_points = {
            "lh.white.gii": np.array(
                [[5.0, 5.0, 5.0], [7.0, 7.0, 7.0], [0.0, 0.0, 0.0]]
            ),
            "lh.pial.gii": np.array(
                [[5.0, 5.0, 5.0], [7.0, 7.0, 7.0], [0.0, 0.0, 0.0]]
            ),
        }
        fake_nib, fake_freesurfer = _install_fake_nibabel(
            monkeypatch, aseg, aseg_affine, gifti_points
        )
        fake_freesurfer.read_annot.return_value = (
            np.array([5, 6, 0]),
            np.zeros((7, 5)),
            ["unknown", "a", "b", "c", "d", "five", "six"],
        )

        mesh = _make_mock_mesh(
            barycenters=[[5.0, 5.0, 5.0], [7.0, 7.0, 7.0]], tags=[2, 2]
        )
        resolver = ROIResolver(mesh, str(m2m))
        idx, _ = resolver.resolve_roi(
            CorticalROI(atlas_path=str(annot_path), label=[5, 6], hemisphere="lh")
        )
        assert set(idx.tolist()) == {0, 1}
