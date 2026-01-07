"""
Public API for Blender-related business logic.

The goal of this module is to provide a stable, centralized interface that both
CLI and GUI entrypoints can call so they produce identical outputs given the
same inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging

from tit.blender.montage_publication import (
    MontagePublicationResult,
    build_montage_publication_blend,
    configure_montage_loggers,
)


@dataclass(frozen=True)
class MontagePublicationRequest:
    subject_id: str
    simulation_name: str
    output_dir: Optional[str] = None
    show_full_net: bool = True
    electrode_diameter_mm: float = 10.0
    electrode_height_mm: float = 6.0
    export_glb: bool = False


def create_montage_publication_blend(
    req: MontagePublicationRequest,
    *,
    logger: Optional[logging.Logger] = None,
) -> MontagePublicationResult:
    """
    Create a publication-ready montage Blender scene (.blend) for a subject+simulation.

    This is the shared entrypoint for CLI and GUI callers.
    """
    subject_id = (req.subject_id or "").strip()
    simulation_name = (req.simulation_name or "").strip()
    if not subject_id:
        raise ValueError("subject_id is required")
    if not simulation_name:
        raise ValueError("simulation_name is required")
    if req.electrode_diameter_mm <= 0:
        raise ValueError("electrode_diameter_mm must be > 0")
    if req.electrode_height_mm <= 0:
        raise ValueError("electrode_height_mm must be > 0")

    if logger is not None:
        configure_montage_loggers(logger)

    return build_montage_publication_blend(
        subject_id=subject_id,
        simulation_name=simulation_name,
        output_dir=req.output_dir,
        show_full_net=bool(req.show_full_net),
        electrode_diameter_mm=float(req.electrode_diameter_mm),
        electrode_height_mm=float(req.electrode_height_mm),
        export_glb=bool(req.export_glb),
    )


