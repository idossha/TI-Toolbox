#!/usr/bin/env python3
"""
TI-Toolbox Group Analyzer CLI (Click).

Replaces `tit/cli/group_analyzer.sh`.

This is a thin Click wrapper around `tit.analyzer.group_analyzer`.
It focuses on providing a clean, scriptable CLI; interactive prompting is minimal.

Usage:
  simnibs_python -m tit.cli.group_analyzer run --space mesh --analysis-type spherical --output-dir /mnt/<proj>/code/tit/group_analyses/out ...
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import click

from tit.cli import utils


def _run_group_analyzer_with_argv(argv: Sequence[str]) -> int:
    from tit.analyzer import group_analyzer

    utils.run_main_with_argv("tit.analyzer.group_analyzer", argv, group_analyzer.main)
    return 0


def _default_project_dir_from_env() -> Optional[Path]:
    return utils.default_project_dir_from_env()


@click.group(context_settings=dict(help_option_names=["-h", "--help"]), invoke_without_command=True)
@click.option("--run-direct", is_flag=True, help="Run using legacy env vars (non-interactive).")
@click.option("--project-dir", type=click.Path(path_type=Path), default=None)
@click.pass_context
def cli(ctx: click.Context, run_direct: bool, project_dir: Optional[Path]) -> None:
    """Run analysis across multiple subjects and compare results."""
    ctx.ensure_object(dict)
    ctx.obj["run_direct"] = run_direct
    ctx.obj["project_dir"] = project_dir

    # Interactive default if no subcommand
    if ctx.invoked_subcommand is None and not run_direct:
        _interactive_wizard(project_dir)
        raise SystemExit(0)
    if ctx.invoked_subcommand is None and run_direct:
        _direct_from_env(project_dir)
        raise SystemExit(0)


def _direct_from_env(project_dir: Optional[Path]) -> None:
    proj = project_dir or _default_project_dir_from_env()
    if proj is None:
        raise click.ClickException("Project directory not found. Set --project-dir or PROJECT_DIR/PROJECT_DIR_NAME.")

    subjects_env = utils.env_required("SUBJECTS")  # comma-separated subject ids
    simulation = utils.env_required("SIMULATION_NAME")
    space = utils.env_required("SPACE_TYPE")
    analysis_type = utils.env_required("ANALYSIS_TYPE")
    output_dir = Path(os.environ.get("OUTPUT_DIR") or (proj / "code" / "tit" / "group_analyses" / "group_analysis"))

    # Analysis-specific env
    coordinates = os.environ.get("COORDINATES")
    coordinate_space = os.environ.get("COORDINATE_SPACE")
    radius = os.environ.get("RADIUS")
    atlas_name = os.environ.get("ATLAS_NAME")
    region = os.environ.get("REGION")
    whole_head = utils.bool_env("WHOLE_HEAD", default=False)
    visualize = utils.bool_env("VISUALIZE", default=True)
    quiet = utils.bool_env("QUIET", default=True)

    subject_ids = [s.strip() for s in subjects_env.split(",") if s.strip()]
    if len(subject_ids) < 2:
        raise click.ClickException("Group analysis requires at least 2 subjects in SUBJECTS")

    # Build argv for `tit.analyzer.group_analyzer`
    argv: List[str] = ["--space", space, "--analysis_type", analysis_type, "--output_dir", str(output_dir)]
    if quiet:
        argv.append("--quiet")
    if visualize:
        argv.append("--visualize")

    if analysis_type == "spherical":
        if not coordinates or not radius or not coordinate_space:
            raise click.ClickException("Direct spherical requires COORDINATES, RADIUS, COORDINATE_SPACE")
        xyz = coordinates.split()
        if len(xyz) != 3:
            raise click.ClickException("COORDINATES must be 'x y z'")
        argv += ["--coordinates", xyz[0], xyz[1], xyz[2], "--radius", str(float(radius)), "--coordinate-space", coordinate_space]
    else:
        if space == "mesh":
            if not atlas_name:
                raise click.ClickException("Direct mesh cortical requires ATLAS_NAME")
            argv += ["--atlas_name", atlas_name]
        if whole_head:
            argv.append("--whole_head")
        else:
            if not region:
                raise click.ClickException("Direct cortical requires REGION unless WHOLE_HEAD=true")
            argv += ["--region", region]

    # Per-subject specs
    for sid in subject_ids:
        m2m = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}"
        if space == "mesh":
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "mesh" / f"{simulation}_TI.msh"
            argv += ["--subject", sid, str(m2m), str(field)]
        else:
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "niftis" / f"grey_{simulation}_TI_subject_TI_max.nii.gz"
            if analysis_type == "cortical":
                atlas = utils.env_required("ATLAS_PATH")  # single atlas path used for all is acceptable here
                argv += ["--subject", sid, str(m2m), str(field), atlas]
            else:
                argv += ["--subject", sid, str(m2m), str(field)]

    rc = _run_group_analyzer_with_argv(argv)
    raise SystemExit(rc)


def _interactive_wizard(project_dir: Optional[Path]) -> None:
    proj = project_dir or _default_project_dir_from_env()
    if proj is None:
        proj = Path(click.prompt("Project directory (BIDS root)", type=click.Path(path_type=Path)))

    from tit.core import list_subjects as _list_subjects

    subjects = _list_subjects(str(proj))
    if not subjects:
        raise click.ClickException(f"No subjects found under {proj}/derivatives/SimNIBS")

    selected = utils.prompt_subject_ids(subjects)
    if len(selected) < 2:
        raise click.ClickException("Group analysis requires selecting at least 2 subjects")

    simulation = click.prompt("Simulation/montage name (must exist for all subjects)", type=str)
    space = click.prompt("Space", type=click.Choice(["mesh", "voxel"]), default="mesh")
    analysis_type = click.prompt("Analysis type", type=click.Choice(["spherical", "cortical"]), default="spherical")
    output_dir = Path(click.prompt("Output directory", type=click.Path(path_type=Path)))
    visualize = click.confirm("Generate visualizations?", default=True)
    quiet = click.confirm("Summary/quiet mode?", default=True)

    argv: List[str] = ["--space", space, "--analysis_type", analysis_type, "--output_dir", str(output_dir)]
    if quiet:
        argv.append("--quiet")
    if visualize:
        argv.append("--visualize")

    if analysis_type == "spherical":
        x = click.prompt("X", type=float)
        y = click.prompt("Y", type=float)
        z = click.prompt("Z", type=float)
        radius = click.prompt("Radius (mm)", type=float, default=10.0)
        coordinate_space = click.prompt("Coordinate space", type=click.Choice(["MNI", "subject"]), default="MNI")
        argv += ["--coordinates", str(x), str(y), str(z), "--radius", str(radius), "--coordinate-space", coordinate_space]
    else:
        if space == "mesh":
            atlas_name = click.prompt("Atlas name", type=click.Choice(["DK40", "HCP_MMP1", "a2009s"]), default="DK40")
            argv += ["--atlas_name", atlas_name]
        whole_head = click.confirm("Analyze whole head?", default=False)
        if whole_head:
            argv.append("--whole_head")
        else:
            region = click.prompt("Region name", type=str)
            argv += ["--region", region]

    for sid in selected:
        m2m = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}"
        if space == "mesh":
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "mesh" / f"{simulation}_TI.msh"
            argv += ["--subject", sid, str(m2m), str(field)]
        else:
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "niftis" / f"grey_{simulation}_TI_subject_TI_max.nii.gz"
            if analysis_type == "cortical":
                atlas_path = click.prompt("Atlas path (for voxel cortical)", type=str)
                argv += ["--subject", sid, str(m2m), str(field), atlas_path]
            else:
                argv += ["--subject", sid, str(m2m), str(field)]

    if not click.confirm("Proceed with group analysis?", default=True):
        raise click.Abort()

    rc = _run_group_analyzer_with_argv(argv)
    raise SystemExit(rc)


@cli.command("run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option("--space", type=click.Choice(["mesh", "voxel"]), required=True)
@click.option("--analysis-type", "analysis_type", type=click.Choice(["spherical", "cortical"]), required=True)
@click.option("--output-dir", "output_dir", type=click.Path(path_type=Path), required=True)
@click.option("--atlas-name", "atlas_name", type=str, default=None)
@click.option("--coordinates", nargs=3, type=float, default=None)
@click.option("--coordinate-space", "coordinate_space", type=click.Choice(["MNI", "subject"]), default=None)
@click.option("--radius", type=float, default=None)
@click.option("--region", type=str, default=None)
@click.option("--whole-head", "whole_head", is_flag=True, default=False)
@click.option("--visualize", is_flag=True, default=True)
@click.option("--quiet", is_flag=True, default=True, help="Enable summary mode (recommended for CLI).")
@click.option(
    "--subject",
    "subjects",
    multiple=True,
    required=False,
    help="Repeatable subject spec. Provide: subject_id,m2m_path,field_path[,atlas_path].",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    space: str,
    analysis_type: str,
    output_dir: Path,
    atlas_name: Optional[str],
    coordinates: Optional[List[float]],
    coordinate_space: Optional[str],
    radius: Optional[float],
    region: Optional[str],
    whole_head: bool,
    visualize: bool,
    quiet: bool,
    subjects: List[str],
) -> None:
    """
    Run group analysis.

    Notes:
    - For voxel+cortical, each subject must include atlas_path.
    - If you don't pass any --subject, this command errors (we don't replicate the full bash discovery UI).
    """
    argv: List[str] = [
        "--space",
        space,
        "--analysis_type",
        analysis_type,
        "--output_dir",
        str(output_dir),
    ]

    if quiet:
        argv.append("--quiet")
    if visualize:
        argv.append("--visualize")

    if analysis_type == "spherical":
        if not coordinates or radius is None or not coordinate_space:
            raise click.ClickException("Spherical analysis requires --coordinates X Y Z, --radius, and --coordinate-space")
        argv += ["--coordinates", str(coordinates[0]), str(coordinates[1]), str(coordinates[2])]
        argv += ["--radius", str(radius)]
        argv += ["--coordinate-space", coordinate_space]
    else:
        if space == "mesh":
            if not atlas_name:
                raise click.ClickException("Mesh cortical analysis requires --atlas-name")
            argv += ["--atlas_name", atlas_name]
        if whole_head:
            argv.append("--whole_head")
        else:
            if not region:
                raise click.ClickException("Cortical analysis requires --region unless --whole-head is set")
            argv += ["--region", region]

    if not subjects:
        raise click.ClickException("At least one --subject is required (format: subject_id,m2m_path,field_path[,atlas_path])")

    for spec in subjects:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if analysis_type == "spherical" or (analysis_type == "cortical" and space == "mesh"):
            if len(parts) != 3:
                raise click.ClickException(f"Invalid --subject '{spec}'. Expected 3 parts: subject_id,m2m_path,field_path")
        else:
            if len(parts) != 4:
                raise click.ClickException(
                    f"Invalid --subject '{spec}'. Expected 4 parts: subject_id,m2m_path,field_path,atlas_path"
                )
        argv += ["--subject", *parts]

    # Allow extra args passthrough if needed in future
    argv += list(ctx.args)

    rc = _run_group_analyzer_with_argv(argv)
    raise SystemExit(rc)


@cli.command("from-project")
@click.option("--project-dir", type=click.Path(path_type=Path), default=None)
@click.option("--subjects", type=str, required=True, help="Comma-separated subject IDs, e.g. 101,102,103")
@click.option("--simulation", type=str, required=True, help="Simulation/montage name common to all subjects")
@click.option("--space", type=click.Choice(["mesh", "voxel"]), required=True)
@click.option("--analysis-type", type=click.Choice(["spherical", "cortical"]), required=True)
@click.option("--output-dir", type=click.Path(path_type=Path), required=True)
@click.option("--coordinates", nargs=3, type=float, default=None)
@click.option("--coordinate-space", type=click.Choice(["MNI", "subject"]), default=None)
@click.option("--radius", type=float, default=None)
@click.option("--atlas-name", type=str, default=None)
@click.option("--region", type=str, default=None)
@click.option("--whole-head", is_flag=True, default=False)
@click.option("--visualize", is_flag=True, default=True)
@click.option("--quiet", is_flag=True, default=True)
def from_project_cmd(
    project_dir: Optional[Path],
    subjects: str,
    simulation: str,
    space: str,
    analysis_type: str,
    output_dir: Path,
    coordinates: Optional[List[float]],
    coordinate_space: Optional[str],
    radius: Optional[float],
    atlas_name: Optional[str],
    region: Optional[str],
    whole_head: bool,
    visualize: bool,
    quiet: bool,
) -> None:
    """Convenience wrapper that constructs --subject specs from a standard project layout."""
    proj = project_dir or _default_project_dir_from_env()
    if proj is None:
        raise click.ClickException("Project directory not found. Set --project-dir or PROJECT_DIR/PROJECT_DIR_NAME.")

    subject_ids = [s.strip() for s in subjects.split(",") if s.strip()]
    if len(subject_ids) < 2:
        raise click.ClickException("Group analysis requires at least 2 subjects")

    subject_specs: List[str] = []
    for sid in subject_ids:
        m2m = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}"
        if space == "mesh":
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "mesh" / f"{simulation}_TI.msh"
        else:
            field = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / simulation / "TI" / "niftis" / f"grey_{simulation}_TI_subject_TI_max.nii.gz"

        if analysis_type == "cortical" and space == "voxel":
            # Best-effort default atlas location (caller can use `run` for explicit per-subject atlas paths)
            atlas = proj / "derivatives" / "freesurfer" / f"sub-{sid}" / sid / "mri" / "aparc.DKTatlas+aseg.mgz"
            subject_specs.append(f"{sid},{m2m},{field},{atlas}")
        else:
            subject_specs.append(f"{sid},{m2m},{field}")

    # Delegate to `run` implementation by calling the module main with argv.
    argv: List[str] = [
        "--space",
        space,
        "--analysis_type",
        analysis_type,
        "--output_dir",
        str(output_dir),
    ]
    if quiet:
        argv.append("--quiet")
    if visualize:
        argv.append("--visualize")

    if analysis_type == "spherical":
        if not coordinates or radius is None or not coordinate_space:
            raise click.ClickException("Spherical analysis requires --coordinates X Y Z, --radius, and --coordinate-space")
        argv += ["--coordinates", str(coordinates[0]), str(coordinates[1]), str(coordinates[2])]
        argv += ["--radius", str(radius)]
        argv += ["--coordinate-space", coordinate_space]
    else:
        if space == "mesh":
            if not atlas_name:
                raise click.ClickException("Mesh cortical analysis requires --atlas-name")
            argv += ["--atlas_name", atlas_name]
        if whole_head:
            argv.append("--whole_head")
        else:
            if not region:
                raise click.ClickException("Cortical analysis requires --region unless --whole-head is set")
            argv += ["--region", region]

    for spec in subject_specs:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        argv += ["--subject", *parts]

    rc = _run_group_analyzer_with_argv(argv)
    raise SystemExit(rc)


if __name__ == "__main__":
    cli()


