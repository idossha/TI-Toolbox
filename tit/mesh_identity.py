"""Content identity for replaying recorded placements on their original head mesh."""

import hashlib
from pathlib import Path
import re


def sha256_file(path: Path) -> str:
    """Hash a file incrementally without holding a head mesh in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_subject_mesh(pm, subject: str, expected_sha256: str) -> Path:
    """Require the selected subject's confined mesh to match recorded bytes.

    The saved source path is provenance only, never an input to file access.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha256
    ):
        raise ValueError("Recorded head mesh SHA-256 is invalid.")
    path = (Path(pm.m2m(subject)) / f"{subject}.msh").resolve()
    if not path.is_relative_to(Path(pm.project_dir).resolve()):
        raise ValueError("Replay head mesh escapes the selected project.")
    if not path.is_file():
        raise ValueError("The recorded candidate's subject head mesh is missing.")
    if sha256_file(path) != expected_sha256:
        raise ValueError(
            "The subject head mesh has changed since candidate recording; replay is refused."
        )
    return path
