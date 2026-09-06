#!/usr/bin/env python3
"""Write the ``TVSC1`` compatibility fixtures (plan §2.3, lane SCA).

    python3 tests/scene/make_fixtures.py            # regenerate
    python3 tests/scene/make_fixtures.py --check    # fail if the tree is stale

Output goes to ``desktop/tests/fixtures/scene/``. The Python reader
(``tests/test_scene_tvsc.py``) parses these exact bytes, so a disagreement
between the encoder here and the independent byte-level expectations fails a
test instead of reaching a compatibility client as a scrambled brain.

**Where the expected numbers come from.** Nothing in ``fixtures.json`` is read
back out of :mod:`tit.scene.tvsc`. Every position is stated as the parameters
of a formula (``position(i) = (i*STEP_X, ORIGIN_Y - i*STEP_Y, ORIGIN_Z +
i*i*STEP_Z)``) that each reader evaluates for itself, and every byte offset and
header value is stated as a literal taken from the §2.3 spec table. A test that
compared the decoder against the encoder would only prove they share a bug.

The fixtures are deliberately adversarial:

* the three axes have different magnitudes and signs, so a transposed or
  swapped axis moves a vertex by tens of millimetres rather than by rounding;
* ``y`` decreases while ``x`` increases, so a reversed vertex order is visible;
* vertex counts are **odd**, so the ``uint16`` label block ends on a 2-byte
  boundary and the 4-byte tail padding path is exercised (a reader that
  forgets the padding reads the right values but the wrong ``byteLength``);
* one label is ``0`` (= no region) and one is ``65535`` (the largest ``uint16``),
  so a signed-vs-unsigned mistake in either language is loud;
* the triangle list references the last vertex, so an off-by-one in the index
  block runs off the end instead of landing on a plausible neighbour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tit.scene import tvsc  # noqa: E402

OUT_DIR = REPO / "desktop" / "tests" / "fixtures" / "scene"

# The position formula, stated once and written into the manifest so both
# readers can evaluate it without asking the encoder what it wrote.
STEP_X = 1.5
ORIGIN_Y = 40.0
STEP_Y = 7.25
ORIGIN_Z = -12.0
STEP_Z = 3.0

#: 0 = "no region"; 65535 = the largest uint16.
LABELS = [0, 7, 65535, 3, 1]

#: References vertex 4 (the last one), so an off-by-one overruns.
TRIANGLES = [[0, 1, 2], [2, 3, 4], [0, 2, 4]]


def positions(count: int) -> np.ndarray:
    index = np.arange(count, dtype=np.float64)
    return np.stack(
        [index * STEP_X, ORIGIN_Y - index * STEP_Y, ORIGIN_Z + index * index * STEP_Z],
        axis=1,
    )


def build() -> tuple[dict[str, bytes], dict]:
    """``({filename: bytes}, manifest)`` -- deterministic, no timestamps."""
    count = len(LABELS)  # 5: odd on purpose (see the module docstring)
    pos = positions(count)
    tri = np.asarray(TRIANGLES, dtype=np.uint32)
    lab = np.asarray(LABELS, dtype=np.uint16)

    files = {
        "tri-surface.tvsc": tvsc.encode(pos, tri),
        "labels-only.tvsc": tvsc.encode(pos, None, lab),
        "labelled-surface.tvsc": tvsc.encode(pos, tri, lab),
    }

    common = {
        "vertexCount": count,
        "positionFormula": {
            "x": f"i * {STEP_X}",
            "y": f"{ORIGIN_Y} - i * {STEP_Y}",
            "z": f"{ORIGIN_Z} + i*i * {STEP_Z}",
            "stepX": STEP_X,
            "originY": ORIGIN_Y,
            "stepY": STEP_Y,
            "originZ": ORIGIN_Z,
            "stepZ": STEP_Z,
        },
    }
    manifest = {
        "//": (
            "Regenerate with `python3 tests/scene/make_fixtures.py`. Every number here is "
            "authored from the TVSC1 spec table in dev/notes/v3-scene-ia-plan.md 2.3 and the "
            "position formula above, never read back from the encoder."
        ),
        "format": {
            "magic": "TVSC",
            "version": 1,
            "headerBytes": 32,
            "flagLabels": 1,
            "offsets": {
                "magic": 0,
                "version": 4,
                "vertexCount": 8,
                "indexCount": 12,
                "flags": 16,
                "reserved": 20,
                "positions": 32,
            },
            "littleEndian": True,
        },
        "groundTruth": "authored",
        "reader": (
            "python: tests/test_scene_tvsc.py (struct.unpack against the spec offsets, "
            "positions recomputed from positionFormula)"
        ),
        "fixtures": {
            "tri-surface.tvsc": {
                **common,
                "indexCount": int(tri.size),
                "triangles": TRIANGLES,
                "flags": 0,
                "labels": None,
                "bytes": len(files["tri-surface.tvsc"]),
                "pins": (
                    "a surface with no labels: flags bit0 clear and no trailing label block, "
                    "so a reader that always looks for labels reads past the end"
                ),
            },
            "labels-only.tvsc": {
                **common,
                "indexCount": 0,
                "triangles": [],
                "flags": 1,
                "labels": LABELS,
                "bytes": len(files["labels-only.tvsc"]),
                "pins": (
                    "the payload GET /api/scene/labels returns: indexCount 0, an odd vertex "
                    "count so the uint16 block needs 2 bytes of tail padding"
                ),
            },
            "labelled-surface.tvsc": {
                **common,
                "indexCount": int(tri.size),
                "triangles": TRIANGLES,
                "flags": 1,
                "labels": LABELS,
                "bytes": len(files["labelled-surface.tvsc"]),
                "pins": (
                    "all three blocks present: a reader that computes the label offset from "
                    "the header instead of accumulating the index block lands wrong"
                ),
            },
        },
    }
    return files, manifest


def _manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any fixture on disk differs from what this script writes",
    )
    args = parser.parse_args(argv)

    files, manifest = build()
    payload = {**files, "fixtures.json": _manifest_bytes(manifest)}

    if args.check:
        stale = [
            name
            for name, data in payload.items()
            if not (OUT_DIR / name).is_file() or (OUT_DIR / name).read_bytes() != data
        ]
        if stale:
            print("stale scene fixtures: " + ", ".join(sorted(stale)))
            print("regenerate with: python3 tests/scene/make_fixtures.py")
            return 1
        print(f"scene fixtures up to date ({len(payload)} files in {OUT_DIR})")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        (OUT_DIR / name).write_bytes(data)
        print(f"wrote {OUT_DIR / name} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
