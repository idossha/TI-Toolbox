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
# The module-level FONT_* constants are now computed dynamically from
# GraphicsConfig at import time (see bottom of file).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Application-level stylesheet builder
#
# Covers all shared widget types so per-widget setStyleSheet() calls can be
# removed except where a widget needs a genuinely unique style (e.g. the dark
# console, the green Run button, the red Stop button).
# ---------------------------------------------------------------------------


def build_stylesheet(config=None):
    """Build and return the application-level stylesheet string.

    Parameters
    ----------
    config : GraphicsConfig or None
        Visual preference settings.  When *None* the :class:`GraphicsConfig`
        defaults are used.  The import is deferred inside the function to avoid
        circular-import issues.

    Returns
    -------
    str
        A complete Qt stylesheet string with font-size tokens substituted from
        *config*.
    """
    # Lazy import to avoid circular dependencies between style.py and
    # graphics_config.py (which may in turn import from tit.core).
    from tit.gui.graphics_config import GraphicsConfig  # noqa: PLC0415

    if config is None:
        config = GraphicsConfig()

    # Derive the four font-size tokens from config values.
    font_md = f"{config.font_size_body}pt"      # body text / form fields
    font_lg = f"{config.font_size_heading}pt"   # section headings / group boxes
    font_console = f"{config.font_size_console}pt"  # console output (unused in
                                                    # global sheet but available)
    font_tab = f"{config.font_size_tab}pt"      # tab-bar labels

    return f"""
/* ── Buttons ─────────────────────────────────────────────────────────────── */
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

/* ── Group boxes ─────────────────────────────────────────────────────────── */
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

/* ── Input controls ──────────────────────────────────────────────────────── */
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
/* QComboBox kept separate — no background-color override so Fusion can
   render the drop-button and selection area without a white box artefact. */
QComboBox {{
    padding: 2px {SP_XS}px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    font-size: {font_md};
    min-height: 22px;
}}
QComboBox:focus {{ border-color: #4a90d9; }}
QComboBox:disabled {{ color: #888888; }}


/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {{
    font-size: {font_md};
}}

/* ── Tab bar ─────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid #888888;
    border-radius: 3px;
}}
QTabBar::tab {{
    padding: 8px 16px;
    font-size: {font_tab};
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

/* ── Check boxes / radio buttons ─────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    font-size: {font_md};
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
    font-size: {font_md};
    padding: {SP_XS}px {SP_SM}px;
    border: 1px solid #aaaaaa;
    border-radius: 3px;
    background-color: #ffffcc;
    color: #333333;
}}

/* ── Menus (gear icon dropdown etc.) ─────────────────────────────────────── */
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

/* ── Sliders ─────────────────────────────────────────────────────────────── */
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

/* ── SpinBox sizing ───────────────────────────────────────────────────────── */
/* Let Fusion use its natural height so native_btn_w is large enough for
   _NarrowSpinStyle to produce a visible delta (see bottom of this file). */
QSpinBox, QDoubleSpinBox {{
    min-height: 18px;
}}
"""


# Module-level constant — keeps any existing ``from tit.gui.style import
# APP_STYLESHEET`` imports working without change.
APP_STYLESHEET = build_stylesheet()

# ---------------------------------------------------------------------------
# Computed font constants — resolved from GraphicsConfig at import time.
# Import these in other GUI files instead of using literal "Xpt" strings.
# ---------------------------------------------------------------------------
from tit.gui.graphics_config import get_graphics_config as _get_gfx_tokens  # noqa: E402
_gfx_tok = _get_gfx_tokens()

FONT_SM         = f"{_gfx_tok.font_size_sm}pt"
FONT_MD         = f"{_gfx_tok.font_size_body}pt"
FONT_LG         = f"{_gfx_tok.font_size_heading}pt"
FONT_XL         = f"{_gfx_tok.font_size_tab}pt"
FONT_HELP       = f"{_gfx_tok.font_size_help}pt"
FONT_SECTION    = f"{_gfx_tok.font_size_section_title}pt"
FONT_SUBHEADING = f"{_gfx_tok.font_size_subheading}pt"
FONT_MONOSPACE  = f"{_gfx_tok.font_size_monospace}pt"
FONT_NOTE       = f"{_gfx_tok.font_size_note}pt"

_gfx_tokens = _gfx_tok  # public alias for QFont size lookups

# ---------------------------------------------------------------------------
# Proxy style — narrows QSpinBox / QDoubleSpinBox button column
#
# Styling QSpinBox::up-button via CSS on Qt5/Fusion/Linux suppresses the
# native arrow glyph entirely (the painter is handed to the CSS engine which
# needs an explicit image: to draw anything).  Overriding subControlRect()
# instead only changes the geometry; Fusion's own painter still draws the
# arrows correctly.
# ---------------------------------------------------------------------------
from PyQt5 import QtWidgets as _QtW, QtCore as _QtC  # noqa: E402


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

        # Ask the parent style for the native button width once.
        native_btn_w = super().subControlRect(
            cc, opt, _QtW.QStyle.SC_SpinBoxUp, widget
        ).width()
        delta = native_btn_w - self._TARGET_BTN_W
        if delta <= 0:
            return rect  # already narrow enough

        if sc in (_QtW.QStyle.SC_SpinBoxUp, _QtW.QStyle.SC_SpinBoxDown):
            # Shift left edge rightward → narrower column.
            return rect.adjusted(delta, 0, 0, 0)
        # SC_SpinBoxEditField: extend right edge to reclaim the freed space.
        return rect.adjusted(0, 0, delta, 0)
