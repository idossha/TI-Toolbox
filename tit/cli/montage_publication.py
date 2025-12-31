#!/usr/bin/env simnibs_python
"""
TI-Toolbox Montage Publication CLI

Creates a publication-ready Blender scene (.blend) for a given subject + simulation:
- Loads `Simulations/<simulation>/documentation/config.json`
- Exports `scalp.stl` and `gm.stl`
- Places electrodes from EEG net, highlighting montage pairs (optional)
- Saves `<subject>_<simulation>_montage_publication.blend`

Usage:
  simnibs_python tit/cli/montage_publication.py --subject 001 --simulation MySim
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from tit.core import get_path_manager
from tit.blender_exporter.montage_publication import build_montage_publication_blend


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create montage publication .blend")
    parser.add_argument("-s", "--subject", required=True, help="Subject ID (e.g., 001)")
    parser.add_argument("-sim", "--simulation", required=True, help="Simulation name")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <sim_dir>/documentation/montage_publication)",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Optional explicit TI-Toolbox project directory (overrides env auto-detect)",
    )
    parser.add_argument(
        "--montage-only",
        action="store_true",
        help="Only show/place electrodes that are part of the montage pairs in config.json",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    log = logging.getLogger("motage_publication")

    # Optionally set explicit project directory for PathManager auto-resolution
    if args.project_dir:
        pm = get_path_manager()
        pm.project_dir = os.path.abspath(args.project_dir)
        log.info(f"Using project_dir={pm.project_dir}")

    result = build_montage_publication_blend(
        subject_id=args.subject,
        simulation_name=args.simulation,
        output_dir=args.output_dir,
        show_full_net=(not args.montage_only),
    )

    log.info("Done.")
    log.info(f"Scalp STL: {result.scalp_stl}")
    log.info(f"GM STL:    {result.gm_stl}")
    log.info(f"Electrodes blend: {result.electrodes_blend}")
    log.info(f"Final blend:      {result.final_blend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


