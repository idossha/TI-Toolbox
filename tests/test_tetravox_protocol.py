"""E1 — the protocol range and the feature map are one table, in two languages.

The server decides what may be installed and what ``/api/capabilities`` reports;
the renderer decides what a pane may ask for.  Both need the same table, and
nothing in a build catches them disagreeing -- a renderer that thinks ``markers``
arrives at protocol 3 simply hides a control that works.  So this test reads the
TypeScript file off disk and compares it with the Python module, the way
``testing-backend``'s rule 11 pairs a wall with a guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tit.tetravox import protocol

TS_PATH = (
    Path(__file__).resolve().parents[1]
    / "desktop"
    / "src"
    / "renderer"
    / "viewer"
    / "embedProtocol.ts"
)


@pytest.fixture(scope="module")
def ts_source() -> str:
    assert TS_PATH.is_file(), f"the renderer half of E1 is missing: {TS_PATH}"
    return TS_PATH.read_text(encoding="utf-8")


def test_the_supported_range_matches_the_renderer(ts_source: str) -> None:
    match = re.search(
        r"SUPPORTED_EMBED_PROTOCOL\s*=\s*\{\s*min:\s*(\d+),\s*max:\s*(\d+)\s*\}",
        ts_source,
    )
    assert match, "SUPPORTED_EMBED_PROTOCOL not found in embedProtocol.ts"
    assert (int(match.group(1)), int(match.group(2))) == (
        protocol.SUPPORTED_PROTOCOL_MIN,
        protocol.SUPPORTED_PROTOCOL_MAX,
    )


def test_the_feature_map_matches_the_renderer(ts_source: str) -> None:
    block = re.search(
        r"EMBED_FEATURE_MIN_PROTOCOL\s*=\s*\{(.*?)\}\s*as const", ts_source, re.S
    )
    assert block, "EMBED_FEATURE_MIN_PROTOCOL not found in embedProtocol.ts"
    ts_map = {
        name: int(level)
        for name, level in re.findall(r"(\w+):\s*(\d+)", block.group(1))
    }
    assert ts_map == protocol.FEATURE_MIN_PROTOCOL


def test_the_range_covers_every_feature_level() -> None:
    """A feature nothing in range provides is a name no embed can ever satisfy."""
    for name, level in protocol.FEATURE_MIN_PROTOCOL.items():
        assert (
            protocol.SUPPORTED_PROTOCOL_MIN <= level <= protocol.SUPPORTED_PROTOCOL_MAX
        ), name


def test_protocol_supported_rejects_non_integers() -> None:
    assert protocol.protocol_supported(1) and protocol.protocol_supported(2)
    # 3 is Tetravox 0.4.0's surface layer kind, and is now in range.
    assert protocol.protocol_supported(3)
    for value in (0, 4, None, "1", 1.5, True):
        assert not protocol.protocol_supported(value), value
