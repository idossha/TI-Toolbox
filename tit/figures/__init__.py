"""Artefacts TI-Toolbox leaves behind without being asked.

Today that is one thing: the **ROI scene** (:mod:`tit.figures.roi_plate`) — one
small ``roi.tetravox.json`` per target, written by every optimizer run, so a
person can open the voxels the search is about before trusting a number about
them.  An analysis instead writes one ``scene.tetravox.json`` of its field
masked to the ROI (:mod:`tit.analyzer.scene`), built on the same helpers.  A
scene references files that already exist and draws nothing itself; the
optional PNG is made on the host by Tetravox (``desktop/src/main/roiPlates.ts``).
"""

from tit.figures.roi_plate import plan_framing, plan_surface, write_roi_scene

__all__ = ["plan_framing", "plan_surface", "write_roi_scene"]
