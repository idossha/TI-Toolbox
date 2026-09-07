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
        percentile of the averaged field's non-zero voxels, the same
        display floor ``tit.reporting`` already uses for its own field
        figures. A fixed default in V/m cannot work here: a real TI field
        peaks around 0.1 V/m, so the former ``0.3`` was above every voxel
        of every run and the job died inside matplotlib.
    max_cutoff : float or None, optional
        Maximum threshold; ``None`` (the default) uses the 99.9th
        percentile of the averaged data.
    atlas_name : str, optional
        Atlas used for region contours on the slice PDF.
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
        If *subject_simulation_pairs* is empty, or *use_percentiles* is set
        with a cutoff outside ``[0, 100]``.

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
        if not self.subject_simulation_pairs:
            raise ValueError("at least one subject/simulation pair is required")
        if self.use_percentiles:
            for cutoff in (self.min_cutoff, self.max_cutoff):
                if cutoff is not None and not (0 <= cutoff <= 100):
                    raise ValueError("percentile cutoffs must be within [0, 100]")
