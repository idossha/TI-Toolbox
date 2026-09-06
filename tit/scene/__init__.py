"""``tit.scene`` — the slim scene service behind the v3 3D panes.

Plan of record: ``dev/notes/v3-scene-ia-plan.md`` §2, decisions S1-S3.

**Non-goals, written here so they stay non-goals** (decision S1): no volume
slicing, no colormaps, no field overlays, no publication screenshots, no layer
tree. This module exists so a user can *choose* — electrodes on the Simulator,
a target on the Optimizer, a verified ROI on the Analyzer. Everything a
*viewer* does belongs to Tetravox, on the Viewer page and in the Results
preview; building it a second time here is exactly what the microservice split
exists to prevent.

What it does do: extract the two surfaces a pane draws (skin tag 1005, grey
matter tag 1002) out of a 184 MB head mesh, get grey matter under the §S3
budget, carry an atlas' per-vertex labels onto the surface it actually serves,
read an EEG net's electrode coordinates, and cache all of it under
``derivatives/ti-toolbox/scene_cache/``.

Module map, split along the line the host test suite can cross:

===================  ========================================================
module               needs
===================  ========================================================
:mod:`~tit.scene.tvsc`      ``numpy`` only — the ``TVSC1`` wire format (§2.3)
:mod:`~tit.scene.simplify`  ``numpy`` only — grid vertex clustering to the §S3 budget
:mod:`~tit.scene.cache`     stdlib only — fingerprints, atomic publish, build lock (§2.2)
:mod:`~tit.scene.build`     ``simnibs`` / ``nibabel`` / ``scipy``, all imported inside functions
===================  ========================================================

``tests/conftest.py`` replaces ``simnibs``, ``nibabel`` and ``scipy`` with
``MagicMock``s, so the first three are fully exercised by the host suite and
:mod:`~tit.scene.build`'s numeric core is reached through its pure helpers
(:func:`~tit.scene.build.labels_from_nearest`,
:func:`~tit.scene.build.parse_electrode_csv`,
:func:`~tit.scene.build.parse_lut_text`). What only real data can prove — that
labels land on the right region and electrodes land on the skin — is
``tests/test_scene_realdata.py``, gated on ``TIT_SCENE_TESTDATA``.

HTTP surface: :mod:`tit.server.routes.scene`.
"""

from __future__ import annotations

from tit.scene.tvsc import (
    FLAG_LABELS,
    HEADER_SIZE,
    MAGIC,
    VERSION,
    TvscPayload,
    decode,
    encode,
)

__all__ = [
    "MAGIC",
    "VERSION",
    "HEADER_SIZE",
    "FLAG_LABELS",
    "TvscPayload",
    "encode",
    "decode",
]
