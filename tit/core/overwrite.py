"""
Shared overwrite policy helpers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class OverwritePolicy:
    overwrite: bool = False
    prompt: bool = True


def get_overwrite_policy(
    overwrite: Optional[bool] = None, prompt: Optional[bool] = None
) -> OverwritePolicy:
    """Return an overwrite policy based on inputs and environment.

    Parameters
    ----------
    overwrite : bool, optional
        Force overwrite if True. Defaults to `TI_TOOLBOX_OVERWRITE`.
    prompt : bool, optional
        Allow interactive prompting if True. Defaults to
        `TI_TOOLBOX_PROMPT_OVERWRITE`.

    Returns
    -------
    OverwritePolicy
        Resolved overwrite and prompt settings.
    """
    if overwrite is None:
        overwrite_env = os.environ.get("TI_TOOLBOX_OVERWRITE", "false").lower()
        overwrite = overwrite_env in {"1", "true", "yes", "y"}
    if prompt is None:
        prompt_env = os.environ.get("TI_TOOLBOX_PROMPT_OVERWRITE", "true").lower()
        prompt = prompt_env in {"1", "true", "yes", "y"}
    return OverwritePolicy(overwrite=bool(overwrite), prompt=bool(prompt))


def should_overwrite_path(
    path: Path, *, policy: OverwritePolicy, logger, label: str
) -> bool:
    """Determine whether an existing path should be overwritten.

    Parameters
    ----------
    path : Path
        Target path to check.
    policy : OverwritePolicy
        Overwrite/prompt configuration.
    logger : logging.Logger
        Logger used for user-facing messages.
    label : str
        Human-readable label for the resource.

    Returns
    -------
    bool
        True if overwrite should proceed.
    """
    if not path.exists():
        return True
    if policy.overwrite:
        return True
    if not policy.prompt:
        logger.warning(f"{label} found existing output at {path}. Skipping.")
        return False
    if os.isatty(0):
        ans = (
            input(f"{label} output exists at {path}. Overwrite? [y/N]: ")
            .strip()
            .lower()
        )
        return ans in {"y", "yes"}
    logger.error(
        f"{label} output already exists at {path}. "
        "Set TI_TOOLBOX_OVERWRITE=true to overwrite in non-interactive mode."
    )
    return False
