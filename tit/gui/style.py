#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared design tokens and application-level stylesheet for TI-Toolbox GUI.

Usage
-----
In main.py::

    from tit.gui.style import APP_STYLESHEET, SP_SM, SP_MD, SP_LG
    app.setStyleSheet(APP_STYLESHEET)

In individual widgets use SP_* for setContentsMargins / setSpacing calls so
that layout geometry stays on the same scale.  Font sizes are in points (pt)
so Qt maps them through the screen's logical DPI automatically.
"""

# ---------------------------------------------------------------------------
# Spacing scale (logical pixels — Qt scales these with AA_EnableHighDpiScaling)
# ---------------------------------------------------------------------------
SP_XS = 4  # tight inline gaps, icon padding, thin borders
SP_SM = 8  # control padding, inner group margins
SP_MD = 12  # section separation
SP_LG = 20  # outer panel / dialog margins

# ---------------------------------------------------------------------------
# Font size scale (points — device-density-aware)
# ---------------------------------------------------------------------------
FONT_SM = "4pt"  # secondary / hint / caption labels
FONT_MD = "5pt"  # body text, console output, form fields
FONT_LG = "5pt"  # section headings, group-box titles, busy messages
FONT_XL = "6pt"  # tab titles, page headings

# ---------------------------------------------------------------------------
# Application-level stylesheet
#
# Covers all shared widget types so per-widget setStyleSheet() calls can be
# removed except where a widget needs a genuinely unique style (e.g. the dark
# console, the green Run button, the red Stop button).
# ---------------------------------------------------------------------------
APP_STYLESHEET = f"""
/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    padding: {SP_XS}px {SP_SM}px;
    border-radius: 3px;
    border: 1px solid #b0b0b0;
    background-color: #f0f0f0;
    font-size: {FONT_MD};
}}
QPushButton:hover  {{ background-color: #e2e2e2; border-color: #888; }}
QPushButton:pressed {{ background-color: #d0d0d0; }}
QPushButton:disabled {{ color: #999999; border-color: #cccccc;
                        background-color: #f8f8f8; }}

/* ── Group boxes ─────────────────────────────────────────────────────────── */
QGroupBox {{
    font-weight: bold;
    font-size: {FONT_LG};
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

/* ── Input controls ──────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    padding: 3px {SP_XS}px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    font-size: {FONT_MD};
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
/* QComboBox kept separate — no background-color override so Fusion can
   render the drop-button and selection area without a white box artefact. */
QComboBox {{
    padding: 2px {SP_XS}px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    font-size: {FONT_MD};
    min-height: 22px;
}}
QComboBox:focus {{ border-color: #4a90d9; }}
QComboBox:disabled {{ color: #888888; }}


/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {{
    font-size: {FONT_MD};
}}

/* ── Tab bar ─────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid #888888;
    border-radius: 3px;
}}
QTabBar::tab {{
    padding: 8px 16px;
    font-size: 5pt;
    min-width: 60px;
    border: 1px solid #888888;
    border-bottom: none;
    background-color: #e8e8e8;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
}}
QTabBar::tab:selected {{
    font-weight: bold;
    background-color: #ffffff;
    border-color: #555555;
}}
QTabBar::tab:!selected:hover {{
    background-color: #f0f0f0;
}}
/* Each scroller slot — one slot per arrow button */
QTabBar::scroller {{
    width: 24px;
}}
/* Scroll buttons shown when tabs overflow the bar width */
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

/* ── Table / list views ──────────────────────────────────────────────────── */
QTableWidget, QListWidget {{
    font-size: {FONT_MD};
    border: 1px solid #cccccc;
    border-radius: 3px;
    gridline-color: #e0e0e0;
}}
QHeaderView::section {{
    font-size: {FONT_MD};
    font-weight: bold;
    padding: {SP_XS}px;
    border: none;
    border-bottom: 1px solid #cccccc;
    background-color: #f5f5f5;
}}

/* ── Check boxes / radio buttons ─────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    font-size: {FONT_MD};
    spacing: {SP_XS}px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
}}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
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

/* ── Tool tips ───────────────────────────────────────────────────────────── */
QToolTip {{
    font-size: {FONT_MD};
    padding: {SP_XS}px {SP_SM}px;
    border: 1px solid #aaaaaa;
    border-radius: 3px;
    background-color: #ffffcc;
    color: #333333;
}}
"""
