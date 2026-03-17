"""
Unified field analyzer for mesh and voxel spaces.

Provides a single ``Analyzer`` class that dispatches spherical and cortical
ROI analyses to the appropriate mesh- or voxel-based implementation, returning
a typed ``AnalysisResult`` dataclass.
"""


import logging
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from tit.analyzer.field_selector import select_field_file
from tit.analyzer.visualizer import (
    save_histogram,
    save_mesh_roi_overlay,
    save_nifti_roi_overlay,
    save_results_csv,
)
from tit.logger import add_file_handler
from tit.paths import get_path_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AnalysisResult:
    """Immutable container for ROI analysis statistics."""

    field_name: str
    region_name: str
    space: str  # "mesh" or "voxel"
    analysis_type: str  # "spherical" or "cortical"
    roi_mean: float
    roi_max: float
    roi_min: float
    roi_focality: float  # TImean_ROI / TImean_GM
    gm_mean: float
    gm_max: float
    normal_mean: float | None = None
    normal_max: float | None = None
    normal_focality: float | None = None
    percentile_95: float | None = None
    percentile_99: float | None = None
    percentile_99_9: float | None = None
    focality_50_area: float | None = None
    focality_75_area: float | None = None
    focality_90_area: float | None = None
    focality_95_area: float | None = None
    n_elements: int = 0
    total_area_or_volume: float = 0.0


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class Analyzer:
    """Unified analyzer for mesh and voxel field data.

    Lazily loads the field file on first analysis call.  All coordinate
    transforms and ROI masking are handled internally.

    Parameters
    ----------
    subject_id:
        Subject identifier (without ``sub-`` prefix).
    simulation:
        Simulation (montage) folder name.
    space:
        ``"mesh"`` or ``"voxel"``.
    output_dir:
        Override output directory.  If *None*, derived from PathManager.
    """

    def __init__(
        self,
        subject_id: str,
        simulation: str,
        space: str = "mesh",
        tissue_type: str = "GM",
        output_dir: str | None = None,
    ) -> None:
        self.subject_id = subject_id
        self.simulation = simulation
        self.space = space
        self.tissue_type = self._normalize_tissue_type(tissue_type)
        if self.space == "mesh":
            self.tissue_type = "GM"

        field_path, field_name = select_field_file(
            subject_id,
            simulation,
            space,
            tissue_type=self.tissue_type,
        )
        self.field_path = field_path
        self.field_name = field_name

        pm = get_path_manager()
        self.m2m_path = pm.m2m(subject_id)
        self.output_dir = output_dir
        self._pm = pm

        # Attach a file handler so every log message is persisted to disk
        logs_dir = pm.logs(subject_id)
        pm.ensure(logs_dir)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = Path(logs_dir) / f"analyzer_{simulation}_{timestamp}.log"
        self._log_handler = add_file_handler(log_file)

        logger.info(
            "Analyzer initialised: subject=%s sim=%s space=%s tissue=%s",
            subject_id,
            simulation,
            space,
            self.tissue_type,
        )

        # Cached lazily
        self._surface_mesh = None
        self._surface_mesh_path: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_sphere(
        self,
        center: tuple[float, float, float],
        radius: float,
        coordinate_space: str = "subject",
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze a spherical ROI.

        Parameters
        ----------
        center:
            (x, y, z) coordinates of the sphere centre.
        radius:
            Radius in mm.
        coordinate_space:
            ``"subject"`` (default) or ``"MNI"``.
        visualize:
            Generate overlay, histogram and CSV artifacts.
        """
        dispatch = {"mesh": self._sphere_mesh, "voxel": self._sphere_voxel}
        return dispatch[self.space](center, radius, coordinate_space, visualize)

    def analyze_cortex(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze a cortical atlas region.

        Parameters
        ----------
        atlas:
            Atlas name recognised by SimNIBS (e.g. ``"DK40"``, ``"HCP_MMP1"``).
        region:
            Region name within the atlas, or a list of region names whose
            masks will be unioned into a single combined ROI.
        visualize:
            Generate overlay, histogram and CSV artifacts.
        """
        dispatch = {"mesh": self._cortex_mesh, "voxel": self._cortex_voxel}
        return dispatch[self.space](atlas, region, visualize)

    # ------------------------------------------------------------------
    # Mesh: spherical
    # ------------------------------------------------------------------

    def _sphere_mesh(
        self,
        center: tuple[float, float, float],
        radius: float,
        coordinate_space: str,
        visualize: bool,
    ) -> AnalysisResult:
        surface = self._load_surface_mesh()
        values = self._field_values(surface)
        coords = surface.nodes.node_coord
        node_areas = self._node_areas(surface)

        center_arr = self._maybe_transform_coords(center, coordinate_space)
        mask = np.linalg.norm(coords - center_arr, axis=1) <= radius
        region_name = (
            f"sphere_x{center[0]:.2f}_y{center[1]:.2f}" f"_z{center[2]:.2f}_r{radius}"
        )

        return self._analyze_mesh_roi(
            surface,
            values,
            node_areas,
            mask,
            region_name=region_name,
            analysis_type="spherical",
            center=center,
            radius=radius,
            coordinate_space=coordinate_space,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Mesh: cortical
    # ------------------------------------------------------------------

    def _cortex_mesh(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool,
    ) -> AnalysisResult:
        from simnibs import subject_atlas

        surface = self._load_surface_mesh()
        values = self._field_values(surface)
        node_areas = self._node_areas(surface)

        atlas_map = subject_atlas(atlas, self.m2m_path)

        regions = region if isinstance(region, list) else [region]

        # Resolve region names to atlas keys. MeshAtlasManager shows names
        # like "cuneus-lh" but subject_atlas() may use "lh.cuneus", "cuneus",
        # or just "cuneus" depending on the atlas version.
        atlas_keys = []
        seen = set()
        for r in regions:
            keys = self._resolve_mesh_region(r, atlas_map)
            for k in keys:
                if k not in seen:
                    seen.add(k)
                    atlas_keys.append(k)

        masks = [np.asarray(atlas_map[k], dtype=bool) for k in atlas_keys]
        mask = masks[0]
        for m in masks[1:]:
            mask = mask | m
        region_name = "+".join(atlas_keys)

        return self._analyze_mesh_roi(
            surface,
            values,
            node_areas,
            mask,
            region_name=region_name,
            analysis_type="cortical",
            atlas=atlas,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Voxel: spherical
    # ------------------------------------------------------------------

    def _sphere_voxel(
        self,
        center: tuple[float, float, float],
        radius: float,
        coordinate_space: str,
        visualize: bool,
    ) -> AnalysisResult:
        import nibabel as nib

        img = nib.load(str(self.field_path))
        field_arr = self._squeeze_4d(img.get_fdata())
        affine = img.affine
        voxel_size = np.array(img.header.get_zooms()[:3])

        center_arr = self._maybe_transform_coords(center, coordinate_space)
        voxel_center = np.dot(np.linalg.inv(affine), np.append(center_arr, 1))[:3]

        shape = field_arr.shape
        x, y, z = np.ogrid[: shape[0], : shape[1], : shape[2]]
        dist = np.sqrt(
            ((x - voxel_center[0]) * voxel_size[0]) ** 2
            + ((y - voxel_center[1]) * voxel_size[1]) ** 2
            + ((z - voxel_center[2]) * voxel_size[2]) ** 2
        )
        sphere_mask = dist <= radius
        positive_mask = field_arr > 0
        tissue_mask = self._voxel_tissue_mask(img, field_arr.shape[:3], affine)
        analysis_mask = positive_mask & tissue_mask
        roi_mask = sphere_mask & analysis_mask

        region_name = (
            f"sphere_x{center[0]:.2f}_y{center[1]:.2f}" f"_z{center[2]:.2f}_r{radius}"
        )

        return self._analyze_voxel_roi(
            field_arr,
            roi_mask,
            analysis_mask,
            affine,
            voxel_size,
            region_name=region_name,
            analysis_type="spherical",
            center=center,
            radius=radius,
            coordinate_space=coordinate_space,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Voxel: cortical
    # ------------------------------------------------------------------

    def _cortex_voxel(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool,
    ) -> AnalysisResult:
        import nibabel as nib

        img = nib.load(str(self.field_path))
        field_arr = self._squeeze_4d(img.get_fdata())
        affine = img.affine
        voxel_size = np.array(img.header.get_zooms()[:3])

        atlas_path = self._resolve_voxel_atlas(atlas)
        atlas_img = nib.load(str(atlas_path))
        atlas_arr = atlas_img.get_fdata()

        atlas_arr = self._resample_if_needed(
            atlas_img,
            atlas_arr,
            field_arr.shape[:3],
            affine,
            atlas_path,
        )

        regions = region if isinstance(region, list) else [region]
        ids = [self._find_voxel_region_id(atlas_arr, atlas_path, r) for r in regions]
        region_mask_raw = np.zeros_like(atlas_arr, dtype=bool)
        for rid in ids:
            region_mask_raw = region_mask_raw | (atlas_arr == rid)
        region_name = "+".join(regions)

        positive_mask = field_arr > 0
        tissue_mask = self._voxel_tissue_mask(img, field_arr.shape[:3], affine)
        analysis_mask = positive_mask & tissue_mask
        roi_mask = region_mask_raw & analysis_mask

        return self._analyze_voxel_roi(
            field_arr,
            roi_mask,
            analysis_mask,
            affine,
            voxel_size,
            region_name=region_name,
            analysis_type="cortical",
            atlas=atlas,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Shared mesh analysis
    # ------------------------------------------------------------------

    def _analyze_mesh_roi(
        self,
        surface,
        values: np.ndarray,
        node_areas: np.ndarray,
        roi_mask: np.ndarray,
        *,
        region_name: str,
        analysis_type: str,
        visualize: bool = False,
        **kwargs,
    ) -> AnalysisResult:
        roi_values = values[roi_mask]
        pos_within_roi = roi_values > 0
        roi_pos = roi_values[pos_within_roi]
        roi_areas = node_areas[roi_mask][pos_within_roi]

        surface_pos_mask = values > 0
        surface_pos = values[surface_pos_mask]
        surface_areas = node_areas[surface_pos_mask]

        roi_mean = float(np.average(roi_pos, weights=roi_areas))
        roi_max = float(np.max(roi_pos))
        roi_min = float(np.min(roi_pos))
        surface_mean = float(np.average(surface_pos, weights=surface_areas))
        surface_max = float(np.max(surface_pos))
        roi_focality = roi_mean / surface_mean

        focality = self._compute_focality_metrics(surface_pos, surface_areas)
        normal = self._get_normal_stats(roi_mask, node_areas)

        out_dir = self._resolve_output_dir(
            analysis_type=analysis_type,
            region_name=region_name,
            **kwargs,
        )

        result = AnalysisResult(
            field_name=self.field_name,
            region_name=region_name,
            space="mesh",
            analysis_type=analysis_type,
            roi_mean=roi_mean,
            roi_max=roi_max,
            roi_min=roi_min,
            roi_focality=roi_focality,
            gm_mean=surface_mean,
            gm_max=surface_max,
            normal_mean=normal.get("mean") if normal else None,
            normal_max=normal.get("max") if normal else None,
            normal_focality=normal.get("focality") if normal else None,
            n_elements=int(np.sum(roi_mask)),
            total_area_or_volume=float(np.sum(roi_areas)),
            **focality,
        )

        if visualize:
            self._visualize_mesh(
                surface,
                values,
                roi_mask,
                region_name,
                out_dir,
                result,
                surface_pos,
                surface_areas,
                roi_pos,
                roi_areas,
            )

        save_results_csv(asdict(result), Path(out_dir))
        logger.info("Analysis complete for %s (%s)", region_name, analysis_type)
        return result

    # ------------------------------------------------------------------
    # Shared voxel analysis
    # ------------------------------------------------------------------

    def _analyze_voxel_roi(
        self,
        field_arr: np.ndarray,
        roi_mask: np.ndarray,
        analysis_mask: np.ndarray,
        affine: np.ndarray,
        voxel_size: np.ndarray,
        *,
        region_name: str,
        analysis_type: str,
        visualize: bool = False,
        **kwargs,
    ) -> AnalysisResult:
        roi_values = field_arr[roi_mask]
        tissue_values = field_arr[analysis_mask]
        voxel_vol = float(np.prod(voxel_size))

        roi_mean = float(np.mean(roi_values))
        roi_max = float(np.max(roi_values))
        roi_min = float(np.min(roi_values))
        tissue_mean = float(np.mean(tissue_values))
        tissue_max = float(np.max(tissue_values))
        roi_focality = roi_mean / tissue_mean

        tissue_weights = np.full(len(tissue_values), voxel_vol)
        focality = self._compute_focality_metrics(tissue_values, tissue_weights)

        out_dir = self._resolve_output_dir(
            analysis_type=analysis_type,
            region_name=region_name,
            **kwargs,
        )

        result = AnalysisResult(
            field_name=self.field_name,
            region_name=region_name,
            space="voxel",
            analysis_type=analysis_type,
            roi_mean=roi_mean,
            roi_max=roi_max,
            roi_min=roi_min,
            roi_focality=roi_focality,
            gm_mean=tissue_mean,
            gm_max=tissue_max,
            n_elements=int(np.sum(roi_mask)),
            total_area_or_volume=float(np.sum(roi_mask)) * voxel_vol,
            **focality,
        )

        if visualize:
            self._visualize_voxel(
                field_arr,
                roi_mask,
                analysis_mask,
                affine,
                region_name,
                out_dir,
                result,
            )

        save_results_csv(asdict(result), Path(out_dir))
        logger.info("Analysis complete for %s (%s)", region_name, analysis_type)
        return result

    # ------------------------------------------------------------------
    # Surface mesh loading (lazy, cached)
    # ------------------------------------------------------------------

    def _load_surface_mesh(self):
        """Load or generate the cortical surface mesh, cached on instance."""
        if self._surface_mesh is not None:
            return self._surface_mesh

        import simnibs

        surface_path = self._ensure_central_surface()
        self._surface_mesh = simnibs.read_msh(str(surface_path))
        self._surface_mesh_path = surface_path
        logger.info("Loaded surface mesh: %s", surface_path)
        return self._surface_mesh

    def _ensure_central_surface(self) -> Path:
        """Return path to central surface mesh, generating via msh2cortex if needed."""
        base = self.field_path.stem  # e.g. "montage1_TI"
        mesh_dir = self.field_path.parent
        surfaces_dir = mesh_dir / "surfaces"
        central_path = surfaces_dir / f"{base}_central.msh"

        if central_path.exists():
            logger.debug("Using cached central surface: %s", central_path)
            return central_path

        self._pm.ensure(str(surfaces_dir))
        logger.info("Generating central surface via msh2cortex...")
        cmd = [
            "msh2cortex",
            "-i",
            str(self.field_path),
            "-m",
            str(self.m2m_path),
            "-o",
            str(surfaces_dir),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return central_path

    # ------------------------------------------------------------------
    # Normal field extraction (mesh only)
    # ------------------------------------------------------------------

    def _get_normal_stats(
        self,
        roi_mask: np.ndarray,
        node_areas: np.ndarray,
    ) -> dict | None:
        """Load the normal mesh and compute weighted ROI stats."""
        normal_path = self._normal_mesh_path()
        if normal_path is None or not normal_path.exists():
            logger.debug("Normal mesh not found, skipping normal stats")
            return None

        import simnibs

        normal_mesh = simnibs.read_msh(str(normal_path))
        if "TI_normal" not in normal_mesh.field:
            return None

        nf = normal_mesh.field["TI_normal"].value
        roi_nf = nf[roi_mask]
        pos = roi_nf > 0
        if not np.any(pos):
            return None

        areas = node_areas[roi_mask][pos]
        mean = float(np.average(roi_nf[pos], weights=areas))
        mx = float(np.max(roi_nf[pos]))

        gm_pos = nf > 0
        gm_areas_raw = self._node_areas(normal_mesh)
        gm_mean = float(np.average(nf[gm_pos], weights=gm_areas_raw[gm_pos]))
        focality = mean / gm_mean

        return {"mean": mean, "max": mx, "focality": focality}

    def _normal_mesh_path(self) -> Path | None:
        """Derive the normal mesh path from the field mesh path."""
        name = self.field_path.name
        replacements = {
            "_mTI.msh": "_mTI_normal.msh",
            "_TI.msh": "_normal.msh",
        }
        for suffix, replacement in replacements.items():
            if name.endswith(suffix):
                return self.field_path.parent / name.replace(suffix, replacement)
        return None

    # ------------------------------------------------------------------
    # Focality metrics
    # ------------------------------------------------------------------

    def _compute_focality_metrics(
        self,
        values: np.ndarray,
        weights: np.ndarray,
    ) -> dict:
        """Compute percentile and area/volume focality metrics.

        Returns a dict with keys matching the optional fields on
        ``AnalysisResult``: ``percentile_95``, ``percentile_99``,
        ``percentile_99_9``, ``focality_50_area`` ... ``focality_95_area``.
        """
        valid = ~np.isnan(values)
        data = values[valid]
        sizes = weights[valid]

        sort_idx = np.argsort(data)
        data_sorted = data[sort_idx]
        sizes_sorted = sizes[sort_idx]

        cumulative = np.cumsum(sizes_sorted)
        total = cumulative[-1]
        normalised = cumulative / total

        percentile_thresholds = [95, 99, 99.9]
        pct_values = []
        for pct in percentile_thresholds:
            idx = min(
                int(np.searchsorted(normalised, pct / 100.0)),
                len(data_sorted) - 1,
            )
            pct_values.append(float(data_sorted[idx]))

        # Area/volume above X% of the 99.9th percentile value
        ref = pct_values[2]  # 99.9th percentile
        focality_cutoffs = [50, 75, 90, 95]
        foc_values = []
        for cutoff in focality_cutoffs:
            threshold = (cutoff / 100.0) * ref
            above = data >= threshold
            area = float(np.sum(sizes[above])) / 100.0  # mm^2 -> cm^2
            foc_values.append(area)

        return {
            "percentile_95": pct_values[0],
            "percentile_99": pct_values[1],
            "percentile_99_9": pct_values[2],
            "focality_50_area": foc_values[0],
            "focality_75_area": foc_values[1],
            "focality_90_area": foc_values[2],
            "focality_95_area": foc_values[3],
        }

    # ------------------------------------------------------------------
    # Visualization helpers
    # ------------------------------------------------------------------

    def _visualize_mesh(
        self,
        surface,
        values,
        roi_mask,
        region_name,
        out_dir,
        result,
        gm_values,
        gm_areas,
        roi_values,
        roi_areas,
    ) -> None:
        out = Path(out_dir)
        save_mesh_roi_overlay(
            surface_mesh_path=self._surface_mesh_path,
            field_values=values,
            roi_mask=roi_mask,
            field_name=self.field_name,
            region_name=region_name,
            output_dir=out,
            normal_mesh_path=self._normal_mesh_path(),
        )
        save_histogram(
            whole_head_values=gm_values,
            roi_values=roi_values,
            output_dir=out,
            region_name=region_name,
            whole_head_weights=gm_areas,
            roi_weights=roi_areas,
            roi_mean=result.roi_mean,
        )

    def _visualize_voxel(
        self,
        field_arr,
        roi_mask,
        analysis_mask,
        affine,
        region_name,
        out_dir,
        result,
    ) -> None:
        out = Path(out_dir)
        save_nifti_roi_overlay(
            field_data=field_arr,
            roi_mask=roi_mask,
            region_name=region_name,
            output_dir=out,
            affine=affine,
        )
        tissue_values = field_arr[analysis_mask]
        roi_values = field_arr[roi_mask]
        save_histogram(
            whole_head_values=tissue_values,
            roi_values=roi_values,
            output_dir=out,
            region_name=region_name,
            roi_mean=result.roi_mean,
        )

    # ------------------------------------------------------------------
    # Output directory resolution
    # ------------------------------------------------------------------

    def _resolve_output_dir(
        self,
        *,
        analysis_type: str,
        region_name: str,
        **kwargs,
    ) -> str:
        if self.output_dir is not None:
            self._pm.ensure(self.output_dir)
            return self.output_dir

        pm_kwargs: dict = {
            "sid": self.subject_id,
            "sim": self.simulation,
            "space": self.space,
            "analysis_type": analysis_type,
        }

        if analysis_type == "spherical":
            center = kwargs.get("center", (0, 0, 0))
            pm_kwargs["coordinates"] = list(center)
            pm_kwargs["radius"] = kwargs.get("radius", 0)
            pm_kwargs["coordinate_space"] = kwargs.get("coordinate_space", "subject")
        else:
            pm_kwargs["region"] = region_name
            pm_kwargs["atlas_name"] = kwargs.get("atlas")

        out = self._pm.analysis_output_dir(**pm_kwargs)
        self._pm.ensure(out)
        return out

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_mesh_region(name: str, atlas_map) -> list[str]:
        """Resolve a user-facing region name to atlas key(s).

        Handles three naming conventions:
        - Direct match: ``"lh.cuneus"`` → ``["lh.cuneus"]``
        - GUI suffix: ``"cuneus-lh"`` → ``["lh.cuneus"]``
        - Bare name: ``"cuneus"`` → ``["lh.cuneus", "rh.cuneus"]`` (both hemis)
        """
        # 1. Direct match (user typed exact atlas key)
        if name in atlas_map:
            return [name]

        # 2. GUI-style suffix: "cuneus-lh" → try "lh.cuneus"
        if name.endswith(("-lh", "-rh")):
            hemi = name[-2:]  # "lh" or "rh"
            bare = name[:-3]
            prefixed = f"{hemi}.{bare}"
            if prefixed in atlas_map:
                return [prefixed]
            # Also try bare (some atlases don't prefix)
            if bare in atlas_map:
                return [bare]

        # 3. Bare name: "cuneus" → try "lh.cuneus" + "rh.cuneus"
        found = []
        for hemi in ("lh", "rh"):
            prefixed = f"{hemi}.{name}"
            if prefixed in atlas_map:
                found.append(prefixed)
        if found:
            return found

        # Nothing matched — build helpful error
        available = list(atlas_map.keys()) if hasattr(atlas_map, "keys") else []
        close = [a for a in available if name.lower().rstrip("-lhrh") in a.lower()]
        hint = f" Similar: {close[:5]}" if close else ""
        raise KeyError(f"Region {name!r} not found in atlas.{hint}")

    def _maybe_transform_coords(
        self,
        center: tuple[float, float, float],
        coordinate_space: str,
    ) -> np.ndarray:
        """Return *center* in subject space, transforming from MNI if needed."""
        arr = np.array([list(center)], dtype=float)
        if coordinate_space.upper() == "MNI":
            from simnibs import mni2subject_coords

            arr = mni2subject_coords(arr, str(self.m2m_path))
            arr = np.atleast_2d(arr)
        return arr[0]

    # ------------------------------------------------------------------
    # Field / mesh helpers
    # ------------------------------------------------------------------

    def _field_values(self, surface) -> np.ndarray:
        """Extract the named field from the surface mesh.

        If the field is a vector (N x 3), the magnitude is returned.
        """
        v = surface.field[self.field_name].value
        if v.ndim == 2:
            return np.linalg.norm(v, axis=1)
        return v

    @staticmethod
    def _node_areas(surface) -> np.ndarray:
        """Return per-node areas as a plain ndarray."""
        areas = surface.nodes_areas()
        if hasattr(areas, "value"):
            areas = areas.value
        return np.asarray(areas)

    @staticmethod
    def _squeeze_4d(arr: np.ndarray) -> np.ndarray:
        """Collapse a 4-D array to 3-D by taking the first volume."""
        if arr.ndim == 4:
            return arr[:, :, :, 0]
        return arr

    @staticmethod
    def _normalize_tissue_type(tissue_type: str) -> str:
        normalized = str(tissue_type or "GM").strip().upper()
        if normalized not in {"GM", "WM", "BOTH"}:
            raise ValueError(
                f"Unsupported tissue_type: {tissue_type!r} (expected 'GM', 'WM', or 'both')"
            )
        return normalized

    def _voxel_tissue_mask(
        self,
        field_img,
        target_shape: tuple[int, int, int],
        target_affine: np.ndarray,
    ) -> np.ndarray:
        """Return a voxel mask for the configured tissue selection.

        Mesh analysis is always GM surface-based; tissue selection only applies to voxel
        analyses. ``GM`` and ``WM`` can use the tissue-specific field NIfTIs directly.
        ``BOTH`` requires an explicit GM|WM union mask so that non-brain voxels from the
        full-field NIfTI are excluded.
        """
        if self.tissue_type == "GM" and self.field_path.name.startswith("grey_"):
            return np.ones(target_shape[:3], dtype=bool)
        if self.tissue_type == "WM" and self.field_path.name.startswith("white_"):
            return np.ones(target_shape[:3], dtype=bool)

        base_name = self.field_path.name
        for prefix in ("grey_", "white_"):
            if base_name.startswith(prefix):
                base_name = base_name[len(prefix) :]
                break

        prefixes = (
            ("grey_", "white_")
            if self.tissue_type == "BOTH"
            else ("grey_",) if self.tissue_type == "GM" else ("white_",)
        )

        import nibabel as nib

        mask = np.zeros(target_shape[:3], dtype=bool)
        for prefix in prefixes:
            tissue_path = self.field_path.parent / f"{prefix}{base_name}"
            if not tissue_path.exists():
                logger.warning("Tissue mask NIfTI not found: %s", tissue_path)
                continue

            tissue_img = nib.load(str(tissue_path))
            tissue_arr = self._squeeze_4d(tissue_img.get_fdata())
            tissue_arr = self._resample_if_needed(
                tissue_img,
                tissue_arr,
                target_shape,
                target_affine,
                tissue_path,
            )
            mask |= tissue_arr > 0

        return mask

    # ------------------------------------------------------------------
    # Voxel atlas helpers
    # ------------------------------------------------------------------

    def _resolve_voxel_atlas(self, atlas: str) -> Path:
        """Find the atlas NIfTI/MGZ file for voxel-space analysis."""
        if Path(atlas).is_file():
            return Path(atlas)

        fs_mri = Path(self._pm.freesurfer_mri(self.subject_id))
        seg_dir = Path(self._pm.segmentation(self.subject_id))
        candidates = [
            fs_mri / atlas,
            seg_dir / atlas,
            fs_mri / f"{atlas}.mgz",
            fs_mri / f"{atlas}.nii.gz",
            fs_mri / f"{atlas}.nii",
            seg_dir / f"{atlas}.nii.gz",
            seg_dir / f"{atlas}.nii",
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError(
            f"Atlas file not found for '{atlas}' in {fs_mri} or {seg_dir}"
        )

    @staticmethod
    def _resample_if_needed(
        atlas_img,
        atlas_arr: np.ndarray,
        target_shape: tuple,
        target_affine: np.ndarray,
        atlas_path: Path,
    ) -> np.ndarray:
        """Resample atlas array to *target_shape* if dimensions differ."""
        if atlas_arr.shape[:3] == target_shape[:3]:
            return atlas_arr

        import nibabel as nib

        logger.info(
            "Resampling atlas %s -> %s",
            atlas_arr.shape[:3],
            target_shape[:3],
        )

        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tf:
            template_path = tf.name
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tf:
            output_path = tf.name

        template_img = nib.Nifti1Image(np.zeros(target_shape[:3]), target_affine)
        nib.save(template_img, template_path)

        cmd = [
            "mri_convert",
            "--reslice_like",
            template_path,
            str(atlas_path),
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        resampled = nib.load(output_path).get_fdata()
        Path(template_path).unlink()
        Path(output_path).unlink()
        return resampled

    @staticmethod
    def _find_voxel_region_id(
        atlas_arr: np.ndarray,
        atlas_path: Path,
        region: str,
    ) -> int:
        """Resolve a region name to its integer label in the atlas volume."""
        region_stripped = region.strip()
        if region_stripped.isdigit():
            return int(region_stripped)

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as tf:
            stats_path = tf.name

        cmd = [
            "mri_segstats",
            "--seg",
            str(atlas_path),
            "--excludeid",
            "0",
            "--ctab-default",
            "--sum",
            stats_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        region_lower = region.lower()
        with open(stats_path) as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                parts = line.strip().split()
                if len(parts) >= 5:
                    seg_id = int(parts[1])
                    name = " ".join(parts[4:])
                    if region_lower in name.lower():
                        Path(stats_path).unlink()
                        return seg_id

        Path(stats_path).unlink()
        raise ValueError(f"Region '{region}' not found in atlas {atlas_path}")
