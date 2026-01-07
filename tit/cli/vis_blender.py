#!/usr/bin/env simnibs_python
"""
TI-Toolbox Montage Publication CLI

Creates a publication-ready Blender scene (.blend) for a given subject + simulation:
- Loads `Simulations/<simulation>/documentation/config.json`
- Exports `scalp.stl` and `gm.stl`
- Places electrodes from EEG net, highlighting montage pairs (optional)
- Saves `<subject>_<simulation>_montage_publication.blend`

Usage:
  # Interactive mode
  simnibs_python tit/cli/vis_blender.py

  # Direct mode
  simnibs_python tit/cli/vis_blender.py --subject 001 --simulation MySim
"""

#!/usr/bin/env simnibs_python
from __future__ import annotations

# Ensure tit package is importable when run as a script
# This must happen before any tit imports
import os
import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
ti_toolbox_root = os.path.dirname(os.path.dirname(script_dir))  # Go up from tit/cli/ to /ti-toolbox or /TI-toolbox
if ti_toolbox_root not in sys.path:
    sys.path.insert(0, ti_toolbox_root)

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from tit.cli.base import ArgumentDefinition, InteractivePrompt, BaseCLI
from tit.core import get_path_manager
from tit.core import constants as const
from tit import logger as logging_util


logger = logging.getLogger("tit.cli.vis_blender")


class VisBlenderCLI(BaseCLI):
    """CLI for creating Blender visualization scenes."""

    def __init__(self):
        super().__init__(
            description="Create publication-ready Blender scenes for TI simulations"
        )

        # Add argument definitions
        self.add_argument(ArgumentDefinition(name="subject", type=str, help="Subject ID (e.g., 001)", required=True, flags=["--subject", "--sub"]))
        self.add_argument(ArgumentDefinition(name="simulation", type=str, help="Simulation name", required=True, flags=["--simulation", "--sim"]))
        self.add_argument(ArgumentDefinition(name="output_dir", type=str, help="Output directory (default: <project>/derivatives/ti-toolbox/sub-<id>/<sim>/)", required=False))
        self.add_argument(ArgumentDefinition(name="montage_only", type=bool, help="Only show/place electrodes that are part of the montage pairs in config.json", default=False))
        self.add_argument(ArgumentDefinition(name="electrode_diameter_mm", type=float, help="Electrode diameter in mm (default: 10.0)", default=10.0))
        self.add_argument(ArgumentDefinition(name="electrode_height_mm", type=float, help="Electrode height in mm (default: 6.0)", default=6.0))
        self.add_argument(ArgumentDefinition(name="export_glb", type=bool, help="Export GLB file for web viewing", default=False))
        self.add_argument(ArgumentDefinition(name="verbose", type=bool, help="Verbose logging", default=False))


    def run_interactive(self) -> int:
        pm = get_path_manager()

        from tit.cli.base import BaseCLI as _B
        from tit.cli import utils as _u

        _u.echo_header("Vis Blender (interactive)")
        subject_id = _B.select_one(
            prompt_text="Select subject",
            options=pm.list_subjects(),
            help_text="Choose from available subjects in your project",
        )
        simulation_name = _B.select_one(
            prompt_text="Select simulation",
            options=pm.list_simulations(subject_id),
            help_text="Choose from available simulations for this subject",
        )

        montage_only = _u.ask_bool("Montage-only electrodes?", default=False)

        if not _u.review_and_confirm(
            "Review (vis blender)",
            items=[
                ("Subject", subject_id),
                ("Simulation", simulation_name),
                ("Montage-only", "yes" if montage_only else "no"),
            ],
            default_yes=True,
        ):
            _u.echo_warning("Cancelled.")
            return 0

        return self.execute(
            dict(
                subject=subject_id,
                simulation=simulation_name,
                montage_only=montage_only,
            )
        )

    def execute(self, args: Dict[str, Any]) -> int:
        """Execute the Blender visualization creation."""
        pm = get_path_manager()

        # Set up logging
        log_file = self._setup_logging(args)
        log = _setup_logging_with_file(args.get("verbose", False), log_file)

        if get_path_manager().project_dir:
            log.info(f"Using project_dir={get_path_manager().project_dir}")
        if log_file:
            log.info(f"Logging to: {log_file}")

        try:
            # Lazy import: Blender/SimNIBS stack is heavy; keep `--help` import-safe.
            from tit.blender.api import (
                MontagePublicationRequest,
                create_montage_publication_blend,
            )

            req = MontagePublicationRequest(
                subject_id=args["subject"],
                simulation_name=args["simulation"],
                output_dir=args.get("output_dir"),
                show_full_net=(not args.get("montage_only", False)),
                electrode_diameter_mm=args.get("electrode_diameter_mm", 10.0),
                electrode_height_mm=args.get("electrode_height_mm", 6.0),
                export_glb=args.get("export_glb", False),
            )
            result = create_montage_publication_blend(req, logger=log)

            log.info("Done.")
            log.info(f"Scalp STL: {result.scalp_stl}")
            log.info(f"GM STL:    {result.gm_stl}")
            log.info(f"Electrodes blend: {result.electrodes_blend}")
            log.info(f"Final blend:      {result.final_blend}")
            return 0

        except Exception as e:
            log.error(f"Failed to create Blender scene: {e}")
            return 1

    def _setup_logging(self, args: Dict[str, Any]) -> Optional[str]:
        """Set up logging file path."""
        pm = get_path_manager()

        logs_dir = os.path.join(
            pm.project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            f"{const.PREFIX_SUBJECT}{args['subject']}",
        )
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(logs_dir, f"vis_blender_{args['simulation']}_{ts}.log")


def _setup_logging_with_file(verbose: bool, log_file: Optional[str]) -> logging.Logger:
    """Configure console + optional file logging with consistent formatting."""
    root_name = "tit.cli.vis_blender"
    log = logging_util.get_logger(root_name, log_file=log_file, overwrite=True, console=True)

    if verbose:
        for h in list(log.handlers):
            try:
                h.setLevel(logging.DEBUG)
            except Exception:
                # Logger handler configuration may fail
                pass

    # Use shared logger configuration
    from tit.blender.montage_publication import configure_montage_loggers
    configure_montage_loggers(log)
    return log


if __name__ == "__main__":
    cli = VisBlenderCLI()
    raise SystemExit(cli.run())


