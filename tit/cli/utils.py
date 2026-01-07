from __future__ import annotations

"""
Shared utilities for TI-Toolbox CLIs.

Goals:
- Keep CLI UX consistent (styling, prompts, tables)
- Centralize repetitive env + path discovery logic
- Make direct vs interactive flows uniform across CLIs
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple, TypeVar, Union
import csv
from datetime import datetime
import shlex

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

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return sys.stdout.isatty()


def style(text: str, *, fg: Optional[str] = None, bold: bool = False) -> str:
    if not _use_color():
        return text
    parts: List[str] = []
    if bold:
        parts.append(_ANSI["bold"])
    if fg and fg in _ANSI:
        parts.append(_ANSI[fg])
    parts.append(text)
    parts.append(_ANSI["reset"])
    return "".join(parts)


def prompt_text(text: str) -> str:
    return style(text, fg=COLORS["prompt"], bold=True)


def echo_header(text: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {style(text, fg=COLORS['header'], bold=True)}")
    print(f"{'=' * 50}\n")


def echo_section(text: str) -> None:
    print(f"\n{style(text, fg=COLORS['header'], bold=True)}")
    print(style("-" * len(text), fg=COLORS["header"]))


def echo_success(text: str) -> None:
    print(style("✓ ", fg=COLORS["success"], bold=True) + style(text, fg=COLORS["success"]))


def echo_warning(text: str) -> None:
    print(style("⚠ ", fg=COLORS["warning"], bold=True) + style(text, fg=COLORS["warning"]))


def echo_error(text: str) -> None:
    print(style("✗ ", fg=COLORS["error"], bold=True) + style(text, fg=COLORS["error"]))


def echo_info(text: str) -> None:
    print(style("ℹ ", fg=COLORS["info"], bold=True) + style(text, fg=COLORS["info"]))


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
        raise RuntimeError(f"Missing required environment variable: {name}")
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
            print(line)


def print_options(options: List[str]) -> None:
    """
    Print options in a compact multi-column table.

    Requirement: keep the list readable even for long option sets (e.g. electrodes),
    by rendering with a maximum of 10 rows per column.
    """
    # NOTE: avoid ANSI styling here to keep column alignment stable.
    display_table(options, max_rows=10, col_width=25)


def ask(prompt: str, *, default: Optional[str] = None) -> str:
    suffix = ""
    if default is not None and default != "":
        suffix = style(f" (default {default})", fg=COLORS["info"])
    raw = input(f"{prompt_text(prompt)}{suffix}: ").strip()
    if not raw and default is not None:
        return str(default)
    return raw


def ask_required(prompt: str, *, default: Optional[str] = None) -> str:
    """Ask for a non-empty value. If default is provided, empty accepts default."""
    while True:
        val = ask(prompt, default=default)
        if val.strip():
            return val
        echo_error("Value required.")


def ask_float(prompt: str, *, default: Optional[Union[str, float]] = None) -> float:
    while True:
        raw = ask_required(prompt, default=(str(default) if default is not None else None))
        try:
            return float(raw)
        except ValueError:
            echo_error("Please enter a number.")


def ask_int(prompt: str, *, default: Optional[Union[str, int]] = None) -> int:
    while True:
        raw = ask_required(prompt, default=(str(default) if default is not None else None))
        try:
            return int(raw)
        except ValueError:
            echo_error("Please enter an integer.")


def ask_bool(prompt: str, *, default: bool = False) -> bool:
    """
    Ask a boolean as a concrete decision (Yes/No).
    Accepts: 1/2, y/n, yes/no. Enter accepts default.
    """
    default_idx = 1 if default else 2
    print(f"{prompt_text(prompt)} [1-2] (default {default_idx}):")
    print_options(["Yes", "No"])
    while True:
        raw = input(f"{prompt_text('Selection')}: ").strip().lower()
        if not raw:
            return default
        if raw in {"1", "y", "yes", "true", "on"}:
            return True
        if raw in {"2", "n", "no", "false", "off"}:
            return False
        echo_warning("Invalid selection. Please choose 1 or 2 (or press Enter for default).")


def choose_one(prompt: str, options: List[str], *, default: Optional[str] = None, help_text: Optional[str] = None) -> str:
    """Choose one from options; optional default must be in options."""
    if not options:
        raise RuntimeError("No options available.")
    if help_text:
        echo_info(help_text)
    default_idx: Optional[int] = None
    if default is not None and default in options:
        default_idx = options.index(default) + 1
    print(f"{prompt_text(prompt)} [1-{len(options)}]{f' (default {default_idx})' if default_idx else ''}:")
    print_options(options)
    while True:
        raw = input(f"{prompt_text('Selection')}: ").strip()
        if not raw and default_idx is not None:
            return options[default_idx - 1]
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(options):
                return options[n - 1]
        echo_warning("Invalid selection. Please choose a number from the list.")


def choose_many(prompt: str, options: List[str], *, help_text: Optional[str] = None, min_count: int = 1) -> List[str]:
    """Choose many by comma-separated indices (1-based)."""
    if not options:
        raise RuntimeError("No options available.")
    if help_text:
        echo_info(help_text)
    print(f"{prompt_text(prompt)} (comma-separated indices):")
    print_options(options)
    while True:
        raw = input(f"{prompt_text('Selection')}: ").strip()
        if not raw:
            echo_error("Value required.")
            continue
        out: List[str] = []
        ok = True
        for tok in raw.split(","):
            t = tok.strip()
            if not t.isdigit():
                ok = False
                break
            idx = int(t)
            if not (1 <= idx <= len(options)):
                ok = False
                break
            out.append(options[idx - 1])
        out = list(dict.fromkeys(out))
        if ok and len(out) >= min_count:
            return out
        echo_error("Invalid selection.")


def choose_or_enter(
    *,
    prompt: str,
    options: List[str],
    default: Optional[str] = None,
    allow_enter: bool = True,
    enter_label: str = "Enter manually…",
    help_text: Optional[str] = None,
) -> str:
    """Choose from options or explicitly pick 'Enter manually…'."""
    opts = list(options)
    if allow_enter:
        opts.append(enter_label)
    choice = choose_one(prompt, opts, default=default if default in opts else None, help_text=help_text)
    if allow_enter and choice == enter_label:
        return ask_required(prompt)
    return choice


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def cmd_preview(argv: List[str]) -> str:
    """Shell-ish preview of a command."""
    try:
        return shlex.join(argv)
    except Exception:
        return " ".join(argv)


def review_and_confirm(
    title: str,
    *,
    items: List[tuple[str, str]],
    command: Optional[List[str]] = None,
    env: Optional[List[tuple[str, str]]] = None,
    default_yes: bool = True,
) -> bool:
    """
    Verbose interactive review + confirmation gate.
    Returns True to proceed, False to abort.
    """
    echo_section(title)
    for k, v in items:
        print(f"{style(k + ':', fg=COLORS['header'], bold=True)} {v}")
    if env:
        echo_section("Environment")
        for k, v in env:
            print(f"{style(k + '=', fg=COLORS['header'], bold=True)} {v}")
    if command:
        echo_section("Command")
        print(cmd_preview(command))
    return ask_bool("Proceed?", default=default_yes)

def load_eeg_cap_labels(eeg_cap_csv_path: Path) -> List[str]:
    """
    Load electrode labels from an EEG cap CSV.
    Tries common schemas; falls back to last column.
    """
    if not eeg_cap_csv_path.is_file():
        return []
    with eeg_cap_csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            # Prefer explicit label/name fields
            preferred = None
            for cand in ["label", "name", "electrode", "electrode_name"]:
                if cand in reader.fieldnames:
                    preferred = cand
                    break
            labels: List[str] = []
            for row in reader:
                if preferred and row.get(preferred):
                    labels.append(str(row[preferred]).strip())
                else:
                    # last column fallback
                    last = row.get(reader.fieldnames[-1])
                    if last:
                        labels.append(str(last).strip())
            labels = [x for x in labels if x]
            labels = list(dict.fromkeys(labels))
            return labels
    return []


def prompt_select_index(prompt: str, *, count: int, default: Optional[int] = None) -> int:
    """Prompt for a 1-based index."""
    if count <= 0:
        raise RuntimeError("Nothing to select from")
    while True:
        raw = input(f"{prompt} [1-{count}]{f' (default {default})' if default else ''}: ").strip()
        if not raw and default is not None:
            return default
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= count:
                return n
        echo_warning("Invalid selection")


def prompt_subject_ids(subjects: List[str]) -> List[str]:
    """Prompt user for subject selection by number or subject id."""
    echo_section("Available Subjects")
    display_table(subjects)
    print()

    selection = input("Enter subject numbers (comma-separated) or IDs: ").strip()

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
        raise RuntimeError("No valid subjects selected")
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


