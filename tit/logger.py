"""Logging configuration for TI-Toolbox.

Configures the ``tit`` logger hierarchy with a handler-free design:
:func:`setup_logging` sets the log level and silences noisy third-party
loggers, but attaches **no** handlers.  Handlers are added on demand via
:func:`add_file_handler`, :func:`add_stream_handler`, or the Qt signal
bridge in the GUI.

Public API
----------
setup_logging
    Set the package-wide log level (no handlers attached).
add_file_handler
    Attach a :class:`~logging.FileHandler` to a named logger.
add_stream_handler
    Attach a :class:`~logging.StreamHandler` (stdout) to a named logger.
get_file_only_logger
    Return a logger that writes **only** to a file (no console).

Module Attributes
-----------------
LOG_FORMAT : str
    Default format string for file handlers.
DATE_FORMAT : str
    Date format used in log timestamps.
"""

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Silence noisy third-party loggers at import time (before setup_logging is called)
for _name in ("matplotlib", "matplotlib.font_manager", "PIL"):
    logging.getLogger(_name).setLevel(logging.ERROR)


def setup_logging(level: str = "INFO") -> None:
    """Configure the ``tit`` logger hierarchy.

    Sets the log level but adds **no** handlers — file handlers are attached
    later via :func:`add_file_handler` and GUI handlers via Qt signal bridges.

    Parameters
    ----------
    level : str, optional
        Logging level name (e.g., ``"DEBUG"``, ``"INFO"``).  Default is
        ``"INFO"``.

    See Also
    --------
    add_file_handler : Attach a file handler to a named logger.
    add_stream_handler : Attach a console handler to a named logger.
    """
    logger = logging.getLogger("tit")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False  # never bubble to root/terminal

    # Quiet noisy third-party loggers
    for name in ("matplotlib", "matplotlib.font_manager", "PIL"):
        logging.getLogger(name).setLevel(logging.ERROR)


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
        The newly created handler.

    See Also
    --------
    setup_logging : Set the package-wide log level.
    add_stream_handler : Attach a console (stdout) handler.
    get_file_only_logger : Create an isolated file-only logger.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(log_file), mode="a")
    fh.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logging.getLogger(logger_name).addHandler(fh)
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
