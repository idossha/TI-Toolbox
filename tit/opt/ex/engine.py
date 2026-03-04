"""Single-class exhaustive search engine.

Replaces: runner.py (5 classes), roi_utils.py (4 functions).
Direct SimNIBS usage — no tit.core.roi wrappers needed except calculate_roi_metrics.
"""

from __future__ import annotations

import csv
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from simnibs.utils import TI_utils as TI

from tit.core.roi import calculate_roi_metrics
from .logic import (
    count_combinations,
    generate_current_ratios,
    generate_montage_combinations,
)


class ExSearchEngine:
    """Exhaustive TI electrode search engine.

    Owns the full pipeline: leadfield loading, ROI resolution,
    simulation loop, and ROI CRUD.
    """

    def __init__(self, leadfield_hdf: str, roi_file: str, roi_name: str, logger: Any):
        self.leadfield_hdf = leadfield_hdf
        self.roi_file = roi_file
        self.roi_name = roi_name
        self.logger = logger

        self.leadfield = None
        self.mesh = None
        self.idx_lf = None
        self.roi_coords = None
        self.roi_indices = None
        self.roi_volumes = None
        self.gm_indices = None
        self.gm_volumes = None

    # ── Initialization ────────────────────────────────────────────────────

    def initialize(self, roi_radius: float = 3.0) -> None:
        """Load leadfield, parse ROI CSV, find ROI + GM elements."""
        self._load_leadfield()
        self._load_roi_coordinates()
        self._find_roi_elements(roi_radius)
        self._find_gm_elements()

    def _load_leadfield(self) -> None:
        self.logger.info(f"Loading leadfield: {self.leadfield_hdf}")
        start = time.time()
        self.leadfield, self.mesh, self.idx_lf = TI.load_leadfield(self.leadfield_hdf)
        self.logger.info(f"Loaded in {time.time() - start:.1f}s")

    def _load_roi_coordinates(self) -> None:
        """Read ROI center from a simple CSV (one row: x,y,z)."""
        with open(self.roi_file) as f:
            for row in csv.reader(f):
                if not row:
                    continue
                coords = [float(v.strip()) for v in row if v.strip()]
                if len(coords) >= 3:
                    self.roi_coords = coords[:3]
                    self.logger.info(f"ROI coords: {self.roi_coords}")
                    return
        raise ValueError(f"No valid coordinates in {self.roi_file}")

    def _find_roi_elements(self, roi_radius: float) -> None:
        """Find mesh elements whose barycenters fall within a sphere."""
        self.logger.info(f"Finding ROI elements (radius={roi_radius}mm)...")
        centers = self.mesh.elements_baricenters().value
        center = np.asarray(self.roi_coords, dtype=float)
        mask = np.sum((centers - center) ** 2, axis=1) <= roi_radius**2

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

    def compute_ti_field(
        self,
        e1_plus: str,
        e1_minus: str,
        current_ch1_mA: float,
        e2_plus: str,
        e2_minus: str,
        current_ch2_mA: float,
    ) -> Dict[str, float]:
        """Compute TI field for one montage and return ROI metrics."""
        lf = self.leadfield
        idx = self.idx_lf

        ef1 = TI.get_field([e1_plus, e1_minus, current_ch1_mA / 1000], lf, idx)
        ef2 = TI.get_field([e2_plus, e2_minus, current_ch2_mA / 1000], lf, idx)
        ti_max_full = TI.get_maxTI(ef1, ef2)

        metrics = calculate_roi_metrics(
            ti_max_full[self.roi_indices],
            self.roi_volumes,
            ti_field_gm=ti_max_full[self.gm_indices],
            gm_volumes=self.gm_volumes,
        )

        return {
            f"{self.roi_name}_TImax_ROI": metrics["TImax_ROI"],
            f"{self.roi_name}_TImean_ROI": metrics["TImean_ROI"],
            f"{self.roi_name}_TImean_GM": metrics.get("TImean_GM", 0.0),
            f"{self.roi_name}_Focality": metrics.get("Focality", 0.0),
            f"{self.roi_name}_n_elements": metrics["n_elements"],
            "current_ch1_mA": current_ch1_mA,
            "current_ch2_mA": current_ch2_mA,
        }

    # ── Simulation Loop ───────────────────────────────────────────────────

    def run(
        self,
        e1_plus: List[str],
        e1_minus: List[str],
        e2_plus: List[str],
        e2_minus: List[str],
        current_ratios: List[Tuple[float, float]],
        all_combinations: bool,
        output_dir: str,
    ) -> Dict[str, Dict[str, float]]:
        """Run the full simulation loop. Returns {mesh_key: metrics}."""
        stop = False

        def _on_signal(sig, frame):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        total = count_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
        )
        self._log_config_summary(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            current_ratios,
            all_combinations,
            total,
        )

        results: Dict[str, Dict[str, float]] = {}
        start_time = time.time()

        for i, (ep1, em1, ep2, em2, (ch1, ch2)) in enumerate(
            generate_montage_combinations(
                e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
            ),
            1,
        ):
            if stop:
                self.logger.warning("Interrupted")
                break

            name = f"{ep1}_{em1}_and_{ep2}_{em2}_I1-{ch1:.1f}mA_I2-{ch2:.1f}mA"
            key = f"TI_field_{name}.msh"

            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0

            self.logger.info(f"[{i}/{total}] {name}")
            self.logger.info(
                f"  {100 * i / total:.1f}% | {rate:.2f}/s | ETA {eta / 60:.1f}min"
            )

            sim_start = time.time()
            data = self.compute_ti_field(ep1, em1, ch1, ep2, em2, ch2)
            results[key] = data

            self.logger.info(
                f"  {time.time() - sim_start:.2f}s | "
                f"TImax={data[f'{self.roi_name}_TImax_ROI']:.4f} "
                f"TImean={data[f'{self.roi_name}_TImean_ROI']:.4f} "
                f"Foc={data[f'{self.roi_name}_Focality']:.4f}"
            )

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
    ) -> None:
        self.logger.info(f"\n{'=' * 60}")
        mode = "All Combinations" if all_combinations else "Bucketed"
        self.logger.info(f"TI Exhaustive Search ({mode})")
        self.logger.info(f"Total combinations: {total}")
        self.logger.info(f"Current ratios: {len(current_ratios)}")
        self.logger.info(f"{'=' * 60}\n")

    # ── ROI CRUD (static, for GUI) ────────────────────────────────────────

    @staticmethod
    def get_available_rois(subject_id: str) -> List[str]:
        """List ROI CSV files for a subject."""
        from tit.core import get_path_manager

        roi_dir = Path(get_path_manager().rois(subject_id))
        return sorted(p.name for p in roi_dir.glob("*.csv"))

    @staticmethod
    def create_roi(
        subject_id: str,
        roi_name: str,
        x: float,
        y: float,
        z: float,
    ) -> Tuple[bool, str]:
        """Create an ROI CSV from coordinates."""
        from tit.core import get_path_manager

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
    def delete_roi(subject_id: str, roi_name: str) -> Tuple[bool, str]:
        """Delete an ROI file and remove from roi_list.txt."""
        from tit.core import get_path_manager

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
    ) -> Optional[Tuple[float, float, float]]:
        """Read ROI center coordinates from CSV."""
        from tit.core import get_path_manager

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
