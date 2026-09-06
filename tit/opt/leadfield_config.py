"""Configuration dataclass for leadfield generation.

Pure Python -- no SimNIBS dependency. Mirrors the constructor and
``generate()`` parameters of :class:`tit.opt.leadfield.LeadfieldGenerator`
so :mod:`tit.config_io` can generate a JSON Schema for it and a future
``POST /api/jobs`` (kind ``"leadfield"``) can validate a request body before
submitting the job. This module does not change ``LeadfieldGenerator`` --
see ``LeadfieldConfig``'s Notes for the two things it models that the
generator does not implement today.

See Also
--------
tit.opt.leadfield.LeadfieldGenerator : Consumes these values as separate
    constructor / method arguments (not this dataclass).
"""

from __future__ import annotations

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

    Raises
    ------
    ValueError
        If *eeg_net* is empty, or *tissues* is empty or contains a value
        other than 1 or 2.

    Notes
    -----
    Two fields this dataclass models that
    :meth:`~tit.opt.leadfield.LeadfieldGenerator.generate` does not
    implement today, reported rather than silently patched into
    ``tit/opt/leadfield.py`` (not owned by this track):

    - ``generate(tissues=...)`` immediately overwrites its own parameter
      with a hardcoded ``tissues = [1, 2]`` before building the SimNIBS
      ``TDCSLEADFIELD`` -- the argument (and, by extension, this dataclass's
      *tissues* field) has no effect today. This looks like a genuine bug
      in ``tit/opt/leadfield.py`` rather than intentional behavior.
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

    def __post_init__(self) -> None:
        if not (self.eeg_net or "").strip():
            raise ValueError("eeg_net is required")
        if not self.tissues:
            raise ValueError("tissues must be non-empty")
        if any(t not in (1, 2) for t in self.tissues):
            raise ValueError("tissues values must be 1 (WM) or 2 (GM)")
