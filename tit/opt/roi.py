"""ROI resolver for volume-only leadfield meshes.

The leadfield is generated with ``tissues=[1,2]``, ``interpolation=None``,
``map_to_surf=False``, so it contains only WM (tag 1) and GM (tag 2)
volume tetrahedra.  All ROI definitions operate on element barycenters
of these volume elements.

Surface-based ROI types (FreeSurfer ``.annot``) are **not** supported.
"""

import logging

import numpy as np

log = logging.getLogger(__name__)

WM_TAG = 1
GM_TAG = 2


def _tissue_tags(tissues: str) -> list[int]:
    """Map tissue string to element tag list."""
    mapping = {"GM": [GM_TAG], "WM": [WM_TAG], "both": [WM_TAG, GM_TAG]}
    if tissues not in mapping:
        raise ValueError(f"tissues must be 'GM', 'WM', or 'both', got '{tissues}'")
    return mapping[tissues]


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
        roi_config : SphericalROI | SubcorticalROI
            ROI definition from ``FlexConfig``.

        Raises
        ------
        ValueError
            If an unsupported ROI type is passed (e.g. AtlasROI).
        """
        if hasattr(roi_config, "hemisphere"):
            raise ValueError(
                "AtlasROI is not supported for leadfield-based optimization. "
                "Use SphericalROI or SubcorticalROI (volumetric atlas) instead. "
                "For surface-based ROI, use flex-search."
            )

        if hasattr(roi_config, "x"):  # SphericalROI
            return self._resolve_spherical(roi_config)
        if hasattr(roi_config, "atlas_path"):  # SubcorticalROI
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
        nonroi_config : SphericalROI | SubcorticalROI, optional
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

        # Tissue filter
        tissue_tags = _tissue_tags(roi.tissues)
        tissue_mask = np.isin(self.mesh.elm.tag1, tissue_tags)
        tissue_idx = np.flatnonzero(tissue_mask)
        tissue_centers = self.barycenters[tissue_idx]

        # For each tissue element, check if nearest atlas voxel is close enough.
        # Use a KDTree for efficient spatial lookup.
        from scipy.spatial import cKDTree

        tree = cKDTree(world_coords)
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
        dists, _ = tree.query(tissue_centers, k=1)
        match_mask = dists <= voxel_size * 1.5  # generous tolerance

        matched_idx = tissue_idx[match_mask]
        log.info(
            f"SubcorticalROI: atlas={roi.atlas_path}, label={roi.label}, "
            f"tissues={roi.tissues}, voxel_size={voxel_size:.3f}mm "
            f"→ {len(matched_idx)} elements"
        )
        if len(matched_idx) == 0:
            raise ValueError(
                f"SubcorticalROI resolved to 0 mesh elements "
                f"(atlas={roi.atlas_path}, label={roi.label}, "
                f"tissues={roi.tissues}). The label exists in the atlas "
                f"({len(voxel_ijk)} voxels) but no {roi.tissues} element "
                f"barycenter fell within {voxel_size * 1.5:.2f}mm of it. "
                f"Check that the atlas and the leadfield mesh are in the same "
                f"space, and that the tissue filter is not excluding the target."
            )
        return matched_idx, self.volumes[matched_idx]

    def _mni_to_subject(self, coords_mni: np.ndarray) -> np.ndarray:
        """Transform MNI coordinates to subject space."""
        if self.m2m_path is None:
            raise ValueError("m2m_path required for MNI→subject coordinate transform")
        from simnibs import mni2subject_coords

        result = mni2subject_coords(coords_mni.reshape(1, 3), self.m2m_path)
        return result.flatten()
