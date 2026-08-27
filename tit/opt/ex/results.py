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
generate_plots
    Create histogram and scatter-plot PNGs.
generate_electrode_maps
    Create the electrode heatmap and strength/focality montage maps.
regenerate_plots
    Rebuild the electrode maps from an existing run's ``final_output.csv``
    (also ``simnibs_python -m tit.opt.ex.results <run_dir> [--eeg-csv CSV]``).
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
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any

MONTAGE_MAP_TOP_N = 150
HEATMAP_TOP_N = 50


def save_run_config(config, n_combinations: int, output_dir: str, logger: Any) -> str:
    """Write run configuration metadata to JSON for reproducibility.

    Parameters
    ----------
    config : ExConfig or MExConfig
        Exhaustive-search (2-pair) or multipolar exhaustive-search (4-pair)
        configuration dataclass.  The current-parameter fields differ
        between the two (``total_current``/``current_step``/``channel_limit``
        vs. a flat ``current_mA``), so both are recorded when present.
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
            f.name: getattr(config.electrodes, f.name)
            for f in dataclass_fields(config.electrodes)
        }

    run_info = {
        "subject_id": config.subject_id,
        "roi_name": config.roi_name,
        "roi_radius": config.roi_radius,
        "leadfield_hdf": config.leadfield_hdf,
        "electrode_mode": electrode_mode,
        "electrodes": electrode_info,
        "n_combinations": n_combinations,
        "run_name": config.run_name,
    }
    if hasattr(config, "total_current"):
        run_info["total_current_mA"] = config.total_current
        run_info["current_step_mA"] = config.current_step
        run_info["channel_limit_mA"] = config.channel_limit
    if hasattr(config, "current_mA"):
        run_info["current_mA"] = config.current_mA
    if hasattr(config, "channels"):
        run_info["channels"] = config.channels
    if hasattr(config, "symmetric_bucket"):
        run_info["symmetric_bucket"] = config.symmetric_bucket
        run_info["symmetry_pairing"] = (
            config.symmetry_pairing if config.symmetric_bucket else None
        )
        run_info["symmetry_eeg_csv"] = config.symmetry_eeg_csv

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


def generate_plots(
    results: dict,
    roi_name: str,
    output_dir: str,
    logger: Any,
    timax_vals: list[float],
    timean_vals: list[float],
    foc_vals: list[float],
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


_MONTAGE_SUFFIX = re.compile(r"_I1?-[\d.]+mA(?:_I2-[\d.]+mA)?$")


def parse_montage_string(montage: str) -> list[str]:
    """Electrode labels of a ``final_output.csv`` montage string.

    Handles ``A_B <> C_D`` (ex-search) and ``A_B <> C_D <> E_F <> G_H``
    (m-ex-search), stripping the ``_I1-..mA_I2-..mA`` / ``_I-..mA`` suffix.
    """
    montage = _MONTAGE_SUFFIX.sub("", montage.strip())
    electrodes = []
    for pair in montage.split("<>"):
        a, sep, b = pair.strip().partition("_")
        if not sep or not a or not b:
            raise ValueError(f"Cannot parse electrode pair {pair!r} in {montage!r}")
        electrodes.extend([a, b])
    return electrodes


def montage_score_records(results: dict, roi_name: str) -> list[dict]:
    """Per-montage records for the electrode maps.

    Uses the electrode tuple the engine stored under ``"electrodes"`` (4 or
    8 labels) and falls back to parsing the mesh key for results produced
    without it.
    """
    records = []
    for mesh_name, data in results.items():
        ti_mean = data.get(f"{roi_name}_TImean_ROI")
        focality = data.get(f"{roi_name}_Focality")
        if ti_mean is None or focality is None:
            continue
        name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name)
        electrodes = data.get("electrodes")
        if not electrodes:
            electrodes = parse_montage_string(name.replace("_and_", " <> "))
        records.append(
            {
                "montage": name,
                "electrodes": list(electrodes),
                "timean": float(ti_mean),
                "focality": float(focality),
                "composite": float(ti_mean) * float(focality),
            }
        )
    return records


def montage_score_records_from_csv(csv_path: str | Path) -> list[dict]:
    """Records for the electrode maps read back from ``final_output.csv``."""
    records = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                ti_mean = float(row["TImean_ROI"])
                focality = float(row["Focality"])
            except (KeyError, TypeError, ValueError):
                continue
            records.append(
                {
                    "montage": row["Montage"],
                    "electrodes": parse_montage_string(row["Montage"]),
                    "timean": ti_mean,
                    "focality": focality,
                    "composite": ti_mean * focality,
                }
            )
    return records


def generate_electrode_maps(
    records: list[dict],
    eeg_positions_csv: str | Path,
    output_dir: str,
    logger: Any,
) -> list[str]:
    """Write ``electrode_score_heatmap.png``, ``montage_strength_map.png`` and
    ``montage_focality_map.png`` into *output_dir*."""
    from tit.plotting.ti_metrics import (
        plot_electrode_score_heatmap,
        plot_montage_score_map,
    )

    if not records:
        return []
    title_prefix = "mTI Search" if len(records[0]["electrodes"]) > 4 else "Ex-Search"
    eeg_positions_csv = str(eeg_positions_csv)
    saved = []

    heatmap = plot_electrode_score_heatmap(
        eeg_positions_csv=eeg_positions_csv,
        montage_scores=records,
        output_file=os.path.join(output_dir, "electrode_score_heatmap.png"),
        top_n=HEATMAP_TOP_N,
        dpi=300,
        title_prefix=title_prefix,
    )
    if heatmap:
        saved.append(heatmap)
        logger.info(f"Electrode score heatmap: {heatmap}")
    else:
        logger.info("Electrode score heatmap skipped: no montage matches the EEG CSV")

    for filename, kwargs in (
        (
            "montage_strength_map.png",
            {
                "metric_key": "timean",
                "metric_label": "TImean_ROI (V/m)",
                "title_metric": "ROI Strength",
                "cmap_name": ("#003b70", "#d7191c"),
            },
        ),
        (
            "montage_focality_map.png",
            {
                "metric_key": "focality",
                "metric_label": "Focality",
                "title_metric": "Focality",
                "cmap_name": ("#003b70", "#f28e2b"),
            },
        ),
    ):
        path = plot_montage_score_map(
            eeg_positions_csv=eeg_positions_csv,
            montage_scores=records,
            output_file=os.path.join(output_dir, filename),
            top_n=MONTAGE_MAP_TOP_N,
            dpi=300,
            title_prefix=title_prefix,
            **kwargs,
        )
        if path:
            saved.append(path)
            logger.info(f"Montage map: {path}")
        else:
            logger.info(f"{filename} skipped: no montage matches the EEG CSV")
    return saved


def _eeg_positions_csv_for_config(config) -> Path | None:
    from tit.opt.ex.symmetry import resolve_eeg_positions_csv
    from tit.paths import get_path_manager

    try:
        return resolve_eeg_positions_csv(config, get_path_manager())
    except (RuntimeError, ValueError, OSError):
        # No project directory (e.g. unit tests calling process_and_save
        # directly): the maps are optional, skip them.
        return None


def regenerate_plots(run_dir: str | Path, eeg_csv: str | Path | None = None) -> list[str]:
    """Rebuild the electrode maps of an existing ex-/m-ex-search run.

    Reads ``final_output.csv`` in *run_dir* and writes the three map PNGs
    next to it.  *eeg_csv* defaults to the CSV inferred from the
    ``leadfield_hdf`` recorded in ``run_config.json`` (the subject's
    ``m2m_*/eeg_positions/{net}.csv`` next to the leadfields directory,
    or the bundled template for known nets).
    """
    import logging

    from tit.opt.ex.symmetry import infer_symmetry_eeg_csv

    run_dir = Path(run_dir)
    logger = logging.getLogger("tit.opt.ex_search.results")
    csv_path = run_dir / "final_output.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"No final_output.csv in {run_dir}")

    if eeg_csv is None:
        run_config_path = run_dir / "run_config.json"
        if not run_config_path.is_file():
            raise ValueError(
                f"No run_config.json in {run_dir}; pass eeg_csv explicitly"
            )
        with open(run_config_path) as f:
            run_config = json.load(f)
        if run_config.get("symmetry_eeg_csv"):
            eeg_csv = run_config["symmetry_eeg_csv"]
        else:
            leadfield = Path(run_config["leadfield_hdf"])
            eeg_dir = (
                leadfield.parent.parent
                / f"m2m_{run_config['subject_id']}"
                / "eeg_positions"
            )
            eeg_csv = infer_symmetry_eeg_csv(leadfield, eeg_dir)
        if eeg_csv is None:
            raise ValueError(
                f"Could not infer an EEG-position CSV from {run_config['leadfield_hdf']}; "
                "pass eeg_csv explicitly"
            )
    if not Path(eeg_csv).is_file():
        raise FileNotFoundError(f"EEG-position CSV not found: {eeg_csv}")

    records = montage_score_records_from_csv(csv_path)
    if not records:
        raise ValueError(f"{csv_path} has no montage rows")
    return generate_electrode_maps(records, eeg_csv, str(run_dir), logger)


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
    viz_paths = generate_plots(
        results, roi_name, output_dir, logger, timax_vals, timean_vals, foc_vals
    )
    if results:
        eeg_positions_csv = _eeg_positions_csv_for_config(config)
        if eeg_positions_csv is None:
            logger.info(
                "Electrode maps skipped: no EEG-position CSV found for "
                f"{config.leadfield_hdf} (set symmetry_eeg_csv to enable them)"
            )
        else:
            viz_paths += generate_electrode_maps(
                montage_score_records(results, roi_name),
                eeg_positions_csv,
                output_dir,
                logger,
            )

    def _range(vals):
        return (min(vals), max(vals)) if vals else None

    return {
        "config_json_path": config_json_path,
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


def main(argv: list[str] | None = None) -> None:
    """``simnibs_python -m tit.opt.ex.results <run_dir> [--eeg-csv CSV]``."""
    import argparse
    import logging

    parser = argparse.ArgumentParser(
        description="Regenerate the electrode-map figures of an ex-/m-ex-search run."
    )
    parser.add_argument("run_dir", help="Run directory containing final_output.csv")
    parser.add_argument(
        "--eeg-csv",
        default=None,
        help="EEG-position CSV (default: inferred from run_config.json)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for path in regenerate_plots(args.run_dir, args.eeg_csv):
        print(path)


if __name__ == "__main__":
    main()
