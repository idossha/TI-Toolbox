"""Figures TI-Toolbox draws for itself, without being asked.

Today that is one thing: the **ROI plate** (:mod:`tit.figures.roi_plate`) — the
picture every optimizer and every analyzer run leaves behind so a person can see
the voxels the job is about before trusting a number about them.
"""

from tit.figures.roi_plate import plan_framing, write_roi_plate

__all__ = ["plan_framing", "write_roi_plate"]
