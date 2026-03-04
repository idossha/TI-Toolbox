"""Logging configuration for TI-Toolbox."""

import logging
import os
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root tit logger. Call once at application startup.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to INFO. Reads TI_LOG_LEVEL env var if not overridden.
    """
    root = logging.getLogger("tit")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("matplotlib.font_manager", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)


def add_file_handler(
    log_file: str | Path,
    level: str = "DEBUG",
    logger_name: str = "tit",
) -> logging.FileHandler:
    """Attach a file handler to a named logger.

    Creates the parent directory if it does not exist. Returns the handler
    so callers can remove it when the run completes.

    Args:
        log_file: Path to the log file (opened in append mode).
        level: Minimum log level for this handler. Defaults to DEBUG so the
               file captures everything.
        logger_name: Logger to attach to. Defaults to the root "tit" logger.

    Returns:
        The created FileHandler instance.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(log_file), mode="a")
    fh.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logging.getLogger(logger_name).addHandler(fh)
    return fh
