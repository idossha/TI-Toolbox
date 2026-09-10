"""``/api/files/*`` — jailed file reads and bounded custom-mask imports (v1).

Every route resolves its ``path`` against the project directory (all catalog
routes hand back absolute container paths already) and against the bundled
``resources/`` tree (atlases, electrode caps -- read-only reference data a
viewer may legitimately want, e.g. the MNI152 template), and refuses to
serve anything that resolves outside both. No path rule beyond that jail
check lives here; content comes from ``tit.catalog`` (reports) or is read
directly for generic artifacts, matching the other v1 route modules.
"""

from __future__ import annotations

import csv
import hashlib
import mimetypes
import os
import stat
from email.utils import formatdate
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from tit import catalog
from tit.paths import get_path_manager
from tit.viewspec import jail_roots, raw_jail_roots

router = APIRouter()
_MASK_UPLOAD_LIMIT = 64 * 1024 * 1024
_MASK_DECOMPRESSED_LIMIT = 512 * 1024 * 1024

# Own CSP for the sandboxed report iframe (TODO.md §2.6): reports embed
# inline <script>/<style> (tit/reporting/core/templates.py) and are derived
# from run data, so they never run in the app's own origin/CSP. The
# ``sandbox allow-scripts`` directive is enforced here, server-side --
# independent of the renderer's own iframe ``sandbox="allow-scripts"``
# attribute -- so the document gets an opaque origin (no cookies, no
# same-origin fetch back into the API) even if a viewer ever opens the URL
# directly rather than through the sandboxed iframe (ra_14 finding 6).
REPORT_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; sandbox allow-scripts"
)

# Extensions the browser could plausibly execute as a document (HTML) --
# these get the same server-side sandbox CSP as reports when served through
# /api/files/artifact, on top of the nosniff header every artifact response
# carries (ra_14 finding 6: a same-origin .html/.txt artifact previously had
# script-src 'self' and no nosniff, so it could <script src> back into the
# session-cookied API).
_HTML_ARTIFACT_EXTS = {".html", ".htm"}
ARTIFACT_HTML_CSP = "sandbox allow-scripts"

_ALLOWED_ARTIFACT_EXTS = {".pdf", ".png", ".csv", ".json", ".txt", ".html"}

# /api/files/raw is a deny list, not an allow list: the viewer must be able to
# fetch any volume/mesh/LUT the catalog names, and new formats keep arriving.
# What is refused is exactly what a browser could execute as a document in this
# origin -- everything else is opaque bytes behind nosniff + attachment.
_RAW_DENY_EXTS = (".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".mhtml")


def _etag(st: os.stat_result) -> str:
    """Quoted ETag over mtime+size, byte-identical to Starlette's own."""
    base = f"{st.st_mtime}-{st.st_size}"
    return f'"{hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()}"'


def _if_none_match(header: str | None, etag: str) -> bool:
    if not header:
        return False
    candidates = [part.strip() for part in header.split(",")]
    return "*" in candidates or etag in candidates


def _resolve_jailed(raw_path: str, roots: list[Path] | None = None) -> Path:
    """*raw_path* resolved and checked against the jail, or 403/404.

    Jail roots default to :func:`tit.viewspec.jail_roots` -- the same project
    + ``resources/`` boundary :mod:`tit.server.routes.viewers` enforces for
    layer/mesh paths, so there is exactly one definition of "inside the
    project" across both route modules. The raw route passes the narrower
    :func:`tit.viewspec.raw_jail_roots` instead.
    """
    try:
        resolved = os.path.realpath(raw_path)
    except OSError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail="Not found") from exc
    for root in roots or jail_roots():
        canonical_root = os.path.realpath(root)
        # Include the separator so a sibling such as project-copy cannot match.
        if resolved == canonical_root:
            if not os.path.isfile(canonical_root):
                raise HTTPException(status_code=404, detail="Not found")
            return Path(canonical_root)
        if resolved.startswith(canonical_root.rstrip(os.sep) + os.sep):
            if not os.path.isfile(resolved):
                raise HTTPException(status_code=404, detail="Not found")
            return Path(resolved)
    raise HTTPException(status_code=403, detail="Path escapes the project jail")


@router.get(
    "/api/files/report/{report_id:path}",
    summary="One generated HTML report, served with its own CSP for a sandboxed iframe",
)
def report(report_id: str) -> Response:
    pm = get_path_manager()
    path = catalog.find_report_path(pm, report_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown report id")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "content-security-policy": REPORT_CSP,
            "x-content-type-options": "nosniff",
        },
    )


@router.get(
    "/api/files/artifact",
    summary="One job/analysis artifact by path (pdf/png/csv/json/txt/html), jailed to the project",
)
def artifact(path: str = Query(...)) -> FileResponse:
    resolved = _resolve_jailed(path)
    ext = resolved.suffix.lower()
    if ext not in _ALLOWED_ARTIFACT_EXTS:
        raise HTTPException(
            status_code=403, detail="File type not servable as an artifact"
        )
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    headers = {"x-content-type-options": "nosniff"}
    if ext in _HTML_ARTIFACT_EXTS or media_type == "text/html":
        headers["content-security-policy"] = ARTIFACT_HTML_CSP
    return FileResponse(resolved, media_type=media_type, headers=headers)


def _raw_stream(fd: int, start: int, length: int, chunk: int = 256 * 1024):
    """Yield *length* bytes from *fd* starting at *start*, then close it."""
    with os.fdopen(fd, "rb", closefd=True) as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            data = handle.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _parse_range(header: str, size: int) -> tuple[int, int] | None | bool:
    """``(start, end)`` for a single satisfiable byte range.

    ``None`` -- no range to honour (serve the whole file, which RFC 9110
    always allows); ``False`` -- syntactically fine but unsatisfiable (416).
    Multi-range requests are answered with the full body rather than a
    ``multipart/byteranges``: nothing in this app asks for one.
    """
    value = header.strip().lower()
    if not value.startswith("bytes=") or "," in value:
        return None
    spec = value[len("bytes=") :].strip()
    first, _, last = spec.partition("-")
    try:
        if not first:  # bytes=-N -> the last N bytes
            suffix = int(last)
            if suffix <= 0:
                return False
            start, end = max(0, size - suffix), size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
    except ValueError:
        return None
    if start >= size or start < 0 or end < start:
        return False
    return start, min(end, size - 1)


_RAW_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"description": "raw file bytes", "content": {"*/*": {}}},
    206: {"description": "partial content", "content": {"*/*": {}}},
    304: {"description": "not modified (If-None-Match matched the ETag)"},
    403: {"description": "outside the jail, or a document-executable extension"},
    416: {"description": "requested range not satisfiable"},
}


@router.get(
    "/api/files/raw/{path:path}",
    summary="Raw bytes of one volume/mesh/LUT file for the in-app viewer, jailed to the project",
    response_class=Response,
    responses=_RAW_RESPONSES,
)
@router.head("/api/files/raw/{path:path}", include_in_schema=False)
def raw(
    request: Request,
    path: str,
    range_header: str | None = Header(None, alias="Range"),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    if_range: str | None = Header(None, alias="If-Range"),
) -> Response:
    """Stream one project file to the in-app viewer as opaque bytes.

    Unlike ``/api/files/artifact`` this is not restricted to the document
    extension allow-list -- the viewer needs ``.nii.gz``, ``.msh``,
    ``.msh.opt``, ``.gii``, ``*_LUT.txt``, ``.lut`` and friends, none of
    which that route will serve. The trade is the opposite response policy:
    every response is ``application/octet-stream`` with ``nosniff`` and
    ``attachment``, and the handful of extensions a browser could execute as
    a document in this origin are refused outright, so nothing served here
    can ever become a page.

    The URL *is* the file's absolute path minus its leading slash
    (``/api/files/raw/mnt/000/.../T1.nii.gz``) rather than a ``?path=``
    query, because the engine's loader takes the file name, the gzip
    decision and its volume-vs-mesh routing from the URL's last segment.

    Range/206, ``If-Range`` and ``ETag``/304 are supported so a large mesh
    can be resumed. No response ever carries a ``Content-Encoding``: a
    ``.nii.gz`` must reach the viewer still deflated (it inflates the stream
    itself), and an encoded body would break both ``Content-Length`` and
    ranges.

    This route is the whole reason the in-app viewer needs no X11 at all
    (D3, ``docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)``): it is served to a
    canvas inside the Tetravox embed's iframe, never to an external
    Freeview/Gmsh process -- there is no X11 capability left to gate.
    """
    resolved = _resolve_jailed("/" + path.lstrip("/"), roots=raw_jail_roots())
    lowered = resolved.name.lower()
    if any(lowered.endswith(ext) for ext in _RAW_DENY_EXTS):
        raise HTTPException(
            status_code=403,
            detail="File type not servable as raw data; use /api/files/artifact",
        )

    # Open once, with O_NOFOLLOW on the final component, and serve the bytes
    # of *that* file descriptor: the jail check and the read then cannot see
    # two different files, so a symlink swapped in after the check (the TOCTOU
    # window /api/files/artifact still has) cannot redirect the response.
    try:
        fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise HTTPException(status_code=404, detail="Not found")
    except BaseException:
        os.close(fd)
        raise

    size = st.st_size
    etag = _etag(st)
    headers = {
        "content-type": "application/octet-stream",
        "x-content-type-options": "nosniff",
        "content-disposition": f'attachment; filename="{resolved.name}"',
        "cache-control": "private, max-age=0, must-revalidate",
        "accept-ranges": "bytes",
        "etag": etag,
        "last-modified": formatdate(st.st_mtime, usegmt=True),
    }

    if _if_none_match(if_none_match, etag):
        os.close(fd)
        return Response(status_code=304, headers=headers)

    requested = range_header
    if requested and if_range and if_range.strip() != etag:
        requested = None  # the file changed under the client: send it whole
    start, end = 0, size - 1
    status_code = 200
    if requested:
        parsed = _parse_range(requested, size)
        if parsed is False:
            os.close(fd)
            return Response(
                status_code=416,
                headers={**headers, "content-range": f"bytes */{size}"},
            )
        if parsed is not None:
            start, end = parsed
            status_code = 206
            headers["content-range"] = f"bytes {start}-{end}/{size}"

    length = 0 if size == 0 else end - start + 1
    headers["content-length"] = str(length)
    if request.method == "HEAD":
        os.close(fd)
        return Response(status_code=status_code, headers=headers)
    return StreamingResponse(
        _raw_stream(fd, start, length), status_code=status_code, headers=headers
    )


@router.get("/api/files/text", summary="Tail of a text/log file, jailed to the project")
def text(
    path: str = Query(...), tail: int | None = Query(None, ge=1)
) -> PlainTextResponse:
    resolved = _resolve_jailed(path)
    with open(resolved, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if tail is not None:
        lines = lines[-tail:]
    return PlainTextResponse("".join(lines))


@router.get(
    "/api/files/csv", summary="A CSV file parsed into a table, jailed to the project"
)
def csv_file(path: str = Query(...)) -> dict:
    resolved = _resolve_jailed(path)
    with open(resolved, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {"columns": [], "rows": []}
    columns, *data = rows
    return {"columns": columns, "rows": data}


@router.post(
    "/api/files/mask",
    status_code=201,
    summary="Upload a custom NIfTI mask",
    responses={413: {"description": "Mask exceeds the size limit"}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def upload_mask(
    request: Request, name: str = Query(...), subject: str = Query(...)
) -> dict:
    """Store a validated mask under this subject; coordinate space is chosen per job."""
    import re
    import tempfile

    from starlette.concurrency import run_in_threadpool

    # Reserve 13 bytes for the collision-avoidance suffix within a 255-byte filename.
    if len(name) > 242 or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_. -]*\.nii(?:\.gz)?", name
    ):
        raise HTTPException(422, "Choose a .nii or .nii.gz file with a simple filename")
    pm = get_path_manager()
    if subject not in catalog.subject_ids(pm):
        raise HTTPException(404, "Unknown subject")
    directory = Path(pm.masks(subject)) / "imported"
    root = Path(pm.project_dir).resolve()
    if not directory.resolve().is_relative_to(root):
        raise HTTPException(403, "Mask directory escapes the project")
    directory.mkdir(parents=True, exist_ok=True)
    # Imports stay outside atlas autodiscovery: their coordinate space is explicit in the job.
    suffix = ".nii.gz" if name.endswith(".nii.gz") else ".nii"
    try:
        with tempfile.TemporaryDirectory(dir=directory) as scratch:
            uploaded = Path(scratch) / ("upload" + suffix)
            total = 0
            with uploaded.open("wb") as stream:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > _MASK_UPLOAD_LIMIT:
                        raise HTTPException(413, "Mask upload exceeds 64 MiB")
                    stream.write(chunk)
            destination = await run_in_threadpool(
                _finish_mask_upload, uploaded, Path(scratch), directory, name, suffix
            )
    except HTTPException:
        raise
    except (OSError, ValueError, EOFError) as exc:
        raise HTTPException(422, f"Invalid NIfTI mask: {exc}") from exc
    return {"path": str(destination)}


def _finish_mask_upload(
    uploaded: Path, scratch: Path, directory: Path, name: str, suffix: str
) -> Path:
    import gzip
    import uuid

    from tit.opt.masks import validate_mask

    plain = uploaded
    if suffix == ".nii.gz":
        plain = scratch / "mask.nii"
        total = 0
        with gzip.open(uploaded, "rb") as source, plain.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > _MASK_DECOMPRESSED_LIMIT:
                    raise HTTPException(413, "Decompressed mask exceeds 512 MiB")
                target.write(chunk)
    validate_mask(str(plain))
    stem = name[: -len(suffix)]
    destination = directory / f"{stem}-{uuid.uuid4().hex[:12]}{suffix}"
    uploaded.rename(destination)
    return destination
