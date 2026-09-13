"""Versioned array caches for derived fields, with explicit input provenance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile
import numpy as np


def input_fingerprints(paths: list[str | Path]) -> list[dict[str, object]]:
    """Hash input bytes so edited files cannot silently reuse old projections."""
    records = []
    for raw in paths:
        path = Path(raw).resolve()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        records.append(
            {
                "path": str(path),
                "sha256": digest.hexdigest(),
                "bytes": path.stat().st_size,
            }
        )
    return records


def read_array_cache(
    path: str | Path, metadata: dict, required_fields: tuple[str, ...]
) -> dict[str, np.ndarray] | None:
    """Return a cache only when provenance and every requested field match."""
    try:
        with np.load(path, allow_pickle=False) as cache:
            if "_metadata_json" not in cache or not set(required_fields).issubset(
                cache.files
            ):
                return None
            if json.loads(str(cache["_metadata_json"].item())) != metadata:
                return None
            return {name: np.asarray(cache[name]) for name in required_fields}
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None


def write_array_cache(
    path: str | Path, arrays: dict[str, np.ndarray], metadata: dict
) -> None:
    """Atomically write arrays and JSON provenance without pickle objects."""
    target = Path(path)
    if "_metadata_json" in arrays:
        raise ValueError("_metadata_json is reserved for cache provenance")
    converted = {name: np.asarray(value) for name, value in arrays.items()}
    if any(value.dtype.hasobject for value in converted.values()):
        raise ValueError("Object arrays are not permitted in scientific caches")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=target.stem + "-", suffix=".npz", dir=target.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(
                stream, **converted, _metadata_json=json.dumps(metadata, sort_keys=True)
            )
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
