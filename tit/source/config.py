#!/usr/bin/env simnibs_python
"""Configuration dataclasses for EEG source-forward preparation.

Defines the two typed configs consumed by :mod:`tit.source`:

* :class:`ForwardConfig` -- parameters for rebuilding an MNE-compatible EEG
  forward solution (leadfield, source space, fsaverage morph) from an existing
  SimNIBS head model.
* :class:`FsavgMapConfig` -- parameters for projecting existing simulation field
  outputs (TI_max, TI_normal, |E|) onto an fsaverage template.

See Also
--------
tit.source.forward.prepare_forward : Consumes :class:`ForwardConfig`.
tit.source.fsaverage.project_fields_to_fsaverage : Consumes :class:`FsavgMapConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Field quantities that :func:`tit.source.fsaverage.project_fields_to_fsaverage`
#: knows how to compute on the subject central surface before morphing.
#:
#: ``hf_max`` is the peak instantaneous carrier exposure ``|E1| + |E2|`` (sum of
#: carrier magnitudes) -- distinct from ``magnitude`` = ``|E1 + E2|`` (the
#: coherent vector sum); both derive from the same two carrier overlays.
VALID_FSAVG_FIELDS: tuple[str, ...] = ("TI_max", "TI_normal", "magnitude", "hf_max")

#: fsaverage subdivision factors accepted by SimNIBS ``prepare_eeg_forward`` and
#: ``cross_subject_map`` (5 -> 10242, 6 -> 40962, 7 -> 163842 nodes per hemi).
VALID_FSAVG_SPACINGS: tuple[int, ...] = (5, 6, 7)


@dataclass(frozen=True)
class ForwardConfig:
    """Parameters for rebuilding a SimNIBS/MNE EEG forward solution.

    Attributes
    ----------
    eeg_net : str
        EEG cap name **without** the ``.csv`` suffix, as found in the subject's
        ``m2m_<id>/eeg_positions/`` directory (e.g. ``"GSN-HydroCel-185"``).
    fsaverage_spacing : int
        fsaverage subdivision factor (5, 6, or 7) for the morph target.
    cpus : int
        SimNIBS FEM workers used while computing the leadfield.
    overwrite : bool
        Recompute even when valid outputs already exist.  The expensive FEM
        leadfield is still reused when present unless this is ``True``.
    """

    eeg_net: str = "GSN-HydroCel-185"
    fsaverage_spacing: int = 5
    cpus: int = 1
    overwrite: bool = False

    def __post_init__(self) -> None:
        if self.fsaverage_spacing not in VALID_FSAVG_SPACINGS:
            raise ValueError(
                f"fsaverage_spacing must be one of {VALID_FSAVG_SPACINGS}, "
                f"got {self.fsaverage_spacing}"
            )


@dataclass(frozen=True)
class FsavgMapConfig:
    """Parameters for projecting simulation field outputs onto fsaverage.

    Attributes
    ----------
    fields : tuple of str
        Which field quantities to project.  Any of
        :data:`VALID_FSAVG_FIELDS` (``"TI_max"``, ``"TI_normal"``,
        ``"magnitude"``, ``"hf_max"``).
    fsaverage_spacing : int
        fsaverage subdivision factor (5, 6, or 7) to morph onto.
    workers : int
        Number of subjects projected in parallel (1 = serial).
    overwrite : bool
        Re-project even when a cached ``.npz`` already exists.
    """

    fields: tuple[str, ...] = field(default_factory=lambda: VALID_FSAVG_FIELDS)
    fsaverage_spacing: int = 5
    workers: int = 1
    overwrite: bool = False

    def __post_init__(self) -> None:
        if self.fsaverage_spacing not in VALID_FSAVG_SPACINGS:
            raise ValueError(
                f"fsaverage_spacing must be one of {VALID_FSAVG_SPACINGS}, "
                f"got {self.fsaverage_spacing}"
            )
        unknown = set(self.fields) - set(VALID_FSAVG_FIELDS)
        if unknown:
            raise ValueError(
                f"Unknown field(s) {sorted(unknown)}; valid: {VALID_FSAVG_FIELDS}"
            )
        if not self.fields:
            raise ValueError("At least one field must be selected.")
