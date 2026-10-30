#!/usr/bin/env simnibs_python
"""Mesh-to-NIfTI conversion using the SimNIBS Python API.

Wraps ``simnibs.transformations`` so that the simulation pipeline can
convert ``.msh`` meshes to volumetric NIfTI files without shelling out
to bash scripts.

Public API
----------
msh_to_nifti
    Convert a single mesh to subject-space NIfTI.
msh_to_mni
    Convert a single mesh to MNI-space NIfTI.
convert_mesh_dir
    Batch-convert every ``.msh`` file in a directory.

See Also
--------
tit.tools.nifti_to_mesh : Inverse operation (NIfTI to surface mesh).
tit.tools.field_extract : Extract tissue sub-meshes before conversion.
"""

import concurrent.futures
import logging
import os
import tempfile
from copy import deepcopy

from simnibs import mesh_io, transformations

logger = logging.getLogger(__name__)

#: The tissue crops a field mesh's NIfTIs are written for, as SimNIBS tissue tags: the
#: ``grey_`` / ``white_`` NIfTIs are the volume mesh's grey- and white-matter tetrahedra.
TISSUE_TAGS: dict[str, list[int]] = {"grey": [2], "white": [1]}


def _resolve_workers(n_tasks: int, max_workers: int | None) -> int:
    """Decide how many worker processes to use for a batch of *n_tasks*.

    Precedence: explicit *max_workers* argument, then the
    ``TI_NIFTI_WORKERS`` environment variable, then a default of
    ``min(n_tasks, job_cpus(), 8)`` (the global CPU limit outside a
    job).  The result is always clamped to ``[1, n_tasks]``.
    """
    workers = max_workers
    if workers is None:
        env = os.environ.get("TI_NIFTI_WORKERS")
        if env:
            try:
                workers = int(env)
            except ValueError:
                logger.warning("Invalid TI_NIFTI_WORKERS=%r; ignoring", env)
    if workers is None or workers <= 0:
        from tit.cpu import job_cpus

        workers = min(n_tasks, job_cpus(), 8)
    return max(1, min(workers, n_tasks))


def _subject_worker(src_path: str, m2m_dir: str, out_prefix: str) -> None:
    """Convert *src_path* to subject-space NIfTI (process-pool target)."""
    mesh = mesh_io.read_msh(src_path)
    transformations.interpolate_to_volume(mesh, m2m_dir, out_prefix)


def _mni_worker(src_path: str, m2m_dir: str, out_prefix: str) -> None:
    """Convert *src_path* to MNI-space NIfTI (process-pool target)."""
    transformations.warp_volume(src_path, m2m_dir, out_prefix)


def _write_temp_mesh(mesh) -> str:
    """Write *mesh* to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".msh")
    os.close(fd)
    mesh_io.write_msh(mesh, path)
    return path


def _cropped(mesh, tags: list[int] | None):
    """*mesh* cropped to the elements tagged *tags*; *mesh* itself when *tags* is ``None``."""
    return mesh if tags is None else mesh.crop_mesh(tags=tags)


def _filter_mesh_fields(mesh, fields: list[str]):
    """Return a shallow copy of *mesh* containing only the named fields.

    Filters both ``elmdata`` (element data) and ``nodedata`` (node data).
    If a requested field is not present it is silently skipped.
    """
    out = deepcopy(mesh)
    out.elmdata = [d for d in out.elmdata if d.field_name in fields]
    out.nodedata = [d for d in out.nodedata if d.field_name in fields]
    return out


def msh_to_nifti(
    mesh_path: str,
    m2m_dir: str,
    output_path: str,
    fields: list[str] | None = None,
    tags: list[int] | None = None,
) -> None:
    """Convert a mesh file to subject-space NIfTI.

    Parameters
    ----------
    mesh_path : str
        Path to the ``.msh`` file.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory (used as reference grid).
    output_path : str
        Output file prefix.  SimNIBS appends the field name
        (e.g. ``prefix_magnE.nii.gz``).
    fields : list[str] | None
        If given, only these fields are written.  Otherwise all fields in the
        mesh are converted.
    tags : list[int] | None
        If given, the mesh is first cropped to the elements with these tissue tags
        (:data:`TISSUE_TAGS`).
    """
    mesh = _cropped(mesh_io.read_msh(mesh_path), tags)
    if fields:
        mesh = _filter_mesh_fields(mesh, fields)
    transformations.interpolate_to_volume(mesh, m2m_dir, output_path)


def msh_to_mni(
    mesh_path: str,
    m2m_dir: str,
    output_path: str,
    fields: list[str] | None = None,
    tags: list[int] | None = None,
) -> None:
    """Convert a mesh file to MNI-space NIfTI.

    Parameters
    ----------
    mesh_path : str
        Path to the ``.msh`` file.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory.
    output_path : str
        Output file prefix.  SimNIBS appends the field name
        (e.g. ``prefix_magnE.nii.gz``).
    fields : list[str] | None
        If given, only these fields are written.
    tags : list[int] | None
        If given, the mesh is first cropped to the elements with these tissue tags.
    """
    temp = None
    if fields or tags:
        mesh = _cropped(mesh_io.read_msh(mesh_path), tags)
        if fields:
            mesh = _filter_mesh_fields(mesh, fields)
        mesh_path = temp = _write_temp_mesh(mesh)
    try:
        transformations.warp_volume(mesh_path, m2m_dir, output_path)
    finally:
        if temp is not None:
            os.unlink(temp)


def convert_mesh_dir(
    mesh_dir: str,
    output_dir: str,
    m2m_dir: str,
    fields: list[str] | None = None,
    skip_patterns: list[str] | None = None,
    max_workers: int | None = None,
    map_to_mni: bool = True,
) -> None:
    """Batch-convert every ``.msh`` file in *mesh_dir* to NIfTI.

    Subject-space NIfTI is always produced; MNI output is optional:

    * ``{basename}_subject_{field}.nii.gz``  – subject space
    * ``{basename}_MNI_{field}.nii.gz``      – MNI space

    The subject-space and MNI-space conversions are independent (distinct
    output files, no shared state), so all conversions across every mesh
    are run concurrently in a process pool.  The SimNIBS transforms are
    single-threaded (``OMP_NUM_THREADS`` is typically 1 in the container),
    so this yields a substantial wall-clock speedup on multi-core hosts.

    Parameters
    ----------
    mesh_dir : str
        Directory containing ``.msh`` files.
    output_dir : str
        Where the NIfTI files are written.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory.
    fields : list[str] | None
        If given, only these fields are converted.
    skip_patterns : list[str] | None
        Basenames containing any of these substrings are skipped. By default
        only basenames ending in ``_normal`` are -- the surface-only
        ``<name>_normal.msh`` / ``<name>_mTI_normal.msh`` meshes, which have no
        volume elements -- so a montage or subject whose name merely contains
        "normal" is still converted.
    map_to_mni : bool
        Include MNI-space outputs (default True for standalone conversion).
    max_workers : int | None
        Number of worker processes.  Defaults to the ``TI_NIFTI_WORKERS``
        environment variable, or ``min(n_tasks, job_cpus(), 8)``.  Set to
        ``1`` to run serially (e.g. for debugging or memory-constrained
        hosts).

    See Also
    --------
    convert_mesh_dirs : Convert several directories in a single pool.
    """
    tasks, temp_paths = _collect_tasks(
        mesh_dir, output_dir, fields, skip_patterns, map_to_mni
    )
    if not tasks:
        logger.warning("No .msh files to convert in %s", mesh_dir)
        return

    _run_tasks(tasks, m2m_dir, temp_paths, max_workers)
    logger.info("NIfTI conversion complete: %s", output_dir)


def convert_mesh_dirs(
    specs: list[dict],
    m2m_dir: str,
    max_workers: int | None = None,
    map_to_mni: bool = True,
) -> None:
    """Convert several mesh directories to NIfTI in a single process pool.

    Equivalent to calling :func:`convert_mesh_dir` once per directory, but
    every conversion task from every directory is submitted to *one* shared
    pool.  This overlaps directories that would otherwise run one after the
    other (e.g. the TI-mesh and HF-mesh directories in the simulation
    pipeline) and avoids nesting process pools.

    Parameters
    ----------
    specs : list[dict]
        One dict per directory with keys ``mesh_dir`` and ``output_dir``
        (required) and optional ``fields`` / ``skip_patterns`` (same meaning
        as in :func:`convert_mesh_dir`) and ``tissues``: ``True`` also converts each
        mesh's grey- and white-matter crops (:data:`TISSUE_TAGS`) as
        ``grey_<base>`` / ``white_<base>``, the simulator's field-mesh NIfTIs.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory.
    map_to_mni : bool
        Include MNI-space outputs (default True for standalone conversion).
    max_workers : int | None
        Number of worker processes.  See :func:`convert_mesh_dir`.

    See Also
    --------
    convert_mesh_dir : Convert a single directory.
    """
    all_tasks: list[tuple] = []
    all_temp: list[str] = []
    for spec in specs:
        tasks, temp_paths = _collect_tasks(
            spec["mesh_dir"],
            spec["output_dir"],
            spec.get("fields"),
            spec.get("skip_patterns"),
            map_to_mni,
            tissues=spec.get("tissues", False),
        )
        all_tasks.extend(tasks)
        all_temp.extend(temp_paths)

    if not all_tasks:
        logger.warning("No .msh files to convert in any of %d directories", len(specs))
        return

    _run_tasks(all_tasks, m2m_dir, all_temp, max_workers)
    for spec in specs:
        logger.info("NIfTI conversion complete: %s", spec["output_dir"])


def _collect_tasks(
    mesh_dir: str,
    output_dir: str,
    fields: list[str] | None,
    skip_patterns: list[str] | None,
    map_to_mni: bool = True,
    *,
    tissues: bool = False,
) -> tuple[list[tuple], list[str]]:
    """Build the (tasks, temp_paths) for one mesh directory.

    Each task is a ``(worker, source-mesh-path, output-prefix)`` triple.
    When filtering fields or cropping to a tissue (*tissues*), the mesh is
    written to a temp file once and shared by both the subject- and MNI-space
    tasks (``warp_volume`` only accepts file paths, not in-memory meshes).
    """

    def skipped(base: str) -> bool:
        if skip_patterns is None:
            return base.endswith("_normal")  # the surface-only TI_normal mesh
        return any(p in base for p in skip_patterns)

    os.makedirs(output_dir, exist_ok=True)

    msh_files = sorted(
        f
        for f in os.listdir(mesh_dir)
        if f.endswith(".msh")
        and not f.startswith("._")  # AppleDouble metadata is not a mesh.
        and os.path.isfile(os.path.join(mesh_dir, f))
    )
    if not msh_files:
        logger.warning("No .msh files found in %s", mesh_dir)
        return [], []

    tasks: list[tuple] = []
    temp_paths: list[str] = []
    for fname in msh_files:
        base = os.path.splitext(fname)[0]
        if skipped(base):
            logger.debug("Skipping surface mesh: %s", fname)
            continue

        mesh_path = os.path.join(mesh_dir, fname)
        sources = [(base, mesh_path)]
        if fields or tissues:
            mesh = mesh_io.read_msh(mesh_path)
            if fields:
                mesh = _filter_mesh_fields(mesh, fields)
            variants = [(base, mesh)]
            if tissues:
                variants += [
                    (f"{tissue}_{base}", mesh.crop_mesh(tags=tags))
                    for tissue, tags in TISSUE_TAGS.items()
                ]
            sources = []
            for name, variant in variants:
                if variant is mesh and not fields:
                    sources.append((name, mesh_path))
                    continue
                temp = _write_temp_mesh(variant)
                temp_paths.append(temp)
                sources.append((name, temp))

        for name, src_path in sources:
            tasks.append(
                (_subject_worker, src_path, os.path.join(output_dir, f"{name}_subject"))
            )
            if map_to_mni:
                tasks.append(
                    (_mni_worker, src_path, os.path.join(output_dir, f"{name}_MNI"))
                )

    return tasks, temp_paths


def _run_tasks(
    tasks: list[tuple],
    m2m_dir: str,
    temp_paths: list[str],
    max_workers: int | None,
) -> None:
    """Run conversion *tasks* in a process pool, cleaning up *temp_paths*."""
    workers = _resolve_workers(len(tasks), max_workers)
    logger.info(
        "Converting %d mesh task(s) to NIfTI with %d worker(s)", len(tasks), workers
    )

    try:
        if workers == 1:
            for fn, src, out in tasks:
                fn(src, m2m_dir, out)
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
                futures = [ex.submit(fn, src, m2m_dir, out) for fn, src, out in tasks]
                for fut in concurrent.futures.as_completed(futures):
                    fut.result()  # re-raise any worker exception
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
