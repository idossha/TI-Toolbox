"""``GET /api/version`` — version handshake."""

from __future__ import annotations

import hashlib
import platform
from importlib import metadata

from fastapi import APIRouter

import tit
from tit.server import SERVER_API
from tit.server.routes.schema import SCHEMA_PATH
from tit.server.schemas import Version

router = APIRouter()

# (mtime, hexdigest) — same cache-by-mtime shape as routes/schema.py's own cache, so a
# dev/build_schema.py rebuild is picked up without a server restart.
_schema_hash_cache: tuple[float, str] | None = None


def schema_hash() -> str:
    """sha256 (hex) of ``contracts/generated/config.schema.json``'s raw bytes; ``""`` if the file doesn't exist
    yet (a fresh checkout before ``dev/build_schema.py`` has ever run)."""
    global _schema_hash_cache
    try:
        mtime = SCHEMA_PATH.stat().st_mtime
    except OSError:
        return ""
    if _schema_hash_cache is None or _schema_hash_cache[0] != mtime:
        digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
        _schema_hash_cache = (mtime, digest)
    return _schema_hash_cache[1]


def simnibs_version() -> str | None:
    """Installed SimNIBS version from package metadata (never imports it)."""
    try:
        return metadata.version("simnibs")
    except metadata.PackageNotFoundError:
        return None


@router.get("/api/version", response_model=Version, summary="Version handshake")
def version() -> Version:
    return Version(
        tit_version=tit.__version__,
        server_api=SERVER_API,
        schema_hash=schema_hash(),
        python=platform.python_version(),
        simnibs=simnibs_version(),
    )
