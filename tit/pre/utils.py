"""
Utility helpers for the ``tit.pre`` package.

Provides subject discovery, BIDS directory scaffolding, dataset-description
management, subprocess execution with cancellation support, and shared
exception classes.

Public API
----------
discover_subjects
    Return sorted subject IDs found in a BIDS project tree.
check_m2m_exists
    Check whether a SimNIBS m2m directory exists.

See Also
--------
tit.pre : Package-level overview and convenience re-exports.
"""

import glob
import json
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from tit.paths import get_path_manager

DATASET_TEMPLATES = {
    "freesurfer": "freesurfer.dataset_description.json",
    "simnibs": "simnibs.dataset_description.json",
    "ti-toolbox": "ti-toolbox.dataset_description.json",
}


class PreprocessError(RuntimeError):
    """Raised when a preprocessing step fails.

    See Also
    --------
    PreprocessCancelled : Raised specifically when cancelled by a stop event.
    """


class PreprocessCancelled(RuntimeError):
    """Raised when a preprocessing run is cancelled via a stop event.

    See Also
    --------
    PreprocessError : General preprocessing failure.
    """


def discover_subjects(project_dir: str | None) -> list[str]:
    """Return sorted, deduplicated subject IDs found in a BIDS project tree.

    Returns an empty list when *project_dir* is ``None`` (project not
    configured).

    Discovery order:

    1. ``sourcedata/sub-*/T1w/`` or ``T2w/`` -- any subdir, NIfTI, DICOM,
       or supported DICOM archive (``.zip``, ``.tar``, ``.tar.gz``, ``.tgz``).
    2. ``sourcedata/sub-*/*.tgz`` (compressed bundles at top level).
    3. ``sub-*/anat/*T1w*.nii[.gz]`` or ``*T2w*.nii[.gz]`` at project root.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.

    Returns
    -------
    list[str]
        Sorted list of subject identifiers (without the ``sub-`` prefix).

    See Also
    --------
    check_m2m_exists : Check whether a subject's m2m directory exists.
    """
    if project_dir is None:
        return []

    found: list[str] = []

    sourcedata_dir = os.path.join(project_dir, "sourcedata")
    if os.path.exists(sourcedata_dir):
        for subj_dir in glob.glob(os.path.join(sourcedata_dir, "sub-*")):
            if os.path.isdir(subj_dir):
                t1w_dir = os.path.join(subj_dir, "T1w")
                t2w_dir = os.path.join(subj_dir, "T2w")

                supported_modality_files = (
                    ".dcm",
                    ".dicom",
                    ".zip",
                    ".tar",
                    ".tar.gz",
                    ".tgz",
                    ".json",
                    ".nii",
                    ".nii.gz",
                )
                has_valid_structure = (
                    (
                        os.path.exists(t1w_dir)
                        and (
                            any(
                                os.path.isdir(os.path.join(t1w_dir, d))
                                for d in os.listdir(t1w_dir)
                            )
                            or any(
                                f.lower().endswith(supported_modality_files)
                                for f in os.listdir(t1w_dir)
                            )
                        )
                    )
                    or (
                        os.path.exists(t2w_dir)
                        and (
                            any(
                                os.path.isdir(os.path.join(t2w_dir, d))
                                for d in os.listdir(t2w_dir)
                            )
                            or any(
                                f.lower().endswith(supported_modality_files)
                                for f in os.listdir(t2w_dir)
                            )
                        )
                    )
                    or any(f.endswith(".tgz") for f in os.listdir(subj_dir))
                )

                if has_valid_structure:
                    subject_id = os.path.basename(subj_dir).replace("sub-", "")
                    found.append(subject_id)

    for subj_dir in glob.glob(os.path.join(project_dir, "sub-*")):
        if os.path.isdir(subj_dir):
            subject_id = os.path.basename(subj_dir).replace("sub-", "")
            if subject_id in found:
                continue
            anat_dir = os.path.join(subj_dir, "anat")
            if os.path.exists(anat_dir):
                has_nifti = any(
                    f.endswith((".nii", ".nii.gz")) and ("T1w" in f or "T2w" in f)
                    for f in os.listdir(anat_dir)
                )
                if has_nifti:
                    found.append(subject_id)

    return sorted(found)


def check_m2m_exists(project_dir: str, subject_id: str) -> bool:
    """Return ``True`` if the SimNIBS m2m directory already exists.

    Checks for
    ``<project_dir>/derivatives/SimNIBS/sub-<subject_id>/m2m_<subject_id>``.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.

    Returns
    -------
    bool
        ``True`` if the m2m directory exists on disk.

    See Also
    --------
    discover_subjects : Find all subject IDs in a BIDS project.
    run_charm : Generate the m2m head mesh.
    """
    m2m_dir = os.path.join(
        project_dir,
        "derivatives",
        "SimNIBS",
        f"sub-{subject_id}",
        f"m2m_{subject_id}",
    )
    return os.path.exists(m2m_dir)


def _find_anat_files(subject_id: str) -> tuple[Path | None, Path | None]:
    """Find T1w and T2w anatomical NIfTI files for a subject."""
    pm = get_path_manager()
    bids_anat_dir = Path(pm.bids_anat(subject_id))

    t1_file = _find_nifti(bids_anat_dir, f"sub-{subject_id}_T1w")
    t2_file = _find_nifti(bids_anat_dir, f"sub-{subject_id}_T2w")

    return t1_file, t2_file


def _find_nifti(directory: Path, stem: str) -> Path | None:
    """Return the first ``.nii.gz`` or ``.nii`` file matching *stem*."""
    for ext in (".nii.gz", ".nii"):
        path = directory / f"{stem}{ext}"
        if path.exists():
            return path
    return None


def ensure_subject_dirs(project_dir: str, subject_id: str) -> None:
    """Create the standard BIDS directory scaffold for a subject."""
    pm = get_path_manager(project_dir)
    for modality in ("T1w", "T2w"):
        pm.ensure(pm.sourcedata_dicom(subject_id, modality))
    pm.ensure(pm.bids_anat(subject_id))
    pm.ensure(pm.freesurfer_subject(subject_id))
    pm.ensure(pm.sub(subject_id))
    pm.ensure(pm.ti_toolbox())


def _dataset_description_target(project_dir: str, dataset: str) -> Path:
    """Return the target path for a dataset_description.json file."""
    if dataset == "freesurfer":
        return (
            Path(project_dir)
            / "derivatives"
            / "freesurfer"
            / "dataset_description.json"
        )
    if dataset == "simnibs":
        return (
            Path(project_dir) / "derivatives" / "SimNIBS" / "dataset_description.json"
        )
    if dataset == "ti-toolbox":
        return (
            Path(project_dir)
            / "derivatives"
            / "ti-toolbox"
            / "dataset_description.json"
        )
    raise ValueError(f"Unknown dataset: {dataset}")


def ensure_dataset_descriptions(project_dir: str, datasets: Iterable[str]) -> None:
    """Create or update ``dataset_description.json`` for each dataset."""
    project_name = Path(project_dir).name
    today = date.today().strftime("%Y-%m-%d")
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / "resources" / "dataset_descriptions"

    for dataset in datasets:
        template_name = DATASET_TEMPLATES.get(dataset)
        if not template_name:
            continue
        template_path = assets_dir / template_name
        target_path = _dataset_description_target(project_dir, dataset)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if not target_path.exists():
            if template_path.exists():
                target_path.write_text(
                    template_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            else:
                target_path.write_text(
                    json.dumps(
                        {
                            "Name": f"{dataset} derivatives",
                            "BIDSVersion": "1.10.0",
                            "DatasetType": "derivative",
                            "SourceDatasets": [{"URI": ""}],
                            "DatasetLinks": {},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        payload = json.loads(target_path.read_text(encoding="utf-8"))

        uri_value = f"bids:{project_name}@{today}"
        source_datasets = payload.get("SourceDatasets")
        if isinstance(source_datasets, list) and source_datasets:
            if isinstance(source_datasets[0], dict):
                if not source_datasets[0].get("URI"):
                    source_datasets[0]["URI"] = uri_value
        elif "URI" in payload and not payload.get("URI"):
            payload["URI"] = uri_value

        dataset_links = payload.get("DatasetLinks")
        if isinstance(dataset_links, dict) and not dataset_links:
            payload["DatasetLinks"] = {project_name: "../../"}

        target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_logger(
    step_name: str,
    subject_id: str,
    project_dir: str,
    *,
    log_file: str | None = None,
    console: bool = True,
) -> logging.Logger:
    """Create a named logger with a file handler for a preprocessing step."""
    from tit.logger import add_file_handler

    pm = get_path_manager(project_dir)
    log_dir = pm.logs(subject_id)
    os.makedirs(log_dir, exist_ok=True)
    if log_file is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"{step_name}_{timestamp}.log")

    logger_name = f"tit.pre.{step_name}.{subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    return logging.getLogger(logger_name)


def _terminate_process(proc: subprocess.Popen) -> None:
    """Send SIGTERM to a subprocess and its process group."""
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


class CommandRunner:
    """Run subprocesses with cancellation and streaming log output.

    Wraps ``subprocess.Popen`` to stream stdout/stderr line-by-line to a
    logger while honouring a ``threading.Event`` for cancellation.

    Parameters
    ----------
    stop_event : threading.Event or None, optional
        Event that, when set, causes any running command to be terminated.
        A fresh event is created if ``None``.

    Attributes
    ----------
    stop_event : threading.Event
        The cancellation event.

    See Also
    --------
    PreprocessCancelled : Exception raised when a command is cancelled.
    """

    def __init__(self, stop_event: threading.Event | None = None) -> None:
        self.stop_event = stop_event or threading.Event()
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()

    def request_stop(self) -> None:
        """Signal cancellation and terminate all running processes."""
        self.stop_event.set()
        self.terminate_all()

    def terminate_all(self) -> None:
        """Terminate all tracked child processes."""
        with self._lock:
            procs = list(self._processes)
        for proc in procs:
            _terminate_process(proc)

    def run(
        self,
        cmd: Sequence[str],
        *,
        logger: logging.Logger,
        cwd: str | None = None,
        env: dict | None = None,
    ) -> int:
        """Execute *cmd* and stream its output to *logger*.

        Parameters
        ----------
        cmd : sequence of str
            Command and arguments.
        logger : logging.Logger
            Logger that receives each output line at INFO level.
        cwd : str or None, optional
            Working directory for the subprocess.
        env : dict or None, optional
            Environment variables for the subprocess.

        Returns
        -------
        int
            Process exit code.

        Raises
        ------
        PreprocessCancelled
            If ``stop_event`` is set before or during execution.
        ValueError
            If *cmd* is empty.
        """
        if self.stop_event.is_set():
            raise PreprocessCancelled("Pre-processing cancelled before command start.")

        if not cmd:
            raise ValueError("Command is empty.")

        logger.debug(f"Command: {' '.join(cmd)}")

        preexec_fn = os.setsid if os.name != "nt" else None
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
            preexec_fn=preexec_fn,
        )

        with self._lock:
            self._processes.add(proc)

        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if self.stop_event.is_set():
                        _terminate_process(proc)
                        raise PreprocessCancelled("Pre-processing cancelled.")
                    line = line.strip()
                    if line:
                        logger.info(line)
            returncode = proc.wait()
        finally:
            with self._lock:
                self._processes.discard(proc)

        return returncode
