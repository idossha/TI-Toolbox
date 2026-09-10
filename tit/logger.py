"""Logging configuration for TI-Toolbox.

Configures the ``tit`` logger hierarchy with a handler-free design:
:func:`setup_logging` sets the log level and silences noisy third-party
loggers, but attaches **no** handlers of its own beyond the opt-in JSON
event sink described below.  Handlers are added on demand via
:func:`add_file_handler`, :func:`add_stream_handler`, or the Qt signal
bridge in the GUI.

When ``$TIT_EVENTS_FILE`` is set (a runner launched as a job by
``tit.server``), :func:`setup_logging` also attaches a
:class:`JsonEventHandler` to the ``tit`` and ``simnibs`` loggers, so every
log record becomes a ``type: "log"`` line in that job's ``events.jsonl``
(``contracts/events.schema.json``) with no per-runner code changes. The
same sink backs ``tit.jobs.events``'s structured stage/progress/artifact/
result/exit helpers, so the two interleave into one ordered stream.

Public API
----------
setup_logging
    Set the package-wide log level; attaches a JSON event handler too when
    ``$TIT_EVENTS_FILE`` is set.
add_file_handler
    Attach a :class:`~logging.FileHandler` to a named logger (de-duplicated
    per (logger, path) pair).
add_stream_handler
    Attach a :class:`~logging.StreamHandler` (stdout) to a named logger.
get_file_only_logger
    Return a logger that writes **only** to a file (no console).
get_event_sink
    Return (creating on first call) the process-wide :class:`JsonEventSink`
    for ``$TIT_EVENTS_FILE``, or ``None`` when unset.
JsonEventSink, JsonEventHandler
    The sink and logging handler backing the above.

Module Attributes
-----------------
LOG_FORMAT : str
    Default format string for file handlers.
DATE_FORMAT : str
    Date format used in log timestamps.
TIT_EVENTS_FILE_ENV : str
    Name of the environment variable that turns on JSON event emission.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Env var read by :func:`setup_logging`; when set, a :class:`JsonEventHandler`
#: is attached to the ``tit`` and ``simnibs`` loggers so every log record also
#: becomes a ``type: "log"`` line in the job's ``events.jsonl``
#: (``contracts/events.schema.json``). See ``tit.jobs.events`` for the
#: structured (stage/progress/artifact/result/exit) event helpers, which
#: share this same sink.
TIT_EVENTS_FILE_ENV = "TIT_EVENTS_FILE"

#: Hard per-line cap from ``contracts/events.schema.json`` / the v3 build
#: plan ("one JSON object per line <= 4 KB").
_EVENT_LINE_LIMIT = 4096

# Silence noisy third-party loggers at import time (before setup_logging is called)
for _name in ("matplotlib", "matplotlib.font_manager", "PIL"):
    logging.getLogger(_name).setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# JSON event sink -- shared by JsonEventHandler (log events) and
# tit.jobs.events (structured stage/progress/artifact/result/exit events),
# so every line in one job's events.jsonl shares one monotonic `seq`.
# ---------------------------------------------------------------------------


class JsonEventSink:
    """Append-only JSON-lines writer for one job's ``events.jsonl``.

    Opened ``O_APPEND`` (safe for concurrent short writes), one JSON object
    per line, flushed on every write. Assigns a process-wide monotonic
    ``seq`` and a ``ts`` (unix seconds) to every record, so callers only
    supply the event-specific fields.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to ``events.jsonl`` (typically ``$TIT_EVENTS_FILE``).

    See Also
    --------
    get_event_sink : Process-wide singleton accessor, keyed by path.
    JsonEventHandler : Feeds ``log`` records into a sink.
    tit.jobs.events : Structured event helpers that write through a sink.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._fd = os.open(
            str(self._path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644
        )

    def write(self, event: dict[str, Any]) -> None:
        """Append one event, filling in ``seq`` and ``ts``.

        Parameters
        ----------
        event : dict
            Event-specific fields (e.g. ``{"type": "stage", "stage": "charm"}``).
            ``seq`` and ``ts`` are added here and must not be passed in.
        """
        with self._lock:
            record = {"seq": self._seq, "ts": time.time(), **event}
            self._seq += 1
            line = _render_capped(record)
            os.write(self._fd, (line + "\n").encode("utf-8"))

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


def _render_capped(record: dict[str, Any], limit: int = _EVENT_LINE_LIMIT) -> str:
    """Serialise *record* to one JSON line, truncating ``msg`` if oversized.

    A log line from a chatty tool (a full traceback, a long stdout line)
    is the only field realistically large enough to blow the 4 KB budget;
    every other field is a short scalar. Truncating ``msg`` first keeps the
    record's structure (``type``, ``level``, ``logger``, ...) intact instead
    of dropping the line.
    """
    line = json.dumps(record, default=str)
    if len(line.encode("utf-8")) <= limit or "msg" not in record:
        return line
    # Reserve headroom for the rest of the record plus the truncation marker.
    overhead = len(line.encode("utf-8")) - len(str(record["msg"]).encode("utf-8"))
    budget = max(limit - overhead - len(b"...[truncated]"), 0)
    truncated = record["msg"].encode("utf-8")[:budget].decode("utf-8", "ignore")
    record = {**record, "msg": truncated + "...[truncated]"}
    return json.dumps(record, default=str)


_event_sinks_lock = threading.Lock()
_event_sinks: dict[str, JsonEventSink] = {}


def get_event_sink(path: str | None = None) -> JsonEventSink | None:
    """Return the process-wide :class:`JsonEventSink` for *path*, or ``None``.

    Parameters
    ----------
    path : str or None, optional
        Defaults to ``$TIT_EVENTS_FILE``. Returns ``None`` when neither is
        set -- the standard no-op case for a script/notebook/CLI run with no
        job wrapper.

    Returns
    -------
    JsonEventSink or None
        The sink for *path*, created on first call and cached for the
        life of the process (so :class:`JsonEventHandler` and
        ``tit.jobs.events``'s ``emit_*`` helpers share one ``seq`` counter).
    """
    path = path or os.environ.get(TIT_EVENTS_FILE_ENV)
    if not path:
        return None
    with _event_sinks_lock:
        sink = _event_sinks.get(path)
        if sink is None:
            sink = JsonEventSink(path)
            _event_sinks[path] = sink
        return sink


class JsonEventHandler(logging.Handler):
    """Logging handler that appends each record as a ``type: "log"`` event.

    Parameters
    ----------
    sink : JsonEventSink
        Destination sink (see :func:`get_event_sink`).
    """

    def __init__(self, sink: JsonEventSink) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging crash the runner
            msg = str(getattr(record, "msg", ""))
        try:
            self._sink.write(
                {
                    "type": "log",
                    "level": record.levelname.lower(),
                    "logger": record.name,
                    "msg": msg,
                }
            )
        except OSError:
            # A dead/removed events file must never crash the runner.
            pass


def setup_logging(level: str = "INFO") -> None:
    """Configure the ``tit`` logger hierarchy.

    Sets the log level but adds **no** handlers of its own — file handlers
    are attached later via :func:`add_file_handler` and GUI handlers via Qt
    signal bridges. The one exception: when ``$TIT_EVENTS_FILE`` is set, a
    :class:`JsonEventHandler` is attached to both the ``tit`` and
    ``simnibs`` loggers (flex/ex/mex/sim already attach their own file
    handlers to ``simnibs`` -- that is where FEM solver progress goes) so
    every log record also becomes a ``type: "log"`` line in the job's
    ``events.jsonl``, with no per-runner changes needed for plain log
    output. Structured events (stage/progress/artifact/result/exit) are
    emitted separately via ``tit.jobs.events``, through the same sink.

    Parameters
    ----------
    level : str, optional
        Logging level name (e.g., ``"DEBUG"``, ``"INFO"``).  Default is
        ``"INFO"``.

    See Also
    --------
    add_file_handler : Attach a file handler to a named logger.
    add_stream_handler : Attach a console handler to a named logger.
    get_event_sink : The sink a JsonEventHandler writes through.
    """
    logger = logging.getLogger("tit")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False  # never bubble to root/terminal

    # Quiet noisy third-party loggers
    for name in ("matplotlib", "matplotlib.font_manager", "PIL"):
        logging.getLogger(name).setLevel(logging.ERROR)

    sink = get_event_sink()
    if sink is not None:
        for logger_name in ("tit", "simnibs"):
            target = logging.getLogger(logger_name)
            if not any(isinstance(h, JsonEventHandler) for h in target.handlers):
                handler = JsonEventHandler(sink)
                handler.setLevel(logging.DEBUG)
                target.addHandler(handler)
    else:
        logging.getLogger("tit.logger").debug(
            f"${TIT_EVENTS_FILE_ENV} not set; no JsonEventHandler attached"
        )


def add_file_handler(
    log_file: str | Path,
    level: str = "DEBUG",
    logger_name: str = "tit",
) -> logging.FileHandler:
    """Attach a file handler to a named logger.

    Creates the parent directory if it does not exist.  Returns the handler
    so callers can remove it when the run completes.

    Parameters
    ----------
    log_file : str or pathlib.Path
        Path to the log file (opened in append mode).
    level : str, optional
        Minimum log level for this handler.  Default is ``"DEBUG"`` so the
        file captures everything.
    logger_name : str, optional
        Logger to attach to.  Default is ``"tit"`` (the package root).

    Returns
    -------
    logging.FileHandler
        The handler for *log_file* on *logger_name* -- newly created, or the
        existing one if this exact (logger, path) pair was already attached
        (a long-lived process, e.g. one ROI loop calling this per iteration,
        would otherwise leak one handler -- and one open file descriptor --
        per call).

    See Also
    --------
    setup_logging : Set the package-wide log level.
    add_stream_handler : Attach a console (stdout) handler.
    get_file_only_logger : Create an isolated file-only logger.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    resolved = str(log_file.resolve())
    for existing in logger.handlers:
        if (
            isinstance(existing, logging.FileHandler)
            and getattr(existing, "baseFilename", None) == resolved
        ):
            return existing
    fh = logging.FileHandler(str(log_file), mode="a")
    fh.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(fh)
    return fh


def add_stream_handler(
    logger_name: str = "tit",
    level: str = "INFO",
) -> logging.StreamHandler:
    """Attach a stdout handler to a named logger.

    Used by scripts for terminal output and by ``__main__`` entry points
    so that ``BaseProcessThread`` can capture subprocess stdout for the GUI.

    Parameters
    ----------
    logger_name : str, optional
        Logger to attach to.  Default is ``"tit"``.
    level : str, optional
        Minimum log level.  Default is ``"INFO"``.

    Returns
    -------
    logging.StreamHandler
        The newly created handler.

    See Also
    --------
    setup_logging : Set the package-wide log level.
    add_file_handler : Attach a file handler.
    """
    import sys

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    return handler


def get_file_only_logger(
    name: str,
    log_file: str | Path,
    level: str = "DEBUG",
) -> logging.Logger:
    """Return a logger that writes **only** to *log_file* — no console output.

    If a logger with *name* already exists its handlers are replaced so that
    repeated calls (e.g., across ROIs) always point at the correct file.

    Parameters
    ----------
    name : str
        Logger name (should be unique per use-case).
    log_file : str or pathlib.Path
        Path to the log file.
    level : str, optional
        Minimum log level.  Default is ``"DEBUG"``.

    Returns
    -------
    logging.Logger
        A configured logger with a single file handler and
        ``propagate=False``.

    See Also
    --------
    add_file_handler : Lower-level helper used internally.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    logger.propagate = False  # never bubble to root/terminal
    add_file_handler(log_file, level=level, logger_name=name)
    return logger
