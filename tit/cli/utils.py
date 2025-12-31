from __future__ import annotations

"""
Shared utilities for TI-Toolbox Click CLIs.

Goals:
- Keep CLI UX consistent (styling, prompts, tables)
- Centralize repetitive env + path discovery logic
- Make direct vs interactive flows uniform across CLIs
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple, TypeVar

import click

T = TypeVar("T")


# =============================================================================
# Styling helpers
# =============================================================================

COLORS = {
    "header": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "prompt": "white",
}


def echo_header(text: str) -> None:
    click.secho(f"\n{'=' * 50}", fg=COLORS["header"], bold=True)
    click.secho(f"  {text}", fg=COLORS["header"], bold=True)
    click.secho(f"{'=' * 50}\n", fg=COLORS["header"], bold=True)


def echo_section(text: str) -> None:
    click.secho(f"\n{text}", fg=COLORS["header"], bold=True)
    click.secho("-" * len(text), fg=COLORS["header"])


def echo_success(text: str) -> None:
    click.secho(f"✓ {text}", fg=COLORS["success"])


def echo_warning(text: str) -> None:
    click.secho(f"⚠ {text}", fg=COLORS["warning"])


def echo_error(text: str) -> None:
    click.secho(f"✗ {text}", fg=COLORS["error"])


def echo_info(text: str) -> None:
    click.secho(f"ℹ {text}", fg=COLORS["info"])


# =============================================================================
# Env helpers
# =============================================================================


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_required(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise click.ClickException(f"Missing required environment variable: {name}")
    return val


def default_project_dir_from_env() -> Optional[Path]:
    """
    Prefer:
    - PROJECT_DIR (full path)
    - /mnt/$PROJECT_DIR_NAME (container convention)
    """
    proj = os.environ.get("PROJECT_DIR")
    if proj:
        return Path(proj)

    proj_name = os.environ.get("PROJECT_DIR_NAME")
    if proj_name and Path("/mnt").exists():
        return Path("/mnt") / proj_name

    return None


# =============================================================================
# Prompting helpers
# =============================================================================


def display_table(items: List[str], *, max_rows: int = 10, col_width: int = 25) -> None:
    """Display items in multi-column table with 1-based indexing."""
    if not items:
        echo_warning("No items found")
        return

    num_cols = (len(items) + max_rows - 1) // max_rows
    for row in range(max_rows):
        line = ""
        for col in range(num_cols):
            idx = col * max_rows + row
            if idx < len(items):
                line += f"{idx + 1:3d}. {items[idx]:<{col_width}}"
        if line:
            click.echo(line)


def prompt_select_index(prompt: str, *, count: int, default: Optional[int] = None) -> int:
    """Prompt for a 1-based index."""
    if count <= 0:
        raise click.ClickException("Nothing to select from")
    return click.prompt(
        click.style(prompt, fg=COLORS["prompt"]),
        type=click.IntRange(1, count),
        default=default,
    )


def prompt_subject_ids(subjects: List[str]) -> List[str]:
    """Prompt user for subject selection by number or subject id."""
    echo_section("Available Subjects")
    display_table(subjects)
    click.echo()

    selection = click.prompt(
        click.style("Enter subject numbers (comma-separated) or IDs", fg=COLORS["prompt"]),
        type=str,
    )

    selected: List[str] = []
    for tok in selection.split(","):
        t = tok.strip()
        if not t:
            continue
        if t.isdigit():
            n = int(t)
            if 1 <= n <= len(subjects):
                selected.append(subjects[n - 1])
            else:
                echo_warning(f"Invalid number: {n}")
        else:
            if t in subjects:
                selected.append(t)
            else:
                echo_warning(f"Unknown subject: {t}")

    selected = list(dict.fromkeys(selected))  # stable unique
    if not selected:
        raise click.ClickException("No valid subjects selected")
    return selected


# =============================================================================
# Sys.argv/module helpers
# =============================================================================


def run_main_with_argv(
    progname: str,
    argv: Sequence[str],
    main: Callable[[], T],
) -> T:
    """
    Run a "main()" function that reads argparse/sys.argv by temporarily overriding sys.argv.
    """
    old_argv = sys.argv[:]
    try:
        sys.argv = [progname, *argv]
        return main()
    finally:
        sys.argv = old_argv


def ensure_repo_root_importable(repo_root: Path) -> None:
    """Ensure repo root is on sys.path and PYTHONPATH."""
    sys.path.insert(0, str(repo_root))
    os.environ["PYTHONPATH"] = f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}".rstrip(os.pathsep)


# =============================================================================
# Project structure helpers
# =============================================================================


def discover_simulations(project_dir: Path, subject_id: str) -> List[str]:
    sim_base = project_dir / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / "Simulations"
    if not sim_base.exists():
        return []
    sims: List[str] = []
    for sim_dir in sorted(sim_base.glob("*")):
        if not sim_dir.is_dir():
            continue
        if (sim_dir / "TI" / "mesh").is_dir() or (sim_dir / "TI" / "niftis").is_dir():
            sims.append(sim_dir.name)
    return sims


def discover_fields(project_dir: Path, subject_id: str, simulation_name: str, space_type: str) -> List[Path]:
    base = project_dir / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / "Simulations" / simulation_name / "TI"
    if space_type == "mesh":
        field_dir = base / "mesh"
        return sorted(field_dir.glob("*.msh")) if field_dir.is_dir() else []
    field_dir = base / "niftis"
    if not field_dir.is_dir():
        return []
    return sorted(list(field_dir.glob("*.nii")) + list(field_dir.glob("*.nii.gz")))


