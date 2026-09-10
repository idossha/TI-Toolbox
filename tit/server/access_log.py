"""Mask ``?token=`` values in uvicorn's log lines.

The launcher's one-time ``GET /auth/session?token=…`` and the WebSocket
``?token=`` fallback would otherwise print the shared secret into the access
log (``uvicorn.access``) and the handshake log (``uvicorn.error``).
"""

from __future__ import annotations

import logging
import re

_TOKEN_RE = re.compile(r"(token=)[^&\s\"']*")
MASK = r"\1***"


def mask_token(text: str) -> str:
    """``…?token=abc&x=1`` → ``…?token=***&x=1``."""
    return _TOKEN_RE.sub(MASK, text)


class TokenMaskFilter(logging.Filter):
    """Rewrite ``token=<value>`` in the record's message and string args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_token(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                mask_token(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: mask_token(val) if isinstance(val, str) else val
                for key, val in record.args.items()
            }
        return True
