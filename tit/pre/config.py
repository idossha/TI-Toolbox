"""Configuration dataclass for the preprocessing runner.

Pure Python -- no SimNIBS, FreeSurfer, or other heavy dependencies. Mirrors
the ``tit.opt.config`` / ``tit.sim.config`` pattern: a thin, typed wrapper
around the keyword arguments :func:`tit.pre.structural.run_pipeline` already
accepts, read verbatim from :mod:`tit.pre.__main__` (which forwards every one
of these keys with the same defaults). This module does not change either of
those -- see ``PreprocessConfig``'s Notes for the one real mismatch it
surfaces rather than silently papering over.

See Also
--------
tit.pre.__main__ : Reads the exact dict keys this dataclass mirrors.
tit.pre.structural.run_pipeline : Consumes them (as plain keyword arguments,
    not this dataclass).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tit import constants as const


@dataclass
class QSIPrepSettings:
    """Subject-independent QSIPrep resource and pipeline settings.

    Flat by design: mirrors exactly the keyword arguments
    :func:`tit.pre.qsi.qsiprep.run_qsiprep` reads off ``qsiprep_cfg.get(...)``
    inside :func:`tit.pre.structural.run_pipeline` (which loops over
    ``subject_ids`` itself and supplies ``subject_id`` per call) -- there is
    no ``subject_id`` field here, and resource knobs are top-level rather
    than nested under a ``resources`` object. This is deliberately a
    *different* shape from :class:`tit.pre.qsi.config.QSIPrepConfig` (which
    has ``subject_id`` and a nested ``resources: ResourceConfig``, and is
    used internally by ``run_qsiprep``/``docker_builder`` to build the
    Docker invocation) -- serializing *that* class here previously wrote
    ``qsiprep_config.resources.cpus``, which the flat ``.get("cpus")`` read
    never found.

    Attributes
    ----------
    output_resolution : float
        Target output resolution in mm.
    cpus : int or None
        Number of CPUs to allocate. ``None`` inherits from the current
        container.
    memory_gb : int or None
        Memory limit in GB. ``None`` inherits from the current container.
    omp_threads : int
        Threads per process (ANTs, MRtrix, ...).
    image_tag : str
        Docker image tag for QSIPrep.
    skip_bids_validation : bool
        Skip BIDS validation.
    denoise_method : str
        ``"dwidenoise"``, ``"patch2self"``, or ``"none"``.
    unringing_method : str
        ``"mrdegibbs"``, ``"rpg"``, or ``"none"``.

    Raises
    ------
    ValueError
        If *output_resolution* is not positive, or *denoise_method* /
        *unringing_method* is not one of its valid values.

    See Also
    --------
    tit.pre.qsi.qsiprep.run_qsiprep : Consumes these values as keyword
        arguments (not this dataclass).
    """

    output_resolution: float = const.QSI_DEFAULT_OUTPUT_RESOLUTION
    cpus: int | None = None
    memory_gb: int | None = None
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS
    image_tag: str = const.QSI_QSIPREP_IMAGE_TAG
    skip_bids_validation: bool = True
    denoise_method: str = "dwidenoise"
    unringing_method: str = "mrdegibbs"

    def __post_init__(self) -> None:
        if self.output_resolution <= 0:
            raise ValueError("output_resolution must be positive")
        valid_denoise = {"dwidenoise", "patch2self", "none"}
        if self.denoise_method not in valid_denoise:
            raise ValueError(f"denoise_method must be one of {valid_denoise}")
        valid_unring = {"mrdegibbs", "rpg", "none"}
        if self.unringing_method not in valid_unring:
            raise ValueError(f"unringing_method must be one of {valid_unring}")


@dataclass
class QSIReconSettings:
    """Subject-independent QSIRecon resource and pipeline settings.

    Flat by design: mirrors exactly the keyword arguments
    :func:`tit.pre.qsi.qsirecon.run_qsirecon` reads off ``recon_cfg.get(...)``
    inside :func:`tit.pre.structural.run_pipeline`. See
    :class:`QSIPrepSettings` for why this is a distinct, subject-less,
    flat-resource shape from :class:`tit.pre.qsi.config.QSIReconConfig`.

    Attributes
    ----------
    recon_specs : list of str
        Reconstruction specs to run.
    atlases : list of str or None
        Atlases for connectivity analysis. ``None`` = no connectivity.
    use_gpu : bool
        Enable GPU acceleration (requires NVIDIA Docker runtime).
    cpus : int or None
        Number of CPUs to allocate. ``None`` inherits from the current
        container.
    memory_gb : int or None
        Memory limit in GB. ``None`` inherits from the current container.
    omp_threads : int
        Threads per process.
    image_tag : str
        Docker image tag for QSIRecon.
    skip_odf_reports : bool
        Skip ODF report generation.

    Raises
    ------
    ValueError
        If *recon_specs* is empty or contains an unknown spec, or *atlases*
        contains an unknown atlas.

    See Also
    --------
    tit.pre.qsi.qsirecon.run_qsirecon : Consumes these values as keyword
        arguments (not this dataclass).
    """

    recon_specs: list[str] = field(
        default_factory=lambda: [const.QSI_DEFAULT_RECON_SPEC]
    )
    atlases: list[str] | None = None
    use_gpu: bool = False
    cpus: int | None = None
    memory_gb: int | None = None
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS
    image_tag: str = const.QSI_QSIRECON_IMAGE_TAG
    skip_odf_reports: bool = True

    def __post_init__(self) -> None:
        if not self.recon_specs:
            raise ValueError("At least one recon_spec is required")
        valid_specs = set(const.QSI_RECON_SPECS)
        for spec in self.recon_specs:
            if spec not in valid_specs:
                raise ValueError(
                    f"Unknown recon spec: {spec}. Valid specs: {valid_specs}"
                )
        if self.atlases:
            valid_atlases = set(const.QSI_ATLASES)
            for atlas in self.atlases:
                if atlas not in valid_atlases:
                    raise ValueError(
                        f"Unknown atlas: {atlas}. Valid atlases: {valid_atlases}"
                    )


#: Old ``PreprocessConfig`` keys still accepted on input, mapped to what they
#: mean now. ``None`` means "dropped, no replacement".
LEGACY_KEYS: dict[str, str | None] = {
    "run_recon": "run_fastsurfer",
    "parallel_recon": None,
    "parallel_cores": None,
    "run_subcortical_segmentations": None,
}


def migrate_legacy_keys(
    data: dict, *, logger=None, warnings: list[str] | None = None
) -> dict:
    """Return *data* with pre-FastSurfer keys translated, warning on each.

    Reads a config JSON written before the FreeSurfer stage was removed:
    ``run_recon`` becomes ``run_fastsurfer`` (unless the caller already set
    it), and ``parallel_recon`` / ``parallel_cores`` /
    ``run_subcortical_segmentations`` are dropped. The input dict is not
    mutated.

    Parameters
    ----------
    data : dict
        Raw config mapping, as read from JSON.
    logger : logging.Logger or None, optional
        Logger for the deprecation warnings. Defaults to the ``tit.pre``
        logger.
    warnings : list[str] or None, optional
        When given, each deprecation message is also appended here (in
        addition to the log line) -- lets a caller such as
        ``POST /api/plan/pre`` surface the migration in its own HTTP
        response instead of only the server log, since a caller still on
        the pre-v3 JSON shape has no other way to see it (QA researcher
        finding, ``qa-neuro-researcher-notes.md`` #5).

    Returns
    -------
    dict
        A copy with only current keys.
    """
    if not any(key in data for key in LEGACY_KEYS):
        return data

    import logging

    log = logger or logging.getLogger("tit.pre")

    def warn(message: str) -> None:
        log.warning(message)
        if warnings is not None:
            warnings.append(message)

    migrated = dict(data)
    for old_key, new_key in LEGACY_KEYS.items():
        if old_key not in migrated:
            continue
        value = migrated.pop(old_key)
        if new_key is None:
            warn(
                f"Preprocessing config key {old_key!r} is no longer supported "
                "(FreeSurfer recon-all and the MATLAB-runtime subfield "
                "segmentations were removed); ignoring it."
            )
            continue
        if new_key in migrated:
            warn(
                f"Preprocessing config key {old_key!r} is deprecated; "
                f"{new_key!r} is already set, ignoring the old key."
            )
            continue
        warn(
            f"Preprocessing config key {old_key!r} is deprecated; reading it "
            f"as {new_key!r} (FastSurfer --seg_only replaces recon-all)."
        )
        migrated[new_key] = value
    return migrated


@dataclass
class PreprocessConfig:
    """Configuration for one preprocessing-pipeline run.

    Every step is opt-in via its own boolean flag; disabled steps are
    skipped. Mirrors ``run_pipeline``'s keyword arguments exactly (see
    :func:`tit.pre.structural.run_pipeline`).

    Attributes
    ----------
    subject_ids : list of str
        Subject identifiers (without the ``sub-`` prefix). Must be
        non-empty.
    convert_dicom : bool
        Run DICOM-to-NIfTI conversion.
    run_fastsurfer : bool
        Run FastSurfer ``--seg_only`` deep segmentation. Requires a BIDS
        T1w image; the UI offers it checked whenever one exists.
    fastsurfer_threads : int or None
        Thread count for FastSurfer inference. ``None`` uses
        :data:`tit.pre.fastsurfer.DEFAULT_THREADS` (or
        ``$TIT_FASTSURFER_THREADS``).
    create_m2m : bool
        Run SimNIBS ``charm`` (also runs ``subject_atlas``).
    run_tissue_analysis : bool
        Run tissue-volume and thickness analysis.
    run_qsiprep : bool
        Run QSIPrep DWI preprocessing via Docker.
    run_qsirecon : bool
        Run QSIRecon reconstruction via Docker.
    qsiprep_config : QSIPrepSettings or None
        Extra QSIPrep configuration. Serializes to the same flat shape
        :func:`tit.pre.structural.run_pipeline` reads via
        ``qsiprep_cfg.get(...)`` -- see :class:`QSIPrepSettings`.
    qsi_recon_config : QSIReconSettings or None
        Extra QSIRecon configuration. Same shape guarantee as
        *qsiprep_config* -- see :class:`QSIReconSettings`.
    extract_dti : bool
        Extract DTI tensor for SimNIBS anisotropic conductivity.
    skip_existing_outputs : bool
        Skip selected steps when their output already exists.
    replace_existing_outputs : bool
        Remove selected existing outputs before rerunning their steps.

    Raises
    ------
    ValueError
        If *subject_ids* is empty.

    Notes
    -----
    **Deprecated keys.** ``run_recon`` (FreeSurfer ``recon-all``),
    ``parallel_recon``, ``parallel_cores`` and
    ``run_subcortical_segmentations`` (thalamic nuclei / hippocampal
    subfields, MATLAB-runtime binaries) were removed with the FreeSurfer
    container. :func:`tit.pre.config.migrate_legacy_keys` still reads them
    off an old config JSON: ``run_recon`` maps onto ``run_fastsurfer`` with
    a warning, the other three are dropped with a warning. Existing
    ``derivatives/freesurfer`` output on disk keeps working -- every atlas
    reader still discovers it.

    ``qsiprep_config`` / ``qsi_recon_config`` are deliberately **not**
    :class:`tit.pre.qsi.config.QSIPrepConfig` / ``QSIReconConfig`` (those
    dataclasses carry a required ``subject_id`` and nest resource knobs
    under ``resources: ResourceConfig`` -- shapes built and consumed
    internally by :func:`tit.pre.qsi.qsiprep.run_qsiprep` /
    :func:`tit.pre.qsi.qsirecon.run_qsirecon` themselves, per call, once
    ``run_pipeline`` already knows which subject it is processing).
    :class:`QSIPrepSettings` / :class:`QSIReconSettings` are the flat,
    subject-independent settings shape ``run_pipeline`` actually reads off
    these two fields (via ``qsiprep_cfg.get("cpus")`` etc.) for every
    subject in *subject_ids*; :mod:`tit.pre.__main__` converts each to a
    plain dict before calling ``run_pipeline``.

    See Also
    --------
    tit.pre.structural.run_pipeline : Consumes these values as keyword
        arguments (not this dataclass).
    """

    subject_ids: list[str] = field(default_factory=list)

    convert_dicom: bool = False
    run_fastsurfer: bool = False
    fastsurfer_threads: int | None = None
    create_m2m: bool = False
    run_tissue_analysis: bool = False
    run_qsiprep: bool = False
    run_qsirecon: bool = False
    qsiprep_config: QSIPrepSettings | None = None
    qsi_recon_config: QSIReconSettings | None = None
    extract_dti: bool = False
    skip_existing_outputs: bool = False
    replace_existing_outputs: bool = False

    def __post_init__(self) -> None:
        if not self.subject_ids:
            raise ValueError("subject_ids must be non-empty")
