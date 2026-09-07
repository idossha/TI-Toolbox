"""``simnibs_python -m tit.server`` — run the job server (or dump its OpenAPI).

Token hygiene: the shared secret reaches the server through ``--token`` or
``TIT_SERVER_TOKEN``.  Under ``--reload`` the resolved settings are handed to
the reloader's child through a 0600 JSON file named by
``TIT_SERVER_SETTINGS_FILE`` — never through ``TIT_SERVER_TOKEN`` in the
child's environment.  Job runners (Phase 3) must likewise scrub
``TIT_SERVER_TOKEN`` (and ``TIT_SERVER_SETTINGS_FILE``) from the environment
of every subprocess they spawn.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
import tempfile

from tit.logger import DATE_FORMAT, LOG_FORMAT, setup_logging
from tit.server.settings import (
    ENV_HOST,
    ENV_PORT,
    ENV_SETTINGS_FILE,
    ENV_TOKEN,
    ServerSettings,
    SettingsError,
    resolve_allow_hosts,
    resolve_dev_origins,
    resolve_project_dir,
    resolve_static_dir,
    resolve_tetravox_embed_dir,
    resolve_tetravox_embed_override,
    resolve_tetravox_install_root,
    resolve_token,
)

# Named explicitly: under ``-m tit.server`` __name__ is "__main__", outside the "tit" hierarchy.
logger = logging.getLogger("tit.server")


def _configure_logging(level: str = "INFO") -> None:
    """``tit`` logger → stderr (stdout is reserved for the one-line token print)."""
    setup_logging(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logging.getLogger("tit").addHandler(handler)


def _uvicorn_log_config() -> dict:
    """uvicorn's default logging, with the access log moved to stderr.

    stdout carries at most the single ``TIT_SERVER_TOKEN=`` line (when the
    token was generated) so a launcher can read it without parsing logs.
    Both uvicorn handlers get :class:`~tit.server.access_log.TokenMaskFilter`
    so ``?token=…`` never appears in a log line.
    """
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config["handlers"]["access"]["stream"] = "ext://sys.stderr"
    config["filters"] = {
        "mask_token": {"()": "tit.server.access_log.TokenMaskFilter"},
    }
    for name in ("default", "access"):
        config["handlers"][name]["filters"] = ["mask_token"]
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tit.server", description="TI-Toolbox job server"
    )
    parser.add_argument("--project", help="project directory (container path)")
    parser.add_argument("--host", default=None, help="bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="port (default 8765)")
    parser.add_argument("--token", help="shared secret (default: TIT_SERVER_TOKEN)")
    parser.add_argument(
        "--static-dir", help="UI bundle directory (default: TIT_STATIC_DIR)"
    )
    parser.add_argument(
        "--tetravox-dir",
        help="Tetravox embed bundle directory, served at /tetravox/ "
        "(default: TIT_TETRAVOX_EMBED_DIR, else /opt/tetravox/embed). Given "
        "explicitly it overrides any bundle installed through /api/tetravox.",
    )
    parser.add_argument(
        "--tetravox-install-root",
        help="where POST /api/tetravox/install writes bundles "
        "(default: TIT_TETRAVOX_INSTALL_ROOT, else <user config>/tetravox/embed)",
    )
    parser.add_argument(
        "--dev-origin",
        action="append",
        default=None,
        metavar="ORIGIN",
        help="extra WebSocket Origin to accept, e.g. http://127.0.0.1:5173 "
        "(repeatable; also TIT_DEV_ORIGINS, comma-separated)",
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        default=None,
        metavar="HOST",
        help="extra Host header to accept besides 127.0.0.1/localhost "
        "(repeatable; also TIT_ALLOW_HOSTS, comma-separated)",
    )
    parser.add_argument("--reload", action="store_true", help="uvicorn auto-reload")
    parser.add_argument(
        "--reload-dir",
        action="append",
        default=None,
        metavar="DIR",
        help="restrict --reload's file watcher to DIR (repeatable). Without it uvicorn "
        "watches the whole working directory, which in the dev container is the "
        "bind-mounted repository -- desktop/node_modules included",
    )
    parser.add_argument(
        "--dump-openapi",
        metavar="PATH",
        help="write the OpenAPI document as JSON to PATH and exit",
    )
    return parser


def settings_from_file(path: str | None = None) -> ServerSettings:
    """Settings written by :func:`main` for the ``--reload`` child process."""
    path = path or os.environ.get(ENV_SETTINGS_FILE)
    if not path:
        raise SettingsError(f"{ENV_SETTINGS_FILE} is not set")
    with open(path, "r", encoding="utf-8") as fh:
        return ServerSettings.from_json(fh.read())


def write_settings_file(settings: ServerSettings) -> str:
    """Serialise *settings* to a 0600 temp file; returns its path."""
    fd, path = tempfile.mkstemp(prefix="tit-server-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(settings.to_json())
    except BaseException:
        os.unlink(path)
        raise
    return path


def resolve_reload_dirs(dirs: list[str] | None) -> list[str]:
    """Existing entries of *dirs*, warning about the ones that are missing.

    A ``--reload-dir`` naming a path that is not there is the dev container's own
    failure mode: the entrypoint passes ``/ti-toolbox/tit`` whenever
    ``TIT_SERVER_RELOAD=1``, and without the worktree bind-mounted there that
    directory does not exist.  uvicorn would abort on it; warning and falling back
    to uvicorn's default watch root keeps the server up and says why the reloader
    is watching more than it was told to.
    """
    resolved: list[str] = []
    for entry in dirs or []:
        if os.path.isdir(entry):
            resolved.append(entry)
        else:
            logger.warning("--reload-dir %s does not exist; ignoring it", entry)
    return resolved


def app_factory():
    """uvicorn factory target for ``--reload`` (``tit.server.__main__:app_factory``)."""
    from tit.server.app import create_app

    return create_app(settings_from_file())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging()

    from tit.server.app import create_app

    try:
        project_dir = resolve_project_dir(
            args.project, required=args.dump_openapi is None
        )
    except SettingsError as exc:
        logger.error("%s", exc)
        return 2

    if args.dump_openapi:
        settings = ServerSettings(project_dir=project_dir, token="dump")
        document = create_app(settings).openapi()
        with open(args.dump_openapi, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2, sort_keys=True)
            fh.write("\n")
        logger.info("OpenAPI written to %s", args.dump_openapi)
        return 0

    token, generated = resolve_token(args.token)
    settings = ServerSettings(
        project_dir=project_dir,
        host=args.host or os.environ.get(ENV_HOST, "0.0.0.0"),
        port=args.port or int(os.environ.get(ENV_PORT, "8765")),
        token=token,
        static_dir=resolve_static_dir(args.static_dir),
        tetravox_embed_dir=resolve_tetravox_embed_dir(args.tetravox_dir),
        tetravox_embed_override=resolve_tetravox_embed_override(args.tetravox_dir),
        tetravox_install_root=resolve_tetravox_install_root(args.tetravox_install_root),
        dev_reload=args.reload,
        dev_origins=resolve_dev_origins(args.dev_origin),
        allow_hosts=resolve_allow_hosts(args.allow_host),
    )
    if generated:
        print(f"{ENV_TOKEN}={token}", flush=True)

    import uvicorn

    logger.info(
        "tit.server listening on http://%s:%d (project=%s, static_dir=%s)",
        settings.host,
        settings.port,
        settings.project_dir,
        settings.static_dir or "-",
    )
    if settings.dev_reload:
        # The reloader re-imports the app in a child process that inherits
        # os.environ: hand it the settings through a 0600 file, and make sure
        # the token itself is not in that environment.
        settings_file = write_settings_file(settings)
        os.environ[ENV_SETTINGS_FILE] = settings_file
        os.environ.pop(ENV_TOKEN, None)
        reload_dirs = resolve_reload_dirs(args.reload_dir)
        try:
            uvicorn.run(
                "tit.server.__main__:app_factory",
                factory=True,
                host=settings.host,
                port=settings.port,
                reload=True,
                reload_dirs=reload_dirs or None,
                log_config=_uvicorn_log_config(),
            )
        finally:
            os.environ.pop(ENV_SETTINGS_FILE, None)
            try:
                os.unlink(settings_file)
            except OSError:
                pass
    else:
        uvicorn.run(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            log_config=_uvicorn_log_config(),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
