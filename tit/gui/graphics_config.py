"""Graphics configuration — per-project visual preferences.

Settings are persisted to ``code/ti-toolbox/config/graphics.json`` inside the
active project directory (alongside ``extensions.json``).  When no project is
loaded the module returns ``DEFAULTS`` silently so the rest of the GUI is never
blocked.

Usage::

    from tit.gui.graphics_config import get_graphics_config, save_graphics_config

    cfg = get_graphics_config()          # cached after first call
    cfg2 = GraphicsConfig(font_scale=1.2)
    save_graphics_config(cfg2)
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class GraphicsConfig:
    """Visual preference settings for the TI-Toolbox GUI.

    Default values match the current hardcoded values so that the first run
    (before the user saves anything) is indistinguishable from the old
    behaviour.
    """

    # ---- Window ------------------------------------------------------------
    window_width: int = 1143
    """Initial main-window width in pixels."""

    window_height: int = 1000
    """Initial main-window height in pixels."""

    # ---- Console -----------------------------------------------------------
    console_min_height: int = 200
    """Minimum height of embedded log consoles in pixels."""

    console_max_height: int = 600
    """Maximum height of embedded log consoles in pixels."""

    # ---- Font --------------------------------------------------------------
    font_scale: float = 1.0
    """Multiplier applied to all font-size tokens (0.5–2.0)."""

    font_size_body: int = 5
    """Body text / form fields font size in pt (maps to FONT_MD)."""

    font_size_heading: int = 5
    """Section headings / group-box titles font size in pt (maps to FONT_LG)."""

    font_size_console: int = 5
    """Console output font size in pt."""

    font_size_tab: int = 7
    """Tab-bar label font size in pt."""

    font_size_sm: int = 4
    """Very small hint/caption text (e.g. pre-processing parallel-job comments)."""

    font_size_help: int = 8
    """Help / annotation text below form controls."""

    font_size_section_title: int = 7
    """Intra-tab section/panel title labels."""

    font_size_subheading: int = 10
    """Emphasized section headings (dialog group boxes, electrode titles, status labels)."""

    font_size_monospace: int = 10
    """Fixed-width text views (NIfTI viewer output, Quick Notes, rich-text widgets)."""

    font_size_note: int = 9
    """Note and info labels (e.g. 'Changes apply on next launch')."""

    # ---- NIfTI Viewer ----------------------------------------------------------
    nifti_field_opacity: int = 70
    """Initial opacity (0–100) for field overlays in the NIfTI viewer."""

    nifti_atlas_opacity: int = 50
    """Initial opacity (0–100) for atlas overlays in the NIfTI viewer."""

    # ---- Layout ----------------------------------------------------------------
    config_panel_max_height: int = 600
    """Maximum height (px) of configuration scroll-area panels across all tabs."""

    # ---- Icon sizes ------------------------------------------------------------
    icon_size_gear: int = 24
    """Font size (px) of the gear ⚙ settings button glyph."""

    icon_size_extensions: int = 18
    """Font size (px) of the extensions ◳ button glyph."""


#: Canonical defaults — compare against this to detect "nothing saved yet".
DEFAULTS = GraphicsConfig()

# ---------------------------------------------------------------------------
# Internal cache
# ---------------------------------------------------------------------------

_cached_config: Optional[GraphicsConfig] = None


def reset_cached_config() -> None:
    """Clear the in-process cache.

    Useful in tests and after saving new settings to force a reload on the
    next :func:`get_graphics_config` call.
    """
    global _cached_config
    _cached_config = None


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _config_path() -> Optional[Path]:
    """Return the path to ``graphics.json``, or *None* if not available.

    Returns ``None`` (instead of raising) when PathManager has not been
    initialised yet — e.g. when the application starts without a project.
    """
    try:
        from tit.core import get_path_manager

        pm = get_path_manager()
        config_dir = Path(pm.ensure_dir("ti_toolbox_config"))
        return config_dir / "graphics.json"
    except Exception:
        return None


def load_graphics_config() -> GraphicsConfig:
    """Load :class:`GraphicsConfig` from disk.

    Returns :data:`DEFAULTS` when:
    - PathManager is not yet initialised (no project open), or
    - ``graphics.json`` does not exist yet.

    Unknown keys in the JSON file are silently ignored so that downgrading
    the application does not break anything.
    """
    path = _config_path()
    if path is None or not path.exists():
        return dataclasses.replace(DEFAULTS)

    try:
        with path.open("r", encoding="utf-8") as fh:
            raw: dict = json.load(fh)
    except Exception as exc:
        logger.warning("Could not read graphics.json (%s); using defaults.", exc)
        return dataclasses.replace(DEFAULTS)

    # Build config from defaults, overriding only known fields.
    known_fields = {f.name for f in dataclasses.fields(GraphicsConfig)}
    filtered = {k: v for k, v in raw.items() if k in known_fields}

    try:
        return GraphicsConfig(**filtered)
    except Exception as exc:
        logger.warning("Malformed graphics.json (%s); using defaults.", exc)
        return dataclasses.replace(DEFAULTS)


def save_graphics_config(config: GraphicsConfig) -> None:
    """Persist *config* to ``graphics.json``.

    Raises :exc:`RuntimeError` when PathManager is not initialised (no
    project is open) — callers should guard against this by checking
    :func:`_config_path` or disabling the Save button when no project is
    loaded.
    """
    path = _config_path()
    if path is None:
        raise RuntimeError(
            "Cannot save graphics settings: no project is currently open."
        )

    data = dataclasses.asdict(config)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    logger.debug("Saved graphics config to %s", path)

    # Invalidate cache so that any subsequent get_graphics_config() call
    # in the same process reflects the new values.
    reset_cached_config()


def get_graphics_config() -> GraphicsConfig:
    """Return the cached :class:`GraphicsConfig`, loading it on first call.

    This function never raises.  When PathManager is unavailable it returns
    :data:`DEFAULTS` silently so the GUI can initialise normally.
    """
    global _cached_config
    if _cached_config is None:
        _cached_config = load_graphics_config()
    return _cached_config
