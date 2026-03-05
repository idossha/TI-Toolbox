#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
GUI Components Package
Reusable UI components for TI-Toolbox GUI

Note: PathManager lives at tit.paths
Import it from there: from tit.paths import get_path_manager
"""

from .console import ConsoleWidget
from .action_buttons import RunStopButtons
from .base_thread import detect_message_type_from_content
from .qsi_config_dialogs import QSIPrepConfigDialog, QSIReconConfigDialog

__all__ = [
    "ConsoleWidget",
    "RunStopButtons",
    "detect_message_type_from_content",
    "QSIPrepConfigDialog",
    "QSIReconConfigDialog",
]
