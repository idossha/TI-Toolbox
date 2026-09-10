"""Launch the TI-Toolbox container and open its browser UI.

Uses the same compose specification and container labels as Electron.
Installed wheels use BUILTIN_SPEC; tests verify it matches docker-compose.yml.
"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "LABEL_HOST_DIR",
    "LABEL_PROJECT",
    "LABEL_SERVICE",
    "LABEL_STACK",
    "STACK_ID",
    "LaunchError",
    "StackSpec",
    "build_env",
    "build_run_argv",
    "container_name",
    "default_image",
    "find_free_port",
    "hash8",
    "load_spec",
    "project_name",
    "session_url",
]

# --------------------------------------------------------------------------------------
# Labels — the basis of attach/stop/status, and shared verbatim with the Electron app
# (desktop/src/shared/compose.ts).  Changing one of these here without changing it there
# splits the two launchers into two kinds of container.
# --------------------------------------------------------------------------------------
LABEL_PROJECT = "tit.project"
LABEL_STACK = "tit.stack"
LABEL_SERVICE = "tit.service"
LABEL_HOST_DIR = "tit.host_project_dir"
STACK_ID = "ti-toolbox-v3"
SERVICE_NAME = "tit"

DEFAULT_PORT = 8765
#: The image is amd64-only (decision D1), so the platform is pinned rather than inferred.
PLATFORM = "linux/amd64"
IMAGE_REPO = "idossha/ti-toolbox"


class LaunchError(RuntimeError):
    """A failure the user can act on; the message is the remedy, not a stack trace."""


# --------------------------------------------------------------------------------------
# The run spec
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StackSpec:
    """The parts of the compose service this launcher realises.

    Values still carry ``${VAR}`` / ``${VAR:-default}`` references; they are
    interpolated against :func:`build_env` when the argv is built, exactly as
    ``shared/composeFile.ts`` does for the app.
    """

    image: str
    working_dir: str
    init: bool
    volumes: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    ports: tuple[str, ...]
    healthcheck: tuple[str, ...] = ()


#: Fallback used when the repository's ``docker-compose.yml`` is not on disk (an installed
#: wheel).  Kept honest by ``tests/test_launch.py::test_builtin_spec_matches_compose``.
BUILTIN_SPEC = StackSpec(
    image="idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.0.0}",
    working_dir="/ti-toolbox",
    init=True,
    volumes=(
        "${LOCAL_PROJECT_DIR}:/mnt/${PROJECT_DIR_NAME}",
        "${TIT_USER_CONFIG}:/root/.config/ti-toolbox",
        "/var/run/docker.sock:/var/run/docker.sock",
        "${TIT_REPO_DIR:-}:/ti-toolbox",
    ),
    environment=(
        ("PROJECT_DIR_NAME", "${PROJECT_DIR_NAME}"),
        ("LOCAL_PROJECT_DIR", "${LOCAL_PROJECT_DIR}"),
        ("TIT_SERVER_TOKEN", "${TIT_SERVER_TOKEN}"),
        ("TIT_SERVER_PORT", "${TIT_SERVER_PORT:-8765}"),
        ("TIT_STATIC_DIR", "${TIT_STATIC_DIR:-}"),
        ("PYTHONPATH", "/ti-toolbox"),
        ("TIT_REPO_DIR", "${TIT_REPO_DIR:-}"),
        ("TIT_SERVER_RELOAD", "${TIT_SERVER_RELOAD:-}"),
        ("TZ", "${TZ:-UTC}"),
        ("TIT_HOST_OS", "${TIT_HOST_OS:-unknown}"),
        ("TIT_HOST_OS_VERSION", "${TIT_HOST_OS_VERSION:-unknown}"),
        ("TIT_HOST_ARCH", "${TIT_HOST_ARCH:-unknown}"),
    ),
    ports=("127.0.0.1:${TIT_SERVER_PORT:-8765}:${TIT_SERVER_PORT:-8765}",),
    healthcheck=(
        "CMD",
        "curl",
        "-fsS",
        "http://127.0.0.1:${TIT_SERVER_PORT:-8765}/api/health",
    ),
)


def compose_path() -> Path | None:
    """Resolve an explicit compose file, the checkout copy, or the built-in fallback.

    Standalone loaders pass their adjacent YAML through ``TIT_COMPOSE_FILE``.
    An invalid explicit path fails instead of silently starting a different spec.
    """
    override = os.environ.get("TIT_COMPOSE_FILE")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_file():
            raise LaunchError(
                f"Compose file does not exist or is not a file: {candidate}"
            )
        return candidate
    candidate = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    return candidate if candidate.is_file() else None


def load_spec(path: Path | None = None) -> StackSpec:
    """Parse the compose file into a :class:`StackSpec`, or return :data:`BUILTIN_SPEC`.

    ``path`` defaults to :func:`compose_path`.  Passing a path that does not
    exist is an error (the caller asked for that file); omitting it and having
    no checkout is not.
    """
    if path is None:
        path = compose_path()
        if path is None:
            return BUILTIN_SPEC
    return parse_compose(path.read_text(encoding="utf-8"))


# The compose subset this understands is the same one ``shared/composeFile.ts`` documents:
# a single service with image/init/working_dir/volumes/environment/ports/healthcheck, no
# anchors, no flow mappings, no multi-line scalars.  A real YAML parser is not used because
# the launcher must run on a host with nothing but the standard library.
_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][\w.-]*):\s*(?P<value>.*?)\s*$")
_ITEM = re.compile(r"^(?P<indent> *)-\s*(?P<value>.*?)\s*$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _strip_comment(value: str) -> str:
    """Drop a trailing ``# …`` comment from an unquoted scalar."""
    if value.startswith(("'", '"')):
        return value
    cut = value.find(" #")
    return value[:cut] if cut >= 0 else value


def parse_compose(text: str) -> StackSpec:
    """The ``services.tit`` block of a v3 compose file, as a :class:`StackSpec`."""
    lines = [line.rstrip() for line in text.splitlines()]
    service = _block(lines, ["services", SERVICE_NAME])
    if service is None:
        raise LaunchError(f"the compose file has no services.{SERVICE_NAME} block")

    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    maps: dict[str, list[tuple[str, str]]] = {}
    for key, body, inline in _entries(service):
        if inline:
            scalars[key] = _unquote(_strip_comment(inline))
        elif body and body[0].lstrip().startswith("- "):
            lists[key] = [
                _unquote(_strip_comment(m.group("value")))
                for m in (_ITEM.match(line) for line in body)
                if m
            ]
        else:
            maps[key] = [
                (k, _unquote(_strip_comment(v)))
                for k, _sub, v in _entries(body)
                if v is not None
            ]

    health = maps.get("healthcheck", [])
    test = next((v for k, v in health if k == "test"), "")

    return StackSpec(
        image=scalars.get("image", ""),
        working_dir=scalars.get("working_dir", "/ti-toolbox"),
        init=scalars.get("init", "false").lower() == "true",
        volumes=tuple(lists.get("volumes", ())),
        environment=tuple(
            (k, v) for k, v in maps.get("environment", []) if v is not None
        ),
        ports=tuple(lists.get("ports", ())),
        healthcheck=_parse_flow_list(test),
    )


def _parse_flow_list(raw: str) -> tuple[str, ...]:
    """``["CMD", "curl", …]`` — the one flow sequence the compose file uses."""
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return ()
    return tuple(_unquote(part) for part in raw[1:-1].split(",") if part.strip())


def _block(lines: list[str], path: list[str]) -> list[str]:
    """The indented body under ``path`` (``["services", "tit"]``), comments removed."""
    body = [
        line for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]
    for key in path:
        found = None
        for index, line in enumerate(body):
            match = _KEY.match(line)
            if (
                match
                and match.group("key") == key
                and len(match.group("indent")) == _base_indent(body)
            ):
                found = index
                break
        if found is None:
            return None  # type: ignore[return-value]
        indent = len(_KEY.match(body[found]).group("indent"))  # type: ignore[union-attr]
        rest = []
        for line in body[found + 1 :]:
            if len(line) - len(line.lstrip()) <= indent:
                break
            rest.append(line)
        body = rest
    return body


def _base_indent(body: list[str]) -> int:
    return min((len(line) - len(line.lstrip()) for line in body), default=0)


def _entries(body: list[str]) -> list[tuple[str, list[str], str | None]]:
    """``(key, indented body, inline scalar)`` for each key at ``body``'s top level."""
    if not body:
        return []
    indent = _base_indent(body)
    out: list[tuple[str, list[str], str | None]] = []
    index = 0
    while index < len(body):
        match = _KEY.match(body[index])
        if not match or len(match.group("indent")) != indent:
            index += 1
            continue
        key = match.group("key")
        inline = match.group("value") or None
        sub: list[str] = []
        index += 1
        while (
            index < len(body)
            and (len(body[index]) - len(body[index].lstrip())) > indent
        ):
            sub.append(body[index])
            index += 1
        out.append((key, sub, inline))
    return out


# --------------------------------------------------------------------------------------
# Interpolation, naming, environment
# --------------------------------------------------------------------------------------

_VAR = re.compile(r"\$\{(?P<name>[A-Za-z_]\w*)(?::-(?P<default>[^}]*))?\}")


def interpolate(template: str, env: dict[str, str]) -> str:
    """``${VAR}`` / ``${VAR:-default}``, from ``env`` only (never ``os.environ``).

    Reading the ambient environment here is exactly the hazard
    ``shared/compose.ts`` documents for ``TIT_REPO_DIR``: a stray variable in
    the user's shell must not bind-mount a host directory over the image's own
    ``/ti-toolbox``.
    """

    def replace(match: re.Match[str]) -> str:
        value = env.get(match.group("name"))
        if value is None or value == "":
            return match.group("default") or ""
        return value

    return _VAR.sub(replace, template)


def hash8(text: str) -> str:
    """The Electron app's 32-bit project hash (``shared/compose.ts#hash8``), reproduced.

    Not a security boundary — it exists so both launchers derive the *same*
    container name and ``tit.project`` label for the same directory, which is
    what lets ``tit launch --status`` see a container the app started and the
    app attach to one this launcher started.
    """
    mask = 0xFFFFFFFF

    def imul(a: int, b: int) -> int:
        product = ((a & mask) * (b & mask)) & mask
        return product - 0x100000000 if product & 0x80000000 else product

    h1 = 0xDEADBEEF ^ len(text)
    h2 = 0x41C6CE57 ^ len(text)
    for char in text:
        code = ord(char)
        h1 = imul(h1 ^ code, 2654435761)
        h2 = imul(h2 ^ code, 1597334677)
    h1 = imul(h1 ^ ((h1 & mask) >> 16), 2246822507) ^ imul(
        h2 ^ ((h2 & mask) >> 13), 3266489909
    )
    return format(h1 & mask, "08x")


def project_name(host_project_dir: str) -> str:
    """``ti-toolbox-<hash8>`` — the compose project name and ``tit.project`` label."""
    return f"ti-toolbox-{hash8(host_project_dir)}"


def container_name(host_project_dir: str) -> str:
    """What ``docker compose`` itself would have named the service's container."""
    return f"{project_name(host_project_dir)}-{SERVICE_NAME}-1"


def default_image() -> str:
    """Use the compose image default, or an explicit ``TIT_IMAGE_TAG`` override.

    Runtime package versions can be prereleases with no matching image. The compose
    spec (and its wheel fallback) owns the image independently of that version.
    """
    tag = os.environ.get("TIT_IMAGE_TAG", "").strip()
    if tag:
        return tag if "/" in tag else f"{IMAGE_REPO}:{tag}"
    return interpolate(load_spec().image, {})


def user_config_dir() -> Path:
    """``~/.config/ti-toolbox``, created if absent — mounted at ``/root/.config/ti-toolbox``."""
    root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    path = root / "ti-toolbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_env(
    *,
    host_project_dir: str,
    port: int,
    token: str,
    user_config: str,
    image_tag: str,
    repo_dir: str = "",
    static_dir: str = "",
    server_reload: bool = False,
) -> dict[str, str]:
    """The map the compose file's ``${VAR}`` references are interpolated from.

    Mirrors ``shared/compose.ts#buildStackEnv``.  ``TIT_REPO_DIR`` and
    ``TIT_SERVER_RELOAD`` are always present and empty by default for the reason
    that file gives: an omitted key would let the user's own shell supply one.
    """
    return {
        "LOCAL_PROJECT_DIR": host_project_dir,
        "PROJECT_DIR_NAME": Path(host_project_dir).name,
        "TIT_USER_CONFIG": user_config,
        "TIT_HOST_OS": platform.system().lower(),
        "TIT_HOST_OS_VERSION": platform.release(),
        "TIT_HOST_ARCH": platform.machine(),
        "TZ": os.environ.get("TZ", "UTC"),
        "TIT_SERVER_PORT": str(port),
        "TIT_SERVER_TOKEN": token,
        "TIT_IMAGE_TAG": image_tag,
        "TIT_REPO_DIR": repo_dir,
        "TIT_STATIC_DIR": static_dir,
        "TIT_SERVER_RELOAD": "1" if server_reload else "",
    }


def build_run_argv(
    spec: StackSpec, env: dict[str, str], *, host_project_dir: str, image: str
) -> list[str]:
    """The full ``docker run`` argv for one stack — pure, so it can be asserted in a test.

    Every volume whose source interpolates to empty is dropped rather than
    handed to Docker as an empty bind source (``composeFile.ts`` does the same);
    that is how the optional dev-repo mount switches itself off.
    """
    name = container_name(host_project_dir)
    argv = [
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--platform",
        PLATFORM,
        "--workdir",
        spec.working_dir,
    ]
    if spec.init:
        argv.append("--init")
    for key, value in (
        (LABEL_PROJECT, project_name(host_project_dir)),
        (LABEL_STACK, STACK_ID),
        (LABEL_SERVICE, SERVICE_NAME),
        (LABEL_HOST_DIR, host_project_dir),
    ):
        argv += ["--label", f"{key}={value}"]
    for entry in spec.volumes:
        resolved = interpolate(entry, env)
        source = resolved.split(":", 1)[0]
        if not source:
            continue
        argv += ["--volume", resolved]
    for key, template in spec.environment:
        argv += ["--env", f"{key}={interpolate(template, env)}"]
    for entry in spec.ports:
        argv += ["--publish", interpolate(entry, env)]
    if spec.healthcheck and spec.healthcheck[0] == "CMD":
        argv += [
            "--health-cmd",
            " ".join(interpolate(part, env) for part in spec.healthcheck[1:]),
            "--health-interval",
            "10s",
            "--health-timeout",
            "3s",
            "--health-start-period",
            "20s",
            "--health-retries",
            "6",
        ]
    argv.append(image)
    return argv


def session_url(origin: str, token: str) -> str:
    """The one URL a browser needs: it trades the token for the session cookie.

    ``tit/server/auth.py`` mints a session id, sets it as an
    ``HttpOnly; SameSite=Strict`` cookie and redirects to ``/``, so the token
    never has to be typed again and never appears in the address bar afterwards.
    """
    from urllib.parse import quote

    return f"{origin}/auth/session?token={quote(token, safe='')}"


def find_free_port(preferred: int = DEFAULT_PORT, attempts: int = 64) -> int:
    """First free TCP port at or above ``preferred`` on the loopback interface."""
    for offset in range(attempts):
        candidate = preferred + offset
        if candidate > 65535:
            break
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    raise LaunchError(f"no free port in {preferred}-{preferred + attempts - 1}")


# --------------------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------------------


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if shutil.which("docker") is None:
        raise LaunchError(
            "Docker was not found on this machine. Install Docker Desktop (macOS/Windows) "
            "or Docker Engine (Linux), then try again."
        )
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise LaunchError(
            (result.stderr or result.stdout).strip()
            or f"docker {' '.join(args)} failed"
        )
    return result


def require_docker() -> None:
    """Fail with the remedy, not a traceback, when the daemon is unreachable."""
    result = _docker("version", "--format", "{{.Server.APIVersion}}", check=False)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        if "permission denied" in detail.lower():
            raise LaunchError(
                "Permission denied talking to the Docker socket. On Linux, add your user to the "
                "docker group (sudo usermod -aG docker $USER), then log out and back in. "
                "On macOS, restart Docker Desktop."
            )
        raise LaunchError(
            "Docker is installed but not running. Start Docker Desktop (or your Docker daemon) "
            f"and try again.{(' (' + detail + ')') if detail else ''}"
        )


def find_container(host_project_dir: str) -> dict | None:
    """The container this project owns, by label — the app's own attach rule.

    Both labels are checked: ``tit.project`` is a 32-bit hash, so matching it
    alone could attach one project's UI to another project's container.
    """
    result = _docker(
        "ps",
        "--all",
        "--filter",
        f"label={LABEL_PROJECT}={project_name(host_project_dir)}",
        "--format",
        "{{.ID}}",
    )
    for cid in result.stdout.split():
        info = json.loads(_docker("inspect", cid).stdout)[0]
        labels = info["Config"].get("Labels") or {}
        recorded = labels.get(LABEL_HOST_DIR)
        if recorded and os.path.realpath(recorded) == os.path.realpath(
            host_project_dir
        ):
            return info
    return None


def find_running_containers() -> list[dict]:
    """Discover current and legacy toolbox sessions, including other projects."""
    result = _docker("ps", "--format", "{{.ID}}")
    containers = []
    for cid in result.stdout.split():
        info = json.loads(_docker("inspect", cid).stdout)[0]
        config = info.get("Config", {})
        labels = config.get("Labels") or {}
        name = info.get("Name", "").lstrip("/").lower()
        image = config.get("Image", "").lower()
        if labels.get(LABEL_SERVICE) not in (None, "", SERVICE_NAME):
            continue
        if (
            labels.get(LABEL_STACK)
            or labels.get(LABEL_PROJECT)
            or re.match(r"^ti[-_]toolbox(?:[-_]|$)", name)
            or re.search(r"(?:^|/)ti[-_]toolbox(?::|@|$)", image)
        ):
            containers.append(info)
    return containers


def choose_existing(containers: list[dict], options: LaunchOptions) -> tuple[dict, str]:
    """Require a deliberate session and action; never infer consent from matching config."""
    options.echo("\nRunning TI-Toolbox containers")
    for index, info in enumerate(containers, 1):
        options.echo(f"  {index}. {info.get('Config', {}).get('Image', 'TI-Toolbox')}")
    selected = None
    if options.container:
        selected = next(
            (
                info
                for info in containers
                if options.container in (info["Id"], info["Name"].lstrip("/"))
            ),
            None,
        )
        if selected is None:
            raise LaunchError(
                "--container does not identify a running TI-Toolbox container"
            )
    elif len(containers) == 1:
        selected = containers[0]
    elif sys.stdin.isatty():
        try:
            index = int(input("Select container number: "))
            if 1 <= index <= len(containers):
                selected = containers[index - 1]
        except (ValueError, EOFError):
            pass
    if selected is None:
        raise LaunchError(
            "select a running session with --container NAME (multiple containers found)"
        )
    action = options.existing
    if action is None and sys.stdin.isatty():
        options.echo(
            "\nAvailable actions\n-----------------\n  1. Recreate (default)\n  2. Attach"
        )
        options.echo("\nRecreate stops this container and its jobs.")
        try:
            answer = input("Choose [1]: ").strip().lower()
            action = {
                "": "recreate",
                "1": "recreate",
                "r": "recreate",
                "recreate": "recreate",
                "2": "attach",
                "a": "attach",
                "attach": "attach",
            }.get(answer)
        except EOFError:
            action = None
    if action not in ("attach", "recreate"):
        raise LaunchError(
            "existing container left unchanged; choose --existing attach or "
            "--existing recreate (stops jobs and removes the selected container)"
        )
    return selected, action


def container_credentials(info: dict) -> tuple[str, str]:
    """``(origin, token)`` read out of a running container's own environment.

    The token is never written to the host filesystem — on attach it comes back
    from the container that holds it, which is why there is no state file here.
    """
    env = dict(
        pair.split("=", 1) for pair in info["Config"].get("Env", []) if "=" in pair
    )
    token = env.get("TIT_SERVER_TOKEN", "")
    port = env.get("TIT_SERVER_PORT", str(DEFAULT_PORT))
    if not token:
        raise LaunchError(
            f"container {info['Name'].lstrip('/')} has no TIT_SERVER_TOKEN; "
            "stop it with `tit launch --stop` and start a fresh one."
        )
    return f"http://127.0.0.1:{port}", token


def ensure_image(image: str, *, refresh: bool = True, echo=print) -> None:
    """Refresh the mutable release image; retain cached images for offline/dev use."""
    cached = _docker("image", "inspect", image, check=False).returncode == 0
    if cached and not (refresh and image == "idossha/ti-toolbox:v3.0.0"):
        echo(f"image {image} is already present")
        return
    echo(f"checking for updates to {image}…" if cached else f"downloading {image}…")
    result = subprocess.run(["docker", "pull", "--platform", PLATFORM, image])
    if result.returncode != 0:
        if cached:
            echo(f"Warning: could not refresh {image}; using the cached image.")
            return
        raise LaunchError(
            f"could not download {image}.\n"
            "  - If you are on a pre-release checkout, no such tag is published yet: build it\n"
            "    with `container/blueprint/build.sh --tag "
            + image
            + "` (30-60+ minutes), or\n"
            "    pass --image with a tag you already have (`docker images idossha/ti-toolbox`).\n"
            "  - Otherwise check your internet connection and registry access."
        )


def wait_for_health(origin: str, timeout: float = 180.0, *, echo=print) -> None:
    """Poll ``/api/health`` until it answers ``{"status": "ok"}``.

    The generous default matches the Electron app's: a cold amd64 start under
    emulation is slow, and declaring a live stack dead costs the user the whole
    session.
    """
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{origin}/api/health", timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("status") == "ok":
                return
            last = f"health status {body.get('status')!r}"
        except (
            urllib.error.URLError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as err:
            last = str(err)
        time.sleep(0.5)
    raise LaunchError(
        f"the container started but {origin}/api/health did not answer within "
        f"{int(timeout)}s ({last}). Run `tit launch --logs` to see why."
    )


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------


@dataclass
class LaunchOptions:
    """One launch invocation.

    The last three are the *dev overrides* — the three variables the compose file exposes
    as ``${TIT_REPO_DIR:-}``, ``${TIT_SERVER_RELOAD:-}`` and ``${TIT_STATIC_DIR:-}``, and
    the only difference between a user run and a developer run (see
    ``dev/loader/docker-compose.dev.yml``).  They default to off, which is the only correct
    answer for a user: ``repo_dir`` bind-mounts a host directory over ``/ti-toolbox``, which
    is where the image installed its own ``tit`` from, so a non-empty value in a packaged or
    pip-installed run replaces the toolbox with whatever is at that path.
    """

    project: str
    port: int = DEFAULT_PORT
    image: str | None = None
    open_browser: bool = True
    timeout: float = 180.0
    echo: object = field(default=print)
    repo_dir: str = ""
    server_reload: bool = False
    static_dir: str = ""
    existing: str | None = None
    container: str | None = None
    session_container: str = ""
    session_project: str = ""


def resolve_project(raw: str | None) -> str:
    """The absolute, real path of the project directory, or a message saying what is wrong."""
    if not raw:
        raise LaunchError(
            "no project directory given. Pass --project /path/to/bids-project (or set "
            "TIT_PROJECT_DIR); TI-Toolbox opens one project at a time and will not guess which."
        )
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise LaunchError(f"project directory does not exist: {path}")
    return os.path.realpath(path)


def start(options: LaunchOptions) -> tuple[str, str]:
    """Ask before reusing or replacing any running toolbox container; return ``(origin, token)``."""
    echo = options.echo
    require_docker()
    host_project_dir = resolve_project(options.project)
    image = options.image or default_image()
    image_ready = False

    running = find_running_containers()
    if running:
        selected, action = choose_existing(running, options)
        if action == "attach":
            origin, token = container_credentials(selected)
            options.session_container = selected["Id"]
            options.session_project = (selected["Config"].get("Labels") or {}).get(
                LABEL_HOST_DIR, ""
            )
            echo(
                f"attached to {selected['Name'].lstrip('/')} at {origin}; using its existing configuration"
            )
            wait_for_health(origin, timeout=60.0, echo=echo)
            return origin, token
        owner = find_container(host_project_dir)
        if (
            owner is not None
            and owner["State"]["Running"]
            and owner["Id"] != selected["Id"]
        ):
            raise LaunchError(
                "another running container owns the requested project; select it explicitly"
            )
        load_spec()  # Validate the requested YAML before stopping an existing session.
        ensure_image(image, refresh=not bool(options.repo_dir), echo=echo)
        image_ready = True
        _docker("stop", selected["Id"])
        _docker("rm", selected["Id"])
    elif options.container or options.existing == "attach":
        raise LaunchError(
            "no selected running TI-Toolbox container is available to attach"
        )
    existing = find_container(host_project_dir)
    if existing is not None:
        if existing["State"]["Running"]:
            raise LaunchError(
                "another running container owns the requested project; select it explicitly"
            )
        echo(f"removing the stopped container {existing['Name'].lstrip('/')}")
        _docker("rm", existing["Id"])

    if not image_ready:
        ensure_image(image, refresh=not bool(options.repo_dir), echo=echo)

    port = find_free_port(options.port)
    if port != options.port:
        echo(f"port {options.port} is taken; using {port}")
    token = secrets.token_urlsafe(32)
    env = build_env(
        host_project_dir=host_project_dir,
        port=port,
        token=token,
        user_config=str(user_config_dir()),
        image_tag=image.rsplit(":", 1)[-1],
        repo_dir=options.repo_dir,
        static_dir=options.static_dir,
        server_reload=options.server_reload,
    )
    argv = build_run_argv(
        load_spec(), env, host_project_dir=host_project_dir, image=image
    )
    echo(f"starting {container_name(host_project_dir)} on port {port}…")
    created = _docker(*argv[1:])
    options.session_container = created.stdout.strip()
    options.session_project = host_project_dir

    origin = f"http://127.0.0.1:{port}"
    echo("waiting for the server to answer…")
    try:
        wait_for_health(origin, timeout=options.timeout, echo=echo)
    except LaunchError:
        logs = _docker(
            "logs", "--tail", "20", container_name(host_project_dir), check=False
        )
        raise LaunchError(
            f"the container did not become healthy. Last log lines:\n{logs.stdout}{logs.stderr}"
        ) from None
    return origin, token


def stop(project: str) -> list[str]:
    """Stop and remove this project's container. Already gone is success, not failure."""
    require_docker()
    host_project_dir = resolve_project(project)
    info = find_container(host_project_dir)
    if info is None:
        return []
    name = info["Name"].lstrip("/")
    _docker("rm", "--force", info["Id"])
    return [name]


def status(project: str) -> dict | None:
    """``{name, state, image, origin, health}`` for this project's container, or ``None``."""
    require_docker()
    info = find_container(resolve_project(project))
    if info is None:
        return None
    env = dict(
        pair.split("=", 1) for pair in info["Config"].get("Env", []) if "=" in pair
    )
    return {
        "name": info["Name"].lstrip("/"),
        "state": info["State"]["Status"],
        "health": (info["State"].get("Health") or {}).get("Status", "n/a"),
        "image": info["Config"]["Image"],
        "origin": f"http://127.0.0.1:{env.get('TIT_SERVER_PORT', DEFAULT_PORT)}",
    }


def logs(project: str, *, follow: bool = False, tail: str = "200") -> int:
    """Stream the container's logs to this terminal; returns docker's exit code."""
    require_docker()
    info = find_container(resolve_project(project))
    if info is None:
        raise LaunchError(
            "no TI-Toolbox container is running for that project directory"
        )
    argv = ["docker", "logs", "--tail", tail]
    if follow:
        argv.append("--follow")
    argv.append(info["Id"])
    return subprocess.run(argv).returncode


def open_in_browser(url: str, *, echo=print) -> None:
    """Open the session URL, saying so either way — a headless host has no browser to open."""
    if webbrowser.open(url):
        echo("opened your browser")
    else:
        echo("could not open a browser automatically; paste the URL above into one")


def run(argv: list[str] | None = None) -> int:
    """``tit launch`` — see :mod:`tit.cli` for the argument parser."""
    from tit.cli import main

    return main(["launch", *(argv or sys.argv[1:])])
