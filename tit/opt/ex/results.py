"""Result persistence and visualization for TI exhaustive search.

Handles writing run metadata (JSON), per-montage CSV tables, and
histogram / scatter-plot visualizations after an exhaustive search
completes.

Public API
----------
save_run_config
    Serialize run parameters to a JSON file.
build_csv_rows
    Convert the results dict into CSV-ready rows and metric arrays.
save_csv
    Write ``final_output.csv``.
save_best_composite_csv
    Write ``best_composite.csv`` with the top composite-index montage.
generate_plots
    Create histogram and scatter-plot PNGs.
process_and_save
    Convenience wrapper that runs the full output pipeline.

See Also
--------
tit.opt.ex.ex_search : Orchestrator that calls :func:`process_and_save`.
"""

import csv
import json
import os
import re
from pathlib import Path
from typing import Any


MONTAGE_MAP_TOP_N = 150


def save_run_config(config, n_combinations: int, output_dir: str, logger: Any) -> str:
    """Write run configuration metadata to JSON for reproducibility.

    Parameters
    ----------
    config : ExConfig
        Exhaustive-search configuration dataclass.
    n_combinations : int
        Total number of montage combinations evaluated.
    output_dir : str
        Directory where ``run_config.json`` will be written.
    logger : logging.Logger
        Logger instance for status messages.

    Returns
    -------
    str
        Path to the saved JSON file.
    """
    if isinstance(config.electrodes, config.PoolElectrodes):
        electrode_mode = "pool"
        electrode_info = {"electrodes": config.electrodes.electrodes}
    else:
        electrode_mode = "bucket"
        electrode_info = {
            "e1_plus": config.electrodes.e1_plus,
            "e1_minus": config.electrodes.e1_minus,
            "e2_plus": config.electrodes.e2_plus,
            "e2_minus": config.electrodes.e2_minus,
        }

    run_info = {
        "subject_id": config.subject_id,
        "roi_name": config.roi_name,
        "roi_radius": config.roi_radius,
        "leadfield_hdf": config.leadfield_hdf,
        "electrode_mode": electrode_mode,
        "electrodes": electrode_info,
        "total_current_mA": config.total_current,
        "current_step_mA": config.current_step,
        "channel_limit_mA": config.channel_limit,
        "n_combinations": n_combinations,
        "run_name": config.run_name,
    }

    path = os.path.join(output_dir, "run_config.json")
    with open(path, "w") as f:
        json.dump(run_info, f, indent=2)
    logger.info(f"Run config saved to: {path}")
    return path


def build_csv_rows(
    results: dict, roi_name: str
) -> tuple[list[list], list[float], list[float], list[float], list[float]]:
    """Build CSV rows and extract per-montage metric arrays.

    Parameters
    ----------
    results : dict
        Mapping of mesh filename to per-montage metric dict.
    roi_name : str
        ROI name prefix used to look up metric keys
        (e.g. ``'{roi_name}_TImax_ROI'``).

    Returns
    -------
    rows : list of list
        Rows suitable for ``csv.writer``, including a header row.
    timax_vals : list of float
        TI-max values for each montage.
    timean_vals : list of float
        TI-mean values for each montage.
    foc_vals : list of float
        Focality values for each montage.
    comp_vals : list of float
        Composite index (``timean * focality``) for each montage.
    """
    header = [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "TImax_ROI",
        "TImean_ROI",
        "TImean_GM",
        "Focality",
        "Composite_Index",
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
            ]
        )
        timax_vals.append(ti_max)
        timean_vals.append(ti_mean)
        foc_vals.append(focality)
        comp_vals.append(composite)

    return rows, timax_vals, timean_vals, foc_vals, comp_vals


def save_csv(results: dict, roi_name: str, output_dir: str, logger: Any) -> str:
    """Write ``final_output.csv`` with one row per evaluated montage.

    Parameters
    ----------
    results : dict
        Mapping of mesh filename to per-montage metric dict.
    roi_name : str
        ROI name prefix for metric key lookup.
    output_dir : str
        Directory where the CSV will be written.
    logger : logging.Logger
        Logger instance for status messages.

    Returns
    -------
    str
        Path to the saved CSV file.
    """
    rows, *_ = build_csv_rows(results, roi_name)
    path = os.path.join(output_dir, "final_output.csv")
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    logger.info(f"CSV output: {path}")
    return path


def save_best_composite_csv(
    results: dict, roi_name: str, output_dir: str, logger: Any
) -> str | None:
    """Write ``best_composite.csv`` with the highest composite-index montage.

    The composite index is the same value used in ``final_output.csv``:
    ``TImean_ROI * Focality``.
    """
    rows, *_ = build_csv_rows(results, roi_name)
    if len(rows) <= 1:
        logger.info("No montage rows available for best-composite summary")
        return None

    header = rows[0]
    composite_index = header.index("Composite_Index")
    best_row = max(rows[1:], key=lambda row: float(row[composite_index]))

    path = os.path.join(output_dir, "best_composite.csv")
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([header, best_row])
    logger.info(f"Best composite output: {path}")
    return path


def generate_plots(
    results: dict,
    roi_name: str,
    output_dir: str,
    logger: Any,
    timax_vals: list[float],
    timean_vals: list[float],
    foc_vals: list[float],
    eeg_positions_csv: str | None = None,
) -> list[str]:
    """Generate histogram and scatter-plot PNGs for search results.

    Parameters
    ----------
    results : dict
        Mapping of mesh filename to per-montage metric dict.
    roi_name : str
        ROI name prefix for metric key lookup.
    output_dir : str
        Directory where images will be saved.
    logger : logging.Logger
        Logger instance.
    timax_vals : list of float
        TI-max values across montages.
    timean_vals : list of float
        TI-mean values across montages.
    foc_vals : list of float
        Focality values across montages.

    Returns
    -------
    list of str
        Paths to the saved plot files.
    """
    from tit.plotting.ti_metrics import (
        plot_electrode_score_heatmap,
        plot_intensity_vs_focality,
        plot_montage_score_map,
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

    if eeg_positions_csv:
        montage_score_records = _build_montage_score_records(results, roi_name)
        score_map_path = os.path.join(output_dir, "montage_score_map.png")
        score_map = plot_montage_score_map(
            eeg_positions_csv=eeg_positions_csv,
            montage_scores=montage_score_records,
            output_file=score_map_path,
            top_n=MONTAGE_MAP_TOP_N,
            dpi=300,
        )
        if score_map:
            saved.append(score_map)
            logger.info(f"Montage score map: {score_map}")
        else:
            logger.info("Montage score map skipped: no plottable montage records")

        strength_map_path = os.path.join(output_dir, "montage_strength_map.png")
        strength_map = plot_montage_score_map(
            eeg_positions_csv=eeg_positions_csv,
            montage_scores=montage_score_records,
            output_file=strength_map_path,
            top_n=MONTAGE_MAP_TOP_N,
            dpi=300,
            metric_key="timean",
            metric_label="TImean_ROI (V/m)",
            title_metric="ROI Strength",
            cmap_name=("#003b70", "#d7191c"),
        )
        if strength_map:
            saved.append(strength_map)
            logger.info(f"Montage strength map: {strength_map}")
        else:
            logger.info("Montage strength map skipped: no plottable montage records")

        focality_map_path = os.path.join(output_dir, "montage_focality_map.png")
        focality_map = plot_montage_score_map(
            eeg_positions_csv=eeg_positions_csv,
            montage_scores=montage_score_records,
            output_file=focality_map_path,
            top_n=MONTAGE_MAP_TOP_N,
            dpi=300,
            metric_key="focality",
            metric_label="Focality",
            title_metric="Focality",
            cmap_name=("#003b70", "#f28e2b"),
        )
        if focality_map:
            saved.append(focality_map)
            logger.info(f"Montage focality map: {focality_map}")
        else:
            logger.info("Montage focality map skipped: no plottable montage records")

        heatmap_path = os.path.join(output_dir, "electrode_score_heatmap.png")
        heatmap = plot_electrode_score_heatmap(
            eeg_positions_csv=eeg_positions_csv,
            montage_scores=montage_score_records,
            output_file=heatmap_path,
            top_n=50,
            dpi=300,
        )
        if heatmap:
            saved.append(heatmap)
            logger.info(f"Electrode score heatmap: {heatmap}")
        else:
            logger.info("Electrode score heatmap skipped: no plottable records")

    return saved


def _build_montage_score_records(results: dict, roi_name: str) -> list[dict]:
    records = []
    pattern = re.compile(
        r"^TI_field_(?P<e1_plus>[^_]+)_(?P<e1_minus>[^_]+)_and_"
        r"(?P<e2_plus>[^_]+)_(?P<e2_minus>[^_]+)"
    )
    for mesh_name, data in results.items():
        match = pattern.match(mesh_name)
        if not match:
            continue
        ti_mean = data.get(f"{roi_name}_TImean_ROI")
        focality = data.get(f"{roi_name}_Focality")
        if ti_mean is None or focality is None:
            continue
        record = match.groupdict()
        record.update(
            {
                "montage": re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name),
                "composite": float(ti_mean) * float(focality),
                "timean": float(ti_mean),
                "focality": float(focality),
            }
        )
        records.append(record)
    return records


def _find_eeg_positions_csv(config) -> str | None:
    try:
        from tit.paths import get_path_manager

        pm = get_path_manager()
        eeg_dir = Path(pm.eeg_positions(config.subject_id))
    except (RuntimeError, ValueError, OSError, AttributeError):
        return None

    if not eeg_dir.is_dir():
        return None

    stem = Path(str(config.leadfield_hdf)).stem
    if "_leadfield_" in stem:
        net_name = stem.split("_leadfield_", 1)[1]
    elif stem.endswith("_leadfield"):
        net_name = stem[: -len("_leadfield")]
    else:
        net_name = stem

    for prefix in (f"{config.subject_id}_", config.subject_id):
        if net_name.startswith(prefix):
            net_name = net_name[len(prefix) :]
            break
    net_name = net_name.strip("_")

    candidates = [net_name]
    if net_name.endswith(".csv"):
        candidates.append(net_name[:-4])
    else:
        candidates.append(f"{net_name}.csv")

    for candidate in candidates:
        path = eeg_dir / candidate
        if path.is_file():
            return str(path)

    return None


def process_and_save(results: dict, config, output_dir: str, logger: Any) -> dict:
    """Run the full post-search output pipeline (JSON + CSV + plots).

    Parameters
    ----------
    results : dict
        Mapping of mesh filename to per-montage metric dict.
    config : ExConfig
        Exhaustive-search configuration.
    output_dir : str
        Root output directory for this search run.
    logger : logging.Logger
        Logger instance.

    Returns
    -------
    dict
        Summary with keys ``'config_json_path'``, ``'csv_path'``,
        ``'visualization_paths'``, and ``'summary_stats'``.
    """
    roi_name = config.roi_name
    config_json_path = save_run_config(config, len(results), output_dir, logger)
    rows, timax_vals, timean_vals, foc_vals, comp_vals = build_csv_rows(
        results, roi_name
    )
    csv_path = save_csv(results, roi_name, output_dir, logger)
    best_composite_csv = save_best_composite_csv(
        results, roi_name, output_dir, logger
    )
    eeg_positions_csv = _find_eeg_positions_csv(config)
    viz_paths = generate_plots(
        results,
        roi_name,
        output_dir,
        logger,
        timax_vals,
        timean_vals,
        foc_vals,
        eeg_positions_csv=eeg_positions_csv,
    )

    def _range(vals):
        return (min(vals), max(vals)) if vals else None

    return {
        "config_json_path": config_json_path,
        "csv_path": csv_path,
        "best_composite_csv": best_composite_csv,
        "visualization_paths": viz_paths,
        "summary_stats": {
            "total_montages": len(results),
            "timax_range": _range(timax_vals),
            "timean_range": _range(timean_vals),
            "focality_range": _range(foc_vals),
            "composite_range": _range(comp_vals),
        },
    }
