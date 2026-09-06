"""``/api/tetravox`` — install, activate and remove the embedded viewer bundle.

The mechanism the maintainer asked for: *"a system where we do not need to
release a new version every time Tetravox updates"*.  A Tetravox release is
installed into a writable root at runtime and served immediately at
``/tetravox/``; nothing about it requires a TI-Toolbox release, because this
build pins a protocol **range** and named features rather than a version
(:mod:`tit.tetravox.protocol`).

Five routes, and the shape of each is the safety story:

- ``GET /api/tetravox`` — active bundle + why, everything installed, the baked
  floor, the supported range.  A pure read; no network.
- ``GET /api/tetravox/updates`` — the release index (the GitHub Releases API,
  A2), from the cache unless ``?refresh=true``.  Answers ``available: false``
  with a sentence when it cannot be reached: being offline is a state to render,
  not a 500 to retry.
- ``POST /api/tetravox/policy`` — ``{auto_update}`` (A3), the only switch.
- ``POST /api/tetravox/install`` — ``{url, sha256}`` or ``{version}`` resolved
  from the index.  Verified before unpacking, extracted traversal-safe,
  activated atomically (:mod:`tit.tetravox.install`).
- ``POST /api/tetravox/activate`` — ``{version}``, or ``"baked"`` to roll back to
  the copy in the image.  This is what makes a bad update recoverable without
  deleting the evidence.
- ``DELETE /api/tetravox/{version}`` — remove an installed bundle.

**Every write here starts at a request a user made in Settings.**  The one thing
that acts on its own is the background policy in :mod:`tit.tetravox.updates`
(A3, started by ``tit.server.app``'s lifespan): it installs only a release whose
protocol is inside this build's range, and only while ``auto_update`` is on --
which this module's ``/policy`` route is what turns off.

Import-time work: none (a route module that does work at import takes the whole
server down under ``--reload`` when it fails; see
``dev/notes/v3-scene-ia-plan.md`` §6 F1).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from tit.server.schemas import (
    ProtocolRange,
    TetravoxRelease,
    TetravoxState,
    TetravoxUpdate,
    TetravoxUpdateOutcome,
    TetravoxUpdates,
)
from tit.tetravox import install as tvx_install
from tit.tetravox import protocol as tvx_protocol
from tit.tetravox import store as tvx_store
from tit.tetravox import updates as tvx_updates

router = APIRouter()


def _root(request: Request) -> str:
    settings = request.app.state.settings
    return tvx_store.install_root(getattr(settings, "tetravox_install_root", None))


def _as_release(
    release: tvx_store.EmbedRelease, *, active_path: str | None
) -> TetravoxRelease:
    return TetravoxRelease(
        version=release.version,
        protocol=release.protocol,
        source=release.source,
        path=release.path,
        name=release.name,
        sha=release.sha,
        features=list(release.features),
        compatible=release.compatible,
        active=release.path == active_path,
    )


def _state(request: Request) -> TetravoxState:
    """The whole picture in one read — what Settings renders."""
    settings = request.app.state.settings
    root = _root(request)
    resolution = tvx_store.resolve_from_settings(settings)
    active_path = resolution.path
    baked_dir = getattr(settings, "tetravox_embed_dir", None)
    baked = tvx_store.describe(baked_dir, "baked") if baked_dir else None
    return TetravoxState(
        active=(
            _as_release(resolution.release, active_path=active_path)
            if resolution.release
            else None
        ),
        reason=resolution.reason,
        installed=[
            _as_release(r, active_path=active_path)
            for r in tvx_store.list_installed(root)
        ],
        baked=_as_release(baked, active_path=active_path) if baked else None,
        supported=ProtocolRange(**tvx_protocol.supported_range()),
        install_root=root,
        index_url=tvx_updates.release_index_url(),
        auto_update=tvx_updates.read_policy(root),
    )


@router.get(
    "/api/tetravox",
    response_model=TetravoxState,
    summary="The active embed bundle, everything installed, and the supported range",
)
def get_tetravox(request: Request) -> TetravoxState:
    return _state(request)


@router.get(
    "/api/tetravox/updates",
    response_model=TetravoxUpdates,
    summary="Check the release index for installable embed bundles",
)
def get_tetravox_updates(request: Request, refresh: bool = False) -> TetravoxUpdates:
    """The cached answer unless ``?refresh=true`` -- "Check now" is the refresh.

    A read of this route never costs a GitHub request on its own: the cache is
    what the background check (A3) writes, and an unauthenticated IP gets 60
    requests an hour.  A user pressing "Check now" is a request they made, so it
    passes ``refresh=true`` and the ETag makes an unchanged index nearly free.
    """
    root = _root(request)
    installed = {r.version for r in tvx_store.list_installed(root)}
    result = tvx_updates.check(root, force=refresh)
    outcome = tvx_updates.read_outcome(root)
    return TetravoxUpdates(
        available=result.available,
        message=result.message,
        index_url=result.index_url,
        auto_update=tvx_updates.read_policy(root),
        checked_at=result.checked_at,
        from_cache=result.from_cache,
        last_outcome=TetravoxUpdateOutcome(**outcome) if outcome else None,
        releases=[
            TetravoxUpdate(
                **entry,
                compatible=tvx_protocol.protocol_supported(entry["protocol"]),
                installed=entry["version"] in installed,
            )
            for entry in result.releases
        ],
    )


@router.post(
    "/api/tetravox/policy",
    response_model=TetravoxState,
    summary="Turn automatic viewer updates on or off",
    responses={400: {"description": "`auto_update` is not a boolean"}},
)
def post_tetravox_policy(body: dict[str, Any], request: Request) -> TetravoxState:
    """A3's switch.  Off means *check and report*, never *stop knowing*."""
    auto_update = body.get("auto_update")
    if not isinstance(auto_update, bool):
        raise HTTPException(status_code=400, detail="`auto_update` must be a boolean")
    tvx_updates.write_policy(_root(request), auto_update)
    return _state(request)


def _resolve_from_index(version: str) -> tuple[str, str]:
    """``(url, sha256)`` for *version* from the release index."""
    try:
        entries = tvx_updates.fetch_release_index()
    except tvx_install.InstallError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    for entry in entries:
        if entry["version"] == version:
            return entry["url"], entry["sha256"]
    raise HTTPException(
        status_code=404,
        detail=f"The release index has no version {version}",
    )


@router.post(
    "/api/tetravox/install",
    response_model=TetravoxState,
    summary="Download, verify and activate an embed bundle",
    responses={
        400: {
            "description": "bad digest, bad manifest, unsupported protocol, "
            "or a host off the allowlist"
        },
        502: {"description": "the download or the release index could not be reached"},
    },
)
def post_tetravox_install(body: dict[str, Any], request: Request) -> TetravoxState:
    url = body.get("url")
    sha256 = body.get("sha256")
    version = body.get("version")
    if not url:
        if not isinstance(version, str) or not version:
            raise HTTPException(
                status_code=400,
                detail="Give either {url, sha256} or {version} from the release index",
            )
        url, sha256 = _resolve_from_index(version)
    if not isinstance(url, str):
        raise HTTPException(status_code=400, detail="`url` must be a string")
    try:
        tvx_install.install_from_url(url, root=_root(request), sha256=sha256)
    except tvx_install.InstallError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return _state(request)


@router.post(
    "/api/tetravox/activate",
    response_model=TetravoxState,
    summary='Activate an installed version, or "baked" to roll back to the image',
    responses={400: {"description": "no version given"}},
)
def post_tetravox_activate(body: dict[str, Any], request: Request) -> TetravoxState:
    version = body.get("version")
    if not isinstance(version, str) or not version:
        raise HTTPException(status_code=400, detail="`version` is required")
    try:
        tvx_store.activate(_root(request), version)
    except tvx_store.StoreError as exc:
        # 404, not 400: the request is well formed, the version simply is not here.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _state(request)


@router.delete(
    "/api/tetravox/{version}",
    response_model=TetravoxState,
    summary="Remove an installed embed bundle",
)
def delete_tetravox_version(version: str, request: Request) -> TetravoxState:
    try:
        tvx_store.remove_version(_root(request), version)
    except tvx_store.StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _state(request)
