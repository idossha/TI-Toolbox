"""Multi-subject group analysis.

Runs per-subject ROI analyses in-process via :class:`Analyzer`, aggregates the
results into a summary CSV with an AVERAGE row, and produces a 2x2 comparison
bar-chart saved as PDF.

Public API
----------
GroupResult
    Container for multi-subject group analysis outcomes.
run_group_analysis
    Run the same ROI analysis across multiple subjects and summarise.

See Also
--------
tit.analyzer.analyzer : Single-subject analyzer used per-subject.
"""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from tit.analyzer.analyzer import Analyzer, AnalysisResult
from tit.logger import add_file_handler
from tit.paths import PathManager, get_path_manager

logger = logging.getLogger(__name__)

_NUMERIC_COLS = [
    "ROI_Mean",
    "ROI_Max",
    "ROI_Min",
    "ROI_Focality",
    "GM_Mean",
    "GM_Max",
    "Normal_Mean",
    "Normal_Max",
    "Normal_Focality",
    "HF_Focality",
    "RMS_Focality",
    "TI_Selectivity",
]


@dataclass
class GroupResult:
    """Outcome of a multi-subject group analysis.

    Attributes
    ----------
    subject_results : dict of str to AnalysisResult
        Mapping of subject ID to its
        :class:`~tit.analyzer.analyzer.AnalysisResult`.
    summary_csv_path : pathlib.Path
        Path to the summary CSV (one row per subject plus an AVERAGE row).
    comparison_plot_path : pathlib.Path or None
        Path to the 2x2 comparison bar-chart PDF, or ``None`` if plotting
        failed.

    See Also
    --------
    run_group_analysis : Factory function that produces this result.
    AnalysisResult : Per-subject analysis container.
    """

    subject_results: dict[str, AnalysisResult]
    summary_csv_path: Path
    comparison_plot_path: Path | None


def run_group_analysis(
    subject_ids: list[str],
    simulation: str,
    space: str = "mesh",
    tissue_type: str = "GM",
    analysis_type: str = "spherical",
    center: tuple[float, float, float] | None = None,
    radius: float | None = None,
    coordinate_space: str = "subject",
    spheres: Sequence[tuple[float, float, float, float]] | None = None,
    atlas: str | None = None,
    region: str | list[str] | None = None,
    visualize: bool = False,
    output_dir: str | Path | None = None,
    field: str | None = None,
    mask_path: str | None = None,
) -> GroupResult:
    """Run the same ROI analysis across multiple subjects and summarise.

    Dispatches to ``analyze_sphere`` or ``analyze_cortex`` on each subject,
    builds a summary CSV (with an AVERAGE row), and generates a 2x2
    comparison bar-chart PDF.

    Parameters
    ----------
    subject_ids : list of str
        Subject identifiers (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name, shared by all subjects.
    space : str, optional
        ``"mesh"`` or ``"voxel"``. Default ``"mesh"``.
    tissue_type : str, optional
        ``"GM"``, ``"WM"``, or ``"both"`` (voxel only). Default ``"GM"``.
    analysis_type : str, optional
        ``"spherical"``, ``"cortical"``, ``"subcortical"`` or ``"mask"``.
        Default ``"spherical"``.
    center : tuple of float or None, optional
        ``(x, y, z)`` sphere centre; required when *analysis_type* is
        ``"spherical"``.
    radius : float or None, optional
        Sphere radius in mm; required when *analysis_type* is
        ``"spherical"``.
    coordinate_space : str, optional
        ``"subject"`` or ``"MNI"`` (spherical, subcortical and mask): the
        space of the sphere centre, the volume atlas or the mask. Default
        ``"subject"``; a group mask analysis requires ``"MNI"``.
    spheres : sequence of tuple of float or None, optional
        One ``(x, y, z, r)`` per sphere, unioned into a single ROI
        (spherical only). Takes precedence over *center*/*radius*.
    atlas : str or None, optional
        Atlas name (cortical and subcortical).
    region : str, list of str, or None, optional
        Region name or list of region names (cortical and subcortical).
    visualize : bool, optional
        Generate per-subject visualization artifacts. Default ``False``.
    output_dir : str, pathlib.Path, or None, optional
        Override output directory. If ``None``, each run writes to its own
        ``derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>[_<field>][_<tissue>]_<timestamp>/``
        (the field and tissue suffixes as :func:`group_run_name` adds them; a second
        run of the same name started in the same second gets ``_2``, ``_3``, ...). The
        per-subject analyses always go to each subject's own default folder.
    field : str or None, optional
        Field to analyze (``constants.FIELD_REGISTRY`` name, e.g.
        ``"TI_max"``, ``"TI_normal"``, ``"hf_peak"``). Default ``None``
        resolves the TI_max/mTI_max envelope per subject.
    mask_path : str or None, optional
        MNI-space NIfTI mask (``analysis_type="mask"`` only).

    Returns
    -------
    GroupResult
        Per-subject results, the summary CSV path
        (``group_summary.csv``), and the comparison plot path.

    Raises
    ------
    KeyError
        If *analysis_type* is not ``"spherical"``, ``"cortical"``,
        ``"subcortical"`` or ``"mask"``.
    ValueError
        If ``analysis_type="mask"`` with a non-MNI *coordinate_space* or an
        unreadable *mask_path*; if a sphere lacks a finite centre or a
        positive, finite radius (checked once, before any subject); or if a
        subject's analysis is refused (for example its ROI is empty), and
        then the message starts with ``sub-<id>:``.
    FileNotFoundError
        If a subject has no field file for *simulation* in *space*.

    Examples
    --------
    >>> from tit.analyzer import run_group_analysis
    >>> res = run_group_analysis(
    ...     subject_ids=["ernie", "101"], simulation="L_Insula", space="voxel",
    ...     analysis_type="spherical", center=(-35.0, 5.0, 5.0), radius=10.0,
    ...     coordinate_space="MNI",
    ... )  # doctest: +SKIP
    >>> res.summary_csv_path.name, sorted(res.subject_results)  # doctest: +SKIP
    ('group_summary.csv', ['101', 'ernie'])
    >>> run_group_analysis(["ernie", "101"], "L_Insula", space="mesh",
    ...                    analysis_type="cortical", atlas="DK40",
    ...                    region="lh.insula")  # doctest: +SKIP

    See Also
    --------
    Analyzer : Single-subject analyzer used internally per subject.
    GroupResult : Container for the returned outcomes.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    if analysis_type == "mask":
        from tit.opt.masks import validate_mask

        if coordinate_space.lower() != "mni":
            raise ValueError("Group mask analysis requires an MNI-space mask")
        validate_mask(mask_path)
    if analysis_type == "spherical":
        # The same sphere for every subject: refuse it once, blaming no subject.
        Analyzer._checked_spheres(spheres or [(*center, radius)])

    with track_operation(_const.TELEMETRY_OP_GROUP_ANALYSIS):
        run_name = group_run_name(
            simulation,
            space,
            analysis_type,
            center=center,
            radius=radius,
            coordinate_space=coordinate_space,
            spheres=spheres,
            region=region,
            mask_path=mask_path,
            field=field,
            tissue_type=tissue_type,
        )
        out = _resolve_output_dir(output_dir, run_name)

        # File handler so group analysis logs are persisted
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = out / f"group_analysis_{timestamp}.log"
        group_log = add_file_handler(log_file)
        try:
            logger.info(
                "Group analysis started: %d subjects, space=%s, type=%s",
                len(subject_ids),
                space,
                analysis_type,
            )

            dispatch: dict[str, callable] = {
                "spherical": lambda a: (
                    a.analyze_spheres(
                        spheres=spheres,
                        coordinate_space=coordinate_space,
                        visualize=visualize,
                    )
                    if spheres
                    else a.analyze_sphere(
                        center=center,
                        radius=radius,
                        coordinate_space=coordinate_space,
                        visualize=visualize,
                    )
                ),
                "mask": lambda a: a.analyze_mask(
                    mask_path=mask_path,
                    coordinate_space=coordinate_space,
                    visualize=visualize,
                ),
                "cortical": lambda a: a.analyze_cortex(
                    atlas=atlas,
                    region=region,
                    visualize=visualize,
                ),
                "subcortical": lambda a: a.analyze_subcortical(
                    atlas=atlas,
                    region=region,
                    coordinate_space=coordinate_space,
                    visualize=visualize,
                ),
            }
            analyze_fn = dispatch[analysis_type]

            results: dict[str, AnalysisResult] = {}
            for sid in subject_ids:
                logger.info("Analyzing subject %s", sid)
                analyzer = None
                try:
                    analyzer = Analyzer(
                        sid, simulation, space, tissue_type, field=field
                    )
                    results[sid] = analyze_fn(analyzer)
                except ValueError as exc:
                    # An empty or invalid target is per subject (anatomy differs): say whose.
                    raise ValueError(f"sub-{sid}: {exc}") from exc
                finally:
                    # Each subject's own log holds its own analysis only, not the next one's.
                    handler = getattr(analyzer, "_log_handler", None)
                    if handler is not None:
                        _detach_log_handler(handler)

            df = _build_summary_df(results)
            csv_path = out / "group_summary.csv"
            df.to_csv(csv_path, index=False, float_format="%.3f")
            logger.info("Summary CSV written to %s", csv_path)

            plot_path = _generate_comparison_plot(df, out)
            logger.info("Comparison plot written to %s", plot_path)

            return GroupResult(
                subject_results=results,
                summary_csv_path=csv_path,
                comparison_plot_path=plot_path,
            )
        finally:
            _detach_log_handler(group_log)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _target_label(
    analysis_type, center, radius, coordinate_space, spheres, region, mask_path
) -> str:
    """The run's target in a few words, for its folder name."""
    if analysis_type == "spherical":
        if spheres and len(spheres) > 1:
            return PathManager.spherical_union_analysis_name(spheres, coordinate_space)
        x, y, z, r = spheres[0] if spheres else (*center, radius)
        return PathManager.spherical_analysis_name(x, y, z, r, coordinate_space)
    if analysis_type == "mask":
        return Path(mask_path).name.split(".")[0]
    regions = region if isinstance(region, list) else [region]
    return "+".join(str(r) for r in regions if r)


def group_run_name(
    simulation: str,
    space: str,
    analysis_type: str,
    *,
    center=None,
    radius=None,
    coordinate_space: str = "subject",
    spheres=None,
    region=None,
    mask_path=None,
    field: str | None = None,
    tissue_type: str | None = None,
) -> str:
    """``<simulation>_<space>_<target>[_<field>][_<tissue>]``: what a group run is named by.

    The target as :func:`_target_label` words it, then the field and tissue the way an
    analysis folder carries them (:meth:`PathManager.analysis_variant_suffix`), so a
    TI_max and an hf_peak run of one ROI are told apart by name too.

    Args:
        simulation: Simulation folder name shared by the subjects.
        space: ``"mesh"`` or ``"voxel"``.
        analysis_type: ``"spherical"``, ``"cortical"``, ``"subcortical"`` or ``"mask"``.
        center: Sphere centre ``(x, y, z)`` (spherical).
        radius: Sphere radius in mm (spherical).
        coordinate_space: ``"subject"`` or ``"MNI"``.
        spheres: One ``(x, y, z, r)`` per sphere of a union (spherical).
        region: Region name or names (cortical, subcortical).
        mask_path: Mask file (mask).
        field: The analysed field; ``None`` or the envelope adds no suffix.
        tissue_type: Voxel tissue; ``None`` or ``"GM"`` adds no suffix.

    Returns:
        The run name, before :func:`group_output_dir` makes it folder-safe and
        stamps it, e.g. ``"M1_voxel_sphere_x-35.00_y5.00_z5.00_r10.0_subject_WM"``.
    """
    target = _target_label(
        analysis_type, center, radius, coordinate_space, spheres, region, mask_path
    )
    variant = PathManager.analysis_variant_suffix(space, field, tissue_type)
    return f"{simulation}_{space}_{target}{variant}"


def group_output_dir(
    output_dir: str | Path | None, run_name: str, stamp: str | None = None
) -> str:
    """The folder a group run writes its summary into (not created).

    Shared with the plan, which previews the folder a run started now would name.

    Args:
        output_dir: The run's explicit output folder, used verbatim when set.
        run_name: :func:`group_run_name`'s name; characters a folder name may not carry
            become ``_`` and it is cut so the stamped name fits 128 characters.
        stamp: ``YYYYmmdd_HHMMSS`` of the second the run starts; now when ``None``.

    Returns:
        *output_dir*, or ``derivatives/ti-toolbox/group_analysis/<run_name>_<stamp>``.
    """
    if output_dir:
        return str(output_dir)
    pm = get_path_manager()
    stamp = stamp or time.strftime("%Y%m%d_%H%M%S")
    # A folder name is letters, digits, ".", "_", "-" and at most 128 characters.
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", run_name)[: 127 - len(stamp)]
    return pm.group_analysis(f"{name.strip('._-')}_{stamp}")


def _resolve_output_dir(output_dir: str | Path | None, run_name: str) -> Path:
    """Return (and create) the output directory.

    Without *output_dir* every run gets its own
    ``derivatives/ti-toolbox/group_analysis/<run_name>_<YYYYmmdd_HHMMSS>/``: one fixed
    folder let each run overwrite the last one's summary and plot, and one Run press in
    the Analyzer submits one group job per sphere or region. The folder is created
    exclusively, so a second run of the same name started in the same second takes
    ``<stamp>_2`` (then ``_3`` ...) instead of writing into the first one's folder.
    """
    if output_dir:
        return Path(get_path_manager().ensure(group_output_dir(output_dir, run_name)))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    attempt = 1
    while True:
        candidate = Path(
            group_output_dir(
                None, run_name, stamp if attempt == 1 else f"{stamp}_{attempt}"
            )
        )
        candidate.parent.mkdir(parents=True, exist_ok=True)
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            attempt += 1


def _detach_log_handler(handler) -> None:
    """Remove *handler* from the ``tit`` logger and close its file."""
    logging.getLogger("tit").removeHandler(handler)
    handler.close()


def _build_summary_df(results: dict[str, AnalysisResult]) -> pd.DataFrame:
    """One row per subject plus an AVERAGE row at the bottom.

    A subject without normal-component statistics (every voxel analysis; a mesh run
    without a normal mesh) has empty ``Normal_*`` cells, not ``0``: the AVERAGE of a
    column is over the subjects that have it, and is empty when none does. The carrier
    columns (``HF_Focality``, ``RMS_Focality``, ``TI_Selectivity``) follow the same rule for
    a simulation that did not write ``hf_peak`` / ``hf_sar``.
    """
    rows = [
        {
            "Subject": sid,
            "ROI_Mean": r.roi_mean,
            "ROI_Max": r.roi_max,
            "ROI_Min": r.roi_min,
            "ROI_Focality": r.roi_focality,
            "GM_Mean": r.gm_mean,
            "GM_Max": r.gm_max,
            "Normal_Mean": r.normal_mean,
            "Normal_Max": r.normal_max,
            "Normal_Focality": r.normal_focality,
            "HF_Focality": r.hf_focality,
            "RMS_Focality": r.rms_focality,
            "TI_Selectivity": r.ti_selectivity,
        }
        for sid, r in results.items()
    ]
    df = pd.DataFrame(rows)
    df[_NUMERIC_COLS] = df[_NUMERIC_COLS].astype(float)  # None -> NaN
    avg = {"Subject": "AVERAGE", **df[_NUMERIC_COLS].mean().to_dict()}
    return pd.concat([df, pd.DataFrame([avg])], ignore_index=True)


def _generate_comparison_plot(df: pd.DataFrame, output_dir: Path) -> Path:
    """2x2 bar chart: Mean, Max, Focality, Normal_Mean per subject.

    The Normal Mean panel is left out when no subject has normal statistics; a subject
    without them has no bar there, and the group mean and spread are over the rest.
    """
    subject_df = df[df["Subject"] != "AVERAGE"]
    metrics = ["ROI_Mean", "ROI_Max", "ROI_Focality", "Normal_Mean"]
    labels = ["Mean (V/m)", "Max (V/m)", "Focality", "Normal Mean (V/m)"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    if subject_df["Normal_Mean"].isna().all():
        metrics, labels, colors = metrics[:3], labels[:3], colors[:3]

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("Group Field Value Comparison", fontsize=16, fontweight="bold")
    subjects = subject_df["Subject"].tolist()
    x_pos = np.arange(len(subjects))

    for ax in axes.flat[len(metrics) :]:
        fig.delaxes(ax)
    for ax, metric, label, color in zip(axes.flat, metrics, labels, colors):
        values = subject_df[metric].values.astype(float)
        present = values[np.isfinite(values)]
        mean_val = float(np.mean(present))
        std_val = float(np.std(present, ddof=1)) if len(present) > 1 else 0.0

        bars = ax.bar(x_pos, values, color=color, alpha=0.7)
        for bar, val in zip(bars, values):
            bar.set_alpha(0.8 if val >= mean_val else 0.4)

        ax.axhline(
            y=mean_val,
            color="black",
            linestyle="-",
            linewidth=2,
            alpha=0.8,
            label=f"Mean ({mean_val:.3f})",
        )
        _add_std_lines(ax, mean_val, std_val)
        ax.set_title(f"ROI {label}", fontweight="bold")
        ax.set_ylabel(label)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(subjects, ha="right", rotation=45)
        ax.grid(True, alpha=0.3)

    fig.legend(
        handles=[
            Line2D(
                [0], [0], color="black", linestyle="-", linewidth=2, label="Group Mean"
            ),
            Line2D([0], [0], color="gray", linestyle="--", label="\u00b11 Std Dev"),
            Line2D([0], [0], color="red", linestyle="--", label="\u00b12 Std Dev"),
        ],
        loc="upper right",
        bbox_to_anchor=(0.98, 0.95),
    )
    plt.tight_layout()
    plt.subplots_adjust(top=0.93)

    plot_path = output_dir / "group_comparison.pdf"
    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return plot_path


def _add_std_lines(ax, mean_val: float, std_val: float) -> None:
    """Draw +/-1 sigma and +/-2 sigma reference lines."""
    if std_val <= 0:
        return
    for mult, color in [(1, "gray"), (2, "red")]:
        ax.axhline(
            y=mean_val + mult * std_val,
            color=color,
            linestyle="--",
            linewidth=1,
            alpha=0.6,
        )
        ax.axhline(
            y=mean_val - mult * std_val,
            color=color,
            linestyle="--",
            linewidth=1,
            alpha=0.6,
        )
