"""GIfTI serialisation for the scene panes (plan of record §1, decision E7).

``TVSC1`` (:mod:`tit.scene.tvsc`) is the frozen compatibility format from the
retired desktop renderer path. The run-page panes now use the **Tetravox
embed**, whose engine reads no bespoke format at all -- so the scene service
keeps everything that makes it worth having (cropping a 184 MB mesh to skin +
cortex, simplifying to the §S3 budget, carrying an atlas' labels onto the
surface it actually serves, and the fingerprinted cache) and changes only the
bytes it hands out.

What the engine parses, read out of its own source rather than assumed
(``crates/tvx-mesh-io/src/gifti.rs`` in the Tetravox tree, at the protocol-2
tag lane T packed):

* the format is sniffed **by content**, not by a file name -- ``sniff()`` tries
  ``gifti::looks_like`` before any extension hint -- so ``GET
  /api/scene/surface?subject=ernie&part=skin&format=gii`` needs no ``.gii`` in
  its URL;
* three encodings: ``ASCII``, ``Base64Binary`` and ``GZipBase64Binary``, and
  the last is a **zlib** stream (``ZlibDecoder``), not gzip;
* ``NIFTI_INTENT_POINTSET`` (3 components), ``NIFTI_INTENT_TRIANGLE``
  (3 components) and anything else as a per-vertex node field;
* a ``NIFTI_INTENT_LABEL`` array **plus** a ``<LabelTable>`` is remapped to a
  *dense* index (position in the table) and the table becomes the layer's
  palette. A value the table does not name maps to dense **0**, so the table's
  first entry has to be the "no region" one or every unlabelled vertex is
  painted with the first region's colour -- a whole cortex in one colour, and
  it looks plausible.

Why this module writes the XML itself rather than calling ``nibabel``:

* :mod:`tit.scene` is deliberately split so that everything except
  :mod:`tit.scene.build` needs **numpy only** -- ``tests/conftest.py`` replaces
  ``nibabel`` with a ``MagicMock``, so a nibabel-based writer could not be
  exercised at all by the host suite, and this is the half whose bug is
  invisible until a renderer draws garbage.
* The engine parses a documented subset. Writing that subset directly means
  the bytes are pinned by a test in this repository instead of by whatever
  nibabel's defaults happen to be.

The bytes are checked against a **real** ``nibabel`` (which the container has
and the host suite mocks) by ``tests/test_scene_gifti.py``, which skips when
nibabel is a mock -- so the round trip is proved on the interpreter that ships.
"""

from __future__ import annotations

import base64
import zlib
from dataclasses import dataclass
from xml.sax.saxutils import quoteattr

import numpy as np

__all__ = [
    "GIFTI_VERSION",
    "LabelEntry",
    "encode_surface",
    "label_table_from_legend",
]

#: The ``<GIFTI Version=...>`` attribute. 1.0 is the only version there is.
GIFTI_VERSION = "1.0"

#: NIfTI intent codes, by their GIfTI spelling.
_INTENT_POINTSET = "NIFTI_INTENT_POINTSET"
_INTENT_TRIANGLE = "NIFTI_INTENT_TRIANGLE"
_INTENT_LABEL = "NIFTI_INTENT_LABEL"

#: ``NIFTI_XFORM_SCANNER_ANAT``. Our surfaces are already in the subject's own
#: world-RAS millimetres, so the coordinate system is declared honestly and its
#: matrix is the identity -- the engine bakes the matrix in only when the
#: transformed space is this one, and an identity baked in changes nothing.
_SCANNER_ANAT = "NIFTI_XFORM_SCANNER_ANAT"

#: Written as ``Encoding``. zlib, base64'd -- the encoding every reference
#: surface in the engine's own test data uses.
_ENCODING = "GZipBase64Binary"

#: The key a vertex with no region carries, and the first row of every table
#: this module writes. See the module docstring: the engine maps an unknown
#: value to dense 0, so the row at position 0 must be the one that means
#: "nothing", or unlabelled cortex takes the first region's colour.
NO_REGION = 0


@dataclass(frozen=True)
class LabelEntry:
    """One ``<Label>`` row: its key, its name and its 0..1 RGBA."""

    key: int
    name: str
    rgba: tuple[float, float, float, float]


def label_table_from_legend(
    legend: list[dict],
    *,
    unlabelled_name: str = "unlabelled",
    unlabelled_rgba: tuple[float, float, float, float] = (0.6, 0.6, 0.62, 0.0),
) -> list[LabelEntry]:
    """A ``<LabelTable>`` from ``build_labels``' own legend rows.

    ``legend`` rows carry ``label`` (the ``uint16`` value in the payload),
    ``name`` and ``color`` as ``"#rrggbb"``. The result always begins with
    :data:`NO_REGION`, whatever the legend holds.
    """
    entries = [
        LabelEntry(key=NO_REGION, name=unlabelled_name, rgba=unlabelled_rgba)
    ]
    for row in legend:
        key = int(row["label"])
        if key == NO_REGION:
            continue
        entries.append(
            LabelEntry(
                key=key,
                name=str(row.get("name", f"region {key}")),
                rgba=_hex_to_rgba(str(row.get("color", "#808080"))),
            )
        )
    return entries


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    """``"#rrggbb"`` -> 0..1 RGBA. Anything unparseable is opaque mid-grey."""
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return (0.5, 0.5, 0.5, 1.0)
    try:
        r, g, b = (int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.5, 0.5, 0.5, 1.0)
    return (r, g, b, 1.0)


def _darray(
    *,
    intent: str,
    dtype: str,
    dims: tuple[int, ...],
    data: bytes,
    name: str | None = None,
    coordinate_system: bool = False,
) -> str:
    """One ``<DataArray>`` element, already base64'd and zlib-compressed."""
    payload = base64.b64encode(zlib.compress(data, 6)).decode("ascii")
    dim_attrs = " ".join(f'Dim{i}="{d}"' for i, d in enumerate(dims))
    meta = ""
    if name is not None:
        meta = (
            "\n      <MetaData>\n"
            "        <MD>\n"
            f"          <Name><![CDATA[Name]]></Name>\n"
            f"          <Value><![CDATA[{name}]]></Value>\n"
            "        </MD>\n"
            "      </MetaData>"
        )
    else:
        meta = "\n      <MetaData/>"
    csys = ""
    if coordinate_system:
        csys = (
            "\n      <CoordinateSystemTransformMatrix>\n"
            f"        <DataSpace><![CDATA[{_SCANNER_ANAT}]]></DataSpace>\n"
            f"        <TransformedSpace><![CDATA[{_SCANNER_ANAT}]]></TransformedSpace>\n"
            "        <MatrixData>\n"
            "          1 0 0 0\n"
            "          0 1 0 0\n"
            "          0 0 1 0\n"
            "          0 0 0 1\n"
            "        </MatrixData>\n"
            "      </CoordinateSystemTransformMatrix>"
        )
    return (
        "   <DataArray "
        f"ArrayIndexingOrder=\"RowMajorOrder\" "
        f"DataType={quoteattr(dtype)} "
        f"Dimensionality=\"{len(dims)}\" "
        f"{dim_attrs} "
        f"Encoding={quoteattr(_ENCODING)} "
        f"Endian=\"LittleEndian\" "
        f"ExternalFileName=\"\" ExternalFileOffset=\"\" "
        f"Intent={quoteattr(intent)}>"
        f"{meta}{csys}\n"
        f"      <Data>{payload}</Data>\n"
        "   </DataArray>\n"
    )


def encode_surface(
    positions: np.ndarray,
    indices: np.ndarray | None = None,
    labels: np.ndarray | None = None,
    label_table: list[LabelEntry] | None = None,
    *,
    label_name: str = "regions",
) -> bytes:
    """Serialise one surface (and optionally its per-vertex labels) as GIfTI.

    Parameters mirror :func:`tit.scene.tvsc.encode` exactly, on purpose: this
    is a change of serialisation and nothing else, so the same guards apply and
    the same call sites work.

    ``positions``
        ``(V, 3)`` world-RAS millimetres, cast to ``float32``. A non-finite
        coordinate is refused rather than shipped: a ``NaN`` collapses the
        engine's bounding box and the pane then frames nothing, with no error
        anywhere.
    ``indices``
        ``(T, 3)`` triangle corners, ``None`` for a labels-only payload. Every
        index must be ``< V``; the engine checks this too and fails the whole
        load, so failing here names the surface instead.
    ``labels``
        ``(V,)`` per-vertex region ids. Written as ``NIFTI_TYPE_INT32``
        (GIfTI's label type) with the ``<LabelTable>`` in ``label_table``.
    ``label_table``
        The ``<Label>`` rows. Required when ``labels`` is given: without a
        table the engine treats the array as a continuous scalar and the
        regions are painted through a colormap instead of their own colours.
    """
    pos = np.ascontiguousarray(positions, dtype=np.float32)
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"positions must be (V, 3), got {pos.shape}")
    if not np.isfinite(pos).all():
        raise ValueError("positions contain non-finite values")
    n_vertices = int(pos.shape[0])

    if indices is None:
        tri = np.zeros((0, 3), dtype=np.int32)
    else:
        tri = np.ascontiguousarray(indices, dtype=np.int32)
        if tri.size == 0:
            tri = tri.reshape(0, 3)
        if tri.ndim != 2 or tri.shape[1] != 3:
            raise ValueError(f"indices must be (T, 3), got {tri.shape}")
        if tri.size and (int(tri.max()) >= n_vertices or int(tri.min()) < 0):
            raise ValueError(
                f"index {int(tri.max())} out of range for {n_vertices} vertices"
            )

    arrays: list[str] = [
        _darray(
            intent=_INTENT_POINTSET,
            dtype="NIFTI_TYPE_FLOAT32",
            dims=(n_vertices, 3),
            data=pos.tobytes(),
            coordinate_system=True,
        )
    ]
    if tri.shape[0] > 0:
        arrays.append(
            _darray(
                intent=_INTENT_TRIANGLE,
                dtype="NIFTI_TYPE_INT32",
                dims=(int(tri.shape[0]), 3),
                data=tri.tobytes(),
            )
        )

    table_xml = "   <LabelTable/>\n"
    if labels is not None:
        lab = np.ascontiguousarray(labels, dtype=np.int32)
        if lab.shape != (n_vertices,):
            raise ValueError(
                f"labels must be ({n_vertices},) to align with positions, got {lab.shape}"
            )
        if not label_table:
            raise ValueError(
                "labels need a label_table: without a <LabelTable> the engine "
                "reads the array as a continuous scalar, not as regions"
            )
        arrays.append(
            _darray(
                intent=_INTENT_LABEL,
                dtype="NIFTI_TYPE_INT32",
                dims=(n_vertices,),
                data=lab.tobytes(),
                name=label_name,
            )
        )
        table_xml = _label_table_xml(label_table)

    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE GIFTI SYSTEM "http://www.nitrc.org/frs/download.php/115/gifti.dtd">\n'
        f'<GIFTI Version="{GIFTI_VERSION}" NumberOfDataArrays="{len(arrays)}">\n'
        "   <MetaData/>\n"
    )
    return (head + table_xml + "".join(arrays) + "</GIFTI>\n").encode("utf-8")


def _label_table_xml(entries: list[LabelEntry]) -> str:
    rows = []
    for entry in entries:
        r, g, b, a = entry.rgba
        rows.append(
            f'      <Label Key="{int(entry.key)}" Red="{r:.6f}" Green="{g:.6f}" '
            f'Blue="{b:.6f}" Alpha="{a:.6f}"><![CDATA[{entry.name}]]></Label>\n'
        )
    return "   <LabelTable>\n" + "".join(rows) + "   </LabelTable>\n"

