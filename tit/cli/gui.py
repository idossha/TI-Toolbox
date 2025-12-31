#!/usr/bin/env python3
"""
TI-Toolbox GUI Launcher (Python).

Replaces `tit/cli/GUI.sh`.

Usage:
  simnibs_python -m tit.cli.gui
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path

import click

from tit.cli import utils


def _repo_root_from_this_file() -> Path:
    # tit/cli/gui.py -> repo root is ../../
    return Path(__file__).resolve().parents[2]


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--run-direct", is_flag=True, help="No-op (GUI launch is already non-interactive).")
def cli(run_direct: bool) -> None:
    """Launch the TI-Toolbox GUI (Qt)."""
    _ = run_direct
    repo_root = _repo_root_from_this_file()

    # Match the bash script behavior: run from repo root and ensure imports resolve.
    os.chdir(repo_root)
    utils.ensure_repo_root_importable(repo_root)

    runpy.run_module("tit.gui.main", run_name="__main__")


if __name__ == "__main__":
    cli()


