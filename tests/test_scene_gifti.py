"""``tit.scene.gifti`` — the bytes the Tetravox embed reads (decision E7).

This is the half of the format change whose bug is invisible until a renderer
draws garbage, so it is pinned twice:

* **here**, with numpy and the standard library only, which is why it runs in
  the host suite where ``nibabel`` is a ``MagicMock``;
* against a **real** ``nibabel`` and against the engine itself, in
  ``tests/test_scene_realdata.py`` (``TIT_SCENE_TESTDATA``) and in
  ``desktop/tests/e2e/real/``.

Every expectation below is either a rule read out of the engine's own GIfTI
reader (``crates/tvx-mesh-io/src/gifti.rs``) or a guard whose failure is stated
with what it costs.
"""

from __future__ import annotations

import base64
import re
import zlib
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from tit.scene import gifti


def _tree(blob: bytes) -> ET.Element:
    return ET.fromstring(blob.decode("utf-8"))


def _arrays(blob: bytes) -> dict[str, ET.Element]:
    return {d.get("Intent", ""): d for d in _tree(blob).findall("DataArray")}


def _values(darray: ET.Element, dtype: str) -> np.ndarray:
    """Decode one ``<DataArray>`` the way the engine does: base64, then zlib."""
    assert darray.get("Encoding") == "GZipBase64Binary"
    assert darray.get("Endian") == "LittleEndian"
    assert darray.get("ArrayIndexingOrder") == "RowMajorOrder"
    text = (darray.findtext("Data") or "").strip()
    raw = zlib.decompress(base64.b64decode(text))
    dims = [
        int(darray.get(f"Dim{i}", "0"))
        for i in range(int(darray.get("Dimensionality", "1")))
    ]
    return np.frombuffer(raw, dtype=dtype).reshape(dims)


SQUARE = np.array(
    [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]],
    dtype=np.float32,
)
TRIS = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)


# ── the geometry survives the round trip ─────────────────────────────────────


def test_a_surface_is_a_pointset_and_a_triangle_array_the_engine_can_find() -> None:
    """The two intents the engine matches on, by name.

    ``read()`` switches on ``NIFTI_INTENT_POINTSET`` and
    ``NIFTI_INTENT_TRIANGLE`` and treats **every other intent** as a per-vertex
    node field. A misspelled intent therefore does not fail: it silently
    becomes a scalar field and the surface loads with no geometry.
    """
    blob = gifti.encode_surface(SQUARE, TRIS)
    arrays = _arrays(blob)
    assert set(arrays) == {"NIFTI_INTENT_POINTSET", "NIFTI_INTENT_TRIANGLE"}
    assert _tree(blob).get("NumberOfDataArrays") == "2"

    positions = _values(arrays["NIFTI_INTENT_POINTSET"], "<f4")
    np.testing.assert_array_equal(positions, SQUARE)
    triangles = _values(arrays["NIFTI_INTENT_TRIANGLE"], "<i4")
    np.testing.assert_array_equal(triangles, TRIS.astype(np.int32))


def test_the_declared_dimensions_match_the_data() -> None:
    """``Dim0``/``Dim1`` are what the reader allocates from.

    ``widen()`` refuses a payload shorter than ``Dim0 * Dim1`` values and
    **truncates** a longer one, so a dimension that overstated the data would
    fail the load and one that understated it would silently drop vertices.
    """
    blob = gifti.encode_surface(SQUARE, TRIS)
    points = _arrays(blob)["NIFTI_INTENT_POINTSET"]
    assert (points.get("Dim0"), points.get("Dim1")) == ("4", "3")
    assert points.get("DataType") == "NIFTI_TYPE_FLOAT32"
    tris = _arrays(blob)["NIFTI_INTENT_TRIANGLE"]
    assert (tris.get("Dim0"), tris.get("Dim1")) == ("2", "3")
    assert tris.get("DataType") == "NIFTI_TYPE_INT32"


def test_the_coordinate_system_says_scanner_anat_with_an_identity_matrix() -> None:
    """Our surfaces are already in the subject's world-RAS millimetres.

    The engine bakes a ``CoordinateSystemTransformMatrix`` into the vertices
    **only** when ``TransformedSpace`` is ``NIFTI_XFORM_SCANNER_ANAT``. Naming
    that space with a non-identity matrix would move every vertex; naming a
    different space would leave `appliedTransform` unreported. Identity in
    scanner-anat says "these are already world millimetres" and is the only
    honest pair.
    """
    blob = gifti.encode_surface(SQUARE, TRIS)
    csys = _arrays(blob)["NIFTI_INTENT_POINTSET"].find(
        "CoordinateSystemTransformMatrix"
    )
    assert csys is not None
    assert (csys.findtext("DataSpace") or "").strip() == "NIFTI_XFORM_SCANNER_ANAT"
    assert (
        csys.findtext("TransformedSpace") or ""
    ).strip() == "NIFTI_XFORM_SCANNER_ANAT"
    matrix = [float(v) for v in (csys.findtext("MatrixData") or "").split()]
    np.testing.assert_array_equal(np.array(matrix).reshape(4, 4), np.eye(4))


def test_a_labels_only_payload_has_no_triangle_array() -> None:
    """The encoder omits triangles only when a caller passes no triangle array.

    A zero-length ``NIFTI_INTENT_TRIANGLE`` array would be a surface with no
    faces, which renders nothing and reports no error.
    """
    labels = np.array([0, 1, 2, 1], dtype=np.uint16)
    table = gifti.label_table_from_legend(
        [{"label": 1, "name": "a", "color": "#ff0000"},
         {"label": 2, "name": "b", "color": "#00ff00"}]
    )
    blob = gifti.encode_surface(SQUARE, None, labels, table)
    arrays = _arrays(blob)
    assert "NIFTI_INTENT_TRIANGLE" not in arrays
    np.testing.assert_array_equal(
        _values(arrays["NIFTI_INTENT_LABEL"], "<i4"), labels.astype(np.int32)
    )


def test_the_label_array_carries_its_field_name() -> None:
    """The layer's ``label.name`` is the node-field name, i.e. this string.

    The engine falls back to a short form of the intent when a ``DataArray``
    has no ``Name`` metadata, which would name the field ``LABEL`` — readable,
    but not what the pane asks for by name.
    """
    labels = np.zeros(4, dtype=np.uint16)
    table = gifti.label_table_from_legend([])
    blob = gifti.encode_surface(SQUARE, None, labels, table, label_name="DK40")
    darray = _arrays(blob)["NIFTI_INTENT_LABEL"]
    names = [md.findtext("Name") for md in darray.iter("MD")]
    values = [md.findtext("Value") for md in darray.iter("MD")]
    assert names == ["Name"] and values == ["DK40"]


# ── the label table ──────────────────────────────────────────────────────────


def test_the_table_always_starts_with_no_region() -> None:
    """The trap decision E7 exists to avoid, and it is silent.

    The engine remaps a labelled array to a **dense index** — the row's
    *position* in the table — and maps a value the table does not name to dense
    ``0``. Put a real region in row 0 and every unlabelled vertex takes that
    region's colour: a whole cortex painted one colour, which looks plausible.
    """
    table = gifti.label_table_from_legend(
        [{"label": 7, "name": "cuneus", "color": "#123456"}]
    )
    assert [e.key for e in table] == [0, 7]
    assert table[0].name == "unlabelled"
    assert table[0].rgba[3] == 0.0, "the no-region row is transparent, not a colour"


def test_a_legend_row_claiming_label_zero_never_displaces_no_region() -> None:
    """``0`` means "no region" by convention across ``tit.scene``.

    A legend that also used it would put a named region at position 0 and take
    the "nothing" meaning with it.
    """
    table = gifti.label_table_from_legend(
        [
            {"label": 0, "name": "unknown", "color": "#000000"},
            {"label": 1, "name": "bankssts", "color": "#19c8ff"},
        ]
    )
    assert [e.key for e in table] == [0, 1]
    assert table[0].name == "unlabelled"


def test_the_table_carries_the_atlas_colours_as_zero_to_one_floats() -> None:
    """GIfTI writes 0..1; the engine's ``unit_to_u8`` reads 0..1 *or* 0..255.

    It resolves the ambiguity by ``x <= 1.0``, so a colour written as 0..255
    would come back as 1/255 of itself for every channel below 1 — a nearly
    black atlas.
    """
    table = gifti.label_table_from_legend(
        [{"label": 1, "name": "x", "color": "#ff8000"}]
    )
    blob = gifti.encode_surface(SQUARE, None, np.ones(4, dtype=np.uint16), table)
    row = _tree(blob).find("LabelTable/Label[@Key='1']")
    assert row is not None
    assert float(row.get("Red", "0")) == pytest.approx(1.0)
    assert float(row.get("Green", "0")) == pytest.approx(128 / 255, abs=1e-6)
    assert float(row.get("Blue", "0")) == pytest.approx(0.0)
    assert float(row.get("Alpha", "0")) == pytest.approx(1.0)


def test_a_region_name_with_xml_characters_survives() -> None:
    """Region names come from a ``.annot`` this repository did not write."""
    table = gifti.label_table_from_legend(
        [{"label": 1, "name": "G&S_front-inf <Triangul>", "color": "#101010"}]
    )
    blob = gifti.encode_surface(SQUARE, None, np.ones(4, dtype=np.uint16), table)
    parsed = _tree(blob).find("LabelTable/Label[@Key='1']")
    assert parsed is not None
    assert (parsed.text or "").strip() == "G&S_front-inf <Triangul>"


def test_a_surface_with_no_labels_still_declares_an_empty_table() -> None:
    """``<LabelTable/>`` is what the reference surfaces carry.

    The engine's parser treats a self-closing ``<LabelTable/>`` as "no table";
    omitting the element entirely is legal GIfTI but is the one shape neither
    the engine's tests nor the reference data exercise.
    """
    blob = gifti.encode_surface(SQUARE, TRIS)
    assert b"<LabelTable/>" in blob
    assert _tree(blob).find("LabelTable") is not None


# ── the guards, each with what it prevents ───────────────────────────────────


def test_a_non_finite_coordinate_is_refused() -> None:
    """A ``NaN`` collapses the engine's bounding box: the pane frames nothing."""
    bad = SQUARE.copy()
    bad[2, 1] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        gifti.encode_surface(bad, TRIS)


def test_an_index_past_the_last_vertex_is_refused_here_not_there() -> None:
    """The engine refuses it too — by failing the whole load, unnamed.

    ``read()`` walks every triangle and errors with "GIfTI triangle references
    vertex N of M", which names neither the subject nor the surface. Refusing
    here names both.
    """
    with pytest.raises(ValueError, match="out of range"):
        gifti.encode_surface(SQUARE, np.array([[0, 1, 9]], dtype=np.uint32))


def test_labels_without_a_table_are_refused() -> None:
    """A labelled array with no ``<LabelTable>`` is not a mistake the engine reports.

    Its remap only fires when the file carried a table; without one the values
    stay continuous and the cortex is painted through a colormap. It renders,
    it just is not the atlas.
    """
    with pytest.raises(ValueError, match="label_table"):
        gifti.encode_surface(SQUARE, None, np.zeros(4, dtype=np.uint16))


def test_labels_that_do_not_align_with_the_vertices_are_refused() -> None:
    table = gifti.label_table_from_legend([])
    with pytest.raises(ValueError, match="to align with positions"):
        gifti.encode_surface(SQUARE, None, np.zeros(3, dtype=np.uint16), table)


def test_a_positions_array_of_the_wrong_shape_is_refused() -> None:
    with pytest.raises(ValueError, match=r"\(V, 3\)"):
        gifti.encode_surface(np.zeros((4, 2), dtype=np.float32))


# ── the document itself ──────────────────────────────────────────────────────


def test_the_document_is_well_formed_utf8_xml_the_sniffer_recognises() -> None:
    """The embed never sees a file name: the format is sniffed from the bytes.

    ``sniff()`` asks ``gifti::looks_like`` before it looks at any extension
    hint, which is what lets ``/api/scene/surface?subject=…&format=gii`` be a
    URL with no ``.gii`` in it.
    """
    blob = gifti.encode_surface(SQUARE, TRIS)
    assert blob.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert b"<GIFTI " in blob[:400]
    assert re.search(rb'Version="1\.0"', blob[:400])
    blob.decode("utf-8")  # the reader rejects anything that is not UTF-8 XML
    assert _tree(blob).tag == "GIFTI"


def test_the_payload_is_zlib_not_gzip() -> None:
    """``GZipBase64Binary`` is a **zlib** stream despite the name.

    The engine inflates it with a ``ZlibDecoder``; a gzip stream fails on its
    first byte, and the whole surface fails to load.
    """
    darray = _arrays(gifti.encode_surface(SQUARE, TRIS))["NIFTI_INTENT_POINTSET"]
    raw = base64.b64decode((darray.findtext("Data") or "").strip())
    assert raw[:2] != b"\x1f\x8b", "that is a gzip header, which the engine cannot read"
    assert zlib.decompress(raw) == SQUARE.tobytes()


def test_a_float64_input_is_written_as_float32() -> None:
    """``build`` works in float64 and the wire is float32, as ``TVSC1`` was.

    Declaring ``NIFTI_TYPE_FLOAT32`` over float64 bytes would read every second
    word as a coordinate — a surface of noise, with no error.
    """
    blob = gifti.encode_surface(SQUARE.astype(np.float64), TRIS)
    darray = _arrays(blob)["NIFTI_INTENT_POINTSET"]
    assert darray.get("DataType") == "NIFTI_TYPE_FLOAT32"
    np.testing.assert_array_equal(_values(darray, "<f4"), SQUARE)
