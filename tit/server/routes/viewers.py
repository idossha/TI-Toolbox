"""``/api/view/{kind}`` and ``/api/view/args`` (v1).

The ViewSpec is built entirely in :mod:`tit.viewspec` (layer rules, LUT
lookups, the six audit-bug fixes, percentile resolution, the Tetravox
``ViewSpec`` v2 ``scene`` document); this module only maps the query params
to ``build_view``.

D3 (``docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)``): the external Freeview/Gmsh
launch routes (``POST /api/viewers/freeview``, ``POST /api/viewers/gmsh``),
``_require_x11`` and the ``viewer`` job-kind submission they drove are
**removed** -- there is no X11 in this runtime. ``freeview_args`` itself
stays on the response for one release (deprecated) so an old client
mid-migration does not break; :func:`view_args` still exists to preview it.

V2 (``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``): viewing is the
**host-installed Tetravox desktop app**, not an embed served from this
origin. ``POST /api/view/open`` (bottom of this module) writes the scene
document that app opens; it still launches nothing server-side, because the
app it writes for is not on this side of the container boundary.

Electrode overlay creation (v1 gap, ``pages/viewer/PARITY.md`` #1): the
Viewer page's "Create/refresh electrode overlay" action is not a viewer
launch -- it is a ``tools`` job that runs
``tit.tools.electrode_overlay`` as a plain module invocation
(``tit/jobs/kinds.py``'s ``tools`` branch: ``simnibs_python -m <module>
*args``), the same way any other standalone ``tit.tools.*`` script would be
run. The client submits::

    POST /api/jobs
    {
      "kind": "tools",
      "config": {
        "module": "tit.tools.electrode_overlay",
        "args": [
          "<sim_dir>/documentation/config.json",
          "<m2m_dir>/T1.nii.gz",
          "<sim_dir>/<TI|mTI>/montage_imgs/electrode_overlay_subject.nii.gz"
        ]
      },
      "subject_ids": ["<id>"]
    }

(see ``tit/tools/electrode_overlay.py::main`` for the exact positional
``config``/``reference``/``output`` argv and the optional ``--montage``/
``--eeg-positions-dir`` flags). Once that job succeeds,
``GET /api/catalog/electrode-overlays?subject=&simulation=``
(``tit.catalog.electrode_overlays``) reports the resulting file's
presence/path per TI/mTI mode -- ``tit.viewspec._electrode_overlay_layer``
already builds the ViewSpec layer for it once the file exists on disk, so no
viewspec change was needed for the *viewing* half of this gap, only the
*listing* half.
"""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request

from tit import viewspec
from tit.catalog import classify_view_file
from tit.server.schemas import ViewerOpen, ViewSpec

router = APIRouter()


def _jail_viewspec_layers(spec: dict[str, Any]) -> None:
    """Resolve every layer's ``path`` against :func:`viewspec.jail_roots`, in place.

    ``spec`` (``body.viewspec``) is client-supplied at preview time -- a
    layer's ``path`` is not necessarily one this server generated, so it
    must be re-jailed here exactly like any other externally-supplied file
    path, not trusted just because it arrived inside a ``ViewSpec`` shape
    (ra_14 finding 11). The raw string is replaced with its resolved
    absolute form so a later symlink swap can't matter, and so every
    resulting Freeview arg is guaranteed to start with ``/`` -- never ``-``.
    """
    for layer in spec.get("layers", []):
        raw = layer.get("path")
        resolved = viewspec.resolve_jailed(raw) if isinstance(raw, str) else None
        if resolved is None:
            raise HTTPException(
                status_code=403,
                detail=f"Layer path escapes the project/resources jail: {raw!r}",
            )
        layer["path"] = str(resolved)


def _reject_option_like_args(args: list[str]) -> None:
    """Refuse any argv entry that looks like a flag (ra_14 finding 11).

    Every argument this route ever builds comes from
    :func:`viewspec.to_freeview_args` (one
    ``<jailed-absolute-path>:key=value...`` string per layer) -- always
    starts with ``/`` once jailed. A leading ``-`` can therefore only mean a
    layer path was not actually resolved through the jail (a bug here);
    refuse rather than let a malformed argv reach a client-side launcher.
    """
    for arg in args:
        if arg.startswith("-"):
            raise HTTPException(
                status_code=422,
                detail=f"Refusing option-like viewer argument: {arg!r}",
            )


@router.get(
    "/api/view/{kind}",
    summary="Build a declarative ViewSpec for something to view",
    response_model=ViewSpec,
)
def view(
    kind: str,
    subject: str | None = Query(None),
    simulation: str | None = Query(None),
    space: str | None = Query(None),
    field: str | None = Query(None),
    analysis: str | None = Query(None),
    atlas: str | None = Query(
        None,
        description=(
            "Which atlas overlay to build (R5). An id from "
            "GET /api/catalog/atlases for the same subject and space, or a "
            "bundled MNI atlas basename. Absent keeps the server's own "
            "choice, which is what every caller did before this parameter "
            "existed; an unknown id falls back to that same choice."
        ),
    ),
    roi: str | None = Query(None),
    path: str | None = Query(None),
) -> dict[str, Any]:
    spec = viewspec.build_view(
        kind,
        subject=subject,
        simulation=simulation,
        space=space,
        field=field,
        analysis=analysis,
        atlas=atlas,
        roi=roi,
        path=path,
    )
    if spec is None:
        raise HTTPException(
            status_code=404, detail="Unknown subject/simulation/analysis"
        )
    return spec


@router.post(
    "/api/view/args",
    summary="The exact Freeview argv/command and Tetravox scene for a (possibly edited) ViewSpec",
)
def view_args(body: dict[str, Any]) -> dict[str, Any]:
    """``{viewspec}`` -> ``{freeview_args, freeview_command, scene}``.

    Exists so the Viewer page's "preview command" panel can show the *real*
    command -- generated by the same :func:`viewspec.to_freeview_args` a
    launch would use, on the same jailed/percentile-resolved spec -- instead
    of a hand-rolled TypeScript mirror that can (and did) drift from the
    server's actual argument grammar (ra_13 finding 9). Read-only: this
    never submits a job and launches nothing; layer paths are jailed but
    nothing runs.
    """
    spec = body.get("viewspec")
    if not isinstance(spec, dict):
        raise HTTPException(status_code=422, detail="body.viewspec is required")
    _jail_viewspec_layers(spec)
    viewspec.resolve_percentiles(spec)
    # The same finishing step GET /api/view/{kind} runs, so an edited spec's
    # argv and its scene can never be built by two different sets of rules.
    viewspec.finish_spec(spec)
    args = spec["freeview_args"]
    _reject_option_like_args(args)
    return {
        "freeview_args": args,
        "freeview_command": ["freeview"] + args,
        "scene": spec["scene"],
    }


# ---------------------------------------------------------------------------
# V2 -- the scene file the host-installed Tetravox desktop app opens.
#
# The embed is retired (docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer), V4):
# nothing renders a viewer inside this app any more, and this container has no
# display to render one in.  Viewing is the Tetravox *desktop app* on the host,
# which the maintainer already installs and which auto-updates itself.  This
# server's whole part in that is to put a scene document where that app can
# open it.
#
# Two facts shape everything below.
#
# 1. **The app reads files, not URLs.**  ``to_tetravox_viewspec`` writes every
#    ``DatasetRef.path`` as ``/api/files/raw/<abs path>`` because the embed
#    fetched its bytes back through this origin.  A desktop app on the host
#    opens ``/Users/me/datasets/000/...`` instead, so every dataset and sidecar
#    path is rewritten here -- container path out of the URL, then container
#    root -> host root.  A scene whose host root is unknowable is still written
#    (the caller may only want to download it), with ``host_path: null`` saying
#    so.
#
# 2. **The extension is ``.tetravox.json``, not ``.tvx.json``.**  Measured in
#    the Tetravox repo at 0.3.11: ``packages/app/src/main/menu.ts::isScenePath``
#    is ``/\.tetravox\.json$/i`` and ``electron-builder.yml`` registers exactly
#    that compound extension as the app's owned document type.  Any other
#    suffix is classified as *data* and the app tries to read the JSON as a
#    volume -- the plan's working name ``<name>.tvx.json`` would have failed
#    that way, silently, at the last step.
# ---------------------------------------------------------------------------

_SCENE_SUFFIX = ".tetravox.json"

#: One file per view kind, overwritten on every Open.  A timestamped name per
#: click would leave a directory nobody ever cleans up inside the user's own
#: project; the scene is a derived artefact of the current selection, not a
#: record of it.
_SCENE_NAMES = {
    "subject": "subject",
    "simulation": "simulation",
    "analysis": "analysis",
    "group": "group",
    "custom": "custom",
}


def viewer_scene_dir() -> str:
    """``<project>/code/ti-toolbox/viewer/`` -- sibling of ``config/`` and ``jobs/``."""
    from tit.paths import get_path_manager

    return os.path.join(os.path.dirname(get_path_manager().config_dir()), "viewer")


def _container_path_from_raw_url(url: str) -> str | None:
    """``/api/files/raw/mnt/000/x.nii.gz`` -> ``/mnt/000/x.nii.gz``; anything else -> ``None``."""
    if not isinstance(url, str) or not url.startswith(viewspec.RAW_ROUTE_PREFIX):
        return None
    return "/" + unquote(url[len(viewspec.RAW_ROUTE_PREFIX) :])


def _to_host(container_path: str, container_root: str, host_root: str) -> str:
    """``container_path`` re-rooted onto the host, keeping the *host's* separator.

    A Windows host's project root is ``C:\\Users\\me\\data`` while every path
    this server produces is POSIX, so the remainder is translated rather than
    concatenated -- the same rule :func:`tit.server.host_path._join_host` uses
    for the project root itself.
    """
    root = container_root.rstrip("/")
    if container_path == root:
        remainder = ""
    elif container_path.startswith(root + "/"):
        remainder = container_path[len(root) :]
    else:
        return container_path
    if not remainder:
        return host_root
    if "\\" in host_root and "/" not in host_root:
        return host_root.rstrip("\\") + remainder.replace("/", "\\")
    return host_root.rstrip("/") + remainder


def localise_scene_paths(
    scene: dict[str, Any], container_root: str, host_root: str | None
) -> dict[str, Any]:
    """Every dataset/sidecar URL in *scene* rewritten to a filesystem path.

    Returns a new document; *scene* is not mutated (the same object is still
    the response body of ``GET /api/view/{kind}``, where the URL form is
    correct).  With no *host_root* the container path is used, which is right
    for a browser-mode download opened on a machine that mounts the project at
    the same place, and honest everywhere else -- Tetravox says which file it
    could not find.
    """

    def localise(url: Any) -> Any:
        container = _container_path_from_raw_url(url)
        if container is None:
            return url
        if host_root is None:
            return container
        return _to_host(container, container_root, host_root)

    out = copy.deepcopy(scene)
    for dataset in out.get("datasets", []):
        if not isinstance(dataset, dict):
            continue
        for key in ("path", "absPath"):
            if key in dataset:
                dataset[key] = localise(dataset[key])
        for sidecar in (dataset.get("sidecars") or {}).values():
            if not isinstance(sidecar, dict):
                continue
            for key in ("path", "absPath"):
                if key in sidecar:
                    sidecar[key] = localise(sidecar[key])
    return out


def _scene_files(spec: dict[str, Any], localised: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per dataset the scene references -- the Viewer's editable list.

    Both path languages, because the row does two jobs: ``path`` is what the
    scene carries and what a person can check on their own machine, and
    ``container_path`` is what the client sends back in ``files`` when the row
    is kept, moved or joined by another (VM2).  A row that reported only the
    host path could not be handed back to a server that jails container paths.

    Layers and datasets are the same list in the same order
    (``to_tetravox_viewspec`` builds one dataset per layer, in order), so they
    are zipped rather than matched by basename -- two files with the same
    basename in different directories are ordinary here.

    Sizes come from the container's own paths, because that is where the bytes
    are.  A file that cannot be stat'ed reports ``bytes: null`` rather than 0:
    "unknown" and "empty" are different answers and only one is a problem.
    """
    rows: list[dict[str, Any]] = []
    for layer, dataset in zip(spec.get("layers", []), localised.get("datasets", [])):
        if not isinstance(dataset, dict):
            continue
        container = layer.get("path")
        path = dataset.get("path")
        if not isinstance(container, str) or not isinstance(path, str):
            continue
        try:
            size: int | None = os.path.getsize(container)
        except OSError:
            size = None
        rows.append(
            {
                "id": dataset.get("id"),
                "kind": dataset.get("kind"),
                "name": dataset.get("name") or os.path.basename(container),
                "path": path,
                "container_path": container,
                "bytes": size,
            }
        )
    return rows


#: `.../derivatives/SimNIBS/sub-<id>/...` -- the only place in a project where a path names whose
#: head it came out of. Files outside it (the bundled MNI template and atlases) belong to nobody
#: and are exempt below, which is deliberate: an MNI scene is *supposed* to mix them in.
_SUBJECT_IN_PATH = re.compile(r"/derivatives/SimNIBS/sub-([^/]+)/")


def _refuse_a_scene_that_spans_two_subjects(files: list[Any]) -> None:
    """422 naming both, rather than a picture that is wrong in a way no reader can see.

    Overlaying one person's field on another's anatomy produces a scene that looks entirely
    normal -- two brains, roughly head-shaped, roughly aligned -- and is a false result. There is
    no rendering artefact to notice and no warning to read; the only place it can be caught is
    here, before anything is drawn.

    It is a real path and not a hypothetical: the Viewer's "what will open" list survives a change
    of subject, so picking 101 after ernie kept ernie's rows in the list, and the real
    `viewer-open` spec first passed while measuring the wrong subject entirely
    (`desktop/tests/e2e/real/viewer-open.spec.ts`, the "one subject per scene" block). The client
    now re-scopes that list on a subject change; this is the rule that makes it not matter whether
    a client remembers to.
    """
    subjects: dict[str, str] = {}
    for raw in files:
        if not isinstance(raw, str):
            continue
        match = _SUBJECT_IN_PATH.search(raw)
        if match:
            subjects.setdefault(match.group(1), raw)
    if len(subjects) > 1:
        named = ", ".join(
            f"{sid} ({os.path.basename(path)})" for sid, path in sorted(subjects.items())
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"A scene cannot span two subjects: {named}. "
                "Choose one subject's files, or change subject and compose again."
            ),
        )


def _refuse_a_surface_this_embed_cannot_draw(
    request: Request | None, files: list[Any]
) -> None:  # noqa: D401
    """422 rather than send a cortical sheet as if it were a tetrahedral FEM mesh.

    Degrading to `kind: "mesh"` is the tempting alternative and it is the wrong one. A sheet sent
    as a mesh loads (it is a triangle-only mesh, and the engine will take it), so nothing fails --
    it simply comes back with a mesh's defaults: filled in 2D instead of outlined, capped clip
    planes for an object with no interior, and no way to attach the parcellation that was the
    reason for ticking it. The person gets a picture and no reason to doubt it.

    The Menu already disables these rows (`tit.viewspec._tree_node`), so a client that reads the
    tree never reaches this. It exists for the ones that do not: a saved composition from a newer
    embed, a deep link, a script.
    """
    from tit.server.routes.viewer_library import surfaces_supported

    # No request means no app to probe -- a direct call from a test or a script. Those are not the
    # caller this guard is for, and refusing them would be refusing on no evidence.
    if request is None or surfaces_supported(request):
        return
    offered = [
        raw
        for raw in files
        if isinstance(raw, str) and classify_view_file(raw) == "surface"
    ]
    if offered:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{viewspec.SURFACE_UNSUPPORTED_REASON}: "
                + ", ".join(sorted({os.path.basename(p) for p in offered}))
            ),
        )


@router.post(
    "/api/view/open",
    summary="Resolve a scene once: the embed ViewSpec, and the scene file on disk",
    response_model=ViewerOpen,
)
def view_open(
    body: dict[str, Any] | None = None,
    # Annotated bare `Request` (never `Request | None`): FastAPI reads the annotation to know this
    # is the request object and not a body field, and a union is not something it can special-case.
    # The `= None` is for the direct calls the tests make, which have no app to hand.
    request: Request = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """``{kind, subject, ...}`` -> ``{name, path, host_path, scene, view, files}``.

    Launches nothing, and never could: the server has no display (D3).  One
    resolution produces two addressings of the same scene --

    * ``view``  -- every dataset an ``/api/files/raw/...`` URL.  This is what
      the Viewer sub-page posts into the Tetravox embed's iframe, which fetches
      its bytes back through this origin.
    * ``scene`` -- the same document with every path re-rooted onto the host,
      also written to ``<project>/code/ti-toolbox/viewer/<kind>.tetravox.json``
      so the file can be opened by a desktop Tetravox or kept as a record of
      what was viewed.

    They come from one ``build_view`` call on purpose.  Two calls could resolve
    differently -- a job finishing between them is enough -- and then the list
    the page shows, the file on disk and the scene on screen would disagree
    about what is in the scene, with nothing to say which was right.
    """
    from tit.paths import get_path_manager
    from tit.server.host_path import host_project_dir

    payload = body or {}
    kind = str(payload.get("kind") or "")
    if kind not in _SCENE_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {', '.join(sorted(_SCENE_NAMES))}",
        )
    extras = payload.get("extras")
    overrides = payload.get("overrides")
    # VM2: the Viewer page is one editable "what will open" list. When the
    # client sends that list it is *authoritative* -- these datasets, this
    # order -- and the view type contributes only each kept file's default
    # layer settings. Absent, nothing changes for any caller.
    files = payload.get("files")
    if isinstance(files, list):
        _refuse_a_scene_that_spans_two_subjects(files)
        _refuse_a_surface_this_embed_cannot_draw(request, files)
    spec = viewspec.build_view(
        kind,
        subject=payload.get("subject"),
        simulation=payload.get("simulation"),
        space=payload.get("space"),
        field=payload.get("field"),
        analysis=payload.get("analysis"),
        atlas=payload.get("atlas"),
        roi=payload.get("roi"),
        path=payload.get("path"),
        extras=list(extras) if isinstance(extras, list) else None,
        overrides=overrides if isinstance(overrides, dict) else None,
        files=list(files) if isinstance(files, list) else None,
    )
    if spec is None:
        raise HTTPException(
            status_code=404, detail="Unknown subject/simulation/analysis"
        )
    scene = spec.get("scene")
    if not isinstance(scene, dict):
        raise HTTPException(
            status_code=404, detail="The server built no scene for this selection"
        )

    container_root = get_path_manager().project_dir or ""
    host_root = host_project_dir(container_root)
    localised = localise_scene_paths(scene, container_root, host_root)

    directory = viewer_scene_dir()
    name = f"{_SCENE_NAMES[kind]}{_SCENE_SUFFIX}"
    target = os.path.join(directory, name)
    dry_run = bool(payload.get("dry_run"))
    if not dry_run:
        os.makedirs(directory, exist_ok=True)
        # Written whole, then renamed: the app may be watching this exact path
        # from a previous Open, and half a JSON document is a parse error on
        # screen.
        tmp = f"{target}.partial"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(localised, handle, indent=1)
        os.replace(tmp, target)

    return {
        "name": name,
        "path": target,
        "host_path": (
            _to_host(target, container_root, host_root) if host_root else None
        ),
        "scene": localised,
        # The embed's own addressing, from the SAME resolution: `scene` is what
        # `build_view` produced (every dataset an /api/files/raw URL) and
        # `localised` is that document re-rooted onto the host. Returning both
        # is what lets the Viewer sub-page post a scene to the iframe and the
        # written file describe the same set of datasets, in the same order,
        # without a second call that could resolve differently in between.
        "view": scene,
        "files": _scene_files(spec, localised),
        "dry_run": dry_run,
    }


@router.get(
    "/api/viewer/candidates",
    summary="Every file this subject/simulation offers the Viewer's \"+ Add…\"",
)
def viewer_candidates(
    subject: str | None = Query(None),
    simulation: str | None = Query(None),
    space: str | None = Query(None),
) -> dict[str, Any]:
    """A read: it opens nothing and writes nothing.

    Only files a scene can actually use are listed (volumes and meshes), each
    with its size, because the point of the picker is to choose without
    guessing -- and one of these files is routinely 64 MB.
    """
    return {"candidates": viewspec.viewer_candidates(subject, simulation, space)}


# ---------------------------------------------------------------------------
# VM -- saved viewer selections.
#
# A composition panel is only worth its keystrokes if a person can get the
# same composition back.  These live beside the scene files, in the project,
# as plain JSON: ``<project>/code/ti-toolbox/viewer/presets/<slug>.json``.
# The project is the unit people copy, archive and share, so a preset that
# lived in browser storage would be lost exactly when the work it describes
# was passed on.
#
# The path is ``/api/viewer/presets``, not ``/api/view/presets``: the latter
# is shadowed by ``GET /api/view/{kind}``, which would answer "presets" with a
# 404 from ``build_view`` rather than a list -- a routing accident that would
# have looked like an empty preset list.
# ---------------------------------------------------------------------------

_PRESET_SUFFIX = ".json"


def viewer_preset_dir() -> str:
    return os.path.join(viewer_scene_dir(), "presets")


def _preset_slug(name: str) -> str:
    """A file name from a display name, or a 422.

    Deliberately strict rather than sanitising: a name that quietly becomes a
    different file is worse than a refusal, and every character kept here is
    one a person typed on purpose.
    """
    slug = "".join(c if (c.isalnum() or c in "-_ ") else "-" for c in name).strip()
    slug = slug.replace(" ", "_")
    if not slug or slug in (".", "..") or len(slug) > 80:
        raise HTTPException(status_code=422, detail=f"Unusable preset name: {name!r}")
    return slug


@router.get("/api/viewer/presets", summary="Saved Viewer selections")
def viewer_presets() -> dict[str, Any]:
    directory = viewer_preset_dir()
    out: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        names = []
    for entry in names:
        if not entry.endswith(_PRESET_SUFFIX):
            continue
        try:
            with open(os.path.join(directory, entry), encoding="utf-8") as handle:
                body = json.load(handle)
        except (OSError, ValueError):
            # A hand-edited or half-written preset is skipped, not fatal: one
            # bad file must not empty the menu.
            continue
        if not isinstance(body, dict):
            continue
        body.setdefault("name", entry[: -len(_PRESET_SUFFIX)])
        out.append(body)
    return {"presets": out}


@router.put("/api/viewer/presets/{name}", summary="Save one Viewer selection")
def save_viewer_preset(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    slug = _preset_slug(name)
    directory = viewer_preset_dir()
    os.makedirs(directory, exist_ok=True)
    document = dict(body or {})
    document["name"] = name
    target = os.path.join(directory, f"{slug}{_PRESET_SUFFIX}")
    tmp = f"{target}.partial"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
    os.replace(tmp, target)
    return document


@router.delete("/api/viewer/presets/{name}", summary="Forget one saved selection")
def delete_viewer_preset(name: str) -> dict[str, Any]:
    target = os.path.join(viewer_preset_dir(), f"{_preset_slug(name)}{_PRESET_SUFFIX}")
    try:
        os.remove(target)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No preset named {name!r}")
    return {"name": name, "deleted": True}
