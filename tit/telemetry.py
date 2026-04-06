"""Anonymous usage telemetry for TI-Toolbox.

Collects minimal, non-identifying usage data to help the development team
understand feature adoption, platform distribution, and error rates.  All
network calls are fire-and-forget in daemon threads — they never block or
crash the user's workflow.

Collected Data
--------------
- TI-Toolbox version, Python version, OS / platform
- Operation type (``sim_ti``, ``sim_mti``, ``flex_search``, etc.)
- Operation status (``start``, ``success``, ``error``)
- Error class name on failure (e.g. ``ValueError`` — **no** tracebacks)
- Anonymous client ID (random UUID, stored locally)
- Approximate country via GA4 IP-based geolocation (IP is anonymised by Google)

**Not** collected: file paths, subject IDs, parameter values, hostnames,
usernames, tracebacks, or any scientific data.

Opt-Out
-------
1. Environment variable: ``TIT_NO_TELEMETRY=1``
2. Config file: ``~/.config/ti-toolbox/telemetry.json`` → ``"enabled": false``
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
import sys
import threading
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


def _config_path() -> Path:
    """Return the path to the telemetry config file.

    Uses ``~/.config/ti-toolbox/telemetry.json`` on all platforms (XDG
    convention).  Creates the parent directory if it does not exist.

    Returns
    -------
    pathlib.Path
        Absolute path to the JSON config file.
    """
    config_dir = Path.home() / ".config" / const.TELEMETRY_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / const.TELEMETRY_CONFIG_FILE


def load_config() -> TelemetryConfig:
    """Load telemetry config from disk, or return defaults.

    Returns
    -------
    TelemetryConfig
        Loaded or default configuration.
    """
    path = _config_path()
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

    Sets file permissions to ``0o600`` (owner read/write only).

    Parameters
    ----------
    config : TelemetryConfig
        Configuration to write.
    """
    path = _config_path()
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

    Parameters
    ----------
    enabled : bool
        ``True`` to enable, ``False`` to disable.
    """
    cfg = _get_config()
    cfg.enabled = enabled
    cfg.consent_shown = True
    save_config(cfg)
    _invalidate_cache()


# ---------------------------------------------------------------------------
# System parameters (attached to every event)
# ---------------------------------------------------------------------------


def _system_params() -> dict[str, str]:
    """Return a dict of non-identifying system metadata.

    Returns
    -------
    dict[str, str]
        Keys: ``tit_version``, ``python_version``, ``os_name``,
        ``os_version``, ``platform``.
    """
    return {
        "tit_version": tit.__version__,
        "python_version": platform.python_version(),
        "os_name": platform.system(),
        "os_version": platform.release(),
        "platform": platform.machine(),
    }


# ---------------------------------------------------------------------------
# GA4 Measurement Protocol sender
# ---------------------------------------------------------------------------


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
        with urllib.request.urlopen(req, timeout=const.TELEMETRY_TIMEOUT_S):
            pass  # GA4 MP returns 204 No Content on success
    except (urllib.error.URLError, OSError, ValueError):
        pass  # Network issues, firewall, DNS — silently drop


def track_event(
    event_name: str,
    params: dict[str, str] | None = None,
) -> None:
    """Send a single GA4 event in a background daemon thread.

    Does nothing if telemetry is disabled.

    Parameters
    ----------
    event_name : str
        GA4 event name (e.g. ``"sim_ti"``, ``"gui_launch"``).
        Must be ≤40 chars, alphanumeric + underscores.
    params : dict[str, str], optional
        Extra event parameters.  System params (OS, version, etc.) are
        merged in automatically.

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
    try:
        yield
    except Exception as exc:
        track_event(op_name, {"status": "error", "error_type": type(exc).__name__})
        raise
    else:
        track_event(op_name, {"status": "success"})


# ---------------------------------------------------------------------------
# Consent prompts
# ---------------------------------------------------------------------------

_CONSENT_BANNER = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TI-Toolbox — Anonymous Usage Statistics

  TI-Toolbox can collect anonymous usage data to
  help us improve the software. We collect:

    • OS, Python version, TI-Toolbox version
    • Which operations you run (simulation,
      optimization, analysis)
    • Whether operations succeed or fail

  We do NOT collect any personal information,
  file paths, subject data, or scientific results.

  You can change this at any time:
    • Set  TIT_NO_TELEMETRY=1  in your environment
    • Edit ~/.config/ti-toolbox/telemetry.json
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
    msg.setWindowTitle("TI-Toolbox — Usage Statistics")
    msg.setIcon(QtWidgets.QMessageBox.Question)
    msg.setText(
        "<b>Anonymous Usage Statistics</b><br><br>"
        "TI-Toolbox can collect anonymous usage data to help us "
        "improve the software.<br><br>"
        "<b>We collect:</b><br>"
        "• OS, Python version, TI-Toolbox version<br>"
        "• Which operations you run (simulation, optimization, analysis)<br>"
        "• Whether operations succeed or fail<br><br>"
        "<b>We do NOT collect</b> any personal information, file paths, "
        "subject data, or scientific results.<br><br>"
        "You can change this at any time in Settings → Privacy."
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
