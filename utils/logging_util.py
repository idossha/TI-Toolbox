import logging
import sys
from typing import List, Optional

# ----------------------------------------------------------------------------
# Configuration constants
# ----------------------------------------------------------------------------
LOG_LEVEL = logging.INFO
FILE_FORMAT = '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
CONSOLE_FORMAT = '%(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------
def _cleanup_handlers(logger: logging.Logger) -> None:
    """
    Remove and close all handlers attached to the given logger.
    """
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _copy_handler(handler: logging.Handler) -> logging.Handler:
    """
    Create a fresh handler of the same type as 'handler', preserving its formatter and level.
    """
    if isinstance(handler, logging.FileHandler):
        new_handler = logging.FileHandler(handler.baseFilename, mode=handler.mode)
    elif isinstance(handler, logging.StreamHandler):
        new_handler = logging.StreamHandler(sys.stdout)
    else:
        # Fallback: instantiate same class without args
        new_handler = handler.__class__()

    new_handler.setLevel(handler.level)
    if handler.formatter:
        new_handler.setFormatter(handler.formatter)
    return new_handler

# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
def get_logger(name: str,
               log_file: Optional[str] = None,
               overwrite: bool = True) -> logging.Logger:
    """
    Create or retrieve a named logger configured with a console handler and
    an optional file handler.

    Args:
        name:      the logger's name/name-space
        log_file:  path to a file to log into; if None, no file handler is added
        overwrite: if True, open the file in 'w' mode; otherwise append

    Returns:
        A logging.Logger instance, with propagation disabled.
    """
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    # clean out any existing handlers
    _cleanup_handlers(logger)

    # console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    logger.addHandler(console_handler)

    # optional file handler
    if log_file:
        mode = 'w' if overwrite else 'a'
        file_handler = logging.FileHandler(log_file, mode=mode)
        file_handler.setLevel(LOG_LEVEL)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def configure_external_loggers(names: List[str],
                               parent_logger: logging.Logger) -> None:
    """
    Redirect logs from external loggers into the same handlers used by 'parent_logger'.

    Args:
        names: list of logger names (e.g. ['simnibs', 'mesh_io'])
        parent_logger: a logger whose handlers/levels we want to mirror
    """
    for name in names:
        ext_logger = logging.getLogger(name)
        ext_logger.setLevel(parent_logger.level)
        ext_logger.propagate = False

        # remove old handlers
        _cleanup_handlers(ext_logger)

        # attach copies of the parent's handlers
        for handler in parent_logger.handlers:
            ext_logger.addHandler(_copy_handler(handler))
