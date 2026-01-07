"""
CLI direct-mode smoke tests.

Goal: Every CLI module should be runnable in "direct" interaction mode and at
minimum render `--help` successfully. This catches:
- broken imports at module import time
- argparse misconfiguration that prevents showing help
- accidental heavy imports during import-time (best practice: lazy import in execute())
"""

from __future__ import annotations

import subprocess
import sys

import pytest


CLI_MODULES = [
    "tit.cli.analyzer",
    "tit.cli.cluster_permuatation",
    "tit.cli.create_leadfield",
    "tit.cli.ex_search",
    "tit.cli.flex_search",
    "tit.cli.group_analyzer",
    "tit.cli.gui",
    "tit.cli.pre_process",
    "tit.cli.simulator",
    "tit.cli.vis_blender",
    "tit.cli.advanced.batch_simulate",
]


@pytest.mark.unit
@pytest.mark.parametrize("module", CLI_MODULES)
def test_cli_module_help_smoke(module: str):
    """
    `python -m <module> --help` must exit 0 for every CLI module.
    """
    p = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, (
        f"{module} --help failed.\n"
        f"stdout:\n{p.stdout}\n\n"
        f"stderr:\n{p.stderr}\n"
    )



