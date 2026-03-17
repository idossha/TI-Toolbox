"""Logging configuration for TI-Toolbox."""


import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Silence noisy third-party loggers at import time (before setup_logging is called)
for _name in ("matplotlib", "matplotlib.font_manager", "PIL"):
    logging.getLogger(_name).setLevel(logging.ERROR)


def setup_logging(level: str = "INFO") -> None:
    """Configure the ``tit`` logger hierarchy.

    Sets the log level but adds NO handlers — file handlers are attached
    later via ``add_file_handler()`` and GUI handlers via Qt signal bridges.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to INFO.
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


def add_stream_handler(
    logger_name: str = "tit",
    level: str = "INFO",
) -> logging.StreamHandler:
    """Attach a stdout handler to a named logger.

    Used by scripts for terminal output and by ``__main__`` entry points
    so that ``BaseProcessThread`` can capture subprocess stdout for the GUI.

    Args:
        logger_name: Logger to attach to. Defaults to ``"tit"``.
        level: Minimum log level. Defaults to INFO.

    Returns:
        The created StreamHandler instance.
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
    """Return a logger that writes ONLY to *log_file* — no console output.

    If a logger with *name* already exists its handlers are replaced so that
    repeated calls (e.g. across ROIs) always point at the correct file.

    Args:
        name: Logger name (should be unique per use-case).
        log_file: Path to the log file.
        level: Minimum log level. Defaults to DEBUG.

    Returns:
        A configured :class:`logging.Logger`.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    logger.propagate = False  # never bubble to root/terminal
    add_file_handler(log_file, level=level, logger_name=name)
    return logger
