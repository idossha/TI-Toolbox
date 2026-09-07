#!/usr/bin/env simnibs_python
"""
FastSurfer ``--seg_only`` deep segmentation.

Replaces the FreeSurfer ``recon-all`` stage as the source of a voxel-space
cortical+subcortical parcellation (``aparc.DKTatlas+aseg``). FastSurfer is
Apache-2.0, PyTorch-only, needs no FreeSurfer binaries and no MATLAB runtime,
and its label ids are byte-identical to FreeSurfer's colour table -- so every
existing reader (``VoxelAtlasManager``, ``roi_spec``, the analyzer) works on
its output unchanged.

Public API
----------
fastsurfer_available
    Capability probe: is a runnable FastSurfer checkout present?
fastsurfer_home
    Resolved ``FASTSURFER_HOME`` (env, else ``/opt/fastsurfer``).
run_fastsurfer
    Run ``run_fastsurfer.sh --seg_only`` for one subject.

Notes
-----
Measured on this project's own spike (``docs/dev/HISTORY.md § 2026-09-03``,
sub-ernie, Apple M2, 8 threads, CPU only): ~5 min for the segmentation
itself, 4.84 GiB peak RSS, mean Dice 0.922 (14 subcortical) / 0.914
(20 cortical DKT) against real ``recon-all`` output on the same subject.
``--no_cc`` is mandatory: without it FastSurfer downloads 81 MB of
corpus-callosum checkpoints the toolbox has no use for, and the CC module
crashed in that spike *after* the segmentation was already written.

See Also
--------
tit.pre.charm : SimNIBS charm head-mesh generation (runs in parallel).
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
tit.atlas.segstats : The LUT/label-listing code reused for the sidecar.
"""

from __future__ import annotations

import gzip
import os
import shutil
import tempfile
from pathlib import Path

from tit.paths import get_path_manager

from .utils import CommandRunner, PreprocessError, _find_anat_files

#: Environment variable naming the FastSurfer checkout.
ENV_FASTSURFER_HOME = "FASTSURFER_HOME"

#: Where the ``idossha/ti-toolbox`` image puts FastSurfer (plan D1).
DEFAULT_FASTSURFER_HOME = "/opt/fastsurfer"

#: Environment override for the interpreter handed to ``--py``.
ENV_FASTSURFER_PYTHON = "TIT_FASTSURFER_PYTHON"

#: FastSurfer's ``--py`` selects the interpreter that imports torch. In the
#: image that is the SimNIBS environment itself (torch is already a charm
#: dependency), so there is no second venv to point at.
DEFAULT_FASTSURFER_PYTHON = "simnibs_python"

#: Environment override for the thread count (see :func:`resolve_threads`).
ENV_FASTSURFER_THREADS = "TIT_FASTSURFER_THREADS"

RUN_SCRIPT = "run_fastsurfer.sh"

#: The one output the toolbox consumes, in FastSurfer's own naming.
SEG_FILENAME = "aparc.DKTatlas+aseg.deep.mgz"

#: NIfTI copy written next to it, for readers that cannot open ``.mgz``.
SEG_NIFTI_FILENAME = "aparc.DKTatlas+aseg.deep.nii.gz"

#: ``mri_segstats --sum``-shaped label sidecar both files share
#: (:meth:`tit.atlas.voxel.VoxelAtlasManager.list_regions` derives exactly
#: this name from either atlas filename).
SEG_LABELS_FILENAME = "aparc.DKTatlas+aseg.deep_labels.txt"

#: Threads used when neither the caller nor the environment says otherwise.
#: FastSurfer peaks at ~4.8 GiB regardless of thread count; the ``pre`` job
#: kind's default budget is 2 cpus / 6 GB (:mod:`tit.jobs.costs`), so 2 is
#: the honest default and callers with a bigger budget pass it explicitly.
DEFAULT_THREADS = 2


def fastsurfer_home() -> Path:
    """Return the resolved FastSurfer checkout directory.

    ``$FASTSURFER_HOME`` when set and non-empty, else
    :data:`DEFAULT_FASTSURFER_HOME`. The directory is not required to exist
    -- use :func:`fastsurfer_available` for that.
    """
    return Path(os.environ.get(ENV_FASTSURFER_HOME) or DEFAULT_FASTSURFER_HOME)


def fastsurfer_script() -> Path | None:
    """Return the path to ``run_fastsurfer.sh``, or ``None`` if absent."""
    script = fastsurfer_home() / RUN_SCRIPT
    return script if script.is_file() else None


def fastsurfer_available() -> bool:
    """Return ``True`` when a runnable FastSurfer checkout is present.

    Capability-probe shape (same contract as the server's other capability
    probes): filesystem-only, no subprocess, safe to call on any platform.
    """
    return fastsurfer_script() is not None


def fastsurfer_python() -> str:
    """Return the interpreter passed to FastSurfer's ``--py`` flag."""
    return os.environ.get(ENV_FASTSURFER_PYTHON) or DEFAULT_FASTSURFER_PYTHON


def resolve_threads(threads: int | None = None) -> int:
    """Return the thread count for one FastSurfer run.

    Precedence: explicit *threads* argument (the job's own cpu budget),
    then ``$TIT_FASTSURFER_THREADS``, then :data:`DEFAULT_THREADS`. Values
    below 1 are clamped up to 1.
    """
    if threads is None:
        env_value = os.environ.get(ENV_FASTSURFER_THREADS)
        if env_value:
            try:
                threads = int(env_value)
            except ValueError:
                threads = None
    if threads is None:
        threads = DEFAULT_THREADS
    return max(1, int(threads))


def _missing_fastsurfer_error() -> PreprocessError:
    return PreprocessError(
        f"FastSurfer is not installed: no {RUN_SCRIPT} under "
        f"{fastsurfer_home()}. Set {ENV_FASTSURFER_HOME} to a FastSurfer "
        "checkout, or use an image that ships one "
        f"(the TI-Toolbox image installs it at {DEFAULT_FASTSURFER_HOME})."
    )


def _write_nifti_copy(mgz_path: Path, nifti_path: Path, *, logger) -> None:
    """Write a ``.nii.gz`` copy of *mgz_path*, preserving integer labels.

    Goes through an uncompressed temporary file and stdlib ``gzip``:
    nibabel's own gzip writer is unreliable on Docker bind mounts (the same
    workaround :func:`tit.pre.qsi.dti_extractor._save_nifti_gz` uses).
    """
    import nibabel as nib
    import numpy as np

    img = nib.load(str(mgz_path))
    data = np.asanyarray(img.dataobj)
    # Label volumes must stay integral: MGH stores DKT+aseg ids as int32 or
    # uint8; float output here would break every `np.unique`-based reader.
    if not np.issubdtype(data.dtype, np.integer):
        data = np.rint(data).astype(np.int32)
    out = nib.Nifti1Image(data, img.affine)
    out.set_data_dtype(data.dtype)

    nifti_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_nii = Path(tmpdir) / "seg.nii"
        tmp_gz = Path(tmpdir) / "seg.nii.gz"
        nib.save(out, str(tmp_nii))
        with open(tmp_nii, "rb") as f_in, gzip.open(str(tmp_gz), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        shutil.copy2(str(tmp_gz), str(nifti_path))
    logger.info(f"Wrote NIfTI copy: {nifti_path}")


def _write_labels_sidecar(atlas_path: Path, labels_path: Path, *, logger) -> None:
    """Write the ``*_labels.txt`` sidecar the atlas readers cache-read.

    Reuses :mod:`tit.atlas.segstats` -- the FreeSurfer-free replacement for
    ``mri_segstats``, validated voxel-for-voxel against the real binary.
    """
    from tit.atlas.segstats import (
        compute_segstats,
        resolve_lut_for_atlas,
        write_segstats_sum,
    )

    lut = resolve_lut_for_atlas(str(atlas_path))
    stats = compute_segstats(str(atlas_path), lut)
    write_segstats_sum(stats, str(labels_path))
    logger.info(f"Wrote {len(stats)} labels: {labels_path}")


def write_derived_outputs(mri_dir: Path, *, logger) -> None:
    """Write the NIfTI copy and label sidecar next to FastSurfer's ``.mgz``.

    Split out of :func:`run_fastsurfer` so a project whose segmentation was
    produced by an earlier run (or by hand) can be brought up to the layout
    the atlas readers expect without re-running the network.

    Raises
    ------
    PreprocessError
        If *mri_dir* holds no :data:`SEG_FILENAME`.
    """
    seg_path = mri_dir / SEG_FILENAME
    if not seg_path.is_file():
        raise PreprocessError(f"FastSurfer segmentation not found at {seg_path}.")

    nifti_path = mri_dir / SEG_NIFTI_FILENAME
    if not nifti_path.is_file():
        _write_nifti_copy(seg_path, nifti_path, logger=logger)

    labels_path = mri_dir / SEG_LABELS_FILENAME
    if not labels_path.is_file():
        _write_labels_sidecar(seg_path, labels_path, logger=logger)


def run_fastsurfer(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
    threads: int | None = None,
) -> None:
    """Run FastSurfer ``--seg_only`` for one subject.

    Writes ``derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep.mgz``
    plus a ``.nii.gz`` copy and a ``*_labels.txt`` sidecar, then returns.
    Idempotent: an existing segmentation is left alone (only the derived
    NIfTI/labels are backfilled if missing).

    The input is the **raw BIDS T1w**, the same image ``recon-all`` was
    given. Two reasons, both load-bearing: it keeps this stage independent
    of ``charm`` so the two can run in parallel after DICOM import (the DAG
    in :mod:`tit.jobs.plans` relies on that), and it is the image the
    spike's Dice numbers were measured on -- ``m2m_<id>/T1.nii.gz`` is
    charm's own bias-corrected, re-conformed volume, a different input with
    unmeasured effect on the network's output.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger used for progress and streamed command output.
    runner : CommandRunner or None, optional
        Subprocess runner used to stream output and honour cancellation.
    threads : int or None, optional
        Thread count for the inference. Defaults to
        ``$TIT_FASTSURFER_THREADS``, else :data:`DEFAULT_THREADS`.

    Raises
    ------
    PreprocessError
        If FastSurfer is not installed, no T1w is found, ``run_fastsurfer.sh``
        exits non-zero, or the expected segmentation is missing afterwards.

    See Also
    --------
    fastsurfer_available : Probe before offering this step in a UI.
    tit.pre.charm.run_charm : The other post-import stage (G2a).
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_FASTSURFER):
        pm = get_path_manager(project_dir)

        subject_dir = Path(pm.fastsurfer_subject(subject_id))
        mri_dir = Path(pm.fastsurfer_mri(subject_id))
        seg_path = mri_dir / SEG_FILENAME

        if seg_path.is_file():
            logger.info(
                f"FastSurfer segmentation already exists at {seg_path}; skipping."
            )
            write_derived_outputs(mri_dir, logger=logger)
            return

        script = fastsurfer_script()
        if script is None:
            raise _missing_fastsurfer_error()

        t1_file, _t2_file = _find_anat_files(subject_id)
        if not t1_file:
            bids_anat_dir = Path(pm.bids_anat(subject_id))
            raise PreprocessError(f"No T1 file found in {bids_anat_dir}")

        subjects_root = subject_dir.parent
        subjects_root.mkdir(parents=True, exist_ok=True)

        n_threads = resolve_threads(threads)
        cmd = [
            str(script),
            "--seg_only",
            # The image runs FastSurfer as root (the container's only user) and
            # run_fastsurfer.sh 2.x refuses that outright ("pass --allow_root")
            # -- the pre_fastsurfer smoke row failed on exactly this line.
            "--allow_root",
            "--no_cereb",
            "--no_hypothal",
            # Mandatory: see the module docstring's spike note.
            "--no_cc",
            "--sid",
            f"sub-{subject_id}",
            "--sd",
            str(subjects_root),
            "--t1",
            str(t1_file),
            "--device",
            "cpu",
            "--threads",
            str(n_threads),
            "--py",
            fastsurfer_python(),
        ]

        logger.info(
            f"Running FastSurfer seg_only for subject {subject_id} "
            f"({n_threads} threads, cpu)"
        )
        if runner is None:
            runner = CommandRunner()
        exit_code = runner.run(cmd, logger=logger)

        if exit_code != 0:
            raise PreprocessError(
                f"FastSurfer failed for subject {subject_id} (exit {exit_code})."
            )

        if not seg_path.is_file():
            raise PreprocessError(
                f"FastSurfer reported success but {seg_path} was not written."
            )

        write_derived_outputs(mri_dir, logger=logger)
