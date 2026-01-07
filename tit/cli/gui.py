#!/usr/bin/env simnibs_python
"""
TI-Toolbox GUI Launcher (Python).

Replaces `tit/cli/GUI.sh`.

Usage:
  simnibs_python -m tit.cli.gui
"""

from __future__ import annotations

import runpy
from tit.cli.base import BaseCLI
from tit.cli import utils


class GuiCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__(description="Launch the TI-Toolbox GUI (Qt).")

if __name__ == "__main__":
    runpy.run_module("tit.gui.main", run_name="__main__")

