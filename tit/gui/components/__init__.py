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
from .electrode_config import ElectrodeConfigWidget
from .qsi_config_dialogs import QSIPrepConfigDialog, QSIReconConfigDialog
from .roi_picker import ROIPickerWidget
from .solver_params import SolverParamsWidget

__all__ = [
    "ConsoleWidget",
    "ElectrodeConfigWidget",
    "ROIPickerWidget",
    "RunStopButtons",
    "SolverParamsWidget",
    "detect_message_type_from_content",
    "QSIPrepConfigDialog",
    "QSIReconConfigDialog",
    "SubjectRow",
    "SubjectRowManager",
]

from .subject_row import SubjectRow, SubjectRowManager
