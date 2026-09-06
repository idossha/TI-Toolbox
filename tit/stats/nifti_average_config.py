"""Configuration dataclass for group NIfTI averaging (owner: B4).

Mirrors the fields the "NIfTI Group Averaging" GUI extension
(``tit/gui/extensions/nifti_group_average.py``) collects, so
:mod:`tit.config_io` can generate a JSON Schema for it and a future
``POST /api/jobs`` (kind ``"nifti_average"``) can validate a request body
before submitting the job. Pure Python -- no numpy/nibabel dependency.

Public API
----------
NiftiAverageSpace
    Which per-subject NIfTI space the group average is computed in.
NiftiAverageSubject
    One subject/simulation/group assignment row.
NiftiAverageConfig
    Configuration for one group NIfTI averaging run.

See Also
--------
tit.stats.nifti_average : Runner entry point that consumes this config
    (``simnibs_python -m tit.stats.nifti_average config.json``).
tit.stats.nifti.load_grouped_subjects_ti_toolbox : Loads the per-group data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class NiftiAverageSpace(StrEnum):
    """Which per-subject NIfTI space the group average is computed in."""

    SUBJECT = "subject"
    MNI = "mni"


#: Default filename pattern per :class:`NiftiAverageSpace`, matching what
#: ``tit.sim``/``tit.analyzer`` actually write under a simulation's
#: ``TI/niftis/`` directory (see
#: ``tit.stats.nifti.load_subject_nifti_ti_toolbox``'s own MNI default).
_DEFAULT_PATTERNS: dict[NiftiAverageSpace, str] = {
    NiftiAverageSpace.MNI: "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    NiftiAverageSpace.SUBJECT: "grey_{simulation_name}_TI_max.nii.gz",
}


@dataclass
class NiftiAverageSubject:
    """One subject/simulation/group assignment row.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without the ``sub-`` prefix).
    simulation_name : str
        Simulation folder name whose NIfTI is averaged.
    group : str, optional
        Group label this subject belongs to. Default is ``"Group1"``.
    """

    subject_id: str
    simulation_name: str
    group: str = "Group1"


@dataclass
class NiftiAverageConfig:
    """Configuration for one group NIfTI averaging run.

    Attributes
    ----------
    output_name : str
        Name of the output subdirectory under
        ``derivatives/ti-toolbox/nifti_average/`` (the GUI's "Analysis Name").
    subjects : list of NiftiAverageSubject
        Subject/simulation/group rows -- at least 2, spanning at least 1 group.
    space : NiftiAverageSpace, optional
        Which per-subject NIfTI space to average in. Selects the default
        *nifti_file_pattern* when one is not given explicitly. Default is
        :attr:`NiftiAverageSpace.MNI`.
    nifti_file_pattern : str or None, optional
        Filename pattern with ``{subject_id}``/``{simulation_name}``
        placeholders. Defaults to :data:`_DEFAULT_PATTERNS`\\ [*space*] when
        left ``None``.
    diff_pairs : list of str, optional
        ``"GroupA-GroupB"`` pairs to difference. Empty (the default) means
        every pairwise combination of the groups present in *subjects*.

    Raises
    ------
    ValueError
        If *output_name* is blank, or fewer than 2 *subjects* are given.

    See Also
    --------
    tit.stats.nifti_average.main : Consumes this config.
    """

    output_name: str
    subjects: list[NiftiAverageSubject]
    space: NiftiAverageSpace = NiftiAverageSpace.MNI
    nifti_file_pattern: str | None = None
    diff_pairs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (self.output_name or "").strip():
            raise ValueError("output_name is required")
        if len(self.subjects) < 2:
            raise ValueError("at least 2 subjects are required")
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _DEFAULT_PATTERNS[NiftiAverageSpace(self.space)]
