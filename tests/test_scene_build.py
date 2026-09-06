"""``tit.scene.build``'s pure core and cached-GM label build (2026-09-04).

What this pins
    The three functions whose bug would be invisible in a picture: the EEG-net
    CSV split (a mis-parsed row puts an electrode at the wrong coordinate), the
    LUT parse (a legend that disagrees with the optimizer's ROI dropdown), and
    :func:`tit.scene.build.labels_from_nearest` (the step where a region pick
    starts highlighting the wrong region).

Where the numbers come from
    Hand-authored fixtures whose answers are arithmetic: the CSV rows are
    stated inline with the coordinates they must produce, and the
    nearest-neighbour inputs are computed here by a brute-force
    ``argmin(|a-b|)`` over a 1-D point set -- an independent implementation of
    what ``scipy.spatial.cKDTree`` does in the real builder, which this suite
    cannot run (``scipy`` is a ``MagicMock`` here).

    The cached-GM regression reuses ``desktop/tests/fixtures/scene/``: its
    manifest gives the authored TVSC1 position formula, triangles and labels.
    The real builder reads the cached TVSC1 bytes; stdlib XML/base64/zlib reads
    its GIfTI output independently. Coordinates are subject-RAS millimetres;
    this is a serialization check, not a transform or resampling test.

How to run it
    ``python -m pytest -q tests/test_scene_build.py``. The existing fixtures
    regenerate with ``python tests/scene/make_fixtures.py``; no real data or
    environment variable is required.

Deliberately elsewhere
    Anything that needs a real mesh, a real ``.annot`` or a real KD-tree is
    ``tests/test_scene_realdata.py``, gated on ``TIT_SCENE_TESTDATA``.
"""

from __future__ import annotations

import base64
import json
import os
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np
import pytest

from tit.paths import get_path_manager
from tit.scene import build, cache

REAL_NET_ROWS = (
    # Verbatim shape of m2m_ernie/eeg_positions/EEG10-10_UI_Jurak_2007.csv
    "Electrode,-26.080394138417162,113.65480801883132,19.072867841317812,Fp1\n"
    "Electrode,1.8719770962212081,116.90152796730355,22.641229752023637,Fpz\n"
    "ReferenceElectrode,0.0,0.0,90.0,Cz\n"
    "Fiducial,2.0886058524158653,114.04901772235128,-12.885007640211896,Nz\n"
)


# ── the EEG net CSV ──────────────────────────────────────────────────────────


def test_electrode_rows_are_split_by_type() -> None:
    parsed = build.parse_electrode_csv(REAL_NET_ROWS)
    assert [e["name"] for e in parsed["electrodes"]] == ["Fp1", "Fpz"]
    assert [e["name"] for e in parsed["reference"]] == ["Cz"]
    assert [e["name"] for e in parsed["fiducials"]] == ["Nz"]


def test_electrode_coordinates_keep_full_precision_in_xyz_order() -> None:
    """An x/z swap here puts every marker on the wrong side of the head."""
    first = build.parse_electrode_csv(REAL_NET_ROWS)["electrodes"][0]
    assert first["world"] == pytest.approx(
        [-26.080394138417162, 113.65480801883132, 19.072867841317812], abs=0.0
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n",
        "Electrode,1,2\n",  # short row
        "Electrode,x,y,z,Fp1\n",  # unparseable coordinates
        "Electrode,1,2,nan,Fp1\n",  # NaN would collapse the renderer's bounds
        "Comment,1,2,3,ignored\n",  # unknown row type
    ],
)
def test_a_malformed_row_is_skipped_not_fatal(text: str) -> None:
    """charm's files occasionally carry a trailing blank line."""
    parsed = build.parse_electrode_csv(text)
    assert parsed == {"electrodes": [], "reference": [], "fiducials": []}


def test_a_malformed_row_does_not_lose_the_good_ones() -> None:
    parsed = build.parse_electrode_csv("Electrode,1,2\n" + REAL_NET_ROWS)
    assert len(parsed["electrodes"]) == 2


# ── the label volume LUT ─────────────────────────────────────────────────────


LUT_TEXT = (
    "#No.\t  Label Name:\t\t\t   R   G   B   A\n"
    "\n"
    "2\t  Left-Cerebral-White-Matter       245 245 245 255 \n"
    "3\t  Left-Cerebral-Cortex     \t   205 62 78 255 \n"
    "10\t  Left-Thalamus-Proper     \t   0 118 14 255 \n"
)


def test_lut_entries_carry_id_name_and_hex_colour() -> None:
    entries = build.parse_lut_text(LUT_TEXT)
    assert entries == [
        {"id": 2, "name": "Left-Cerebral-White-Matter", "color": "#f5f5f5"},
        {"id": 3, "name": "Left-Cerebral-Cortex", "color": "#cd3e4e"},
        {"id": 10, "name": "Left-Thalamus-Proper", "color": "#00760e"},
    ]


def test_lut_comments_and_blank_lines_are_skipped() -> None:
    assert build.parse_lut_text("# only a comment\n\n   \n") == []


def test_a_duplicated_lut_id_keeps_the_first_definition() -> None:
    """Two legend entries for one voxel value would render as two swatches."""
    entries = build.parse_lut_text(LUT_TEXT + "2\t  Something-Else 1 2 3 255\n")
    assert [e["id"] for e in entries] == [2, 3, 10]
    assert entries[0]["name"] == "Left-Cerebral-White-Matter"


def test_a_lut_row_without_colours_still_names_the_region() -> None:
    entries = build.parse_lut_text("7\t  Left-Cerebellum-White-Matter\n")
    assert entries == [
        {"id": 7, "name": "Left-Cerebellum-White-Matter", "color": None}
    ]


# ── the label transfer ───────────────────────────────────────────────────────


def _brute_force_nearest(
    query: np.ndarray, reference: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``(distance, index)`` by exhaustive search -- not the builder's KD-tree."""
    delta = np.linalg.norm(query[:, None, :] - reference[None, :, :], axis=2)
    index = delta.argmin(axis=1)
    return delta[np.arange(len(query)), index], index


def test_labels_are_copied_from_the_nearest_reference_vertex() -> None:
    reference = np.array([[0.0, 0, 0], [10.0, 0, 0], [20.0, 0, 0]])
    reference_labels = np.array([5, 6, 7], dtype=np.uint16)
    #                 0.5 from #0     1.0 from #1     0.2 from #2     5.0 from both
    query = np.array([[0.5, 0, 0], [9.0, 0, 0], [20.2, 0, 0], [5.0, 0, 0]])

    distance, index = _brute_force_nearest(query, reference)
    labels = build.labels_from_nearest(index, distance, reference_labels, radius=2.0)
    np.testing.assert_array_equal(labels, [5, 6, 7, 0])


def test_a_vertex_beyond_the_radius_is_unlabelled_not_mislabelled() -> None:
    """The cerebellum case: 7.35 % of ernie's GM has no cortical region at all.

    Borrowing the least-far cortical label instead would paint cerebellum with
    an occipital region and a user's ROI would silently include it.
    """
    reference = np.array([[0.0, 0, 0]])
    reference_labels = np.array([9], dtype=np.uint16)
    query = np.array([[1.0, 0, 0], [2.9, 0, 0], [3.1, 0, 0], [45.0, 0, 0]])

    distance, index = _brute_force_nearest(query, reference)
    labels = build.labels_from_nearest(
        index, distance, reference_labels, radius=build.LABEL_RADIUS_MM
    )
    np.testing.assert_array_equal(labels, [9, 9, 0, 0])
    assert build.NO_REGION == 0


def test_the_label_array_is_uint16_and_aligned_to_the_query_order() -> None:
    """One label per served vertex, in the served order -- §2.3's flags bit0."""
    reference = np.array([[0.0, 0, 0], [1.0, 0, 0]])
    reference_labels = np.array([65535, 1], dtype=np.uint16)
    query = np.array([[1.0, 0, 0], [0.0, 0, 0], [0.4, 0, 0]])

    distance, index = _brute_force_nearest(query, reference)
    labels = build.labels_from_nearest(index, distance, reference_labels, radius=1.0)
    assert labels.dtype == np.uint16
    assert labels.shape == (3,)
    np.testing.assert_array_equal(labels, [1, 65535, 65535])


def test_build_labels_keeps_the_cached_gm_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a builder/decoder field mismatch before a cold atlas returns 500.

    Unlike the route stubs, this calls the real builder on an actual cached
    TVSC1 surface. Only the annotation input and native KD-tree are replaced;
    the cache, decoder, label transfer and GIfTI writer all run unchanged.
    """
    fixtures = Path(__file__).resolve().parents[1] / "desktop/tests/fixtures/scene"
    manifest = json.loads((fixtures / "fixtures.json").read_text())
    surface = manifest["fixtures"]["tri-surface.tvsc"]
    formula = surface["positionFormula"]
    index = np.arange(surface["vertexCount"], dtype=np.float64)
    positions = np.column_stack(
        (
            index * formula["stepX"],
            formula["originY"] - index * formula["stepY"],
            formula["originZ"] + index * index * formula["stepZ"],
        )
    )
    labels = np.asarray(
        manifest["fixtures"]["labelled-surface.tvsc"]["labels"], dtype=np.uint16
    )
    legend = [
        {"label": int(label), "name": f"region-{label}", "color": "#123456"}
        for label in np.unique(labels)
        if label != 0
    ]
    pm = get_path_manager(str(tmp_path))
    sid, atlas = "synthetic", "DK40"
    surface_fp = build.surface_fingerprint(pm, sid)
    cache.publish(
        tmp_path,
        sid,
        "gm",
        surface_fp,
        (fixtures / "tri-surface.tvsc").read_bytes(),
        {},
    )

    def refuse_surface_rebuild(*args):
        pytest.fail("build_labels must read the existing cached GM")

    class BruteForceTree:
        def __init__(self, reference):
            self.reference = reference

        def query(self, query, *, workers):
            return _brute_force_nearest(query, self.reference)

    monkeypatch.setattr(build, "build_surfaces", refuse_surface_rebuild)
    monkeypatch.setattr(
        build, "_load_reference_labels", lambda *args: (positions, labels, legend)
    )
    monkeypatch.setattr("scipy.spatial.cKDTree", BruteForceTree)

    meta = build.build_labels(pm, sid, atlas)
    cached = cache.find_cached(
        tmp_path,
        sid,
        build._labels_key(atlas),
        build.labels_fingerprint(pm, sid, atlas),
        "gii",
    )
    assert cached is not None
    arrays = {}
    for array in ET.fromstring(cached.path.read_bytes()).findall("DataArray"):
        raw = zlib.decompress(base64.b64decode(array.findtext("Data") or ""))
        dims = tuple(
            int(array.attrib[f"Dim{i}"])
            for i in range(int(array.attrib["Dimensionality"]))
        )
        dtype = "<f4" if array.attrib["DataType"] == "NIFTI_TYPE_FLOAT32" else "<i4"
        arrays[array.attrib["Intent"]] = np.frombuffer(raw, dtype=dtype).reshape(dims)

    assert set(arrays) == {
        "NIFTI_INTENT_POINTSET",
        "NIFTI_INTENT_TRIANGLE",
        "NIFTI_INTENT_LABEL",
    }
    # The fixture's quarters/halves are exactly representable as float32;
    # serialization must preserve every value, so no numeric tolerance applies.
    np.testing.assert_array_equal(arrays["NIFTI_INTENT_POINTSET"], positions)
    np.testing.assert_array_equal(arrays["NIFTI_INTENT_TRIANGLE"], surface["triangles"])
    np.testing.assert_array_equal(arrays["NIFTI_INTENT_LABEL"], labels)
    assert meta["triangles"] == len(surface["triangles"])
    assert meta["aligned_to_fingerprint"] == surface_fp


# ── source-file resolution and readable failures ─────────────────────────────


def test_head_mesh_path_names_the_missing_file_and_the_fix(tmp_path: Path) -> None:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("bare"))
    with pytest.raises(build.SceneUnavailable, match="charm"):
        build.head_mesh_path(pm, "bare")


def test_label_sources_cover_the_mesh_the_annots_and_the_surfaces(
    tmp_path: Path,
) -> None:
    """A labels payload is stale if *any* of these five files changes."""
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("ernie"))
    sources = build.label_sources(pm, "ernie", "DK40")
    assert len(sources) == 5
    assert sources[0].endswith("ernie.msh")
    assert any("annot" in s for s in sources[1:3])
    assert any("gii" in s for s in sources[3:])


def test_the_labels_cache_key_cannot_escape_the_cache_directory() -> None:
    """An atlas id reaches the filesystem as part of a file name."""
    assert build._labels_key("DK40") == "labels-DK40"
    assert "/" not in build._labels_key("../../etc/passwd")
    assert ".." not in build._labels_key("../../etc/passwd").replace("_", "")


def test_reading_a_net_refuses_a_path_instead_of_a_name(tmp_path: Path) -> None:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.eeg_positions("ernie"))
    with pytest.raises(build.SceneUnavailable, match="not a net file name"):
        build.read_net(pm, "ernie", "../../../etc/passwd")


def test_the_scene_budget_is_the_one_decision_s3_states() -> None:
    """A silently raised budget is how a 4 MB payload ships."""
    assert build.MAX_TRIANGLES == 150_000
    assert build.MAX_BYTES == 3 * 1024 * 1024
    assert build.PART_TAGS == {"skin": 1005, "gm": 1002}


@pytest.mark.parametrize(
    "atlas_id",
    ["../../../../etc/passwd", "DK40/../..", "a\\b", "*", "", "x" * 100],
)
def test_an_atlas_id_never_reaches_a_glob_unchecked(
    tmp_path: Path, atlas_id: str
) -> None:
    """``find_atlas_file`` interpolates the id into a glob, and globs walk ``..``.

    Without the two membership checks in ``annot_paths`` this is a read of any
    ``lh.*.annot`` on the machine, aimed by a query parameter.
    """
    pm = get_path_manager(str(tmp_path))
    os.makedirs(os.path.join(pm.m2m("ernie"), "segmentation"))
    assert build.annot_paths(pm, "ernie", atlas_id) == {}


def test_an_atlas_the_subject_does_not_have_resolves_to_nothing(
    tmp_path: Path,
) -> None:
    """A builtin name with no file behind it is not an atlas this subject has."""
    pm = get_path_manager(str(tmp_path))
    os.makedirs(os.path.join(pm.m2m("ernie"), "segmentation"))
    assert build.annot_paths(pm, "ernie", "DK40") == {}


def test_the_lut_parse_matches_the_roi_pickers() -> None:
    """The drift guard for the one rule this module copies rather than imports.

    ``tit.scene.build._parse_lut_line`` is a copy of
    ``tit.opt.roi_spec._parse_lut_line`` (importing the original costs 3.2 s of
    ``simnibs``/optimizer import in the container -- see that function's
    docstring). Both are driven over the same lines here, including the awkward
    ones, so a change to either shows up as a failure rather than as a legend
    that disagrees with the ROI dropdown.
    """
    from tit.opt.roi_spec import _parse_lut_line as theirs

    from tit.scene.build import _parse_lut_line as ours

    lines = [
        "2\t  Left-Cerebral-White-Matter       245 245 245 255 ",
        "3\t  Left-Cerebral-Cortex     \t   205 62 78 255 ",
        "7  Left-Cerebellum-White-Matter",
        "-1  Negative-Id 1 2 3",
        "1000 Two Word Name 10 20 30 255",
        "not-a-number  Whatever 1 2 3",
        "5",
        "",
        "   ",
    ]
    assert [ours(line) for line in lines] == [theirs(line) for line in lines]
