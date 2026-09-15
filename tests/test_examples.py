"""``tit.examples.fetch_ernie`` -- the on-demand SimNIBS example subject.

No network: the URL opener is monkeypatched to serve a tiny synthetic zip whose members mirror
the real ``v4.1/simnibs4_examples.zip`` layout (``m2m_ernie/``, ``org/ernie_T1.nii.gz`` at the
archive root, no top-level folder). The sha256 constant is patched to that archive's digest;
``test_sha_mismatch_rejected`` leaves it alone and checks nothing is written.

Reproduce: ``python3 -m pytest -q tests/test_examples.py``.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from tit import examples


def _archive() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("m2m_ernie/ernie.msh", b"mesh")
        zf.writestr("m2m_ernie/T1.nii.gz", b"t1")
        zf.writestr("m2m_ernie/segmentation/labeling.nii.gz", b"lab")
        zf.writestr("m2m_ernie/eeg_positions/EEG10-10_UI_Jurak_2007.csv", b"csv")
        zf.writestr("m2m_MNI152/MNI152.msh", b"not wanted")
        zf.writestr("org/ernie_T1.nii.gz", b"rawT1")
        zf.writestr("org/ernie_T2.nii.gz", b"rawT2")
        zf.writestr("org/ernie_dMRI.nii.gz", b"not wanted")
        zf.writestr("readme.txt", b"not wanted")
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def served(monkeypatch):
    data = _archive()
    calls: list[str] = []

    def fake_urlopen(url):
        calls.append(url)
        return _Resp(data)

    monkeypatch.setattr(examples.urllib.request, "urlopen", fake_urlopen)
    return data, calls


@pytest.fixture
def pinned(served, monkeypatch):
    data, calls = served
    monkeypatch.setattr(examples, "RELEASE_SHA256", hashlib.sha256(data).hexdigest())
    return calls


def test_layout_matches_path_manager(tmp_path: Path, pinned, capsys):
    from tit.paths import get_path_manager
    from tit.pre import check_m2m_exists

    m2m = examples.fetch_ernie(tmp_path)

    pm = get_path_manager(str(tmp_path))
    assert str(m2m) == pm.m2m("ernie")
    assert check_m2m_exists(str(tmp_path), "ernie")
    assert (m2m / "ernie.msh").read_bytes() == b"mesh"
    assert (m2m / "segmentation" / "labeling.nii.gz").read_bytes() == b"lab"
    assert (tmp_path / "sub-ernie" / "anat" / "sub-ernie_T1w.nii.gz").read_bytes() == b"rawT1"
    assert (tmp_path / "sub-ernie" / "anat" / "sub-ernie_T2w.nii.gz").read_bytes() == b"rawT2"
    assert not (tmp_path / "derivatives" / "SimNIBS" / "sub-MNI152").exists()
    assert not (tmp_path / "readme.txt").exists()
    assert (tmp_path / "dataset_description.json").exists()
    assert (tmp_path / "derivatives" / "SimNIBS" / "dataset_description.json").exists()
    status = json.loads((tmp_path / "code" / "ti-toolbox" / "config" / "project_status.json").read_text())
    assert status["example_subjects"] == ["ernie"]
    assert pinned == [examples.RELEASE_URL]
    assert "download 100%" in capsys.readouterr().out


def test_idempotent_skip(tmp_path: Path, pinned):
    examples.fetch_ernie(tmp_path)
    examples.fetch_ernie(tmp_path)
    assert pinned == [examples.RELEASE_URL], "second call must not download"
    examples.fetch_ernie(tmp_path, force=True)
    assert len(pinned) == 2


def test_sha_mismatch_rejected(tmp_path: Path, served):
    with pytest.raises(ValueError, match="sha256 mismatch"):
        examples.fetch_ernie(tmp_path)
    assert not (tmp_path / "derivatives").exists()
    assert not (tmp_path / "sub-ernie").exists()


def test_cli(tmp_path: Path, pinned):
    assert examples.main(["--project", str(tmp_path)]) == 0
    assert (tmp_path / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie").is_dir()


def test_cli_reports_bad_archive(tmp_path: Path, served, capsys):
    assert examples.main(["--project", str(tmp_path)]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err


def test_project_init_runner_fetches_when_asked(tmp_path: Path, pinned):
    from tit.project_init.__main__ import main

    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"project_dir": str(project), "example_subject": True}))
    assert main([str(config)]) == 0
    assert (project / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie" / "ernie.msh").exists()
    assert pinned == [examples.RELEASE_URL]
