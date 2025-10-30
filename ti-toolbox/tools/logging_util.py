import logging
import sys
import os
from typing import List, Optional
from datetime import datetime

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

class HostTimestampFormatter(logging.Formatter):
    """Custom formatter that uses host timestamp from environment variable."""

    def formatTime(self, record, datefmt=None):
        """Override formatTime to use host timestamp."""
        host_timestamp = os.environ.get('HOST_TIMESTAMP')
        if host_timestamp:
            # Extract just the time part from host timestamp (HH:MM:SS)
            # Format is like: "Thu Oct 30 13:57:36 CDT 2025"
            try:
                # Split by spaces and get the time part (index 3)
                parts = host_timestamp.split()
                if len(parts) >= 4:
                    time_part = parts[3]
                    return time_part
            except (IndexError, AttributeError):
                pass
        # Fallback to default formatting
        return super().formatTime(record, datefmt)


class CallbackHandler(logging.Handler):
    """Custom handler that redirects log messages to a callback function.
    
    Useful for GUI applications where log messages need to be displayed
    in a custom console widget rather than stdout/stderr.
    """
    
    def __init__(self, callback):
        """
        Initialize callback handler.
        
        Args:
            callback: Function with signature callback(message: str, msg_type: str)
                     where msg_type is one of: 'error', 'warning', 'info', 'debug'
        """
        super().__init__()
        self.callback = callback
    
    def emit(self, record):
        """Emit a record by calling the callback with formatted message."""
        try:
            msg = self.format(record)
            if self.callback:
                # Map log level to message type
                if record.levelno >= logging.ERROR:
                    msg_type = 'error'
                elif record.levelno >= logging.WARNING:
                    msg_type = 'warning'
                elif record.levelno >= logging.DEBUG:
                    msg_type = 'debug'
                else:
                    msg_type = 'info'
                self.callback(msg, msg_type)
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
        file_handler.setFormatter(HostTimestampFormatter(FILE_FORMAT, datefmt=DATE_FORMAT))
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


def suppress_console_output(logger: logging.Logger) -> None:
    """
    Remove console/stdout handlers from a logger, keeping only file handlers.
    
    This is useful in GUI contexts where you want logs to go to a file
    but not to the terminal.
    
    Args:
        logger: Logger instance to modify
    """
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)


def add_callback_handler(logger: logging.Logger,
                         callback,
                         level: int = logging.INFO) -> CallbackHandler:
    """
    Add a callback handler to a logger for GUI integration.
    
    Args:
        logger: Logger instance to modify
        callback: Function with signature callback(message: str, msg_type: str)
        level: Minimum log level for the handler
    
    Returns:
        The created CallbackHandler instance
    """
    handler = CallbackHandler(callback)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    logger.addHandler(handler)
    return handler


def get_file_only_logger(name: str,
                         log_file: str,
                         level: int = logging.INFO) -> logging.Logger:
    """
    Create a file-only logger (no console output).
    
    Useful for logging detailed information to file without cluttering
    the GUI console with verbose details.
    
    Args:
        name: Logger name
        log_file: Path to log file (will append)
        level: Minimum log level
    
    Returns:
        Logger instance configured with only a file handler
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    
    # Remove any existing handlers
    _cleanup_handlers(logger)
    
    # Add only file handler (no console handler)
    file_handler = FlushingFileHandler(log_file, mode='a')
    file_handler.setLevel(level)
    file_handler.setFormatter(HostTimestampFormatter(FILE_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(file_handler)
    
    return logger
