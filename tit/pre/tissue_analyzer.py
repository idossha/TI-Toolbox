#!/usr/bin/env simnibs_python
"""
Wrapper for tissue analyzer pipeline.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError


DEFAULT_TISSUES = ("bone", "csf", "skin")


def run_tissue_analysis(
    project_dir: str,
    subject_id: str,
    *,
    tissues: Iterable[str] = DEFAULT_TISSUES,
    logger,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run tissue analysis for a subject.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the `sub-` prefix.
    tissues : iterable of str, optional
        Tissue types to analyze.
    logger : logging.Logger
        Logger used for progress and command output.
    runner : CommandRunner, optional
        Subprocess runner used to stream output.
    """
    pm = get_path_manager()
    pm.project_dir = project_dir
    label_path = Path(pm.path("tissue_labeling", subject_id=subject_id))
    if not label_path.exists():
        raise PreprocessError(f"Labeling.nii.gz not found at {label_path}")

    output_root = Path(pm.ensure_dir("tissue_analysis_output", subject_id=subject_id))
    script_path = Path(__file__).resolve().parents[1] / "tools" / "tissue_analyzer.py"
    if not script_path.exists():
        raise PreprocessError(f"tissue_analyzer.py not found at {script_path}")

    for tissue in tissues:
        output_dir = output_root / f"{tissue}_analysis"
        cmd = [
            sys.executable,
            str(script_path),
            str(label_path),
            "-t",
            tissue,
            "-o",
            str(output_dir),
        ]
        env = os.environ.copy()
        if runner:
            exit_code = runner.run(cmd, logger=logger, env=env)
        else:
            exit_code = subprocess.call(cmd, env=env)
        if exit_code != 0:
            raise PreprocessError(f"Tissue analysis failed for {subject_id} ({tissue}).")
