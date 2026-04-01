"""Save multi-polar DE search results to disk.

Writes config.json (full config + results summary) and top_k.csv
(best montages with metrics).
"""

import csv
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime

from tit.opt.config import FlexConfig, MultiPolarConfig


def _serialize_roi(roi) -> dict:
    """Convert an ROI dataclass to a plain dict with a type discriminator."""
    if isinstance(roi, FlexConfig.SphericalROI):
        return {"_type": "SphericalROI", **asdict(roi)}
    if isinstance(roi, FlexConfig.SubcorticalROI):
        return {"_type": "SubcorticalROI", **asdict(roi)}
    raise ValueError(f"Unknown ROI type: {type(roi)}")


def save_results(
    de_result: dict,
    config: MultiPolarConfig,
    output_dir: str,
    logger: logging.Logger,
) -> dict[str, str]:
    """Save DE search results to output_dir.

    Parameters
    ----------
    de_result : dict
        Result dict from ``run_de_search`` with keys: best_focality,
        best_montage, best_indices, n_iterations, n_evaluations,
        convergence_success, message.
    config : MultiPolarConfig
        The configuration used for this run.
    output_dir : str
        Directory to write results into.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    dict mapping output name to file path: {"config_json": ..., "top_k_csv": ...}
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    # ── config.json ───────────────────────────────────────────────────────
    config_data = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "subject_id": config.subject_id,
        "leadfield_hdf": config.leadfield_hdf,
        "n_pairs": config.n_pairs,
        "current_mA": config.current_mA,
        "roi": _serialize_roi(config.roi),
        "non_roi_method": config.non_roi_method,
        "non_roi": _serialize_roi(config.non_roi) if config.non_roi else None,
        "de_params": {
            "max_iterations": config.max_iterations,
            "population_size": config.population_size,
            "tolerance": config.tolerance,
            "mutation": config.mutation,
            "recombination": config.recombination,
            "n_multistart": config.n_multistart,
            "patience": config.patience,
            "min_electrode_distance": config.min_electrode_distance,
        },
        "result": {
            "best_focality": de_result["best_focality"],
            "best_montage": [
                {"plus": p, "minus": m, "current_mA": c}
                for p, m, c in de_result["best_montage"]
            ],
            "best_indices": de_result["best_indices"],
            "n_iterations": de_result["n_iterations"],
            "n_evaluations": de_result["n_evaluations"],
            "convergence_success": de_result["convergence_success"],
            "message": de_result["message"],
        },
    }

    config_path = os.path.join(output_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump(config_data, f, indent=2)
    paths["config_json"] = config_path
    logger.info(f"Config written to {config_path}")

    # ── top_k.csv ─────────────────────────────────────────────────────────
    # Build column headers based on n_pairs
    header = ["rank"]
    for i in range(1, config.n_pairs + 1):
        header.extend([f"pair{i}_plus", f"pair{i}_minus"])
    header.extend(["focality", "current_mA"])

    csv_path = os.path.join(output_dir, "top_k.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # Write the single best result
        montage = de_result["best_montage"]
        row = [1]  # rank
        for plus_name, minus_name, _mA in montage:
            row.extend([plus_name, minus_name])
        row.extend([de_result["best_focality"], config.current_mA])
        writer.writerow(row)

    paths["top_k_csv"] = csv_path
    logger.info(f"Top-K CSV written to {csv_path}")

    return paths
