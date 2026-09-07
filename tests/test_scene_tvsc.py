"""``TVSC1`` — the frozen compatibility wire format (lane SCA, 2026-09-04).

What this pins
    Every byte of ``tit/scene/tvsc.py`` against the spec table frozen in
    ``docs/dev/HISTORY.md § 2026-09-04 (scene service)`` §2.3, and the three committed fixtures
    that compatibility clients can use to validate their own readers.

Where the numbers come from
    Not from the encoder. The header is read here with a bare
    ``struct.unpack_from`` at the literal offsets in the §2.3 table (never
    ``tvsc._HEADER``), the positions are recomputed from the formula
    ``desktop/tests/fixtures/scene/fixtures.json`` states, and the byte sizes
    are computed from ``32 + 12V + 4I + pad(2V)``. A test that asked the
    decoder what the encoder wrote would prove only that they share a bug.

Reproduce
    ``python3 tests/scene/make_fixtures.py`` regenerates the fixtures;
    ``--check`` fails if the tree is stale (also asserted below).

Deliberately elsewhere
    Real-mesh payload sizes and triangle counts are
    ``tests/test_scene_realdata.py`` (env-gated); the run-page renderer now
    reads GIfTI through the embedded Tetravox bundle instead of a TypeScript
    TVSC decoder.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tit.scene import tvsc

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "desktop" / "tests" / "fixtures" / "scene"

# The §2.3 table, retyped here on purpose: this file is the independent reader,
# so it must not import the writer's own struct definition.
OFF_MAGIC, OFF_VERSION, OFF_VERTICES, OFF_INDICES, OFF_FLAGS, OFF_DATA = (
    0,
    4,
    8,
    12,
    16,
    32,
)


def _read_header(blob: bytes) -> dict:
    """The header, read with plain ``struct`` at the spec's literal offsets."""
    return {
        "magic": blob[OFF_MAGIC : OFF_MAGIC + 4],
        "version": struct.unpack_from("<I", blob, OFF_VERSION)[0],
        "vertices": struct.unpack_from("<I", blob, OFF_VERTICES)[0],
        "indices": struct.unpack_from("<I", blob, OFF_INDICES)[0],
        "flags": struct.unpack_from("<I", blob, OFF_FLAGS)[0],
        "reserved": blob[20:32],
    }


@pytest.fixture(scope="module")
def manifest() -> dict:
    path = FIXTURES / "fixtures.json"
    if not path.is_file():  # pragma: no cover - generator not run
        pytest.fail(f"missing {path}; run python3 tests/scene/make_fixtures.py")
    return json.loads(path.read_text())


def _expected_positions(entry: dict) -> np.ndarray:
    """Positions from the manifest's formula, not from the encoder."""
    f = entry["positionFormula"]
    i = np.arange(entry["vertexCount"], dtype=np.float64)
    return np.stack(
        [
            i * f["stepX"],
            f["originY"] - i * f["stepY"],
            f["originZ"] + i * i * f["stepZ"],
        ],
        axis=1,
    )


# ── the format itself ────────────────────────────────────────────────────────


def test_header_is_the_frozen_32_byte_shape() -> None:
    """§2.3: magic, version 1, three u32 fields, 12 reserved zero bytes."""
    assert tvsc.HEADER_SIZE == 32
    assert tvsc.MAGIC == b"TVSC"
    assert tvsc.VERSION == 1
    assert tvsc.FLAG_LABELS == 1

    blob = tvsc.encode(np.zeros((2, 3)), np.array([[0, 1, 1]]))
    header = _read_header(blob)
    assert header["magic"] == b"TVSC"
    assert header["version"] == 1
    assert header["vertices"] == 2
    assert header["indices"] == 3  # index *count*, not triangle count
    assert header["flags"] == 0
    assert header["reserved"] == b"\x00" * 12


def test_byte_size_follows_the_documented_layout() -> None:
    """``32 + 12V + 4I + pad4(2V)`` -- the size a caller budgets against."""
    positions = np.arange(3 * 7, dtype=np.float64).reshape(7, 3)
    triangles = np.array([[0, 1, 2], [3, 4, 5]])
    labels = np.arange(7, dtype=np.uint16)

    assert len(tvsc.encode(positions, triangles)) == 32 + 12 * 7 + 4 * 6
    assert len(tvsc.encode(positions, None, labels)) == 32 + 12 * 7 + 16  # 14 -> 16
    assert len(tvsc.encode(positions, triangles, labels)) == 32 + 12 * 7 + 4 * 6 + 16


def test_round_trip_preserves_positions_indices_and_labels() -> None:
    positions = np.array([[1.5, -2.25, 3.0], [0.0, 10.5, -7.75], [4.0, 4.0, 4.0]])
    triangles = np.array([[0, 1, 2], [2, 1, 0]])
    labels = np.array([0, 65535, 12], dtype=np.uint16)

    decoded = tvsc.decode(tvsc.encode(positions, triangles, labels))
    assert decoded.vertex_count == 3
    assert decoded.triangle_count == 2
    np.testing.assert_allclose(decoded.positions, positions, rtol=0, atol=0)
    np.testing.assert_array_equal(decoded.indices, triangles)
    np.testing.assert_array_equal(decoded.labels, labels)


def test_labels_only_payload_has_no_index_block() -> None:
    """The shape ``GET /api/scene/labels`` returns: V positions, 0 indices."""
    positions = np.zeros((5, 3))
    blob = tvsc.encode(positions, None, np.arange(5, dtype=np.uint16))
    assert _read_header(blob)["indices"] == 0
    decoded = tvsc.decode(blob)
    assert decoded.triangle_count == 0
    assert decoded.indices.shape == (0, 3)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"positions": np.zeros((2, 2))}, "positions must be"),
        ({"positions": np.array([[0.0, 0.0, np.nan]])}, "non-finite"),
        (
            {"positions": np.zeros((2, 3)), "indices": np.array([[0, 1, 2]])},
            "out of range",
        ),
        (
            {"positions": np.zeros((2, 3)), "labels": np.zeros(3, dtype=np.uint16)},
            "align with positions",
        ),
    ],
)
def test_encode_refuses_payloads_a_renderer_cannot_draw(kwargs, message) -> None:
    """Each of these renders as nothing, or as undefined WebGL behaviour."""
    with pytest.raises(ValueError, match=message):
        tvsc.encode(**kwargs)


@pytest.mark.parametrize(
    ("blob", "message"),
    [
        (b"TVS", "shorter than"),
        (b"XXXX" + b"\x00" * 28, "bad magic"),
        (b"TVSC" + struct.pack("<I", 2) + b"\x00" * 24, "unsupported TVSC version"),
        (
            b"TVSC" + struct.pack("<IIII", 1, 1, 4, 0) + b"\x00" * 12 + b"\x00" * 12,
            "not a multiple of 3",
        ),
        (b"TVSC" + struct.pack("<IIII", 1, 9, 0, 0) + b"\x00" * 12, "header requires"),
    ],
)
def test_decode_rejects_a_blob_it_cannot_trust(blob, message) -> None:
    """A truncated or mislabelled blob must fail here, not at the GPU."""
    with pytest.raises(ValueError, match=message):
        tvsc.decode(blob)


# ── the committed fixtures both languages read ───────────────────────────────


#: What ``tests/scene/make_fixtures.py`` owns in that directory. Lane SCB
#: writes its own renderer fixtures alongside them (``skin.tvsc``,
#: ``gm.tvsc``, ``electrodes.json``), so this is a subset check, not an
#: equality one -- an equality check would fail every time the other lane
#: added a fixture, which is how a drift guard gets switched off.
GENERATED = (
    "fixtures.json",
    "labelled-surface.tvsc",
    "labels-only.tvsc",
    "tri-surface.tvsc",
)


def test_fixtures_are_present_and_current() -> None:
    """The drift guard: the tree must match what the generator writes today."""
    names = {p.name for p in FIXTURES.glob("*")}
    assert set(GENERATED) <= names, sorted(set(GENERATED) - names)
    result = subprocess.run(
        [sys.executable, str(REPO / "tests" / "scene" / "make_fixtures.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_fixture_matches_its_authored_manifest(manifest: dict) -> None:
    """Read each fixture with the independent header reader and the formula."""
    entries = manifest["fixtures"]
    assert entries, "has fixtures to check"
    for name, entry in entries.items():
        blob = (FIXTURES / name).read_bytes()
        assert len(blob) == entry["bytes"], name

        header = _read_header(blob)
        assert header["magic"] == manifest["format"]["magic"].encode(), name
        assert header["version"] == manifest["format"]["version"], name
        assert header["vertices"] == entry["vertexCount"], name
        assert header["indices"] == entry["indexCount"], name
        assert header["flags"] == entry["flags"], name

        decoded = tvsc.decode(blob)
        np.testing.assert_allclose(
            decoded.positions, _expected_positions(entry), rtol=0, atol=1e-4
        )
        np.testing.assert_array_equal(
            decoded.indices, np.asarray(entry["triangles"], dtype=np.uint32).reshape(-1, 3)
        )
        if entry["labels"] is None:
            assert decoded.labels is None, name
        else:
            np.testing.assert_array_equal(decoded.labels, entry["labels"])


def test_fixture_label_block_starts_after_the_index_block(manifest: dict) -> None:
    """The offset a reader must accumulate, not read from the header.

    ``labelled-surface`` is the only fixture where the two ways of computing
    the label offset differ, which is exactly why it exists.
    """
    entry = manifest["fixtures"]["labelled-surface.tvsc"]
    blob = (FIXTURES / "labelled-surface.tvsc").read_bytes()
    offset = OFF_DATA + 12 * entry["vertexCount"] + 4 * entry["indexCount"]
    read = struct.unpack_from(f"<{entry['vertexCount']}H", blob, offset)
    assert list(read) == entry["labels"]


def test_this_reader_parses_the_fixtures_the_other_language_wrote() -> None:
    """§2.3: "one test in each language reads a fixture the other wrote".

    Lane SCB's renderer writes its own ``.tvsc`` fixtures into the same
    directory with its TypeScript encoder. Reading them here is the half of
    that promise this side owes: a header field written little-endian on one
    side and read big-endian on the other, or a label block placed before the
    index block, fails here rather than as a scrambled surface in a pane.
    """
    theirs = sorted(p for p in FIXTURES.glob("*.tvsc") if p.name not in GENERATED)
    if not theirs:
        pytest.skip("skipping: lane SCB has written no .tvsc fixtures here yet")
    for path in theirs:
        payload = tvsc.decode(path.read_bytes())
        header = _read_header(path.read_bytes())
        assert header["magic"] == b"TVSC", path.name
        assert header["version"] == 1, path.name
        assert header["reserved"] == b"\x00" * 12, path.name
        assert payload.vertex_count > 0, path.name
        assert np.isfinite(payload.positions).all(), path.name
        if payload.triangle_count:
            assert payload.indices.max() < payload.vertex_count, path.name
        if payload.labels is not None:
            assert payload.labels.shape == (payload.vertex_count,), path.name
