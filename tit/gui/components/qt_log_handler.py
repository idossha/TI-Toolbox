"""Qt logging handler — bridges Python logging to a PyQt5 signal."""

import logging


class QtLogHandler(logging.Handler):
    """Route Python logging records to a PyQt5 output signal.

    Usage::

        handler = QtLogHandler(self.output_signal)
        logging.getLogger("tit").addHandler(handler)
        # later:
        logging.getLogger("tit").removeHandler(handler)

    The signal must have signature ``(str, str)`` — message, message_type.
    message_type is one of: 'error', 'warning', 'info', 'debug', 'default'.
    """

    _LEVEL_TO_TYPE = {
        logging.ERROR: "error",
        logging.CRITICAL: "error",
        logging.WARNING: "warning",
        logging.DEBUG: "debug",
        logging.INFO: "info",
    }

    def __init__(self, signal, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            msg_type = self._LEVEL_TO_TYPE.get(record.levelno, "default")
            self._signal.emit(msg, msg_type)
        except Exception:
            self.handleError(record)
