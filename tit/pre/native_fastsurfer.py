"""Project-scoped mailbox client for the optional macOS FastSurfer worker."""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
import uuid
from pathlib import Path

from tit.pre.utils import PreprocessCancelled, PreprocessError

_HEARTBEAT_SECONDS = 10
_POLL_SECONDS = 0.25


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise PreprocessError("Native FastSurfer path escapes the mounted project.")
    return resolved


def _read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > 16384:
            raise ValueError("message too large")
        result = json.loads(path.read_text())
        if not isinstance(result, dict):
            raise ValueError("expected an object")
        return result
    except (OSError, ValueError) as exc:
        raise PreprocessError(
            f"Invalid native FastSurfer message: {path.name}."
        ) from exc


def _session(root: Path, mailbox: Path) -> str | None:
    path = _inside(root, mailbox / "availability.json")
    if not path.exists():
        return None
    message = _read_json(path)
    session = message.get("session")
    timestamp = message.get("lastSeen")
    try:
        if not isinstance(session, str) or str(uuid.UUID(session)) != session:
            raise ValueError("invalid session")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ValueError("invalid heartbeat")
        age = time.time() - timestamp / 1000
        if message.get("version") != 1 or not math.isfinite(age):
            raise ValueError("invalid protocol")
    except (ValueError, AttributeError) as exc:
        raise PreprocessError(
            "Invalid native FastSurfer availability message."
        ) from exc
    if age < -_HEARTBEAT_SECONDS or age >= _HEARTBEAT_SECONDS:
        raise PreprocessError(
            "Native FastSurfer host is disconnected. Reconnect TI-Toolbox or disable "
            "native FastSurfer before retrying."
        )
    return session


def run_native_fastsurfer(
    project_dir: str,
    subject_id: str,
    input_path: str | Path,
    *,
    threads: int,
    logger: logging.Logger,
    stop_event: threading.Event,
) -> bool:
    """Run via an enabled host worker; return False only when it is not enabled.

    Only project-relative input and a bounded thread count cross the mailbox.
    Cancellation and host disconnection fail the job instead of retrying on CPU.
    """
    root = Path(project_dir).resolve()
    mailbox = _inside(root, root / "code/ti-toolbox/native-fastsurfer")
    session = _session(root, mailbox)
    if session is None:
        return False
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", subject_id):
        raise PreprocessError("Invalid native FastSurfer subject identifier.")
    if (
        isinstance(threads, bool)
        or not isinstance(threads, int)
        or not 1 <= threads <= 1024
    ):
        raise PreprocessError("Native FastSurfer threads must be between 1 and 1024.")
    candidate = Path(input_path)
    source = _inside(root, candidate if candidate.is_absolute() else root / candidate)
    if not source.is_file() or not source.name.lower().endswith((".nii", ".nii.gz")):
        raise PreprocessError(
            "Native FastSurfer requires an existing project NIfTI input."
        )
    if stop_event.is_set():
        raise PreprocessCancelled(
            "Pre-processing cancelled before native command start."
        )
    request_id = str(uuid.uuid4())
    requests = _inside(root, mailbox / "requests")
    requests.mkdir(parents=True, exist_ok=True)
    directory = _inside(root, requests / request_id)
    directory.mkdir()
    request = {
        "version": 1,
        "session": session,
        "id": request_id,
        "subject_id": subject_id,
        "threads": threads,
        "input_path": source.relative_to(root).as_posix(),
    }
    completed = False
    offset = 0
    heartbeat_at = 0.0
    try:
        temporary = directory / "request.tmp"
        temporary.write_text(json.dumps(request))
        (directory / "heartbeat.json").write_text(
            json.dumps({"lastSeen": time.time() * 1000})
        )
        heartbeat_at = time.monotonic()
        temporary.replace(directory / "request.json")
        logger.info("Running native FastSurfer on Apple GPU (CPU view aggregation).")
        while True:
            if time.monotonic() - heartbeat_at >= 2 or heartbeat_at == 0:
                heartbeat = _inside(root, directory / "heartbeat.tmp")
                heartbeat.write_text(json.dumps({"lastSeen": time.time() * 1000}))
                heartbeat.replace(_inside(root, directory / "heartbeat.json"))
                heartbeat_at = time.monotonic()
            if stop_event.is_set():
                raise PreprocessCancelled("Native FastSurfer cancelled.")
            log_path = _inside(root, directory / "stdout.log")
            if log_path.is_file():
                with log_path.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(262144)
                    offset = stream.tell()
                if chunk:
                    logger.info("%s", chunk.decode("utf-8", errors="replace").rstrip())
            result_path = _inside(root, directory / "result.json")
            if result_path.exists():
                result = _read_json(result_path)
                if result.get("ok") is not True:
                    raise PreprocessError(
                        f"Native FastSurfer failed: {str(result.get('error', 'invalid result'))[:2000]}"
                    )
                completed = True
                return True
            if _session(root, mailbox) != session:
                raise PreprocessError(
                    "Native FastSurfer host session ended or changed."
                )
            stop_event.wait(_POLL_SECONDS)
    finally:
        if not completed:
            _inside(root, directory / "cancel").touch()
