"""Utility helpers for the tit.pre package."""


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
    """Raised when a preprocessing step fails."""


class PreprocessCancelled(RuntimeError):
    """Raised when a preprocessing run is cancelled."""


def discover_subjects(project_dir: str) -> list[str]:
    """Return sorted, deduplicated subject IDs found in a BIDS project tree.

    Discovery order:
    1. sourcedata/sub-*/T1w/ or T2w/ — any subdir, NIfTI (.nii/.nii.gz), or .tgz
    2. sourcedata/sub-*/*.tgz (compressed bundles at top level)
    3. sub-*/anat/*T1w*.nii[.gz] or *T2w*.nii[.gz] at project root
    """
    found: list[str] = []

    sourcedata_dir = os.path.join(project_dir, "sourcedata")
    if os.path.exists(sourcedata_dir):
        for subj_dir in glob.glob(os.path.join(sourcedata_dir, "sub-*")):
            if os.path.isdir(subj_dir):
                t1w_dir = os.path.join(subj_dir, "T1w")
                t2w_dir = os.path.join(subj_dir, "T2w")

                has_valid_structure = (
                    (
                        os.path.exists(t1w_dir)
                        and (
                            any(
                                os.path.isdir(os.path.join(t1w_dir, d))
                                for d in os.listdir(t1w_dir)
                            )
                            or any(
                                f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
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
                                f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
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
    """Return True if the SimNIBS m2m directory for subject_id already exists.

    Path: <project_dir>/derivatives/SimNIBS/sub-<subject_id>/m2m_<subject_id>
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
    """Find T1 and T2 weighted anatomical NIfTI files.

    Looks for exact BIDS filenames produced by DICOM conversion:
    sub-{subject_id}_T1w.nii.gz and sub-{subject_id}_T2w.nii.gz
    """
    pm = get_path_manager()
    bids_anat_dir = Path(pm.bids_anat(subject_id))

    t1_file = bids_anat_dir / f"sub-{subject_id}_T1w.nii.gz"
    t2_file = bids_anat_dir / f"sub-{subject_id}_T2w.nii.gz"

    return (
        t1_file if t1_file.exists() else None,
        t2_file if t2_file.exists() else None,
    )


def ensure_subject_dirs(project_dir: str, subject_id: str) -> None:
    pm = get_path_manager(project_dir)
    for modality in ("T1w", "T2w"):
        pm.ensure(pm.sourcedata_dicom(subject_id, modality))
    pm.ensure(pm.bids_anat(subject_id))
    pm.ensure(pm.freesurfer_subject(subject_id))
    pm.ensure(pm.sub(subject_id))
    pm.ensure(pm.ti_toolbox())


def _dataset_description_target(project_dir: str, dataset: str) -> Path:
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
    def __init__(self, stop_event: threading.Event | None = None) -> None:
        self.stop_event = stop_event or threading.Event()
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()

    def request_stop(self) -> None:
        self.stop_event.set()
        self.terminate_all()

    def terminate_all(self) -> None:
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
