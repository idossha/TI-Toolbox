"""``TVSL1`` — the wire format of streamlines for the run-page panes.

The sibling of :mod:`tit.scene.tvsc`, little-endian throughout::

    offset size    field
    0      4       magic b"TVSL"
    4      4       u32 version = 1
    8      4       u32 streamlineCount (S)
    12     4       u32 pointCount      (P)
    16     4       u32 flags           bit0 = per-streamline group ids follow
    20     12      reserved (zero)
    32     12*P    float32 positions, world-RAS mm, x y z
    ...    4*(S+1) uint32 offsets      streamline i is points offsets[i]..offsets[i+1]
    ...    4*S     uint32 streamline index (in the whole tractogram, stable across subsampling)
    ...    4*S     uint32 group        when flags bit0

No scalars: the pane is a form control and colours a line by its edge's swatch (decision S1).
Pure ``numpy``, like its sibling, so the host suite exercises the bytes the browser parses.
"""

from __future__ import annotations

import struct

import numpy as np

MAGIC = b"TVSL"
VERSION = 1
FLAG_GROUPS = 1 << 0
_HEADER = struct.Struct("<4sIIII12s")
HEADER_SIZE = _HEADER.size


def encode(
    positions: np.ndarray,
    offsets: np.ndarray,
    index: np.ndarray,
    groups: np.ndarray | None = None,
) -> bytes:
    """Serialise streamlines to ``TVSL1``; refuses arrays that disagree with each other."""
    pos = np.ascontiguousarray(positions, dtype="<f4")
    off = np.ascontiguousarray(offsets, dtype="<u4")
    idx = np.ascontiguousarray(index, dtype="<u4")
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"positions must be (P, 3), got {pos.shape}")
    if not np.isfinite(pos).all():
        raise ValueError("positions contain non-finite values")
    n = len(idx)
    if off.shape != (n + 1,) or off[0] != 0 or off[-1] != len(pos):
        raise ValueError("offsets must be (S + 1,), from 0 to the point count")
    flags, tail = 0, b""
    if groups is not None:
        grp = np.ascontiguousarray(groups, dtype="<u4")
        if grp.shape != (n,):
            raise ValueError(f"groups must be ({n},), got {grp.shape}")
        flags, tail = FLAG_GROUPS, grp.tobytes()
    header = _HEADER.pack(MAGIC, VERSION, n, len(pos), flags, b"\x00" * 12)
    return header + pos.tobytes() + off.tobytes() + idx.tobytes() + tail
