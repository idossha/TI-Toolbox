"""TI-Toolbox job server (``tit.server``).

FastAPI application that runs inside the SimNIBS container and exposes the
toolbox to the Electron/browser UI over HTTP + WebSocket: the job engine,
project and catalog reads, plan/validate preflight, scene and viewer routes,
notebooks, settings and the live job/system streams.  Scientific and path
logic stays in ``tit`` (PathManager); this package is plumbing only.

Run with ``simnibs_python -m tit.server --project /mnt/<project>``.
"""

SERVER_API = "v0"
COOKIE_NAME = "tit_session"

__all__ = ["SERVER_API", "COOKIE_NAME"]
