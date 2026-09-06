"""``/api/view/{kind}`` and ``/api/view/args`` (v1).

The ViewSpec is built entirely in :mod:`tit.viewspec` (layer rules, LUT
lookups, the six audit-bug fixes, percentile resolution, the Tetravox
``ViewSpec`` v2 ``scene`` document); this module only maps the query params
to ``build_view``.

D3 (``dev/notes/v3-docker-streamline-plan.md``): the external Freeview/Gmsh
launch routes (``POST /api/viewers/freeview``, ``POST /api/viewers/gmsh``),
``_require_x11`` and the ``viewer`` job-kind submission they drove are
**removed** -- viewing is the Tetravox embed rendered client-side from
``ViewSpec.scene`` (served at ``/tetravox/`` by :mod:`tit.server.static`),
which needs no X11 and launches nothing server-side. ``freeview_args``
itself stays on the response for one release (deprecated) so an old client
mid-migration does not break; :func:`view_args` still exists to preview it.

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

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from tit import viewspec
from tit.server.schemas import ViewSpec

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
