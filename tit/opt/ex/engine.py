"""Single-class exhaustive search engine.

Replaces: runner.py (5 classes), roi_utils.py (4 functions).
Direct SimNIBS usage — ROI metrics are computed inline.
"""

import csv
import logging
import os
import signal
import time
from pathlib import Path

import numpy as np
from simnibs.utils import TI_utils as TI

from .roi import read_roi_center
from .logic import (
    _electrode_combinations,
    count_combinations,
    generate_current_ratios,
    generate_montage_combinations,
)
from .parallel import evaluate_ordered, resolve_n_jobs


class ExSearchEngine:
    """Exhaustive TI electrode search engine.

    Owns the full pipeline: leadfield loading, ROI resolution,
    simulation loop, and ROI CRUD.
    """

    def __init__(
        self,
        leadfield_hdf: str,
        roi_file: str | tuple[str, int] | list[str | tuple[str, int]],
        roi_name: str,
        logger: logging.Logger,
    ):
        self.leadfield_hdf = leadfield_hdf
        self.roi_file = roi_file
        self.roi_name = roi_name
        self.logger = logger

        self.leadfield = None
        self.mesh = None
        self.idx_lf = None
        self.roi_coords = None
        self.roi_centers = None
        self.roi_indices = None
        self.roi_volumes = None
        self.gm_indices = None
        self.gm_volumes = None
        self._eval_subset = None

    # ── Initialization ────────────────────────────────────────────────────

    def initialize(self, roi_radius: float = 3.0) -> None:
        """Load leadfield, resolve the ROI (CSV/mask/atlas), find ROI + GM elements."""
        self._load_leadfield()
        self._load_roi_coordinates()
        self._find_roi_elements(roi_radius)
        self._find_gm_elements()
        self._eval_subset = None

    def _load_leadfield(self) -> None:
        self.logger.info(f"Loading leadfield: {self.leadfield_hdf}")
        start = time.time()
        self.leadfield, self.mesh, self.idx_lf = TI.load_leadfield(self.leadfield_hdf)
        self.logger.info(f"Loaded in {time.time() - start:.1f}s")

    def _roi_entries(self) -> list:
        """Normalize ``roi_file`` to a list of entries.

        Each entry is a CSV path (spherical center), a NIfTI/MGZ path
        (mask, ``value > 0``), or a ``(path, label)`` pair (one atlas
        label, ``value == label``).
        """
        return self.roi_file if isinstance(self.roi_file, list) else [self.roi_file]

    @staticmethod
    def _is_nifti_roi(entry) -> bool:
        """True if *entry* selects a volumetric mask rather than a CSV center.

        A ``(path, label)`` pair always names a labelled atlas region. A
        bare path names a mask when it has a NIfTI or FreeSurfer MGZ
        extension (``.nii``, ``.nii.gz``, ``.mgz``) -- the extensions used
        by every atlas :class:`tit.atlas.voxel.VoxelAtlasManager` discovers.
        """
        if isinstance(entry, (tuple, list)):
            return True
        name = str(entry).lower()
        return name.endswith((".nii", ".nii.gz", ".mgz"))

    def _load_roi_coordinates(self) -> None:
        """Read spherical ROI center(s) from the CSV entries in ``roi_file``.

        NIfTI/MGZ mask and atlas-label entries are skipped here and
        resolved directly by :meth:`_find_roi_elements`.  ``roi_coords``
        mirrors the first CSV center for backward compatibility, and is
        ``None`` when every entry is a mask.
        """
        csv_files = [e for e in self._roi_entries() if not self._is_nifti_roi(e)]
        self.roi_centers = [self._read_center(f) for f in csv_files]
        self.roi_coords = self.roi_centers[0] if self.roi_centers else None
        if len(self.roi_centers) == 1:
            self.logger.info(f"ROI coords: {self.roi_coords}")
        elif self.roi_centers:
            self.logger.info(
                f"ROI centers ({len(self.roi_centers)}): {self.roi_centers}"
            )
        else:
            self.logger.info("No spherical ROI centers (mask-only ROI)")

    def _read_center(self, path: str) -> list[float]:
        """Return the first valid ``[x, y, z]`` triple from an ROI CSV."""
        return read_roi_center(path)

    def _nifti_roi_mask(self, entry, baricenters: np.ndarray) -> np.ndarray:
        """Boolean mask selecting elements inside one NIfTI/MGZ ROI source.

        *entry* is either a mask path (elements where ``value > 0``) or a
        ``(atlas_path, label)`` pair selecting one atlas label
        (``value == label``).
        """
        import nibabel as nib

        path, label = entry if isinstance(entry, (tuple, list)) else (entry, None)
        self.logger.info(
            f"Finding ROI elements from {'atlas label ' + str(label) if label is not None else 'mask'}: {path}"
        )

        img = nib.load(path)
        data = np.asanyarray(img.get_fdata())
        if data.ndim == 4:
            data = np.squeeze(data)
        if data.ndim != 3:
            raise ValueError(f"Expected a 3D ROI mask, got shape {data.shape}")
        mask_data = data == label if label is not None else data > 0

        homogeneous = np.hstack([baricenters, np.ones((len(baricenters), 1))])
        vox = (homogeneous @ np.linalg.inv(img.affine).T)[:, :3]
        vox = np.rint(vox).astype(int)

        shape = np.asarray(mask_data.shape[:3])
        in_bounds = np.all((vox >= 0) & (vox < shape), axis=1)
        mask = np.zeros(len(baricenters), dtype=bool)
        valid_vox = vox[in_bounds]
        if len(valid_vox):
            mask[in_bounds] = mask_data[
                valid_vox[:, 0], valid_vox[:, 1], valid_vox[:, 2]
            ]
        return mask

    def _find_roi_elements(self, roi_radius: float) -> None:
        """Find mesh elements that fall within the target ROI.

        Combines spherical centers (``value`` within *roi_radius* of a
        center) and volumetric masks (whole NIfTI/MGZ masks, or
        ``(path, label)`` atlas-label selections) -- every source in
        ``roi_file`` is OR-folded into one region (a single spherical
        center is the N=1 case).
        """
        self.logger.info(f"Finding ROI elements (radius={roi_radius}mm)...")
        baricenters = self.mesh.elements_baricenters().value
        roi_centers = self.roi_centers if self.roi_centers else [self.roi_coords]
        mask = np.zeros(baricenters.shape[0], dtype=bool)
        for c in roi_centers:
            if c is None:
                continue
            center = np.asarray(c, dtype=float)
            mask |= np.sum((baricenters - center) ** 2, axis=1) <= roi_radius**2

        for entry in self._roi_entries():
            if self._is_nifti_roi(entry):
                mask |= self._nifti_roi_mask(entry, baricenters)

        volumes = self.mesh.elements_volumes_and_areas().value
        if volumes.ndim > 1:
            volumes = volumes[:, 0]

        self.roi_indices = np.flatnonzero(mask)
        self.roi_volumes = volumes[mask]
        self.logger.info(f"Found {len(self.roi_indices)} ROI elements")

    def _find_gm_elements(self) -> None:
        """Find grey matter elements by tissue tag."""
        self.logger.info("Finding grey matter elements...")
        GM_TAG = 2
        mask = self.mesh.elm.tag1 == GM_TAG

        volumes = self.mesh.elements_volumes_and_areas().value
        if volumes.ndim > 1:
            volumes = volumes[:, 0]

        self.gm_indices = np.flatnonzero(mask)
        self.gm_volumes = volumes[mask]
        self.logger.info(f"Found {len(self.gm_indices)} GM elements")

    # ── TI Field Computation ──────────────────────────────────────────────

    def _evaluation_subset(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Elements the ROI metrics actually depend on, plus index maps.

        The metrics read only ``ROI | GM``, and every envelope here is
        element-wise, so the field is evaluated on that subset instead of
        the whole leadfield mesh. Returns ``(subset, roi_pos, gm_pos)``
        where ``subset`` is sorted and ``roi_pos``/``gm_pos`` index into it
        in the same order as ``roi_indices``/``gm_indices`` (so the volume
        weights still line up). Cached per ``(roi_indices, gm_indices)``.
        """
        roi = np.asarray(self.roi_indices, dtype=np.intp)
        gm = np.asarray(self.gm_indices, dtype=np.intp)
        cache = self._eval_subset
        if cache is None or cache[0] is not roi or cache[1] is not gm:
            subset = np.union1d(roi, gm)
            roi_pos = np.searchsorted(subset, roi)
            gm_pos = np.searchsorted(subset, gm)
            cache = self._eval_subset = (roi, gm, subset, roi_pos, gm_pos)
        return cache[2], cache[3], cache[4]

    def _roi_metrics(self, field_roi: np.ndarray, field_gm: np.ndarray) -> dict:
        """Volume-weighted ROI/GM metrics of an element-wise field."""
        n_elements = int(len(field_roi))
        if n_elements == 0:
            roi_max = roi_mean = gm_mean = focality = 0.0
        else:
            roi_max = float(np.max(field_roi))
            roi_mean = float(np.average(field_roi, weights=self.roi_volumes))
            if len(field_gm) > 0:
                gm_mean = float(np.average(field_gm, weights=self.gm_volumes))
                focality = roi_mean / gm_mean if gm_mean > 0 else 0.0
            else:
                gm_mean = focality = 0.0
        return {
            f"{self.roi_name}_TImax_ROI": roi_max,
            f"{self.roi_name}_TImean_ROI": roi_mean,
            f"{self.roi_name}_TImean_GM": gm_mean,
            f"{self.roi_name}_Focality": focality,
            f"{self.roi_name}_n_elements": n_elements,
        }

    def compute_ti_fields(
        self,
        e1_plus: str,
        e1_minus: str,
        e2_plus: str,
        e2_minus: str,
        current_ratios: list[tuple[float, float]],
    ) -> list[dict[str, float]]:
        """ROI metrics of one electrode montage at every current split.

        The field is linear in the injected current, so each channel's
        unit-current field is gathered once and scaled per split -- the
        same ``current * (lf[a] - lf[b])`` arithmetic ``TI.get_field``
        performs, restricted to the elements the metrics read.
        """
        lf = self.leadfield
        idx = self.idx_lf
        subset, roi_pos, gm_pos = self._evaluation_subset()

        unit1 = TI.get_field([e1_plus, e1_minus, 1.0], lf, idx)[subset]
        unit2 = TI.get_field([e2_plus, e2_minus, 1.0], lf, idx)[subset]

        results = []
        for current_ch1_mA, current_ch2_mA in current_ratios:
            ef1 = (current_ch1_mA / 1000) * unit1
            ef2 = (current_ch2_mA / 1000) * unit2
            ti_max = TI.get_maxTI(ef1, ef2)
            data = self._roi_metrics(ti_max[roi_pos], ti_max[gm_pos])
            data["current_ch1_mA"] = current_ch1_mA
            data["current_ch2_mA"] = current_ch2_mA
            results.append(data)
        return results

    def compute_ti_field(
        self,
        e1_plus: str,
        e1_minus: str,
        current_ch1_mA: float,
        e2_plus: str,
        e2_minus: str,
        current_ch2_mA: float,
    ) -> dict[str, float]:
        """Compute TI field for one montage and return ROI metrics."""
        return self.compute_ti_fields(
            e1_plus, e1_minus, e2_plus, e2_minus, [(current_ch1_mA, current_ch2_mA)]
        )[0]

    # ── Simulation Loop ───────────────────────────────────────────────────

    def run(
        self,
        e1_plus: list[str],
        e1_minus: list[str],
        e2_plus: list[str],
        e2_minus: list[str],
        current_ratios: list[tuple[float, float]],
        all_combinations: bool,
        output_dir: str,
        n_jobs: int = 1,
        symmetry_mirror_map: dict[str, str] | None = None,
        symmetry_pairing: str = "within_pairs",
    ) -> dict[str, dict[str, float]]:
        """Run the full simulation loop. Returns {mesh_key: metrics}.

        Candidates are evaluated in enumeration order, one electrode
        montage (all its current splits) per task, on ``n_jobs`` forked
        workers (``n_jobs < 1``: all cores minus one; ``1``: in-process).
        A *symmetry_mirror_map* (bucket mode) restricts the enumeration to
        left/right mirrored montages (see :mod:`tit.opt.ex.symmetry`).
        """
        stop = False

        def _on_signal(sig, frame):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        total = count_combinations(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            current_ratios,
            all_combinations,
            symmetry_mirror_map,
            symmetry_pairing,
        )
        n_jobs = resolve_n_jobs(n_jobs)
        self._log_config_summary(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            current_ratios,
            all_combinations,
            total,
            n_jobs,
            symmetry_pairing if symmetry_mirror_map is not None else None,
        )

        results: dict[str, dict[str, float]] = {}
        start_time = time.time()
        ratios = list(current_ratios)

        montages = list(
            _electrode_combinations(
                e1_plus,
                e1_minus,
                e2_plus,
                e2_minus,
                all_combinations,
                symmetry_mirror_map,
                symmetry_pairing,
            )
        )
        evaluations = evaluate_ordered(
            self,
            "compute_ti_fields",
            ((*montage, ratios) for montage in montages),
            n_jobs,
            n_tasks=len(montages),
        )

        i = 0
        for (ep1, em1, ep2, em2), montage_results in zip(montages, evaluations):
            montage_start = time.time()
            for (ch1, ch2), data in zip(ratios, montage_results):
                i += 1
                name = f"{ep1}_{em1}_and_{ep2}_{em2}_I1-{ch1:.1f}mA_I2-{ch2:.1f}mA"
                key = f"TI_field_{name}.msh"

                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0

                self.logger.info(f"[{i}/{total}] {name}")
                self.logger.info(
                    f"  {100 * i / total:.1f}% | {rate:.2f}/s | ETA {eta / 60:.1f}min"
                )

                data["electrodes"] = (ep1, em1, ep2, em2)
                results[key] = data
                self.logger.info(
                    f"  {(time.time() - montage_start) / len(ratios):.2f}s | "
                    f"TImax={data[f'{self.roi_name}_TImax_ROI']:.4f} "
                    f"TImean={data[f'{self.roi_name}_TImean_ROI']:.4f} "
                    f"Foc={data[f'{self.roi_name}_Focality']:.4f}"
                )
            if stop:
                self.logger.warning("Interrupted")
                evaluations.close()
                break

        if results:
            t = time.time() - start_time
            self.logger.info(f"\n{'=' * 60}")
            self.logger.info(
                f"Done: {len(results)}/{total} in {t / 60:.1f}min "
                f"({t / len(results):.2f}s each)"
            )
            self.logger.info(f"Output: {output_dir}")

        return results

    def _log_config_summary(
        self,
        e1_plus,
        e1_minus,
        e2_plus,
        e2_minus,
        current_ratios,
        all_combinations,
        total,
        n_jobs=1,
        symmetry_pairing=None,
    ) -> None:
        self.logger.info(f"\n{'=' * 60}")
        mode = "All Combinations" if all_combinations else "Bucketed"
        if symmetry_pairing:
            mode += f", left/right symmetric ({symmetry_pairing})"
        self.logger.info(f"TI Exhaustive Search ({mode})")
        self.logger.info(f"Total combinations: {total}")
        self.logger.info(f"Current ratios: {len(current_ratios)}")
        self.logger.info(f"Workers: {n_jobs}")
        self.logger.info(f"{'=' * 60}\n")

    # ── ROI CRUD (static, for GUI) ────────────────────────────────────────

    @staticmethod
    def get_available_rois(subject_id: str) -> list[str]:
        """List ROI CSV files for a subject."""
        from tit.paths import get_path_manager

        roi_dir = Path(get_path_manager().rois(subject_id))
        return sorted(p.name for p in roi_dir.glob("*.csv"))

    @staticmethod
    def create_roi(
        subject_id: str,
        roi_name: str,
        x: float,
        y: float,
        z: float,
    ) -> tuple[bool, str]:
        """Create an ROI CSV from coordinates."""
        from tit.paths import get_path_manager

        roi_dir = Path(get_path_manager().rois(subject_id))
        roi_dir.mkdir(parents=True, exist_ok=True)

        if not roi_name.endswith(".csv"):
            roi_name += ".csv"

        roi_file = roi_dir / roi_name
        with open(roi_file, "w", newline="") as f:
            csv.writer(f).writerow([x, y, z])

        roi_list = roi_dir / "roi_list.txt"
        existing = []
        if roi_list.exists():
            existing = [
                ln.strip() for ln in roi_list.read_text().splitlines() if ln.strip()
            ]
        if roi_name not in existing:
            with open(roi_list, "a") as f:
                f.write(f"{roi_name}\n")

        return True, f"ROI '{roi_name}' created at ({x:.2f}, {y:.2f}, {z:.2f})"

    @staticmethod
    def delete_roi(subject_id: str, roi_name: str) -> tuple[bool, str]:
        """Delete an ROI file and remove from roi_list.txt."""
        from tit.paths import get_path_manager

        roi_dir = Path(get_path_manager().rois(subject_id))

        if not roi_name.endswith(".csv"):
            roi_name += ".csv"

        roi_file = roi_dir / roi_name
        if roi_file.exists():
            roi_file.unlink()

        roi_list = roi_dir / "roi_list.txt"
        if roi_list.exists():
            lines = [
                ln.strip() for ln in roi_list.read_text().splitlines() if ln.strip()
            ]
            if roi_name in lines:
                lines.remove(roi_name)
                roi_list.write_text(("\n".join(lines) + "\n") if lines else "")

        return True, f"ROI '{roi_name}' deleted"

    @staticmethod
    def get_roi_coordinates(
        subject_id: str,
        roi_name: str,
    ) -> tuple[float, float, float] | None:
        """Read ROI center coordinates from CSV."""
        from tit.paths import get_path_manager

        roi_dir = Path(get_path_manager().rois(subject_id))

        if not roi_name.endswith(".csv"):
            roi_name += ".csv"

        roi_file = roi_dir / roi_name
        if not roi_file.exists():
            return None

        with open(roi_file) as f:
            for row in csv.reader(f):
                if not row:
                    continue
                coords = [float(v.strip()) for v in row if v.strip()]
                if len(coords) >= 3:
                    return (coords[0], coords[1], coords[2])
        return None
