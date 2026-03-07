#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared design tokens and application-level stylesheet for TI-Toolbox GUI.

All visual constants (fonts, spacing, sizes) are defined here as plain
module-level values.  There is no user-facing settings file -- these are
sensible defaults for the Docker container environment (96 DPI via
QT_FONT_DPI).

Qt resolves pt sizes via: pixelSize = DPI * pointSize / 72.
At 96 DPI:  9pt = 12px, 10pt ≈ 13px, 12pt = 16px, 13pt ≈ 17px.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Spacing scale (logical pixels -- Qt scales with AA_EnableHighDpiScaling)
# ---------------------------------------------------------------------------
SP_XS = 4  # tight inline gaps, icon padding, thin borders
SP_SM = 8  # control padding, inner group margins
SP_MD = 12  # section separation
SP_LG = 20  # outer panel / dialog margins

# ---------------------------------------------------------------------------
# Font sizes (points -- resolved against 96 DPI in Docker)
#
# Reference: v2.2.4 used 13-14px for body/console, which is 10-11pt @ 96 DPI.
# ---------------------------------------------------------------------------
FONT_SIZE_SM = 8  # small hints, captions
FONT_SIZE_BODY = 10  # body text, form fields, labels
FONT_SIZE_HEADING = 13  # section headings, group-box titles
FONT_SIZE_TAB = 10  # tab-bar labels
FONT_SIZE_CONSOLE = 10  # console output (monospace)
FONT_SIZE_HELP = 9  # help / annotation text
FONT_SIZE_SECTION = 12  # intra-tab section titles
FONT_SIZE_SUBHEADING = 12  # dialog group boxes, electrode titles
FONT_SIZE_MONOSPACE = 10  # fixed-width views (NIfTI, Quick Notes)
FONT_SIZE_NOTE = 9  # note / info labels

# Pre-built "Xpt" strings for setStyleSheet / QFont usage
FONT_SM = f"{FONT_SIZE_SM}pt"
FONT_MD = f"{FONT_SIZE_BODY}pt"
FONT_LG = f"{FONT_SIZE_HEADING}pt"
FONT_XL = f"{FONT_SIZE_TAB}pt"
FONT_HELP = f"{FONT_SIZE_HELP}pt"
FONT_SECTION = f"{FONT_SIZE_SECTION}pt"
FONT_SUBHEADING = f"{FONT_SIZE_SUBHEADING}pt"
FONT_MONOSPACE = f"{FONT_SIZE_MONOSPACE}pt"
FONT_NOTE = f"{FONT_SIZE_NOTE}pt"

# ---------------------------------------------------------------------------
# Window / layout sizes
# ---------------------------------------------------------------------------
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800
CONSOLE_MIN_HEIGHT = 200
CONSOLE_MAX_HEIGHT = 600
CONFIG_PANEL_MAX_HEIGHT = 600

# ---------------------------------------------------------------------------
# NIfTI viewer defaults
# ---------------------------------------------------------------------------
NIFTI_FIELD_OPACITY = 70  # 0-100
NIFTI_ATLAS_OPACITY = 50  # 0-100

# ---------------------------------------------------------------------------
# Icon sizes (pixels)
# ---------------------------------------------------------------------------
ICON_SIZE_GEAR = 18
ICON_SIZE_EXTENSIONS = 16

# ---------------------------------------------------------------------------
# Application-level stylesheet
# ---------------------------------------------------------------------------


def build_stylesheet():
    """Build and return the application-level stylesheet string."""
    font_md = FONT_MD
    font_lg = FONT_LG
    font_tab = FONT_XL

    return f"""
/* -- Buttons ------------------------------------------------------------ */
QPushButton {{
    padding: {SP_XS}px {SP_SM}px;
    border-radius: 3px;
    border: 1px solid #b0b0b0;
    background-color: #f0f0f0;
    font-size: {font_md};
}}
QPushButton:hover  {{ background-color: #e2e2e2; border-color: #888; }}
QPushButton:pressed {{ background-color: #d0d0d0; }}
QPushButton:disabled {{ color: #999999; border-color: #cccccc;
                        background-color: #f8f8f8; }}

/* -- Group boxes -------------------------------------------------------- */
QGroupBox {{
    font-weight: bold;
    font-size: {font_lg};
    border: 1px solid #cccccc;
    border-radius: 4px;
    margin-top: {SP_SM}px;
    padding-top: {SP_SM}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {SP_SM}px;
    padding: 0 {SP_XS}px;
}}

/* -- Input controls ----------------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    padding: 3px {SP_XS}px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    font-size: {font_md};
    background-color: white;
    min-height: 22px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: #4a90d9;
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: #f5f5f5;
    color: #888888;
}}
QComboBox {{
    padding: 2px {SP_XS}px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    font-size: {font_md};
    min-height: 22px;
}}
QComboBox:focus {{ border-color: #4a90d9; }}
QComboBox:disabled {{ color: #888888; }}

/* -- Labels ------------------------------------------------------------- */
QLabel {{
    font-size: {font_md};
}}

/* -- Tab bar ------------------------------------------------------------ */
QTabWidget::pane {{
    border: 1px solid #888888;
    border-radius: 3px;
    padding: 0px;
}}
QTabBar::tab {{
    padding: 6px 18px;
    font-size: {font_tab};
    min-width: 60px;
    border: 1px solid #888888;
    border-bottom: none;
    background-color: #e8e8e8;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
}}
QTabBar::tab:selected {{
    background-color: #ffffff;
    border-color: #555555;
}}
QTabBar::tab:!selected:hover {{
    background-color: #f0f0f0;
}}
QTabBar::scroller {{
    width: 24px;
}}
QTabBar QToolButton {{
    background-color: #f0f0f0;
    border: 1px solid #b0b0b0;
    border-radius: 3px;
    width: 22px;
    height: 22px;
    padding: 0px;
}}
QTabBar QToolButton:hover    {{ background-color: #e2e2e2; border-color: #888; }}
QTabBar QToolButton:pressed  {{ background-color: #d0d0d0; }}
QTabBar QToolButton:disabled {{ color: #cccccc; background-color: #f8f8f8;
                                border-color: #dddddd; }}

/* -- Table / list views ------------------------------------------------- */
QTableWidget, QListWidget {{
    font-size: {font_md};
    border: 1px solid #cccccc;
    border-radius: 3px;
    gridline-color: #e0e0e0;
}}
QHeaderView::section {{
    font-size: {font_md};
    font-weight: bold;
    padding: {SP_XS}px;
    border: none;
    border-bottom: 1px solid #cccccc;
    background-color: #f5f5f5;
}}

/* -- Check boxes / radio buttons ---------------------------------------- */
QCheckBox, QRadioButton {{
    font-size: {font_md};
    spacing: {SP_XS}px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
}}

/* -- Scroll bars -------------------------------------------------------- */
QScrollBar:vertical {{
    width: 10px;
    border: none;
    background: #f0f0f0;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: #c0c0c0;
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: #a0a0a0; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    height: 10px;
    border: none;
    background: #f0f0f0;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: #c0c0c0;
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: #a0a0a0; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* -- Tool tips ---------------------------------------------------------- */
QToolTip {{
    font-size: {font_md};
    padding: {SP_XS}px {SP_SM}px;
    border: 1px solid #aaaaaa;
    border-radius: 3px;
    background-color: #ffffcc;
    color: #333333;
}}

/* -- Menus -------------------------------------------------------------- */
QMenu {{
    font-size: {font_md};
    padding: 2px;
}}
QMenu::item {{
    padding: 3px 20px 3px 10px;
}}
QMenu::item:selected {{
    background-color: #4a90d9;
    color: white;
}}

/* -- Sliders ------------------------------------------------------------ */
QSlider::groove:horizontal {{
    height: 4px;
    background: #cccccc;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
    background: #f0f0f0;
    border: 1px solid #999999;
}}
QSlider::groove:vertical {{
    width: 4px;
    background: #cccccc;
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    width: 12px;
    height: 12px;
    margin: 0 -4px;
    border-radius: 6px;
    background: #f0f0f0;
    border: 1px solid #999999;
}}

/* -- SpinBox sizing ----------------------------------------------------- */
QSpinBox, QDoubleSpinBox {{
    min-height: 18px;
}}
"""


# Pre-built stylesheet for ``from tit.gui.style import APP_STYLESHEET``.
APP_STYLESHEET = build_stylesheet()


# ---------------------------------------------------------------------------
# QProxyStyle for narrower spin-box buttons
# ---------------------------------------------------------------------------
from PyQt5 import QtWidgets as _QtW  # noqa: E402


class _NarrowSpinStyle(_QtW.QProxyStyle):
    """Wraps Fusion and narrows the up/down button column of every spin box."""

    _TARGET_BTN_W = 6  # desired button-column width in pixels

    def subControlRect(self, cc, opt, sc, widget=None):
        rect = super().subControlRect(cc, opt, sc, widget)
        if cc != _QtW.QStyle.CC_SpinBox:
            return rect
        if sc not in (
            _QtW.QStyle.SC_SpinBoxUp,
            _QtW.QStyle.SC_SpinBoxDown,
            _QtW.QStyle.SC_SpinBoxEditField,
        ):
            return rect

        native_btn_w = (
            super().subControlRect(cc, opt, _QtW.QStyle.SC_SpinBoxUp, widget).width()
        )
        delta = native_btn_w - self._TARGET_BTN_W
        if delta <= 0:
            return rect

        if sc in (_QtW.QStyle.SC_SpinBoxUp, _QtW.QStyle.SC_SpinBoxDown):
            return rect.adjusted(delta, 0, 0, 0)
        return rect.adjusted(0, 0, delta, 0)
