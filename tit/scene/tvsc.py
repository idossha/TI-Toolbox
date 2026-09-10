"""``TVSC1`` — the frozen compatibility wire format (plan §2.3, decision S3).

Frozen layout, little-endian throughout (every platform the app ships on is
little-endian; a big-endian reader would have to byte-swap and there is none)::

    offset size   field
    0      4      magic b"TVSC"
    4      4      u32 version = 1
    8      4      u32 vertexCount
    12     4      u32 indexCount           (0 for a labels-only payload)
    16     4      u32 flags                bit0 = per-vertex u16 labels follow
    20     12     reserved (zero)
    32     12*V   float32 positions, world-RAS mm, x y z
    ...    4*I    uint32 indices           (triangles)
    ...    2*V    uint16 labels            when flags bit0; padded to 4 bytes

Why a hand-rolled 32-byte header rather than glTF: decision S3 — four
primitives (positions, indices, optional labels, a bbox in the manifest) do
not justify pulling glTF/three.js into either side. Normals are computed in
the browser, so they are deliberately absent here.

This module is pure ``numpy`` on purpose. It is the half of ``tit.scene``
that the host suite can exercise with no ``simnibs``/``nibabel``/``scipy``
(all three are ``MagicMock``-ed in ``tests/conftest.py``), and it is the half
whose bug would be invisible until a renderer draws garbage.

The Python compatibility tests keep the byte layout pinned against fixtures:
``tests/scene/make_fixtures.py`` writes ``desktop/tests/fixtures/scene/*.tvsc``
and ``tests/test_scene_tvsc.py`` reads them back here.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

__all__ = [
    "MAGIC",
    "VERSION",
    "HEADER_SIZE",
    "FLAG_LABELS",
    "TvscPayload",
    "encode",
    "decode",
]

MAGIC = b"TVSC"
VERSION = 1
FLAG_LABELS = 1 << 0

#: ``<`` = little-endian: ``4s`` magic, four ``u32`` (version, vertexCount,
#: indexCount, flags) = 20 bytes, then the 12 reserved bytes -> exactly 32.
_HEADER = struct.Struct("<4sIIII12s")

#: 32, from the struct itself rather than a second literal that could drift
#: from it. ``tests/test_scene_tvsc.py`` pins the 32 against the spec text.
HEADER_SIZE = _HEADER.size


@dataclass(frozen=True)
class TvscPayload:
    """One decoded ``TVSC1`` blob.

    ``indices`` is ``(0, 3)`` for a labels-only payload and ``labels`` is
    ``None`` when the flag bit is clear -- a caller never has to look at
    ``flags`` itself.
    """

    positions: np.ndarray  # (V, 3) float32
    indices: np.ndarray  # (T, 3) uint32
    labels: np.ndarray | None  # (V,) uint16 or None

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.shape[0])


def encode(
    positions: np.ndarray,
    indices: np.ndarray | None = None,
    labels: np.ndarray | None = None,
) -> bytes:
    """Serialise one surface (or labels-only) payload to ``TVSC1`` bytes.

    Parameters
    ----------
    positions:
        ``(V, 3)`` world-RAS millimetres. Cast to ``float32``; a
        non-finite coordinate is refused rather than shipped, because a
        ``NaN`` position silently collapses a renderer's bounding sphere and
        the pane then draws nothing with no error anywhere.
    indices:
        ``(T, 3)`` triangle corners, or ``None``/empty for a labels-only
        payload. Every index must be ``< V``: an out-of-range index reads
        past the vertex buffer in WebGL and the driver's behaviour there is
        undefined.
    labels:
        ``(V,)`` per-vertex ``uint16`` region ids, or ``None``. ``0`` means
        "no region" by convention (see :mod:`tit.scene.build`).
    """
    pos = np.ascontiguousarray(positions, dtype=np.float32)
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"positions must be (V, 3), got {pos.shape}")
    if not np.isfinite(pos).all():
        raise ValueError("positions contain non-finite values")
    n_vertices = pos.shape[0]

    if indices is None:
        tri = np.zeros((0, 3), dtype=np.uint32)
    else:
        tri = np.ascontiguousarray(indices, dtype=np.uint32)
        if tri.size == 0:
            tri = tri.reshape(0, 3)
        if tri.ndim != 2 or tri.shape[1] != 3:
            raise ValueError(f"indices must be (T, 3), got {tri.shape}")
        if tri.size and int(tri.max()) >= n_vertices:
            raise ValueError(
                f"index {int(tri.max())} out of range for {n_vertices} vertices"
            )

    flags = 0
    label_bytes = b""
    if labels is not None:
        lab = np.ascontiguousarray(labels, dtype=np.uint16)
        if lab.shape != (n_vertices,):
            raise ValueError(
                f"labels must be ({n_vertices},) to align with positions, got {lab.shape}"
            )
        flags |= FLAG_LABELS
        label_bytes = lab.tobytes()
        # 4-byte tail padding: the browser maps the whole blob with typed
        # array views, and a Uint32Array view needs a 4-aligned byteLength.
        if len(label_bytes) % 4:
            label_bytes += b"\x00" * (4 - len(label_bytes) % 4)

    header = _HEADER.pack(
        MAGIC, VERSION, n_vertices, int(tri.size), flags, b"\x00" * 12
    )
    return header + pos.tobytes() + tri.tobytes() + label_bytes


def decode(blob: bytes | bytearray | memoryview) -> TvscPayload:
    """Parse ``TVSC1`` bytes back into arrays, or raise ``ValueError``.

    Every length is checked against the header before a view is taken: a
    truncated blob (a half-written cache file, a proxy that cut the body)
    must fail loudly here rather than hand a short array to a caller that
    then indexes past it.
    """
    data = bytes(blob)
    if len(data) < HEADER_SIZE:
        raise ValueError(f"TVSC blob shorter than its {HEADER_SIZE}-byte header")
    magic, version, n_vertices, n_indices, flags, _reserved = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {MAGIC!r}")
    if version != VERSION:
        raise ValueError(f"unsupported TVSC version {version}")
    if n_indices % 3:
        raise ValueError(f"indexCount {n_indices} is not a multiple of 3")

    offset = HEADER_SIZE
    pos_bytes = 12 * n_vertices
    idx_bytes = 4 * n_indices
    lab_bytes = 2 * n_vertices if flags & FLAG_LABELS else 0
    need = offset + pos_bytes + idx_bytes + lab_bytes
    if len(data) < need:
        raise ValueError(f"TVSC blob is {len(data)} bytes, header requires {need}")

    positions = np.frombuffer(
        data, dtype="<f4", count=3 * n_vertices, offset=offset
    ).reshape(n_vertices, 3)
    offset += pos_bytes
    indices = np.frombuffer(
        data, dtype="<u4", count=n_indices, offset=offset
    ).reshape(-1, 3)
    offset += idx_bytes
    labels = None
    if flags & FLAG_LABELS:
        labels = np.frombuffer(data, dtype="<u2", count=n_vertices, offset=offset)
    return TvscPayload(positions=positions, indices=indices, labels=labels)
