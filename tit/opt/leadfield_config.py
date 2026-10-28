"""Configuration dataclass for leadfield generation.

Pure Python -- no SimNIBS dependency. Mirrors the constructor and
``generate()`` parameters of :class:`tit.opt.leadfield.LeadfieldGenerator`
so :mod:`tit.config_io` can generate a JSON Schema for it and
``POST /api/jobs`` (kind ``"leadfield"``) can validate a request body before
submitting the job. See ``LeadfieldConfig``'s Notes for the things it models
that the generator does not implement today.

See Also
--------
tit.opt.leadfield.LeadfieldGenerator : Consumes these values as separate
    constructor / method arguments (not this dataclass).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class LeadfieldConfig:
    """Configuration for one leadfield-generation run.

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    eeg_net : str
        EEG cap name without the ``.csv`` suffix (``LeadfieldGenerator``'s
        ``electrode_cap``).
    tissues : list of int
        Tissue tags to include (1 = WM, 2 = GM).
    interpolation : str or None
        SimNIBS ``TDCSLEADFIELD.interpolation`` mode. ``None`` means no
        interpolation.
    overwrite : bool
        Recompute even when a leadfield for this (*subject_id*, *eeg_net*)
        already exists.
    electrode_shape : str
        ``"ellipse"`` or ``"rect"``: the electrode SimNIBS places at every
        position of the cap.  Default ``"ellipse"``.
    electrode_dimensions : list of float
        ``[width, height]`` of that electrode in mm.  Default ``[8.0, 8.0]``.
    gel_thickness : float
        Saline-gel layer between skin and rubber, in mm.  Default ``1.0``.
    rubber_thickness : float
        Silicone-rubber layer on the gel, in mm.  Default ``2.0``.

    The four electrode fields are :class:`~tit.sim.config.SimulationConfig`'s
    names and defaults: a leadfield is the field of one electrode model at
    every cap position, so a different size is a different leadfield.
    :meth:`~tit.opt.leadfield.LeadfieldGenerator.generate` records them in a
    ``<sid>_leadfield_<net>.json`` sidecar beside the HDF5.

    Raises
    ------
    ValueError
        If *eeg_net* is empty, *tissues* is empty or contains a value other
        than 1 or 2, the shape is not ``"ellipse"``/``"rect"``, or a
        dimension or thickness is not a positive number.

    Notes
    -----
    Two fields this dataclass models that
    :meth:`~tit.opt.leadfield.LeadfieldGenerator.generate` does not
    implement today:

    - ``generate(tissues=...)`` immediately overwrites its own parameter
      with a hardcoded ``tissues = [1, 2]`` before building the SimNIBS
      ``TDCSLEADFIELD`` -- the argument (and, by extension, this dataclass's
      *tissues* field) has no effect today.
    - ``interpolation`` is hardcoded to ``None`` in ``generate()``; there is
      no parameter to set it.
    - There is no ``overwrite`` parameter on ``LeadfieldGenerator`` at all;
      callers today decide whether to skip generation by checking
      ``list_leadfields()`` themselves before calling ``generate()``.

    See Also
    --------
    tit.opt.leadfield.LeadfieldGenerator : The class whose parameters this
        dataclass mirrors.
    """

    subject_id: str
    eeg_net: str = "GSN-HydroCel-185"
    tissues: list[int] = field(default_factory=lambda: [1, 2])
    interpolation: str | None = None
    overwrite: bool = False
    electrode_shape: str = "ellipse"
    electrode_dimensions: list[float] = field(default_factory=lambda: [8.0, 8.0])
    gel_thickness: float = 1.0
    rubber_thickness: float = 2.0

    def __post_init__(self) -> None:
        if not (self.eeg_net or "").strip():
            raise ValueError("eeg_net is required")
        if not self.tissues:
            raise ValueError("tissues must be non-empty")
        if any(t not in (1, 2) for t in self.tissues):
            raise ValueError("tissues values must be 1 (WM) or 2 (GM)")
        if self.electrode_shape not in ("ellipse", "rect"):
            raise ValueError(
                f"electrode_shape must be 'ellipse' or 'rect' (was {self.electrode_shape!r})"
            )
        if (
            not isinstance(self.electrode_dimensions, (list, tuple))
            or len(self.electrode_dimensions) != 2
        ):
            raise ValueError("electrode_dimensions must be [width, height] in mm")
        self.electrode_dimensions = [
            _positive(d, "electrode_dimensions (mm)") for d in self.electrode_dimensions
        ]
        self.gel_thickness = _positive(self.gel_thickness, "gel_thickness (mm)")
        self.rubber_thickness = _positive(
            self.rubber_thickness, "rubber_thickness (mm)"
        )

    def electrode_record(self) -> dict:
        """The electrode fields, as the leadfield's sidecar records them."""
        return {
            "electrode_shape": self.electrode_shape,
            "electrode_dimensions": list(self.electrode_dimensions),
            "gel_thickness": self.gel_thickness,
            "rubber_thickness": self.rubber_thickness,
        }


def _positive(value: object, name: str) -> float:
    """*value* as a finite float > 0, else ``ValueError`` naming *name*."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number (was {value!r})")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be > 0 (was {value!r})")
    return float(value)
