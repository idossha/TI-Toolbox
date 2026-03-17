"""Result saving and visualization for exhaustive search."""


import csv
import json
import os
import re
from typing import Any


def save_json(results: dict, output_dir: str, logger: Any) -> str:
    """Write results dict to JSON."""
    path = os.path.join(output_dir, "analysis_results.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=4)
    logger.info(f"Results saved to: {path}")
    return path


def build_csv_rows(
    results: dict, roi_name: str
) -> tuple[list[list], list[float], list[float], list[float], list[float]]:
    """Build CSV rows and extract metric arrays for plotting."""
    header = [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "TImax_ROI",
        "TImean_ROI",
        "TImean_GM",
        "Focality",
        "Composite_Index",
        "n_elements",
    ]
    rows = [header]
    timax_vals, timean_vals, foc_vals, comp_vals = [], [], [], []

    for mesh_name, data in results.items():
        name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
        ti_max = data[f"{roi_name}_TImax_ROI"]
        ti_mean = data[f"{roi_name}_TImean_ROI"]
        ti_mean_gm = data[f"{roi_name}_TImean_GM"]
        focality = data[f"{roi_name}_Focality"]
        composite = ti_mean * focality

        rows.append(
            [
                name,
                f"{data.get('current_ch1_mA', 0):.1f}",
                f"{data.get('current_ch2_mA', 0):.1f}",
                f"{ti_max:.4f}",
                f"{ti_mean:.4f}",
                f"{ti_mean_gm:.4f}",
                f"{focality:.4f}",
                f"{composite:.4f}",
                data.get(f"{roi_name}_n_elements", 0),
            ]
        )
        timax_vals.append(ti_max)
        timean_vals.append(ti_mean)
        foc_vals.append(focality)
        comp_vals.append(composite)

    return rows, timax_vals, timean_vals, foc_vals, comp_vals


def save_csv(results: dict, roi_name: str, output_dir: str, logger: Any) -> str:
    """Write final_output.csv."""
    rows, *_ = build_csv_rows(results, roi_name)
    path = os.path.join(output_dir, "final_output.csv")
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    logger.info(f"CSV output: {path}")
    return path


def generate_plots(
    results: dict,
    roi_name: str,
    output_dir: str,
    logger: Any,
    timax_vals: list[float],
    timean_vals: list[float],
    foc_vals: list[float],
) -> list[str]:
    """Generate histogram and scatter plot visualizations."""
    from tit.plotting.ti_metrics import (
        plot_intensity_vs_focality,
        plot_montage_distributions,
    )

    saved = []
    if not (timax_vals or timean_vals or foc_vals):
        return saved

    logger.info("Generating visualizations...")

    hist_path = os.path.join(output_dir, "montage_distributions.png")
    saved.append(
        plot_montage_distributions(
            timax_values=timax_vals,
            timean_values=timean_vals,
            focality_values=foc_vals,
            output_file=hist_path,
            dpi=300,
        )
    )

    intensity, focality, composite = [], [], []
    for data in results.values():
        ti_mean = data.get(f"{roi_name}_TImean_ROI")
        foc = data.get(f"{roi_name}_Focality")
        if ti_mean is not None and foc is not None:
            intensity.append(ti_mean)
            focality.append(foc)
            composite.append(ti_mean * foc)

    scatter_path = os.path.join(output_dir, "intensity_vs_focality_scatter.png")
    saved.append(
        plot_intensity_vs_focality(
            intensity=intensity,
            focality=focality,
            composite=composite,
            output_file=scatter_path,
            dpi=300,
        )
    )

    return saved


def process_and_save(
    results: dict, roi_name: str, output_dir: str, logger: Any
) -> dict:
    """Full results pipeline: JSON + CSV + plots. Returns summary dict."""
    json_path = save_json(results, output_dir, logger)
    rows, timax_vals, timean_vals, foc_vals, comp_vals = build_csv_rows(
        results, roi_name
    )
    csv_path = save_csv(results, roi_name, output_dir, logger)
    viz_paths = generate_plots(
        results, roi_name, output_dir, logger, timax_vals, timean_vals, foc_vals
    )

    def _range(vals):
        return (min(vals), max(vals)) if vals else None

    return {
        "json_path": json_path,
        "csv_path": csv_path,
        "visualization_paths": viz_paths,
        "summary_stats": {
            "total_montages": len(results),
            "timax_range": _range(timax_vals),
            "timean_range": _range(timean_vals),
            "focality_range": _range(foc_vals),
            "composite_range": _range(comp_vals),
        },
    }
