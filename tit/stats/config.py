"""Configuration and result dataclasses for cluster-based permutation testing.

Pure Python -- no numpy, nibabel, pandas or other heavy dependencies; the participant
CSV loaders read with the standard :mod:`csv` module.
Mirrors the ``tit.opt.config`` / ``tit.sim.config`` pattern.

Public API
----------
GroupComparisonConfig
    Configuration for two-group cluster-based permutation testing.
GroupComparisonResult
    Result container for group comparison analysis.
CorrelationConfig
    Configuration for correlation-based cluster permutation testing.
CorrelationResult
    Result container for correlation analysis.

See Also
--------
tit.stats.permutation : Orchestration functions that consume these configs.
"""

import csv
import math
import numbers
from dataclasses import dataclass, field
from enum import StrEnum

from tit.constants import FSAVG_FIELD_NAMES, FSAVG_NOT_PROJECTED

#: Cell texts a participants CSV uses for "no value" (pandas' common ``na_values``).
_MISSING_CELLS = frozenset({"", "nan", "na", "n/a", "null", "none"})


def _read_participant_rows(
    csv_path: str, required: set[str]
) -> list[tuple[int, dict[str, str | None]]]:
    """Read a participants CSV as ``(line number, {column: text or None})`` pairs.

    Every cell stays text, so a zero-padded id such as ``001`` keeps its zeros. Header names
    and cells are stripped, a UTF-8 byte-order mark (Excel's "CSV UTF-8") is dropped, and a
    blank or NaN cell becomes ``None``.

    Args:
        csv_path: Path to the CSV file.
        required: Column names the file must have.

    Returns:
        One ``(line, row)`` pair per data row; ``line`` counts the header as line 1.

    Raises:
        ValueError: If a required column is missing.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = {name.strip() for name in reader.fieldnames or []}
        missing = required - columns
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        rows = []
        for row in reader:
            cells: dict[str, str | None] = {}
            for name, value in row.items():
                if name is None:  # cells beyond the header
                    continue
                text = (value or "").strip()
                cells[name.strip()] = None if text.lower() in _MISSING_CELLS else text
            rows.append((reader.line_num, cells))
    return rows


def _participant_id(text: str) -> str:
    """``sub-001`` -> ``001``; a spreadsheet's ``3.0`` -> ``3``."""
    sid = text.replace("sub-", "")
    return sid[:-2] if sid.endswith(".0") else sid


# ── Shared enums (private; aliased into both config classes) ──────────────


class _ClusterStat(StrEnum):
    """Cluster-level statistic: summed t-values (``mass``) or voxel count (``size``)."""

    MASS = "mass"
    SIZE = "size"


class _TissueType(StrEnum):
    """Tissue compartment of the MNI-space NIfTIs: ``grey``, ``white`` or ``all``."""

    GREY = "grey"
    WHITE = "white"
    ALL = "all"


class _AnalysisSpace(StrEnum):
    """Where the group statistics run: MNI volume or fsaverage surface."""

    MNI = "mni"
    FSAVERAGE = "fsaverage"


#: Surface field quantities the fsaverage stats path can load. Sourced from
#: :data:`tit.constants.FSAVG_FIELD_NAMES` (not from
#: :data:`tit.source.config.VALID_FSAVG_FIELDS`, which it mirrors) because
#: importing ``tit.source.config`` would pull in ``mne``.
_VALID_FSAVG_FIELDS = FSAVG_FIELD_NAMES
_VALID_FSAVG_SPACINGS = (5, 6, 7)


def _is_real(value: object) -> bool:
    """``True`` for a finite real number, numpy scalars included (a bool is not one here)."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _count(n: int, noun: str) -> str:
    """``1 responder``, ``2 responders``."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _min_permutations(alpha: float) -> int:
    """Fewest permutations with which a cluster can be significant at *alpha*.

    A permutation p-value is ``(b + 1) / (m + 1)`` (Phipson & Smyth 2010), so with *m*
    permutations no p-value is below ``1 / (m + 1)``, and the engine calls a cluster
    significant only when ``p < alpha``. The answer is the smallest *m* with
    ``1 / (m + 1) < alpha``: ``floor(1 / alpha)`` (20 at alpha 0.05, 100 at 0.01), found with
    the engine's own float division so a rounding edge cannot disagree with it.

    Args:
        alpha: Family-wise error rate, strictly between 0 and 1.

    Returns:
        The minimum permutation count (at least 1).
    """
    m = max(1, math.floor(1 / alpha))
    while 1 / (m + 1) >= alpha:
        m += 1
    while m > 1 and 1 / m < alpha:
        m -= 1
    return m


def _validate_test_parameters(n_permutations, alpha, cluster_threshold) -> int:
    """Shared numeric checks for both config classes; returns *n_permutations* as an ``int``.

    *alpha* and *cluster_threshold* are probabilities, so they lie strictly between 0 and
    1. *n_permutations* is a whole number (a numpy integer or a whole-valued float such as
    ``1000.0`` counts) of at least :func:`_min_permutations` -- with fewer, no p-value can
    fall below *alpha*.
    """
    for name, value in (("alpha", alpha), ("cluster_threshold", cluster_threshold)):
        if not (_is_real(value) and 0 < value < 1):
            raise ValueError(
                f"{name} must be a number strictly between 0 and 1, got {value!r}"
            )
    whole = isinstance(n_permutations, numbers.Integral) or (
        _is_real(n_permutations) and float(n_permutations).is_integer()
    )
    if isinstance(n_permutations, bool) or not whole:
        raise ValueError(
            f"n_permutations must be a whole number, got {n_permutations!r}"
        )
    n_permutations = int(n_permutations)
    minimum = _min_permutations(alpha)
    if n_permutations < minimum:
        raise ValueError(
            f"n_permutations must be at least {minimum} at alpha {alpha}, got "
            f"{n_permutations}: n permutations give no p-value below 1/(n + 1), and a "
            "cluster is significant only when its p-value is below alpha"
        )
    return n_permutations


def _validate_surface_options(space, field, spacing) -> None:
    """Shared fsaverage-option validation for both config classes."""
    if space != _AnalysisSpace.FSAVERAGE:
        return
    if field not in _VALID_FSAVG_FIELDS:
        raise ValueError(
            f"fsaverage_field must be one of {_VALID_FSAVG_FIELDS}, got {field!r}. "
            + FSAVG_NOT_PROJECTED
        )
    if spacing not in _VALID_FSAVG_SPACINGS:
        raise ValueError(
            f"fsaverage_spacing must be one of {_VALID_FSAVG_SPACINGS}, got {spacing}"
        )


# ── Private helper ────────────────────────────────────────────────────────


def _nifti_pattern_for_tissue(tissue: _TissueType) -> str:
    if tissue == _TissueType.GREY:
        return "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    elif tissue == _TissueType.WHITE:
        return "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    else:
        return "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


# ── Configs ───────────────────────────────────────────────────────────────


@dataclass
class GroupComparisonConfig:
    """Configuration for cluster-based permutation testing between two groups.

    Compares voxelwise field intensities between responders and non-responders
    using a t-test with cluster-based permutation correction for multiple
    comparisons.

    Attributes
    ----------
    analysis_name : str
        Human-readable name for this analysis run.
    subjects : list of Subject
        Subject entries, each labelled as responder (1) or non-responder (0).
    test_type : TestType or str
        ``"unpaired"`` (default) or ``"paired"`` t-test.  Strings are
        coerced to :class:`TestType`.
    alternative : Alternative or str
        Sidedness: ``"two-sided"`` (default), ``"greater"`` or ``"less"``.
    cluster_threshold : float
        Uncorrected p-value threshold for forming clusters.  Default
        ``0.05``.
    cluster_stat : ClusterStat or str
        Cluster-level statistic used for permutation testing,
        ``"mass"`` (default) or ``"size"``.
    n_permutations : int
        Number of permutations for the null distribution.  Default
        ``1000``; the smallest reportable p-value is ``1 / (n + 1)``.
    alpha : float
        Family-wise error rate for significance.  Default ``0.05``.
    n_jobs : int
        Number of parallel workers (``-1``, the default, for the global
        CPU limit -- :func:`tit.cpu.cpu_limit`; larger values are clamped to it).
    tissue_type : TissueType or str
        Which tissue compartment to analyze: ``"grey"`` (default),
        ``"white"`` or ``"all"``.  Ignored when *space* is
        ``"fsaverage"``.
    nifti_file_pattern : str or None
        Filename pattern for subject NIfTI files, with a
        ``{simulation_name}`` placeholder.  If ``None`` (default), derived
        from *tissue_type*, e.g.
        ``"grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"``.
    space : AnalysisSpace or str
        Where the statistics run: ``"mni"`` (default, voxelwise on the
        MNI-space NIfTIs) or ``"fsaverage"`` (vertexwise on the per-subject
        fsaverage projections written by the simulator).
    fsaverage_field : str
        Surface field for ``space="fsaverage"``; one of
        :data:`tit.constants.FSAVG_FIELD_NAMES` (``"TI_max"``,
        ``"TI_normal"``, ``"hf_peak"``, ``"hf_rms"``).  Default
        ``"TI_max"``.
    fsaverage_spacing : int
        fsaverage ico spacing for ``space="fsaverage"``: ``5`` (default),
        ``6`` or ``7``.
    group1_name : str
        Display label for the responder group.  Default ``"Responders"``.
    group2_name : str
        Display label for the non-responder group.  Default
        ``"Non-Responders"``.
    value_metric : str
        Label for the field value axis in plots.
    atlas_files : list of str
        Atlas filenames for overlap analysis (looked up in the bundled
        atlas directory).  Default empty.

    Raises
    ------
    ValueError
        If *subjects* lacks at least one responder and one non-responder,
        if a response is not 0 or 1, if a paired test has unequal group
        sizes, if *alpha* or *cluster_threshold* is not strictly between 0
        and 1, if *n_permutations* is not a whole number or is below
        ``floor(1 / alpha)`` (20 at alpha 0.05: with fewer, no p-value could
        fall below *alpha*), if a string value is not a member of
        its enum, or if *fsaverage_field*/*fsaverage_spacing* are invalid
        for ``space="fsaverage"``.

    Examples
    --------
    >>> from tit.stats import GroupComparisonConfig
    >>> subjects = [
    ...     GroupComparisonConfig.Subject("ernie", "L_Insula", response=1),
    ...     GroupComparisonConfig.Subject("101", "L_Insula", response=0),
    ... ]
    >>> cfg = GroupComparisonConfig(
    ...     analysis_name="active_vs_sham", subjects=subjects,
    ...     test_type="unpaired", alternative="two-sided",
    ...     cluster_stat="mass", n_permutations=1000, tissue_type="grey",
    ... )
    >>> cfg.test_type is GroupComparisonConfig.TestType.UNPAIRED
    True
    >>> cfg.nifti_file_pattern
    'grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'

    Subjects can also come from a CSV with columns ``subject_id``,
    ``simulation_name``, ``response``:

    >>> subjects = GroupComparisonConfig.load_subjects("subjects.csv")  # doctest: +SKIP

    See Also
    --------
    GroupComparisonResult : Result container returned by the analysis.
    run_group_comparison : Orchestration function that consumes this config.
    """

    # ── Nested types ──────────────────────────────────────────────────
    ClusterStat = _ClusterStat
    TissueType = _TissueType
    AnalysisSpace = _AnalysisSpace

    class TestType(StrEnum):
        """Type of statistical test for group comparison.

        Attributes
        ----------
        UNPAIRED : str
            ``"unpaired"`` -- independent-samples t-test.
        PAIRED : str
            ``"paired"`` -- paired-samples t-test (groups must be the same
            size and ordered pairwise).
        """

        UNPAIRED = "unpaired"
        PAIRED = "paired"

    class Alternative(StrEnum):
        """Sidedness of the test hypothesis.

        Attributes
        ----------
        TWO_SIDED : str
            ``"two-sided"``.
        GREATER : str
            ``"greater"`` -- responders > non-responders.
        LESS : str
            ``"less"`` -- responders < non-responders.
        """

        TWO_SIDED = "two-sided"
        GREATER = "greater"
        LESS = "less"

    @dataclass
    class Subject:
        """A single subject in a group comparison analysis.

        Attributes
        ----------
        subject_id : str
            Subject identifier (without ``sub-`` prefix).
        simulation_name : str
            Name of the simulation to load for this subject.
        response : int
            Group label -- 1 for responder, 0 for non-responder.
        """

        subject_id: str
        simulation_name: str
        response: int

    # ── Fields ────────────────────────────────────────────────────────
    analysis_name: str
    subjects: list[Subject]

    # Statistical parameters
    test_type: TestType = TestType.UNPAIRED
    alternative: Alternative = Alternative.TWO_SIDED
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = _ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1

    # Data selection
    tissue_type: TissueType = _TissueType.GREY
    nifti_file_pattern: str | None = None

    # Analysis space: MNI volume (default) or fsaverage surface. When
    # ``fsaverage``, the per-subject ``fsaverage_field`` caches are used and the
    # NIfTI/tissue options are ignored.
    space: AnalysisSpace = _AnalysisSpace.MNI
    fsaverage_field: str = "TI_max"
    fsaverage_spacing: int = 5

    # Labels
    group1_name: str = "Responders"
    group2_name: str = "Non-Responders"
    value_metric: str = "Current Intensity"

    # Atlas
    atlas_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Coerce strings (e.g. from the GUI) to enum members so downstream
        # ``.value`` reads never crash; idempotent for members.
        self.test_type = self.TestType(self.test_type)
        self.alternative = self.Alternative(self.alternative)
        self.cluster_stat = self.ClusterStat(self.cluster_stat)
        self.tissue_type = self.TissueType(self.tissue_type)
        self.space = self.AnalysisSpace(self.space)

        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)
        _validate_surface_options(
            self.space, self.fsaverage_field, self.fsaverage_spacing
        )

        self.n_permutations = _validate_test_parameters(
            self.n_permutations, self.alpha, self.cluster_threshold
        )

        for index, subject in enumerate(self.subjects):
            # A response other than 0/1 put the subject in neither group, silently.
            if isinstance(subject.response, bool) or subject.response not in (0, 1):
                raise ValueError(
                    f"subjects[{index}] response must be 0 (non-responder) or 1 "
                    f"(responder), got {subject.response!r}"
                )
        responders = [s for s in self.subjects if s.response == 1]
        non_responders = [s for s in self.subjects if s.response == 0]
        if len(responders) == 0 or len(non_responders) == 0:
            raise ValueError("Need at least one responder and one non-responder")
        if self.test_type == self.TestType.PAIRED and len(responders) != len(
            non_responders
        ):
            raise ValueError(
                "test_type 'paired' pairs responders with non-responders row by row, so "
                f"both groups need the same size; got "
                f"{_count(len(responders), 'responder')} and "
                f"{_count(len(non_responders), 'non-responder')}"
            )

    # ── CSV loader ────────────────────────────────────────────────────

    @classmethod
    def load_subjects(cls, csv_path: str) -> list["GroupComparisonConfig.Subject"]:
        """Load group comparison subjects from a CSV file.

        Expected columns: ``subject_id``, ``simulation_name``, ``response``
        (0 or 1).  The ``sub-`` prefix is stripped from subject IDs
        automatically.

        Parameters
        ----------
        csv_path : str
            Path to a CSV file with the required columns.

        Returns
        -------
        list of Subject
            Subject instances parsed from the CSV rows.

        Raises
        ------
        ValueError
            If required columns are missing, or a row lacks one of their values.
        """
        subjects = []
        for line, row in _read_participant_rows(
            csv_path, {"subject_id", "simulation_name", "response"}
        ):
            if None in (row["subject_id"], row["simulation_name"], row["response"]):
                raise ValueError(
                    f"CSV row {line}: subject_id, simulation_name and response are "
                    "all required"
                )
            subjects.append(
                cls.Subject(
                    subject_id=_participant_id(row["subject_id"]),
                    simulation_name=row["simulation_name"],
                    response=int(float(row["response"])),
                )
            )
        return subjects


@dataclass
class CorrelationConfig:
    """Configuration for correlation-based cluster permutation testing.

    Tests voxelwise correlation between brain field intensities and a
    continuous behavioral or clinical measure (effect size) across subjects,
    with cluster-based permutation correction for multiple comparisons.

    Attributes
    ----------
    analysis_name : str
        Human-readable name for this analysis run.
    subjects : list of Subject
        Subject entries with associated effect sizes.
    correlation_type : CorrelationType
        Pearson or Spearman rank correlation.
    cluster_threshold : float
        Uncorrected p-value threshold for forming clusters.
    cluster_stat : ClusterStat
        Cluster-level statistic used for permutation testing
        (``"mass"`` or ``"size"``).
    n_permutations : int
        Number of permutations for the null distribution.
    alpha : float
        Family-wise error rate for significance.
    n_jobs : int
        Number of parallel workers (``-1`` for the global CPU limit --
        :func:`tit.cpu.cpu_limit`; larger values are clamped to it).
    use_weights : bool
        Whether to apply per-subject weights during correlation.  Default
        ``True``.
    tissue_type : TissueType or str
        Which tissue compartment to analyze: ``"grey"`` (default),
        ``"white"`` or ``"all"``.
    nifti_file_pattern : str or None
        Filename pattern for subject NIfTI files. If ``None``, derived
        automatically from *tissue_type*.
    space : AnalysisSpace or str
        ``"mni"`` (default) or ``"fsaverage"``; see
        :class:`GroupComparisonConfig`.
    fsaverage_field : str
        Surface field for ``space="fsaverage"``.  Default ``"TI_max"``.
    fsaverage_spacing : int
        fsaverage ico spacing (``5``, ``6`` or ``7``).  Default ``5``.
    effect_metric : str
        Label for the behavioral/clinical variable in plots.
    field_metric : str
        Label for the field intensity axis in plots.
    atlas_files : list of str
        Atlas filenames for overlap analysis (looked up in the bundled
        atlas directory).

    Raises
    ------
    ValueError
        If fewer than 3 subjects are given, if an effect size is not a
        finite number or every effect size is equal (the correlation is
        undefined), if *use_weights* is on and a weight is not a positive
        finite number, or for the *alpha*/*cluster_threshold*/
        *n_permutations* rules of :class:`GroupComparisonConfig`.

    See Also
    --------
    CorrelationResult : Result container returned by the analysis.
    run_correlation : Orchestration function that consumes this config.
    """

    # ── Nested types ──────────────────────────────────────────────────
    ClusterStat = _ClusterStat
    TissueType = _TissueType
    AnalysisSpace = _AnalysisSpace

    class CorrelationType(StrEnum):
        """Type of correlation coefficient to compute."""

        PEARSON = "pearson"
        SPEARMAN = "spearman"

    @dataclass
    class Subject:
        """A single subject in a correlation analysis.

        Attributes
        ----------
        subject_id : str
            Subject identifier (without ``sub-`` prefix).
        simulation_name : str
            Name of the simulation to load for this subject.
        effect_size : float
            Continuous behavioral or clinical measure to correlate with
            field intensity.
        weight : float
            Per-subject weight (default 1.0).
        """

        subject_id: str
        simulation_name: str
        effect_size: float
        weight: float = 1.0

    # ── Fields ────────────────────────────────────────────────────────
    analysis_name: str
    subjects: list[Subject]

    # Statistical parameters
    correlation_type: CorrelationType = CorrelationType.PEARSON
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = _ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1
    use_weights: bool = True

    # Data selection
    tissue_type: TissueType = _TissueType.GREY
    nifti_file_pattern: str | None = None

    # Analysis space: MNI volume (default) or fsaverage surface. When
    # ``fsaverage``, the per-subject ``fsaverage_field`` caches are used and the
    # NIfTI/tissue options are ignored.
    space: AnalysisSpace = _AnalysisSpace.MNI
    fsaverage_field: str = "TI_max"
    fsaverage_spacing: int = 5

    # Labels
    effect_metric: str = "Effect Size"
    field_metric: str = "Electric Field Magnitude"

    # Atlas
    atlas_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Coerce strings (e.g. from the GUI) to enum members so downstream
        # ``.value`` reads never crash; idempotent for members.
        self.correlation_type = self.CorrelationType(self.correlation_type)
        self.cluster_stat = self.ClusterStat(self.cluster_stat)
        self.tissue_type = self.TissueType(self.tissue_type)
        self.space = self.AnalysisSpace(self.space)

        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)
        _validate_surface_options(
            self.space, self.fsaverage_field, self.fsaverage_spacing
        )

        if len(self.subjects) < 3:
            raise ValueError(
                f"Need at least 3 subjects for correlation, got {len(self.subjects)}"
            )
        self.n_permutations = _validate_test_parameters(
            self.n_permutations, self.alpha, self.cluster_threshold
        )

        for index, subject in enumerate(self.subjects):
            if not _is_real(subject.effect_size):
                raise ValueError(
                    f"subjects[{index}] effect size must be a finite number, got "
                    f"{subject.effect_size!r}"
                )
            if self.use_weights and not (
                _is_real(subject.weight) and subject.weight > 0
            ):
                raise ValueError(
                    f"subjects[{index}] weight must be a positive finite number when "
                    f"weights are applied, got {subject.weight!r}"
                )
        # r = cov / (std_x * std_y) is 0/0 when every effect size is equal; the engine then
        # reported r = 0 everywhere and a "successful" run with no clusters.
        if len({float(s.effect_size) for s in self.subjects}) == 1:
            raise ValueError(
                "subjects all have the same effect size "
                f"({self.subjects[0].effect_size!r}): a correlation with a constant "
                "variable is undefined"
            )

    # ── CSV loader ────────────────────────────────────────────────────

    @classmethod
    def load_subjects(cls, csv_path: str) -> list["CorrelationConfig.Subject"]:
        """Load correlation subjects from a CSV file.

        Expected columns: ``subject_id``, ``simulation_name``,
        ``effect_size``.  Optional column: ``weight``.  Rows with NaN
        ``subject_id`` or ``effect_size`` are silently skipped.  The ``sub-``
        prefix is stripped from subject IDs automatically.

        Parameters
        ----------
        csv_path : str
            Path to a CSV file with the required columns.

        Returns
        -------
        list of Subject
            Subject instances parsed from valid CSV rows.

        Raises
        ------
        ValueError
            If required columns are missing, a kept row has no simulation_name, or
            no valid subjects are found.
        """
        subjects = []
        for line, row in _read_participant_rows(
            csv_path, {"subject_id", "simulation_name", "effect_size"}
        ):
            if row["subject_id"] is None or row["effect_size"] is None:
                continue
            if row["simulation_name"] is None:
                raise ValueError(f"CSV row {line}: simulation_name is required")
            weight = row.get("weight")
            subjects.append(
                cls.Subject(
                    subject_id=_participant_id(row["subject_id"]),
                    simulation_name=row["simulation_name"],
                    effect_size=float(row["effect_size"]),
                    weight=1.0 if weight is None else float(weight),
                )
            )

        if not subjects:
            raise ValueError("No valid subjects found in CSV")
        return subjects


# ── Results ───────────────────────────────────────────────────────────────


@dataclass
class GroupComparisonResult:
    """Result of a group comparison permutation test.

    Attributes
    ----------
    success : bool
        Whether the analysis completed without error.
    output_dir : str
        Absolute path to the directory containing all outputs (NIfTI maps,
        plots, summary text, log).
    n_responders : int
        Number of responder subjects included.
    n_non_responders : int
        Number of non-responder subjects included.
    n_significant_voxels : int
        Total voxels surviving cluster-corrected threshold.
    n_significant_clusters : int
        Number of spatially contiguous clusters that survived permutation
        correction.
    cluster_threshold : float
        Cluster-level statistic threshold derived from the permutation null
        distribution at the requested alpha.
    analysis_time : float
        Wall-clock duration of the full analysis in seconds.
    clusters : list of dict
        One entry per significant cluster, containing size, mass, peak
        coordinates, and atlas overlap info.
    log_file : str
        Absolute path to the analysis log file.

    See Also
    --------
    GroupComparisonConfig : Configuration that produced this result.
    run_group_comparison : Function that returns this result.
    """

    success: bool
    output_dir: str
    n_responders: int
    n_non_responders: int
    n_significant_voxels: int
    n_significant_clusters: int
    cluster_threshold: float
    analysis_time: float
    clusters: list
    log_file: str


@dataclass
class CorrelationResult:
    """Result of a correlation-based cluster permutation test.

    Attributes
    ----------
    success : bool
        Whether the analysis completed without error.
    output_dir : str
        Absolute path to the directory containing all outputs (NIfTI maps,
        plots, summary text, log).
    n_subjects : int
        Number of subjects included in the analysis.
    n_significant_voxels : int
        Total voxels surviving cluster-corrected threshold.
    n_significant_clusters : int
        Number of spatially contiguous clusters that survived permutation
        correction.
    cluster_threshold : float
        Cluster-level statistic threshold derived from the permutation null
        distribution at the requested alpha.
    analysis_time : float
        Wall-clock duration of the full analysis in seconds.
    clusters : list of dict
        One entry per significant cluster, containing size, mass, peak
        coordinates, mean/peak correlation coefficients, and atlas overlap
        info.
    log_file : str
        Absolute path to the analysis log file.

    See Also
    --------
    CorrelationConfig : Configuration that produced this result.
    run_correlation : Function that returns this result.
    """

    success: bool
    output_dir: str
    n_subjects: int
    n_significant_voxels: int
    n_significant_clusters: int
    cluster_threshold: float
    analysis_time: float
    clusters: list
    log_file: str
