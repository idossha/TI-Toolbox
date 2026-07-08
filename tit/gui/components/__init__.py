#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Reusable UI components for the TI-Toolbox GUI.

This package collects shared widgets (console, electrode config, ROI picker,
subject rows, action buttons, etc.) used across multiple GUI tabs.
"""

from .console import ConsoleWidget
from .action_buttons import RunStopButtons
from .atlas_region_finder import AtlasRegionFinderDialog, merge_into_lineedit
from .base_thread import detect_message_type_from_content
from .electrode_config import ElectrodeConfigWidget
from .help_icon import HelpIcon
from .qsi_config_dialogs import QSIPrepConfigDialog, QSIReconConfigDialog
from .region_chips import FlowLayout, RegionChipsWidget
from .roi_picker import ROIPickerWidget
from .solver_params import SolverParamsWidget

__all__ = [
    "AtlasRegionFinderDialog",
    "ConsoleWidget",
    "ElectrodeConfigWidget",
    "FlowLayout",
    "HelpIcon",
    "RegionChipsWidget",
    "ROIPickerWidget",
    "RunStopButtons",
    "SolverParamsWidget",
    "detect_message_type_from_content",
    "merge_into_lineedit",
    "QSIPrepConfigDialog",
    "QSIReconConfigDialog",
    "SubjectRow",
    "SubjectRowManager",
]

from .subject_row import SubjectRow, SubjectRowManager
