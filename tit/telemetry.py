"""Anonymous usage telemetry for TI-Toolbox.

Collects minimal, non-identifying usage data to help the development team
understand feature adoption, platform distribution, and error rates.  All
network calls are fire-and-forget in daemon threads — they never block or
crash the user's workflow.

Collected Data
--------------
- TI-Toolbox version, Python version, OS / platform
- Interface (``cli`` or ``gui``)
- Operation type (``sim_ti``, ``sim_mti``, ``flex_search``, etc.)
- Operation status (``start``, ``success``, ``error``)
- Operation wall-clock duration (seconds, on completion events)
- Error class name on failure (e.g. ``ValueError`` — **no** tracebacks)
- Anonymous client ID (random UUID, stored locally)
- Approximate country via GA4 IP-based geolocation (IP is anonymised by Google)

**Not** collected: file paths, subject IDs, parameter values, hostnames,
usernames, tracebacks, or any scientific data.

Opt-Out
-------
1. Environment variable: ``TIT_NO_TELEMETRY=1``
2. Config file: user config dir ``telemetry.json`` → ``"enabled": false``
3. GUI: Settings → Privacy toggle

Public API
----------
is_enabled
    Check whether telemetry is active.
track_event
    Send a single GA4 event (non-blocking).
track_operation
    Context manager that sends ``start`` + ``success`` / ``error`` events.
consent_prompt_cli
    Show first-run consent prompt in a terminal.
consent_prompt_gui
    Show first-run consent dialog in the PyQt5 GUI.
set_enabled
    Programmatically enable or disable telemetry.

See Also
--------
tit.constants : ``GA4_MEASUREMENT_ID``, ``GA4_API_SECRET``, and event names.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Generator

import tit
from tit import constants as const

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class TelemetryConfig:
    """Persistent telemetry preferences stored as JSON.

    Attributes
    ----------
    enabled : bool
        Whether telemetry events are sent.  Default ``False`` until the
        user gives explicit consent.
    client_id : str
        Random UUID generated once per install.  Never linked to identity.
    consent_shown : bool
        ``True`` after the user has been asked (regardless of answer).
    """

    enabled: bool = False
    client_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    consent_shown: bool = False


# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------


def _config_path() -> Path | None:
    """Return the path to the telemetry config file, or ``None``.

    Uses the **user-level** config directory
    (``PathManager.user_config_dir()``) so that telemetry consent and
    the anonymous client ID persist across projects and container
    restarts.  Inside Docker, this resolves to
    ``/root/.config/ti-toolbox/`` which the Electron launcher mounts
    from the host.

    Returns ``None`` when the user config directory cannot be resolved
    (e.g. the mount is missing and ``/root/.config`` is not writable).
    Callers treat ``None`` as “telemetry unavailable”.

    Returns
    -------
    pathlib.Path or None
        Absolute path to the JSON config file, or ``None``.
    """
    from tit.paths import PathManager

    config_dir = Path(PathManager.user_config_dir())
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / const.TELEMETRY_CONFIG_FILE


def load_config() -> TelemetryConfig:
    """Load telemetry config from disk, or return defaults.

    Returns ``TelemetryConfig(enabled=False)`` when no project is active
    (i.e. :func:`_config_path` returns ``None``).

    Returns
    -------
    TelemetryConfig
        Loaded or default configuration.
    """
    path = _config_path()
    if path is None:
        return TelemetryConfig()
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            return TelemetryConfig(
                enabled=data.get("enabled", False),
                client_id=data.get("client_id", uuid.uuid4().hex),
                consent_shown=data.get("consent_shown", False),
            )
        except (json.JSONDecodeError, OSError, KeyError):
            logger.debug("Telemetry config corrupt or unreadable; using defaults.")
    return TelemetryConfig()


def save_config(config: TelemetryConfig) -> None:
    """Persist telemetry config to disk.

    Does nothing when no project is active (no config path available).
    Sets file permissions to ``0o600`` (owner read/write only).

    Parameters
    ----------
    config : TelemetryConfig
        Configuration to write.
    """
    path = _config_path()
    if path is None:
        logger.debug("No project active; telemetry config not saved.")
        return
    try:
        with open(path, "w") as f:
            json.dump(asdict(config), f, indent=2)
        path.chmod(0o600)
    except OSError:
        logger.debug("Could not write telemetry config to %s", path)


# ---------------------------------------------------------------------------
# Enabled check
# ---------------------------------------------------------------------------

# Module-level cache so we read the config file at most once per process.
_cached_config: TelemetryConfig | None = None


def _get_config() -> TelemetryConfig:
    """Return the (lazily cached) telemetry config."""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_config()
    return _cached_config


def _invalidate_cache() -> None:
    """Force config re-read on next access (used after consent/toggle)."""
    global _cached_config
    _cached_config = None


def is_enabled() -> bool:
    """Check whether telemetry is active.

    Telemetry is active only when **all** of the following are true:

    1. ``config.enabled`` is ``True`` (user gave consent).
    2. The environment variable ``TIT_NO_TELEMETRY`` is **not** set to a
       truthy value (``1``, ``true``, ``yes``).
    3. The GA4 credentials are not still set to placeholders.

    Returns
    -------
    bool
        ``True`` if telemetry events should be sent.
    """
    env_val = os.environ.get(const.ENV_NO_TELEMETRY, "").strip().lower()
    if env_val in ("1", "true", "yes"):
        return False
    cfg = _get_config()
    if not cfg.enabled:
        return False
    # Don't send events if GA4 credentials haven't been configured yet.
    if const.GA4_MEASUREMENT_ID == "G-XXXXXXXXXX":
        return False
    return True


def set_enabled(enabled: bool) -> None:
    """Programmatically enable or disable telemetry.

    Writes the change to disk immediately and invalidates the in-process
    cache so subsequent ``is_enabled()`` calls reflect the new state.

    When the user opts in for the first time (``enabled=True`` and consent
    was not previously shown), a one-time ``first_open`` event is sent to
    distinguish new installations from returning users.

    Parameters
    ----------
    enabled : bool
        ``True`` to enable, ``False`` to disable.
    """
    cfg = _get_config()
    is_first_consent = enabled and not cfg.consent_shown
    cfg.enabled = enabled
    cfg.consent_shown = True
    save_config(cfg)
    _invalidate_cache()
    if is_first_consent:
        track_event(const.TELEMETRY_OP_FIRST_OPEN)


# ---------------------------------------------------------------------------
# System parameters (attached to every event)
# ---------------------------------------------------------------------------


# Map of raw OS strings (from any source: Node's os.platform(), Python's
# platform.system(), os.name, or unset) to the canonical lower-case names
# we send to GA4. Keeps dashboards simple — they only need to know about
# 'darwin', 'linux', 'windows' (and 'unknown').
_OS_NAME_CANONICAL = {
    # macOS
    "darwin": "darwin",
    "mac": "darwin",
    "macos": "darwin",
    "osx": "darwin",
    # Linux
    "linux": "linux",
    "linux2": "linux",
    # Windows — Node returns 'win32', Python's os.name returns 'nt',
    # platform.system() returns 'Windows'. All of them mean the same OS.
    "windows": "windows",
    "win32": "windows",
    "win64": "windows",
    "nt": "windows",
    "cygwin": "windows",
    "msys": "windows",
}


def _canonical_os_name() -> str:
    """Return a canonical OS name: 'darwin', 'linux', 'windows', or 'unknown'.

    Resolves from ``TIT_HOST_OS`` (set by the Electron launcher or
    ``loader.py``) when present, otherwise from ``platform.system()``.
    Normalises so dashboards don't need to handle launcher-specific
    aliases (Node's ``os.platform()`` returns ``'win32'`` while Python's
    ``platform.system().lower()`` returns ``'windows'`` — both should
    bucket as ``'windows'``).
    """
    raw = os.environ.get("TIT_HOST_OS") or platform.system() or ""
    return _OS_NAME_CANONICAL.get(raw.strip().lower(), "unknown")


# Map of raw arch strings (from Node's os.arch(), Python's platform.machine(),
# or any other source) to canonical values for GA4 telemetry. Ensures Electron's
# 'x64' and Python's 'x86_64' both report as 'x86_64'.
_OS_ARCH_CANONICAL = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "i386": "x86",
    "i686": "x86",
    "x86": "x86",
    "arm64": "arm64",
    "aarch64": "arm64",
    "armv7l": "armv7",
    "armv6l": "armv6",
}


def _canonical_arch() -> str:
    """Return a canonical arch: 'x86_64', 'arm64', 'x86', or 'unknown'.

    Resolves from ``TIT_HOST_ARCH`` (set by the Electron launcher or
    ``loader.py``) when present, otherwise from ``platform.machine()``.
    Normalises so Electron's ``'x64'`` and Python's ``'x86_64'`` both
    bucket as ``'x86_64'`` in telemetry.
    """
    raw = os.environ.get("TIT_HOST_ARCH") or platform.machine() or ""
    return _OS_ARCH_CANONICAL.get(raw.strip().lower(), "unknown")


def _system_params() -> dict[str, str]:
    """Return a dict of non-identifying system metadata.

    Uses ``TIT_HOST_*`` environment variables (set by the Electron
    launcher or dev loader) to report the **host** OS, not the Docker
    container's Linux.  Falls back to ``platform`` for non-Docker use.

    ``os_name`` is normalised to one of ``'darwin'``, ``'linux'``,
    ``'windows'``, or ``'unknown'`` regardless of which launcher set
    ``TIT_HOST_OS``.  See :func:`_canonical_os_name`.

    Returns
    -------
    dict[str, str]
        Keys: ``tit_version``, ``os_name``, ``os_version``, ``platform``,
        ``interface``.
    """
    return {
        "tit_version": tit.__version__,
        "os_name": _canonical_os_name(),
        "os_version": os.environ.get("TIT_HOST_OS_VERSION", platform.release()),
        "platform": _canonical_arch(),
        "interface": os.environ.get("TIT_INTERFACE", "cli"),
    }


# ---------------------------------------------------------------------------
# GA4 Measurement Protocol sender
# ---------------------------------------------------------------------------


# System CA bundle paths to try when the default SSL context has no certs
# (common in conda-based environments like SimNIBS inside Docker).
_CA_BUNDLE_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian / Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL / CentOS / Fedora
    "/etc/ssl/cert.pem",  # Alpine / macOS
    "/etc/ssl/ca-bundle.pem",  # openSUSE
)


def _ssl_context() -> ssl.SSLContext | None:
    """Return an SSL context that can verify GA4's certificate.

    The default context works on most hosts, but inside Docker the
    conda-built Python used by SimNIBS often has no CA bundle.
    This helper falls back to well-known system CA paths.

    Returns ``None`` (use default context) when certs are fine,
    or a configured :class:`ssl.SSLContext` when a system bundle was
    found.
    """
    # Fast path: default context works
    ctx = ssl.create_default_context()
    if ctx.get_ca_certs():
        return None  # urllib will use its own default — no override needed

    # Try system CA bundles
    for ca_path in _CA_BUNDLE_PATHS:
        if os.path.isfile(ca_path):
            ctx.load_verify_locations(ca_path)
            return ctx

    # Last resort: no verification (still encrypted, just no cert check).
    # Acceptable for anonymous telemetry — not for auth or sensitive data.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _send_ga4(payload: dict[str, Any]) -> None:
    """POST a JSON payload to the GA4 Measurement Protocol endpoint.

    Runs synchronously — callers are responsible for offloading to a
    background thread.  Silently swallows all exceptions.

    Parameters
    ----------
    payload : dict
        GA4 MP JSON body (must include ``client_id`` and ``events``).
    """
    url = (
        f"{const.GA4_ENDPOINT}"
        f"?measurement_id={const.GA4_MEASUREMENT_ID}"
        f"&api_secret={const.GA4_API_SECRET}"
    )
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        ctx = _ssl_context()
        with urllib.request.urlopen(
            req, timeout=const.TELEMETRY_TIMEOUT_S, context=ctx
        ):
            pass  # GA4 MP returns 204 No Content on success
    except (urllib.error.URLError, OSError, ValueError):
        pass  # Network issues, firewall, DNS — silently drop


def track_event(
    event_name: str,
    params: dict[str, str | int] | None = None,
    *,
    _blocking: bool = False,
) -> None:
    """Send a single GA4 event in a background daemon thread.

    Does nothing if telemetry is disabled.

    Parameters
    ----------
    event_name : str
        GA4 event name (e.g. ``"sim_ti"``, ``"gui_launch"``).
        Must be ≤40 chars, alphanumeric + underscores.
    params : dict[str, str | int], optional
        Extra event parameters.  System params (OS, version, etc.) are
        merged in automatically.
    _blocking : bool, optional
        If ``True``, wait up to ``TELEMETRY_TIMEOUT_S + 1`` seconds for
        the HTTP request to complete.  Used for completion events
        (``success`` / ``error``) so they are not lost when the process
        exits shortly after.

    Examples
    --------
    >>> from tit.telemetry import track_event
    >>> track_event("gui_launch")
    >>> track_event("sim_ti", {"status": "success"})
    """
    if not is_enabled():
        return

    cfg = _get_config()
    merged_params = _system_params()
    if params:
        merged_params.update(params)

    payload = {
        "client_id": cfg.client_id,
        "events": [
            {
                "name": event_name,
                "params": merged_params,
            }
        ],
    }

    thread = threading.Thread(target=_send_ga4, args=(payload,), daemon=True)
    thread.start()
    if _blocking:
        thread.join(timeout=const.TELEMETRY_TIMEOUT_S + 1)


# ---------------------------------------------------------------------------
# Operation tracking context manager
# ---------------------------------------------------------------------------


@contextmanager
def track_operation(op_name: str) -> Generator[None, None, None]:
    """Context manager that sends ``start`` and ``success``/``error`` events.

    Wraps a major operation (simulation, optimization, analysis) with two
    telemetry events:

    - On entry: ``{op_name}`` with ``{"status": "start"}``
    - On clean exit: ``{op_name}`` with ``{"status": "success"}``
    - On exception: ``{op_name}`` with ``{"status": "error",
      "error_type": "<class name>"}``

    The exception is always re-raised — this context manager is
    transparent to control flow.

    Parameters
    ----------
    op_name : str
        Operation name (e.g. ``"sim_ti"``, ``"flex_search"``).

    Yields
    ------
    None

    Examples
    --------
    >>> from tit.telemetry import track_operation
    >>> with track_operation("sim_ti"):
    ...     run_simulation(config)
    """
    track_event(op_name, {"status": "start"})
    t0 = time.monotonic()
    try:
        yield
    except Exception as exc:
        duration_s = int(round(time.monotonic() - t0))
        detail = re.sub(r"/\S+", "<path>", str(exc))[:80]
        track_event(
            op_name,
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error_detail": detail,
                "duration_s": duration_s,
            },
            _blocking=True,
        )
        raise
    else:
        duration_s = int(round(time.monotonic() - t0))
        track_event(
            op_name, {"status": "success", "duration_s": duration_s}, _blocking=True
        )


# ---------------------------------------------------------------------------
# Consent prompts
# ---------------------------------------------------------------------------

_CONSENT_BANNER = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TI-Toolbox — Usage Data

  TI-Toolbox can send anonymous usage data to
  help us identify issues and improve stability.

  This includes which operations ran and whether
  they succeeded or failed. No personal data,
  file paths, or scientific results are collected.

  You can disable this at any time:
    • Set  TIT_NO_TELEMETRY=1  in your environment
    • Toggle in GUI: Settings → Usage Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def consent_prompt_cli() -> None:
    """Show a one-time consent prompt in the terminal.

    Only runs when:
    - ``consent_shown`` is ``False`` in the stored config.
    - ``sys.stdin`` is a TTY (interactive terminal).

    Non-interactive environments (Docker builds, CI, piped input) are
    silently skipped — telemetry stays disabled until an interactive
    session occurs.

    The user's answer is persisted immediately so the prompt never
    appears again.
    """
    cfg = _get_config()
    if cfg.consent_shown:
        return
    if not sys.stdin.isatty():
        return

    print(_CONSENT_BANNER)
    try:
        answer = input("\n  Enable anonymous usage statistics? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    cfg.enabled = answer in ("", "y", "yes")
    cfg.consent_shown = True
    save_config(cfg)
    _invalidate_cache()

    if cfg.enabled:
        print("  ✓ Telemetry enabled. Thank you!\n")
    else:
        print("  ✗ Telemetry disabled. No data will be sent.\n")


def consent_prompt_gui(parent: Any = None) -> None:
    """Show a one-time consent dialog in the PyQt5 GUI.

    Only runs when ``consent_shown`` is ``False``.  Uses a lazy import
    of ``PyQt5.QtWidgets`` so that non-GUI code never pulls in Qt.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget for the dialog.
    """
    cfg = _get_config()
    if cfg.consent_shown:
        return

    from PyQt5 import QtWidgets

    msg = QtWidgets.QMessageBox(parent)
    msg.setWindowTitle("TI-Toolbox — Usage Data")
    msg.setIcon(QtWidgets.QMessageBox.Question)
    msg.setText(
        "<b>Usage Data</b><br><br>"
        "TI-Toolbox can send anonymous usage data to help us "
        "identify issues and improve stability.<br><br>"
        "This includes which operations ran and whether they "
        "succeeded or failed. No personal data, file paths, or "
        "scientific results are collected.<br><br>"
        "You can disable this at any time in Settings → Privacy."
    )
    msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
    msg.button(QtWidgets.QMessageBox.Yes).setText("Enable")
    msg.button(QtWidgets.QMessageBox.No).setText("No Thanks")

    result = msg.exec_()

    cfg.enabled = result == QtWidgets.QMessageBox.Yes
    cfg.consent_shown = True
    save_config(cfg)
    _invalidate_cache()
