#!/usr/bin/env simnibs_python
"""
Shared utilities for pre-processing steps.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Sequence

from tit.core import get_path_manager
from tit.core.overwrite import (
    OverwritePolicy,
    get_overwrite_policy,
    should_overwrite_path as core_should_overwrite_path,
)
from tit import logger as logging_util


DATASET_TEMPLATES = {
    "freesurfer": "freesurfer.dataset_description.json",
    "simnibs": "simnibs.dataset_description.json",
    "ti-toolbox": "ti-toolbox.dataset_description.json",
}


class PreprocessError(RuntimeError):
    """Raised when a preprocessing step fails."""


class PreprocessCancelled(RuntimeError):
    """Raised when a preprocessing run is cancelled."""


def ensure_subject_dirs(project_dir: str, subject_id: str) -> None:
    pm = get_path_manager()
    pm.project_dir = project_dir
    for modality in ("T1w", "T2w"):
        pm.ensure_dir("sourcedata_dicom", subject_id=subject_id, modality=modality)
    pm.ensure_dir("bids_anat", subject_id=subject_id)
    pm.ensure_dir("freesurfer_subject", subject_id=subject_id)
    pm.ensure_dir("simnibs_subject", subject_id=subject_id)
    pm.ensure_dir("ti_toolbox")


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

        try:
            payload = json.loads(target_path.read_text(encoding="utf-8"))
        except Exception:
            continue

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
    debug: bool = False,
    console: bool = True,
    log_file: Optional[str] = None,
    callback: Optional[callable] = None,
) -> logging.Logger:
    pm = get_path_manager()
    pm.project_dir = project_dir
    log_dir = pm.path("ti_logs", subject_id=subject_id)
    os.makedirs(log_dir, exist_ok=True)
    if log_file is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"{step_name}_{timestamp}.log")

    logger = logging_util.get_logger(
        name=f"pre.{step_name}.{subject_id}",
        log_file=log_file,
        overwrite=False,
        console=console,
    )

    if debug:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setLevel(logging.DEBUG)

    if callback is not None:
        try:
            logging_util.add_callback_handler(logger, callback, level=logging.INFO)
        except Exception:
            pass

    try:
        logging_util.configure_external_loggers(
            ["simnibs", "mesh_io", "sim_struct", "TI"],
            parent_logger=logger,
        )
    except Exception:
        pass

    return logger


def should_overwrite_path(
    path: Path, *, policy: OverwritePolicy, logger: logging.Logger, label: str
) -> bool:
    return core_should_overwrite_path(path, policy=policy, logger=logger, label=label)


class CommandRunner:
    def __init__(self, stop_event: Optional[threading.Event] = None) -> None:
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
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
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
