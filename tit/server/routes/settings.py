"""``GET``/``PUT /api/settings`` (v1).

Two files, read-modify-write with an atomic replace on every write:

- ``telemetry.json`` (user-level config dir, unchanged schema/location --
  ``tit.telemetry.load_config``/``save_config``) for ``telemetry.{consented,
  enabled}``. ``consented`` maps to the existing ``consent_shown`` field
  (has the user been asked, regardless of answer); ``enabled`` is the
  existing field of that name.
- ``code/ti-toolbox/config/settings.json`` (project-level, new in v1 --
  no prior file covered this shape) for ``panels`` (replaces
  ``extensions.json``'s ``{"extensions": {name: bool}}`` with a plain enabled
  list), ``image_tag``, ``allow_unsafe_overrides``, and ``theme``.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from tit import telemetry
from tit.paths import get_path_manager

router = APIRouter()

_SETTINGS_FILENAME = "settings.json"
_DEFAULTS: dict[str, Any] = {
    "panels": [],
    "image_tag": None,
    "allow_unsafe_overrides": False,
    "theme": "system",
}

_VALID_THEMES: frozenset[str] = frozenset({"system", "light", "dark"})

# Every `PanelId` in `desktop/src/renderer/pages/panels/_shared.ts` -- kept in
# sync manually since panels are a renderer-only concept the server has no
# other source of truth for. An unknown id here would silently never appear
# in the nav (`app/registry.ts`), so it is rejected rather than persisted.
_VALID_PANELS: frozenset[str] = frozenset(
    {
        "source",
        "cluster-permutation",
        "nifti-group-average",
        "nilearn-visuals",
        "quick-notes",
        "visual-exporter",
    }
)


def _project_settings_path() -> str:
    return os.path.join(get_path_manager().config_dir(), _SETTINGS_FILENAME)


def _load_project_settings() -> dict[str, Any]:
    path = _project_settings_path()
    if not os.path.isfile(path):
        return dict(_DEFAULTS)
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULTS)
    return {**_DEFAULTS, **data}


def _save_project_settings(data: dict[str, Any]) -> None:
    path = _project_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Unique per call (pid + monotonic ns), not a fixed ".tmp" name -- two
    # concurrent PUTs no longer race each other's os.replace (ra_14 finding 14).
    tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _read_settings() -> dict[str, Any]:
    tconf = telemetry.load_config()
    project = _load_project_settings()
    return {
        "telemetry": {"consented": tconf.consent_shown, "enabled": tconf.enabled},
        # Panel ids no longer known are dropped rather than handed out. `subject-info` was a
        # panel until it was deleted on 2026-09-05, and any project whose settings.json still
        # names it got a document back that `PUT` then refused with 422 -- so the Settings page,
        # which is a read-modify-write of exactly this document, could not save at all. `GET`
        # must never return something `PUT` would reject.
        "panels": [p for p in project.get("panels", []) if p in _VALID_PANELS],
        "image_tag": project.get("image_tag"),
        "allow_unsafe_overrides": bool(project.get("allow_unsafe_overrides", False)),
        "theme": project.get("theme", "system"),
    }


@router.get(
    "/api/settings", summary="Server/project settings and app-level preferences"
)
def get_settings() -> dict[str, Any]:
    return _read_settings()


def _validate_theme(theme: Any) -> str:
    if theme not in _VALID_THEMES:
        raise HTTPException(
            status_code=422,
            detail=f"theme must be one of {sorted(_VALID_THEMES)}, got {theme!r}",
        )
    return theme


def _validate_panels(panels: Any) -> list[str]:
    if not isinstance(panels, list) or not all(isinstance(p, str) for p in panels):
        raise HTTPException(status_code=422, detail="panels must be a list of strings")
    unknown = sorted(set(panels) - _VALID_PANELS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown panel id(s) {unknown}; known panels: {sorted(_VALID_PANELS)}",
        )
    return panels


@router.put("/api/settings", summary="Replace server/project settings")
def put_settings(body: dict[str, Any]) -> dict[str, Any]:
    telemetry_body = body.get("telemetry") or {}
    if "enabled" in telemetry_body:
        # tit.telemetry.set_enabled also marks consent_shown=True, invalidates
        # the in-process cache, and fires the one-time first_open event --
        # exactly the GUI's "Settings -> Privacy toggle" semantics.
        telemetry.set_enabled(bool(telemetry_body["enabled"]))
    elif telemetry_body.get("consented"):
        tconf = telemetry.load_config()
        tconf.consent_shown = True
        telemetry.save_config(tconf)

    _save_project_settings(
        {
            "panels": _validate_panels(body.get("panels", [])),
            "image_tag": body.get("image_tag"),
            "allow_unsafe_overrides": bool(body.get("allow_unsafe_overrides", False)),
            "theme": _validate_theme(body.get("theme", "system")),
        }
    )
    return _read_settings()
