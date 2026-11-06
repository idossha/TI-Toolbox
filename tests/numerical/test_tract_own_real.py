"""A user's own streamline file against a synthetic head model, with the real file readers (2026-11-06).

What this pins
    :func:`tit.tract.own.store` keeps a TCK, a TRK and a TRX that lie inside the brain, with their
    numbers, and refuses one shifted out of the head, one with no streamlines and one that is not a
    streamline file, leaving nothing behind. Coordinates are not transformed.

Where the numbers come from
    The head model is written here: a 40 x 40 x 40 mm box of tissue label 1 in a 60 mm volume of
    label 5, and the streamlines are straight lines of known position, so the fractions are counted by
    hand. ``tests/test_tract_routes.py`` holds the route; the real files on sub-CHN are in
    ``desktop/tests/e2e/real/network-own-file.spec.ts``.

Run: docker exec -w /ti-toolbox <c> simnibs_python -m pytest tests/numerical/test_tract_own_real.py -q
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.tract import own
from tit.tract.io import load_streamlines, save_tractogram


@pytest.fixture
def head(tmp_path: Path, monkeypatch):
    """A project of one subject whose brain is the box -20..20 mm; labels come from a stub atlas."""
    nib = pytest.importorskip("nibabel")
    data = np.full((60, 60, 60), 5, dtype=np.uint8)
    data[10:50, 10:50, 10:50] = 1
    affine = np.eye(4)
    affine[:3, 3] = -30.0
    m2m = tmp_path / "m2m"
    m2m.mkdir()
    nib.save(nib.Nifti1Image(data, affine), m2m / "final_tissues.nii.gz")
    pm = SimpleNamespace(
        m2m=lambda sid: str(m2m),
        tractography=lambda sid: str(tmp_path / "tractography"),
    )
    # Two regions at x = +/-15: an end within 3 mm of one takes it.
    monkeypatch.setattr(
        own,
        "region_points",
        lambda *a: (
            np.array([[-15.0, 0, 0], [15.0, 0, 0]]),
            np.array([0, 1]),
            ["lh.a", "rh.b"],
        ),
    )
    monkeypatch.setattr(own, "default_label_volume", lambda *a: None)
    return pm, affine, data


#: One streamline joining both regions, and one whose second end is near neither.
LINES = [
    np.array([[-15.0, 0, 0], [0, 0, 0], [15.0, 0, 0]], np.float32),
    np.array([[-15.0, 5, 0], [0, 5, 0], [0, 5, 10]], np.float32),
]


def _written(tmp_path: Path, name: str, head, lines=LINES) -> Path:
    nib = pytest.importorskip("nibabel")
    _pm, affine, data = head
    ref = nib.Nifti1Image(data, affine)
    path = tmp_path / name
    save_tractogram(str(path), lines, ref)
    return path


@pytest.mark.parametrize("name", ["mine.tck", "mine.trk", "mine.trx"])
def test_a_file_inside_the_brain_is_kept_with_its_numbers(tmp_path, head, name) -> None:
    pm = head[0]
    record = own.store(pm, "x", _written(tmp_path, name, head), name)
    assert record["name"] == "mine"
    assert record["source_filename"] == name
    assert record["n_streamlines"] == 2
    assert record["n_both_ends_labelled"] == 1
    assert record["n_unlabelled"] == 1
    assert record["checks"]["fraction_points_in_brain"] == 1.0
    assert record["checks"]["fraction_points_in_head"] == 1.0
    assert "cannot prove" in record["checks"]["not_proven"]
    assert own.list_own(pm, "x") == [record]
    # Read back as written: nothing was transformed.
    kept, network = own.load_own(pm, "x", "mine")
    np.testing.assert_allclose(kept[0], LINES[0], atol=1e-3)
    assert len(network["labels"]) == 2
    pairs, counts, unlabelled = own.own_counts(pm, "x", "mine")
    assert pairs == [["lh.a", "rh.b"]]
    assert counts == {("lh.a", "rh.b"): 1}
    assert unlabelled == 1


def test_a_file_in_another_space_is_refused_and_leaves_nothing(tmp_path, head) -> None:
    pm = head[0]
    shifted = [s + np.array([200.0, 0, 0], np.float32) for s in LINES]
    path = _written(tmp_path, "far.tck", head, shifted)
    with pytest.raises(own.OwnNetworkError, match=r"Only 0.0% .*at least 95%"):
        own.store(pm, "x", path, "far.tck")
    assert own.list_own(pm, "x") == []
    assert not own.own_dir(pm, "x").exists()


def test_a_shift_that_stays_in_the_head_but_leaves_the_brain_is_refused(tmp_path, head) -> None:
    # Half of each line past the box's edge at 20 mm, still inside the 30 mm volume.
    near = [s + np.array([0, 18.0, 0], np.float32) for s in [np.array([[-15.0, 0, 0], [0, 4, 0], [15.0, 6, 0]], np.float32)]]
    with pytest.raises(own.OwnNetworkError, match="inside this head model's brain"):
        own.store(head[0], "x", _written(tmp_path, "near.tck", head, near), "near.tck")


def test_an_empty_tractogram_and_a_file_that_is_not_one_are_refused(tmp_path, head) -> None:
    nib = pytest.importorskip("nibabel")
    pm = head[0]
    empty = tmp_path / "empty.tck"
    ref = nib.Nifti1Image(head[2], head[1])
    from dipy.io.stateful_tractogram import Space, StatefulTractogram
    from dipy.io.streamline import save_tractogram as dipy_save

    dipy_save(StatefulTractogram([], ref, Space.RASMM), str(empty), bbox_valid_check=False)
    with pytest.raises(own.OwnNetworkError, match="holds no streamlines"):
        own.store(pm, "x", empty, "empty.tck")
    junk = tmp_path / "junk.tck"
    junk.write_bytes(b"not a tractogram")
    with pytest.raises(own.OwnNetworkError, match="could not be read"):
        own.store(pm, "x", junk, "junk.tck")


def test_the_same_name_with_other_contents_is_refused_and_the_same_file_is_a_no_op(tmp_path, head) -> None:
    pm = head[0]
    first = own.store(pm, "x", _written(tmp_path, "a.tck", head), "mine.tck")
    again = own.store(pm, "x", _written(tmp_path, "b.tck", head), "mine.tck")
    assert again == first
    other = _written(tmp_path, "c.tck", head, LINES[:1])
    with pytest.raises(own.OwnNetworkError, match="already holds another file"):
        own.store(pm, "x", other, "mine.tck")


def test_a_file_name_is_made_safe_and_only_streamline_files_pass() -> None:
    assert own.stored_name("../../my net (1).TCK") == ("my_net__1", ".tck")
    with pytest.raises(own.OwnNetworkError, match="not a streamline file"):
        own.stored_name("mask.nii.gz")
    with pytest.raises(own.OwnNetworkError, match="no usable name"):
        own.stored_name("(((.trx")
