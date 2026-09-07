"""E1 — the app pins a protocol **range** and named **features**, never a version.

This module is the single place on the Python side that says which Tetravox embed
protocol versions this build can host and which named capability each protocol
level brings.  The renderer's half is
``desktop/src/renderer/viewer/embedProtocol.ts``; ``tests/test_tetravox_protocol.py``
reads both files off disk and fails if they disagree, because two hand-maintained
copies of a compatibility table drift the first time one of them is edited alone
(house rule 11: a lint is a wall, a test that reads the source is the guard).

**Why a range and not a version.**  Before this, the only thing that decided which
viewer the app could talk to was the directory baked into the image, so shipping a
Tetravox release meant shipping a TI-Toolbox release.  With a range, an *additive*
Tetravox release (see the plan's E5: protocol 2 adds a points layer, a point tool,
a pick event and camera get/set, and every protocol-1 message keeps working) is
installable and usable with **no change to this repository at all** — the new
protocol number is already inside ``SUPPORTED``, and any feature it brings is
either already named in ``FEATURE_MIN_PROTOCOL`` or declared by the embed's own
manifest (``features``), which :func:`features_for` passes through verbatim.
"""

from __future__ import annotations

from typing import Any

#: Inclusive range of embed protocol versions this build can host.
#:
#: ``min`` is 1 because the Viewer (``desktop/src/renderer/viewer/``) is a
#: protocol-1 host today and an installed embed must never strand it.  ``max`` is
#: 2 because protocol 2 is additive over 1 (plan E5): a protocol-2 embed answers
#: every protocol-1 message unchanged, so hosting one costs this side nothing.
#: Raising ``max`` is the only edit a *breaking* Tetravox release needs here.
SUPPORTED_PROTOCOL_MIN = 1
SUPPORTED_PROTOCOL_MAX = 2

#: Named feature -> the lowest protocol that provides it.
#:
#: Panes and pages ask for a *name* ("can this embed do markers?"), never for a
#: number, so a feature moving to a different protocol level is one edit here and
#: one in the TypeScript twin.  Entries at 1 are the protocol-1 surface the Viewer
#: already drives; entries at 2 are the plan's E5 additions the run-page panes
#: (lane M) will gate on.
FEATURE_MIN_PROTOCOL: dict[str, int] = {
    "volumes": 1,
    "meshes": 1,
    "cursor": 1,
    "probe": 1,
    "screenshot": 1,
    "layers": 1,
    "markers": 2,
    "pick": 2,
    "camera": 2,
}


def protocol_supported(protocol: Any) -> bool:
    """Is *protocol* an integer inside the supported range?

    Anything that is not an ``int`` (missing, a string, a float that is not whole)
    is **not** supported: a manifest that cannot say which protocol it speaks is
    a manifest this host cannot promise to drive.  ``bool`` is rejected too --
    ``True`` is an ``int`` in Python and ``protocol: true`` is not a protocol.
    """
    if isinstance(protocol, bool) or not isinstance(protocol, int):
        return False
    return SUPPORTED_PROTOCOL_MIN <= protocol <= SUPPORTED_PROTOCOL_MAX


def features_for(protocol: Any, declared: Any = None) -> tuple[str, ...]:
    """The feature names an embed at *protocol* offers, sorted.

    *declared* is the embed manifest's own optional ``features`` array.  When it
    is a list of strings it is authoritative and returned as-is (deduplicated and
    sorted): a future Tetravox release can then name a feature this build has
    never heard of and a pane that asks for it by name works without a
    TI-Toolbox change -- which is the whole point of E1.  Otherwise the names are
    derived from :data:`FEATURE_MIN_PROTOCOL`.
    """
    if isinstance(declared, list):
        names = {item for item in declared if isinstance(item, str) and item}
        if names:
            return tuple(sorted(names))
    if isinstance(protocol, bool) or not isinstance(protocol, int):
        return ()
    return tuple(
        sorted(
            name
            for name, minimum in FEATURE_MIN_PROTOCOL.items()
            if protocol >= minimum
        )
    )


def supported_range() -> dict[str, int]:
    """``{"min": …, "max": …}`` — the shape ``/api/capabilities`` publishes."""
    return {"min": SUPPORTED_PROTOCOL_MIN, "max": SUPPORTED_PROTOCOL_MAX}
