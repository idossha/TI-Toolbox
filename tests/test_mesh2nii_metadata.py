"""Pin mesh discovery on metadata-bearing filesystems (2026-09-13) and which meshes convert.

Authored temporary filenames test discovery; a parser-boundary exception tests
error propagation. Run: python3 -m pytest tests/test_mesh2nii_metadata.py -q
Real SimNIBS interpolation and native AppleDouble creation are outside this test.

2026-10-22 (p04 "mesh2nii-normal-substring"): the simulator leaves in one mesh directory
the volume meshes (``<name>_TI.msh``, ``grey_<name>_TI.msh``, ``white_<name>_TI.msh``;
``<name>_mTI.msh`` and its copies for mTI) and one surface-only mesh (``<name>_normal.msh``
or ``<name>_mTI_normal.msh``, ``tit/sim/base.py`` ``_write_ti_normal``), which has no
volume elements and is the only one to skip; the HF directory holds
``<sid>_TDCS_<i>_<cond>.msh``. A substring test for "normal" skipped every mesh of a montage
called "abnormal" and every carrier of a subject called "normal01". Expected tasks follow
mesh2nii's documented rule (``<base>_subject``, plus ``<base>_MNI``), pinned against Dataset
000 by ``test_task_prefixes_match_dataset_000_niftis``
(``TIT_DATASET_000=/path/to/000 python3 -m pytest tests/test_mesh2nii_metadata.py -q``).
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tit.tools.mesh2nii import _collect_tasks, _mni_worker, _subject_worker


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


# ── which meshes become NIfTIs ───────────────────────────────────────────────


def _volume_meshes(name: str, mode: str) -> list[str]:
    stem = f"{name}_{mode}"
    return [f"{stem}.msh", f"grey_{stem}.msh", f"white_{stem}.msh"]


def _surface_mesh(name: str, mode: str) -> str:
    return f"{name}_normal.msh" if mode == "TI" else f"{name}_mTI_normal.msh"


def _expected(out: Path, bases: list[str], map_to_mni: bool) -> set[tuple]:
    tasks = {
        (_subject_worker, f"{base}.msh", str(out / f"{base}_subject")) for base in bases
    }
    if map_to_mni:
        tasks |= {
            (_mni_worker, f"{base}.msh", str(out / f"{base}_MNI")) for base in bases
        }
    return tasks


def _collected(mesh_dir: Path, out: Path, map_to_mni: bool) -> set[tuple]:
    tasks, temporary = _collect_tasks(str(mesh_dir), str(out), None, None, map_to_mni)
    assert temporary == []
    return {(fn, os.path.basename(src), prefix) for fn, src, prefix in tasks}


@pytest.mark.parametrize("map_to_mni", [False, True])
@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize(
    "name", ["abnormal", "normal_sham", "L_Insula", "normal", "x_normal"]
)
def test_every_volume_mesh_is_converted_and_only_the_surface_mesh_skipped(
    tmp_path, name, mode, map_to_mni
):
    mesh_dir = tmp_path / "mesh"
    mesh_dir.mkdir()
    volumes = _volume_meshes(name, mode)
    for fname in [*volumes, _surface_mesh(name, mode)]:
        (mesh_dir / fname).write_bytes(b"mesh")
    out = tmp_path / "niftis"

    got = _collected(mesh_dir, out, map_to_mni)

    bases = [v.removesuffix(".msh") for v in volumes]
    assert got == _expected(out, bases, map_to_mni)
    assert len(got) == 3 * (2 if map_to_mni else 1)


@pytest.mark.parametrize("sid", ["normal01", "101", "abnormal"])
@pytest.mark.parametrize("cond", ["scalar", "vn"])
def test_carrier_meshes_are_converted_whatever_the_subject_is_called(
    tmp_path, sid, cond
):
    mesh_dir = tmp_path / "hf"
    mesh_dir.mkdir()
    bases = [f"{sid}_TDCS_{i}_{cond}" for i in (1, 2)]
    for base in bases:
        (mesh_dir / f"{base}.msh").write_bytes(b"mesh")
    out = tmp_path / "niftis"

    assert _collected(mesh_dir, out, True) == _expected(out, bases, True)


def test_explicit_skip_patterns_still_match_by_substring(tmp_path):
    """A caller's own skip_patterns keep their documented substring meaning."""
    (tmp_path / "keep_TI.msh").write_bytes(b"mesh")
    (tmp_path / "draft_TI.msh").write_bytes(b"mesh")
    tasks, _ = _collect_tasks(
        str(tmp_path), str(tmp_path / "out"), None, ["draft"], False
    )
    assert [os.path.basename(src) for _, src, _ in tasks] == ["keep_TI.msh"]


_DATASET = os.environ.get("TIT_DATASET_000")


@pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_task_prefixes_match_dataset_000_niftis(tmp_path):
    """The subject-space prefixes _collect_tasks makes are exactly those the real NIfTIs carry.

    The mesh file *names* of each Dataset 000 simulation are touched into tmp_path (the
    dataset is only listed); each subject-space NIfTI on disk is ``<prefix>_<field>.nii.gz``.
    """
    root = Path(_DATASET) / "derivatives" / "SimNIBS"
    sims = sorted(root.glob("sub-*/Simulations/*"))
    pairs = [
        (sim / sub / "mesh", sim / sub / "niftis")
        for sim in sims
        for sub in ("TI", "high_Frequency")
        if (sim / sub / "niftis").is_dir()
    ]
    assert len(pairs) >= 10
    before = {p: p.stat().st_mtime_ns for d, _ in pairs for p in d.iterdir()}
    for i, (mesh_dir, nifti_dir) in enumerate(pairs):
        copy = tmp_path / str(i)
        copy.mkdir()
        for p in mesh_dir.iterdir():
            if p.is_file() and p.name.endswith(".msh"):
                (copy / p.name).write_bytes(b"")
        tasks, _ = _collect_tasks(str(copy), str(tmp_path / "out"), None, None, False)
        prefixes = {os.path.basename(prefix) for _, _, prefix in tasks}
        on_disk = {
            p.name.rsplit("_subject_", 1)[0] + "_subject"
            for p in nifti_dir.iterdir()
            if "_subject_" in p.name and p.name.endswith(".nii.gz")
        }
        assert on_disk and prefixes == on_disk, mesh_dir
    assert before == {p: p.stat().st_mtime_ns for d, _ in pairs for p in d.iterdir()}
