"""Extensions configuration persistence for TI-Toolbox GUI.

Handles reading and writing the extensions.json file that tracks
which GUI extensions are enabled/disabled across sessions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def get_extensions_config_path(config_dir: Path) -> Path:
    """Return the path to the extensions configuration file.

    Args:
        config_dir: The project config directory (from PathManager.config_dir()).
    """
    return Path(config_dir) / "extensions.json"


def ensure_extensions_config(config_path: Path) -> None:
    """Ensure the extensions config file exists with default values.

    Args:
        config_path: Full path to the extensions.json file.
    """
    if not config_path.exists():
        default_config: Dict[str, dict] = {"extensions": {}}
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)


def load_extensions_config(config_path: Path) -> dict:
    """Load the extensions configuration from file.

    Args:
        config_path: Full path to the extensions.json file.

    Returns:
        Dictionary with the extensions configuration.
    """
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    return {"extensions": {}}


def save_extension_state(config_path: Path, extension_name: str, enabled: bool) -> None:
    """Save the state of an extension (enabled/disabled as tab).

    Args:
        config_path: Full path to the extensions.json file.
        extension_name: Name of the extension.
        enabled: Whether the extension is enabled.
    """
    config = load_extensions_config(config_path)
    config["extensions"][extension_name] = enabled
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
