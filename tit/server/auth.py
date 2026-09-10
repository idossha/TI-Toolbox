"""Authentication helpers: token → session cookie exchange, bearer/cookie checks.

The launcher calls ``/auth/session?token=…`` exactly once; the server mints a
random session id, remembers it in ``app.state.sessions`` and sets it as an
``HttpOnly; SameSite=Strict; Path=/`` cookie before redirecting to ``/``.
The cookie never carries the token itself, and a server restart forgets every
session (the UI then gets 401 and returns to the launcher).  Every other
``/api/*`` and ``/ws/*`` route accepts that cookie or
``Authorization: Bearer <token>`` (scripts).  ``POST /auth/logout`` forgets
the session and clears the cookie.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, WebSocket

from tit.server import COOKIE_NAME


def _token_matches(candidate: str | None, token: str) -> bool:
    if not candidate or not token:
        return False
    return secrets.compare_digest(candidate.encode("utf-8"), token.encode("utf-8"))


def _bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return credential.strip() or None


def new_session_id() -> str:
    """Random, unguessable session id (never derived from the token)."""
    return secrets.token_urlsafe(32)


def is_authorized(
    token: str,
    sessions: set[str],
    *,
    cookie: str | None,
    authorization: str | None,
) -> bool:
    """True if the cookie names a live session or the bearer credential matches."""
    if cookie and cookie in sessions:
        return True
    return _token_matches(_bearer(authorization), token)


# Methods that never change server state: a cookie alone is enough for these (CSRF only
# matters for a request that does something), matching the browser's own "safe method" notion.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _cookie_csrf_ok(request: Request) -> bool:
    """CSRF guard for a cookie-authenticated, state-changing request (ra_14 finding #7).

    ``SameSite=Strict`` does not stop another *same-site* localhost page (a different port —
    same site, different origin) from riding the session cookie into a mutating call, so this
    additionally requires the request to prove it came from this app's own origin. A real
    browser attaches ``Origin`` to every non-GET fetch/XHR regardless of same- or cross-origin,
    so requiring it here — rather than trusting :func:`origin_allowed`'s "no Origin at all"
    carve-out meant for curl/tests/scripts — costs the app's own renderer nothing. A script
    should use ``Authorization: Bearer`` (see :func:`require_auth`), which is exempt outright.
    """
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin is not None:
        return origin_allowed(
            origin,
            request.headers.get("host"),
            settings.dev_origins,
            secure=request.url.scheme == "https",
        )
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None:
        return sec_fetch_site == "same-origin"
    return False  # neither header present -- can't prove same-origin, so don't trust it


def require_auth(request: Request) -> None:
    """FastAPI dependency: 401 unless the request carries valid credentials.

    A matching ``Authorization: Bearer`` is always sufficient. A cookie is sufficient for a
    "safe" method outright, and for any other method only once :func:`_cookie_csrf_ok` also
    passes -- otherwise this is a 403, not a 401 (the credential is valid; the request is just
    not trusted to have come from this app).
    """
    state = request.app.state
    if _token_matches(
        _bearer(request.headers.get("authorization")), state.settings.token
    ):
        return
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and cookie in state.sessions:
        if request.method.upper() in _SAFE_METHODS or _cookie_csrf_ok(request):
            return
        raise HTTPException(
            status_code=403,
            detail="Cross-site request blocked: missing or foreign Origin",
        )
    raise HTTPException(status_code=401, detail="Unauthorized")


def origin_allowed(
    origin: str | None,
    host: str | None,
    dev_origins: tuple[str, ...] = (),
    *,
    secure: bool = False,
) -> bool:
    """WebSocket origin policy.

    Accepted: no ``Origin`` at all (curl, tests, scripts); an origin whose
    scheme matches the connection (``http`` for ``ws``, ``https`` for
    ``wss``) and whose ``host[:port]`` equals the request's ``Host`` header
    (same origin); or an exact entry of *dev_origins* (``--dev-origin`` /
    ``TIT_DEV_ORIGINS``, e.g. the Vite dev server).
    """
    if origin is None:
        return True
    if origin in dev_origins:
        return True
    parts = urlsplit(origin)
    if parts.scheme != ("https" if secure else "http") or not parts.netloc:
        return False
    return bool(host) and parts.netloc.lower() == host.lower()


def websocket_authorized(ws: WebSocket) -> bool:
    """Cookie, bearer header or ``?token=`` for WebSocket handshakes."""
    state = ws.app.state
    if is_authorized(
        state.settings.token,
        state.sessions,
        cookie=ws.cookies.get(COOKIE_NAME),
        authorization=ws.headers.get("authorization"),
    ):
        return True
    return _token_matches(ws.query_params.get("token"), state.settings.token)
