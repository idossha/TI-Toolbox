"""Artefacts TI-Toolbox leaves behind without being asked.

Today that is one thing: the **ROI scene** (:mod:`tit.figures.roi_plate`) — one
small ``roi.tetravox.json`` per target, written by every optimizer and every
analyzer run, so a person can open the voxels the job is about before trusting a
number about them.  It references files that already exist and draws nothing
itself; the optional PNG is made on the host by Tetravox
(``desktop/src/main/roiPlates.ts``).
"""

from tit.figures.roi_plate import plan_framing, plan_surface, write_roi_scene

__all__ = ["plan_framing", "plan_surface", "write_roi_scene"]
