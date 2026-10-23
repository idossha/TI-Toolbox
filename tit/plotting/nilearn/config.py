"""Configuration dataclass for the Nilearn Visuals panel (owner: B4).

Mirrors the fields that panel collects, so
:mod:`tit.config_io` can generate a JSON Schema for it and a future
``POST /api/jobs`` (kind ``"nilearn"``) can validate a request body before
submitting the job. Pure Python -- no numpy/nibabel/nilearn dependency.

Public API
----------
NilearnSubjectSimulation
    One subject/simulation pair to average and visualise.
NilearnConfig
    Configuration for one Nilearn Visuals run.

See Also
--------
tit.plotting.nilearn.__main__ : Runner entry point that consumes this config
    (``simnibs_python -m tit.plotting.nilearn config.json``).
"""

from __future__ import annotations

from dataclasses import dataclass

from tit.paths import validate_name
from tit.plotting.nilearn.atlases import ATLASES


@dataclass
class NilearnSubjectSimulation:
    """One subject/simulation pair to group-average before visualising."""

    subject_id: str
    simulation_name: str


@dataclass
class NilearnConfig:
    """Configuration for one Nilearn Visuals run.

    Attributes
    ----------
    subject_simulation_pairs : list of NilearnSubjectSimulation
        Subjects/simulations to group-average before visualising.
    min_cutoff : float or None, optional
        Minimum threshold (V/m, or a percentile when *use_percentiles* is
        true). ``None`` -- the default -- is data-driven: the 95th
        percentile of the averaged field's non-zero voxels, the display
        floor the former simulation report derived from real TI fields.
        A fixed default in V/m cannot work here: a real TI field
        peaks around 0.1 V/m, so the former ``0.3`` was above every voxel
        of every run and the job died inside matplotlib.
    max_cutoff : float or None, optional
        Maximum threshold; ``None`` (the default) uses the 99.9th
        percentile of the averaged data.
    atlas_name : str, optional
        Atlas used for region contours on the slice PDF: a key of
        :data:`tit.plotting.nilearn.atlases.ATLASES`, the atlases the image bundles.
    selected_regions : list of int or None, optional
        0-indexed region indices to include; ``None`` includes all.
    subdir_name : str, optional
        Output subdirectory under
        ``derivatives/ti-toolbox/nilearn_visuals/``.
    use_percentiles : bool, optional
        Interpret *min_cutoff*/*max_cutoff* as percentiles (0-100) of the
        averaged data's non-zero voxels rather than absolute V/m values.
    create_glass_brain : bool, optional
        Also render a glass-brain PDF alongside the multi-slice one.
    glass_brain_cmap : str, optional
        Colormap for the glass-brain render.

    Raises
    ------
    ValueError
        If *subject_simulation_pairs* is empty, *use_percentiles* is set
        with a cutoff outside ``[0, 100]``, or *atlas_name* is not a bundled atlas.

    See Also
    --------
    tit.plotting.nilearn.__main__.main : Consumes this config.
    tit.plotting.nilearn.cutoffs.resolve_cutoffs : Turns these fields into
        the two absolute V/m numbers the renderers take, and refuses a
        cutoff that is above the data with a message naming the range.
    """

    subject_simulation_pairs: list[NilearnSubjectSimulation]
    min_cutoff: float | None = None
    max_cutoff: float | None = None
    atlas_name: str = "harvard_oxford_sub"
    selected_regions: list[int] | None = None
    subdir_name: str = "nilearn_visuals"
    use_percentiles: bool = False
    create_glass_brain: bool = False
    glass_brain_cmap: str = "hot"

    def __post_init__(self) -> None:
        """Refuse what would write outside one output folder, plot nothing, or skew the mean.

        Checked here, before a job runs, because each needs no data:

        - *subdir_name* is one folder under ``nilearn_visuals/`` (the panel's
          ``derivatives/ti-toolbox/nilearn_visuals/{name}/``), held to
          :func:`tit.paths.validate_name`: ``"../stats"`` would write into ``stats/``,
          ``"a/b"`` one level deeper, and ``""`` into ``nilearn_visuals/`` itself, where
          the Results page never looks.
        - Both cutoffs given with the minimum not below the maximum is an empty display
          range in either unit (a percentile is monotone in its rank), which
          :func:`~tit.plotting.nilearn.cutoffs.resolve_cutoffs` would refuse only after
          loading every field.
        - A repeated subject/simulation pair would count that field twice in the
          voxelwise mean.
        - An *atlas_name* that is not a key of
          :data:`~tit.plotting.nilearn.atlases.ATLASES` (such as ``"aal"``, offered up to
          v3.1.1) has no bundled label image, so the slice PDF would lose its outlines.

        Raises:
            ValueError: Naming the field and the value it refused.
        """
        if not self.subject_simulation_pairs:
            raise ValueError("at least one subject/simulation pair is required")
        validate_name(self.subdir_name, "subdir_name")
        if self.atlas_name not in ATLASES:
            raise ValueError(
                f"atlas_name {self.atlas_name!r} is not an atlas Nilearn visuals offers; "
                f"choose one of: {', '.join(ATLASES)}"
            )
        if self.use_percentiles:
            for cutoff in (self.min_cutoff, self.max_cutoff):
                if cutoff is not None and not (0 <= cutoff <= 100):
                    raise ValueError("percentile cutoffs must be within [0, 100]")
        if (
            self.min_cutoff is not None
            and self.max_cutoff is not None
            and self.min_cutoff >= self.max_cutoff
        ):
            unit = "%" if self.use_percentiles else " V/m"
            raise ValueError(
                f"min_cutoff {self.min_cutoff:g}{unit} must be below max_cutoff "
                f"{self.max_cutoff:g}{unit}: nothing would be drawn"
            )
        seen = set()
        for pair in self.subject_simulation_pairs:
            key = (pair.subject_id, pair.simulation_name)
            if key in seen:
                raise ValueError(
                    f"subject_simulation_pairs lists sub-{key[0]} / {key[1]} twice: "
                    "the group average would count that simulation double"
                )
            seen.add(key)
