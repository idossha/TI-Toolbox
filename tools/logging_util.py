import logging
import sys
import os
from typing import List, Optional

# ----------------------------------------------------------------------------
# Custom handler for real-time output
# ----------------------------------------------------------------------------
class FlushingStreamHandler(logging.StreamHandler):
    """Custom StreamHandler that forces immediate flushing for real-time output."""
    
    def emit(self, record):
        """Emit a record and force flush immediately."""
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)

class FlushingFileHandler(logging.FileHandler):
    """Custom FileHandler that forces immediate flushing for real-time output."""
    
    def emit(self, record):
        """Emit a record and force flush immediately."""
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
# Console always INFO for clean UI; file level can be overridden via env
_LEVEL_BY_NAME = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
}

FILE_LOG_LEVEL = _LEVEL_BY_NAME.get(os.environ.get('TI_LOG_LEVEL', 'INFO').upper(), logging.INFO)
CONSOLE_LOG_LEVEL = logging.INFO
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
        # Always use append mode for external loggers to avoid overwriting
        new_handler = logging.FileHandler(handler.baseFilename, mode='a')
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
    # Set to lowest level; handlers control effective levels
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # clean out any existing handlers
    _cleanup_handlers(logger)

    # console handler
    console_handler = FlushingStreamHandler(sys.stdout)
    console_handler.setLevel(CONSOLE_LOG_LEVEL)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    # Force immediate flushing for real-time GUI updates
    console_handler.stream.reconfigure(line_buffering=True) if hasattr(console_handler.stream, 'reconfigure') else None
    logger.addHandler(console_handler)

    # optional file handler
    if log_file:
        mode = 'w' if overwrite else 'a'
        file_handler = FlushingFileHandler(log_file, mode=mode)
        file_handler.setLevel(FILE_LOG_LEVEL)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
        # Force immediate flushing for file output too
        if hasattr(file_handler.stream, 'reconfigure'):
            file_handler.stream.reconfigure(line_buffering=True)
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
