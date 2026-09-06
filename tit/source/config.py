#!/usr/bin/env simnibs_python
"""Configuration dataclasses for EEG source-forward preparation.

Defines the two typed configs consumed by :mod:`tit.source`:

* :class:`ForwardConfig` -- parameters for rebuilding an MNE-compatible EEG
  forward solution (leadfield, source space, fsaverage morph) from an existing
  SimNIBS head model.
* :class:`FsavgMapConfig` -- parameters for projecting existing simulation field
  outputs (TI_max, TI_normal, hf_peak, hf_sar) onto an fsaverage template.

See Also
--------
tit.source.forward.prepare_forward : Consumes :class:`ForwardConfig`.
tit.source.fsaverage.project_fields_to_fsaverage : Consumes :class:`FsavgMapConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from tit.constants import FSAVG_FIELD_NAMES

#: Field quantities that :func:`tit.source.fsaverage.project_fields_to_fsaverage`
#: knows how to compute on the subject central surface before morphing.
#:
#: ``hf_peak`` = ``max(|E1+E2|, |E1-E2|)`` is the peak carrier field and ``hf_sar``
#: = ``|E1|^2 + |E2|^2`` the heating driver (Cassarà 2025); see :mod:`tit.fields`.
#:
#: Sourced from :data:`tit.constants.FSAVG_FIELD_NAMES` (the single source of
#: truth, shared with :mod:`tit.stats.config`), which is the field registry
#: minus ``FIELD_MTI_MAX`` ("mTI_max", the 4-pair/mTI mesh spelling): the
#: central-surface pipeline only ever emits ``TI_max``, regardless of whether
#: the simulation was 2-pair or 4-pair, so there is no separate mTI fsaverage
#: field to project. Reproduces the exact historical tuple
#: ``("TI_max", "TI_normal", "hf_peak", "hf_sar")``.
VALID_FSAVG_FIELDS: tuple[str, ...] = FSAVG_FIELD_NAMES

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
        ``"hf_peak"``, ``"hf_sar"``).
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


# ── Top-level runner config ──────────────────────────────────────────────


class SourceMode(StrEnum):
    """Which :mod:`tit.source` pipeline a :class:`SourceConfig` drives.

    Attributes
    ----------
    FORWARD : str
        Rebuild an EEG forward solution per subject (:class:`ForwardConfig`).
    FSAVG_MAP : str
        Project existing simulation fields onto fsaverage for
        (subject, simulation) pairs (:class:`FsavgMapConfig`).
    """

    FORWARD = "forward"
    FSAVG_MAP = "fsavg_map"


@dataclass(frozen=True)
class SourcePair:
    """One (subject, simulation) pair for the ``fsavg_map`` pipeline.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name.
    """

    subject_id: str
    simulation: str


@dataclass
class SourceConfig:
    """Configuration for one :mod:`tit.source` runner invocation.

    Wraps the two pipelines :mod:`tit.source.__main__` dispatches on its
    ``"mode"`` field. Only the fields relevant to *mode* are read by the
    runner; the other pipeline's fields keep their defaults and are
    ignored, mirroring ``tit.source.__main__._run_forward`` /
    ``_run_fsavg_map`` exactly.

    Attributes
    ----------
    mode : SourceMode
        ``"forward"`` or ``"fsavg_map"``.
    subject_ids : list of str
        Subjects to rebuild a forward solution for. Required
        (non-empty) when *mode* is ``"forward"``.
    pairs : list of SourcePair
        (subject, simulation) pairs to project onto fsaverage. Required
        (non-empty) when *mode* is ``"fsavg_map"``.
    forward : ForwardConfig
        Forward-solution parameters (``"forward"`` mode only).
    fsavg_map : FsavgMapConfig
        fsaverage-projection parameters (``"fsavg_map"`` mode only).

    Raises
    ------
    ValueError
        If *mode* is ``"forward"`` with an empty *subject_ids*, or
        ``"fsavg_map"`` with an empty *pairs*.

    See Also
    --------
    tit.source.__main__ : The entry point whose dispatch this mirrors.
    ForwardConfig : Consumed by the ``"forward"`` pipeline.
    FsavgMapConfig : Consumed by the ``"fsavg_map"`` pipeline.
    """

    mode: SourceMode = SourceMode.FORWARD
    subject_ids: list[str] = field(default_factory=list)
    pairs: list[SourcePair] = field(default_factory=list)
    forward: ForwardConfig = field(default_factory=ForwardConfig)
    fsavg_map: FsavgMapConfig = field(default_factory=FsavgMapConfig)

    def __post_init__(self) -> None:
        self.mode = SourceMode(self.mode)
        if self.mode is SourceMode.FORWARD and not self.subject_ids:
            raise ValueError("subject_ids must be non-empty when mode='forward'")
        if self.mode is SourceMode.FSAVG_MAP and not self.pairs:
            raise ValueError("pairs must be non-empty when mode='fsavg_map'")
