"""Route modules of ``tit.server``.

Every module in this package is discovered automatically (no edits to ``app.py`` needed when a
new module is added). A module may expose:

- ``router`` — an ``APIRouter`` mounted **behind** authentication (every ``/api/*`` route);
- ``ws_router`` — an ``APIRouter`` with WebSocket endpoints that authorise inside the handshake
  (see ``tit.server.ws.websocket_authorized``); mounted without the auth dependency.

``health`` is the only module mounted without authentication on purpose.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

OPEN_MODULES = ("health",)


def iter_route_modules() -> list[ModuleType]:
    """Import and return every route module in this package, sorted by name."""
    modules: list[ModuleType] = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        modules.append(importlib.import_module(f"{__name__}.{info.name}"))
    return modules
