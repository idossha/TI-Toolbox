"""Result persistence and figures for reciprocity search.

Writes one run directory:

``summary.json``
    Config echo, target, best montage, timings, candidate count.
``candidates.csv``
    Every evaluated candidate, ranked by the objective.
``reciprocity_scores.csv``
    Every electrode pair's reciprocity score and rank.
``montage.json``
    The winning montage in the shape the Simulator replays.
``run_config.json`` / ``final_output.csv``
    The same two files an ex-search run writes, so a reciprocity run appears
    in the Simulator's replay catalog (:mod:`tit.opt.candidate_catalog`)
    without a second reader.
``fig1_reciprocity_topomap.png`` / ``fig2_candidate_landscape.png`` /
``fig3_summary.png``
    The reciprocity map with the chosen pairs, where the winner sits among
    the candidates, and its intensity against the background.

Public API
----------
write_outputs
    Write every file above and return the paths.

See Also
--------
tit.opt.recip.recip.run_recip_search : Calls :func:`write_outputs`.
"""

from __future__ import annotations

import csv
import json
import os

import numpy as np

_CANDIDATE_HEADER = [
    "rank",
    "montage",
    "roi_mean",
    "roi_max",
    "roi_min",
    "gm_mean",
    "gm_p95",
    "focality_tf",
]


def montage_label(names: list[str], pairs: list[tuple[int, int]]) -> str:
    """``"Fz_Iz <> F2_I1"`` -- the montage spelling ``final_output.csv`` uses."""
    return " <> ".join(f"{names[a]}_{names[b]}" for a, b in pairs)


def topo_xy(positions: np.ndarray) -> np.ndarray:
    """Azimuthal-equidistant projection of electrode positions, seen from above."""
    centred = positions - positions.mean(axis=0)
    centred[:, 2] -= centred[:, 2].min() * 0.3
    radius = np.linalg.norm(centred, axis=1)
    theta = np.arccos(np.clip(centred[:, 2] / radius, -1, 1))
    phi = np.arctan2(centred[:, 1], centred[:, 0])
    return np.c_[theta * np.cos(phi), theta * np.sin(phi)]


def write_outputs(
    *,
    config,
    output_dir: str,
    mesh: dict,
    pairs: np.ndarray,
    scores: np.ndarray,
    order: np.ndarray,
    top_k: int,
    candidates: list[dict],
    target_centroid: np.ndarray,
    n_target_elements: int,
    direction: np.ndarray | None,
    timings: dict,
    leadfield_path: str,
    logger,
) -> dict:
    """Write every run file and return ``{name: path}`` plus the best record."""
    from tit.config_io import serialize_config

    names = mesh["names"]
    best = dict(candidates[0])
    best["montage"] = [[names[a], names[b]] for a, b in best["pairs"]]

    scores_csv = os.path.join(output_dir, "reciprocity_scores.csv")
    with open(scores_csv, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["rank", "electrode_a", "electrode_b", "score", "selected"])
        for rank, index in enumerate(order, start=1):
            a, b = pairs[index]
            writer.writerow(
                [
                    rank,
                    names[a],
                    names[b],
                    f"{scores[index]:.6g}",
                    int(rank <= top_k),
                ]
            )

    candidates_csv = os.path.join(output_dir, "candidates.csv")
    with open(candidates_csv, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(_CANDIDATE_HEADER)
        for record in candidates:
            writer.writerow(
                [
                    record["rank"],
                    montage_label(names, record["pairs"]),
                    f"{record['roi_mean']:.6f}",
                    f"{record['roi_max']:.6f}",
                    f"{record['roi_min']:.6f}",
                    f"{record['gm_mean']:.6f}",
                    f"{record['gm_p95']:.6f}",
                    f"{record['focality_tf']:.6f}",
                ]
            )

    # The ex-search pair of files, so the Simulator's replay catalog reads a
    # reciprocity run with its existing reader.
    run_config = {
        "subject_id": config.subject_id,
        "leadfield_hdf": leadfield_path,
        "run_name": config.run_name,
        "n_channels": config.n_channels,
        "current_mA": config.current_mA,
        "objective": config.objective,
        "focality_weight": config.focality_weight,
        "top_k": top_k,
        "gm_subsample": config.gm_subsample,
        "background": "non-ROI grey matter, random subsample (seed 0)",
    }
    run_config_json = os.path.join(output_dir, "run_config.json")
    with open(run_config_json, "w") as stream:
        json.dump(run_config, stream, indent=2)

    final_csv = os.path.join(output_dir, "final_output.csv")
    with open(final_csv, "w", newline="") as stream:
        writer = csv.writer(stream)
        current_columns = [f"Current_Ch{i + 1}_mA" for i in range(config.n_channels)]
        writer.writerow(
            [
                "Montage",
                *current_columns,
                "TImax_ROI",
                "TImean_ROI",
                "TImean_GM",
                "Focality",
                "Composite_Index",
            ]
        )
        for record in candidates:
            gm_mean = record["gm_mean"]
            focality = record["roi_mean"] / gm_mean if gm_mean > 0 else 0.0
            writer.writerow(
                [
                    montage_label(names, record["pairs"]),
                    *[f"{config.current_mA:.1f}"] * config.n_channels,
                    f"{record['roi_max']:.4f}",
                    f"{record['roi_mean']:.4f}",
                    f"{gm_mean:.4f}",
                    f"{focality:.4f}",
                    f"{record['roi_mean'] * focality:.4f}",
                ]
            )

    montage_json = os.path.join(output_dir, "montage.json")
    with open(montage_json, "w") as stream:
        json.dump(
            {
                "subject_id": config.subject_id,
                "leadfield_hdf": leadfield_path,
                "pairs": best["montage"],
                "currents_mA": [config.current_mA] * config.n_channels,
                "metrics": {
                    key: best[key]
                    for key in (
                        "roi_mean",
                        "roi_max",
                        "roi_min",
                        "gm_mean",
                        "gm_p95",
                        "focality_tf",
                    )
                },
            },
            stream,
            indent=2,
        )

    summary_json = os.path.join(output_dir, "summary.json")
    with open(summary_json, "w") as stream:
        json.dump(
            {
                "config": serialize_config(config),
                "leadfield_hdf": leadfield_path,
                "reference_electrode": mesh["reference"],
                "n_electrodes": len(names),
                "n_pairs": int(len(pairs)),
                "top_k": int(top_k),
                "n_candidates": len(candidates),
                "target": {
                    "centroid": [float(v) for v in target_centroid],
                    "n_elements": int(n_target_elements),
                    "direction": (
                        None if direction is None else list(map(float, direction))
                    ),
                },
                "best": best,
                "timings_s": timings,
            },
            stream,
            indent=2,
        )

    figures = _figures(
        output_dir, mesh, pairs, scores, candidates, best, config, logger
    )
    logger.info("Summary: %s", summary_json)
    logger.info("Candidates: %s", candidates_csv)
    return {
        "best": best,
        "summary_json": summary_json,
        "candidates_csv": candidates_csv,
        "scores_csv": scores_csv,
        "montage_json": montage_json,
        "run_config_json": run_config_json,
        "final_csv": final_csv,
        "figures": figures,
    }


def _figures(
    output_dir: str,
    mesh: dict,
    pairs: np.ndarray,
    scores: np.ndarray,
    candidates: list[dict],
    best: dict,
    config,
    logger,
) -> list[str]:
    """Write the three run figures; a plotting failure never fails the run."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - plotting is optional
        logger.warning("Figures skipped (matplotlib unavailable): %s", exc)
        return []

    names = mesh["names"]
    written = []
    try:
        # 1. Reciprocity map: the best score each electrode reaches, with the
        #    chosen pairs drawn on top.
        per_electrode = np.zeros(len(names))
        for (a, b), score in zip(pairs, scores):
            per_electrode[a] = max(per_electrode[a], score)
            per_electrode[b] = max(per_electrode[b], score)
        xy = topo_xy(mesh["positions"])
        figure, axes = plt.subplots(figsize=(6.5, 6))
        axes.tricontourf(
            xy[:, 0], xy[:, 1], per_electrode * 1e3, levels=40, cmap="RdBu_r"
        )
        axes.scatter(xy[:, 0], xy[:, 1], s=8, c="k", zorder=3)
        colors = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd"]
        for channel, (a, b) in enumerate(best["pairs"]):
            color = colors[channel % len(colors)]
            axes.plot(
                xy[[a, b], 0],
                xy[[a, b], 1],
                "-",
                color=color,
                lw=2.5,
                zorder=4,
                label=f"ch{channel + 1}: {names[a]}-{names[b]}",
            )
            axes.scatter(
                xy[[a, b], 0], xy[[a, b], 1], s=90, c=color, edgecolor="k", zorder=5
            )
        axes.set_aspect("equal")
        axes.axis("off")
        axes.set_title(
            "Reciprocity map (best pair score per electrode, mV/m per mA)", fontsize=10
        )
        axes.legend(fontsize=8, frameon=False, loc="lower center")
        path = os.path.join(output_dir, "fig1_reciprocity_topomap.png")
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)
        written.append(path)

        # 2. Where the winner sits among the evaluated candidates.
        key = "roi_mean" if config.objective == "intensity" else "focality_tf"
        values = np.array([record[key] for record in candidates])
        scale = 1e3 if key == "roi_mean" else 1.0
        figure, axes = plt.subplots(figsize=(7.5, 4))
        axes.hist(values * scale, bins=min(60, max(5, len(values) // 4)), color="#bbb")
        axes.axvline(
            best[key] * scale,
            color="#d62728",
            lw=2,
            label=f"best: {best[key] * scale:.1f}",
        )
        axes.set_xlabel("ROI mean TI (mV/m)" if key == "roi_mean" else "focality_tf")
        axes.set_ylabel("candidates")
        axes.set_title(f"Candidate landscape ({len(candidates)} montages)", fontsize=10)
        axes.legend(fontsize=8)
        path = os.path.join(output_dir, "fig2_candidate_landscape.png")
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)
        written.append(path)

        # 3. Intensity against background for the top montages.
        top = candidates[:5]
        x = np.arange(len(top))
        figure, axes = plt.subplots(figsize=(7.5, 3.8))
        axes.bar(
            x - 0.2, [r["roi_mean"] * 1e3 for r in top], 0.4, label="ROI mean (mV/m)"
        )
        axes.bar(
            x + 0.2,
            [r["gm_p95"] * 1e3 for r in top],
            0.4,
            label="non-ROI GM p95 (mV/m)",
        )
        axes.set_xticks(x)
        axes.set_xticklabels(
            [montage_label(names, r["pairs"]) for r in top], fontsize=7, rotation=15
        )
        axes.set_title(
            f"Top {len(top)} montages at {config.current_mA:.1f} mA per channel",
            fontsize=10,
        )
        axes.legend(fontsize=8)
        path = os.path.join(output_dir, "fig3_summary.png")
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)
        written.append(path)
    except Exception as exc:  # pragma: no cover - a figure must not fail a run
        logger.warning("Figure generation failed: %s", exc)
    return written
