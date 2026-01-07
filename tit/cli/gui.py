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

    def execute(self, args: dict) -> int:
        # Direct mode: no args; just launch GUI module.
        runpy.run_module("tit.gui.main", run_name="__main__")
        return 0

if __name__ == "__main__":
    raise SystemExit(GuiCLI().run())

