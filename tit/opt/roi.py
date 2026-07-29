"""ROI resolver for volume-only leadfield meshes.

The leadfield is generated with ``tissues=[1,2]``, ``interpolation=None``,
``map_to_surf=False``, so it contains only WM (tag 1) and GM (tag 2)
volume tetrahedra.  All ROI definitions operate on element barycenters
of these volume elements.

A cortical surface ROI evaluated *directly on the surface*
(``FlexConfig.AtlasROI``) is **not** supported -- there is no surface mesh
here to evaluate it on.  A cortical *label*, however, can still be used: see
``FlexConfig.CorticalROI``, which projects the same ``.annot`` label into
this volume mesh's GM ribbon (:meth:`ROIResolver._resolve_cortical_surface`).
"""

import logging
import os

import numpy as np

log = logging.getLogger(__name__)

WM_TAG = 1
GM_TAG = 2

# aseg-style cortex tags in segmentation/labeling.nii.gz (labeling_LUT.txt):
# 3 = Left-Cerebral-Cortex, 42 = Right-Cerebral-Cortex.
_ASEG_CORTEX_TAG = {"lh": 3, "rh": 42}


def _tissue_tags(tissues: str) -> list[int]:
    """Map tissue string to element tag list."""
    mapping = {"GM": [GM_TAG], "WM": [WM_TAG], "both": [WM_TAG, GM_TAG]}
    if tissues not in mapping:
        raise ValueError(f"tissues must be 'GM', 'WM', or 'both', got '{tissues}'")
    return mapping[tissues]


def _broadcast_to(values: list, n: int) -> list:
    """Repeat a single-element list to length *n*; pass a full-length list through.

    Mirrors ``tit.opt.flex.utils._broadcast`` -- used to align a shared
    CorticalROI field (e.g. one ``.annot`` path) with a list of labels.
    """
    return values * n if len(values) == 1 and n != 1 else values


class ROIResolver:
    """Resolve ROI / non-ROI element indices on a volume leadfield mesh.

    Parameters
    ----------
    mesh : simnibs Msh
        Mesh returned by ``TI_utils.load_leadfield``.
    m2m_path : str, optional
        Path to the m2m directory (needed for MNI→subject transforms).
    """

    def __init__(self, mesh, m2m_path: str | None = None):
        self.mesh = mesh
        self.m2m_path = m2m_path
        self._barycenters: np.ndarray | None = None
        self._volumes: np.ndarray | None = None
        # Per-(atlas_path, hemisphere, label) cache of projected ribbon world
        # coordinates -- the surface read + GIFTI load + rasterization in
        # _resolve_cortical_surface is the expensive part; memoize it the
        # same way barycenters/volumes are lazily cached above, so a resolver
        # instance that resolves the same CorticalROI more than once (e.g.
        # roi then non_roi="specific") doesn't redo the projection.
        self._cortical_cache: dict[tuple[str, str, int], np.ndarray] = {}

    # ── Lazy cached mesh properties ──────────────────────────────────────

    @property
    def barycenters(self) -> np.ndarray:
        if self._barycenters is None:
            self._barycenters = self.mesh.elements_baricenters().value
        return self._barycenters

    @property
    def volumes(self) -> np.ndarray:
        if self._volumes is None:
            v = self.mesh.elements_volumes_and_areas().value
            self._volumes = v[:, 0] if v.ndim > 1 else v
        return self._volumes

    # ── Public API ───────────────────────────────────────────────────────

    def resolve_roi(self, roi_config) -> tuple[np.ndarray, np.ndarray]:
        """Resolve ROI config to ``(element_indices, element_volumes)``.

        Parameters
        ----------
        roi_config : SphericalROI | SubcorticalROI | CorticalROI
            ROI definition from ``FlexConfig``.

        Raises
        ------
        ValueError
            If an unsupported ROI type is passed (e.g. the surface-only
            AtlasROI).
        """
        # Lazy import: keeps this module free of a hard tit.opt.config
        # dependency at import time, matching the lazy-import pattern used
        # for simnibs/nibabel/scipy elsewhere in this file.
        from tit.opt.config import FlexConfig

        if isinstance(roi_config, FlexConfig.AtlasROI):
            raise ValueError(
                "AtlasROI is not supported for leadfield-based optimization "
                "(there is no surface mesh here to evaluate it on). Use "
                "SphericalROI, SubcorticalROI (volumetric atlas), or "
                "CorticalROI (the same atlas label projected into the "
                "volumetric GM ribbon) instead. For surface-based ROI, use "
                "flex-search."
            )
        if isinstance(roi_config, FlexConfig.SphericalROI):
            return self._resolve_spherical(roi_config)
        if isinstance(roi_config, FlexConfig.CorticalROI):
            return self._resolve_cortical_surface(roi_config)
        if isinstance(roi_config, FlexConfig.SubcorticalROI):
            return self._resolve_volumetric_label(roi_config)

        raise ValueError(f"Unsupported ROI type: {type(roi_config).__name__}")

    def resolve_nonroi(
        self,
        roi_indices: np.ndarray,
        method: str,
        nonroi_config=None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Resolve non-ROI element indices for focality computation.

        Parameters
        ----------
        roi_indices : array
            Element indices of the target ROI.
        method : str
            ``"everything_else"`` — all GM elements minus ROI.
            ``"specific"`` — resolve *nonroi_config* as a separate ROI.
        nonroi_config : SphericalROI | SubcorticalROI | CorticalROI, optional
            Required when *method* is ``"specific"``.
        """
        if method == "everything_else":
            # All brain tissue (GM + WM) minus the ROI
            brain_idx, brain_vol = self.resolve_tissue_elements("both")
            roi_set = set(roi_indices.tolist())
            keep = np.array([i not in roi_set for i in brain_idx])
            return brain_idx[keep], brain_vol[keep]

        if method == "specific":
            if nonroi_config is None:
                raise ValueError("non_roi_method='specific' requires nonroi_config")
            return self.resolve_roi(nonroi_config)

        raise ValueError(f"Unknown non_roi_method: {method}")

    def resolve_tissue_elements(
        self, tissues: str = "GM"
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(indices, volumes)`` for elements matching tissue type."""
        tags = _tissue_tags(tissues)
        mask = np.isin(self.mesh.elm.tag1, tags)
        idx = np.flatnonzero(mask)
        return idx, self.volumes[idx]

    # ── Private resolvers ────────────────────────────────────────────────

    def _resolve_spherical(self, roi) -> tuple[np.ndarray, np.ndarray]:
        """Resolve SphericalROI to element indices."""
        center = np.array([roi.x, roi.y, roi.z], dtype=float)

        if roi.use_mni:
            center = self._mni_to_subject(center)
            log.info(f"MNI ({roi.x}, {roi.y}, {roi.z}) → subject {center}")

        # Tissue filter
        tissues = roi.tissues if hasattr(roi, "volumetric") and roi.volumetric else "GM"
        tissue_tags = _tissue_tags(tissues)
        tissue_mask = np.isin(self.mesh.elm.tag1, tissue_tags)

        # Sphere mask
        dist_sq = np.sum((self.barycenters - center) ** 2, axis=1)
        sphere_mask = dist_sq <= roi.radius**2

        mask = tissue_mask & sphere_mask
        idx = np.flatnonzero(mask)
        log.info(
            f"SphericalROI: center={center}, r={roi.radius}mm, "
            f"tissues={tissues} → {len(idx)} elements"
        )
        return idx, self.volumes[idx]

    def _resolve_volumetric_label(self, roi) -> tuple[np.ndarray, np.ndarray]:
        """Resolve SubcorticalROI (volumetric atlas label) to element indices."""
        import nibabel as nib

        img = nib.load(roi.atlas_path)
        data = np.asarray(img.dataobj)
        affine = img.affine

        # Find voxel coordinates matching the label(s).
        #
        # SubcorticalROI.label accepts either a scalar or a list -- a union of
        # several regions evaluated as one combined target (e.g. both thalami,
        # labels [10, 49]).  np.isin handles both; a bare `data == roi.label`
        # raises a broadcast error for the list case.
        labels = np.atleast_1d(np.asarray(roi.label))
        voxel_ijk = np.argwhere(np.isin(data, labels))
        if len(voxel_ijk) == 0:
            raise ValueError(
                f"Label(s) {labels.tolist()} not found in {roi.atlas_path}. "
                f"Check the atlas LUT for the correct label indices."
            )

        # Convert voxel indices to world (mm) coordinates
        ones = np.ones((len(voxel_ijk), 1))
        voxel_hom = np.hstack([voxel_ijk, ones])  # (N, 4)
        world_coords = (affine @ voxel_hom.T).T[:, :3]  # (N, 3)

        # Voxel size determines the matching radius.
        #
        # Must be derived from the COLUMN NORMS of the direction matrix, not
        # its diagonal: SimNIBS atlases (e.g. segmentation/labeling.nii.gz)
        # carry an oblique affine whose scale sits entirely in the off-diagonal
        # terms, so np.diag() is all zeros there.  Using the diagonal silently
        # yields voxel_size == 0, a zero match radius, and an empty ROI.
        voxel_size = float(np.linalg.norm(affine[:3, :3], axis=0).max())
        if not np.isfinite(voxel_size) or voxel_size <= 0:
            raise ValueError(
                f"Could not determine voxel size from the affine of "
                f"{roi.atlas_path} (computed {voxel_size}). The atlas affine "
                f"may be degenerate."
            )

        source = (
            f"SubcorticalROI(atlas={roi.atlas_path}, label={roi.label}, "
            f"{len(voxel_ijk)} atlas voxels)"
        )
        matched_idx, matched_vol = self._match_world_points_to_tissue(
            world_coords, roi.tissues, voxel_size, source
        )
        log.info(
            f"SubcorticalROI: atlas={roi.atlas_path}, label={roi.label}, "
            f"tissues={roi.tissues}, voxel_size={voxel_size:.3f}mm "
            f"→ {len(matched_idx)} elements"
        )
        return matched_idx, matched_vol

    def _resolve_cortical_surface(self, roi) -> tuple[np.ndarray, np.ndarray]:
        """Resolve CorticalROI (an ``.annot`` label projected into the GM ribbon).

        For each ``(atlas_path, hemisphere, label)`` triple in the
        (possibly unioned) ROI spec:

        1. Read the ``.annot`` file and find the vertices carrying *label*.
        2. Load that hemisphere's white/pial surfaces
           (``m2m_<subject>/surfaces/{hemi}.{white,pial}.gii`` -- vertex-
           aligned 1:1 with the ``.annot``, both produced by the same CHARM
           run) and, for every masked vertex, sample points along its
           white -> pial "cortical column". This thickens the 2D vertex
           label into the 3D GM ribbon.
        3. Rasterize those sample points into the subject's aseg voxel grid
           (``segmentation/labeling.nii.gz``) and keep only voxels tagged
           Left/Right-Cerebral-Cortex (3/42 -- see ``labeling_LUT.txt``), so
           the projection can't bleed past the true GM boundary into white
           matter or an adjacent gyrus.

        The surviving voxels (unioned across every label) are then matched
        to tissue-filtered leadfield elements exactly like
        :meth:`_resolve_volumetric_label`.
        """
        import nibabel as nib
        import nibabel.freesurfer as nfs

        if self.m2m_path is None:
            raise ValueError("m2m_path is required to resolve a CorticalROI")

        from tit.opt.config import _as_list

        labels = [int(v) for v in _as_list(roi.label)]
        n = len(labels)
        atlas_paths = _broadcast_to(_as_list(roi.atlas_path), n)
        hemis = _broadcast_to(_as_list(roi.hemisphere), n)

        labeling_path = os.path.join(self.m2m_path, "segmentation", "labeling.nii.gz")
        if not os.path.isfile(labeling_path):
            raise ValueError(
                "CorticalROI requires the subject's aseg segmentation at "
                f"{labeling_path} (used for the GM-ribbon constraint), which "
                "was not found."
            )
        aseg_img = nib.load(labeling_path)
        aseg = np.asarray(aseg_img.dataobj)
        aseg_affine = aseg_img.affine
        inv_affine = np.linalg.inv(aseg_affine)
        aseg_voxel_size = float(np.linalg.norm(aseg_affine[:3, :3], axis=0).max())

        region_points = []
        for label_idx, atlas_path, hemi in zip(labels, atlas_paths, hemis):
            if hemi not in _ASEG_CORTEX_TAG:
                raise ValueError(
                    f"CorticalROI hemisphere must be 'lh' or 'rh', got {hemi!r}"
                )

            cache_key = (atlas_path, hemi, label_idx)
            cached = self._cortical_cache.get(cache_key)
            if cached is not None:
                region_points.append(cached)
                continue

            vertex_labels, _ctab, names = nfs.read_annot(atlas_path)
            if not (0 <= label_idx < len(names)):
                names_dec = [
                    nm.decode() if isinstance(nm, bytes) else str(nm) for nm in names
                ]
                raise ValueError(
                    f"Label index {label_idx} not found in {atlas_path} "
                    f"(valid range 0-{len(names) - 1}: {names_dec})"
                )
            vertex_mask = vertex_labels == label_idx
            if not np.any(vertex_mask):
                name = names[label_idx]
                name = name.decode() if isinstance(name, bytes) else str(name)
                raise ValueError(
                    f"Region '{hemi}.{name}' (label {label_idx}) has zero "
                    f"vertices in {atlas_path}."
                )

            surf_dir = os.path.join(self.m2m_path, "surfaces")
            white_path = os.path.join(surf_dir, f"{hemi}.white.gii")
            pial_path = os.path.join(surf_dir, f"{hemi}.pial.gii")
            for surf_path in (white_path, pial_path):
                if not os.path.isfile(surf_path):
                    raise ValueError(
                        f"CorticalROI requires a white/pial surface at "
                        f"{surf_path}, which was not found. SimNIBS's CHARM "
                        "segmentation should produce this under "
                        "m2m_<subject>/surfaces/."
                    )
            white_coords = nib.load(white_path).darrays[0].data.astype(float)
            pial_coords = nib.load(pial_path).darrays[0].data.astype(float)
            if len(white_coords) != len(vertex_labels) or len(pial_coords) != len(
                vertex_labels
            ):
                raise ValueError(
                    f"Vertex count mismatch between {atlas_path} "
                    f"({len(vertex_labels)} vertices) and {hemi} white/pial "
                    f"surfaces ({len(white_coords)}/{len(pial_coords)}); "
                    "cannot project this annotation onto these surfaces."
                )

            white_v = white_coords[vertex_mask]
            pial_v = pial_coords[vertex_mask]

            # Sample points along each vertex's white -> pial cortical column.
            n_samples = 6
            t = np.linspace(0.0, 1.0, n_samples)
            samples = (
                white_v[:, None, :] + t[None, :, None] * (pial_v - white_v)[:, None, :]
            )
            samples = samples.reshape(-1, 3)

            # Rasterize into the aseg voxel grid.
            homog = np.hstack([samples, np.ones((len(samples), 1))])
            voxel_coords = (inv_affine @ homog.T).T[:, :3]
            voxel_ijk = np.round(voxel_coords).astype(int)
            shape = np.array(aseg.shape)
            in_bounds = np.all((voxel_ijk >= 0) & (voxel_ijk < shape), axis=1)
            voxel_ijk = voxel_ijk[in_bounds]

            # Intersect with the aseg cortex ribbon so the projection can't
            # bleed past the true GM boundary (labeling_LUT.txt: 3 =
            # Left-Cerebral-Cortex, 42 = Right-Cerebral-Cortex).
            cortex_tag = _ASEG_CORTEX_TAG[hemi]
            voxel_vals = aseg[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]]
            voxel_ijk = np.unique(voxel_ijk[voxel_vals == cortex_tag], axis=0)

            if len(voxel_ijk) == 0:
                name = names[label_idx]
                name = name.decode() if isinstance(name, bytes) else str(name)
                raise ValueError(
                    f"CorticalROI projection for '{hemi}.{name}' produced 0 "
                    f"voxels after intersecting with the aseg cortex ribbon "
                    f"(tag {cortex_tag}) in {labeling_path}. The white/pial "
                    "surfaces may not share the same space as "
                    "segmentation/labeling.nii.gz."
                )

            homog_v = np.hstack([voxel_ijk.astype(float), np.ones((len(voxel_ijk), 1))])
            region_world = (aseg_affine @ homog_v.T).T[:, :3]
            self._cortical_cache[cache_key] = region_world
            region_points.append(region_world)

        world_coords = np.vstack(region_points)
        source = (
            f"CorticalROI(atlas={_as_list(roi.atlas_path)}, "
            f"hemisphere={_as_list(roi.hemisphere)}, label={labels})"
        )
        matched_idx, matched_vol = self._match_world_points_to_tissue(
            world_coords, roi.tissues, aseg_voxel_size, source
        )
        log.info(
            f"CorticalROI: {n} label(s), hemisphere(s)={_as_list(roi.hemisphere)}, "
            f"tissues={roi.tissues} → {len(world_coords)} ribbon voxels → "
            f"{len(matched_idx)} elements"
        )
        return matched_idx, matched_vol

    def _match_world_points_to_tissue(
        self,
        world_coords: np.ndarray,
        tissues: str,
        voxel_size: float,
        source: str,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Match a cloud of world-space (mm) points to tissue-filtered elements.

        Shared final step for :meth:`_resolve_volumetric_label` (points =
        atlas voxel centers) and :meth:`_resolve_cortical_surface` (points =
        projected cortical-ribbon voxel centers): every tissue-filtered
        leadfield element is kept if its barycenter falls within
        ``voxel_size * 1.5`` of the nearest point in *world_coords*.

        Parameters
        ----------
        world_coords : array, shape (N, 3)
            Candidate world-space (mm) points defining the target region.
        tissues : str
            ``"GM"``, ``"WM"``, or ``"both"``.
        voxel_size : float
            Matching-radius basis (mm); the actual tolerance applied is
            ``voxel_size * 1.5``.
        source : str
            Human-readable description of the ROI, used only in the
            zero-match error message.

        Raises
        ------
        ValueError
            If *voxel_size* is non-positive/non-finite, or no tissue-filtered
            element falls within tolerance of any point.
        """
        if not np.isfinite(voxel_size) or voxel_size <= 0:
            raise ValueError(
                f"Could not determine a voxel size to match {source} against "
                f"the leadfield mesh (computed {voxel_size})."
            )

        tissue_tags = _tissue_tags(tissues)
        tissue_mask = np.isin(self.mesh.elm.tag1, tissue_tags)
        tissue_idx = np.flatnonzero(tissue_mask)
        tissue_centers = self.barycenters[tissue_idx]

        # Use a KDTree for efficient nearest-point spatial lookup.
        from scipy.spatial import cKDTree

        tree = cKDTree(world_coords)
        dists, _ = tree.query(tissue_centers, k=1)
        match_mask = dists <= voxel_size * 1.5  # generous tolerance

        matched_idx = tissue_idx[match_mask]
        if len(matched_idx) == 0:
            raise ValueError(
                f"{source} resolved to 0 mesh elements (tissues={tissues}). "
                f"The region has {len(world_coords)} candidate point(s) but "
                f"no {tissues} element barycenter fell within "
                f"{voxel_size * 1.5:.2f}mm of any of them. Check that the "
                "ROI source and the leadfield mesh are in the same space, "
                "and that the tissue filter is not excluding the target."
            )
        return matched_idx, self.volumes[matched_idx]

    def _mni_to_subject(self, coords_mni: np.ndarray) -> np.ndarray:
        """Transform MNI coordinates to subject space."""
        if self.m2m_path is None:
            raise ValueError("m2m_path required for MNI→subject coordinate transform")
        from simnibs import mni2subject_coords

        result = mni2subject_coords(coords_mni.reshape(1, 3), self.m2m_path)
        return result.flatten()
