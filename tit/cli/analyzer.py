#!/usr/bin/env python3
"""
TI-Toolbox Analyzer CLI (Click).

Replaces `tit/cli/analyzer.sh`.

Supports:
- Interactive mode (best-effort; prompts for key inputs)
- Direct/non-interactive mode via `--run-direct` + env vars (used by GUI/tests)

Direct mode env vars (matches legacy bash):
  SUBJECT, SIMULATION_NAME, SPACE_TYPE, ANALYSIS_TYPE, FIELD_PATH
  For spherical:
    COORDINATES="x y z", RADIUS, COORDINATE_SPACE
  For cortical:
    SPACE_TYPE=mesh: ATLAS_NAME, and either WHOLE_HEAD=true or REGION=...
    SPACE_TYPE=voxel: ATLAS_PATH, and either WHOLE_HEAD=true or REGION=...
  Optional:
    OUTPUT_DIR, VISUALIZE=true|false
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import click

from tit.core import list_subjects as _list_subjects
from tit.cli import utils


def _run_main_analyzer_with_argv(argv: Sequence[str]) -> int:
    """
    Run `tit.analyzer.main_analyzer.main()` with an argv override.

    We avoid spawning subprocesses to keep it fast and easy to test.
    """
    from tit.analyzer import main_analyzer

    old_argv = sys.argv[:]
    try:
        sys.argv = ["tit.analyzer.main_analyzer", *argv]
        main_analyzer.main()
        return 0
    finally:
        sys.argv = old_argv


@dataclass(frozen=True)
class DirectConfig:
    subject_id: str
    simulation_name: str
    space_type: str
    analysis_type: str
    field_path: str
    output_dir: Optional[str]
    visualize: bool
    coordinates: Optional[Tuple[float, float, float]]
    radius: Optional[float]
    coordinate_space: Optional[str]
    atlas_name: Optional[str]
    atlas_path: Optional[str]
    whole_head: bool
    region: Optional[str]


def _load_direct_config_from_env() -> DirectConfig:
    subject_id = utils.env_required("SUBJECT")
    simulation_name = utils.env_required("SIMULATION_NAME")
    space_type = utils.env_required("SPACE_TYPE")
    analysis_type = utils.env_required("ANALYSIS_TYPE")
    field_path = utils.env_required("FIELD_PATH")

    output_dir = os.environ.get("OUTPUT_DIR") or None
    visualize = utils.bool_env("VISUALIZE", default=True)

    coordinates: Optional[Tuple[float, float, float]] = None
    radius: Optional[float] = None
    coordinate_space: Optional[str] = None
    atlas_name: Optional[str] = None
    atlas_path: Optional[str] = None
    whole_head = utils.bool_env("WHOLE_HEAD", default=False)
    region = os.environ.get("REGION") or None

    if analysis_type == "spherical":
        coords_raw = utils.env_required("COORDINATES")
        parts = coords_raw.strip().split()
        if len(parts) != 3:
            raise click.ClickException("COORDINATES must be 3 space-separated numbers, e.g. '-50 0 0'")
        coordinates = (float(parts[0]), float(parts[1]), float(parts[2]))
        radius = float(utils.env_required("RADIUS"))
        coordinate_space = utils.env_required("COORDINATE_SPACE")
    else:
        # cortical
        if space_type == "mesh":
            atlas_name = utils.env_required("ATLAS_NAME")
        else:
            atlas_path = utils.env_required("ATLAS_PATH")

        if not whole_head and not region:
            raise click.ClickException("For cortical analysis set WHOLE_HEAD=true or REGION=<region-name>")

    return DirectConfig(
        subject_id=subject_id,
        simulation_name=simulation_name,
        space_type=space_type,
        analysis_type=analysis_type,
        field_path=field_path,
        output_dir=output_dir,
        visualize=visualize,
        coordinates=coordinates,
        radius=radius,
        coordinate_space=coordinate_space,
        atlas_name=atlas_name,
        atlas_path=atlas_path,
        whole_head=whole_head,
        region=region,
    )


def _default_project_dir_from_env() -> Optional[Path]:
    return utils.default_project_dir_from_env()


def _compute_default_output_dir(
    project_dir: Path,
    subject_id: str,
    simulation_name: str,
    space_type: str,
    analysis_type: str,
    coords: Optional[Tuple[float, float, float]],
    radius: Optional[float],
    atlas_name: Optional[str],
    atlas_path: Optional[str],
    whole_head: bool,
    region: Optional[str],
) -> Path:
    analyses_dir = project_dir / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / "Simulations" / simulation_name / "Analyses"
    analysis_type_dir = analyses_dir / ("Mesh" if space_type == "mesh" else "Voxel")

    if analysis_type == "spherical":
        assert coords is not None and radius is not None
        target_info = f"sphere_x{coords[0]}_y{coords[1]}_z{coords[2]}_r{radius}"
    else:
        if whole_head:
            if space_type == "mesh":
                target_info = f"whole_head_{atlas_name}"
            else:
                atlas_base = Path(atlas_path or "atlas").name
                target_info = f"whole_head_{atlas_base.split('.')[0]}"
        else:
            target_info = f"region_{region}"

    return analysis_type_dir / target_info


def _discover_simulations(project_dir: Path, subject_id: str) -> List[str]:
    return utils.discover_simulations(project_dir, subject_id)


def _discover_fields(project_dir: Path, subject_id: str, simulation_name: str, space_type: str) -> List[Path]:
    return utils.discover_fields(project_dir, subject_id, simulation_name, space_type)


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--run-direct", is_flag=True, help="Run using legacy env vars (non-interactive).")
@click.option("--project-dir", type=click.Path(path_type=Path), default=None, help="Project directory (BIDS root).")
def cli(run_direct: bool, project_dir: Optional[Path]) -> None:
    """Analyze simulation results (mesh or voxel) for a single subject."""
    if run_direct:
        cfg = _load_direct_config_from_env()
        proj = project_dir or _default_project_dir_from_env()
        if proj is None:
            raise click.ClickException("Project directory not found. Set --project-dir or PROJECT_DIR/PROJECT_DIR_NAME.")

        out_dir = cfg.output_dir or str(
            _compute_default_output_dir(
                project_dir=proj,
                subject_id=cfg.subject_id,
                simulation_name=cfg.simulation_name,
                space_type=cfg.space_type,
                analysis_type=cfg.analysis_type,
                coords=cfg.coordinates,
                radius=cfg.radius,
                atlas_name=cfg.atlas_name,
                atlas_path=cfg.atlas_path,
                whole_head=cfg.whole_head,
                region=cfg.region,
            )
        )

        # m2m dir is derived from project_dir + subject
        m2m_dir = proj / "derivatives" / "SimNIBS" / f"sub-{cfg.subject_id}" / f"m2m_{cfg.subject_id}"

        argv: List[str] = [
            "--m2m_subject_path",
            str(m2m_dir),
            "--field_path",
            cfg.field_path,
            "--space",
            cfg.space_type,
            "--analysis_type",
            cfg.analysis_type,
            "--output_dir",
            out_dir,
        ]

        if cfg.analysis_type == "spherical":
            assert cfg.coordinates and cfg.radius is not None and cfg.coordinate_space
            argv += ["--coordinates", str(cfg.coordinates[0]), str(cfg.coordinates[1]), str(cfg.coordinates[2])]
            argv += ["--radius", str(cfg.radius)]
            argv += ["--coordinate-space", cfg.coordinate_space]
        else:
            if cfg.space_type == "mesh":
                argv += ["--atlas_name", cfg.atlas_name or "DK40"]
            else:
                argv += ["--atlas_path", cfg.atlas_path or ""]
            if cfg.whole_head:
                argv += ["--whole_head"]
            else:
                argv += ["--region", cfg.region or ""]

        if cfg.space_type == "mesh":
            argv += ["--montage_name", cfg.simulation_name]

        if cfg.visualize:
            argv += ["--visualize"]

        rc = _run_main_analyzer_with_argv(argv)
        raise SystemExit(rc)

    # Interactive mode (best-effort, simplified)
    proj = project_dir or _default_project_dir_from_env()
    if proj is None:
        proj = Path(click.prompt("Project directory (BIDS root)", type=click.Path(path_type=Path)))

    subjects = _list_subjects(str(proj))
    if not subjects:
        raise click.ClickException(f"No subjects found under {proj}/derivatives/SimNIBS")

    click.echo("\nAvailable Subjects:")
    for i, sid in enumerate(subjects, 1):
        click.echo(f"{i:3d}. {sid}")
    idx = click.prompt("Select subject number", type=click.IntRange(1, len(subjects)))
    subject_id = subjects[idx - 1]

    sims = _discover_simulations(proj, subject_id)
    if not sims:
        raise click.ClickException(f"No simulations found for subject {subject_id}")
    click.echo("\nAvailable Simulations:")
    for i, s in enumerate(sims, 1):
        click.echo(f"{i:3d}. {s}")
    sim_idx = click.prompt("Select simulation number", type=click.IntRange(1, len(sims)))
    simulation_name = sims[sim_idx - 1]

    space_type = click.prompt("Space", type=click.Choice(["mesh", "voxel"]), default="mesh")
    analysis_type = click.prompt("Analysis type", type=click.Choice(["spherical", "cortical"]), default="spherical")

    fields = _discover_fields(proj, subject_id, simulation_name, space_type)
    if not fields:
        raise click.ClickException("No field files found for this simulation/space")
    click.echo("\nAvailable Field Files:")
    for i, p in enumerate(fields, 1):
        click.echo(f"{i:3d}. {p.name}")
    f_idx = click.prompt("Select field file number", type=click.IntRange(1, len(fields)))
    field_path = str(fields[f_idx - 1])

    coords: Optional[Tuple[float, float, float]] = None
    radius: Optional[float] = None
    coordinate_space: Optional[str] = None
    atlas_name: Optional[str] = None
    atlas_path: Optional[str] = None
    whole_head = False
    region: Optional[str] = None

    if analysis_type == "spherical":
        x = click.prompt("X", type=float)
        y = click.prompt("Y", type=float)
        z = click.prompt("Z", type=float)
        coords = (x, y, z)
        radius = click.prompt("Radius (mm)", type=float, default=10.0)
        coordinate_space = click.prompt("Coordinate space", type=click.Choice(["MNI", "subject"]), default="subject")
    else:
        if space_type == "mesh":
            atlas_name = click.prompt("Atlas name", type=click.Choice(["DK40", "HCP_MMP1", "a2009s"]), default="DK40")
        else:
            atlas_path = click.prompt("Atlas path", type=str)
        whole_head = click.confirm("Analyze whole head?", default=False)
        if not whole_head:
            region = click.prompt("Region name", type=str)

    visualize = click.confirm("Generate visualizations?", default=True)
    out_dir = str(
        _compute_default_output_dir(
            project_dir=proj,
            subject_id=subject_id,
            simulation_name=simulation_name,
            space_type=space_type,
            analysis_type=analysis_type,
            coords=coords,
            radius=radius,
            atlas_name=atlas_name,
            atlas_path=atlas_path,
            whole_head=whole_head,
            region=region,
        )
    )

    if not click.confirm(f"Proceed? Output dir:\n  {out_dir}", default=True):
        raise click.Abort()

    m2m_dir = proj / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / f"m2m_{subject_id}"
    argv = [
        "--m2m_subject_path",
        str(m2m_dir),
        "--field_path",
        field_path,
        "--space",
        space_type,
        "--analysis_type",
        analysis_type,
        "--output_dir",
        out_dir,
    ]
    if analysis_type == "spherical":
        assert coords and radius is not None and coordinate_space
        argv += ["--coordinates", str(coords[0]), str(coords[1]), str(coords[2])]
        argv += ["--radius", str(radius)]
        argv += ["--coordinate-space", coordinate_space]
    else:
        if space_type == "mesh":
            argv += ["--atlas_name", atlas_name or "DK40"]
        else:
            argv += ["--atlas_path", atlas_path or ""]
        if whole_head:
            argv += ["--whole_head"]
        else:
            argv += ["--region", region or ""]

    if space_type == "mesh":
        argv += ["--montage_name", simulation_name]
    if visualize:
        argv += ["--visualize"]

    rc = _run_main_analyzer_with_argv(argv)
    raise SystemExit(rc)


if __name__ == "__main__":
    cli()


