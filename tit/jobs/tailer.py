"""Reading ``events.jsonl`` (TODO.md §2.3): full parse for backfill, incremental poll for live
push.

``seq`` is the 0-based line index — assigned here, not trusted from the file, so a line a writer
managed to corrupt (or a stray non-JSON line) doesn't shift every later ``seq``. Polling is by
``st_size`` (inotify is unreliable on Docker Desktop bind mounts, per TODO.md §2.3) at whatever
cadence the caller chooses (the manager's background loop uses 250 ms).
"""

from __future__ import annotations

import json
import os
from typing import Any


def read_events(path: str, since: int = 0) -> list[dict[str, Any]]:
    """Every event in *path* with ``seq >= since`` (``seq`` = line index, malformed lines
    skipped but still counted so ``seq`` stays a stable line-index across repeated reads).
    """
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if i < since:
                    continue
                if not isinstance(obj, dict):
                    continue
                obj["seq"] = i
                events.append(obj)
    except OSError:
        pass
    return events


def line_count(path: str) -> int:
    """Number of non-blank lines currently in *path* (next event's ``seq``)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


class EventTailer:
    """Incrementally polls one ``events.jsonl`` for events appended since the last poll."""

    def __init__(self, path: str, start_seq: int = 0) -> None:
        self.path = path
        self._next_seq = start_seq
        self._last_size = -1

    def poll(self) -> list[dict[str, Any]]:
        try:
            size = os.stat(self.path).st_size
        except OSError:
            return []
        if size == self._last_size:
            return []
        self._last_size = size
        events = read_events(self.path, since=self._next_seq)
        if events:
            self._next_seq = events[-1]["seq"] + 1
        return events
