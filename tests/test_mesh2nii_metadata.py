"""Pin mesh discovery on metadata-bearing filesystems (2026-09-13).

Authored temporary filenames test discovery; a parser-boundary exception tests
error propagation. Run: python3 -m pytest tests/test_mesh2nii_metadata.py -q
Real SimNIBS interpolation and native AppleDouble creation are outside this test.
"""

from unittest.mock import patch

import pytest

from tit.tools.mesh2nii import _collect_tasks


def test_collects_ordinary_mesh(tmp_path):
    mesh = tmp_path / "carrier.msh"
    mesh.write_bytes(b"mesh input")

    tasks, temporary = _collect_tasks(str(tmp_path), str(tmp_path / "out"), None, None)

    assert len(tasks) == 2
    assert [task[1] for task in tasks] == [str(mesh), str(mesh)]
    assert temporary == []


def test_ignores_appledouble_and_nonfile_mesh_entries(tmp_path):
    (tmp_path / "._carrier.msh").write_bytes(b"metadata")
    (tmp_path / "directory.msh").mkdir()

    tasks, temporary = _collect_tasks(
        str(tmp_path), str(tmp_path / "out"), ["magnE"], None
    )

    assert tasks == []
    assert temporary == []


def test_genuine_corrupt_mesh_parser_error_propagates(tmp_path):
    (tmp_path / "carrier.msh").write_bytes(b"\xff")
    error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    with patch("tit.tools.mesh2nii.mesh_io.read_msh", side_effect=error):
        with pytest.raises(UnicodeDecodeError) as raised:
            _collect_tasks(str(tmp_path), str(tmp_path / "out"), ["magnE"], None)

    assert raised.value is error


@pytest.mark.parametrize("map_to_mni", [False, True])
def test_conversion_workers_honor_mni_opt_in(tmp_path, map_to_mni):
    from tit.tools.mesh2nii import convert_mesh_dirs

    (tmp_path / "carrier.msh").write_bytes(b"mesh input")
    with (
        patch("tit.tools.mesh2nii._subject_worker") as subject,
        patch("tit.tools.mesh2nii._mni_worker") as mni,
    ):
        convert_mesh_dirs(
            [{"mesh_dir": str(tmp_path), "output_dir": str(tmp_path / "out")}],
            "/m2m",
            max_workers=1,
            map_to_mni=map_to_mni,
        )
    subject.assert_called_once()
    assert mni.call_count == int(map_to_mni)
