"""Configuration dataclass for group NIfTI averaging (owner: B4).

Mirrors the fields the "NIfTI Group Averaging" panel collects, so
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

from tit.paths import validate_name


class NiftiAverageSpace(StrEnum):
    """Which per-subject NIfTI space the group average is computed in."""

    SUBJECT = "subject"
    MNI = "mni"


#: Default filename pattern per :class:`NiftiAverageSpace`: the grey-matter
#: envelope ``tit.tools.mesh2nii`` writes under a simulation's ``TI/niftis/``
#: (``<mesh>_subject_<field>`` / ``<mesh>_MNI_MNI_<field>``). The subject entry
#: read ``grey_{simulation_name}_TI_max.nii.gz``, a file no simulation writes.
#: An mTI simulation is read from ``mTI/niftis/`` with the mTI spelling
#: (:func:`tit.analyzer.field_selector.simulation_nifti_path`).
_DEFAULT_PATTERNS: dict[NiftiAverageSpace, str] = {
    NiftiAverageSpace.MNI: "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    NiftiAverageSpace.SUBJECT: "grey_{simulation_name}_TI_subject_TI_max.nii.gz",
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
        Labels may contain hyphens (``"post-op-pre-op"``): an entry is split
        at the one hyphen that leaves a group label on both sides.

    Raises
    ------
    ValueError
        If *output_name* is blank or not a valid folder name
        (:func:`tit.paths.validate_name`), fewer than 2 *subjects* are given,
        a group label is not a valid file-name part (it names
        ``average_<group>.nii.gz``), or a *diff_pairs* entry does not name
        two different groups exactly one way or repeats an earlier pair.

    Notes
    -----
    Group labels are stripped of edge whitespace, so ``"Group1 "`` and
    ``"Group1"`` are one group.

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
        # The run's folder under nifti_average/, held to stats' analysis_name rule.
        validate_name(self.output_name, "output_name")
        if len(self.subjects) < 2:
            raise ValueError("at least 2 subjects are required")
        for index, subject in enumerate(self.subjects):
            label = subject.group.strip() if isinstance(subject.group, str) else None
            validate_name(label, f"group label of subjects[{index}]")
            subject.group = label
        self.difference_pairs()  # an unknown or ambiguous pair is refused here
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _DEFAULT_PATTERNS[NiftiAverageSpace(self.space)]

    def difference_pairs(self) -> list[tuple[str, str]]:
        """The ``(A, B)`` group pairs whose ``A - B`` difference maps the run writes.

        Returns
        -------
        list of tuple of str
            Every pair of the groups in alphabetical order when *diff_pairs* is
            empty, else one pair per *diff_pairs* entry, in the order given.

        Raises
        ------
        ValueError
            If an entry does not split into two different known group labels,
            splits into them at more than one hyphen, or repeats an earlier pair.
        """
        groups = sorted({s.group for s in self.subjects})
        if not self.diff_pairs:
            return [(a, b) for i, a in enumerate(groups) for b in groups[i + 1 :]]
        pairs: list[tuple[str, str]] = []
        for entry in self.diff_pairs:
            text = entry if isinstance(entry, str) else ""
            splits = {
                (text[:i].strip(), text[i + 1 :].strip())
                for i, char in enumerate(text)
                if char == "-"
            }
            named = [p for p in splits if p[0] in groups and p[1] in groups]
            # A group minus itself is zero everywhere: never a map anyone asked for.
            matches = [p for p in named if p[0] != p[1]]
            if len(matches) != 1:
                if matches:
                    problem = "names two groups in more than one way"
                elif named:
                    problem = "names the same group on both sides"
                else:
                    problem = "does not name two of the groups"
                raise ValueError(
                    f"diff_pairs entry {entry!r} {problem} {groups}; write it as "
                    "GroupA-GroupB"
                )
            if matches[0] in pairs:
                raise ValueError(
                    f"diff_pairs entry {entry!r} repeats an earlier pair "
                    f"({matches[0][0]}-{matches[0][1]})"
                )
            pairs.append(matches[0])
        return pairs
