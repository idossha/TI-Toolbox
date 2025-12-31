#!/usr/bin/env python3
"""
TI-Toolbox Flex-Search CLI (Click).

Replaces `tit/cli/flex-search.sh`.

This is a Click wrapper around the existing module entrypoint `python -m tit.opt.flex`.
We intentionally allow passthrough args so the flex optimizer can evolve without
duplicating its full argument surface here.

Usage:
  simnibs_python -m tit.cli.flex_search -- --subject 101 --goal mean --postproc max_TI ...

Notes:
  - Everything after `--` is forwarded to `tit.opt.flex` unchanged.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

import click

from tit.cli import utils


def _python_executable() -> str:
    # Prefer simnibs_python if available inside containers.
    return os.environ.get("TI_PYTHON", "simnibs_python")

def _set_flex_roi_env_for_spherical(
    *,
    roi_x: float,
    roi_y: float,
    roi_z: float,
    roi_radius: float,
    use_mni_coords: bool,
) -> None:
    os.environ["ROI_X"] = str(roi_x)
    os.environ["ROI_Y"] = str(roi_y)
    os.environ["ROI_Z"] = str(roi_z)
    os.environ["ROI_RADIUS"] = str(roi_radius)
    os.environ["USE_MNI_COORDS"] = "true" if use_mni_coords else "false"


def _set_flex_roi_env_for_atlas(*, atlas_path: str, hemisphere: str, roi_label: int) -> None:
    os.environ["ATLAS_PATH"] = atlas_path
    os.environ["SELECTED_HEMISPHERE"] = hemisphere
    os.environ["ROI_LABEL"] = str(roi_label)


def _set_flex_roi_env_for_subcortical(*, volume_atlas_path: str, roi_label: int) -> None:
    os.environ["VOLUME_ATLAS_PATH"] = volume_atlas_path
    os.environ["VOLUME_ROI_LABEL"] = str(roi_label)


def _call_flex(args: List[str]) -> int:
    cmd = [_python_executable(), "-m", "tit.opt.flex", *args]
    return subprocess.call(cmd)


def _default_project_dir(project_dir: Optional[Path]) -> Path:
    proj = project_dir or utils.default_project_dir_from_env()
    if proj is None:
        raise click.ClickException("Project directory not found. Set --project-dir or PROJECT_DIR/PROJECT_DIR_NAME.")
    return proj


def _direct_from_env(project_dir: Optional[Path]) -> int:
    proj = _default_project_dir(project_dir)
    os.environ["PROJECT_DIR"] = str(proj)

    subjects_env = utils.env_required("SUBJECTS")
    subject_ids = [s.strip() for s in subjects_env.split(",") if s.strip()]
    if not subject_ids:
        raise click.ClickException("SUBJECTS env var is empty")

    # Core args (match flex_config.parse_arguments)
    goal = utils.env_required("GOAL")
    postproc = utils.env_required("POSTPROC")
    current = float(utils.env_required("CURRENT"))
    electrode_shape = utils.env_required("ELECTRODE_SHAPE")
    dimensions = utils.env_required("DIMENSIONS")
    thickness = float(utils.env_required("THICKNESS"))
    roi_method = utils.env_required("ROI_METHOD")

    eeg_net = os.environ.get("EEG_NET")  # required if ENABLE_MAPPING=true
    enable_mapping = utils.bool_env("ENABLE_MAPPING", default=False)
    disable_mapping_sim = utils.bool_env("DISABLE_MAPPING_SIMULATION", default=False)

    n_multistart = os.environ.get("N_MULTISTART")
    max_iterations = os.environ.get("MAX_ITERATIONS")
    population_size = os.environ.get("POPULATION_SIZE")
    cpus = os.environ.get("CPUS")

    detailed_results = utils.bool_env("DETAILED_RESULTS", default=False)
    visualize_valid_skin_region = utils.bool_env("VISUALIZE_VALID_SKIN_REGION", default=False)
    skin_visualization_net = os.environ.get("SKIN_VISUALIZATION_NET")

    thresholds = os.environ.get("THRESHOLDS")
    non_roi_method = os.environ.get("NON_ROI_METHOD")

    # ROI env vars for method
    if roi_method == "spherical":
        _set_flex_roi_env_for_spherical(
            roi_x=float(utils.env_required("ROI_X")),
            roi_y=float(utils.env_required("ROI_Y")),
            roi_z=float(utils.env_required("ROI_Z")),
            roi_radius=float(utils.env_required("ROI_RADIUS")),
            use_mni_coords=utils.bool_env("USE_MNI_COORDS", default=(len(subject_ids) > 1)),
        )
    elif roi_method == "atlas":
        _set_flex_roi_env_for_atlas(
            atlas_path=utils.env_required("ATLAS_PATH"),
            hemisphere=os.environ.get("SELECTED_HEMISPHERE", "lh"),
            roi_label=int(os.environ.get("ROI_LABEL", "1")),
        )
    else:
        _set_flex_roi_env_for_subcortical(
            volume_atlas_path=utils.env_required("VOLUME_ATLAS_PATH"),
            roi_label=int(os.environ.get("VOLUME_ROI_LABEL", "10")),
        )

    # Build arg list per subject and run sequentially
    rc_total = 0
    for sid in subject_ids:
        args: List[str] = [
            "--subject",
            sid,
            "--goal",
            goal,
            "--postproc",
            postproc,
            "--current",
            str(current),
            "--electrode-shape",
            electrode_shape,
            "--dimensions",
            dimensions,
            "--thickness",
            str(thickness),
            "--roi-method",
            roi_method,
        ]

        if enable_mapping:
            if not eeg_net:
                raise click.ClickException("ENABLE_MAPPING=true requires EEG_NET")
            args += ["--enable-mapping", "--eeg-net", eeg_net]
            if disable_mapping_sim:
                args += ["--disable-mapping-simulation"]
        elif eeg_net:
            # still pass eeg-net if provided (helpful for logging/skin viz)
            args += ["--eeg-net", eeg_net]

        if thresholds:
            args += ["--thresholds", thresholds]
        if non_roi_method:
            args += ["--non-roi-method", non_roi_method]

        if n_multistart:
            args += ["--n-multistart", n_multistart]
        if max_iterations:
            args += ["--max-iterations", max_iterations]
        if population_size:
            args += ["--population-size", population_size]
        if cpus:
            args += ["--cpus", cpus]

        if detailed_results:
            args += ["--detailed-results"]
        if visualize_valid_skin_region:
            args += ["--visualize-valid-skin-region"]
        if skin_visualization_net:
            args += ["--skin-visualization-net", skin_visualization_net]

        rc = _call_flex(args)
        if rc != 0:
            rc_total = rc

    return rc_total


def _interactive_wizard(project_dir: Optional[Path]) -> int:
    proj = _default_project_dir(project_dir)
    os.environ["PROJECT_DIR"] = str(proj)

    from tit.core import list_subjects as _list_subjects

    all_subjects = _list_subjects(str(proj))
    if not all_subjects:
        raise click.ClickException(f"No subjects found under {proj}/derivatives/SimNIBS")
    subject_ids = utils.prompt_subject_ids(all_subjects)

    utils.echo_header("Flex-Search Optimization")

    goal = click.prompt("Goal", type=click.Choice(["mean", "focality", "max"]), default="mean")
    postproc = click.prompt(
        "Postproc", type=click.Choice(["max_TI", "dir_TI_normal", "dir_TI_tangential"]), default="max_TI"
    )

    electrode_shape = click.prompt("Electrode shape", type=click.Choice(["rect", "ellipse"]), default="rect")
    dimensions = click.prompt("Dimensions (x,y mm)", type=str, default="8,8")
    thickness = click.prompt("Thickness (mm)", type=float, default=5.0)
    current = click.prompt("Current (mA)", type=float, default=2.0)

    roi_method = click.prompt("ROI method", type=click.Choice(["spherical", "atlas", "subcortical"]), default="spherical")

    if roi_method == "spherical":
        utils.echo_section("Spherical ROI")
        use_mni_coords = len(subject_ids) > 1 and click.confirm(
            "Multiple subjects selected: treat coordinates as MNI and transform per subject?", default=True
        )
        roi_x = click.prompt("ROI X", type=float, default=0.0)
        roi_y = click.prompt("ROI Y", type=float, default=0.0)
        roi_z = click.prompt("ROI Z", type=float, default=0.0)
        roi_radius = click.prompt("ROI radius (mm)", type=float, default=10.0)
        _set_flex_roi_env_for_spherical(
            roi_x=roi_x, roi_y=roi_y, roi_z=roi_z, roi_radius=roi_radius, use_mni_coords=use_mni_coords
        )
    elif roi_method == "atlas":
        utils.echo_section("Atlas ROI")
        atlas_path = click.prompt("ATLAS_PATH (annot file)", type=str)
        hemisphere = click.prompt("Hemisphere", type=click.Choice(["lh", "rh"]), default="lh")
        roi_label = click.prompt("ROI label (int)", type=int, default=1)
        _set_flex_roi_env_for_atlas(atlas_path=atlas_path, hemisphere=hemisphere, roi_label=roi_label)
    else:
        utils.echo_section("Subcortical ROI")
        volume_atlas_path = click.prompt("VOLUME_ATLAS_PATH (.nii/.nii.gz/.mgz)", type=str)
        roi_label = click.prompt("VOLUME_ROI_LABEL (int)", type=int, default=10)
        _set_flex_roi_env_for_subcortical(volume_atlas_path=volume_atlas_path, roi_label=roi_label)

    enable_mapping = click.confirm("Enable mapping to EEG net?", default=False)
    eeg_net: Optional[str] = None
    disable_mapping_sim = False
    if enable_mapping:
        eeg_net = click.prompt("EEG net name (without .csv)", type=str)
        disable_mapping_sim = click.confirm("Disable extra mapped-electrodes simulation?", default=False)

    # Performance options
    n_multistart = click.prompt("n-multistart", type=int, default=1)
    cpus = click.prompt("cpus", type=int, default=1)

    thresholds: Optional[str] = None
    non_roi_method: Optional[str] = None
    if goal == "focality":
        thresholds = click.prompt("thresholds (single or two values 'a' or 'a,b')", type=str)
        non_roi_method = click.prompt(
            "non-roi-method", type=click.Choice(["everything_else", "specific"]), default="everything_else"
        )

    if not click.confirm("Proceed with flex-search?", default=True):
        raise click.Abort()

    # run for each subject
    rc_total = 0
    for sid in subject_ids:
        args = [
            "--subject",
            sid,
            "--goal",
            goal,
            "--postproc",
            postproc,
            "--current",
            str(current),
            "--electrode-shape",
            electrode_shape,
            "--dimensions",
            dimensions,
            "--thickness",
            str(thickness),
            "--roi-method",
            roi_method,
            "--n-multistart",
            str(n_multistart),
            "--cpus",
            str(cpus),
        ]
        if enable_mapping:
            args += ["--enable-mapping", "--eeg-net", eeg_net or ""]
            if disable_mapping_sim:
                args += ["--disable-mapping-simulation"]
        if thresholds:
            args += ["--thresholds", thresholds]
        if non_roi_method:
            args += ["--non-roi-method", non_roi_method]

        rc = _call_flex(args)
        if rc != 0:
            rc_total = rc

    return rc_total


@click.command(
    context_settings=dict(
        help_option_names=["-h", "--help"],
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.pass_context
@click.option("--run-direct", is_flag=True, help="Run using env vars (SUBJECTS, GOAL, POSTPROC, etc.).")
@click.option("--project-dir", type=click.Path(path_type=Path), default=None, help="Project directory (BIDS root).")
def cli(ctx: click.Context, run_direct: bool, project_dir: Optional[Path]) -> None:
    """
    Flex-search CLI.

    - If called with arguments after `--`, they are forwarded to `tit.opt.flex` (direct/scriptable).
    - If called with --run-direct, values are read from env vars and executed.
    - If called with no forwarded args and no --run-direct, an interactive wizard runs.
    """
    extra: List[str] = list(ctx.args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    if extra:
        # passthrough mode
        proj = _default_project_dir(project_dir)
        os.environ.setdefault("PROJECT_DIR", str(proj))
        raise SystemExit(_call_flex(extra))

    if run_direct:
        raise SystemExit(_direct_from_env(project_dir))

    raise SystemExit(_interactive_wizard(project_dir))


if __name__ == "__main__":
    cli()


