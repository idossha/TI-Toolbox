"""Secondary exhaustive search for mTI augmentation.

Starts from a fixed base TI simulation (two HF fields) and searches one added
carrier block (two additional HF fields) from a precomputed leadfield.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from typing import Dict

import numpy as np
from simnibs.utils import TI_utils as TI

from tit.calc import (
    compute_botzanowski_directional_am_stats,
    compute_botzanowski_magnitude_am_vectors,
    compute_grossman_ext_directional_am_stats,
    compute_mti_vectors,
)
from tit.logger import add_file_handler
from tit.opt.config import (
    BucketElectrodes,
    PoolElectrodes,
    SecondaryExConfig,
    SecondaryExResult,
)
from tit.opt.ex.logic import count_combinations, generate_montage_combinations
from tit.opt.ex.results import generate_plots
from tit.opt.secondary import load_base_montage
from tit.paths import get_path_manager


class SecondaryExSearchEngine:
    """Exhaustive search engine for one added carrier on top of a fixed TI base."""

    def __init__(self, config: SecondaryExConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.base_montage = None
        self.fixed_fields = None
        self.leadfield = None
        self.mesh = None
        self.idx_lf = None
        self.roi_coords = None
        self.roi_indices = None
        self.roi_volumes = None
        self.gm_indices = None
        self.gm_volumes = None

    def initialize(self) -> None:
        self.base_montage = load_base_montage(
            self.config.subject_id,
            self.config.base_montage,
            self.config.base_eeg_net,
            project_dir=self.config.project_dir,
        )
        self.logger.info(
            "Using base montage %s (%s) with electrode pairs: %s",
            self.config.base_montage,
            self.config.base_eeg_net,
            ", ".join(
                f"{p[0]}-{p[1]}" for p in self.base_montage.electrode_pairs
            ),
        )

        self.logger.info(
            "2nd Ex-Search fixed current: %.3f mA per pair",
            self.config.current_mA,
        )

        self.leadfield, self.mesh, self.idx_lf = TI.load_leadfield(
            self.config.leadfield_hdf
        )
        self._load_roi_coordinates()
        self._find_roi_elements(self.config.roi_radius)
        self._find_gm_elements()

        self.fixed_fields = self._build_base_fields_from_leadfield()

    def _build_base_fields_from_leadfield(self) -> list[np.ndarray]:
        pairs = self.base_montage.electrode_pairs
        rebuilt = []
        for ep, em in pairs[:2]:
            rebuilt.append(
                TI.get_field([ep, em, float(self.config.current_mA) / 1000], self.leadfield, self.idx_lf)
            )
        self.logger.info(
            "Rebuilt base HF fields from leadfield using %s and %s at %.3fmA each",
            f"{pairs[0][0]}-{pairs[0][1]}",
            f"{pairs[1][0]}-{pairs[1][1]}",
            float(self.config.current_mA),
        )
        return rebuilt

    def _load_roi_coordinates(self) -> None:
        pm = get_path_manager(self.config.project_dir)
        roi_file = os.path.join(pm.rois(self.config.subject_id), self.config.roi_name)
        with open(roi_file) as f:
            for row in csv.reader(f):
                if not row:
                    continue
                coords = [float(v.strip()) for v in row if v.strip()]
                if len(coords) >= 3:
                    self.roi_coords = coords[:3]
                    return
        raise ValueError(f"No valid coordinates in {roi_file}")

    def _find_roi_elements(self, roi_radius: float) -> None:
        centers = self.mesh.elements_baricenters().value
        center = np.asarray(self.roi_coords, dtype=float)
        mask = np.sum((centers - center) ** 2, axis=1) <= roi_radius**2
        volumes = self.mesh.elements_volumes_and_areas().value
        if volumes.ndim > 1:
            volumes = volumes[:, 0]
        self.roi_indices = np.flatnonzero(mask)
        self.roi_volumes = volumes[mask]

    def _find_gm_elements(self) -> None:
        mask = self.mesh.elm.tag1 == 2
        volumes = self.mesh.elements_volumes_and_areas().value
        if volumes.ndim > 1:
            volumes = volumes[:, 0]
        self.gm_indices = np.flatnonzero(mask)
        self.gm_volumes = volumes[mask]

    def _metric_field(self, combined_fields: list[np.ndarray]) -> np.ndarray:
        metric = self.config.metric
        if metric == "recursive_ti":
            return np.linalg.norm(compute_mti_vectors(combined_fields, metric), axis=1)
        if metric == "botzanowski_magnitude_am":
            return np.asarray(
                compute_botzanowski_magnitude_am_vectors(combined_fields), dtype=float
            )
        if metric == "botzanowski_directional_am":
            stats = compute_botzanowski_directional_am_stats(combined_fields)
            return np.linalg.norm(stats["vectors"], axis=1)
        if metric == "botzanowski_directional_am_ti_avg":
            return np.asarray(
                compute_botzanowski_directional_am_stats(combined_fields)["avg"],
                dtype=float,
            )
        if metric == "grossman_ext_directional_am":
            stats = compute_grossman_ext_directional_am_stats(combined_fields)
            return np.linalg.norm(stats["vectors"], axis=1)
        if metric == "grossman_ext_directional_am_ti_avg":
            return np.asarray(
                compute_grossman_ext_directional_am_stats(combined_fields)["avg"],
                dtype=float,
            )
        raise ValueError(f"Unsupported secondary-search metric: {metric!r}")

    def score_candidate(
        self,
        e3_plus: str,
        e3_minus: str,
        e4_plus: str,
        e4_minus: str,
    ) -> Dict[str, float]:
        ef3 = TI.get_field(
            [e3_plus, e3_minus, self.config.current_mA / 1000], self.leadfield, self.idx_lf
        )
        ef4 = TI.get_field(
            [e4_plus, e4_minus, self.config.current_mA / 1000], self.leadfield, self.idx_lf
        )
        metric_field = self._metric_field(
            [self.fixed_fields[0], self.fixed_fields[1], ef3, ef4]
        )

        field_roi = metric_field[self.roi_indices]
        field_gm = metric_field[self.gm_indices]
        if len(field_roi) == 0:
            roi_max = roi_mean = gm_mean = focality = 0.0
            n_elements = 0
        else:
            roi_max = float(np.max(field_roi))
            roi_mean = float(np.average(field_roi, weights=self.roi_volumes))
            if len(field_gm) > 0:
                gm_mean = float(np.average(field_gm, weights=self.gm_volumes))
                focality = roi_mean / gm_mean if gm_mean > 0 else 0.0
            else:
                gm_mean = focality = 0.0
            n_elements = int(len(field_roi))

        return {
            "metric_max_roi": roi_max,
            "metric_mean_roi": roi_mean,
            "metric_mean_gm": gm_mean,
            "focality": focality,
            "n_elements": n_elements,
            "current_ch1_mA": self.config.current_mA,
            "current_ch2_mA": self.config.current_mA,
        }

    def run(
        self,
        e3_plus: list[str],
        e3_minus: list[str],
        e4_plus: list[str],
        e4_minus: list[str],
        all_combinations: bool,
    ) -> Dict[str, Dict[str, float]]:
        total = count_combinations(
            e3_plus, e3_minus, e4_plus, e4_minus, [(self.config.current_mA, self.config.current_mA)], all_combinations
        )
        self.logger.info("Secondary exhaustive search combinations: %d", total)
        results: Dict[str, Dict[str, float]] = {}

        for i, (ep3, em3, ep4, em4, _currents) in enumerate(
            generate_montage_combinations(
                e3_plus,
                e3_minus,
                e4_plus,
                e4_minus,
                [(self.config.current_mA, self.config.current_mA)],
                all_combinations,
            ),
            1,
        ):
            name = (
                f"{ep3}_{em3}_and_{ep4}_{em4}_"
                f"I-{self.config.current_mA:.1f}mA"
            )
            key = f"secondary_field_{name}.json"
            self.logger.info("[%d/%d] %s", i, total, name)
            results[key] = self.score_candidate(ep3, em3, ep4, em4)

        return results


def _save_secondary_results(
    results: Dict[str, Dict[str, float]],
    output_dir: str,
    logger: logging.Logger,
) -> tuple[str, str, str | None, str | None]:
    json_path = os.path.join(output_dir, "analysis_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    csv_path = os.path.join(output_dir, "final_output.csv")
    header = [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "MetricMax_ROI",
        "MetricMean_ROI",
        "MetricMean_GM",
        "Focality",
        "Composite_Index",
        "n_elements",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for name, data in results.items():
            writer.writerow(
                [
                    name,
                    f"{data['current_ch1_mA']:.1f}",
                    f"{data['current_ch2_mA']:.1f}",
                    f"{data['metric_max_roi']:.4f}",
                    f"{data['metric_mean_roi']:.4f}",
                    f"{data['metric_mean_gm']:.4f}",
                    f"{data['focality']:.4f}",
                    f"{data['metric_mean_roi'] * data['focality']:.4f}",
                    data["n_elements"],
                ]
            )
    best_csv_path = None
    if results:
        best_name, best_data = max(
            results.items(),
            key=lambda item: item[1]["metric_mean_roi"] * item[1]["focality"],
        )
        best_csv_path = os.path.join(output_dir, "best_composite.csv")
        with open(best_csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Montage",
                    "Current_mA",
                    "MetricMax_ROI",
                    "MetricMean_ROI",
                    "MetricMean_GM",
                    "Focality",
                    "Composite_Index",
                    "n_elements",
                ]
            )
            writer.writerow(
                [
                    best_name,
                    f"{best_data['current_ch1_mA']:.1f}",
                    f"{best_data['metric_max_roi']:.4f}",
                    f"{best_data['metric_mean_roi']:.4f}",
                    f"{best_data['metric_mean_gm']:.4f}",
                    f"{best_data['focality']:.4f}",
                    f"{best_data['metric_mean_roi'] * best_data['focality']:.4f}",
                    best_data["n_elements"],
                ]
            )

    timax_vals = [data["metric_max_roi"] for data in results.values()]
    timean_vals = [data["metric_mean_roi"] for data in results.values()]
    foc_vals = [data["focality"] for data in results.values()]
    plot_results = {
        name: {
            "secondary_TImax_ROI": data["metric_max_roi"],
            "secondary_TImean_ROI": data["metric_mean_roi"],
            "secondary_TImean_GM": data["metric_mean_gm"],
            "secondary_Focality": data["focality"],
            "secondary_n_elements": data["n_elements"],
            "current_ch1_mA": data["current_ch1_mA"],
            "current_ch2_mA": data["current_ch2_mA"],
        }
        for name, data in results.items()
    }
    viz_paths = generate_plots(
        plot_results,
        "secondary",
        output_dir,
        logger,
        timax_vals,
        timean_vals,
        foc_vals,
    )
    scatter_path = None
    montage_dist_path = None
    for path in viz_paths:
        if not path:
            continue
        if path.endswith("intensity_vs_focality_scatter.png"):
            scatter_path = path
        if path.endswith("montage_distributions.png"):
            montage_dist_path = path
    logger.info("Results saved to %s and %s", json_path, csv_path)
    if best_csv_path:
        logger.info("Best composite summary: %s", best_csv_path)
    return json_path, csv_path, scatter_path, montage_dist_path


def run_secondary_ex_search(config: SecondaryExConfig) -> SecondaryExResult:
    pm = get_path_manager(config.project_dir)
    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(
        logs_dir, f'secondary_ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
    )
    logger_name = f"tit.opt.secondary_ex_search.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    logger = logging.getLogger(logger_name)

    logger.info("Secondary Ex-Search")
    logger.info("Subject: %s", config.subject_id)
    logger.info("Base montage: %s", config.base_montage)
    logger.info("Metric: %s", config.metric)

    engine = SecondaryExSearchEngine(config, logger)
    engine.initialize()

    if isinstance(config.electrodes, PoolElectrodes):
        pool = config.electrodes.electrodes
        e3_plus = e3_minus = e4_plus = e4_minus = pool
        all_combinations = True
    else:
        e3_plus = config.electrodes.e1_plus
        e3_minus = config.electrodes.e1_minus
        e4_plus = config.electrodes.e2_plus
        e4_minus = config.electrodes.e2_minus
        all_combinations = False

    run_name = f"{config.roi_name.replace('.csv', '')}_{config.base_montage}_{config.metric}"
    output_dir = pm.ensure(os.path.join(pm.ex_search(config.subject_id), "secondary", run_name))
    results = engine.run(
        e3_plus, e3_minus, e4_plus, e4_minus, all_combinations
    )
    json_path, csv_path, scatter_path, dist_path = _save_secondary_results(
        results, output_dir, logger
    )
    best_composite_csv = os.path.join(output_dir, "best_composite.csv")
    if not os.path.exists(best_composite_csv):
        best_composite_csv = None

    return SecondaryExResult(
        success=True,
        output_dir=output_dir,
        n_combinations=len(results),
        results_csv=csv_path,
        results_json=json_path,
        best_composite_csv=best_composite_csv,
        scatter_png=scatter_path,
        montage_distribution_png=dist_path,
    )
